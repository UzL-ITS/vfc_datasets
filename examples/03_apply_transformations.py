import logging

import vfc_datasets
from vfc_datasets import transformations
from vfc_datasets.utils.core.logging import setup_logging

setup_logging("apply_transformations")
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    entries = (
        vfc_datasets.MSR2019Dataset() + vfc_datasets.TracerDataset()
    )

    logger.info("Entries before deduplication: %d", len(entries))
    entries = transformations.deduplicate_within_repository(entries)
    logger.info("Entries after deduplication: %d", len(entries))
