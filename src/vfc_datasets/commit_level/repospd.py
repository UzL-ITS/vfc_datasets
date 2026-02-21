import logging
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import pandas as pd

from dataset_entry import DatasetEntry
from vfc_datasets.base_dataset import BaseDataset, DatasetMetadata
from vfc_datasets.download_helper import download_from_gdrive
from vfc_datasets.parsing_helpers import (
    normalize_cve_ids,
    normalize_cwe_ids,
    normalize_or_resolve_commit,
)

logger = logging.getLogger(__name__)


class RepoSPDDataset(BaseDataset):
    metadata = DatasetMetadata(
        name="repospd",
        granularity="commit",
        paper_title="Repository-Level Graph Representation Learning for Enhanced Security Patch Detection",
        paper_url="https://doi.org/10.48550/arXiv.2412.08068",
        download_url="https://github.com/Xin-Cheng-Wen/RepoSPD",
        publication_year=2024,
        programming_languages=("C", "C++"),
        paper_quotes=(
            # ICSE 2025 Paper - Page 1 (Abstract)
            "We further extend these datasets to the repository level, incorporating a total of 20,238 and "
            "28,781 versions of repository in C/C++ programming languages, respectively, denoted as SPI-DB* "
            "and PatchDB*.",
            # Page 6 (Section IV.B.1 - Dataset description)
            "SPI-DB collects patches from two major C/C++ datasets, FFMPeg and Qemu, encompassing 25k patches, "
            "of which 10k have been classified as security-related. PatchDB compiles data from 348 open-source "
            "repositories, containing over 36k code snippets, approximately 12k identified as security patches.",
            # Table I: SPI-DB* 20,482 patches (20,238 repo versions) | PatchDB* 29,042 patches (28,781 repo versions)
        ),
        projects=348,
        # NOTE: Data from the released RepoSPD dataset files:
        vfcs=18127,
        non_vfcs=31397,
    )

    SUBSETS = ("spi_db", "patch_db")
    FILENAMES = ("train.jsonl", "dev.jsonl", "test.jsonl")
    GDRIVE_FILE_ID = "1esVwN0BB-DcKPzVd7gG_ZAhABvrbWjo3"
    PROJECT_URLS = {
        "ffmpeg": "https://github.com/ffmpeg/ffmpeg",
        "qemu": "https://github.com/qemu/qemu",
    }

    def _load_data(self) -> pd.DataFrame:
        dataset_path = self._raw_dir / "repospd"
        self._download_if_missing(dataset_path)

        all_data = []
        for subset in self.SUBSETS:
            for filename in self.FILENAMES:
                file_path = dataset_path / subset / filename
                if not file_path.exists():
                    logger.warning("Missing RepoSPD file: %s", file_path)
                    continue
                df = pd.read_json(file_path, lines=True)
                df["subset"] = subset
                df["split"] = Path(filename).stem
                all_data.append(df)

        return pd.concat(all_data, ignore_index=True)

    def _download_if_missing(self, dataset_path: Path) -> None:
        expected = [
            dataset_path / subset / fname for subset in self.SUBSETS for fname in self.FILENAMES
        ]
        if all(p.exists() for p in expected):
            return

        dataset_path.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = Path(tmpdir) / "repospd.zip"
            download_from_gdrive(self.GDRIVE_FILE_ID, str(zip_path))

            with zipfile.ZipFile(zip_path) as zf:
                for subset in self.SUBSETS:
                    for fname in self.FILENAMES:
                        member = f"dataset/{subset}/{fname}"
                        dest = dataset_path / subset / fname
                        if dest.exists():
                            continue
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        try:
                            zf.extract(member, path=tmpdir)
                            shutil.move(Path(tmpdir) / "dataset" / subset / fname, dest)
                        except KeyError:
                            logger.warning("Missing %s in RepoSPD archive", member)

    def _parse_row(self, row: dict[str, Any]) -> DatasetEntry | None:
        # Transform data
        category = row.get("category")
        if not isinstance(category, str) or not category:
            logger.debug("[%s] Skipping row: missing category", self.metadata.name)
            return None
        is_vfc = category != "non-security"

        ori_dataset = row.get("ori_dataset")
        project_url = self.PROJECT_URLS.get(ori_dataset) if isinstance(ori_dataset, str) else None

        if not project_url:
            # Use owner and repo name
            owner = row.get("owner")
            repo_name = row.get("repo")
            if owner and repo_name:
                project_url = f"https://github.com/{owner}/{repo_name}"
            if not project_url:
                logger.debug(
                    "[%s] Skipping row: missing project_url, owner=%s, repo=%s, ori_dataset=%s",
                    self.metadata.name,
                    owner,
                    repo_name,
                    row.get("ori_dataset"),
                )
                return None

        raw_commit_id = row.get("commit_id")
        commit_id = normalize_or_resolve_commit(raw_commit_id, project_url)
        if not commit_id:
            return None

        return DatasetEntry(
            project_url=project_url,
            commit_id=commit_id,
            src_datasets={self.metadata.name},
            is_vfc=is_vfc,
            cve_ids=normalize_cve_ids(row.get("CVE_ID")),
            cwe_ids=normalize_cwe_ids(row.get("CWE_ID")),
        )
