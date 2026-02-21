import json
import logging
import shutil
import tempfile
from pathlib import Path
from typing import Any

import pandas as pd

from dataset_entry import DatasetEntry
from vfc_datasets.base_dataset import BaseDataset, DatasetMetadata
from vfc_datasets.download_helper import download_from_url
from vfc_datasets.parsing_helpers import extract_url_and_commit

logger = logging.getLogger(__name__)


class VUDEncDataset(BaseDataset):
    ZENODO_RECORD_ID = "3559841"

    metadata = DatasetMetadata(
        name="vudenc",
        granularity="commit",
        paper_title="VUDENC: Vulnerability Detection with Deep Learning on a Natural Codebase for Python",
        paper_url="https://doi.org/10.1016/j.infsof.2021.106809",
        download_url="https://doi.org/10.5281/zenodo.3559840",
        publication_year=2022,
        programming_languages=("Python",),
        paper_quotes=(
            # Page 1 (Abstract)
            "To evaluate Vudenc, we used 1,009 vulnerability-fixing commits from different GitHub repositories "
            "that contain seven different types of vulnerabilities (SQL injection, XSS, Command injection, XSRF, "
            "Remote code execution, Path disclosure, Open redirect) for training.",
            # Page 2
            "Labeled training datasets are obtained in a fully automated fashion by crawling for security-related "
            "fixes in the commit history of a software repository.",
        ),
        vfcs=1009,
    )

    # File names for the 7 vulnerability types in the dataset
    VULNERABILITY_FILES = (
        "plain_command_injection",
        "plain_open_redirect",
        "plain_path_disclosure",
        "plain_remote_code_execution",
        "plain_sql",
        "plain_xsrf",
        "plain_xss",
    )

    def _load_data(self) -> pd.DataFrame:
        base_url = f"https://zenodo.org/records/{self.ZENODO_RECORD_ID}/files"
        links = [f"{base_url}/{name}?download=1" for name in self.VULNERABILITY_FILES]

        logger.info("Downloading VUDEnc datasets...")
        vudenc_dir = self._raw_dir / "vudenc"
        vudenc_dir.mkdir(parents=True, exist_ok=True)

        for link in links:
            file_name = link.split("/")[-1].split("?")[0]
            json_path = vudenc_dir / f"{file_name}.json"
            if not json_path.exists():
                with tempfile.TemporaryDirectory() as tmp_dir:
                    download_from_url(
                        url=link,
                        output_path=Path(tmp_dir) / file_name,
                    )
                    shutil.move(
                        src=Path(tmp_dir) / file_name,
                        dst=json_path,
                    )

        # combine all json files into a single dataframe
        json_files = sorted(vudenc_dir.glob("*.json"))
        if not json_files:
            logger.warning("No VUDENC JSON files found in %s", vudenc_dir)
            return pd.DataFrame()

        records: list[dict[str, Any]] = []
        for jf in json_files:
            with open(jf, encoding="utf-8", errors="replace") as file:
                file_data = json.load(file)
                for commits in file_data.values():
                    if not isinstance(commits, dict):
                        continue
                    for commit_id in commits:
                        commit_data = commits.get(commit_id)
                        if commit_data:
                            records.append({**commit_data})

        return pd.DataFrame.from_records(records)

    def _parse_row(self, row: dict[str, Any]) -> DatasetEntry | None:
        # Extract and validate project URL and commit ID
        project_url, commit_id = extract_url_and_commit(row, "html_url", "sha", self.metadata.name)
        if not project_url or not commit_id:
            return None

        return DatasetEntry(
            project_url=project_url,
            commit_id=commit_id,
            src_datasets={self.metadata.name},
            is_vfc=True,
        )
