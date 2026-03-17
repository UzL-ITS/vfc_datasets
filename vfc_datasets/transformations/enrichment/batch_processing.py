import contextlib
import logging
from collections import defaultdict
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor, as_completed
from itertools import batched
from os import fspath
from typing import Any

from tqdm.auto import tqdm

from vfc_datasets.config import MAX_WORKERS
from vfc_datasets.dataset_entry import DatasetEntry
from vfc_datasets.utils.git.repository import clone_repositories

logger = logging.getLogger(__name__)

BATCH_SIZE = 200


def process_commits_in_batches(
    entries: list[DatasetEntry],
    *,
    filter_fn: Callable[[DatasetEntry], bool],
    batch_fn: Callable[[tuple[Any, ...]], dict[str, Any]],
    apply_fn: Callable[[DatasetEntry, Any], None],
    batch_extra_args: tuple[Any, ...] = (),
    desc: str = "Processing commits",
) -> list[DatasetEntry]:
    """Generic batch processor for commit-level operations over cloned repos.

    Args:
        entries: Full entry list.
        filter_fn: Predicate selecting entries to process.
        batch_fn: Top-level picklable function: (repo_path, commit_ids, *extra) -> {commit_id: data}.
        apply_fn: Applies one result to one entry: (entry, data) -> None.
        batch_extra_args: Extra args appended to each batch tuple.
        desc: tqdm description.
    """
    to_process = [e for e in entries if filter_fn(e)]
    if not to_process:
        return entries

    # Group commit IDs by project_url
    commits_by_url: dict[str, set[str]] = defaultdict(set)
    for e in to_process:
        commits_by_url[e.project_url].add(e.commit_id)

    # Clone
    repo_objects = clone_repositories(to_process)
    repo_paths = {
        url: fspath(r.working_dir) for url, r in repo_objects.items() if r and r.working_dir
    }
    path_to_url: dict[str, str] = {}
    for url, path in repo_paths.items():
        if path in path_to_url:
            logger.warning(
                "Duplicate repo path %s for URLs %s and %s", path, path_to_url[path], url
            )
        path_to_url[path] = url

    # Entry lookup
    entries_by_commit: dict[tuple[str, str], list[DatasetEntry]] = defaultdict(list)
    for e in to_process:
        entries_by_commit[(e.project_url, e.commit_id)].append(e)

    # Build batches
    batches = []
    for url, cids in commits_by_url.items():
        if url not in repo_paths:
            continue
        for batch in batched(cids, BATCH_SIZE):
            batches.append((repo_paths[url], list(batch), *batch_extra_args))
    batches.sort(key=lambda b: len(b[1]), reverse=True)

    total = sum(len(b[1]) for b in batches)
    logger.info("Processing %d commits across %d repos", total, len(repo_paths))

    # Track pending commits per URL for early repo cleanup
    pending_by_url: dict[str, int] = {url: len(cids) for url, cids in commits_by_url.items()}

    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(batch_fn, b): b for b in batches}
        with tqdm(total=total, desc=desc, unit="commits") as pbar:
            for future in as_completed(futures):
                batch = futures[future]
                url = path_to_url[batch[0]]
                try:
                    for commit_id, data in future.result().items():
                        for entry in entries_by_commit.get((url, commit_id), []):
                            apply_fn(entry, data)
                except Exception:
                    logger.exception("Batch failed for %s", batch[0])
                pbar.update(len(batch[1]))

                # Close repo early when all its commits are done
                pending_by_url[url] -= len(batch[1])
                if pending_by_url[url] <= 0:
                    repo = repo_objects.pop(url, None)
                    if repo:
                        with contextlib.suppress(BrokenPipeError, OSError):
                            repo.close()

    # Cleanup any remaining repos (e.g. if batches failed)
    for repo in repo_objects.values():
        with contextlib.suppress(BrokenPipeError, OSError):
            if repo:
                repo.close()

    return entries
