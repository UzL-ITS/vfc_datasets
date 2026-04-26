"""Transformation functions for updating and filtering project URLs.

These functions operate on dataset entries to:
- Remove entries with unreachable project URLs
- Update entries with moved/renamed project URLs
"""

import logging
from collections.abc import Iterable

from vfc_datasets.dataset_entry import DatasetEntry

from .url_mappings import (
    get_moved_urls,
    get_unreachable_urls,
)

logger = logging.getLogger(__name__)


def filter_unreachable_project_urls(entries: Iterable[DatasetEntry]) -> list[DatasetEntry]:
    """Remove entries with unreachable project_url's"""
    logger.info("REMOVE unreachable project_urls")
    unreachable_urls = get_unreachable_urls()
    return [e for e in entries if e.project_url not in unreachable_urls]


def update_project_urls_inplace(entries: Iterable[DatasetEntry]) -> list[DatasetEntry]:
    """Update moved or fixed project_url's in-place and return the modified entries."""
    logger.info("UPDATE project_urls")
    entries = list(entries)
    changed_urls = 0
    moved_urls = get_moved_urls()
    for entry in entries:
        if entry.project_url in moved_urls:
            entry.project_url = moved_urls[entry.project_url]
            changed_urls += 1

    logger.info("%d project_urls were updated", changed_urls)
    return entries
