"""Group-stratified splitting strategy respecting repository relationships."""

import random

from dataset_entry import DatasetEntry
from utils.split.repository_relationships import RepositoryRelationships
from utils.split.split_common import (
    Group,
    group_related_repos,
    validate_split_ratios,
    visualize_split,
)

type HashableGroup = tuple[frozenset[str], int]


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


def _binary_split_group_stratified(
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
    groups = group_related_repos(entries, relationships)
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
        if in_train and in_train != urls:
            raise RuntimeError("Group split between train/test")

    first = [entry for entry in entries if entry.project_url in train_urls]
    second = [entry for entry in entries if entry.project_url not in train_urls]
    return first, second


def train_test_split_group_stratified(
    entries: list[DatasetEntry],
    relationships: RepositoryRelationships,
    split_ratio: float = 0.8,
    seed: int | None = None,
    num_strata: int = 4,
    visualize: bool = True,
) -> tuple[list[DatasetEntry], list[DatasetEntry]]:
    """Stratified shuffle by group size with subset-sum optimization."""
    train, test = _binary_split_group_stratified(
        entries, relationships, split_ratio, seed, num_strata
    )
    if visualize:
        visualize_split(train, test, relationships)
    return train, test


def train_val_test_split_group_stratified(
    entries: list[DatasetEntry],
    relationships: RepositoryRelationships,
    train_ratio: float = 0.6,
    val_ratio: float = 0.2,
    test_ratio: float = 0.2,
    seed: int | None = None,
    num_strata: int = 4,
    visualize: bool = True,
) -> tuple[list[DatasetEntry], list[DatasetEntry], list[DatasetEntry]]:
    """Hierarchical three-way split respecting repository groups."""
    if not entries:
        return [], [], []
    validate_split_ratios(train_ratio, val_ratio, test_ratio)

    rng = random.Random(seed)

    # First split: separate test set from train+val
    trainval_ratio = train_ratio + val_ratio
    if trainval_ratio <= 0:
        raise ValueError("train_ratio + val_ratio must be positive for three-way split")
    trainval, test = _binary_split_group_stratified(
        entries,
        relationships,
        split_ratio=trainval_ratio,
        seed=rng.randint(0, 2**31 - 1),
        num_strata=num_strata,
    )

    # Second split: separate train from val
    train_fraction = train_ratio / trainval_ratio
    train, val = _binary_split_group_stratified(
        trainval,
        relationships,
        split_ratio=train_fraction,
        seed=rng.randint(0, 2**31 - 1),
        num_strata=num_strata,
    )

    if visualize:
        visualize_split(train, test, relationships, val_entries=val)
    return train, val, test
