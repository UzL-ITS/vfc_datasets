import json
from typing import Any, override
from urllib.parse import quote

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

_BASE_URL = "https://raw.githubusercontent.com/ASE-REEF/REEF-data/main/data"
_FILES = {
    "query_C#.jsonl": "b7be901d3cc7f1a55f01e4dc4ae6248e178dd8aebea9a09f773bce455fc8dd32",
    "query_C++.jsonl": "e0be4bd3ee6369fcb59bd782bdd29b9e2979ed20b3259efd067bce5446136818",
    "query_C_part0.jsonl": "65d86820277f16eb5e1f3867751c808c9b621d347f2363066bbecd9503878c72",
    "query_C_part1.jsonl": "49f5f7685208bc1cb37401787a1c5b779d6697bde0e53ccb250c0ac235270c59",
    "query_C_part2.jsonl": "78adfb7123f40194127a5d137045da622b54efc2faf455a003cd967a29d1f80b",
    "query_C_part3.jsonl": "1b9e1f560fa5cfd26331e91a9496ec241551aec4db4f6e107c5f7c7700d07975",
    "query_Go.jsonl": "7e89f86c65b61dedf34a456d7237b696d846317361d0f960adce48569940e7eb",
    "query_JS.jsonl": "51fadc04bb35426782fe4573212f6493a0ce5b3c7867c95947ddf66ed05e9b28",
    "query_Java.jsonl": "c22353223229686b06531c6e67d0433976cdb3b7ba35a970911ff2cdff52929b",
    "query_Python.jsonl": "1aa69665d533c4cf75e527e98a4012f73ae1246737d76950af97e8ade57a395b",
}


class REEFDataset(BaseDataset):
    metadata = DatasetMetadata(
        name="reef",
        granularity="commit",
        paper_title="REEF: A Framework for Collecting Real-World Vulnerabilities and Fixes",
        paper_url="https://doi.org/10.48550/arXiv.2309.08115",
        source_url="https://github.com/ASE-REEF/REEF-data",
        publication_year=2023,
        programming_languages=("C", "C++", "C#", "Go", "Java", "JavaScript", "Python"),
        paper_quotes=(
            # Abstract
            "The dataset we collect contains 4,466 CVEs with 30,987 patches (including 236 "
            "CWE) across 7 programming languages with detailed related information, which is "
            "superior to existing benchmarks in scale, coverage, and quality.",
        ),
    )

    parsed_counts = DatasetCounts(
        vfcs=4466,
        non_vfcs=0,
        projects=1686,
    )

    @override
    def _load_data(self) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        for name, checksum in _FILES.items():
            path = download_file(
                f"{_BASE_URL}/{quote(name)}", RAW_DATA_PATH / "reef" / name, checksum=checksum
            )
            with open(path) as f:
                for line in f:
                    record = json.loads(line)
                    rows.append(
                        {
                            "commit_url": record.get("html_url"),
                            "cve_id": record.get("cve_id"),
                            "cwe_ids": record.get("CWEs"),
                        }
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
            cwe_ids=normalize_cwe_ids(row.get("cwe_ids")),
        )
