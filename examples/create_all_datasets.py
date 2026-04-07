"""Load all VFC datasets and enrich them with commit information."""

import os
from collections.abc import Callable
from pathlib import Path

from dotenv import load_dotenv

import vfc_datasets
from vfc_datasets import transformations
from vfc_datasets.dataset_entry import DatasetEntry
from vfc_datasets.utils.core.logging import setup_logging
from vfc_datasets.utils.core.serialization import save_entries
from vfc_datasets.utils.core.statistics import print_dataset_stats

load_dotenv()
setup_logging("create_all_datasets")

OUTPUT_FILE = Path(os.getenv("DATA_PATH", ".data")) / "datasets" / "new" / "all_datasets.jsonl"


def _all_concrete_datasets(
    base: type[vfc_datasets.BaseDataset],
) -> list[type[vfc_datasets.BaseDataset]]:
    """Recursively collect all concrete BaseDataset subclasses (those with metadata)."""
    result: list[type[vfc_datasets.BaseDataset]] = []
    for sub in base.__subclasses__():
        if hasattr(sub, "metadata") and sub.metadata is not None:
            result.append(sub)
        result.extend(_all_concrete_datasets(sub))
    return result


TRANSFORMATION_PIPELINE: list[Callable[[list[DatasetEntry]], list[DatasetEntry]]] = [
    transformations.update_project_urls_inplace,
    transformations.filter_unreachable_project_urls,
    transformations.extend_commit_ids_local,
    transformations.collapse_to_commit_level,
    transformations.deduplicate_within_repository,
    transformations.add_commit_information_local,
]


def create_all_datasets() -> list[DatasetEntry]:
    """Load all datasets, deduplicate, and enrich with commit information."""
    all_datasets = _all_concrete_datasets(vfc_datasets.BaseDataset)

    entries: list[DatasetEntry] = []
    for dataset_class in all_datasets:
        entries.extend(dataset_class())

    for transform in TRANSFORMATION_PIPELINE:
        entries = transform(entries)

    print_dataset_stats(entries)
    save_entries(entries, OUTPUT_FILE)
    return entries


if __name__ == "__main__":
    all_entries = create_all_datasets()
    print_dataset_stats(all_entries)
