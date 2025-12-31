"""Dataset statistics utilities."""

from typing import TypedDict

from dataset_entry import DatasetEntry


class DatasetStats(TypedDict):
    total: int
    with_diff: int
    projects: int


def compute_dataset_stats(entries: list[DatasetEntry]) -> dict[str, DatasetStats]:
    """Compute per-dataset statistics from entries."""
    # Collect all dataset names from entries
    all_names: set[str] = set()
    for entry in entries:
        all_names.update(entry.src_datasets)

    # Per-dataset stats
    totals: dict[str, int] = dict.fromkeys(all_names, 0)
    with_diffs: dict[str, int] = dict.fromkeys(all_names, 0)
    projects: dict[str, set[str]] = {name: set() for name in all_names}

    for entry in entries:
        for src in entry.src_datasets:
            totals[src] += 1
            projects[src].add(entry.project_url)
            if entry.commit_diff is not None:
                with_diffs[src] += 1

    return {
        name: DatasetStats(
            total=totals[name],
            with_diff=with_diffs[name],
            projects=len(projects[name]),
        )
        for name in all_names
    }


def print_dataset_stats(entries: list[DatasetEntry]) -> None:
    """Print dataset statistics table to logging."""
    import logging

    stats = compute_dataset_stats(entries)

    logging.info("")
    logging.info("Statistics by source dataset:")
    logging.info("  %-20s %7s %7s %8s %8s", "Dataset", "Entries", "w/Diff", "Diff%", "Projects")
    logging.info("-" * 65)

    for name, s in sorted(stats.items(), key=lambda x: -x[1]["total"]):
        pct = (s["with_diff"] / s["total"] * 100) if s["total"] > 0 else 0
        logging.info(
            "  %-20s %7d %7d %7.1f%% %8d", name, s["total"], s["with_diff"], pct, s["projects"]
        )

    logging.info("-" * 65)
    total = len(entries)
    with_diff = sum(1 for e in entries if e.commit_diff is not None)
    unique_projects = len({e.project_url for e in entries})
    pct = (with_diff / total * 100) if total > 0 else 0
    logging.info(
        "  %-20s %7d %7d %7.1f%% %8d",
        "TOTAL",
        total,
        with_diff,
        pct,
        unique_projects,
    )
    logging.info("=" * 65)
