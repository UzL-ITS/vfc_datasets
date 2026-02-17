from typing import Any

import pandas as pd

from dataset_entry import DatasetEntry
from datasets.base_dataset import BaseDataset, DatasetMetadata
from datasets.download_helper import load_or_download_csv
from datasets.parsing_helpers import (
    extract_from_commit_url,
    normalize_cve_ids,
    normalize_or_resolve_commit,
)

TRACER_CSV_URL = "https://raw.githubusercontent.com/patch-tracer/patch-tracer.github.io/refs/heads/main/Experimental%20Data/Empirical%20Study/depth_dataset.csv"


class TracerDataset(BaseDataset):
    metadata = DatasetMetadata(
        name="tracer",
        granularity="commit",
        paper_title="Tracking Patches for Open Source Software Vulnerabilities",
        paper_url="https://doi.org/10.48550/arXiv.2112.02240",
        download_url="https://github.com/patch-tracer/patch-tracer.github.io",
        publication_year=2022,
        paper_quotes=(
            # Page 3 (Section 2.1 - Depth Dataset Construction)
            "Finally, they successfully found patches for 1,295 CVEs, while they were still uncertain "
            "for 122 CVEs due to limited disclosed information.",
        ),
        # NOTE: paper_vfcs refers to released dataset at source_url, not paper's evaluation dataset
        vfcs=3188,  # commits in released CSV
    )

    def _load_data(self) -> pd.DataFrame:
        tracer_csv_data = self._raw_dir / "tracer_depth_dataset.csv"

        try:
            return load_or_download_csv(output_path=tracer_csv_data, url=TRACER_CSV_URL)
        except Exception as e:
            raise RuntimeError(
                f"Failed to load TRACER dataset from {TRACER_CSV_URL}. "
                f"This may be due to a network error or invalid file format. "
                f"Error: {e}"
            ) from e

    def _parse_row(self, row: dict[str, Any]) -> DatasetEntry | None:
        # Extract project URL and raw commit ID from commit URL
        project_url, raw_commit_id = extract_from_commit_url(
            row, "github_commit", self.metadata.name
        )
        if not project_url or not raw_commit_id:
            return None

        # Normalize commit ID
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
