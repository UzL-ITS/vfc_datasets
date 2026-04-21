from typing import Any, override

import pandas as pd

from vfc_datasets.base_dataset import BaseDataset, DatasetMetadata
from vfc_datasets.dataset_entry import DatasetEntry
from vfc_datasets.download_helper import download_file
from vfc_datasets.parsing_helpers import (
    extract_from_commit_url,
    extract_url_and_commit,
    lookup_broken_commit,
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
        source_url="https://github.com/TQRG/security-patches-dataset/tree/main",
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

    @override
    def _load_data(self) -> pd.DataFrame:
        raw_dataset_dir = self._raw_dir / "tqrg"

        # Load positive dataset
        positive_path = raw_dataset_dir / "positive.csv"
        download_file(
            "https://raw.githubusercontent.com/TQRG/security-patches-dataset/main/dataset/security_patches_v1.0.csv",
            positive_path,
            checksum="6acd399813693b8714a3cfd2f1c423bb8511b022ccd5ed7311ac19015359f65e",
        )
        df_positive = pd.read_csv(positive_path)
        df_positive["dataset_type"] = "positive"

        # Load negative dataset
        negative_path = raw_dataset_dir / "negative.csv"
        download_file(
            "https://raw.githubusercontent.com/TQRG/security-patches-dataset/main/dataset/negative_commits.csv",
            negative_path,
            checksum="fc2670c6d0971c1bc7e21939916943614b85fbaf28bef17ac4177a79254564af",
        )
        df_negative = pd.read_csv(negative_path)
        df_negative["dataset_type"] = "negative"

        return pd.concat([df_positive, df_negative], ignore_index=True)

    @override
    def _parse_row(self, row: dict[str, Any]) -> DatasetEntry | None:
        is_vfc = row.get("dataset_type") == "positive"

        if is_vfc:
            project_url, commit_id = extract_url_and_commit(
                row, "project", "sha", self.metadata.name
            )
            if not project_url or not commit_id:
                sha = row.get("sha", "")
                match = lookup_broken_commit(sha)
                if not match:
                    return None
                project_url, commit_id = match
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
