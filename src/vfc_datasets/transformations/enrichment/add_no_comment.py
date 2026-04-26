import logging
import os
import tempfile
from collections.abc import Iterable
from pathlib import PurePosixPath
from typing import Any

import tree_sitter
import tree_sitter_c
import tree_sitter_cpp
import tree_sitter_java
import tree_sitter_javascript
import tree_sitter_python
from git import Repo

from vfc_datasets.config import MAX_DIFF_SIZE
from vfc_datasets.dataset_entry import DatasetEntry
from vfc_datasets.utils.extensions import EXTENSION_TO_LANGUAGE

from .batch_processing import process_commits_in_batches

logger = logging.getLogger(__name__)

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
    return EXTENSION_TO_LANGUAGE.get(PurePosixPath(file_path).suffix.lower())


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
        stack = [tree.root_node]
        while stack:
            node = stack.pop()
            if node.type in comment_types:
                comment_ranges.append((node.start_byte, node.end_byte))
            stack.extend(node.children)

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

            if not before.strip() and not after.strip():
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

    with tempfile.TemporaryDirectory() as tmpdir_a, tempfile.TemporaryDirectory() as tmpdir_b:
        file_a = os.path.join(tmpdir_a, basename)
        file_b = os.path.join(tmpdir_b, basename)

        with open(file_a, "w", encoding="utf-8") as f:
            f.write(content_a)
        with open(file_b, "w", encoding="utf-8") as f:
            f.write(content_b)

        # --no-index exits 1 when files differ, so suppress exceptions
        _, raw, _ = repo.git.execute(  # pyright: ignore[reportCallIssue]
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
            hashes = line.split(" ")[1]
            result.append(f"index {hashes} {mode}")
        elif line.startswith("--- "):
            result.append(f"--- a/{path}")
        elif line.startswith("+++ "):
            result.append(f"+++ b/{path}")
        else:
            result.append(line)

    return "\n".join(result)


def _read_blob(blob: Any) -> str:
    """Read blob content as UTF-8 string."""
    return blob.data_stream.read().decode("utf-8", errors="replace") if blob else ""


def _build_original_diff(diff_item: Any) -> str | None:
    """Build a full diff from a diff_item's raw diff, with a proper header."""
    if not diff_item.diff:
        return None
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
        raw_diff.decode("utf-8", errors="replace") if isinstance(raw_diff, bytes) else raw_diff
    )
    return header + diff_text


def _process_diff_item(diff_item: Any, repo: Repo, include_unsupported: bool) -> str | None:
    """Process a single diff item, stripping comments where possible.

    For unsupported languages/binary files, returns the original diff
    (if include_unsupported is True) or None.
    """
    file_path = diff_item.b_path or diff_item.a_path
    fallback = _build_original_diff(diff_item) if include_unsupported else None

    language = _get_language(file_path) if file_path else None
    if not language:
        return fallback

    if any(
        b and b.mime_type and "text" not in b.mime_type
        for b in [diff_item.a_blob, diff_item.b_blob]
    ):
        return fallback

    try:
        content_a = _read_blob(diff_item.a_blob)
        content_b = _read_blob(diff_item.b_blob)
    except Exception:
        return fallback

    stripped_a = _strip_comments(content_a, language) if content_a else ""
    stripped_b = _strip_comments(content_b, language) if content_b else ""

    if stripped_a is None or stripped_b is None:
        return fallback

    # Get file mode from blob (default 100644)
    blob = diff_item.b_blob or diff_item.a_blob
    mode = f"{blob.mode:06o}" if blob and blob.mode else "100644"

    return _generate_diff(repo, stripped_a, stripped_b, file_path, mode)


def _get_diff_no_comments(
    repo: Repo, commit_id: str, max_diff_size: int, include_unsupported: bool = True
) -> str | None:
    """Generate diff with comments stripped.

    Args:
        repo: Git repository object
        commit_id: Commit SHA to process
        max_diff_size: Maximum diff size (heuristic)
        include_unsupported: If True, include original diff for unsupported files.
                            If False, skip unsupported files entirely.
    """
    try:
        commit = repo.commit(commit_id)
        if not commit.parents:
            return None

        # Note: Using line count as a safe fast-path heuristic for max_diff_size (chars).
        if commit.stats.total["lines"] > max_diff_size:
            return None

        diffs = commit.parents[0].diff(commit, create_patch=True)
        file_diffs: list[str] = []

        for diff_item in diffs:
            diff_str = _process_diff_item(diff_item, repo, include_unsupported)
            if diff_str:
                file_diffs.append(diff_str)

        return "\n".join(file_diffs) if file_diffs else ""
    except Exception as e:
        logger.debug("Failed to process commit %s: %s", commit_id, e)
        return None


def _process_batch(args: tuple[str, list[str], int, bool]) -> dict[str, str]:
    """Process a batch of commits."""
    repo_path, commit_ids, max_diff_size, include_unsupported = args
    results: dict[str, str] = {}

    try:
        with Repo(repo_path) as repository:
            for commit_id in commit_ids:
                diff = _get_diff_no_comments(
                    repository, commit_id, max_diff_size, include_unsupported
                )
                if diff is not None:
                    results[commit_id] = diff
    except Exception:
        logger.exception("Batch error for %s", repo_path)

    return results


def _apply_diff(entry: DatasetEntry, diff: str) -> None:
    entry.commit_diff = diff


def strip_diff_comments(
    entries: Iterable[DatasetEntry], *, include_unsupported: bool = True
) -> list[DatasetEntry]:
    """Strip comments from commit diffs in-place using tree-sitter.

    Args:
        entries: Dataset entries to process
        include_unsupported: If True (default), include original diff for unsupported files.
                            If False, skip unsupported files entirely.
    """
    logger.info("Strip comments from commit diffs [LOCAL]")
    logger.info("Max diff size: %dK chars", MAX_DIFF_SIZE // 1000)

    entries = list(entries)
    needs_processing = [e for e in entries if e.commit_diff]
    skipped = sum(
        1
        for e in needs_processing
        if e.commit_diff is not None and len(e.commit_diff) > MAX_DIFF_SIZE
    )
    if skipped:
        logger.info("Skipped %d entries exceeding size limit", skipped)

    return process_commits_in_batches(
        entries,
        filter_fn=lambda e: (
            e.commit_diff is not None
            and len(e.commit_diff) > 0
            and len(e.commit_diff) <= MAX_DIFF_SIZE
        ),
        batch_fn=_process_batch,
        apply_fn=_apply_diff,
        batch_extra_args=(MAX_DIFF_SIZE, include_unsupported),
        desc="Stripping comments",
    )
