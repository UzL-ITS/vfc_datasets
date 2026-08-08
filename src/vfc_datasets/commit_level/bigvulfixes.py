import logging
from typing import Any, override

import pandas as pd

from vfc_datasets.base_dataset import BaseDataset, DatasetMetadata
from vfc_datasets.commit_data import CommitData, normalize_commit_timestamp
from vfc_datasets.config import RAW_DATA_PATH
from vfc_datasets.dataset_entry import DatasetEntry
from vfc_datasets.download_helper import download_file
from vfc_datasets.parsing_helpers import extract_url_and_commit, normalize_cve_ids

logger = logging.getLogger(__name__)

# Single Parquet from the LLM4VFD replication package on Zenodo (record 13776994).
_DOWNLOAD_URL = (
    "https://zenodo.org/records/13776994/files/20240913_bigvulfix_dataset.parquet?download=1"
)
_SHA256 = "4c5ed1a5b0b85c78050983749773c7534f14035ca299c452968a12f5c0ce26f7"


class BigVulFixesDataset(BaseDataset):
    metadata = DatasetMetadata(
        name="bigvulfixes",
        granularity="commit",
        paper_title=(
            "Code Change Intention, Development Artifact and History Vulnerability: "
            "Putting Them Together for Vulnerability Fix Detection by LLM"
        ),
        paper_url="https://doi.org/10.48550/arXiv.2501.14983",
        source_url="https://doi.org/10.5281/zenodo.13776994",
        publication_year=2025,
        programming_languages=("Java", "C", "C++", "Rust", "JavaScript", "Python", "Go"),
        paper_quotes=(
            # Section 4 (Experiment Setup - Dataset). The paper reports a sampled subset;
            # the published Zenodo parquet ships 1,745 VF / 27,211 NVF commits (the actuals below).
            "Our final evaluation dataset BigVulFixes consists of 1,689 VF and 26,468 NVF "
            "commits, reflecting this sampled ratio.",
            # Section 5.2.2 (Vulnerability and Non-vulnerability Fix Commit Selection)
            "we limit ourselves to vulnerabilities from 7 programming languages, namely "
            "Java, C, C++, Rust, JavaScript, Python, and Go.",
        ),
        vfcs=1745,
        non_vfcs=27211,
        projects=713,
    )

    @override
    def _load_data(self) -> pd.DataFrame:
        path = download_file(_DOWNLOAD_URL, RAW_DATA_PATH / "bigvulfixes.parquet", checksum=_SHA256)
        return pd.read_parquet(path)

    @override
    def _parse_row(self, row: dict[str, Any]) -> DatasetEntry | None:
        # repo_url is a bare GitHub "owner/repo"; build a full URL for parsing.
        repo = row.get("repo_url")
        if not isinstance(repo, str) or not repo.strip():
            return None
        row["project_url"] = f"https://github.com/{repo.strip()}"

        project_url, commit_id = extract_url_and_commit(
            row, "project_url", "commit_id", self.metadata.name
        )
        if not project_url or not commit_id:
            return None

        # vuln_id holds a CVE for fix commits and is null for non-fix commits.
        return DatasetEntry(
            project_url=project_url,
            commit_id=commit_id,
            src_datasets={self.metadata.name},
            is_vfc=row.get("label") == 1,
            cve_ids=normalize_cve_ids(row.get("vuln_id")),
        )

    @override
    def _shipped_commit_data(self, row: dict[str, Any]) -> CommitData:
        # FIXME: `patch` is a format-patch mbox, not a plain diff, so it needs parsing before
        # it means the same thing as every other diff. `patch_date_dt` is off by >90s from
        # both real dates for ~12% of rows.
        return CommitData(
            diff=row.get("patch"),
            authored_at=normalize_commit_timestamp(row.get("patch_date_dt")),
        )
