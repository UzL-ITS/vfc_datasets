from typing import Any, override

import pandas as pd

from vfc_datasets.base_dataset import BaseDataset, DatasetMetadata
from vfc_datasets.dataset_entry import DatasetEntry
from vfc_datasets.download_helper import download_file
from vfc_datasets.parsing_helpers import (
    extract_from_commit_url,
    normalize_commit_id,
    normalize_cve_ids,
)

TRACER_CSV_URL = "https://raw.githubusercontent.com/patch-tracer/patch-tracer.github.io/refs/heads/main/Experimental%20Data/Empirical%20Study/depth_dataset.csv"


class TracerDataset(BaseDataset):
    metadata = DatasetMetadata(
        name="tracer",
        granularity="commit",
        paper_title="Tracking Patches for Open Source Software Vulnerabilities",
        paper_url="https://doi.org/10.48550/arXiv.2112.02240",
        source_url="https://github.com/patch-tracer/patch-tracer.github.io",
        publication_year=2022,
        paper_quotes=(
            # Page 3 (Section 2.1 - Depth Dataset Construction)
            "Finally, they successfully found patches for 1,295 CVEs, while they were still uncertain "
            "for 122 CVEs due to limited disclosed information.",
        ),
        vfcs=3017,  # NOTE: -> 3188 (SVN or unsupported git urls)
        non_vfcs=0,
    )

    @override
    def _load_data(self) -> pd.DataFrame:
        csv_path = self._raw_dir / "tracer_depth_dataset.csv"
        download_file(
            TRACER_CSV_URL,
            csv_path,
            checksum="3202f6a4b8d491ae54cb937467d7159377b1c7ee3125f8dfd38b06d10329906b",
        )
        return pd.read_csv(csv_path)

    @override
    def _parse_row(self, row: dict[str, Any]) -> DatasetEntry | None:
        # Try github_commit first, fallback to other_platform_git_commit
        project_url, raw_commit_id = extract_from_commit_url(
            row, "github_commit", self.metadata.name
        )
        if not project_url or not raw_commit_id:
            project_url, raw_commit_id = extract_from_commit_url(
                row, "other_platform_git_commit", self.metadata.name
            )
        if not project_url or not raw_commit_id:
            return None

        commit_id = normalize_commit_id(raw_commit_id)
        if not commit_id:
            return None

        return DatasetEntry(
            project_url=project_url,
            commit_id=commit_id,
            src_datasets={self.metadata.name},
            is_vfc=True,
            cve_ids=normalize_cve_ids(row.get("cve")),
        )
