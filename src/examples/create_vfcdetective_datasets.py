import logging

from dotenv import load_dotenv

from config import DATASET_PATH
from dataset_entry import DatasetEntry

OUTPUT_PATH = DATASET_PATH / "new"
from datasets import (
    BaseDataset,
    BigVulDataset,
    CC900Dataset,
    CrossVulDataset,
    CVEFixesDataset,
    DevignDataset,
    ICVulDataset,
    MegaVulDataset,
    MorefixesDataset,
    MSR2019Dataset,
    PatchDBDataset,
    PySecDBDataset,
    RepoSPDDataset,
    SecBenchDataset,
    SPIDBDataset,
    SVENDataset,
    TQRGDataset,
    TracerDataset,
    VCMatchDataset,
)
from transformations import (
    C_CPP_EXTENSIONS,
    add_commit_information_api,
    add_commit_information_local,
    collapse_to_commit_level,
    extend_commit_ids_local,
    filter_by_extension,
    filter_by_has_unique_diff,
    deduplicate_commit_level,
    rm_entries_w_unreachable_project_urls,
    update_project_urls_inplace,
)
from utils.core.logging import setup_logging
from utils.core.serialization import save_entries, save_entries_csv
from utils.core.statistics import print_dataset_stats

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

load_dotenv()
log_filename = setup_logging("vfcdetective_datasets")

CSV_FIELDS = ["project_url", "commit_id", "is_vfc", "commit_timestamp_utc", "cwe_ids", "cve_ids"]

# Dataset groupings by validation type
MANUALLY_REVIEWED_DATASETS: list[type[BaseDataset]] = [
    SecBenchDataset,
    DevignDataset,
    MSR2019Dataset,
    SPIDBDataset,
    PatchDBDataset,
    TracerDataset,
    SVENDataset,
    PySecDBDataset, # This will take a while
    RepoSPDDataset,
]

ADVISORY_BASED_DATASETS: list[type[BaseDataset]] = [
    ICVulDataset,
    BigVulDataset,
    CVEFixesDataset,
    CC900Dataset,
    CrossVulDataset,
    TQRGDataset,
    VCMatchDataset,
    MegaVulDataset,
]

TOOL_BASED_DATASETS: list[type[BaseDataset]] = [MorefixesDataset]

# Transformations to apply to all datasets
TRANSFORMATIONS = [
    update_project_urls_inplace,
    rm_entries_w_unreachable_project_urls,
    extend_commit_ids_local,
    collapse_to_commit_level,
    deduplicate_commit_level,
    add_commit_information_local, # This takes a while on the first run
    add_commit_information_api, # API token helps
    filter_by_has_unique_diff,
]


# ---------------------------------------------------------------------------
# Main Pipeline
# ---------------------------------------------------------------------------


def _create_vfcdetective_datasets() -> None:
    """Build all VFCDetective datasets using a unified pipeline.

    Pipeline:
    1. Load ALL datasets once (MR + Advisory + Tool)
    2. Apply all heavy transformations once
    3. Save Dataset 4 (all sources, all languages)
    4. Filter to C/C++ → Dataset 3
    5. Filter by source → Dataset 2 (MR + Advisory) and Dataset 1 (MR only)
    """
    logging.info("=" * 65)
    logging.info("Building VFCDetective datasets")
    logging.info("=" * 65)

    # Step 1: Load all datasets
    logging.info("Step 1/5: Loading all datasets...")
    all_datasets = MANUALLY_REVIEWED_DATASETS + ADVISORY_BASED_DATASETS + TOOL_BASED_DATASETS
    all_entries: list[DatasetEntry] = []
    for dataset_class in all_datasets:
        all_entries.extend(dataset_class())
    logging.info("Loaded %d entries", len(all_entries))

    # Step 2: Apply transformations
    logging.info("Step 2/5: Applying transformations...")
    for t in TRANSFORMATIONS:
        all_entries = t(all_entries) or all_entries
    logging.info("After transformations: %d entries", len(all_entries))

    # Step 3: Save Dataset 4 (all sources, all languages)
    logging.info("Step 3/5: Saving Dataset 4 (all sources, all languages)...")
    save_entries(all_entries, OUTPUT_PATH / "dataset4-all.jsonl")
    save_entries_csv(all_entries, OUTPUT_PATH / "dataset4-all.csv", fields=CSV_FIELDS)

    # Step 4: Filter to C/C++ and save Dataset 3
    logging.info("Step 4/5: Filtering to C/C++...")
    cpp_entries = filter_by_extension(all_entries, extensions=C_CPP_EXTENSIONS)
    save_entries(cpp_entries, OUTPUT_PATH / "dataset3-all-cpp.jsonl")
    save_entries_csv(cpp_entries, OUTPUT_PATH / "dataset3-all-cpp.csv", fields=CSV_FIELDS)

    # Step 5: Filter by source datasets
    logging.info("Step 5/5: Filtering by source datasets...")
    mr_names = {ds.metadata.name for ds in MANUALLY_REVIEWED_DATASETS}
    advisory_names = {ds.metadata.name for ds in ADVISORY_BASED_DATASETS}

    # Dataset 2: MR + Advisory, C/C++ only
    ds2_entries = [e for e in cpp_entries if e.src_datasets & (mr_names | advisory_names)]
    save_entries(ds2_entries, OUTPUT_PATH / "dataset2-mr-advisory-cpp.jsonl")
    save_entries_csv(ds2_entries, OUTPUT_PATH / "dataset2-mr-advisory-cpp.csv", fields=CSV_FIELDS)

    # Dataset 1: MR only, C/C++ only
    ds1_entries = [e for e in cpp_entries if e.src_datasets & mr_names]
    save_entries(ds1_entries, OUTPUT_PATH / "dataset1-manually-reviewed-cpp.jsonl")
    save_entries_csv(ds1_entries, OUTPUT_PATH / "dataset1-manually-reviewed-cpp.csv", fields=CSV_FIELDS)

    # Summary
    logging.info("=" * 65)
    logging.info("All datasets created successfully!")
    logging.info("  Dataset 1 (MR, C/C++):          %6d entries", len(ds1_entries))
    logging.info("  Dataset 2 (MR+Advisory, C/C++): %6d entries", len(ds2_entries))
    logging.info("  Dataset 3 (All, C/C++):         %6d entries", len(cpp_entries))
    logging.info("  Dataset 4 (All, All):           %6d entries", len(all_entries))
    logging.info("=" * 65)

    # Source dataset statistics
    print_dataset_stats(all_entries)


if __name__ == "__main__":
    _create_vfcdetective_datasets()
