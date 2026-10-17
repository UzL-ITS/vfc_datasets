import json
from typing import Any, override

import pandas as pd

from vfc_datasets.base_dataset import BaseDataset, DatasetCounts, DatasetMetadata
from vfc_datasets.config import RAW_DATA_PATH
from vfc_datasets.dataset_entry import DatasetEntry
from vfc_datasets.download_helper import download_file
from vfc_datasets.parsing_helpers import extract_and_normalize_from_commit_url, normalize_cve_ids

_REVISION = "45b5c5ddaae6c2bf8a55314e7d8e773f9558f748"
_DOWNLOAD_URL = (
    f"https://huggingface.co/datasets/XSec-Lab/MultiPatch/resolve/{_REVISION}/MultiPatch.jsonl"
)
_SHA256 = "269f147932b358a6765f3971cdf6ef7b35a72db21c5c9671e931e8533765aceb"


class MultiPatchDataset(BaseDataset):
    metadata = DatasetMetadata(
        name="multipatch",
        granularity="commit",
        paper_title=(
            "Why Not Fix It Once and for All? An Empirical Study of Multiple Patches for "
            "Vulnerability Fixes in Open-Source Software"
        ),
        paper_url="https://doi.org/10.48550/arXiv.2607.13206",
        source_url="https://huggingface.co/datasets/XSec-Lab/MultiPatch",
        publication_year=2026,
        paper_quotes=(
            # Abstract
            "Through a manual examination of 1,646 multi-patch fix records, we develop a "
            "taxonomy with three primary categories and six subcategories based on their causes.",
        ),
    )

    parsed_counts = DatasetCounts(
        vfcs=4045,
        non_vfcs=0,
        projects=823,
    )

    @override
    def _load_data(self) -> pd.DataFrame:
        path = download_file(_DOWNLOAD_URL, RAW_DATA_PATH / "multipatch.jsonl", checksum=_SHA256)

        rows: list[dict[str, Any]] = []
        with open(path) as f:
            for line in f:
                record = json.loads(line)
                for patch in record.get("patches") or []:
                    rows.append(
                        {"commit_url": patch.get("commit url"), "cve_id": record.get("CVE_ID")}
                    )
        return pd.DataFrame(rows)

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
