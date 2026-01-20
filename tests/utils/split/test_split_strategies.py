"""Tests for train/test split functions."""

from dataset_entry import DatasetEntry
from utils.split.dataset_split import (
    _greedy_assign,
    _optimize_assignment,
    train_test_split_group_stratified,
)
from utils.split.repository_relationships import RepositoryRelationships


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


def _entries_from_groups(groups):
    entries = []
    for project_urls, count in groups:
        entries.extend(_make_entries(next(iter(project_urls)), count))
    return entries


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
