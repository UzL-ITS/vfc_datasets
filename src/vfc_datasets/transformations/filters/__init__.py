"""Filter transformations for dataset entries."""

from .collapse_to_commit_level import collapse_to_commit_level
from .duplicates import (
    deduplicate_across_related_repositories,
    deduplicate_function_level,
    deduplicate_within_repository,
    filter_by_has_unique_diff,
)
from .extensions import filter_by_extension

__all__ = [
    # Deduplication
    "deduplicate_across_related_repositories",
    "deduplicate_within_repository",
    "deduplicate_function_level",
    "filter_by_has_unique_diff",
    # Granularity
    "collapse_to_commit_level",
    # Extension filtering
    "filter_by_extension",
]
