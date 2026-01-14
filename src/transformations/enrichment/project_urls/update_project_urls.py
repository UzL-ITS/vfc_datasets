"""Transformation functions for updating and filtering project URLs.

These functions operate on a list of DatasetEntry objects to:
- Remove entries with unreachable project URLs
- Update entries with moved/renamed project URLs
"""

import logging

from dataset_entry import DatasetEntry
from transformations.enrichment.project_urls.url_mappings import (
    get_moved_urls,
    get_unreachable_urls,
)

logger = logging.getLogger(__name__)


def filter_unreachable_project_urls(entries: list[DatasetEntry]) -> list[DatasetEntry]:
    """Remove entries with unreachable project_url's"""
    filtered_entries: list[DatasetEntry] = []
    logger.info("REMOVE unreachable project_urls")
    unreachable_urls = get_unreachable_urls()
    for entry in entries:
        if entry.project_url in unreachable_urls:
            continue
        filtered_entries.append(entry)
    return filtered_entries


def update_project_urls_inplace(entries: list[DatasetEntry]) -> list[DatasetEntry]:
    """Update moved or fixed project_url's in-place and return the modified entries."""
    logger.info("UPDATE project_urls")
    changed_urls = 0
    moved_urls = get_moved_urls()
    for entry in entries:
        project_url = entry.project_url.lower().replace("http://", "https://")
        if project_url in moved_urls:
            entry.project_url = moved_urls[project_url]
            changed_urls += 1

    logger.info("%d project_urls were updated", changed_urls)
    return entries
