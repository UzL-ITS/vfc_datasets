import logging
from typing import Any

import pandas as pd

from dataset_entry import DatasetEntry
from vfc_datasets.base_dataset import BaseDataset, DatasetMetadata
from vfc_datasets.download_helper import download_file
from vfc_datasets.parsing_helpers import (
    normalize_cve_ids,
    normalize_cwe_ids,
    normalize_or_resolve_commit,
)

logger = logging.getLogger(__name__)


class SecBenchDataset(BaseDataset):
    metadata = DatasetMetadata(
        name="secbench",
        granularity="commit",
        paper_title="SECBENCH: A Database of Real Security Vulnerabilities",
        paper_url="https://ceur-ws.org/Vol-1977/paper6.pdf",
        download_url="https://tqrg.github.io/secbench/",
        publication_year=2017,
        paper_quotes=(
            # SecSE 2017 Paper - Page 1 (Abstract)
            "We mined 248 projects - accounting to almost 2M commits - for 16 different vulnerability patterns, "
            "yielding a Database with 682 real security vulnerabilities.",
        ),
        vfcs=676,  # "Dataset of 676 security vulnerabilities patches." https://tqrg.github.io/secbench
        non_vfcs=0,
        projects=248,
    )

    def _load_data(self) -> pd.DataFrame:
        raw_dataset_path = self._raw_dir / "secbench.csv"

        download_file(
            "https://raw.githubusercontent.com/TQRG/secbench/refs/heads/master/dataset/secbench.csv",
            raw_dataset_path,
            checksum="970df88dea3d98c23e36929aa73008f127efaa43ee77aad51a3392d4a038cade",
        )
        return pd.read_csv(raw_dataset_path)

    def _parse_row(self, row: dict[str, Any]) -> DatasetEntry | None:
        # project url is a github url
        owner = row.get("owner")
        project = row.get("project")
        if not isinstance(owner, str) or not owner or not isinstance(project, str) or not project:
            logger.debug(
                "[%s] Skipping row: missing owner=%s or project=%s",
                self.metadata.name,
                owner,
                project,
            )
            return None

        project_url = f"https://github.com/{owner}/{project}"

        raw_commit_id = row.get("sha")
        commit_id = normalize_or_resolve_commit(raw_commit_id, project_url)
        if not commit_id:
            return None

        return DatasetEntry(
            project_url=project_url,
            commit_id=commit_id,
            src_datasets={self.metadata.name},
            is_vfc=True,
            cve_ids=normalize_cve_ids(row.get("cve_id")),
            cwe_ids=normalize_cwe_ids(row.get("cwe_id")),
        )
