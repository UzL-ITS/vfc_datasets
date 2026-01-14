"""Project URL mappings and updates."""

from transformations.enrichment.project_urls.update_project_urls import (
    filter_unreachable_project_urls,
    update_project_urls_inplace,
)

__all__ = [
    "filter_unreachable_project_urls",
    "update_project_urls_inplace",
]
