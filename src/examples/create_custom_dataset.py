import logging

from datasets.commit_level.bigvul import BigVulDataset
from datasets.commit_level.devign import DevignDataset
from transformations.filters.duplicates import deduplicate_commit_level
from utils.core.logging import setup_logging
from utils.core.statistics import print_dataset_stats

log_filename = setup_logging("create_custom_dataset")


def _create_custom_dataset():
    logging.info("Building a custom Dataset:")
    entries = BigVulDataset() + DevignDataset()
    return deduplicate_commit_level(entries)


if __name__ == "__main__":
    custom_dataset = _create_custom_dataset()
    print_dataset_stats(custom_dataset)
