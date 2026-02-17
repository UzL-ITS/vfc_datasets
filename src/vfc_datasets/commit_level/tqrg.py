from typing import Any

import pandas as pd

from dataset_entry import DatasetEntry
from datasets.base_dataset import BaseDataset, DatasetMetadata
from datasets.download_helper import load_or_download_csv
from datasets.parsing_helpers import (
    extract_from_commit_url,
    extract_url_and_commit,
    normalize_cve_ids,
    normalize_cwe_ids,
    normalize_or_resolve_commit,
)


class TQRGDataset(BaseDataset):
    metadata = DatasetMetadata(
        name="tqrg",
        granularity="commit",
        paper_title="A ground-truth dataset of real security patches",
        paper_url="https://doi.org/10.48550/arXiv.2110.09635",
        download_url="https://github.com/TQRG/security-patches-dataset/tree/main",
        publication_year=2021,
        paper_quotes=(
            # Page 1 (Abstract)
            "Our dataset integrates a total of 8057 security-relevant commits—the equivalent to 5942 security "
            "patches—from 1339 different projects spanning 146 different types of vulnerabilities and 20 languages. "
            "A dataset of 110k non-security-related commits is also provided.",
            # Page 2
            "We augmented this data with other 3 datasets that also contain vulnerabilities and the URL links to "
            "security patches: Secbench, Pontas et al. and Big-Vul.",
        ),
        # NOTE: 8057 = security-relevant commits, 5942 = unique security patches (some vulnerabilities need multiple commits)
        vfcs=8057,
        non_vfcs=110161,
        projects=1339,
    )

    def _load_data(self) -> pd.DataFrame:
        raw_dataset_dir = self._raw_dir / "tqrg"

        # Load positive dataset
        df_positive = load_or_download_csv(
            output_path=raw_dataset_dir / "positive.csv",
            url="https://raw.githubusercontent.com/TQRG/security-patches-dataset/main/dataset/security_patches_v1.0.csv",
        )
        df_positive["dataset_type"] = "positive"

        # Load negative dataset
        df_negative = load_or_download_csv(
            output_path=raw_dataset_dir / "negative.csv",
            url="https://raw.githubusercontent.com/TQRG/security-patches-dataset/main/dataset/negative_commits.csv",
        )
        df_negative["dataset_type"] = "negative"

        return pd.concat([df_positive, df_negative], ignore_index=True)

    def _parse_row(self, row: dict[str, Any]) -> DatasetEntry | None:
        is_vfc = row.get("dataset_type") == "positive"

        if is_vfc:
            project_url, commit_id = extract_url_and_commit(
                row, "project", "sha", self.metadata.name
            )
            if not project_url or not commit_id:
                return None
        else:
            project_url, raw_commit_id = extract_from_commit_url(row, "github", self.metadata.name)
            if not project_url or not raw_commit_id:
                return None
            commit_id = normalize_or_resolve_commit(raw_commit_id, project_url)
            if not commit_id:
                return None

        return DatasetEntry(
            project_url=project_url,
            commit_id=commit_id,
            src_datasets={self.metadata.name},
            is_vfc=is_vfc,
            cve_ids=normalize_cve_ids(row.get("cve_id")),
            cwe_ids=normalize_cwe_ids(row.get("cwe_id")),
        )
