import json
import logging
from typing import Any, override

import pandas as pd

from vfc_datasets.base_dataset import BaseDataset, DatasetMetadata
from vfc_datasets.config import RAW_DATA_PATH
from vfc_datasets.dataset_entry import DatasetEntry
from vfc_datasets.download_helper import download_file
from vfc_datasets.parsing_helpers import (
    extract_and_normalize_from_commit_url,
    normalize_cve_ids,
    normalize_cwe_ids,
)

logger = logging.getLogger(__name__)

_DOWNLOAD_URL = (
    "https://raw.githubusercontent.com/bytedance/PatchEval/main/patcheval/datasets/patcheval_dataset.json"
)
_SHA256 = "50a57e837d9b6141178dd6d0271ba696abb5021b6c79799c70f8059f6ee3b50d"


class PatchEvalDataset(BaseDataset):
    metadata = DatasetMetadata(
        name="patcheval",
        granularity="commit",
        paper_title=(
            "PATCHEVAL: A New Benchmark for Evaluating LLMs on Patching Real-World Vulnerabilities"
        ),
        paper_url="https://doi.org/10.48550/arXiv.2511.11019",
        source_url="https://github.com/bytedance/PatchEval",
        publication_year=2025,
        programming_languages=("Go", "JavaScript", "Python"),
        paper_quotes=(
            # Abstract
            "we introduce PATCHEVAL, a multilingual benchmark for Go, JavaScript, and Python, "
            "languages for which existing benchmarks remain unexplored. PATCHEVAL curates a "
            "dataset of 1,000 vulnerabilities drawn from CVEs reported between 2015 and 2025, "
            "covering 65 distinct CWEs.",
        ),
        vfcs=1173,
        non_vfcs=0,
        projects=694,
    )

    @override
    def _load_data(self) -> pd.DataFrame:
        path = download_file(_DOWNLOAD_URL, RAW_DATA_PATH / "patcheval.json", checksum=_SHA256)
        with open(path) as f:
            records = json.load(f)

        rows: list[dict[str, Any]] = []
        for record in records:
            cwe_ids = list((record.get("cwe_info") or {}).keys())
            for commit_url in record.get("patch_url") or []:
                rows.append(
                    {
                        "commit_url": commit_url,
                        "cve_id": record.get("cve_id"),
                        "cwe_ids": cwe_ids,
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
