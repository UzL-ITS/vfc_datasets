"""Enrich dataset entries with commit data from GitHub API."""

import asyncio
import logging
from typing import Any

from tqdm.asyncio import tqdm

from dataset_entry import DatasetEntry
from transformations.enrichment.commit_data_common import apply_commit_data, needs_enrichment
from utils.git.github_client import GITHUB_API_URL, AsyncGitHubClient
from utils.git.url import GitURL

logger = logging.getLogger(__name__)


async def _enrich_entry(entry: DatasetEntry, client: AsyncGitHubClient) -> bool:
    """Fetch commit info from GitHub API and populate entry in-place."""
    git_url = GitURL.parse(entry.project_url)
    if not git_url or git_url.host != "github.com":
        return False

    owner, repo = git_url.owner, git_url.repo
    if not owner or not repo:
        return False

    api_url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/commits/{entry.commit_id}"
    try:
        data = await client.query_api(api_url)
    except Exception as e:
        logger.warning("API error for %s/%s@%s: %s", owner, repo, entry.commit_id, e)
        return False

    if not data:
        return False

    _apply_api_response(entry, data)
    return True


def _apply_api_response(entry: DatasetEntry, data: dict[str, Any]) -> None:
    """Convert GitHub API response to common format and apply."""
    commit = data.get("commit", {})
    files = data.get("files", [])

    patches = [f["patch"] for f in files if f.get("patch")]

    apply_commit_data(
        entry,
        {
            "message": commit.get("message"),
            "timestamp": commit.get("author", {}).get("date"),
            "diff": "\n".join(patches) if patches else None,
            "files_changed": {f["filename"] for f in files if f.get("filename")},
        },
    )


async def _enrich_entries_async(entries: list[DatasetEntry]) -> tuple[int, int]:
    """Enrich entries via GitHub API. Returns (success_count, fail_count)."""
    success = 0

    async with AsyncGitHubClient() as client:
        tasks = [_enrich_entry(e, client) for e in entries]
        with tqdm(
            total=len(entries), desc="API enrichment", dynamic_ncols=True, unit="commits"
        ) as pbar:
            for task in asyncio.as_completed(tasks):
                if await task:
                    success += 1
                pbar.set_postfix_str(f"{client.get_rate_limit_status()} | OK: {success}")
                pbar.update(1)

    return success, len(entries) - success


def add_commit_information_api(entries: list[DatasetEntry]) -> list[DatasetEntry]:
    """Enrich entries with commit data from the GitHub API and return the modified list."""
    entries_to_process = [e for e in entries if needs_enrichment(e)]

    if not entries_to_process:
        logger.info("No entries need API enrichment")
        return entries

    logger.info("Enriching %d entries via GitHub API", len(entries_to_process))
    success, failed = asyncio.run(_enrich_entries_async(entries_to_process))
    logger.info("API enrichment complete: %d succeeded, %d failed", success, failed)
    return entries
