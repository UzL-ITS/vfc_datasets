from collections.abc import Callable

from dotenv import load_dotenv

import datasets
import transformations
from config import DATASET_PATH
from dataset_entry import DatasetEntry
from utils.core.logging import setup_logging
from utils.core.serialization import load_entries, save_entries
from utils.core.statistics import print_dataset_stats
from utils.extensions import extensions_for
from utils.split import (
    create_random_split,
    create_temporal_split,
    create_top_n_group_stratified_splits,
    discover_repository_relationships,
)

load_dotenv()
setup_logging("vfcdetective_datasets")

OUTPUT_PATH = DATASET_PATH / "new"

MANUALLY_REVIEWED_DATASETS: list[type[datasets.BaseDataset]] = [
    datasets.SecBenchDataset,
    datasets.DevignDataset,
    datasets.MSR2019Dataset,
    datasets.SPIDBDataset,
    datasets.PatchDBDataset,
    datasets.TracerDataset,
    datasets.SVENDataset,
    datasets.PySecDBDataset,
    datasets.RepoSPDDataset,
]

ADVISORY_BASED_DATASETS: list[type[datasets.BaseDataset]] = [
    datasets.ICVulDataset,
    datasets.BigVulDataset,
    datasets.CVEFixesDataset,
    datasets.CC900Dataset,
    datasets.CrossVulDataset,
    datasets.TQRGDataset,
    datasets.VCMatchDataset,
    datasets.MegaVulDataset,
]

TOOL_BASED_DATASETS: list[type[datasets.BaseDataset]] = [datasets.MorefixesDataset]


TRANSFORMATION_PIPELINE: list[Callable[[list[DatasetEntry]], list[DatasetEntry]]] = [
    transformations.update_project_urls_inplace,
    transformations.filter_unreachable_project_urls,
    transformations.extend_commit_ids_local,
    transformations.collapse_to_commit_level,
    transformations.deduplicate_within_repository,
    transformations.deduplicate_across_related_repositories,
    transformations.add_commit_information_local,
    # transformations.add_commit_information_api,
    transformations.add_commit_diff_no_comment,
    transformations.filter_by_has_unique_diff,
]


def apply_transformations(entries: list[DatasetEntry]) -> list[DatasetEntry]:
    """Apply all enrichment and deduplication transformations."""
    for transform in TRANSFORMATION_PIPELINE:
        entries = transform(entries)
    # Drop entries where diff couldn't be retrieved.
    return [e for e in entries if e.commit_diff is not None]


def build_dataset_variants(all_entries: list[DatasetEntry]) -> dict[str, list[DatasetEntry]]:
    """Build all dataset variants from the full entry set."""
    mr_names = {ds.metadata.name for ds in MANUALLY_REVIEWED_DATASETS}
    advisory_names = {ds.metadata.name for ds in ADVISORY_BASED_DATASETS}
    cpp_entries = transformations.filter_by_extension(all_entries, extensions=extensions_for("c", "cpp"))

    return {
        "dataset1-manually-reviewed-cpp": [e for e in cpp_entries if e.src_datasets & mr_names],
        "dataset2-mr-advisory-cpp": [e for e in cpp_entries if e.src_datasets & (mr_names | advisory_names)],
        "dataset3-all-cpp": cpp_entries,
        "dataset4-all": all_entries,
    }


def load_vfc_datasets_if_exist() -> dict[str, list[DatasetEntry]] | None:
    """Load datasets from disk if they exist, otherwise return None."""
    dataset_names = ["dataset1-manually-reviewed-cpp", "dataset2-mr-advisory-cpp", "dataset3-all-cpp", "dataset4-all"]
    if all((OUTPUT_PATH / f"{name}.jsonl").exists() for name in dataset_names):
        print("Datasets already exist, loading from disk...")
        return {name: load_entries(OUTPUT_PATH / f"{name}.jsonl") for name in dataset_names}
    return None


def create_vfc_datasets() -> dict[str, list[DatasetEntry]]:
    """Load all datasets, apply transformations, and save variants to disk."""
    # Load raw datasets
    entries: list[DatasetEntry] = []
    for dataset_class in MANUALLY_REVIEWED_DATASETS + ADVISORY_BASED_DATASETS + TOOL_BASED_DATASETS:
        entries.extend(dataset_class())

    # Apply transformations
    entries = apply_transformations(entries)
    print_dataset_stats(entries)

    # Build and save variants
    vfc_datasets = build_dataset_variants(entries)
    for name, variant_entries in vfc_datasets.items():
        save_entries(variant_entries, OUTPUT_PATH / f"{name}.jsonl")

    return vfc_datasets

def create_splits(entries: list[DatasetEntry], name: str) -> None:
    """Create all split variants: random, temporal, and group-stratified."""
    relationships = discover_repository_relationships(entries)

    # Create 3 random splits
    for seed in [1, 2, 3]:
        create_random_split(entries, name, OUTPUT_PATH, seed)

    # Create 1 temporal split
    create_temporal_split(entries, name, OUTPUT_PATH)

    # Create 3 group-stratified splits (best out of 50 seeds)
    create_top_n_group_stratified_splits(entries, name, OUTPUT_PATH, relationships)


if __name__ == "__main__":
    vfc_datasets = load_vfc_datasets_if_exist()
    if vfc_datasets is None:
        vfc_datasets = create_vfc_datasets()
    dataset_target = "dataset3-all-cpp"
    create_splits(vfc_datasets[dataset_target], dataset_target)
