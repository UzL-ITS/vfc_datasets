import logging
from typing import Any

import pandas as pd

from dataset_entry import DatasetEntry
from vfc_datasets.base_dataset import BaseDataset, DatasetMetadata
from vfc_datasets.download_helper import download_from_gdrive
from vfc_datasets.parsing_helpers import normalize_or_resolve_commit

logger = logging.getLogger(__name__)


class DevignDataset(BaseDataset):
    PROJECT_URLS = {
        "ffmpeg": "https://github.com/ffmpeg/ffmpeg",
        "qemu": "https://github.com/qemu/qemu",
    }

    GDRIVE_FILE_IDS = {
        "ffmpeg": "1Nk_U52_gVHYfnNk-pcXlnxssOBrmSllV",
        "qemu": "1RhyA-cZl2oiNb-IJOHYw4waBgvLzViTr",
    }

    metadata = DatasetMetadata(
        name="devign",
        granularity="commit",
        paper_title="Devign: Effective Vulnerability Identification by Learning Comprehensive Program Semantics via Graph Neural Networks",
        paper_url="https://doi.org/10.48550/arXiv.1909.03496",
        download_url="https://sites.google.com/view/devign",
        publication_year=2019,
        programming_languages=("C", "C++"),
        paper_quotes=(
            # NeurIPS 2019 Paper - Page 2 (Contributions)
            "We implement Devign, and evaluate its effectiveness through manually labeled data sets "
            "(cost around 600 man-hours) collected from the 4 popular C libraries. We make two datasets "
            "public together with more details (https://sites.google.com/view/devign).",
            # NOTE: Only FFmpeg and QEMU were released publicly. From Table 1:
            # FFmpeg: 13,962 commits, 5,962 VFCs, 8,000 Non-VFCs
            # QEMU: 11,910 commits, 4,932 VFCs, 6,978 Non-VFCs
        ),
        vfcs=10894,
        non_vfcs=14978,
        projects=2,
    )

    def _load_data(self) -> pd.DataFrame:
        raw_dataset_dir = self._raw_dir / "devign"

        dfs = []
        for project_name, file_id in self.GDRIVE_FILE_IDS.items():
            csv_path = raw_dataset_dir / f"{project_name}.csv"
            download_from_gdrive(file_id, csv_path)
            dfs.append(pd.read_csv(csv_path))

        return pd.concat(dfs, ignore_index=True)

    def _parse_row(self, row: dict[str, Any]) -> DatasetEntry | None:
        raw_commit_id = row.get("sha_id")
        if not raw_commit_id:
            logger.debug("[%s] Skipping row: missing sha_id", self.metadata.name)
            return None

        project_name = row.get("project")
        project_url = self.PROJECT_URLS.get(project_name) if project_name else None
        if not project_url:
            logger.debug(
                "[%s] Skipping row: unknown or missing project=%s", self.metadata.name, project_name
            )
            return None

        commit_id = normalize_or_resolve_commit(raw_commit_id, project_url)
        if not commit_id:
            return None

        return DatasetEntry(
            project_url=project_url,
            commit_id=commit_id,
            src_datasets={self.metadata.name},
            is_vfc=row.get("vulnerability") == 1,
        )
