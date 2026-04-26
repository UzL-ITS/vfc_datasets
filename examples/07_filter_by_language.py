"""Filter a dataset down to commits that touch C/C++ source files."""

import logging

import vfc_datasets
from vfc_datasets import transformations
from vfc_datasets.utils.core.logging import setup_logging

setup_logging("filter_by_language")
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    entries = vfc_datasets.DevignDataset()
    entries = transformations.add_commit_information_local(entries)

    logger.info("Entries before filtering: %d", len(entries))
    entries = transformations.filter_by_extension(entries, {"c", "h", "cpp", "hpp", "cc"})
    logger.info("Entries after filtering: %d", len(entries))
