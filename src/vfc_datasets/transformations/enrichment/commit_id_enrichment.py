import asyncio
import logging
from collections import defaultdict
from collections.abc import Iterable
from concurrent.futures import ProcessPoolExecutor, as_completed

from git import Repo
from tqdm.asyncio import tqdm as async_tqdm
from tqdm.auto import tqdm

from vfc_datasets.config import MAX_WORKERS, MP_CONTEXT
from vfc_datasets.dataset_entry import DatasetEntry
from vfc_datasets.utils.git.github_client import AsyncGitHubClient
from vfc_datasets.utils.git.repository import clone_repository
from vfc_datasets.utils.git.url import GitURL

logger = logging.getLogger(__name__)


def _resolve_commit_ids(args: tuple[str, list[str]]) -> dict[str, str]:
    """Resolve short commit IDs to full SHAs. Returns {short_id: full_sha} for successful lookups."""
    project_url, commit_ids = args
    logger.debug("Processing repository: %s with %d commits", project_url, len(commit_ids))

    path = clone_repository(project_url)
    if not path:
        logger.error("Could not clone repository for project_url %s", project_url)
        return {}

    resolved: dict[str, str] = {}
    with Repo(path) as repo:
        for commit_id in commit_ids:
            try:
                full_sha = repo.commit(commit_id).hexsha
                if full_sha != commit_id:
                    resolved[commit_id] = full_sha
            except Exception as e:
                logger.debug(
                    "Failed to extend commit ID %s for repository %s: %s",
                    commit_id,
                    project_url,
                    e,
                )

    return resolved


async def _extend_commit_ids_api_async(
    entries: list[DatasetEntry],
) -> tuple[int, list[DatasetEntry]]:
    """Async API processing for commit ID extension."""
    updated_count = 0
    api_failed_entries: list[DatasetEntry] = []

    async with AsyncGitHubClient() as client:

        async def _safe_extend(
            entry: DatasetEntry,
        ) -> tuple[DatasetEntry, str | None, bool, Exception | None]:
            """Wrapper that catches exceptions and always returns the entry."""
            try:
                _, extended_id, was_updated = await _extend_commit_id_api_async(entry, client)
                return entry, extended_id, was_updated, None
            except Exception as e:
                return entry, None, False, e

        # Create tasks for all entries
        tasks = [_safe_extend(entry) for entry in entries]

        # Create progress bar
        pbar = async_tqdm(
            total=len(tasks), desc="API extension", dynamic_ncols=True, unit="commits"
        )

        # Process tasks - entry is always available now, even on exception
        for task in asyncio.as_completed(tasks):
            entry, extended_id, was_updated, error = await task

            if error is not None:
                logger.warning("Failed to process entry %s: %s", entry.commit_id, error)
                api_failed_entries.append(entry)
            elif was_updated and extended_id is not None:
                entry.commit_id = extended_id
                updated_count += 1
            else:
                # API failed or not applicable
                api_failed_entries.append(entry)

            pbar.set_postfix_str(f"{client.get_rate_limit_status()} | Updated: {updated_count}")
            pbar.update(1)

        pbar.close()

    return updated_count, api_failed_entries


async def _extend_commit_id_api_async(
    entry: DatasetEntry, client: AsyncGitHubClient
) -> tuple[DatasetEntry, str, bool]:
    """Extend a short commit ID to full 40-character SHA using GitHub API."""
    git_url = GitURL.parse(entry.project_url)
    api_url = git_url.to_github_api_url(f"/commits/{entry.commit_id}") if git_url else None
    if not api_url:
        return entry, entry.commit_id, False

    try:
        result = await client.query_api(api_url)

        if result and "sha" in result:
            extended_id = result["sha"]
            was_updated = extended_id != entry.commit_id
            return entry, extended_id, was_updated

    except Exception as e:
        logger.debug("Async API extension failed for %s: %s", entry.commit_id, e)

    return entry, entry.commit_id, False


def extend_commit_ids_api(entries: Iterable[DatasetEntry]) -> list[DatasetEntry]:
    """Extend commit IDs using the GitHub API (async) and return the (possibly) modified list of entries."""
    entries = list(entries)
    entries_to_process = [
        entry for entry in entries if entry.commit_id and len(entry.commit_id) < 40
    ]

    if not entries_to_process:
        logger.info("No commit IDs need extension")
        return entries

    logger.info("Extending %d commit IDs using API", len(entries_to_process))

    updated_count, api_failed_entries = asyncio.run(
        _extend_commit_ids_api_async(entries_to_process)
    )

    logger.info(
        "API extension complete: %d updated, %d failed",
        updated_count,
        len(api_failed_entries),
    )
    return entries


def extend_commit_ids_local(entries: Iterable[DatasetEntry]) -> list[DatasetEntry]:
    """Extend commit IDs in-place by cloning repositories locally and return the list of modified entries."""
    entries = list(entries)
    entries_to_process = [
        entry for entry in entries if entry.commit_id and len(entry.commit_id) < 40
    ]

    if not entries_to_process:
        logger.info("No commit IDs need extension")
        return entries

    # Group entries by project_url
    entries_by_url: defaultdict[str, list[DatasetEntry]] = defaultdict(list)
    for entry in entries_to_process:
        entries_by_url[entry.project_url].append(entry)

    logger.info(
        "Extending %d commit IDs from %d repositories using %d workers",
        len(entries_to_process),
        len(entries_by_url),
        MAX_WORKERS,
    )

    # Build tasks: send only (project_url, commit_ids) — no full entries
    tasks = [
        (url, list({e.commit_id for e in url_entries}))
        for url, url_entries in entries_by_url.items()
    ]
    tasks.sort(key=lambda t: len(t[1]), reverse=True)

    updated_count = 0
    with ProcessPoolExecutor(max_workers=MAX_WORKERS, mp_context=MP_CONTEXT) as executor:
        future_to_url = {executor.submit(_resolve_commit_ids, task): task[0] for task in tasks}

        with tqdm(
            total=len(tasks),
            desc="Local extension",
            dynamic_ncols=True,
            unit="repos",
        ) as pbar:
            for future in as_completed(future_to_url):
                url = future_to_url[future]
                resolved = future.result()

                for entry in entries_by_url[url]:
                    if full_sha := resolved.get(entry.commit_id):
                        entry.commit_id = full_sha
                        updated_count += 1

                pbar.update(1)
                pbar.set_postfix_str(f"Total updated: {updated_count}")

    logger.info("Local extension complete: %d updated", updated_count)
    return entries
