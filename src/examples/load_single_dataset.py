import vfc_datasets
from utils.core.logging import setup_logging
from utils.core.statistics import print_dataset_stats

setup_logging("load_single_dataset")

if __name__ == "__main__":
    entries = vfc_datasets.BigVulDataset()
    print_dataset_stats(entries)
