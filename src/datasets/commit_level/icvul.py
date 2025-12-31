"""
# TODO: think about how we should handle the Vulnerability Contributing Commits (VCCs)
# in this dataset
"""

import logging
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import pandas as pd

from dataset_entry import DatasetEntry
from datasets.base_dataset import BaseDataset, DatasetMetadata
from datasets.download_helper import download_from_gdrive
from datasets.parsing_helpers import (
    normalize_cve_ids,
    normalize_cwe_ids,
    normalize_or_resolve_commit,
)
from utils.git.url import GitURL

logger = logging.getLogger(__name__)


class ICVulDataset(BaseDataset):
    metadata = DatasetMetadata(
        name="icvul",
        granularity="commit",
        paper_title="ICVul: A Well-labeled C/C++ Vulnerability Dataset with Comprehensive Metadata and VCCs",
        paper_url="https://doi.org/10.48550/arXiv.2505.08503",
        download_url="https://github.com/Chaomeng-Lu/ICVul",
        publication_year=2025,
        programming_languages=("C", "C++"),
        paper_quotes=(
            # Table I (Dataset Comparison) - ICVul row:
            # Repos: 807 | CWEs: 146 | VFCs: 4,327 | Files: 6,862 | Functions: 15,396 | Vul Funcs: 6,276 | Ratio: 41%
        ),
        # NOTE: From Table I - 4,327 fix commits, 807 repos, 146 CWEs, 15,396 functions (6,276 vulnerable)
        vfcs=4327,
        projects=807,
        vulnerable_functions=6276,
        benign_functions=9120,
    )

    GDRIVE_FILE_ID = "1Bnnb7kJa8GEfyESIAuGXj2z0g8FvXgRk"
    ARCHIVE_MEMBER = "ICVul-Dataset/cve_fc_vcc_mapping.csv"
    CSV_FILENAME = "icvul_cve_fc_vcc_mapping.csv"

    def _load_data(self) -> pd.DataFrame:
        csv_path = self._raw_dir / self.CSV_FILENAME
        self._download_if_missing(csv_path)
        return pd.read_csv(csv_path, encoding="utf-8")

    def _download_if_missing(self, csv_path: Path) -> None:
        if csv_path.exists():
            return

        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = Path(tmpdir) / "icvul.zip"
            download_from_gdrive(self.GDRIVE_FILE_ID, str(zip_path))

            with zipfile.ZipFile(zip_path) as zf:
                zf.extract(self.ARCHIVE_MEMBER, path=tmpdir)
                shutil.move(Path(tmpdir) / self.ARCHIVE_MEMBER, csv_path)

    def _parse_row(self, row: dict[str, Any]) -> DatasetEntry | None:
        repo_url = row.get("repo_url")
        if not isinstance(repo_url, str) or not repo_url:
            logger.debug("[%s] Skipping row: missing repo_url", self.metadata.name)
            return None

        git_url = GitURL.parse(repo_url)
        project_url = git_url.to_https_url() if git_url else None
        if not project_url:
            logger.debug("[%s] Skipping row: failed to parse repo_url=%s", self.metadata.name, repo_url)
            return None

        fc_hash = row.get("fc_hash")
        if not isinstance(fc_hash, str) or not fc_hash:
            logger.debug("[%s] Skipping row: missing fc_hash", self.metadata.name)
            return None

        commit_id = normalize_or_resolve_commit(fc_hash, project_url)
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
