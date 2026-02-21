import logging

import transformations
import vfc_datasets
from utils.core.logging import setup_logging
from utils.core.statistics import print_dataset_stats

log_filename = setup_logging("create_custom_dataset")


def _create_custom_dataset():
    logging.info("Building a custom Dataset:")
    entries = vfc_datasets.BigVulDataset() + vfc_datasets.DevignDataset()
    return transformations.deduplicate_within_repository(entries)


if __name__ == "__main__":
    custom_dataset = _create_custom_dataset()
    print_dataset_stats(custom_dataset)
