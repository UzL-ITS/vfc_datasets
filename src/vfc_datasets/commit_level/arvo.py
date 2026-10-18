import sqlite3
from typing import Any, override

import pandas as pd

from vfc_datasets.base_dataset import BaseDataset, DatasetCounts, DatasetMetadata
from vfc_datasets.config import RAW_DATA_PATH
from vfc_datasets.dataset_entry import DatasetEntry
from vfc_datasets.download_helper import download_file
from vfc_datasets.parsing_helpers import extract_url_and_commit

_DOWNLOAD_URL = "https://github.com/n132/ARVO-Meta/releases/download/v3.0.0/arvo.db"
_SHA256 = "331184ca807c2f136f98dac9f1df94c893f4ee2fdf9329dca517ff88e72f97ce"


class ARVODataset(BaseDataset):
    metadata = DatasetMetadata(
        name="arvo",
        granularity="commit",
        paper_title="ARVO: Atlas of Reproducible Vulnerabilities for Open-Source Software",
        paper_url="https://doi.org/10.48550/arXiv.2408.02153",
        source_url="https://github.com/n132/ARVO-Meta",
        publication_year=2026,
        programming_languages=("C", "C++"),
        paper_quotes=(
            # Abstract (v2)
            "ARVO is a large-scale dataset consisting of over 6,100 real-world "
            "vulnerabilities across 311 projects.",
        ),
    )

    parsed_counts = DatasetCounts(
        vfcs=5742,
        non_vfcs=0,
        projects=310,
    )

    @override
    def _load_data(self) -> pd.DataFrame:
        path = download_file(_DOWNLOAD_URL, RAW_DATA_PATH / "arvo" / "arvo.db", checksum=_SHA256)
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
            return pd.read_sql_query("SELECT localId, repo_addr, fix_commit FROM arvo", connection)

    @override
    def _parse_row(self, row: dict[str, Any]) -> DatasetEntry | None:
        # 394 issues narrow the fix only to a range of commits
        if "\n" in (row.get("fix_commit") or "").strip():
            return None
        # 2 issues name an SVN repository, whose fix is a revision number, not a git commit
        if "://svn." in (row.get("repo_addr") or ""):
            return None

        project_url, commit_id = extract_url_and_commit(
            row, "repo_addr", "fix_commit", self.metadata.name
        )
        if not project_url or not commit_id:
            return None

        return DatasetEntry(
            project_url=project_url,
            commit_id=commit_id,
            src_datasets={self.metadata.name},
            is_vfc=True,
        )
