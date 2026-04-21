"""Enrichment transformations for dataset entries."""

from .add_commit_data_api import add_commit_information_api
from .add_commit_data_local import add_commit_information_local
from .add_no_comment import strip_diff_comments
from .commit_id_enrichment import (
    extend_commit_ids_api,
    extend_commit_ids_local,
)
from .project_urls.update_project_urls import (
    filter_unreachable_project_urls,
    update_project_urls_inplace,
)
from .project_urls.url_mappings import (
    get_moved_urls,
    get_unreachable_urls,
)

__all__ = [
    # Commit data enrichment
    "add_commit_information_api",
    "add_commit_information_local",
    "strip_diff_comments",
    # Commit ID extension
    "extend_commit_ids_api",
    "extend_commit_ids_local",
    # Project URL handling
    "filter_unreachable_project_urls",
    "update_project_urls_inplace",
    "get_moved_urls",
    "get_unreachable_urls",
]
