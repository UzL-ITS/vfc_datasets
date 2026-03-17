import logging
from typing import Any

import pandas as pd

from vfc_datasets.base_dataset import BaseDataset, DatasetMetadata
from vfc_datasets.dataset_entry import DatasetEntry
from vfc_datasets.parsing_helpers import normalize_cve_ids, normalize_or_resolve_commit

logger = logging.getLogger(__name__)


class VCMatchDataset(BaseDataset):
    metadata = DatasetMetadata(
        name="vcmatch",
        granularity="commit",
        paper_title="VCMatch: A Ranking-based Approach for Automatic Security Patches Localization for OSS Vulnerabilities",
        paper_url="https://doi.org/10.1109/SANER53432.2022.00076",
        source_url="https://figshare.com/s/0f3ed11f9348e2f3a9f8",
        publication_year=2022,
        paper_quotes=(
            # Page 2 (Contribution 1)
            "We build a dataset containing 1,669 vulnerabilities and their corresponding fixing "
            "commits from 10 popular OSS projects.",
        ),
        vfcs=1669,
        non_vfcs=0,
        projects=10,
    )

    PROJECT_URLS = {
        "FFmpeg": "https://github.com/FFmpeg/FFmpeg",
        "ImageMagick": "https://github.com/ImageMagick/ImageMagick",
        "jenkins": "https://github.com/jenkinsci/jenkins",
        "linux": "https://github.com/torvalds/linux",
        "moodle": "https://github.com/moodle/moodle",
        "openssl": "https://github.com/openssl/openssl",
        "php-src": "https://github.com/php/php-src",
        "phpmyadmin": "https://github.com/phpmyadmin/phpmyadmin",
        "qemu": "https://github.com/qemu/qemu",
        "wireshark": "https://github.com/wireshark/wireshark",
    }

    def _load_data(self) -> pd.DataFrame:
        raw_dataset_path = self._raw_dir / "vcmatch.csv"

        if not raw_dataset_path.exists():
            url = (
                "https://figshare.com/ndownloader/files/32403518?private_link=0f3ed11f9348e2f3a9f8"
            )
            raise FileNotFoundError(
                f"VCMatch dataset not found at {raw_dataset_path}. "
                f"Figshare blocks automated downloads (AWS WAF bot challenge). "
                f"Please download manually from {url}, extract data/data.csv, "
                f"and place it at {raw_dataset_path}"
            )

        return pd.read_csv(raw_dataset_path)

    def _parse_row(self, row: dict[str, Any]) -> DatasetEntry | None:
        project_name = row.get("repo")
        project_url = self.PROJECT_URLS.get(project_name) if project_name else None

        if not project_url:
            logger.debug(
                "[%s] Skipping row: unknown or missing project name=%s",
                self.metadata.name,
                project_name,
            )
            return None

        raw_commit_id = row.get("commit")
        commit_id = normalize_or_resolve_commit(raw_commit_id, project_url)
        if not commit_id:
            return None

        return DatasetEntry(
            project_url=project_url,
            commit_id=commit_id,
            src_datasets={self.metadata.name},
            is_vfc=True,
            cve_ids=normalize_cve_ids(row.get("cve")),
        )
