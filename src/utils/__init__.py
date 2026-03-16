"""Utility modules for VFC datasets."""

# Core utilities (no DatasetEntry dependency)
from utils.core.logging import setup_logging

# Language utilities
from utils.extensions import EXTENSION_TO_LANGUAGE, extensions_for

# Git utilities (no DatasetEntry dependency)
from utils.git.github_client import AsyncGitHubClient, query_github_api_sync
from utils.git.url import (
    GitURL,
    normalize_commit_id,
    url_to_pathname,
)

# Other utilities
from utils.owasp import cwes_to_owasp
from utils.patterns import CVE_PATTERN, CWE_PATTERN

__all__ = [
    # Git
    "AsyncGitHubClient",
    "GitURL",
    "normalize_commit_id",
    "query_github_api_sync",
    "url_to_pathname",
    # Core
    "setup_logging",
    # Languages
    "EXTENSION_TO_LANGUAGE",
    "extensions_for",
    # Other
    "CVE_PATTERN",
    "CWE_PATTERN",
    "cwes_to_owasp",
]
