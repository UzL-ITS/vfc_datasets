"""Split creation utilities."""

import logging
from pathlib import Path

from vfc_datasets.dataset_entry import DatasetEntry
from vfc_datasets.utils.core.serialization import save_entries_csv

from .repository_relationships import RepositoryRelationships
from .split_common import group_related_repos, visualize_split
from .split_group_stratified import train_val_test_split_group_stratified
from .split_random import train_val_test_split_random
from .split_temporal import train_val_test_split_temporal

logger = logging.getLogger(__name__)


def _evaluate_split_quality(
    train: list[DatasetEntry],
    val: list[DatasetEntry],
    test: list[DatasetEntry],
    relationships: RepositoryRelationships,
) -> dict[str, float]:
    """
    Evaluate the quality of a train/val/test split.

    Returns scores where lower is better.

    Metrics:
    - commits_per_project_balance: Max relative deviation in commits-per-project across splits
    - vfc_ratio_balance: Max relative deviation in VFC ratios (label balance) across splits
    - combined_score: Weighted combination (0.4 * commits_per_project_balance + 0.6 * vfc_ratio_balance)
    """
    splits = [train, val, test]

    # 1. Commits-per-project balance
    commits_per_project = []
    for split in splits:
        groups = group_related_repos(split, relationships)
        num_projects = len(groups)
        num_commits = len(split)
        commits_per_project.append(num_commits / num_projects if num_projects > 0 else 0)

    mean_commits_per_project = (
        sum(commits_per_project) / len(commits_per_project) if commits_per_project else 0
    )
    if mean_commits_per_project > 0:
        commits_per_project_balance = max(
            abs(r - mean_commits_per_project) / mean_commits_per_project
            for r in commits_per_project
        )
    else:
        commits_per_project_balance = 0.0

    # 2. VFC ratio (label) balance
    vfc_ratios = []
    for split in splits:
        if len(split) > 0:
            vfc_count = sum(1 for e in split if e.is_vfc)
            vfc_ratios.append(vfc_count / len(split))
        else:
            vfc_ratios.append(0.0)

    mean_vfc = sum(vfc_ratios) / len(vfc_ratios) if vfc_ratios else 0
    if mean_vfc > 0:
        vfc_ratio_balance = max(abs(vfc - mean_vfc) / mean_vfc for vfc in vfc_ratios)
    else:
        vfc_ratio_balance = 0.0

    # 3. Combined score
    combined_score = 0.4 * commits_per_project_balance + 0.6 * vfc_ratio_balance

    return {
        "commits_per_project_balance": commits_per_project_balance,
        "vfc_ratio_balance": vfc_ratio_balance,
        "combined_score": combined_score,
    }


def create_random_split(
    entries: list[DatasetEntry],
    name: str,
    output_path: Path,
    seed: int,
    *,
    relationships: RepositoryRelationships | None = None,
    train_ratio: float = 0.6,
    val_ratio: float = 0.2,
    test_ratio: float = 0.2,
) -> None:
    """Create a random split with the specified seed."""
    logger.info("Creating random split for %s - seed %d", name, seed)

    train, val, test = train_val_test_split_random(
        entries,
        train_ratio=train_ratio,
        val_ratio=val_ratio,
        test_ratio=test_ratio,
        seed=seed,
        relationships=relationships,
    )

    save_entries_csv(train, output_path / f"{name}-random-seed{seed}-train.csv")
    save_entries_csv(val, output_path / f"{name}-random-seed{seed}-val.csv")
    save_entries_csv(test, output_path / f"{name}-random-seed{seed}-test.csv")


def create_temporal_split(
    entries: list[DatasetEntry],
    name: str,
    output_path: Path,
    *,
    relationships: RepositoryRelationships | None = None,
    train_ratio: float = 0.6,
    val_ratio: float = 0.2,
    test_ratio: float = 0.2,
) -> None:
    """Create a temporal split (chronological)."""
    logger.info("Creating temporal split for %s", name)

    train, val, test = train_val_test_split_temporal(
        entries,
        train_ratio=train_ratio,
        val_ratio=val_ratio,
        test_ratio=test_ratio,
        relationships=relationships,
    )

    save_entries_csv(train, output_path / f"{name}-temporal-train.csv")
    save_entries_csv(val, output_path / f"{name}-temporal-val.csv")
    save_entries_csv(test, output_path / f"{name}-temporal-test.csv")


def create_top_n_group_stratified_splits(
    entries: list[DatasetEntry],
    name: str,
    output_path: Path,
    relationships: RepositoryRelationships,
    *,
    train_ratio: float = 0.6,
    val_ratio: float = 0.2,
    test_ratio: float = 0.2,
    num_seeds: int = 50,
    top_n: int = 3,
) -> None:
    """Find the best *top_n* group-stratified splits out of *num_seeds* seeds and save them."""
    logger.info("Creating group-stratified splits for %s (evaluating %d seeds)", name, num_seeds)

    seed_results = []
    for seed in range(1, num_seeds + 1):
        train, val, test = train_val_test_split_group_stratified(
            entries,
            relationships,
            train_ratio=train_ratio,
            val_ratio=val_ratio,
            test_ratio=test_ratio,
            seed=seed,
            visualize=False,
        )
        metrics = _evaluate_split_quality(train, val, test, relationships)
        seed_results.append((seed, train, val, test, metrics))
        logger.debug(
            "Seed %2d: combined=%.4f (commits_per_project_balance=%.4f, vfc_ratio_balance=%.4f)",
            seed,
            metrics["combined_score"],
            metrics["commits_per_project_balance"],
            metrics["vfc_ratio_balance"],
        )

    # Sort by combined score (lower is better) and take top N
    seed_results.sort(key=lambda x: x[4]["combined_score"])
    top_results = seed_results[:top_n]

    summary_lines = [f"Top {top_n} group-stratified seeds:"]
    for rank, (seed, _, _, _, metrics) in enumerate(top_results, 1):
        summary_lines.append(
            f"  #{rank} seed {seed}: "
            f"combined_score={metrics['combined_score']:.4f}, "
            f"commits_per_project_balance={metrics['commits_per_project_balance']:.4f}, "
            f"vfc_ratio_balance={metrics['vfc_ratio_balance']:.4f}"
        )
    logger.info("\n".join(summary_lines))

    for seed, train, val, test, _ in top_results:
        visualize_split(train, test, relationships, val_entries=val)

        save_entries_csv(train, output_path / f"{name}-groupstrat-seed{seed}-train.csv")
        save_entries_csv(val, output_path / f"{name}-groupstrat-seed{seed}-val.csv")
        save_entries_csv(test, output_path / f"{name}-groupstrat-seed{seed}-test.csv")
