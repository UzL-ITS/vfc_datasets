import json
from typing import Any, override

import pandas as pd

from vfc_datasets.base_dataset import BaseDataset, DatasetCounts, DatasetMetadata
from vfc_datasets.config import RAW_DATA_PATH
from vfc_datasets.dataset_entry import DatasetEntry
from vfc_datasets.download_helper import download_file
from vfc_datasets.parsing_helpers import (
    extract_and_normalize_from_commit_url,
    normalize_cve_ids,
    normalize_cwe_ids,
)

# Complete ReposVul.jsonl (all four languages, ~2.4 GB)
_DOWNLOAD_URL = "https://drive.google.com/uc?id=1szQ9FnIC_onQRu_TjZ2uofkjv9z_s4pv"
_SHA256 = "e3074e185b9d84ec0c2f372c42e02ae7d2f652e9e20a88e1af141caef57b2a03"


class ReposVulDataset(BaseDataset):
    metadata = DatasetMetadata(
        name="reposvul",
        granularity="commit",
        paper_title="ReposVul: A Repository-Level High-Quality Vulnerability Dataset",
        paper_url="https://doi.org/10.48550/arXiv.2401.13169",
        source_url="https://github.com/Eshe0922/ReposVul",
        publication_year=2024,
        programming_languages=("C", "C++", "Java", "Python"),
        paper_quotes=(
            # Abstract
            "The constructed repository-level ReposVul encompasses 6,134 CVE entries representing "
            "236 CWE types across 1,491 projects and four programming languages.",
            "Outdated Patches: The existing datasets usually contain outdated patches, which may "
            "bias the model during training.",
        ),
    )

    parsed_counts = DatasetCounts(
        vfcs=6000,  # excluding the entries marked as "outdated"
        non_vfcs=0,
        projects=1494,
    )

    @override
    def _load_data(self) -> pd.DataFrame:
        jsonl_path = download_file(
            _DOWNLOAD_URL, RAW_DATA_PATH / "reposvul.jsonl", checksum=_SHA256
        )

        rows: list[dict[str, Any]] = []
        with open(jsonl_path) as f:
            for line in f:
                record = json.loads(line)
                rows.append(
                    {
                        "commit_url": record.get("html_url"),
                        "cve_id": record.get("cve_id"),
                        "cwe_ids": record.get("cwe_id"),
                        "outdated": record.get("outdated"),
                    }
                )
        return pd.DataFrame(rows)

    @override
    def _parse_row(self, row: dict[str, Any]) -> DatasetEntry | None:
        if row.get("outdated"):
            return None

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
            cwe_ids=normalize_cwe_ids(row.get("cwe_ids")),
        )
