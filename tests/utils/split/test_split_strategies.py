"""Tests for train/test split functions."""

from datetime import UTC, datetime, timedelta

import pytest

from dataset_entry import DatasetEntry
from utils.split.repository_relationships import RepositoryRelationships
from utils.split.split_group_stratified import (
    _greedy_assign,
    _optimize_assignment,
    train_test_split_group_stratified,
    train_val_test_split_group_stratified,
)
from utils.split.split_random import train_val_test_split_random
from utils.split.split_temporal import train_val_test_split_temporal


def _make_entries(project_url: str, count: int) -> list[DatasetEntry]:
    return [
        DatasetEntry(
            project_url=project_url,
            commit_id=f"abc{i:04x}",
            src_datasets={"test"},
        )
        for i in range(count)
    ]


def _make_groups(sizes: list[int]) -> list[tuple[set[str], int]]:
    return [({f"https://github.com/test/repo{i}"}, size) for i, size in enumerate(sizes)]


def _count_train(groups, train_urls):
    """Count entries in train based on URLs."""
    return sum(count for urls, count in groups if urls & train_urls)


# --- _greedy_assign tests ---

def test_greedy_simple_split():
    groups = _make_groups([100, 100, 100, 100, 100])
    target = 500 * 0.8  # 400
    train_urls = _greedy_assign(groups, target)
    assert _count_train(groups, train_urls) == 400


def test_greedy_finds_exact_target():
    groups = _make_groups([500, 300, 200])
    target = 1000 * 0.8  # 800
    train_urls = _greedy_assign(groups, target)
    assert _count_train(groups, train_urls) == 800


def test_greedy_minimizes_deviation():
    groups = _make_groups([600, 350, 50])
    target = 1000 * 0.8  # 800
    train_urls = _greedy_assign(groups, target)
    # Target 800: 950 (deviation 150) closer than 600 (deviation 200)
    assert _count_train(groups, train_urls) == 950


def test_greedy_ratio_zero():
    groups = _make_groups([100, 100, 100])
    train_urls = _greedy_assign(groups, 0.0)
    assert _count_train(groups, train_urls) == 0


def test_greedy_ratio_one():
    groups = _make_groups([100, 100, 100])
    train_urls = _greedy_assign(groups, 300.0)
    assert _count_train(groups, train_urls) == 300


# --- _optimize_assignment tests ---

def test_optimize_finds_exact_target():
    groups = _make_groups([500, 300, 200])
    target = 1000 * 0.8
    train_urls = _greedy_assign(groups, target)
    train_urls = _optimize_assignment(groups, train_urls, target)
    assert _count_train(groups, train_urls) == 800


def test_optimize_improves_on_greedy():
    groups = _make_groups([600, 350, 150, 50])
    target = 1150 * 0.8  # 920
    train_urls = _greedy_assign(groups, target)
    train_urls = _optimize_assignment(groups, train_urls, target)
    # Greedy gives 950 (600+350), which has deviation 30 from 920
    # 600+350=950 is optimal (no better combination exists)
    assert _count_train(groups, train_urls) == 950


def test_optimize_empty():
    train_urls = _greedy_assign([], 0.0)
    train_urls = _optimize_assignment([], train_urls, 0.0)
    assert train_urls == set()


# --- train_test_split_stratified tests ---

def test_split_stratified_empty():
    train, test = train_test_split_group_stratified([], RepositoryRelationships())
    assert train == []
    assert test == []


def test_split_stratified_single_group():
    entries = _make_entries("https://github.com/test/only", 100)
    train, test = train_test_split_group_stratified(entries, RepositoryRelationships(), split_ratio=0.8)
    assert len(train) == 100
    assert len(test) == 0


def test_split_stratified_preserves_total():
    entries = (
        _make_entries("https://github.com/test/a", 600)
        + _make_entries("https://github.com/test/b", 300)
        + _make_entries("https://github.com/test/c", 100)
    )
    train, test = train_test_split_group_stratified(entries, RepositoryRelationships())
    assert len(train) + len(test) == 1000


def test_split_stratified_deterministic_with_seed():
    entries = (
        _make_entries("https://github.com/test/a", 50)
        + _make_entries("https://github.com/test/b", 50)
    )
    rel = RepositoryRelationships()
    train1, _ = train_test_split_group_stratified(entries, rel, seed=42)
    train2, _ = train_test_split_group_stratified(entries, rel, seed=42)
    assert len(train1) == len(train2)


# --- train_val_test_split_group_stratified tests ---

def test_three_way_split_empty():
    train, val, test = train_val_test_split_group_stratified([], RepositoryRelationships())
    assert train == []
    assert val == []
    assert test == []


def test_three_way_split_preserves_total():
    entries = (
        _make_entries("https://github.com/test/a", 600)
        + _make_entries("https://github.com/test/b", 300)
        + _make_entries("https://github.com/test/c", 100)
    )
    train, val, test = train_val_test_split_group_stratified(entries, RepositoryRelationships())
    assert len(train) + len(val) + len(test) == 1000


def test_three_way_split_respects_ratios():
    entries = (
        _make_entries("https://github.com/test/a", 200)
        + _make_entries("https://github.com/test/b", 200)
        + _make_entries("https://github.com/test/c", 200)
        + _make_entries("https://github.com/test/d", 200)
        + _make_entries("https://github.com/test/e", 200)
    )
    train, val, test = train_val_test_split_group_stratified(
        entries,
        RepositoryRelationships(),
        train_ratio=0.7,
        val_ratio=0.15,
        test_ratio=0.15,
    )
    total = len(entries)
    # With 5 equal groups, can achieve close to target ratios
    assert 0.6 <= len(train) / total <= 0.8
    assert 0.1 <= len(val) / total <= 0.3
    assert 0.1 <= len(test) / total <= 0.3


def test_three_way_split_deterministic_with_seed():
    entries = (
        _make_entries("https://github.com/test/a", 100)
        + _make_entries("https://github.com/test/b", 100)
        + _make_entries("https://github.com/test/c", 100)
    )
    rel = RepositoryRelationships()
    train1, val1, test1 = train_val_test_split_group_stratified(entries, rel, seed=42)
    train2, val2, test2 = train_val_test_split_group_stratified(entries, rel, seed=42)
    assert len(train1) == len(train2)
    assert len(val1) == len(val2)
    assert len(test1) == len(test2)


def test_three_way_split_no_group_leakage():
    """Verify related repos stay in same split."""
    from utils.split.repository_relationships import RepositoryGroup
    # Create entries from 3 repos, where repo2 and repo3 are related
    entries = (
        _make_entries("https://github.com/test/repo1", 100)
        + _make_entries("https://github.com/test/repo2", 100)
        + _make_entries("https://github.com/test/repo3", 100)
    )
    # Link repo2 and repo3
    group = RepositoryGroup(
        group_id=0,
        project_urls={"https://github.com/test/repo2", "https://github.com/test/repo3"},
        detection_methods={"test"},
    )
    rel = RepositoryRelationships(
        groups=[group],
        url_to_group_id={
            "https://github.com/test/repo2": 0,
            "https://github.com/test/repo3": 0,
        },
        _id_to_group={0: group},
    )

    train, val, test = train_val_test_split_group_stratified(entries, rel, seed=42)

    # Extract URLs from each split
    train_urls = {e.project_url for e in train}
    val_urls = {e.project_url for e in val}
    test_urls = {e.project_url for e in test}

    # repo2 and repo3 should be in the same split
    repo2_url = "https://github.com/test/repo2"
    repo3_url = "https://github.com/test/repo3"

    in_train = repo2_url in train_urls and repo3_url in train_urls
    in_val = repo2_url in val_urls and repo3_url in val_urls
    in_test = repo2_url in test_urls and repo3_url in test_urls

    assert in_train or in_val or in_test, "Related repos should be in same split"
    assert not (in_train and in_val), "Related repos should not be split"
    assert not (in_train and in_test), "Related repos should not be split"
    assert not (in_val and in_test), "Related repos should not be split"


def test_three_way_split_single_group():
    """Single group should go entirely to train."""
    entries = _make_entries("https://github.com/test/only", 100)
    train, val, test = train_val_test_split_group_stratified(
        entries,
        RepositoryRelationships(),
        train_ratio=0.7,
        val_ratio=0.15,
        test_ratio=0.15,
    )
    # Single indivisible group should go to largest split (train)
    assert len(train) == 100
    assert len(val) == 0
    assert len(test) == 0


def test_three_way_split_invalid_ratios():
    """Ratios must sum to 1.0."""
    entries = _make_entries("https://github.com/test/repo", 100)
    with pytest.raises(ValueError, match=r"Ratios must sum to 1\.0"):
        train_val_test_split_group_stratified(
            entries,
            RepositoryRelationships(),
            train_ratio=0.7,
            val_ratio=0.2,
            test_ratio=0.2,  # Sum is 1.1
        )


def test_three_way_split_custom_ratios():
    """Test with non-default ratios."""
    entries = (
        _make_entries("https://github.com/test/a", 300)
        + _make_entries("https://github.com/test/b", 300)
        + _make_entries("https://github.com/test/c", 300)
        + _make_entries("https://github.com/test/d", 100)
    )
    train, val, test = train_val_test_split_group_stratified(
        entries,
        RepositoryRelationships(),
        train_ratio=0.6,
        val_ratio=0.2,
        test_ratio=0.2,
        seed=123,
    )
    total = len(entries)
    assert len(train) + len(val) + len(test) == total
    # Verify approximate ratios (allow deviation for discrete groups)
    assert 0.4 <= len(train) / total <= 0.7
    assert 0.1 <= len(val) / total <= 0.35
    assert 0.05 <= len(test) / total <= 0.35


# --- train_val_test_split_random tests ---

def test_random_split_empty():
    train, val, test = train_val_test_split_random([], visualize=False)
    assert train == []
    assert val == []
    assert test == []


def test_random_split_preserves_total():
    entries = (
        _make_entries("https://github.com/test/a", 600)
        + _make_entries("https://github.com/test/b", 300)
        + _make_entries("https://github.com/test/c", 100)
    )
    train, val, test = train_val_test_split_random(entries, visualize=False)
    assert len(train) + len(val) + len(test) == 1000


def test_random_split_deterministic_with_seed():
    entries = (
        _make_entries("https://github.com/test/a", 100)
        + _make_entries("https://github.com/test/b", 100)
        + _make_entries("https://github.com/test/c", 100)
    )
    train1, val1, test1 = train_val_test_split_random(entries, seed=42, visualize=False)
    train2, val2, test2 = train_val_test_split_random(entries, seed=42, visualize=False)
    assert len(train1) == len(train2)
    assert len(val1) == len(val2)
    assert len(test1) == len(test2)
    # Check actual content is the same
    assert {e.commit_id for e in train1} == {e.commit_id for e in train2}


def test_random_split_different_seeds_differ():
    entries = (
        _make_entries("https://github.com/test/a", 100)
        + _make_entries("https://github.com/test/b", 100)
    )
    train1, _, _ = train_val_test_split_random(entries, seed=1, visualize=False)
    train2, _, _ = train_val_test_split_random(entries, seed=2, visualize=False)
    # Different seeds should produce different splits (with high probability)
    assert {e.commit_id for e in train1} != {e.commit_id for e in train2}


def test_random_split_respects_ratios():
    entries = _make_entries("https://github.com/test/a", 1000)
    train, val, test = train_val_test_split_random(
        entries,
        train_ratio=0.6,
        val_ratio=0.2,
        test_ratio=0.2,
        visualize=False,
    )
    # With 1000 entries, ratios should be exact
    assert len(train) == 600
    assert len(val) == 200
    assert len(test) == 200


# --- train_val_test_split_temporal tests ---

def _make_entries_with_timestamps(project_url: str, count: int, start_date: datetime | None = None) -> list[DatasetEntry]:
    """Create entries with sequential timestamps."""
    if start_date is None:
        start_date = datetime(2020, 1, 1, 0, 0, 0, tzinfo=UTC)

    return [
        DatasetEntry(
            project_url=project_url,
            commit_id=f"abc{i:04x}",
            src_datasets={"test"},
            commit_timestamp_utc=start_date + timedelta(days=i),
        )
        for i in range(count)
    ]


def test_temporal_split_empty():
    train, val, test = train_val_test_split_temporal([], visualize=False)
    assert train == []
    assert val == []
    assert test == []


def test_temporal_split_preserves_total():
    entries = (
        _make_entries_with_timestamps("https://github.com/test/a", 600, start_date=datetime(2020, 1, 1, tzinfo=UTC))
        + _make_entries_with_timestamps("https://github.com/test/b", 300, start_date=datetime(2020, 6, 1, tzinfo=UTC))
        + _make_entries_with_timestamps("https://github.com/test/c", 100, start_date=datetime(2021, 1, 1, tzinfo=UTC))
    )
    train, val, test = train_val_test_split_temporal(entries, visualize=False)
    assert len(train) + len(val) + len(test) == 1000


def test_temporal_split_chronological_ordering():
    """Oldest commits should be in train, newest in test."""
    entries = _make_entries_with_timestamps("https://github.com/test/a", 1000)
    train, val, test = train_val_test_split_temporal(
        entries,
        train_ratio=0.6,
        val_ratio=0.2,
        test_ratio=0.2,
        visualize=False,
    )

    # All train timestamps should be < all val timestamps < all test timestamps
    # We know timestamps are not None since _make_entries_with_timestamps creates them
    train_timestamps = [e.commit_timestamp_utc for e in train if e.commit_timestamp_utc is not None]
    val_timestamps = [e.commit_timestamp_utc for e in val if e.commit_timestamp_utc is not None]
    test_timestamps = [e.commit_timestamp_utc for e in test if e.commit_timestamp_utc is not None]

    assert len(train_timestamps) == len(train)  # Ensure all have timestamps
    assert len(val_timestamps) == len(val)
    assert len(test_timestamps) == len(test)

    assert max(train_timestamps) <= min(val_timestamps)
    assert max(val_timestamps) <= min(test_timestamps)


def test_temporal_split_requires_timestamps():
    """Entries without timestamps should raise ValueError."""
    entries = _make_entries("https://github.com/test/a", 100)  # No timestamps
    with pytest.raises(ValueError, match="All entries must have commit_timestamp_utc"):
        train_val_test_split_temporal(entries, visualize=False)


def test_temporal_split_respects_ratios():
    entries = _make_entries_with_timestamps("https://github.com/test/a", 1000)
    train, val, test = train_val_test_split_temporal(
        entries,
        train_ratio=0.6,
        val_ratio=0.2,
        test_ratio=0.2,
        visualize=False,
    )
    # With 1000 entries, ratios should be exact
    assert len(train) == 600
    assert len(val) == 200
    assert len(test) == 200
