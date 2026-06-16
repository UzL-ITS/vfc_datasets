import logging
from typing import Any, override

import pandas as pd

from vfc_datasets.base_dataset import BaseDataset, DatasetMetadata
from vfc_datasets.dataset_entry import DatasetEntry
from vfc_datasets.download_helper import download_file
from vfc_datasets.parsing_helpers import extract_and_normalize_from_commit_url

logger = logging.getLogger(__name__)

_BASE_URL = "https://raw.githubusercontent.com/security-pride/CommitShield/main/dataset/VFD"

# (filename, is_vfc, sha256) for the two label files shipped in the CommitShield repo.
_FILES: tuple[tuple[str, bool, str], ...] = (
    (
        "all_vul_fix.txt",
        True,
        "88ffca8d46e03d6f0f49db7dc0d5e42a752c00e517e2f1309e8c306f084ef340",
    ),
    (
        "all_non_vul_fix.txt",
        False,
        "be495cb6eabbc6246745be437e1994ad9057844459869de5a82a912c1feb58e2",
    ),
)


class CommitVulFixDataset(BaseDataset):
    metadata = DatasetMetadata(
        name="commitvulfix",
        granularity="commit",
        paper_title="CommitShield: Tracking Vulnerability Introduction and Fix in Version Control Systems",
        paper_url="https://doi.org/10.48550/arXiv.2501.03626",
        source_url="https://github.com/security-pride/CommitShield",
        publication_year=2025,
        programming_languages=("C", "C++"),
        paper_quotes=(
            # Section IV-A1 Dataset of VFD
            "This dataset comprises 681 C/C++ vulnerability fix commits and 1,118 C/C++ "
            "non-vulnerability fix commits.",
        ),
        vfcs=681,
        non_vfcs=1118,
        projects=233,
    )

    @override
    def _load_data(self) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        for filename, is_vfc, checksum in _FILES:
            path = download_file(
                f"{_BASE_URL}/{filename}", self._raw_dir / filename, checksum=checksum
            )
            with open(path) as f:
                for line in f:
                    url = line.strip()
                    if url:
                        rows.append({"commit_url": url, "is_vfc": is_vfc})

        return pd.DataFrame(rows)

    @override
    def _parse_row(self, row: dict[str, Any]) -> DatasetEntry | None:
        # The files are plain lists of ".../commit/<sha>" GitHub URLs with no
        # diffs, messages, or CVE IDs
        project_url, commit_id = extract_and_normalize_from_commit_url(
            row, "commit_url", self.metadata.name
        )
        if not project_url or not commit_id:
            return None

        return DatasetEntry(
            project_url=project_url,
            commit_id=commit_id,
            src_datasets={self.metadata.name},
            is_vfc=bool(row.get("is_vfc")),
        )
