"""Create train/test splits that respect repository relationships."""

from __future__ import annotations

import logging
import random
from collections import defaultdict

from dataset_entry import DatasetEntry
from utils.split.repository_relationships import RepositoryRelationships

Group = tuple[set[str], int]
HashableGroup = tuple[frozenset[str], int]


def _group_related_repos(
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


def _greedy_assign(groups: list[Group], target: float) -> set[str]:
    """Assign groups to train using greedy distance minimization."""
    train_urls: set[str] = set()
    current_count = 0
    for urls, count in groups:
        if abs(current_count + count - target) <= abs(current_count - target):
            train_urls.update(urls)
            current_count += count
    return train_urls


def _optimize_assignment(
    groups: list[Group],
    train_urls: set[str],
    target: float,
) -> set[str]:
    """Optimize assignment using single moves and swaps."""
    train_groups: set[HashableGroup] = set()
    test_groups: set[HashableGroup] = set()
    for urls, count in groups:
        hashable = (frozenset(urls), count)
        (train_groups if urls & train_urls else test_groups).add(hashable)

    train_total = sum(count for _, count in train_groups)
    best_deviation = abs(train_total - target)

    def sort_key(group: HashableGroup) -> tuple[int, str]:
        return (group[1], min(group[0]))

    # Phase 1: Single moves
    improved = True
    while improved:
        improved = False
        for group in sorted(train_groups, key=sort_key):
            new_deviation = abs(train_total - group[1] - target)
            if new_deviation < best_deviation:
                train_groups.remove(group)
                test_groups.add(group)
                train_total -= group[1]
                best_deviation = new_deviation
                improved = True
                break
        if not improved:
            for group in sorted(test_groups, key=sort_key):
                new_deviation = abs(train_total + group[1] - target)
                if new_deviation < best_deviation:
                    test_groups.remove(group)
                    train_groups.add(group)
                    train_total += group[1]
                    best_deviation = new_deviation
                    improved = True
                    break

    # Phase 2: Swaps
    improved = True
    while improved:
        improved = False
        for train_group in sorted(train_groups, key=sort_key):
            for test_group in sorted(test_groups, key=sort_key):
                new_total = train_total - train_group[1] + test_group[1]
                new_deviation = abs(new_total - target)
                if new_deviation < best_deviation:
                    train_groups.remove(train_group)
                    train_groups.add(test_group)
                    test_groups.remove(test_group)
                    test_groups.add(train_group)
                    train_total = new_total
                    best_deviation = new_deviation
                    improved = True
                    break
            if improved:
                break

    return {url for urls, _ in train_groups for url in urls}


def _visualize_split(
    train_entries: list[DatasetEntry],
    test_entries: list[DatasetEntry],
    relationships: RepositoryRelationships,
) -> None:
    """Log a text visualization of a split."""
    total = len(train_entries) + len(test_entries)
    if total == 0:
        logging.info("Empty split")
        return

    # Build lookup for canonical URLs
    canonical_urls: dict[str, str] = {}
    for rel_group in relationships.groups:
        if rel_group.canonical_url:
            for url in rel_group.project_urls:
                canonical_urls[url] = rel_group.canonical_url

    train_groups = sorted(_group_related_repos(train_entries, relationships), key=lambda g: -g[1])
    test_groups = sorted(_group_related_repos(test_entries, relationships), key=lambda g: -g[1])

    all_counts = [count for _, count in train_groups + test_groups]
    max_count = max(all_counts, default=1)
    small_threshold = sorted(all_counts)[int(len(all_counts) * 0.75)] if all_counts else 0

    lines: list[str] = []

    def get_display_name(urls: set[str]) -> str:
        """Get display name, preferring canonical URL."""
        first_url = sorted(urls)[0]
        display_url = canonical_urls.get(first_url, first_url)
        parts = display_url.rstrip("/").split("/")
        return "/".join(parts[-2:]) if len(parts) >= 2 else parts[-1]

    def render(groups: list[Group], label: str, entry_count: int) -> None:
        pct = entry_count / total * 100
        project_count = len(groups)
        repo_count = sum(len(urls) for urls, _ in groups)
        lines.append(f"{label} ({pct:.1f}%) - {entry_count:,} commits, {project_count:,} projects, {repo_count:,} repos")
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
            lines.append(f"  ... +{len(large_groups) - 10} more large projects ({remaining_count:,} commits)")
        if small_groups:
            small_count = sum(count for _, count in small_groups)
            lines.append(f"  ... {len(small_groups):,} small projects ({small_count:,} commits)")

    render(train_groups, "Train", len(train_entries))
    lines.append("")
    render(test_groups, "Test", len(test_entries))

    logging.info("Split visualization:\n%s", "\n".join(lines))


def train_test_split_stratified(
    entries: list[DatasetEntry],
    relationships: RepositoryRelationships,
    split_ratio: float = 0.8,
    seed: int | None = None,
    num_strata: int = 4,
) -> tuple[list[DatasetEntry], list[DatasetEntry]]:
    """Stratified shuffle by group size with subset-sum optimization."""
    if not entries:
        return [], []

    rng = random.Random(seed)
    groups = _group_related_repos(entries, relationships)
    total = sum(count for _, count in groups)
    target = total * split_ratio

    # Stratified shuffle: distribute by size, shuffle within strata, interleave
    sorted_groups = sorted(groups, key=lambda g: -g[1])
    strata: list[list[Group]] = [[] for _ in range(num_strata)]
    for i, group in enumerate(sorted_groups):
        strata[i % num_strata].append(group)
    for stratum in strata:
        rng.shuffle(stratum)

    max_stratum_len = max(len(stratum) for stratum in strata)
    ordered = [stratum[i] for i in range(max_stratum_len) for stratum in strata if i < len(stratum)]

    # Greedy assignment + optimization
    train_urls = _greedy_assign(ordered, target)
    train_urls = _optimize_assignment(groups, train_urls, target)

    # Verify no group is split between train/test
    for urls, _ in groups:
        in_train = urls & train_urls
        assert in_train == urls or not in_train, "Group split between train/test"

    train = [entry for entry in entries if entry.project_url in train_urls]
    test = [entry for entry in entries if entry.project_url not in train_urls]
    _visualize_split(train, test, relationships)
    return train, test
