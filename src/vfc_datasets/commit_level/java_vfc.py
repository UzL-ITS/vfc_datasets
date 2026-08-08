import logging
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, override

import pandas as pd

from vfc_datasets.base_dataset import BaseDataset, DatasetMetadata
from vfc_datasets.commit_data import CommitData, from_git_show
from vfc_datasets.config import RAW_DATA_PATH
from vfc_datasets.dataset_entry import DatasetEntry
from vfc_datasets.download_helper import download_file
from vfc_datasets.parsing_helpers import extract_and_normalize_from_commit_url

logger = logging.getLogger(__name__)


def _committer_timestamp(value: object) -> datetime | None:
    """Committer-date epoch seconds; `read_json` may pre-parse it."""
    if isinstance(value, datetime):
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    try:
        return datetime.fromtimestamp(int(value), UTC)  # pyright: ignore[reportArgumentType]
    except (TypeError, ValueError):
        return None


class _JavaVFCBase(BaseDataset):
    _ZENODO_RECORD_ID = "13731781"

    @override
    def _load_data(self) -> pd.DataFrame:
        file_name = f"{self.metadata.name}.jsonl"
        raw_dataset_path = RAW_DATA_PATH / "javavfc" / file_name
        if not raw_dataset_path.exists():
            url = (
                f"https://zenodo.org/records/{self._ZENODO_RECORD_ID}/files/{file_name}?download=1"
            )
            logger.info("Downloading %s...", file_name)
            download_file(url=url, output_path=raw_dataset_path)
        return pd.read_json(raw_dataset_path, lines=True)

    @override
    def _parse_row(self, row: dict[str, Any]) -> DatasetEntry | None:
        project_url, commit_id = extract_and_normalize_from_commit_url(
            row, "commit_link", self.metadata.name
        )
        if not project_url or not commit_id:
            return None

        return DatasetEntry(
            project_url=project_url,
            commit_id=commit_id,
            src_datasets={self.metadata.name},
            is_vfc=True,
        )

    @override
    def _shipped_commit_data(self, row: dict[str, Any]) -> CommitData:
        # `diff_raw` is `git show` output; its header carries the message the flattened
        # `message` column has lost the line breaks from.
        return replace(
            from_git_show(row.get("diff_raw")),
            committed_at=_committer_timestamp(row.get("date")),
        )


class JavaVFCDataset(_JavaVFCBase):
    metadata = DatasetMetadata(
        name="javavfc",
        granularity="commit",
        paper_title="JavaVFC: Java Vulnerability Fixing Commits from Open-source Software",
        paper_url="https://doi.org/10.48550/arXiv.2409.05576",
        source_url="https://doi.org/10.5281/zenodo.13731781",
        publication_year=2024,
        programming_languages=("Java",),
        paper_quotes=(
            "The JAVAVFC dataset, which was manually curated, includes data from 263 projects with a total of 784 unique code commits",
        ),
        projects=263,
        vfcs=784,
        non_vfcs=0,
    )


class JavaVFCDatasetExtended(_JavaVFCBase):
    metadata = DatasetMetadata(
        name="javavfc_extended",
        granularity="commit",
        paper_title="JavaVFC: Java Vulnerability Fixing Commits from Open-source Software",
        paper_url="https://doi.org/10.48550/arXiv.2409.05576",
        source_url="https://doi.org/10.5281/zenodo.13731781",
        publication_year=2024,
        programming_languages=("Java",),
        paper_quotes=(
            "In contrast, the JAVAVFC-EXTENDED dataset was generated using an automated approach, resulting in a much larger collection of 16,837 code commits across 2,532 projects.",
        ),
        projects=2532,
        vfcs=16837,
        non_vfcs=0,
    )
