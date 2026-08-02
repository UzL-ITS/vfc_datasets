import logging
import shutil
import tempfile
from pathlib import Path
from typing import Any, override

import pandas as pd

from vfc_datasets.base_dataset import BaseDataset, DatasetMetadata
from vfc_datasets.config import RAW_DATA_PATH
from vfc_datasets.dataset_entry import DatasetEntry
from vfc_datasets.download_helper import download_and_extract_zip
from vfc_datasets.parsing_helpers import (
    extract_and_normalize_from_commit_url,
    lookup_broken_commit,
    normalize_cve_ids,
    normalize_cwe_ids,
)

logger = logging.getLogger(__name__)


class CrossVulDataset(BaseDataset):
    ZENODO_RECORD_ID = "4734050"

    metadata = DatasetMetadata(
        name="cross_vul",
        granularity="commit",
        paper_title="CrossVul: a cross-language vulnerability dataset with commit data",
        paper_url="https://doi.org/10.1145/3468264.3473122",
        source_url="https://doi.org/10.5281/zenodo.4734049",
        publication_year=2021,
        programming_languages=("40+ languages",),
        paper_quotes=(
            # ESEC/FSE 2021 Paper - Page 1 (Abstract)
            "We present a dataset (~1.4 GB) containing vulnerable source code files together with "
            "the corresponding, patched versions. Contrary to other existing vulnerability datasets, "
            "ours includes vulnerable files written in more than 40 programming languages.",
            # Page 1 (Introduction)
            "we have examined 5877 GitHub commits referenced by NVD (National Vulnerability Database) "
            "and CVE (Common Vulnerability and Exposures) entries.",
            # Page 2 (Section 3 - Dataset Description)
            "the dataset contains 1.4 GB of source code including 27476 files collected from "
            "1675 GitHub repositories.",
            # Page 2 (Table 1 - Descriptive statistics)
            # Commits: 5877, Unique CWEs: 168, Unique CVEs: 5131
            # All files: 27476, Vulnerable files: 13738, Non-vulnerable files: 13738
        ),
        vfcs=5877,
        non_vfcs=0,
        projects=1675,
    )

    @override
    def _load_data(self) -> pd.DataFrame:
        raw_dataset_path = RAW_DATA_PATH / "cross_vul.csv"

        if not raw_dataset_path.exists():
            with tempfile.TemporaryDirectory() as tmp_dir:
                url = f"https://zenodo.org/records/{self.ZENODO_RECORD_ID}/files/dataset.zip?download=1"
                logger.info("Downloading CrossVul dataset...")

                # Download and extract specific file
                download_and_extract_zip(
                    url=url,
                    extract_path=tmp_dir,
                    files_to_extract=["dataset_final_sorted/commits.list"],
                )

                shutil.move(
                    src=Path(tmp_dir) / "dataset_final_sorted" / "commits.list",
                    dst=raw_dataset_path,
                )

        return pd.read_csv(
            raw_dataset_path,
            delimiter=";",
            names=["cwe_id", "cve_id", "commit_url"],
        )

    @override
    def _parse_row(self, row: dict[str, Any]) -> DatasetEntry | None:
        project_url, commit_id = extract_and_normalize_from_commit_url(
            row, "commit_url", self.metadata.name
        )
        if not commit_id:
            match = lookup_broken_commit(row.get("commit_url", ""))
            if not match:
                return None
            project_url, commit_id = match

        if not project_url:
            return None

        return DatasetEntry(
            project_url=project_url,
            commit_id=commit_id,
            src_datasets={self.metadata.name},
            is_vfc=True,
            cve_ids=normalize_cve_ids(row.get("cve_id")),
            cwe_ids=normalize_cwe_ids(row.get("cwe_id")),
        )
