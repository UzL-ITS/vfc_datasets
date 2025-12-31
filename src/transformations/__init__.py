"""Dataset filters and enrichment transformations."""

# Re-export commonly used transformations
from .enrichment import (
    add_commit_information_api,
    add_commit_information_local,
    extend_commit_ids_api,
    extend_commit_ids_local,
    get_moved_urls,
    get_unreachable_urls,
    rm_entries_w_unreachable_project_urls,
    update_project_urls_inplace,
)
from .filters import (
    C_CPP_EXTENSIONS,
    GO_EXTENSIONS,
    JAVA_EXTENSIONS,
    JAVASCRIPT_EXTENSIONS,
    PYTHON_EXTENSIONS,
    RUST_EXTENSIONS,
    collapse_to_commit_level,
    deduplicate_commit_level,
    deduplicate_function_level,
    filter_by_extension,
    filter_by_has_unique_diff,
)

__all__ = [
    # Deduplication
    "deduplicate_function_level",
    "deduplicate_commit_level",
    # Filters
    "collapse_to_commit_level",
    "filter_by_extension",
    "filter_by_has_unique_diff",
    # Language extension sets
    "C_CPP_EXTENSIONS",
    "GO_EXTENSIONS",
    "JAVA_EXTENSIONS",
    "JAVASCRIPT_EXTENSIONS",
    "PYTHON_EXTENSIONS",
    "RUST_EXTENSIONS",
    # Enrichment
    "add_commit_information_api",
    "add_commit_information_local",
    "extend_commit_ids_api",
    "extend_commit_ids_local",
    "get_moved_urls",
    "get_unreachable_urls",
    "rm_entries_w_unreachable_project_urls",
    "update_project_urls_inplace",
]
