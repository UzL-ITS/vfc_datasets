"""Filter transformations for dataset entries."""

from .collapse_to_commit_level import collapse_to_commit_level
from .duplicates import (
    deduplicate_commit_level,
    deduplicate_function_level,
    filter_by_has_unique_diff,
)
from .programming_languages import (
    C_CPP_EXTENSIONS,
    GO_EXTENSIONS,
    JAVA_EXTENSIONS,
    JAVASCRIPT_EXTENSIONS,
    PYTHON_EXTENSIONS,
    RUST_EXTENSIONS,
    filter_by_extension,
)

__all__ = [
    # Deduplication
    "deduplicate_function_level",
    "deduplicate_commit_level",
    "filter_by_has_unique_diff",
    # Granularity
    "collapse_to_commit_level",
    # Language filtering
    "filter_by_extension",
    "C_CPP_EXTENSIONS",
    "GO_EXTENSIONS",
    "JAVA_EXTENSIONS",
    "JAVASCRIPT_EXTENSIONS",
    "PYTHON_EXTENSIONS",
    "RUST_EXTENSIONS",
]
