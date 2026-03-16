import hashlib
import logging
from typing import Any

import pandas as pd

from dataset_entry import DatasetEntry
from datasets import load_dataset  # type: ignore[attr-defined]
from vfc_datasets.base_dataset import BaseDataset, DatasetMetadata
from vfc_datasets.parsing_helpers import (
    extract_and_normalize_from_commit_url,
    normalize_cve_ids,
    normalize_cwe_ids,
)

logger = logging.getLogger(__name__)


class CleanVulDataset(BaseDataset):
    """CleanVul function-level dataset (Threshold 3 subset)."""

    metadata = DatasetMetadata(
        name="cleanvul",
        granularity="function",
        paper_title="CleanVul: Automatic Function-Level Vulnerability Detection in Code Commits Using LLM Heuristics",
        paper_url="https://doi.org/10.48550/arXiv.2411.17274",
        source_url="https://huggingface.co/datasets/yikun-li/CleanVul",
        publication_year=2024,
        programming_languages=("C", "C++", "C#", "Java", "JavaScript", "Python"),
        paper_quotes=(
            "We developed CleanVul, a high-quality dataset comprising 8,198 functions using our LLM heuristic enhancement approach (...)",
            "Increasing the threshold to 4 results in 6,368 vulnerability-fixing changes (...)",
        ),
        vfcs=4500,
        non_vfcs=0,
        vulnerable_functions=8198,
        benign_functions=0,
    )

    def _load_data(self) -> pd.DataFrame:
        ds = load_dataset("yikun-li/CleanVul")
        df = ds["train"].to_pandas()
        # Filter for Threshold 3
        return df[df["vulnerability_score"] >= 3].copy()

    def _parse_row(self, row: dict[str, Any]) -> DatasetEntry | None:
        project_url, commit_id = extract_and_normalize_from_commit_url(
            row, "commit_url", self.metadata.name
        )
        if not project_url or not commit_id:
            return None

        function_after = row.get("func_after")
        if not function_after:
            return None
        # TODO: Use function name instead of hash.
        function_name = hashlib.md5(function_after.encode()).hexdigest()

        file_name = row.get("file_name")

        return DatasetEntry(
            project_url=project_url,
            commit_id=commit_id,
            src_datasets={self.metadata.name},
            function_name=function_name,
            is_vfc=True,
            files_changed={file_name} if file_name else set(),
            cve_ids=normalize_cve_ids(row.get("cve_id")),
            cwe_ids=normalize_cwe_ids(row.get("cwe_id")),
            commit_message=row.get("commit_msg"),
        )
