"""Core DatasetEntry model for vulnerability-fixing commit data."""

import logging
import re
from dataclasses import dataclass, field, fields
from typing import Any, Self

from vfc_datasets.commit_data import CommitData
from vfc_datasets.utils.git.url import MIN_COMMIT_LENGTH, GitURL, normalize_commit_id
from vfc_datasets.utils.owasp import OwaspCategory, cwes_to_owasp
from vfc_datasets.utils.patterns import CVE_PATTERN, CWE_PATTERN

logger = logging.getLogger(__name__)


def _validate_ids(
    ids: set[str], pattern: re.Pattern[str], id_type: str, context: str
) -> set[str]:
    """Filter IDs by regex pattern, logging any invalid ones."""
    valid = {id_ for id_ in ids if pattern.fullmatch(id_)}
    if invalid := ids - valid:
        logger.warning("Invalid %s IDs dropped for %s: %s", id_type, context, invalid)
    return valid


@dataclass(slots=True)
class DatasetEntry:
    """One labelled commit (or function within one).

    Identity and labels live on the entry; everything known about the commit itself lives
    in `commit`. `function_file` is the file a `function_name` was found in, which is entry
    identity — distinct from `commit.files_changed`, the files the commit touched.
    """

    project_url: str
    commit_id: str
    src_datasets: set[str]
    is_vfc: bool = True
    cve_ids: set[str] = field(default_factory=set[str])
    cwe_ids: set[str] = field(default_factory=set[str])
    function_name: str | None = None
    function_file: str | None = None
    ghsa_id: str | None = None
    owasp_categories: set[OwaspCategory] | None = None
    commit: CommitData = field(default_factory=CommitData)

    def __post_init__(self) -> None:
        # Validate commit_id
        if not isinstance(self.commit_id, str) or not self.commit_id.strip():
            raise ValueError(f"commit_id must be a non-empty string, got: {self.commit_id!r}")
        if not (normalized_id := normalize_commit_id(self.commit_id)):
            raise ValueError(
                f"Invalid commit_id: {self.commit_id!r} "
                f"(must be {MIN_COMMIT_LENGTH}-40 hex characters)"
            )
        self.commit_id = normalized_id

        # Validate project_url
        if not (git_url := GitURL.parse(self.project_url)):
            raise ValueError(
                f"Invalid project URL: {self.project_url!r}. "
                "Supported platforms: GitHub, GitLab, Bitbucket, googlesource, "
                "Savannah, kernel.org, freedesktop.org, and generic git hosts."
            )
        if not (normalized_url := git_url.to_https_url()):
            raise ValueError(f"Failed to normalize project URL: {self.project_url}")
        self.project_url = normalized_url

        # Validate src_datasets
        if not self.src_datasets:
            raise ValueError("src_datasets must not be empty")

        # Validate CVE/CWE IDs
        location = f"{self.project_url}/commit/{self.commit_id}"
        self.cve_ids = _validate_ids(self.cve_ids, CVE_PATTERN, "CVE", location)
        self.cwe_ids = _validate_ids(self.cwe_ids, CWE_PATTERN, "CWE", location)

        # Derive OWASP categories from CWE if not explicitly provided
        if self.owasp_categories is None and self.cwe_ids:
            self.owasp_categories = cwes_to_owasp(self.cwe_ids)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        d: dict[str, Any] = {}
        for f in fields(self):
            value: Any = getattr(self, f.name)
            if isinstance(value, CommitData):
                value = value.to_dict()
            elif isinstance(value, set):
                value = sorted(value)
            d[f.name] = value
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Create a DatasetEntry from a serialized dict (e.g. loaded from JSON)."""
        set_fields = {"src_datasets", "cve_ids", "cwe_ids"}
        converted: dict[str, Any] = {
            k: set(v or []) if k in set_fields else v for k, v in data.items() if k != "commit"
        }
        if converted.get("owasp_categories") is not None:
            converted["owasp_categories"] = {
                OwaspCategory(v) for v in converted["owasp_categories"]
            }
        converted["commit"] = CommitData.from_dict(data.get("commit"))
        return cls(**converted)
