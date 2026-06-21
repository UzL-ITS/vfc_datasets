import json
import logging
import re
from typing import Any, override

import pandas as pd

from vfc_datasets.base_dataset import BaseDataset, DatasetMetadata
from vfc_datasets.dataset_entry import DatasetEntry
from vfc_datasets.download_helper import download_and_extract_zip
from vfc_datasets.parsing_helpers import extract_and_normalize_from_commit_url

logger = logging.getLogger(__name__)


def _normalize_url(url: str) -> str:
    if not url.startswith(("http://", "https://")):
        return f"https://{url}"
    return url


class _FixSeekerBase(BaseDataset):
    _file_glob: str

    @override
    def _load_data(self) -> pd.DataFrame:
        raw_dir = download_and_extract_zip(self.metadata.source_url, self._raw_dir / "fixseeker")
        json_files = sorted(raw_dir.rglob(self._file_glob))
        if not json_files:
            raise RuntimeError(f"No files matching {self._file_glob} in {raw_dir}")

        rows: list[dict[str, Any]] = []
        for path in json_files:
            logger.info("Loading %s", path.name)
            with open(path) as f:
                raw = f.read()
            # Fix trailing commas (invalid JSON present in source data)
            data = json.loads(re.sub(r",\s*([}\]])", r"\1", raw))
            for url in data.get("vul", []):
                rows.append({"commit_url": _normalize_url(url), "vulnerability": 1})
            for url in data.get("nonvul", []):
                rows.append({"commit_url": _normalize_url(url), "vulnerability": 0})

        return pd.DataFrame(rows)

    @override
    def _parse_row(self, row: dict[str, Any]) -> DatasetEntry | None:
        project_url, commit_id = extract_and_normalize_from_commit_url(
            row, "commit_url", self.metadata.name
        )
        if not project_url or not commit_id:
            return None

        return DatasetEntry(
            project_url=project_url,
            commit_id=commit_id,
            src_datasets={self.metadata.name},
            is_vfc=row.get("vulnerability") == 1,
        )


class FixSeekerBalancedDataset(_FixSeekerBase):
    metadata = DatasetMetadata(
        name="fixseeker_balanced",
        granularity="commit",
        paper_title="Fixseeker: An Empirical Driven Graph-based Approach for Detecting Silent Vulnerability Fixes in Open Source Software",
        paper_url="https://doi.org/10.48550/arXiv.2503.20265",
        source_url="https://drive.google.com/file/d/1TUsX9KQ6mm42VeAMZ4A8arThtm8FLW9Y/view?usp=drive_link",
        publication_year=2025,
        programming_languages=("C", "C++", "Java", "Python", "PHP"),
        paper_quotes=(
            "Our datasets cover four programming languages: C/C++, Java, Python, and PHP, "
            "with a total of 10,258 VFCs across 2,094 open-source projects.",
        ),
        vfcs=9885,
        non_vfcs=10979,
        projects=2094,
    )

    _file_glob = "*_balance.json"


class FixSeekerImbalancedDataset(_FixSeekerBase):
    metadata = DatasetMetadata(
        name="fixseeker_imbalanced",
        granularity="commit",
        paper_title="Fixseeker: An Empirical Driven Graph-based Approach for Detecting Silent Vulnerability Fixes in Open Source Software",
        paper_url="https://doi.org/10.48550/arXiv.2503.20265",
        source_url="https://drive.google.com/file/d/1TUsX9KQ6mm42VeAMZ4A8arThtm8FLW9Y/view?usp=drive_link",
        publication_year=2025,
        programming_languages=("C", "C++", "Java", "Python", "PHP"),
        paper_quotes=(
            "Our datasets cover four programming languages: C/C++, Java, Python, and PHP, "
            "with a total of 10,258 VFCs across 2,094 open-source projects.",
        ),
        vfcs=9884,
        non_vfcs=499150,
        projects=2094,
    )

    _file_glob = "*_imbalance.json"
