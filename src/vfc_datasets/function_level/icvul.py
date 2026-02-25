import logging
from typing import Any

import pandas as pd

from dataset_entry import DatasetEntry
from vfc_datasets.base_dataset import BaseDataset, DatasetMetadata
from vfc_datasets.download_helper import download_and_extract_zip
from vfc_datasets.parsing_helpers import (
    extract_url_and_commit,
    normalize_cve_ids,
    normalize_cwe_ids,
)

logger = logging.getLogger(__name__)


class ICVulDataset(BaseDataset):
    metadata = DatasetMetadata(
        name="icvul",
        granularity="function",
        paper_title="ICVul: A Well-labeled C/C++ Vulnerability Dataset with Comprehensive Metadata and VCCs",
        paper_url="https://doi.org/10.48550/arXiv.2505.08503",
        download_url="https://github.com/Chaomeng-Lu/ICVul",
        publication_year=2025,
        programming_languages=("C", "C++"),
        paper_quotes=(
            # Table I (Dataset Comparison) - ICVul row:
            # Repos: 807 | CWEs: 146 | VFCs: 4,327 | Files: 6,862 | Functions: 15,396 | Vul Funcs: 6,276 | Ratio: 41%
        ),
        # NOTE: The paper reports 4,327 VFCs (4,605 unique fc_hash in mapping, 4,327 with
        # commit metadata). Of those, only 3,916 have function data in function_info.csv,
        # and only 2,723 have at least one vulnerable function.
        vfcs=2723,
        non_vfcs=0,
        projects=807,
        vulnerable_functions=6276,
        benign_functions=9120,
    )

    GDRIVE_FILE_ID = "1Bnnb7kJa8GEfyESIAuGXj2z0g8FvXgRk"

    def _load_data(self) -> pd.DataFrame:
        dataset_dir = self._raw_dir / "icvul"
        base_path = dataset_dir / "ICVul-Dataset"

        mapping_path = base_path / "cve_fc_vcc_mapping.csv"
        commit_path = base_path / "commit_info.csv"
        function_path = base_path / "function_info.csv"

        if not mapping_path.exists():
            url = f"https://drive.google.com/uc?id={self.GDRIVE_FILE_ID}"
            download_and_extract_zip(url, dataset_dir)

        # 1. Load mapping and commit info, inner join to keep only VFCs
        df_mapping = pd.read_csv(mapping_path)
        df_commits = pd.read_csv(commit_path, usecols=["hash", "msg", "author_date"])

        # Inner join to get the VFCs that have metadata
        df_vfc = pd.merge(df_mapping, df_commits, left_on="fc_hash", right_on="hash", how="inner")

        # Collapse duplicate rows from commits fixing multiple CVEs
        df_vfc_agg = (
            df_vfc.groupby("hash")
            .agg(
                repo_url=("repo_url", "first"),
                cve_id=("cve_id", lambda x: list(set(x.dropna()))),
                cwe_id=("cwe_id", lambda x: list(set(x.dropna()))),
                msg=("msg", "first"),
                author_date=("author_date", "first"),
            )
            .reset_index()
        )

        # 2. Load function info (only columns used by _parse_row) and join with VFC metadata
        func_cols = ["hash", "name", "filename", "start_line", "end_line", "before_change"]
        df_functions = pd.read_csv(function_path, usecols=func_cols)
        df = pd.merge(df_functions, df_vfc_agg, on="hash", how="inner")

        return df

    def _parse_row(self, row: dict[str, Any]) -> DatasetEntry | None:
        # Extract and validate project URL and commit ID
        project_url, commit_id = extract_url_and_commit(row, "repo_url", "hash", self.metadata.name)

        if not project_url or not commit_id:
            return None

        is_vulnerable = row.get("before_change") is True

        function_name = f"{row.get('name')}-[{row.get('start_line')}-{row.get('end_line')}]"

        file_name = row.get("filename")

        return DatasetEntry(
            project_url=project_url,
            commit_id=commit_id,
            src_datasets={self.metadata.name},
            is_vfc=is_vulnerable,
            cve_ids=normalize_cve_ids(row.get("cve_id")),
            cwe_ids=normalize_cwe_ids(row.get("cwe_id")),
            function_name=function_name,
            files_changed={file_name} if file_name else set(),
            commit_message=row.get("msg"),
            commit_timestamp_utc=row.get("author_date"),
        )
