import logging
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from os import fspath
from typing import Any

from git import Repo
from tqdm.auto import tqdm

from config import MAX_DIFF_SIZE, MAX_WORKERS
from dataset_entry import DatasetEntry
from utils.git.repository import clone_repositories

logger = logging.getLogger(__name__)

BATCH_SIZE = 200


def _apply_commit_data(entry: DatasetEntry, data: dict[str, Any]) -> None:
    """Update entry fields from commit data."""
    if entry.commit_message is None:
        entry.commit_message = data["message"]
    if entry.commit_timestamp_utc is None:
        entry.commit_timestamp_utc = data["timestamp"]
    if entry.commit_diff is None:
        entry.commit_diff = data["diff"]
    if not entry.files_changed:
        entry.files_changed = data["files_changed"]


def _get_commit_info_gitpython(
    repo_path: str, commit_id: str, max_diff_size: int
) -> dict[str, Any] | None:
    """Get commit info using GitPython."""
    repo = None
    try:
        repo = Repo(repo_path)
        commit = repo.commit(commit_id)

        # Get diff
        if commit.parents:
            diff_text = repo.git.diff(commit.parents[0].hexsha, commit.hexsha)
        else:
            diff_text = repo.git.show(commit.hexsha, format="", p=True)

        # Check diff size limit
        diff_data: str | None = diff_text
        if len(diff_text) > max_diff_size:
            diff_data = None

        # Get files changed
        files_changed: set[str] = set()
        if commit.parents:
            for diff_item in commit.diff(commit.parents[0]):
                if diff_item.a_path:
                    files_changed.add(diff_item.a_path)
                if diff_item.b_path:
                    files_changed.add(diff_item.b_path)

        return {
            "message": commit.message,
            "timestamp": datetime.fromtimestamp(commit.committed_date, tz=UTC).isoformat(),
            "diff": diff_data,
            "files_changed": files_changed,
        }
    except Exception as e:
        logger.debug("Failed to get commit %s from %s: %s", commit_id, repo_path, e)
        return None
    finally:
        if repo is not None:
            repo.close()


def _process_commit_batch(args: tuple[str, list[str], int]) -> dict[str, dict[str, Any]]:
    """Process a batch of commits. Must be top-level for pickling."""
    repo_path, commit_ids, max_diff_size = args
    results = {}
    for commit_id in commit_ids:
        info = _get_commit_info_gitpython(repo_path, commit_id, max_diff_size)
        if info:
            results[commit_id] = info
    return results


def add_commit_information_local(entries: list[DatasetEntry]) -> list[DatasetEntry]:
    """
    Enriches DatasetEntry objects with commit information using GitPython + ProcessPoolExecutor
    and returns the enriched list of entries.
    """
    logger.info("Add commit information [LOCAL]")

    # 1. Filter entries that need processing
    entries_to_process = [
        entry
        for entry in entries
        if entry.commit_diff is None
        or entry.commit_message is None
        or entry.commit_timestamp_utc is None
        or not entry.files_changed
    ]
    if not entries_to_process:
        logger.info("All entries already have commit information.")
        return entries

    # 2. Group commit IDs by project_url
    commits_by_project_url = defaultdict(set)
    for entry in entries_to_process:
        commits_by_project_url[entry.project_url].add(entry.commit_id)

    # 3. Clone all required repositories
    logger.info("Cloning repositories for %d entries...", len(entries_to_process))
    repo_objects = clone_repositories(entries_to_process)

    repo_paths: dict[str, str] = {
        url: fspath(repo.working_dir)
        for url, repo in repo_objects.items()
        if repo and repo.working_dir
    }

    # Reverse mapping: repo_path -> project_url (for associating batch results)
    path_to_url: dict[str, str] = {path: url for url, path in repo_paths.items()}

    # Build lookup for fast entry access by (project_url, commit_id)
    # Multiple entries can share the same commit (e.g., from different source datasets)
    entries_by_commit: dict[tuple[str, str], list[DatasetEntry]] = defaultdict(list)
    for entry in entries_to_process:
        entries_by_commit[(entry.project_url, entry.commit_id)].append(entry)

    # Track pending commits per repo for early cleanup
    pending_commits_by_url: dict[str, int] = {
        url: len(commits) for url, commits in commits_by_project_url.items()
    }

    # 4. Calculate workers and batch size
    total_commits = sum(len(ids) for ids in commits_by_project_url.values())
    num_workers = MAX_WORKERS

    logger.info("Max diff size limit: %d KB", MAX_DIFF_SIZE // 1024)

    logger.info(
        "Processing %d commits across %d repos (workers=%d, batch_size=%d)",
        total_commits,
        len(repo_paths),
        num_workers,
        BATCH_SIZE,
    )

    # 5. Create batches
    batches: list[tuple[str, list[str], int]] = []
    for project_url, commit_ids_set in commits_by_project_url.items():
        if project_url not in repo_paths:
            continue

        repo_path = repo_paths[project_url]
        commit_ids = list(commit_ids_set)

        for i in range(0, len(commit_ids), BATCH_SIZE):
            batch_commit_ids = commit_ids[i : i + BATCH_SIZE]
            batches.append((repo_path, batch_commit_ids, MAX_DIFF_SIZE))

    # Sort largest batches first (LPT scheduling) for better load balancing
    batches.sort(key=lambda b: len(b[1]), reverse=True)

    # 6. Process with ProcessPoolExecutor - stream processing mode
    # Update entries immediately as results arrive, then discard results to free memory
    failed_batches = 0

    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        future_to_batch = {executor.submit(_process_commit_batch, batch): batch for batch in batches}

        with tqdm(
            total=total_commits,
            desc="Adding commit data (local)",
            dynamic_ncols=True,
            unit="commits",
        ) as pbar:
            for future in as_completed(future_to_batch):
                repo_path, batch_commit_ids, _ = future_to_batch[future]
                project_url = path_to_url[repo_path]

                try:
                    result_dict = future.result()

                    # Update entries immediately - no accumulation!
                    for commit_id, data in result_dict.items():
                        for entry in entries_by_commit.get((project_url, commit_id), []):
                            _apply_commit_data(entry, data)

                    # result_dict goes out of scope here - memory freed immediately

                except Exception:
                    logger.exception("Error processing batch for %s", repo_path)
                    failed_batches += 1

                # Decrement pending count and close repo when all its commits are done
                pending_commits_by_url[project_url] -= len(batch_commit_ids)
                if pending_commits_by_url[project_url] <= 0:
                    repo = repo_objects.get(project_url)
                    if repo is not None:
                        repo.close()
                        del repo_objects[project_url]

                pbar.update(len(batch_commit_ids))

    logger.info("Local enrichment complete for %d entries.", len(entries_to_process))
    if failed_batches:
        logger.warning("%d batches failed during processing", failed_batches)

    # Cleanup: Close any remaining Repo objects (shouldn't be any if all batches succeeded)
    if repo_objects:
        logger.debug("Closing %d remaining repo objects", len(repo_objects))
        for repo in repo_objects.values():
            if repo is not None:
                repo.close()
        repo_objects.clear()

    return entries
