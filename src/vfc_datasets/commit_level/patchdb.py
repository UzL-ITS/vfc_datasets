import logging
from typing import Any, override

import pandas as pd

from vfc_datasets.base_dataset import BaseDataset, DatasetMetadata
from vfc_datasets.config import RAW_DATA_PATH
from vfc_datasets.dataset_entry import DatasetEntry
from vfc_datasets.download_helper import download_file
from vfc_datasets.parsing_helpers import (
    normalize_commit_id,
    normalize_cve_ids,
    normalize_cwe_ids,
)

logger = logging.getLogger(__name__)


class PatchDBDataset(BaseDataset):
    metadata = DatasetMetadata(
        name="patchdb",
        granularity="commit",
        paper_title="PatchDB: A Large-Scale Security Patch Dataset",
        paper_url="https://doi.org/10.1109/DSN48987.2021.00030",
        source_url="https://huggingface.co/datasets/sunlab/patch_db",
        publication_year=2021,
        programming_languages=("C", "C++"),
        paper_quotes=(
            # ASE 2021 Paper - Page 2 (Features)
            "it is a large-scale security patch dataset that contains 12K natural security patches, "
            "where 4K are from the NVD-based dataset and 8K are from the wild-based dataset",
            # Page 7 (Section IV-A - RQ1 Results)
            "After the five rounds of the dataset augmentation process, we collect a security patch "
            "dataset of 12,073 instances, where 4076 ones belong to the NVD-based dataset and 7997 "
            "ones belong to the wild-based dataset. We also get a cleaned non-security patch dataset "
            "of 23,742 instances.",
            # Page 3 (Section III-A): 313 GitHub repositories, C/C++ patches from NVD (1999-2019)
        ),
        vfcs=10691,  # --> 12073, NOTE: Many commits without project url. Try to find the missing URLs using the CVE ID and verify them using the commit message or diff.
        non_vfcs=23742,
        projects=313,
    )

    @override
    def _load_data(self) -> pd.DataFrame:
        patch_db_dump = RAW_DATA_PATH / "patch_db.json"

        if not patch_db_dump.exists():
            download_file(
                url="https://huggingface.co/datasets/sunlab/patch_db/resolve/main/patch_db.json",
                output_path=patch_db_dump,
                checksum="c59e9ff76b0dd21c4fa5f3b735ba8e5eadbe3a326f93c597b8619cfa395829c6",
            )

        return pd.read_json(patch_db_dump)

    @override
    def _parse_row(self, row: dict[str, Any]) -> DatasetEntry | None:
        # Skip invalid entries
        owner = row.get("owner")
        repo = row.get("repo")
        if not isinstance(owner, str) or not isinstance(repo, str):
            logger.debug("[%s] Skipping row: missing owner/repo", self.metadata.name)
            return None
        if owner == "NA" or repo == "NA":
            logger.debug("[%s] Skipping row: owner or repo is 'NA'", self.metadata.name)
            return None

        # Build project URL
        project_url = f"https://github.com/{owner}/{repo}"

        # Extract raw commit ID
        raw_commit_id = row.get("commit_id")
        if not raw_commit_id:
            logger.debug(
                "[%s] Skipping row: missing commit_id for project=%s",
                self.metadata.name,
                project_url,
            )
            return None

        # Handle corrupted commit IDs with spaces
        raw_commit_id_str = str(raw_commit_id)
        if " " in raw_commit_id_str:
            logger.warning(
                "PatchDB entry has commit_id with space: %r for %s. "
                "Attempting to extract valid hash from first part.",
                raw_commit_id_str,
                project_url,
            )
            # Try first part only
            first_part = raw_commit_id_str.split()[0]
            commit_id = normalize_commit_id(first_part)
            if not commit_id:
                logger.debug(
                    "[%s] Skipping row: could not extract valid commit hash from %r for %s",
                    self.metadata.name,
                    raw_commit_id_str,
                    project_url,
                )
                return None
        else:
            commit_id = normalize_commit_id(raw_commit_id_str)
            if not commit_id:
                return None

        return DatasetEntry(
            project_url=project_url,
            commit_id=commit_id,
            src_datasets={self.metadata.name},
            is_vfc="non-security" not in str(row.get("category", "")),
            cve_ids=normalize_cve_ids(row.get("CVE_ID")),
            cwe_ids=normalize_cwe_ids(row.get("CWE_ID")),
        )
