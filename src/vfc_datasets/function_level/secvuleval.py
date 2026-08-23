import logging
import re
from typing import Any, override

import pandas as pd

from datasets import load_dataset
from vfc_datasets.base_dataset import BaseDataset, DatasetMetadata
from vfc_datasets.commit_data import CommitData, same_commit
from vfc_datasets.dataset_entry import DatasetEntry
from vfc_datasets.parsing_helpers import (
    extract_url_and_commit,
    normalize_cve_ids,
    normalize_cwe_ids,
)

logger = logging.getLogger(__name__)

# The three forms a backport's message takes to name the commit it was taken from.
_DERIVED_FROM = re.compile(
    r"^commit ([0-9a-f]{7,40}) upstream\.?\s*$"
    r"|\[\s*Upstream commit ([0-9a-f]{7,40})\s*\]"
    r"|\(cherry picked from commit ([0-9a-f]{7,40})\)",
    re.MULTILINE | re.IGNORECASE,
)


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
            function_file=file_path,
        )

    @override
    def _shipped_commit_data(self, row: dict[str, Any]) -> CommitData:
        message = row.get("commit_message")
        if not isinstance(message, str) or self._is_backport_of(message, row.get("commit_id")):
            return CommitData()
        return CommitData(message=message)

    @staticmethod
    def _is_backport_of(message: str, commit_id: object) -> bool:
        """Whether the message is a backport's, naming `commit_id` itself as its source.

        No commit's own message can say it was taken from itself, so such a row holds the
        original commit paired with the backport's text. 40 rows across the three idioms.
        """
        if not isinstance(commit_id, str):
            return False
        return any(
            same_commit(sha, commit_id)
            for found in _DERIVED_FROM.finditer(message)
            for sha in found.groups()
            if sha
        )
