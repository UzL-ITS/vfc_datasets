"""Central configuration for VFC-datasets project."""

import logging
import os
from pathlib import Path


def _env_int(
    name: str, default: int, *, minimum: int | None = None, maximum: int | None = None
) -> int:
    """Get integer env var with validation."""
    value = os.getenv(name)
    if value is None:
        return default
    parsed = int(value)
    if minimum is not None and parsed < minimum:
        raise ValueError(f"{name} must be >= {minimum}, got {parsed}")
    if maximum is not None and parsed > maximum:
        raise ValueError(f"{name} must be <= {maximum}, got {parsed}")
    return parsed


def _env_path(name: str, default: Path) -> Path:
    """Get path env var, expanding ~."""
    value = os.getenv(name)
    if value is None:
        return default
    return Path(value).expanduser()


# Paths
BASE_DATA_PATH = _env_path("DATA_PATH", Path(".data"))
DATASET_PATH = BASE_DATA_PATH / "datasets"
RAW_DATA_PATH = DATASET_PATH / "raw"
REPOSITORY_PATH = _env_path("REPOSITORY_PATH", BASE_DATA_PATH / "repositories")

# Workers
MAX_WORKERS = _env_int("MAX_WORKERS", os.cpu_count() or 1, minimum=1)

# API Base URLs
GITHUB_API_URL = os.getenv("GITHUB_API_URL", "https://api.github.com")

# Git Operations
GIT_CLONE_TIMEOUT = _env_int("GIT_CLONE_TIMEOUT", 3600, minimum=1)  # 1 hour default
MAX_CLONE_WORKERS = _env_int("MAX_CLONE_WORKERS", 4, minimum=1)

# Clone strategy: repos with >= this many commits to enrich get a full clone
FULL_CLONE_THRESHOLD = _env_int("FULL_CLONE_THRESHOLD", 100, minimum=1)

# Partial clone size filter. Git accepts suffixes (k/m/g). Blobs above this
# size are omitted during clone and fetched lazily on access.
BLOB_SIZE_LIMIT = os.getenv("BLOB_SIZE_LIMIT", "1m")

# Dataset Caching
USE_DATASET_CACHE = os.getenv("USE_DATASET_CACHE", "true").lower() in ("true", "yes")

# Logging
LOG_LEVEL: int = logging.getLevelNamesMapping().get(
    os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO
)
LOG_DIR = BASE_DATA_PATH / "logs"

# Max diff size in characters
MAX_DIFF_SIZE = _env_int("MAX_DIFF_SIZE", 100_000, minimum=0)
