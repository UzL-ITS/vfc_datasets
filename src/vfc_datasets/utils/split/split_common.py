"""Shared utilities for dataset splitting strategies."""

import logging
from collections import defaultdict

from vfc_datasets.dataset_entry import DatasetEntry

from .repository_relationships import RepositoryRelationships

type Group = tuple[set[str], int]


def validate_split_ratios(train_ratio: float, val_ratio: float, test_ratio: float) -> None:
    """Validate that split ratios sum to 1.0."""
    if abs(train_ratio + val_ratio + test_ratio - 1.0) > 1e-6:
        raise ValueError("Ratios must sum to 1.0")


def split_by_ratio(
    items: list[DatasetEntry],
    train_ratio: float,
    val_ratio: float,
    test_ratio: float,
) -> tuple[list[DatasetEntry], list[DatasetEntry], list[DatasetEntry]]:
    """Split a list into three parts according to ratios."""
    total = len(items)
    train_end = int(total * train_ratio)
    val_end = train_end + int(total * val_ratio)

    train = items[:train_end]
    val = items[train_end:val_end]
    test = items[val_end:]

    return train, val, test


def group_related_repos(
    entries: list[DatasetEntry],
    relationships: RepositoryRelationships,
) -> list[Group]:
    """Group related repos together, standalone repos as single-item groups."""
    url_counts: dict[str, int] = defaultdict(int)
    for entry in entries:
        url_counts[entry.project_url] += 1

    all_urls = set(url_counts.keys())
    processed: set[str] = set()
    groups: list[Group] = []

    for rel_group in relationships.groups:
        urls = rel_group.project_urls & all_urls
        if urls:
            groups.append((urls, sum(url_counts[url] for url in urls)))
            processed.update(urls)

    for url in all_urls - processed:
        groups.append(({url}, url_counts[url]))

    return groups


def visualize_split(
    train_entries: list[DatasetEntry],
    test_entries: list[DatasetEntry],
    relationships: RepositoryRelationships,
    val_entries: list[DatasetEntry] | None = None,
) -> None:
    """Log a text visualization of a two-way or three-way split."""
    split_parts = [train_entries, test_entries]
    if val_entries is not None:
        split_parts.insert(1, val_entries)

    total = sum(len(part) for part in split_parts)
    if total == 0:
        logging.info("Empty split")
        return

    # Build lookup for canonical URLs
    canonical_urls: dict[str, str] = {}
    for rel_group in relationships.groups:
        if rel_group.canonical_url:
            for url in rel_group.project_urls:
                canonical_urls[url] = rel_group.canonical_url

    all_groups = [
        sorted(group_related_repos(part, relationships), key=lambda g: -g[1])
        for part in split_parts
    ]
    all_counts = [count for groups in all_groups for _, count in groups]
    max_count = max(all_counts, default=1)
    small_threshold = sorted(all_counts)[int(len(all_counts) * 0.75)] if all_counts else 0

    lines: list[str] = []

    def get_display_name(urls: set[str]) -> str:
        """Get display name, preferring canonical URL."""
        first_url = sorted(urls)[0]
        display_url = canonical_urls.get(first_url, first_url)
        parts = display_url.rstrip("/").split("/")
        return "/".join(parts[-2:]) if len(parts) >= 2 else parts[-1]

    def render(groups: list[Group], label: str, entries_in_split: list[DatasetEntry]) -> None:
        entry_count = len(entries_in_split)
        pct = entry_count / total * 100
        project_count = len(groups)
        repo_count = sum(len(urls) for urls, _ in groups)
        vfc_count = sum(1 for e in entries_in_split if e.is_vfc)
        vfc_ratio = (vfc_count / entry_count * 100) if entry_count > 0 else 0.0
        lines.append(
            f"{label} ({pct:.1f}%) - {entry_count:,} commits, {project_count:,} projects, "
            f"{repo_count:,} repos - VFC Ratio: {vfc_ratio:.1f}%"
        )
        lines.append("-" * 70)

        if not groups:
            lines.append("  (empty)")
            return

        large_groups = [(urls, count) for urls, count in groups if count >= small_threshold]
        small_groups = [(urls, count) for urls, count in groups if count < small_threshold]

        for urls, count in large_groups[:10]:
            name = get_display_name(urls)
            suffix = f" [{len(urls)} repos]" if len(urls) > 1 else ""
            bar = "#" * max(1, int(count / max_count * 30))
            lines.append(f"  {bar} {name}{suffix} ({count:,})")

        if len(large_groups) > 10:
            remaining_count = sum(count for _, count in large_groups[10:])
            lines.append(
                f"  ... +{len(large_groups) - 10} more large projects ({remaining_count:,} commits)"
            )
        if small_groups:
            small_count = sum(count for _, count in small_groups)
            lines.append(f"  ... {len(small_groups):,} small projects ({small_count:,} commits)")

    labels = ["Train", "Val", "Test"] if val_entries is not None else ["Train", "Test"]
    for i, (groups, label, entries) in enumerate(zip(all_groups, labels, split_parts, strict=True)):
        if i > 0:
            lines.append("")
        render(groups, label, entries)

    logging.info("Split visualization:\n%s", "\n".join(lines))
