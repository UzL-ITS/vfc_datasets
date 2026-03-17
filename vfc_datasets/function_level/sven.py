import json
import logging
import os
from pathlib import Path
from typing import Any

import pandas as pd

from vfc_datasets.base_dataset import BaseDataset, DatasetMetadata
from vfc_datasets.dataset_entry import DatasetEntry
from vfc_datasets.parsing_helpers import normalize_commit_id, normalize_cwe_ids
from vfc_datasets.utils.git.repository import clone_repository
from vfc_datasets.utils.git.url import GitURL, url_to_pathname

logger = logging.getLogger(__name__)


class SVENDataset(BaseDataset):
    metadata = DatasetMetadata(
        name="sven",
        granularity="function",
        paper_title="Large Language Models for Code: Security Hardening and Adversarial Testing",
        paper_url="https://doi.org/10.1145/3576915.3623175",
        source_url="https://github.com/eth-sri/sven",
        publication_year=2023,
        programming_languages=("C", "C++", "Python"),
        paper_quotes=(
            # Page 2
            "To obtain a high-quality dataset for SVEN, we perform manual curation on [BigVul, CrossVul, VUDENC], "
            "which results in ~1.6k programs.",
            # Page 7
            "Our data construction relies on manual effort and deliberately excludes samples that do not meet "
            "our quality criteria, thus prioritizing quality over quantity.",
        ),
        vfcs=559,
        non_vfcs=0,
        vulnerable_functions=800,
        benign_functions=0,
    )

    def __init__(self) -> None:
        super().__init__()
        self.sven_repo_path: str | None = None

    def _load_data(self) -> pd.DataFrame:
        self.sven_repo_path = url_to_pathname(self.metadata.source_url)
        clone_repository(self.metadata.source_url, branch="master")

        if not os.path.exists(self.sven_repo_path):
            logger.error("Failed to clone repository: %s", self.metadata.source_url)
            return pd.DataFrame()

        # Load all jsonl files from train and val directories
        all_data: list[dict[str, Any]] = []
        subdirs = ["data_train_val/train", "data_train_val/val"]

        for sub_dir in subdirs:
            for file in (Path(self.sven_repo_path) / sub_dir).glob("*.jsonl"):
                with open(file, encoding="utf-8", errors="replace") as f:
                    all_data.extend(json.loads(line) for line in f)

        return pd.DataFrame(all_data)

    def _parse_row(self, row: dict[str, Any]) -> DatasetEntry | None:
        commit_link = row.get("commit_link")
        if not isinstance(commit_link, str) or not commit_link:
            logger.debug("[%s] Skipping row: missing commit_link", self.metadata.name)
            return None
        if not commit_link.startswith("http"):
            commit_link = "https://" + commit_link

        git_url = GitURL.parse(commit_link)
        project_url = git_url.to_https_url() if git_url else None
        commit_id = normalize_commit_id(git_url.commit_id) if git_url else None

        # Skip if missing required fields
        if not project_url or not commit_id:
            logger.debug(
                "[%s] Skipping row: missing project_url=%s or commit_id=%s from commit_link=%s",
                self.metadata.name,
                project_url,
                commit_id,
                commit_link,
            )
            return None

        function_name = row.get("func_name")
        if not function_name:
            logger.debug(
                "[%s] Skipping row: missing function_name for project=%s, commit=%s",
                self.metadata.name,
                project_url,
                commit_id,
            )
            return None

        file_name = row.get("file_name")

        return DatasetEntry(
            function_name=function_name,
            project_url=project_url,
            commit_id=commit_id,
            src_datasets={self.metadata.name},
            is_vfc=True,
            files_changed={file_name} if file_name else set(),
            cwe_ids=normalize_cwe_ids(row.get("vul_type")),
        )
