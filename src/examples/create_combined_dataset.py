import transformations
import vfc_datasets
from utils.core.logging import setup_logging
from utils.core.statistics import print_dataset_stats

setup_logging("create_combined_dataset")

if __name__ == "__main__":
    entries = (
        vfc_datasets.BigVulDataset() + vfc_datasets.DevignDataset() + vfc_datasets.CVEFixesDataset()
    )
    entries = transformations.collapse_to_commit_level(entries)
    entries = transformations.deduplicate_within_repository(entries)
    print_dataset_stats(entries)
