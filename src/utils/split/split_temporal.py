"""Temporal splitting strategy based on commit timestamps."""

from __future__ import annotations

from dataset_entry import DatasetEntry
from utils.split.repository_relationships import discover_repository_relationships
from utils.split.split_common import _split_by_ratio, _validate_split_ratios, visualize_split


def _sort_and_validate_temporal(
    entries: list[DatasetEntry],
) -> list[DatasetEntry]:
    """Validate timestamps and return entries sorted chronologically."""
    if not all(e.commit_timestamp_utc is not None for e in entries):
        raise ValueError("All entries must have commit_timestamp_utc for temporal split")
    return sorted(entries, key=lambda e: e.commit_timestamp_utc)  # type: ignore


def _slice_by_percent(
    sorted_entries: list[DatasetEntry],
    start: float,
    end: float,
) -> list[DatasetEntry]:
    """Slice a sorted list by start/end percentages (0.0–1.0)."""
    n = len(sorted_entries)
    return sorted_entries[int(n * start) : int(n * end)]


def train_val_test_split_temporal(
    entries: list[DatasetEntry],
    train_ratio: float = 0.6,
    val_ratio: float = 0.2,
    test_ratio: float = 0.2,
    visualize: bool = True,
) -> tuple[list[DatasetEntry], list[DatasetEntry], list[DatasetEntry]]:
    """Temporal split based on commit timestamps."""
    if not entries:
        return [], [], []
    _validate_split_ratios(train_ratio, val_ratio, test_ratio)

    sorted_entries = _sort_and_validate_temporal(entries)
    train, val, test = _split_by_ratio(sorted_entries, train_ratio, val_ratio, test_ratio)

    if visualize:
        relationships = discover_repository_relationships(entries)
        visualize_split(train, test, relationships, val_entries=val)

    return train, val, test


def train_val_test_split_temporal_sliding(
    entries: list[DatasetEntry],
    visualize: bool = True,
    *,
    window_size: float = 0.6,
    step: float = 0.05,
) -> list[tuple[list[DatasetEntry], list[DatasetEntry], list[DatasetEntry]]]:
    """Sliding-window temporal splits with configurable step size.

    Each window covers *window_size* of the data (split equally into
    train/val/test) and advances by *step* each iteration.  The large
    window (Q1+Q2 train, Q3 val, Q4 test) is returned first, followed
    by all sliding windows.

    With defaults (window_size=0.6, step=0.05) this yields:
        - 1 large window  (40% train, 20% val, 20% test)
        - 9 sliding windows (each 20% train, 20% val, 20% test)
    """
    num_sliding = int((1.0 - window_size) / step) + 1
    if not entries:
        return [([], [], []) for _ in range(1 + num_sliding)]

    sorted_entries = _sort_and_validate_temporal(entries)
    part = window_size / 3

    # Large window: Q1+Q2 train, Q3 val, Q4 test
    large_window = (
        _slice_by_percent(sorted_entries, 0.0, 2 * part),
        _slice_by_percent(sorted_entries, 2 * part, 3 * part),
        _slice_by_percent(sorted_entries, 3 * part, 4 * part),
    )

    # Sliding windows at 5% increments
    sliding_windows = []
    for i in range(num_sliding):
        start = round(i * step, 10)
        sliding_windows.append((
            _slice_by_percent(sorted_entries, start, start + part),
            _slice_by_percent(sorted_entries, start + part, start + 2 * part),
            _slice_by_percent(sorted_entries, start + 2 * part, start + 3 * part),
        ))

    windows = [large_window, *sliding_windows]

    if visualize:
        relationships = discover_repository_relationships(entries)
        for train, val, test in windows:
            visualize_split(train, test, relationships, val_entries=val)

    return windows
