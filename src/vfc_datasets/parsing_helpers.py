import logging
from collections.abc import Iterable
from typing import Any

from vfc_datasets.utils.git.url import GitURL, normalize_commit_id
from vfc_datasets.utils.patterns import CVE_PATTERN

logger = logging.getLogger(__name__)

__all__ = [
    "extract_and_normalize_from_commit_url",
    "extract_from_commit_url",
    "extract_url_and_commit",
    "lookup_broken_commit",
    "normalize_commit_id",
    "normalize_cve_ids",
    "normalize_cwe_ids",
    "pinned_commit",
]

# Irregular refs (tags/rev-expressions) pinned to canonical SHAs, resolved once, so
# parsing stays deterministic and offline. Tags are immutable, so these don't drift.
KNOWN_BROKEN_COMMITS: dict[str, dict[str, str]] = {
    "https://github.com/curl/curl": {
        "curl-7_51_0-162-g3ab3c16": "3ab3c16db6a5674f53cf23d5654366663f734493",
        "curl-7_50_2~32": "7700fcba64bf5806de28f6c1c7da3b4f0b38567d",
    },
    "https://github.com/imagemagick/imagemagick": {
        "7.0.2-1": "01588fbdd5469847e919b472e8bfbd69bef0d652",
        "7.0.1-5": "580b68fc398b9bf7ec1a025524f294ce76fcf521",
    },
    "https://github.com/dom4j/dom4j": {
        "version-2.0.3": "177069f0e96a40ddab5ab7f41519ec29e5a39652",
    },
}


def lookup_broken_commit(text: str) -> tuple[str, str] | None:
    """Check if text contains a known broken commit ref. Returns (project_url, full_hash) or None."""
    for url, fixes in KNOWN_BROKEN_COMMITS.items():
        for broken_ref, full_hash in fixes.items():
            if broken_ref in text:
                return url, full_hash
    return None


def pinned_commit(project_url: str | None, ref: object) -> str | None:
    """Return the pinned SHA for an irregular (project_url, ref), if one is recorded."""
    if not project_url or not isinstance(ref, str):
        return None
    return KNOWN_BROKEN_COMMITS.get(project_url, {}).get(ref.strip())


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
    commit_id = normalize_commit_id(raw_commit_id) or pinned_commit(project_url, raw_commit_id)

    # Fallback: try extracting from URL if the explicit field is missing/invalid
    if not commit_id and git_url.commit_id:
        commit_id = normalize_commit_id(git_url.commit_id) or pinned_commit(project_url, git_url.commit_id)

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


def extract_and_normalize_from_commit_url(
    row: dict[str, Any], url_field: str, dataset_name: str = "dataset"
) -> tuple[str | None, str | None]:
    """Extract project URL and normalized commit ID from a combined commit URL field."""
    project_url, raw_commit_id = extract_from_commit_url(row, url_field, dataset_name)
    if not project_url or not raw_commit_id:
        return None, None
    commit_id = normalize_commit_id(raw_commit_id) or pinned_commit(project_url, raw_commit_id)
    return project_url, commit_id


def normalize_cve_ids(cve_input: object) -> set[str]:
    """Normalize CVE IDs to a set of validated uppercase strings."""
    match cve_input:
        case None | float():
            return set()
        case str() as s:
            cve_items: Iterable[object] = [s]
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
    match cwe_input:
        case None | float():
            return set()
        case int() | str() as item:
            cwe_items: Iterable[object] = [item]
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
