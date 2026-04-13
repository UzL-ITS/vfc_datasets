import vfc_datasets
from vfc_datasets.utils.core.logging import setup_logging
from vfc_datasets.utils.core.statistics import print_dataset_stats

setup_logging("load_dataset")

if __name__ == "__main__":
    entries = vfc_datasets.BigVulDataset()
    print_dataset_stats(entries)
