import logging
from collections import defaultdict

from vfc_datasets.dataset_entry import DatasetEntry

from .duplicates import merge_entry_group

logger = logging.getLogger(__name__)


def collapse_to_commit_level(
    entries: list[DatasetEntry],
    *,
    include_benign_only: bool = True,
) -> list[DatasetEntry]:
    """Collapse function-level entries to commit-level by aggregating per-function rows.

    If any function in a commit is vulnerable, the commit is marked vulnerable.
    """
    if include_benign_only:
        logger.warning(
            "Keeping benign-only commits. Some function-level datasets might miss vulnerable "
            "functions. This could lead to mislabeling VFCs as non-VFC."
        )

    if not entries:
        return []

    groups: dict[tuple[str, str], list[DatasetEntry]] = defaultdict(list)
    for entry in entries:
        groups[(entry.project_url, entry.commit_id)].append(entry)

    result = []
    dropped = 0
    for group_entries in groups.values():
        is_vfc = any(e.is_vfc for e in group_entries)
        if not is_vfc and not include_benign_only:
            dropped += 1
            continue
        merged = merge_entry_group(group_entries)
        merged.is_vfc = is_vfc
        merged.function_name = None
        result.append(merged)

    if dropped:
        logger.info("Dropped %d benign-only commits during collapse.", dropped)

    return result
