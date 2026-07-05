"""Tests for the include_dataset_commit_data flag on BaseDataset."""

from pathlib import Path
from typing import Any, override

import pandas as pd

from vfc_datasets.base_dataset import BaseDataset, DatasetMetadata
from vfc_datasets.dataset_entry import DatasetEntry
from vfc_datasets.transformations.enrichment.commit_data_common import needs_enrichment


class StubShippedDataDataset(BaseDataset):
    """Minimal dataset whose rows ship commit message, diff, and timestamp.

    Caches into a caller-supplied directory so tests never touch the real dataset path.
    """

    metadata = DatasetMetadata(
        name="stub_shipped",
        granularity="commit",
        source_url="https://example.invalid/stub",
        publication_year=2026,
    )

    def __init__(self, dataset_dir: Path, *, include_dataset_commit_data: bool = False) -> None:
        super().__init__(include_dataset_commit_data=include_dataset_commit_data)
        self._tmp_dataset_dir = dataset_dir

    @property
    @override
    def _dataset_dir(self) -> Path:
        return self._tmp_dataset_dir

    @override
    def _load_data(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "commit_id": "abc1234def5678",
                    "message": "fix overflow",
                    "diff": "--- a/x\n+++ b/x",
                    "timestamp": "2024-01-02T03:04:05Z",
                }
            ]
        )

    @override
    def _parse_row(self, row: dict[str, Any]) -> DatasetEntry | None:
        return DatasetEntry(
            project_url="https://github.com/test/repo",
            commit_id=row["commit_id"],
            src_datasets={self.metadata.name},
            commit_message=row.get("message"),
            commit_diff=row.get("diff"),
            commit_timestamp_utc=row.get("timestamp"),
            files_changed={"x"},
        )


def test_shipped_commit_data_stripped_by_default(tmp_path: Path):
    entries = list(StubShippedDataDataset(tmp_path))

    assert len(entries) == 1
    entry = entries[0]
    assert entry.commit_message is None
    assert entry.commit_diff is None
    assert entry.commit_timestamp_utc is None
    # files_changed is entry identity, never stripped
    assert entry.files_changed == {"x"}
    assert needs_enrichment(entry)


def test_shipped_commit_data_kept_when_opted_in(tmp_path: Path):
    entries = list(StubShippedDataDataset(tmp_path, include_dataset_commit_data=True))

    assert len(entries) == 1
    entry = entries[0]
    assert entry.commit_message == "fix overflow"
    assert entry.commit_diff == "--- a/x\n+++ b/x"
    assert entry.commit_timestamp_utc is not None
    assert entry.commit_timestamp_utc.isoformat() == "2024-01-02T03:04:05+00:00"
    assert not needs_enrichment(entry)


def test_cache_key_folds_in_flag(tmp_path: Path):
    stripped = StubShippedDataDataset(tmp_path)
    shipped = StubShippedDataDataset(tmp_path, include_dataset_commit_data=True)

    assert stripped._cache_key().endswith("-d0")
    assert shipped._cache_key().endswith("-d1")
    assert stripped._cache_key() != shipped._cache_key()


def test_flag_survives_a_cache_round_trip(tmp_path: Path):
    """A second parse reads the cache written by the first, per flag value."""

    def first_message(*, include: bool) -> str | None:
        dataset = StubShippedDataDataset(tmp_path, include_dataset_commit_data=include)
        return next(iter(dataset)).commit_message

    # Writes the cache, then reads it back.
    assert first_message(include=False) is None
    assert first_message(include=False) is None

    # Opting in must not be served the stripped cache above.
    assert first_message(include=True) == "fix overflow"
    assert first_message(include=True) == "fix overflow"
