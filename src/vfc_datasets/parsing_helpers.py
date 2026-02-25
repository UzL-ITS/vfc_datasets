from __future__ import annotations

import logging
import math
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from utils.git.url import COMMIT_HASH_PATTERN, GitURL, normalize_commit_id
from utils.patterns import CVE_PATTERN

logger = logging.getLogger(__name__)


def _resolve_ref_local(ref: str, git_url: str) -> str | None:
    """Try to resolve a symbolic ref using a local repository clone."""
    try:
        from git import Repo
        from git.exc import BadName, InvalidGitRepositoryError

        from utils.git.url import url_to_pathname
    except ImportError:
        return None

    # Check if local repo exists (don't clone just for ref resolution)
    repo_path = Path(url_to_pathname(git_url))
    if not repo_path.exists():
        return None

    repo = None
    try:
        repo = Repo(repo_path)
        commit = repo.commit(ref)
        sha = commit.hexsha

        normalized_sha = normalize_commit_id(sha)
        if normalized_sha:
            logger.debug("Resolved %r -> %s locally for %s", ref, normalized_sha, git_url)
            return normalized_sha
    except (BadName, InvalidGitRepositoryError, ValueError):
        # Ref not found locally or repo is invalid
        pass
    except Exception as exc:
        logger.debug("Local ref resolution failed for %r: %s", ref, exc)
    finally:
        if repo is not None:
            repo.close()

    return None


def _resolve_ref_via_api(ref: str, git_url: str) -> str | None:
    """Resolve a symbolic ref via GitHub API (fallback)."""
    parsed_url = GitURL.parse(git_url)
    if not parsed_url or parsed_url.host != "github.com":
        logger.debug("API ref resolution only supported for GitHub: %s", git_url)
        return None

    if not parsed_url.owner or not parsed_url.repo:
        logger.warning("Missing owner/repo in URL: %s", git_url)
        return None

    api_url = f"https://api.github.com/repos/{parsed_url.owner}/{parsed_url.repo}/commits/{ref}"

    try:
        from utils.git.github_client import query_github_api_sync

        logger.info(
            "Resolving symbolic ref %r for %s/%s via GitHub API",
            ref,
            parsed_url.owner,
            parsed_url.repo,
        )
        commit_data = query_github_api_sync(api_url)
    except ImportError as exc:
        logger.debug("GitHub API client not available; cannot resolve %r: %s", api_url, exc)
        return None
    except Exception as exc:
        logger.warning(
            "Failed to resolve symbolic ref %r for %s/%s via API: %s",
            ref,
            parsed_url.owner,
            parsed_url.repo,
            exc,
        )
        return None

    if not isinstance(commit_data, dict):
        logger.warning(
            "Failed to resolve symbolic ref %r for %s/%s: unexpected response %r",
            ref,
            parsed_url.owner,
            parsed_url.repo,
            commit_data,
        )
        return None

    sha = commit_data.get("sha")
    if not sha:
        logger.warning(
            "Failed to resolve symbolic ref %r for %s/%s: No SHA in API response",
            ref,
            parsed_url.owner,
            parsed_url.repo,
        )
        return None

    normalized_sha = normalize_commit_id(str(sha))
    if not normalized_sha:
        logger.warning(
            "Failed to normalize resolved SHA %r for %s/%s",
            sha,
            parsed_url.owner,
            parsed_url.repo,
        )
        return None

    logger.info(
        "Resolved %r -> %s for %s/%s",
        ref,
        normalized_sha,
        parsed_url.owner,
        parsed_url.repo,
    )
    return normalized_sha


def _resolve_symbolic_ref(ref: str | None, git_url: str | None) -> str | None:
    """Resolve a symbolic git reference (branch/tag) to a commit SHA."""
    if not ref or not isinstance(ref, str) or not git_url:
        return None

    ref_str = ref.strip()
    if not ref_str:
        return None

    local_sha = _resolve_ref_local(ref_str, git_url)
    if local_sha:
        return local_sha

    return _resolve_ref_via_api(ref_str, git_url)


def normalize_or_resolve_commit(
    raw_commit_id: str | None,
    project_url: str | None,
) -> str | None:
    """Normalize commit ID, falling back to symbolic ref resolution if needed."""

    commit_id = normalize_commit_id(raw_commit_id)

    if commit_id and COMMIT_HASH_PATTERN.fullmatch(commit_id):
        return commit_id

    ref_to_resolve = commit_id or raw_commit_id
    resolved_commit_id = _resolve_symbolic_ref(ref_to_resolve, project_url)
    if resolved_commit_id:
        return resolved_commit_id

    logger.debug(
        "Failed to normalize or resolve commit_id=%s for project=%s",
        raw_commit_id,
        project_url,
    )
    return None


def extract_url_and_commit(
    row: dict[str, Any], url_field: str, commit_field: str, dataset_name: str = "dataset"
) -> tuple[str | None, str | None]:
    """Extract and validate project URL and commit ID from row."""
    # Extract and parse URL
    url = row.get(url_field)
    git_url = GitURL.parse(url) if url else None
    if not git_url:
        logger.debug(
            "[%s] Skipping row: failed to parse URL from %s=%s", dataset_name, url_field, url
        )
        return None, None

    project_url = git_url.to_https_url()
    if not project_url:
        logger.debug(
            "[%s] Skipping row: failed to convert to HTTPS URL from %s=%s",
            dataset_name,
            url_field,
            url,
        )
        return None, None

    # Extract and normalize commit ID
    raw_commit_id = row.get(commit_field)
    commit_id = normalize_or_resolve_commit(raw_commit_id, project_url)

    # Fallback: try extracting from URL if the explicit field is missing/invalid
    if not commit_id and git_url.commit_id:
        commit_id = normalize_or_resolve_commit(git_url.commit_id, project_url)

    if not commit_id:
        return None, None

    return project_url, commit_id


def extract_from_commit_url(
    row: dict[str, Any], url_field: str, dataset_name: str = "dataset"
) -> tuple[str | None, str | None]:
    """Extract project URL and raw commit ID from a combined commit URL field."""
    commit_url = row.get(url_field)
    if not commit_url or not isinstance(commit_url, str):
        logger.debug(
            "[%s] Skipping row: missing or invalid %s=%s", dataset_name, url_field, commit_url
        )
        return None, None

    git_url = GitURL.parse(commit_url)
    if not git_url:
        logger.debug(
            "[%s] Skipping row: failed to parse URL from %s=%s", dataset_name, url_field, commit_url
        )
        return None, None

    project_url = git_url.to_https_url()
    raw_commit_id = git_url.commit_id

    if not project_url or not raw_commit_id:
        logger.debug(
            "[%s] Skipping row: failed to extract project_url=%s or commit_id=%s from %s=%s",
            dataset_name,
            project_url,
            raw_commit_id,
            url_field,
            commit_url,
        )
        return None, None

    return project_url, raw_commit_id


def normalize_cve_ids(cve_input: object) -> set[str]:
    """Normalize CVE IDs to a set of validated uppercase strings."""
    if isinstance(cve_input, float) and math.isnan(cve_input):
        return set()

    match cve_input:
        case None | float():
            return set()
        case str() as s:
            cve_items: Iterable[str] = [s]
        case Iterable() as items:
            cve_items = items
        case _:
            return set()

    return {
        cve.strip().upper()
        for cve in cve_items
        if isinstance(cve, str) and cve != "NA" and CVE_PATTERN.fullmatch(cve.strip().upper())
    }


def normalize_cwe_ids(cwe_input: object) -> set[str]:
    """Normalize CWE IDs to a set of validated strings (CWE-1 to CWE-9999)."""
    if isinstance(cwe_input, float) and math.isnan(cwe_input):
        return set()

    match cwe_input:
        case None:
            return set()
        case float() | int() | str() as item:
            cwe_items: Iterable[str | int | float] = [item]
        case Iterable() as items:
            cwe_items = items
        case _:
            return set()

    normalized_cwe_ids: set[str] = set()
    for cwe in cwe_items:
        cwe_str = str(cwe).strip()
        if not cwe_str:
            continue

        cwe_upper = cwe_str.upper()
        if cwe_upper == "NA":
            continue

        # Extract numeric part (strip "CWE-" prefix if present)
        suffix = cwe_str[4:] if cwe_upper.startswith("CWE-") else cwe_str

        # Validate: must be 1-4 digits (CWE-1 to CWE-9999)
        if suffix.isdigit() and 1 <= len(suffix) <= 4:
            normalized_cwe_ids.add(f"CWE-{int(suffix)}")

    return normalized_cwe_ids
