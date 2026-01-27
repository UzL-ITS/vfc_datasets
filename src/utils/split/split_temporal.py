"""Temporal splitting strategy based on commit timestamps."""

from __future__ import annotations

from dataset_entry import DatasetEntry
from utils.split.repository_relationships import discover_repository_relationships
from utils.split.split_common import _split_by_ratio, _validate_split_ratios, visualize_split


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

    assert all(e.commit_timestamp_utc is not None for e in entries), "All entries must have commit_timestamp_utc for temporal split."

    # Sort by timestamp
    sorted_entries = sorted(entries, key=lambda e: e.commit_timestamp_utc)  # type: ignore

    # Split the sorted entries
    train, val, test = _split_by_ratio(sorted_entries, train_ratio, val_ratio, test_ratio)

    if visualize:
        relationships = discover_repository_relationships(entries)
        visualize_split(train, test, relationships, val_entries=val)

    return train, val, test
