from __future__ import annotations

import contextlib
import logging
import os
import tempfile
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from os import fspath
from typing import Any

import tree_sitter
import tree_sitter_c
import tree_sitter_cpp
import tree_sitter_java
import tree_sitter_javascript
import tree_sitter_python
from git import Repo
from tqdm.auto import tqdm

from config import MAX_DIFF_SIZE, MAX_WORKERS
from dataset_entry import DatasetEntry
from utils.extensions import EXTENSION_TO_LANGUAGE
from utils.git.repository import clone_repositories

logger = logging.getLogger(__name__)

BATCH_SIZE = 200

# Comment node types for each language
COMMENT_NODE_TYPES: dict[str, set[str]] = {
    "python": {"comment"},
    "java": {"line_comment", "block_comment"},
    "javascript": {"comment", "line_comment", "block_comment"},
    "c": {"comment"},
    "cpp": {"comment"},
}

_LANGUAGE_MODULES: dict[str, Any] = {
    "python": tree_sitter_python,
    "java": tree_sitter_java,
    "javascript": tree_sitter_javascript,
    "c": tree_sitter_c,
    "cpp": tree_sitter_cpp,
}

# Lazy-loaded parsers cache (per-process)
_parsers: dict[str, tree_sitter.Parser] = {}


def _get_parser(language: str) -> tree_sitter.Parser | None:
    """Get or create a tree-sitter parser for the given language."""
    if language in _parsers:
        return _parsers[language]

    if language not in COMMENT_NODE_TYPES:
        return None

    module = _LANGUAGE_MODULES[language]
    parser = tree_sitter.Parser(tree_sitter.Language(module.language()))
    _parsers[language] = parser
    return parser


def _get_language(file_path: str) -> str | None:
    """Get language from file extension."""
    return next(
        (lang for ext, lang in EXTENSION_TO_LANGUAGE.items() if file_path.endswith(ext)), None
    )


def _strip_comments(source_code: str, language: str) -> str | None:
    """Remove comments from source code using tree-sitter."""
    if not source_code:
        return source_code

    parser = _get_parser(language)
    comment_types = COMMENT_NODE_TYPES.get(language)
    if not parser or not comment_types:
        return None

    try:
        source_bytes = source_code.encode("utf-8")
        tree = parser.parse(source_bytes)

        # Collect comment byte ranges
        comment_ranges: list[tuple[int, int]] = []

        def collect_comments(node: tree_sitter.Node) -> None:
            if node.type in comment_types:
                comment_ranges.append((node.start_byte, node.end_byte))
            for child in node.children:
                collect_comments(child)

        collect_comments(tree.root_node)

        if not comment_ranges:
            return source_code

        # Remove comments from end to start (preserves byte offsets)
        comment_ranges.sort(reverse=True)
        result = bytearray(source_bytes)

        for start, end in comment_ranges:
            # Find line boundaries
            line_start = result.rfind(b"\n", 0, start)
            line_start = 0 if line_start == -1 else line_start + 1
            line_end = result.find(b"\n", end)
            line_end = len(result) if line_end == -1 else line_end

            # Check if line is comment-only (whitespace + comment)
            before = result[line_start:start]
            after = result[end:line_end]

            if before.strip() == b"" and after.strip() == b"":
                # Remove entire line including newline
                if line_end < len(result):
                    line_end += 1
                del result[line_start:line_end]
            else:
                # Remove just the comment and preceding whitespace
                ws_start = start
                while ws_start > line_start and result[ws_start - 1 : ws_start] in (b" ", b"\t"):
                    ws_start -= 1
                del result[ws_start:end]

        return result.decode("utf-8")
    except Exception as e:
        logger.debug("Failed to strip comments for %s: %s", language, e)
        return None


def _generate_diff(
    repo: Repo, content_a: str, content_b: str, path: str, mode: str = "100644"
) -> str:
    """Generate git-style unified diff between two contents using git diff --no-index."""
    if content_a == content_b:
        return ""

    basename = os.path.basename(path)
    tmpdir_a = tmpdir_b = None
    try:
        tmpdir_a = tempfile.mkdtemp()
        tmpdir_b = tempfile.mkdtemp()
        file_a = os.path.join(tmpdir_a, basename)
        file_b = os.path.join(tmpdir_b, basename)

        with open(file_a, "w", encoding="utf-8") as f:
            f.write(content_a)
        with open(file_b, "w", encoding="utf-8") as f:
            f.write(content_b)

        # --no-index exits 1 when files differ, so suppress exceptions
        _, raw, _ = repo.git.execute(  # type: ignore[call-overload]
            ["git", "diff", "--no-index", "--", file_a, file_b],
            with_extended_output=True,
            with_exceptions=False,
        )

        if not raw:
            return ""

        # Replace temp paths with canonical a/path and b/path
        lines = raw.split("\n")
        result: list[str] = []
        for line in lines:
            if line.startswith("diff --git"):
                result.append(f"diff --git a/{path} b/{path}")
            elif line.startswith("index "):
                # Keep git's hash abbreviation, only fix the mode
                hashes = line.split(" ")[1]
                result.append(f"index {hashes} {mode}")
            elif line.startswith("--- "):
                result.append(f"--- a/{path}")
            elif line.startswith("+++ "):
                result.append(f"+++ b/{path}")
            else:
                result.append(line)

        return "\n".join(result)
    finally:
        for tmpdir in (tmpdir_a, tmpdir_b):
            if tmpdir is not None:
                try:
                    filepath = os.path.join(tmpdir, basename)
                    if os.path.exists(filepath):
                        os.unlink(filepath)
                    os.rmdir(tmpdir)
                except OSError:
                    pass


def _read_blob(blob: Any) -> str:
    """Read blob content as UTF-8 string."""
    return blob.data_stream.read().decode("utf-8", errors="replace") if blob else ""


def _process_diff_item(diff_item: Any, repo: Repo) -> tuple[str | None, bool]:
    """Process a diff item, returning (stripped_diff, is_unsupported)."""
    file_path = diff_item.b_path or diff_item.a_path
    language = _get_language(file_path) if file_path else None
    if not language:
        return None, True

    # Check for binary
    if any(
        b and b.mime_type and "text" not in b.mime_type
        for b in [diff_item.a_blob, diff_item.b_blob]
    ):
        return None, True

    try:
        content_a = _read_blob(diff_item.a_blob)
        content_b = _read_blob(diff_item.b_blob)
    except Exception:
        return None, True

    # Strip comments
    stripped_a = _strip_comments(content_a, language) if content_a else ""
    stripped_b = _strip_comments(content_b, language) if content_b else ""

    if stripped_a is None or stripped_b is None:
        return None, True

    # Get file mode from blob (default 100644)
    blob = diff_item.b_blob or diff_item.a_blob
    mode = f"{blob.mode:06o}" if blob and blob.mode else "100644"

    return _generate_diff(repo, stripped_a, stripped_b, file_path, mode), False


def _get_diff_no_comments(
    repo: Repo, commit_id: str, include_unsupported: bool = True
) -> str | None:
    """Generate diff with comments stripped.

    Args:
        repo: Git repository object
        commit_id: Commit SHA to process
        include_unsupported: If True, include original diff for unsupported files.
                            If False, skip unsupported files entirely.
    """
    try:
        commit = repo.commit(commit_id)
        if not commit.parents:
            return None

        diffs = commit.parents[0].diff(commit, create_patch=True)
        file_diffs: list[str] = []

        for diff_item in diffs:
            diff_str, unsupported = _process_diff_item(diff_item, repo)
            if unsupported:
                if include_unsupported and diff_item.diff:
                    # Construct full diff with header for unsupported files
                    path = diff_item.b_path or diff_item.a_path
                    blob_a = diff_item.a_blob.hexsha[:7] if diff_item.a_blob else "0000000"
                    blob_b = diff_item.b_blob.hexsha[:7] if diff_item.b_blob else "0000000"
                    blob = diff_item.b_blob or diff_item.a_blob
                    mode = f"{blob.mode:06o}" if blob and blob.mode else "100644"
                    header = (
                        f"diff --git a/{path} b/{path}\n"
                        f"index {blob_a}..{blob_b} {mode}\n"
                        f"--- a/{path}\n"
                        f"+++ b/{path}\n"
                    )
                    raw_diff = diff_item.diff
                    diff_text = (
                        raw_diff.decode("utf-8", errors="replace")
                        if isinstance(raw_diff, bytes)
                        else raw_diff
                    )
                    file_diffs.append(header + diff_text)
            elif diff_str:
                file_diffs.append(diff_str)

        return "\n".join(file_diffs) if file_diffs else ""
    except Exception as e:
        logger.debug("Failed to process commit %s: %s", commit_id, e)
        return None


def _process_batch(args: tuple[str, list[str], bool]) -> dict[str, str]:
    """Process a batch of commits."""
    repo_path, commit_ids, include_unsupported = args
    results: dict[str, str] = {}

    with Repo(repo_path) as repository:
        for commit_id in commit_ids:
            diff = _get_diff_no_comments(repository, commit_id, include_unsupported)
            if diff is not None:
                results[commit_id] = diff

    return results


def add_commit_diff_no_comment(
    entries: list[DatasetEntry], *, include_unsupported: bool = True
) -> list[DatasetEntry]:
    """Enrich entries with comment-stripped diffs using tree-sitter.

    Args:
        entries: List of dataset entries to process
        include_unsupported: If True (default), include original diff for unsupported files.
                            If False, skip unsupported files entirely.
    """
    logger.info("Add commit diff without comments [LOCAL]")
    logger.info("Max diff size: %d KB", MAX_DIFF_SIZE // 1024)

    # Filter entries needing processing
    needs_processing = [e for e in entries if e.commit_diff and e.commit_diff_no_comment is None]
    to_process = [
        e for e in needs_processing if e.commit_diff and len(e.commit_diff) <= MAX_DIFF_SIZE
    ]

    if skipped := len(needs_processing) - len(to_process):
        logger.info("Skipped %d entries exceeding size limit", skipped)

    if not to_process:
        logger.info("No entries to process")
        return entries

    # Group by project
    commits_by_url: dict[str, set[str]] = defaultdict(set)
    for e in to_process:
        commits_by_url[e.project_url].add(e.commit_id)

    # Clone repos
    logger.info("Cloning repositories for %d entries...", len(to_process))
    repos = clone_repositories(to_process)
    repo_paths = {url: fspath(r.working_dir) for url, r in repos.items() if r and r.working_dir}
    path_to_url = {v: k for k, v in repo_paths.items()}

    # Entry lookup
    entries_by_commit: dict[tuple[str, str], list[DatasetEntry]] = defaultdict(list)
    for e in to_process:
        entries_by_commit[(e.project_url, e.commit_id)].append(e)

    # Create batches
    batches: list[tuple[str, list[str], bool]] = []
    for url, commit_ids in commits_by_url.items():
        if url not in repo_paths:
            continue
        path = repo_paths[url]
        ids = list(commit_ids)
        for i in range(0, len(ids), BATCH_SIZE):
            batches.append((path, ids[i : i + BATCH_SIZE], include_unsupported))

    batches.sort(key=lambda b: len(b[1]), reverse=True)
    total = sum(len(b[1]) for b in batches)

    logger.info("Processing %d commits across %d repos", total, len(repo_paths))

    # Process
    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(_process_batch, b): b for b in batches}

        with tqdm(total=total, desc="Stripping comments", unit="commits") as pbar:
            for future in as_completed(futures):
                path, batch_ids, _ = futures[future]
                url = path_to_url[path]

                try:
                    for commit_id, diff in future.result().items():
                        for entry in entries_by_commit.get((url, commit_id), []):
                            entry.commit_diff_no_comment = diff
                except Exception as exc:
                    logger.error("Batch failed for %s: %s: %s", path, type(exc).__name__, exc)

                pbar.update(len(batch_ids))

    for repository in repos.values():
        with contextlib.suppress(BrokenPipeError, OSError):
            if repository:
                repository.close()

    logger.info("Done processing %d entries", len(to_process))
    return entries
