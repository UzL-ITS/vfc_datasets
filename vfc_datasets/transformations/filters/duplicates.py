import copy
import hashlib
import logging
from collections import Counter, defaultdict
from collections.abc import Callable

from tqdm.auto import tqdm

from vfc_datasets.dataset_entry import DatasetEntry
from vfc_datasets.utils.split.repository_relationships import (
    RepositoryGroup,
    RepositoryRelationships,
    discover_repository_relationships,
)

logger = logging.getLogger(__name__)


def merge_entry_group(entries: list[DatasetEntry]) -> DatasetEntry:
    """Merge a group of entries with the same key into a new entry."""
    base = copy.copy(entries[0])
    base.cwe_ids = set(base.cwe_ids)
    base.cve_ids = set(base.cve_ids)
    base.src_datasets = set(base.src_datasets)
    base.files_changed = set(base.files_changed)
    if base.owasp_categories is not None:
        base.owasp_categories = set(base.owasp_categories)

    for other in entries[1:]:
        base.cwe_ids |= other.cwe_ids
        base.cve_ids |= other.cve_ids
        base.src_datasets |= other.src_datasets
        base.files_changed |= other.files_changed

        if base.owasp_categories is None:
            if other.owasp_categories is not None:
                base.owasp_categories = set(other.owasp_categories)
        elif other.owasp_categories:
            base.owasp_categories |= other.owasp_categories

        if base.commit_timestamp_utc is None:
            base.commit_timestamp_utc = other.commit_timestamp_utc
        if base.commit_message is None:
            base.commit_message = other.commit_message
        if base.commit_diff is None:
            base.commit_diff = other.commit_diff
        if base.ghsa_id is None:
            base.ghsa_id = other.ghsa_id

    return base


def _merge_duplicates(
    entries: list[DatasetEntry],
    key_func: Callable[[DatasetEntry], tuple],
    level_name: str,
) -> list[DatasetEntry]:
    logger.info("Merging duplicates at %s level.", level_name)

    entry_groups_by_key = defaultdict(list)
    for entry in entries:
        entry_groups_by_key[key_func(entry)].append(entry)

    result_entries: list[DatasetEntry] = []
    stats: Counter[str] = Counter()

    for key, group_entries in tqdm(entry_groups_by_key.items(), desc="Merging duplicates"):
        if len(group_entries) == 1:
            stats["unique"] += 1
            result_entries.append(group_entries[0])
        else:
            vfc_values = {entry.is_vfc for entry in group_entries}
            if len(vfc_values) > 1:
                logger.warning(
                    "Excluding entries due to VFC conflict for %s/%s. Datasets involved: %s",
                    key[0],
                    key[1],
                    [entry.src_datasets for entry in group_entries],
                )
                stats["conflict"] += len(group_entries)
                continue

            result_entries.append(merge_entry_group(group_entries))
            stats["merged"] += 1

    logger.info("\tUnique entries: %d", stats["unique"])
    logger.info("\tMerged entries: %d", stats["merged"])
    logger.info("\tEntries excluded due to VFC conflicts: %d", stats["conflict"])
    logger.info("Result: %d unique entries.", len(result_entries))

    return result_entries


def deduplicate_function_level(entries: list[DatasetEntry]) -> list[DatasetEntry]:
    """Deduplicate by (project_url, commit_id, function_name)."""
    return _merge_duplicates(
        entries,
        key_func=lambda entry: (entry.project_url, entry.commit_id, entry.function_name),
        level_name="function",
    )


def deduplicate_within_repository(entries: list[DatasetEntry]) -> list[DatasetEntry]:
    """Deduplicate by (project_url, commit_id). Clears function_name."""
    result = _merge_duplicates(
        entries,
        key_func=lambda entry: (entry.project_url, entry.commit_id),
        level_name="commit",
    )
    for entry in result:
        entry.function_name = None
    return result


def filter_by_has_unique_diff(entries: list[DatasetEntry]) -> list[DatasetEntry]:
    """Remove entries with duplicate (diff, files_changed) pairs. Entries without diff are kept."""
    seen_by_hash: dict[tuple[str, tuple[str, ...] | None], DatasetEntry] = {}
    # Entries without diffs are kept separately - we can't determine if they're duplicates
    entries_without_diff: list[DatasetEntry] = []
    duplicates_removed = 0

    sorted_entries = sorted(entries, key=lambda entry: (entry.project_url, entry.commit_id))

    for entry in tqdm(sorted_entries, desc="Filtering duplicate diffs"):
        if entry.commit_diff is None:
            # Keep entries without diffs - we can't check for duplicates without diff content
            entries_without_diff.append(entry)
            continue

        files_changed = entry.files_changed
        # Convert directly to sorted tuple for deterministic representation
        sorted_files = tuple(sorted(files_changed)) if files_changed else None

        # Hash the diff instead of using it directly as key
        # Use surrogatepass to handle diffs with invalid UTF-8 sequences (e.g., binary files)
        diff_hash = hashlib.sha256(
            entry.commit_diff.encode("utf-8", errors="surrogatepass")
        ).hexdigest()
        key = (diff_hash, sorted_files)

        # Keep only the first occurrence of each unique combination
        if key not in seen_by_hash:
            seen_by_hash[key] = entry
        else:
            duplicates_removed += 1
            original = seen_by_hash[key]
            logger.debug(
                "Duplicate diff: %s/commit/%s duplicates %s/commit/%s",
                entry.project_url,
                entry.commit_id,
                original.project_url,
                original.commit_id,
            )

    result = list(seen_by_hash.values()) + entries_without_diff
    logger.info(
        "Duplicate diff filter: %d unique diffs, %d duplicates removed, %d entries without diff (kept)",
        len(seen_by_hash),
        duplicates_removed,
        len(entries_without_diff),
    )
    return result


def deduplicate_across_related_repositories(
    entries: list[DatasetEntry],
    relationships: RepositoryRelationships | None = None,
) -> list[DatasetEntry]:
    """Remove duplicate commits across related repositories.

    When the same commit exists in multiple related repos (forks/mirrors),
    keep only one entry, preferring the canonical URL.

    If relationships is None, discovers them automatically.
    """
    if relationships is None:
        relationships = discover_repository_relationships(entries)

    commit_to_entries: dict[str, list[DatasetEntry]] = defaultdict(list)
    for entry in entries:
        commit_to_entries[entry.commit_id].append(entry)

    result: list[DatasetEntry] = []
    duplicates_removed = 0

    for commit_entries in commit_to_entries.values():
        if len(commit_entries) == 1:
            result.append(commit_entries[0])
            continue

        # Group by relationship group
        entries_by_group_id: dict[int, tuple[RepositoryGroup, list[DatasetEntry]]] = {}
        standalone: list[DatasetEntry] = []

        for entry in commit_entries:
            group = relationships.get_group(entry.project_url)
            if group:
                if group.group_id not in entries_by_group_id:
                    entries_by_group_id[group.group_id] = (group, [])
                entries_by_group_id[group.group_id][1].append(entry)
            else:
                standalone.append(entry)

        # Merge metadata from all entries, keep canonical URL
        for group, group_entries in entries_by_group_id.values():
            if len(group_entries) == 1:
                result.append(group_entries[0])
                continue
            merged = merge_entry_group(group_entries)
            merged.project_url = group.canonical_url or group_entries[0].project_url
            result.append(merged)
            duplicates_removed += len(group_entries) - 1

        result.extend(standalone)

    logger.info(
        "Relationship dedup: %d duplicates removed, %d entries remaining",
        duplicates_removed,
        len(result),
    )
    return result
