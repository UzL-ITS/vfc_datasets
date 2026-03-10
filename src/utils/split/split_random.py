"""Random splitting strategy without respecting repository relationships."""

import random

from dataset_entry import DatasetEntry
from utils.split.repository_relationships import discover_repository_relationships
from utils.split.split_common import _split_by_ratio, _validate_split_ratios, visualize_split


def train_val_test_split_random(
    entries: list[DatasetEntry],
    train_ratio: float = 0.6,
    val_ratio: float = 0.2,
    test_ratio: float = 0.2,
    seed: int | None = None,
    visualize: bool = True,
) -> tuple[list[DatasetEntry], list[DatasetEntry], list[DatasetEntry]]:
    """Random split without respecting repository relationships."""
    if not entries:
        return [], [], []
    _validate_split_ratios(train_ratio, val_ratio, test_ratio)

    # Shuffle entries
    rng = random.Random(seed)
    shuffled = entries.copy()
    rng.shuffle(shuffled)

    # Split according to ratios
    train, val, test = _split_by_ratio(shuffled, train_ratio, val_ratio, test_ratio)

    if visualize:
        relationships = discover_repository_relationships(entries)
        visualize_split(train, test, relationships, val_entries=val)

    return train, val, test
