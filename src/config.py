"""Central configuration for VFC-datasets project."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _env(name: str, default: str) -> str:
    """Get string env var with default."""
    return os.getenv(name, default)


def _env_optional(name: str) -> str | None:
    """Get optional string env var (None if not set)."""
    return os.getenv(name)


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
DATASET_PATH = _env_path("DATASET_PATH", BASE_DATA_PATH / "datasets")
RAW_DATA_PATH = DATASET_PATH / "raw"
CACHE_PATH = DATASET_PATH / "cache"
REPOSITORY_PATH = _env_path("REPOSITORY_PATH", BASE_DATA_PATH / "repositories")

# Create directories on import
for _p in [BASE_DATA_PATH, DATASET_PATH, RAW_DATA_PATH, CACHE_PATH, REPOSITORY_PATH]:
    _p.mkdir(parents=True, exist_ok=True)

# Workers
MAX_WORKERS = _env_int("MAX_WORKERS", os.cpu_count() or 1, minimum=1)

# API Tokens (optional)
HF_TOKEN = _env_optional("HF_TOKEN")
GITHUB_TOKEN = _env_optional("GITHUB_TOKEN")

# Git Operations
GIT_CLONE_TIMEOUT = _env_int("GIT_CLONE_TIMEOUT", 3600, minimum=1)  # 1 hour default

# Dataset Caching
USE_DATASET_CACHE = os.getenv("USE_DATASET_CACHE", "true").lower() in ("true", "yes")

# Max diff size in bytes
MAX_DIFF_SIZE = _env_int("MAX_DIFF_SIZE", 256 * 1024, minimum=0)  # 256 KB default

# MoreFixes Database (optional)
MOREFIXES_DB_HOST = _env("MOREFIXES_DB_HOST", "localhost")
MOREFIXES_DB_PORT = _env_int("MOREFIXES_DB_PORT", 5432, minimum=1, maximum=65535)
