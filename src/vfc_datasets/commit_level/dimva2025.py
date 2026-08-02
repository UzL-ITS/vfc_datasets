import logging
from typing import Any, override

import pandas as pd

from vfc_datasets.base_dataset import BaseDataset, DatasetMetadata
from vfc_datasets.config import RAW_DATA_PATH
from vfc_datasets.dataset_entry import DatasetEntry
from vfc_datasets.download_helper import download_file
from vfc_datasets.parsing_helpers import extract_url_and_commit, normalize_cve_ids

logger = logging.getLogger(__name__)

_FILES: tuple[tuple[str, str, str], ...] = (
    (
        "https://ndownloader.figshare.com/files/52479353",
        "single-multi.csv",
        "ecd2b65634488734924db10576abd0796f4320906cada656dd4ac15736d80349",
    ),
    (
        "https://ndownloader.figshare.com/files/52481675",
        "multi-multi.csv",
        "76bf02ae60cdec2623599cf29f87c0ea7a9ded3dc08a2c54b83513ad0bb6d022",
    ),
)


class DIMVA2025Dataset(BaseDataset):
    metadata = DatasetMetadata(
        name="dimva2025",
        granularity="commit",
        paper_title="An Empirical Study of Multi-language Security Patches in Open Source Software",
        paper_url="https://doi.org/10.1007/978-3-031-97623-0_8",
        source_url="https://doi.org/10.6084/m9.figshare.28447463",
        publication_year=2025,
        paper_quotes=(
            # Abstract
            "We first collect a large-scale dataset of multi-language security patches "
            "from the MITRE corporation.",
            # Figshare description
            "The multi-language security patch dataset contains 1253 multi-file multi-language "
            "security patches and 1545 single-file multi-language security patches from MITRE. "
            "They have been stored in two CSV files respectively. The multi-multi.csv stores the "
            "metadata and the fixing pattern of each multi-file multi-language security patch. "
            "The single-multi.csv stores the metadata and the embedded language of each "
            "single-file multi-language security patch.",
        ),
        vfcs=2798,  # 1253 multi-file + 1545 single-file patches
        non_vfcs=0,
        projects=1246,
    )

    @override
    def _load_data(self) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        for url, filename, checksum in _FILES:
            path = download_file(url, RAW_DATA_PATH / filename, checksum=checksum)
            df = pd.read_csv(path)
            for record in df.to_dict(orient="records"):
                owner, repo = record.get("Owner"), record.get("Repo")
                if not isinstance(owner, str) or not isinstance(repo, str):
                    continue
                rows.append(
                    {
                        "project_url": f"https://github.com/{owner}/{repo}",
                        "commit_id": record.get("Commit_ID"),
                        "cve_id": record.get("CVE_ID"),
                    }
                )
        return pd.DataFrame(rows)

    @override
    def _parse_row(self, row: dict[str, Any]) -> DatasetEntry | None:
        project_url, commit_id = extract_url_and_commit(
            row, "project_url", "commit_id", self.metadata.name
        )
        if not project_url or not commit_id:
            return None

        return DatasetEntry(
            project_url=project_url,
            commit_id=commit_id,
            src_datasets={self.metadata.name},
            is_vfc=True,
            cve_ids=normalize_cve_ids(row.get("cve_id")),
        )
