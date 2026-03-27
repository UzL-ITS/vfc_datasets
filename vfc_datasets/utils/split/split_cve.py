"""CVE-based splitting strategy with VFC-ratio-matched benign filling."""

from __future__ import annotations

import random

from vfc_datasets.dataset_entry import DatasetEntry

from .repository_relationships import discover_repository_relationships
from .split_common import visualize_split


def train_val_test_split_cve(
    entries: list[DatasetEntry],
    val_ratio: float = 0.5,
    test_ratio: float = 0.5,
    seed: int | None = None,
    visualize: bool = True,
) -> tuple[list[DatasetEntry], list[DatasetEntry], list[DatasetEntry]]:
    """Split by CVE presence: val/test contain CVE entries, filled with benign to match VFC ratio."""
    if not entries:
        return [], [], []

    rng = random.Random(seed)

    # Separate CVE and non-CVE entries
    cve_entries = [e for e in entries if e.cve_ids]
    non_cve_entries = [e for e in entries if not e.cve_ids]

    # Split CVE entries between val and test
    shuffled_cve = cve_entries.copy()
    rng.shuffle(shuffled_cve)
    split_idx = int(len(shuffled_cve) * val_ratio / (val_ratio + test_ratio))
    val_cve = shuffled_cve[:split_idx]
    test_cve = shuffled_cve[split_idx:]

    # Calculate target VFC ratio from overall dataset
    total_vfc = sum(1 for e in entries if e.is_vfc)
    target_vfc_ratio = total_vfc / len(entries)

    # Separate non-CVE entries into VFC and benign
    non_cve_vfc = [e for e in non_cve_entries if e.is_vfc]
    non_cve_benign = [e for e in non_cve_entries if not e.is_vfc]
    rng.shuffle(non_cve_benign)

    # Calculate benign fill for val and test
    val_vfc_count = sum(1 for e in val_cve if e.is_vfc)
    test_vfc_count = sum(1 for e in test_cve if e.is_vfc)
    val_benign_needed = _benign_needed_for_ratio(val_vfc_count, len(val_cve), target_vfc_ratio)
    test_benign_needed = _benign_needed_for_ratio(test_vfc_count, len(test_cve), target_vfc_ratio)

    # Assign benign samples to val and test, remainder to train
    val_benign = non_cve_benign[:val_benign_needed]
    test_benign = non_cve_benign[val_benign_needed : val_benign_needed + test_benign_needed]
    train_benign = non_cve_benign[val_benign_needed + test_benign_needed :]

    val = val_cve + val_benign
    test = test_cve + test_benign
    train = non_cve_vfc + train_benign

    if visualize:
        relationships = discover_repository_relationships(entries)
        visualize_split(train, test, relationships, val_entries=val)

    return train, val, test


def _benign_needed_for_ratio(
    vfc_count: int, current_total: int, target_vfc_ratio: float
) -> int:
    """Calculate benign samples needed to achieve target VFC ratio."""
    if target_vfc_ratio <= 0 or target_vfc_ratio >= 1:
        return 0
    target_total = int(vfc_count / target_vfc_ratio)
    return max(0, target_total - current_total)
