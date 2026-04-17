"""Load a single VFC dataset and log its statistics."""

import vfc_datasets
from vfc_datasets.utils.core.logging import setup_logging
from vfc_datasets.utils.core.statistics import log_dataset_stats

setup_logging("load_dataset")

if __name__ == "__main__":
    entries = vfc_datasets.BigVulDataset()
    log_dataset_stats(entries)
