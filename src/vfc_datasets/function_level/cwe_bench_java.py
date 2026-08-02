import logging
from typing import Any, override

import pandas as pd

from vfc_datasets.base_dataset import BaseDataset, DatasetMetadata
from vfc_datasets.config import RAW_DATA_PATH
from vfc_datasets.dataset_entry import DatasetEntry
from vfc_datasets.download_helper import download_file
from vfc_datasets.parsing_helpers import (
    extract_url_and_commit,
    normalize_cve_ids,
    normalize_cwe_ids,
)

logger = logging.getLogger(__name__)

_BASE_URL = "https://raw.githubusercontent.com/iris-sast/cwe-bench-java/master/data"


class CWEBenchJavaDataset(BaseDataset):
    metadata = DatasetMetadata(
        name="cwe_bench_java",
        granularity="function",
        paper_title="IRIS: LLM-Assisted Static Analysis for Detecting Security Vulnerabilities",
        paper_url="https://doi.org/10.48550/arXiv.2405.17238",
        source_url="https://github.com/iris-sast/cwe-bench-java",
        publication_year=2024,
        programming_languages=("Java",),
        paper_quotes=(
            # Abstract:
            "For evaluation, we curate a new dataset, CWE-Bench-Java, comprising 120 "
            "manually validated security vulnerabilities in real-world Java projects.",
        ),
        vfcs=179,
        non_vfcs=0,
        projects=88,
        vulnerable_functions=1119,
        benign_functions=0,
    )

    @override
    def _load_data(self) -> pd.DataFrame:
        dataset_dir = RAW_DATA_PATH / "cwe_bench_java"

        project_path = download_file(
            f"{_BASE_URL}/project_info.csv", dataset_dir / "project_info.csv"
        )
        fix_path = download_file(f"{_BASE_URL}/fix_info.csv", dataset_dir / "fix_info.csv")

        df_projects = pd.read_csv(project_path, usecols=["cve_id", "cwe_id", "advisory_id"])
        df_fixes = pd.read_csv(fix_path)

        # fix_info is the function-level spine; enrich each method with its CVE's CWE
        # and GHSA advisory. Join on cve_id (project_slug misses some fix_info CVEs).
        df = df_fixes.merge(df_projects, on="cve_id", how="left")

        # Every fix_info row carries the owning repo; build the canonical GitHub URL.
        df["project_url"] = (
            "https://github.com/"
            + df["github_username"].astype(str)
            + "/"
            + df["github_repository_name"].astype(str)
        )
        return df

    @override
    def _parse_row(self, row: dict[str, Any]) -> DatasetEntry | None:
        project_url, commit_id = extract_url_and_commit(
            row, "project_url", "commit", self.metadata.name
        )
        if not project_url or not commit_id:
            return None

        # Prefer the full method signature (disambiguates overloads); fall back to name.
        function_name = row.get("signature") or row.get("method")
        if not function_name:
            return None

        file_path = row.get("file")

        advisory_id = row.get("advisory_id")
        ghsa_id = (
            advisory_id
            if isinstance(advisory_id, str) and advisory_id.startswith("GHSA-")
            else None
        )

        return DatasetEntry(
            project_url=project_url,
            commit_id=commit_id,
            src_datasets={self.metadata.name},
            is_vfc=True,
            cve_ids=normalize_cve_ids(row.get("cve_id")),
            cwe_ids=normalize_cwe_ids(row.get("cwe_id")),
            ghsa_id=ghsa_id,
            function_name=function_name,
            files_changed={file_path} if file_path else set(),
        )
