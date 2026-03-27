"""Core DatasetEntry model for vulnerability-fixing commit data."""

import logging
import re
from datetime import UTC, datetime
from typing import Any

from vfc_datasets.utils.git.url import MIN_COMMIT_LENGTH, GitURL, normalize_commit_id
from vfc_datasets.utils.owasp import OwaspCategory, cwes_to_owasp
from vfc_datasets.utils.patterns import CVE_PATTERN, CWE_PATTERN

logger = logging.getLogger(__name__)


class DatasetEntry:
    __hash__ = None  # pyright: ignore[reportAssignmentType]
    __slots__ = (
        "_commit_timestamp_utc",
        "commit_diff",
        "commit_id",
        "commit_message",
        "cve_ids",
        "cwe_ids",
        "files_changed",
        "function_name",
        "ghsa_id",
        "is_vfc",
        "owasp_categories",
        "project_url",
        "src_datasets",
    )

    @staticmethod
    def _validate_ids(
        ids: set[str] | None, pattern: re.Pattern[str], id_type: str, context: str = ""
    ) -> set[str]:
        """Filter IDs by regex pattern, logging any invalid ones."""
        if ids is None:
            return set()
        valid = {id_ for id_ in ids if pattern.fullmatch(id_)}
        if invalid := ids - valid:
            ctx = f" for {context}" if context else ""
            logger.warning("Invalid %s IDs dropped%s: %s", id_type, ctx, invalid)
        return valid

    def __init__(
        self,
        project_url: str,
        commit_id: str,
        src_datasets: set[str],
        *,
        is_vfc: bool = True,
        cve_ids: set[str] | None = None,
        cwe_ids: set[str] | None = None,
        function_name: str | None = None,
        ghsa_id: str | None = None,
        owasp_categories: set[OwaspCategory] | None = None,
        commit_message: str | None = None,
        commit_diff: str | None = None,
        files_changed: set[str] | None = None,
        commit_timestamp_utc: datetime | str | None = None,
    ) -> None:
        # Validate commit_id
        if not isinstance(commit_id, str) or not commit_id.strip():
            raise ValueError(f"commit_id must be a non-empty string, got: {commit_id!r}")
        if not (normalized_id := normalize_commit_id(commit_id)):
            raise ValueError(
                f"Invalid commit_id: {commit_id!r} (must be {MIN_COMMIT_LENGTH}-40 hex characters)"
            )
        self.commit_id = normalized_id

        # Validate project_url
        if not (git_url := GitURL.parse(project_url)):
            raise ValueError(
                f"Invalid project URL: {project_url!r}. "
                "Supported platforms: GitHub, GitLab, Bitbucket, googlesource, "
                "Savannah, kernel.org, freedesktop.org, and generic git hosts."
            )
        if not (normalized_url := git_url.to_https_url()):
            raise ValueError(f"Failed to normalize project URL: {project_url}")
        self.project_url = normalized_url

        # Validate src_datasets
        if not src_datasets:
            raise ValueError("src_datasets must not be empty")
        self.src_datasets = src_datasets

        # Simple assignments
        self.is_vfc = is_vfc
        self.commit_message = commit_message
        self.commit_diff = commit_diff
        self.files_changed = files_changed or set()
        self.function_name = function_name
        self.ghsa_id = ghsa_id
        self.commit_timestamp_utc = commit_timestamp_utc

        # Validate CVE/CWE IDs
        location = f"{self.project_url}/commit/{self.commit_id}"
        self.cve_ids = self._validate_ids(cve_ids, CVE_PATTERN, "CVE", location)
        self.cwe_ids = self._validate_ids(cwe_ids, CWE_PATTERN, "CWE", location)

        # Derive OWASP categories from CWE if not provided
        if owasp_categories is not None:
            self.owasp_categories: set[OwaspCategory] | None = owasp_categories
        elif self.cwe_ids:
            self.owasp_categories = cwes_to_owasp(self.cwe_ids)
        else:
            self.owasp_categories = None

    @property
    def commit_timestamp_utc(self) -> datetime | None:
        return self._commit_timestamp_utc

    @commit_timestamp_utc.setter
    def commit_timestamp_utc(self, value: datetime | str | None) -> None:
        if value is None:
            self._commit_timestamp_utc = None
        else:
            dt = datetime.fromisoformat(value) if isinstance(value, str) else value
            self._commit_timestamp_utc = (
                dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)
            )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        d = {}
        for slot in self.__slots__:
            # Expose _commit_timestamp_utc as commit_timestamp_utc
            key = "commit_timestamp_utc" if slot == "_commit_timestamp_utc" else slot
            value = getattr(self, slot, None)
            if isinstance(value, set):
                value = sorted(value, key=str)
            elif isinstance(value, datetime):
                value = value.isoformat().replace("+00:00", "Z")
            d[key] = value
        return d


def create_dataset_entry(data: dict[str, Any]) -> DatasetEntry:
    """Create DatasetEntry from dict, coercing serialized types to their runtime equivalents."""
    converted = {k: set(v) if isinstance(v, list) else v for k, v in data.items()}
    if converted.get("owasp_categories") is not None:
        converted["owasp_categories"] = {OwaspCategory(v) for v in converted["owasp_categories"]}
    return DatasetEntry(**converted)  # pyright: ignore[reportArgumentType]
