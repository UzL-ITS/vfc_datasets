import json
import re
from abc import ABC
from pathlib import Path
from typing import Any, override

import pandas as pd

from vfc_datasets.base_dataset import BaseDataset, DatasetCounts, DatasetMetadata
from vfc_datasets.config import RAW_DATA_PATH
from vfc_datasets.dataset_entry import DatasetEntry
from vfc_datasets.download_helper import download_and_extract_zip
from vfc_datasets.parsing_helpers import extract_and_normalize_from_commit_url, normalize_cve_ids

_DOWNLOAD_URL = "https://zenodo.org/records/21410721/files/artifact.zip?download=1"
_SHA256 = "c9adb1ea29783ed4e5e1a4c3fe3d0ccfec26485d822f48228f2c5516cb88623b"
_SP_DB = "artifact/data/rq1/ase2026_multi_patches_05to26.json"
_GROUND_TRUTH = "artifact/data/rq3/gt_verified_719.csv"
_PAPER_TITLE = (
    "One Is Not Enough: The Untold Story of Multiple Security Patches for One Vulnerability"
)
_PAPER_URL = "https://doi.org/10.48550/arXiv.2609.07224"
_SOURCE_URL = "https://doi.org/10.5281/zenodo.21410721"
_PULL_REQUEST_COMMIT = re.compile(r"/pull/\d+/commits/(?=[0-9a-f]{7,40}\b)")


class _MultiSPBase(BaseDataset, ABC):
    def _extract(self, member: str) -> Path:
        extract_dir = RAW_DATA_PATH / "multi_sp"
        download_and_extract_zip(
            _DOWNLOAD_URL, extract_dir, files_to_extract=[_SP_DB, _GROUND_TRUTH], checksum=_SHA256
        )
        return extract_dir / member

    @override
    def _parse_row(self, row: dict[str, Any]) -> DatasetEntry | None:
        project_url, commit_id = extract_and_normalize_from_commit_url(
            row, "commit_url", self.metadata.name
        )
        if not project_url or not commit_id:
            return None

        return DatasetEntry(
            project_url=project_url,
            commit_id=commit_id,
            src_datasets={self.metadata.name},
            is_vfc=True,
            cve_ids=normalize_cve_ids(row.get("cve_id")),
        )


class MultiSPDataset(_MultiSPBase):
    metadata = DatasetMetadata(
        name="multi_sp",
        granularity="commit",
        paper_title=_PAPER_TITLE,
        paper_url=_PAPER_URL,
        source_url=_SOURCE_URL,
        publication_year=2026,
        paper_quotes=(
            # Abstract
            "By merging four major vulnerability databases, we construct a dataset of 6,053 "
            "multi-SP CVEs with 16,260 SPs, showing that 20.6% of CVEs with patches involve "
            "multiple SPs and that merging databases increases recognized multi-SP CVE counts "
            "by 36-55% over any single source.",
        ),
    )

    parsed_counts = DatasetCounts(
        vfcs=16253,
        non_vfcs=0,
        projects=2696,
    )

    @override
    def _load_data(self) -> pd.DataFrame:
        records = json.loads(self._extract(_SP_DB).read_text())
        return pd.DataFrame(
            [
                {
                    "commit_url": _PULL_REQUEST_COMMIT.sub("/commit/", url),
                    "cve_id": record.get("cve_id"),
                }
                for record in records
                for url in record.get("total_patches") or []
            ]
        )


class MultiSPVerifiedDataset(_MultiSPBase):
    metadata = DatasetMetadata(
        name="multi_sp_verified",
        granularity="commit",
        paper_title=_PAPER_TITLE,
        paper_url=_PAPER_URL,
        source_url=_SOURCE_URL,
        publication_year=2026,
        paper_quotes=(
            # Section 4.3.2 (Effectiveness Evaluation of SPectre)
            "Two authors independently reviewed the candidates (Cohen's K = 0.945), with "
            "disagreements resolved by a third author, yielding 719 ground-truth SPs for 300 CVEs",
        ),
    )

    parsed_counts = DatasetCounts(
        vfcs=719,
        non_vfcs=0,
        projects=189,
    )

    @override
    def _load_data(self) -> pd.DataFrame:
        df = pd.read_csv(self._extract(_GROUND_TRUTH), dtype=str)
        df["commit_url"] = "https://github.com/" + df["repo"] + "/commit/" + df["commit"]
        return df
