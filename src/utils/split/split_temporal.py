"""Temporal splitting strategy based on commit timestamps."""

from dataset_entry import DatasetEntry
from utils.split.repository_relationships import RepositoryRelationships
from utils.split.split_common import split_by_ratio, validate_split_ratios, visualize_split


def train_val_test_split_temporal(
    entries: list[DatasetEntry],
    train_ratio: float = 0.6,
    val_ratio: float = 0.2,
    test_ratio: float = 0.2,
    relationships: RepositoryRelationships | None = None,
) -> tuple[list[DatasetEntry], list[DatasetEntry], list[DatasetEntry]]:
    """Temporal split based on commit timestamps."""
    if not entries:
        return [], [], []
    validate_split_ratios(train_ratio, val_ratio, test_ratio)

    if not all(e.commit_timestamp_utc is not None for e in entries):
        raise ValueError("All entries must have commit_timestamp_utc for temporal split")

    # Sort by timestamp
    sorted_entries = sorted(entries, key=lambda e: e.commit_timestamp_utc)  # type: ignore

    # Split the sorted entries
    train, val, test = split_by_ratio(sorted_entries, train_ratio, val_ratio, test_ratio)

    if relationships is not None:
        visualize_split(train, test, relationships, val_entries=val)

    return train, val, test
