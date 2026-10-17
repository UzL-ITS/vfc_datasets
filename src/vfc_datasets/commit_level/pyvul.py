import json
from typing import Any, override

import pandas as pd

from vfc_datasets.base_dataset import BaseDataset, DatasetCounts, DatasetMetadata
from vfc_datasets.config import RAW_DATA_PATH
from vfc_datasets.dataset_entry import DatasetEntry
from vfc_datasets.download_helper import download_file
from vfc_datasets.parsing_helpers import extract_and_normalize_from_commit_url, normalize_cwe_ids

_BASE_URL = "https://raw.githubusercontent.com/billquan/PyVul/main/dataset"
_COMMITS = (
    "commit_level_dataset.out",
    "796981ada2ba1e86b8f4a3806f3d52f4be3df9b32ee55fa6c4e6ff93ab3dcebc",
)
_CWE_MAP = (
    "commits_cwe_map.json",
    "316f87c8f4929398500167aca38c3375bcaae5ef6cb28e56af4a46d96169c1ce",
)


class PyVulDataset(BaseDataset):
    """PyVul's commit-level benchmark: one fix-commit URL per line, CWEs in a side map."""

    metadata = DatasetMetadata(
        name="pyvul",
        granularity="commit",
        paper_title="An Empirical Study of Vulnerabilities in Python Packages and Their Detection",
        paper_url="https://doi.org/10.48550/arXiv.2509.04260",
        source_url="https://github.com/billquan/PyVul",
        publication_year=2025,
        programming_languages=("Python",),
        paper_quotes=(
            # Abstract
            "PyVul includes 1,157 publicly reported, developer-verified vulnerabilities, each "
            "linked to its affected packages.",
        ),
    )

    parsed_counts = DatasetCounts(
        vfcs=1155,
        non_vfcs=0,
        projects=348,
    )

    @override
    def _load_data(self) -> pd.DataFrame:
        paths = {
            name: download_file(
                f"{_BASE_URL}/{name}", RAW_DATA_PATH / "pyvul" / name, checksum=checksum
            )
            for name, checksum in (_COMMITS, _CWE_MAP)
        }
        cwe_by_url: dict[str, str] = json.loads(paths[_CWE_MAP[0]].read_text())

        with open(paths[_COMMITS[0]]) as f:
            urls = [line.strip() for line in f if line.strip()]
        return pd.DataFrame([{"commit_url": url, "cwe_id": cwe_by_url.get(url)} for url in urls])

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
            cwe_ids=normalize_cwe_ids(row.get("cwe_id")),
        )
