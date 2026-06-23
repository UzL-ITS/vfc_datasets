import logging
from typing import Any, override

import pandas as pd

from datasets import load_dataset
from vfc_datasets.base_dataset import BaseDataset, DatasetMetadata
from vfc_datasets.dataset_entry import DatasetEntry
from vfc_datasets.parsing_helpers import (
    extract_url_and_commit,
    normalize_cve_ids,
    normalize_cwe_ids,
)

logger = logging.getLogger(__name__)


class SecVulEvalDataset(BaseDataset):
    """SecVulEval function-level C/C++ dataset (with non-vulnerable functions)."""

    metadata = DatasetMetadata(
        name="secvuleval",
        granularity="function",
        paper_title="SecVulEval: Benchmarking LLMs for Real-World C/C++ Vulnerability Detection",
        paper_url="https://doi.org/10.48550/arXiv.2505.19828",
        source_url="https://huggingface.co/datasets/arag0rn/SecVulEval",
        publication_year=2025,
        programming_languages=("C", "C++"),
        paper_quotes=(
            # Abstract / Section 1
            "SecVulEval (...) comprises 25,440 function samples (5,867 CVEs) with "
            "10,998 vulnerable and 14,442 non-vulnerable functions from 1999 to 2024.",
        ),
        vfcs=4637,
        non_vfcs=0,
        projects=736,
        vulnerable_functions=10992,
        benign_functions=14435,
    )

    @override
    def _load_data(self) -> pd.DataFrame:
        return load_dataset("arag0rn/SecVulEval", split="train").to_pandas()  # pyright: ignore[reportReturnType]

    @override
    def _parse_row(self, row: dict[str, Any]) -> DatasetEntry | None:
        project_url, commit_id = extract_url_and_commit(
            row, "project_url", "commit_id", self.metadata.name
        )
        if not project_url or not commit_id:
            return None

        function_name = row.get("func_name")
        if not function_name:
            return None

        file_path = row.get("filepath")

        return DatasetEntry(
            project_url=project_url,
            commit_id=commit_id,
            src_datasets={self.metadata.name},
            is_vfc=bool(row.get("is_vulnerable")),
            cve_ids=normalize_cve_ids(row.get("cve_list")),
            cwe_ids=normalize_cwe_ids(row.get("cwe_list")),
            function_name=function_name,
            files_changed={file_path} if file_path else set(),
            commit_message=row.get("commit_message"),
        )
