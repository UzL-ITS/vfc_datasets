import json
import logging
from functools import cache
from pathlib import Path
from typing import Any

import pandas as pd

from dataset_entry import DatasetEntry
from vfc_datasets.base_dataset import BaseDataset, DatasetMetadata
from vfc_datasets.download_helper import download_file
from vfc_datasets.parsing_helpers import normalize_commit_id, normalize_cwe_ids

logger = logging.getLogger(__name__)


class DiverseVulDataset(BaseDataset):
    metadata = DatasetMetadata(
        name="diversevul",
        granularity="function",
        paper_title="DiverseVul: A New Vulnerable Source Code Dataset for Deep Learning Based Vulnerability Detection",
        paper_url="https://doi.org/10.1145/3607199.3607242",
        source_url="https://github.com/wagner-group/diversevul",
        publication_year=2023,
        programming_languages=("C", "C++"),
        paper_quotes=(
            # Page 4 (Section 3 - Data Collection)
            "In total, we have collected 7,514 commits from 797 projects, which result in 18,945 "
            "vulnerable functions and 330,492 non-vulnerable functions, covering 150 CWEs.",
        ),
        vfcs=7514,
        non_vfcs=0,
        projects=797,
        vulnerable_functions=18945,
        benign_functions=311547,
    )

    @staticmethod
    @cache
    def _get_project_urls() -> dict[str, list[str]]:
        with open(Path(__file__).parent / "diversevul_project_urls.json", encoding="utf-8") as f:
            return json.load(f)

    def _load_data(self) -> pd.DataFrame:
        raw_dataset_path = self._raw_dir / "diversevul.json"
        download_file(
            "https://drive.google.com/uc?id=12IWKhmLhq7qn5B_iXgn5YerOQtkH-6RG", raw_dataset_path
        )

        # Load JSON lines and filter vulnerable functions only
        data = []
        with open(raw_dataset_path, encoding="utf-8", errors="replace") as f:
            for line in f:
                entry = json.loads(line)
                # TODO: Do not only include vulnerable functions (target = 1)
                # if entry.get("target"):
                data.append(entry)

        return pd.DataFrame(data)

    def _parse_row(self, row: dict[str, Any]) -> DatasetEntry | None:
        # Get commit ID
        raw_commit_id = row.get("commit_id")
        commit_id = normalize_commit_id(raw_commit_id)
        if not commit_id:
            logger.debug(
                "[%s] Skipping row: invalid commit_id=%s", self.metadata.name, raw_commit_id
            )
            return None

        # Get project URL
        project_name = row.get("project", "").lower()
        project_url = self._get_project_url(project_name, commit_id)
        if not project_url:
            logger.debug(
                "[%s] Skipping row: no project URL mapping for project=%s, commit_id=%s",
                self.metadata.name,
                project_name,
                commit_id,
            )
            return None

        function_hash = row.get("hash")  # This is the MD5 hash of row['func']
        if isinstance(function_hash, int):
            function_hash = hex(function_hash)[2:]

        # func = row.get("func")
        # TODO: Get function name from row['func']
        # until then... use function hash as name

        if not function_hash:
            logger.debug(
                "[%s] Skipping row: missing function hash for project=%s, commit_id=%s",
                self.metadata.name,
                project_url,
                commit_id,
            )
            return None

        return DatasetEntry(
            function_name=function_hash,
            project_url=project_url,
            commit_id=commit_id,
            src_datasets={self.metadata.name},
            is_vfc=row.get("target") == 1,
            cwe_ids=normalize_cwe_ids(row.get("cwe", [])),
            commit_message=row.get("message"),
        )

    def _get_project_url(self, project_name: str, commit_id: str) -> str | None:
        # Special cases
        if project_name == "profanity" and commit_id == "69ff010c14ff80ec14246772db6a245aa59e6689":
            return "https://github.com/johguse/profanity"
        if project_name == "librsvg":
            special_commits = {
                "34c95743ca692ea0e44778e41a7c0a129363de84",
                "d83e426fff3f6d0fa6042d0930fb70357db24125",
                "f01aded72c38f0e18bc7ff67dee800e380251c8e",
                "40af93e6eb1c94b90c3b9a0b87e0840e126bb8df",
                "a51919f7e1ca9c535390a746fbf6e28c8402dc61",
                "d1c9191949747f6dcfd207831d15dd4ba00e31f2",
                "0035e95118a60c0cd3949c2300472d805e16a022",
                "ecf9267a24b2c3c0cd211dbdfa9ef2232511972a",
                "572f95f739529b865e2717664d6fefcef9493135",
            }
            if commit_id in special_commits:
                return "https://github.com/gnome/librsvg"

        # Look up in mapping
        urls = self._get_project_urls().get(project_name)
        if urls:
            return urls[0]

        return None
