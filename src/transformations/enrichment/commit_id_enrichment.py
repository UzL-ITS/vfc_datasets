import asyncio
import logging
from concurrent.futures import ProcessPoolExecutor, as_completed

from tqdm.asyncio import tqdm as async_tqdm
from tqdm.auto import tqdm

from config import MAX_WORKERS
from dataset_entry import DatasetEntry
from utils.git.github_client import AsyncGitHubClient
from utils.git.repository import clone_repository
from utils.git.url import GitURL

logger = logging.getLogger(__name__)


def _extend_commit_ids_one_repository(
    entries: list[DatasetEntry],
) -> list[DatasetEntry]:
    """Extend commit IDs for all entries from one repository."""
    if not entries:
        return entries

    project_url = entries[0].project_url
    logger.debug("Processing repository: %s with %d commits", project_url, len(entries))

    repo = clone_repository(project_url)
    if not repo:
        logger.error("Could not clone repository for project_url %s", project_url)
        return entries

    for entry in entries:
        if not entry.commit_id or len(entry.commit_id) >= 40:
            continue

        try:
            commit = repo.commit(entry.commit_id)
            if commit.hexsha != entry.commit_id:
                entry.commit_id = commit.hexsha
        except Exception as e:
            logger.debug(
                "Failed to extend commit ID %s for repository %s: %s",
                entry.commit_id,
                project_url,
                e,
            )

    return entries


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
    if not entry.commit_id or len(entry.commit_id) >= 40:
        return entry, entry.commit_id, False

    # Only works for GitHub repositories
    if not entry.project_url or "github.com" not in entry.project_url:
        return entry, entry.commit_id, False

    git_url = GitURL.parse(entry.project_url)
    if not git_url or git_url.host != "github.com":
        return entry, entry.commit_id, False

    owner, name = git_url.owner, git_url.repo
    if not owner or not name:
        return entry, entry.commit_id, False

    try:
        api_url = f"https://api.github.com/repos/{owner}/{name}/commits/{entry.commit_id}"
        result = await client.query_api(api_url)

        if result and "sha" in result:
            extended_id = result["sha"]
            was_updated = extended_id != entry.commit_id
            return entry, extended_id, was_updated

    except Exception as e:
        logger.debug("Async API extension failed for %s: %s", entry.commit_id, e)

    return entry, entry.commit_id, False


def extend_commit_ids_api(entries: list[DatasetEntry]) -> list[DatasetEntry]:
    """Extend commit IDs using the GitHub API (async) and return the (possibly) modified list of entries."""
    # Filter entries that need extension
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


def extend_commit_ids_local(entries: list[DatasetEntry]) -> list[DatasetEntry]:
    """Extend commit IDs in-place by cloning repositories locally and return the list of modified entries."""
    # Filter entries that need extension
    entries_to_process = [
        entry for entry in entries if entry.commit_id and len(entry.commit_id) < 40
    ]

    if not entries_to_process:
        logger.info("No commit IDs need extension")
        return entries

    logger.info("Extending %d commit IDs using local repositories", len(entries_to_process))

    # Group entries by project_url (repository)
    entries_by_project_url: dict[str, list[DatasetEntry]] = {}
    for entry in entries_to_process:
        project_url = entry.project_url
        if project_url not in entries_by_project_url:
            entries_by_project_url[project_url] = []
        entries_by_project_url[project_url].append(entry)

    logger.info(
        f"Processing {len(entries_to_process)} entries from "
        f"{len(entries_by_project_url)} repositories using {MAX_WORKERS} workers"
    )

    # Sort by number of entries per repository (descending)
    entries_by_project_url = dict(
        sorted(
            entries_by_project_url.items(),
            key=lambda item: len(item[1]),
            reverse=True,
        )
    )

    updated_count = 0
    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_url = {
            executor.submit(
                _extend_commit_ids_one_repository, entries_by_project_url[project_url]
            ): project_url
            for project_url in entries_by_project_url
        }

        with tqdm(
            total=len(entries_by_project_url),
            desc="Local extension",
            dynamic_ncols=True,
            unit="repos",
        ) as pbar:
            for future in as_completed(future_to_url):
                project_url = future_to_url[future]
                modified_entries = future.result()
                original_entries = entries_by_project_url[project_url]
                # Update original entries with data from child process
                for orig, mod in zip(original_entries, modified_entries, strict=True):
                    if orig.commit_id != mod.commit_id:
                        orig.commit_id = mod.commit_id
                        updated_count += 1

                pbar.update(1)
                pbar.set_postfix_str(f"Total updated: {updated_count}")

    logger.info("Local extension complete: %d updated", updated_count)
    return entries
