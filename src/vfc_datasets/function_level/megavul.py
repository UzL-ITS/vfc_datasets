import json
import logging
from typing import Any, override

import pandas as pd

from vfc_datasets.base_dataset import BaseDataset, DatasetMetadata
from vfc_datasets.config import RAW_DATA_PATH
from vfc_datasets.dataset_entry import DatasetEntry
from vfc_datasets.parsing_helpers import normalize_cve_ids, normalize_cwe_ids
from vfc_datasets.utils.git.url import GitURL, normalize_commit_id

logger = logging.getLogger(__name__)


class MegaVulDataset(BaseDataset):
    metadata = DatasetMetadata(
        name="megavul",
        granularity="function",
        paper_title="MegaVul: A C/C++ Vulnerability Dataset with Comprehensive Code Representations",
        paper_url="https://doi.org/10.1145/3643991.3644886",
        source_url="https://github.com/Icyrockton/MegaVul",
        publication_year=2024,
        programming_languages=("C", "C++", "Java"),
        paper_quotes=(
            # MSR 2024 Paper - Page 1 (Abstract)
            "Totally, MegaVul contains 17,380 vulnerabilities collected from 992 open-source repositories "
            "spanning 169 different vulnerability types disclosed from January 2006 to October 2023.",
            # Page 4 (Section 7 - Conclusion)
            "In conclusion, MegaVul has gathered high-quality functions from 9,019 commits, including "
            "17,380 vulnerable and 322,168 non-vulnerable functions.",
        ),
        # NOTE: Paper has C/CPP and Java dataset
        vfcs=10182,
        non_vfcs=0,
        projects=992,
        vulnerable_functions=20267,
        benign_functions=367147,
    )

    @override
    def _load_data(self) -> pd.DataFrame:
        megavul_dir = RAW_DATA_PATH / "megavul"

        cpp_json_path = megavul_dir / "megavul_simple_cpp.json"
        java_json_path = megavul_dir / "megavul_simple_java.json"

        # Could not find permalinks for OneDrive...
        if not cpp_json_path.is_file() or not java_json_path.is_file():
            raise FileNotFoundError(
                f"MegaVul JSON files not found in {megavul_dir}. "
                "Please download 'megavul_simple_cpp.json' and 'megavul_simple_java.json' "
                "You can find the files here: https://1drv.ms/f/s!AtzrzuojQf5sgeISZ9zN_4owVnUn9g."
            )

        with open(cpp_json_path, encoding="utf-8") as f:
            cpp_data = json.load(f)
        with open(java_json_path, encoding="utf-8") as f:
            java_data = json.load(f)

        return pd.DataFrame(cpp_data + java_data)

    @override
    def _parse_row(self, row: dict[str, Any]) -> DatasetEntry | None:
        git_url_value = row.get("git_url")
        if not git_url_value:
            logger.debug("[%s] Skipping row: missing git_url", self.metadata.name)
            return None

        commit_id = normalize_commit_id(row.get("commit_hash"))

        # Special case: ffmpeg URLs in MegaVul are malformed
        repo_name = row.get("repo_name")
        if repo_name == "ffmpeg":
            project_url: str | None = "https://github.com/ffmpeg/ffmpeg"
        else:
            parsed_git_url = GitURL.parse(str(git_url_value))
            if not parsed_git_url:
                logger.debug(
                    "[%s] Skipping row: failed to parse git_url=%s",
                    self.metadata.name,
                    git_url_value,
                )
                return None
            project_url = parsed_git_url.to_https_url()
            if not project_url:
                logger.debug(
                    "[%s] Skipping row: failed to extract project_url from git_url=%s",
                    self.metadata.name,
                    git_url_value,
                )
                return None

        if not project_url or not commit_id:
            logger.debug(
                "[%s] Skipping row: missing project_url=%s or commit_id=%s",
                self.metadata.name,
                project_url,
                commit_id,
            )
            return None

        # Skip entries without function name (required for function-level dataset)
        function_name = row.get("func_name")
        if not function_name:
            logger.debug(
                "[%s] Skipping row: missing function_name for project=%s, commit=%s",
                self.metadata.name,
                project_url,
                commit_id,
            )
            return None

        file_path = row.get("file_path")

        return DatasetEntry(
            project_url=project_url,
            commit_id=commit_id,
            src_datasets={self.metadata.name},
            files_changed={file_path} if file_path else set(),
            is_vfc=bool(row.get("is_vul")),
            cve_ids=normalize_cve_ids(row.get("cve_id")),
            cwe_ids=normalize_cwe_ids(row.get("cwe_ids")),
            function_name=function_name,
        )
