import logging
from typing import Any, override

import pandas as pd

from vfc_datasets.base_dataset import BaseDataset, DatasetCounts, DatasetMetadata
from vfc_datasets.config import RAW_DATA_PATH
from vfc_datasets.dataset_entry import DatasetEntry
from vfc_datasets.download_helper import download_file
from vfc_datasets.parsing_helpers import normalize_commit_id, normalize_cve_ids

logger = logging.getLogger(__name__)

_DOWNLOAD_URL = (
    "https://raw.githubusercontent.com/MarkLee131/PatchFinder/main/data/patch_data_4870.csv"
)
_SHA256 = "58898944be1e45bcd20d1b1bb4e6d6b92a8298d34fad140f6189e89c8d097eb3"


class PatchFinderDataset(BaseDataset):
    metadata = DatasetMetadata(
        name="patchfinder",
        granularity="commit",
        paper_title=(
            "PatchFinder: A Two-Phase Approach to Security Patch Tracing for "
            "Disclosed Vulnerabilities in Open-Source Software"
        ),
        paper_url="https://doi.org/10.48550/arXiv.2407.17065",
        source_url="https://github.com/MarkLee131/PatchFinder",
        publication_year=2024,
        paper_quotes=(
            # Abstract
            "We evaluated our system against 4,789 CVEs from 532 OSS projects.",
        ),
    )

    parsed_counts = DatasetCounts(
        vfcs=4870,
        non_vfcs=0,
        projects=530,
    )

    @override
    def _load_data(self) -> pd.DataFrame:
        csv_path = download_file(_DOWNLOAD_URL, RAW_DATA_PATH / "patchfinder.csv", checksum=_SHA256)
        return pd.read_csv(csv_path)

    @override
    def _parse_row(self, row: dict[str, Any]) -> DatasetEntry | None:
        owner = row.get("owner")
        repo = row.get("repo")
        commit_id = normalize_commit_id(row.get("commit_id"))

        if not owner or not repo or not commit_id:
            logger.debug(
                "[%s] Skipping row: owner=%s repo=%s commit_id=%s",
                self.metadata.name,
                owner,
                repo,
                row.get("commit_id"),
            )
            return None

        return DatasetEntry(
            project_url=f"https://github.com/{owner}/{repo}",
            commit_id=commit_id,
            src_datasets={self.metadata.name},
            is_vfc=True,
            cve_ids=normalize_cve_ids(row.get("cve")),
        )
