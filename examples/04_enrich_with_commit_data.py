"""Enrich a dataset with commit messages, diffs, and timestamps via local clones."""

import vfc_datasets
from vfc_datasets import transformations
from vfc_datasets.utils.core.logging import setup_logging
from vfc_datasets.utils.core.statistics import log_dataset_stats

setup_logging("enrich_with_commit_data")

if __name__ == "__main__":
    entries = list(vfc_datasets.DevignDataset()) # Devign contains only 2 projects (FFmpeg, QEMU).

    entries = transformations.add_commit_information_local(entries)
    log_dataset_stats(entries)
