import logging
from collections.abc import Iterable
from datetime import UTC, datetime

from git import Repo

from vfc_datasets.config import MAX_DIFF_SIZE
from vfc_datasets.dataset_entry import DatasetEntry
from vfc_datasets.utils.git.commit import get_commit_diff

from .batch_processing import process_commits_in_batches
from .commit_data_common import (
    CommitData,
    apply_commit_data,
    needs_enrichment,
)

logger = logging.getLogger(__name__)


def _get_commit_info(repo: Repo, commit_id: str, max_diff_size: int) -> CommitData | None:
    """Get commit info from an open Repo object."""
    try:
        commit = repo.commit(commit_id)

        diff_data: str | None = None
        # Line count is a fast-path heuristic for max_diff_size (chars): skip
        # rendering the diff if it clearly exceeds the limit.
        if commit.stats.total["lines"] <= max_diff_size:
            diff_text = get_commit_diff(repo, commit_id)
            if len(diff_text) <= max_diff_size:
                diff_data = diff_text

        return CommitData(
            message=str(commit.message),
            timestamp=datetime.fromtimestamp(commit.committed_date, tz=UTC).isoformat(),
            diff=diff_data,
            files_changed={str(f) for f in commit.stats.files},
        )
    except Exception as e:
        logger.debug("Failed to get commit %s: %s", commit_id, e)
        return None


def _process_commit_batch(args: tuple[str, list[str], int]) -> dict[str, CommitData]:
    """Process a batch of commits. Must be top-level for pickling."""
    repo_path, commit_ids, max_diff_size = args
    results = {}
    with Repo(repo_path) as repo:
        for commit_id in commit_ids:
            info = _get_commit_info(repo, commit_id, max_diff_size)
            if info:
                results[commit_id] = info
    return results


def add_commit_information_local(entries: Iterable[DatasetEntry]) -> list[DatasetEntry]:
    """Enrich DatasetEntry objects with commit information from local git repos."""
    logger.info("Add commit information [LOCAL]")
    logger.info("Max diff size limit: %dK chars", MAX_DIFF_SIZE // 1000)

    return process_commits_in_batches(
        list(entries),
        filter_fn=needs_enrichment,
        batch_fn=_process_commit_batch,
        apply_fn=apply_commit_data,
        batch_extra_args=(MAX_DIFF_SIZE,),
        desc="Adding commit data (local)",
    )
