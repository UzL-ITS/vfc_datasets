"""Random splitting strategy without respecting repository relationships."""

import random

from vfc_datasets.dataset_entry import DatasetEntry
from vfc_datasets.utils.relationships import RepositoryRelationships

from .split_common import split_by_ratio, validate_split_ratios, visualize_split


def train_val_test_split_random(
    entries: list[DatasetEntry],
    train_ratio: float = 0.6,
    val_ratio: float = 0.2,
    test_ratio: float = 0.2,
    seed: int | None = None,
    relationships: RepositoryRelationships | None = None,
) -> tuple[list[DatasetEntry], list[DatasetEntry], list[DatasetEntry]]:
    """Random split without respecting repository relationships."""
    if not entries:
        return [], [], []
    validate_split_ratios(train_ratio, val_ratio, test_ratio)

    # Shuffle entries
    rng = random.Random(seed)
    shuffled = entries.copy()
    rng.shuffle(shuffled)

    # Split according to ratios
    train, val, test = split_by_ratio(shuffled, train_ratio, val_ratio, test_ratio)

    if relationships is not None:
        visualize_split(train, test, relationships, val_entries=val)

    return train, val, test
