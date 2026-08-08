"""Tests for the include_dataset_commit_data flag on BaseDataset."""

from pathlib import Path
from typing import Any, override

import pandas as pd

from vfc_datasets.base_dataset import BaseDataset, DatasetMetadata
from vfc_datasets.commit_data import CommitData
from vfc_datasets.dataset_entry import DatasetEntry


class StubShippedDataDataset(BaseDataset):
    """Minimal dataset whose rows ship commit message, diff, timestamp, and files.

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
        )

    @override
    def _shipped_commit_data(self, row: dict[str, Any]) -> CommitData:
        return CommitData(
            message=row.get("message"),
            diff=row.get("diff"),
            authored_at=row.get("timestamp"),
            committed_at=row.get("timestamp"),
            files_changed=frozenset({"x"}),
        )


class StubIdentityFilesDataset(StubShippedDataDataset):
    """Function-level shape: the function's file is identity, set by `_parse_row`."""

    metadata = DatasetMetadata(
        name="stub_identity_files",
        granularity="function",
        source_url="https://example.invalid/stub",
        publication_year=2026,
    )

    @override
    def _parse_row(self, row: dict[str, Any]) -> DatasetEntry | None:
        return DatasetEntry(
            project_url="https://github.com/test/repo",
            commit_id=row["commit_id"],
            src_datasets={self.metadata.name},
            function_name="do_thing",
            function_file="identity.c",
        )


def test_shipped_commit_data_stripped_by_default(tmp_path: Path):
    entries = list(StubShippedDataDataset(tmp_path))

    assert len(entries) == 1
    entry = entries[0]
    assert entry.commit.message is None
    assert entry.commit.diff is None
    assert entry.commit.committed_at is None
    # Commit file lists are commit data, so they are gated by the flag too.
    assert entry.commit.files_changed == frozenset()
    assert not entry.commit.is_complete()


def test_shipped_commit_data_kept_when_opted_in(tmp_path: Path):
    entries = list(StubShippedDataDataset(tmp_path, include_dataset_commit_data=True))

    assert len(entries) == 1
    entry = entries[0]
    assert entry.commit.message == "fix overflow"
    assert entry.commit.diff == "--- a/x\n+++ b/x"
    assert entry.commit.committed_at is not None
    assert entry.commit.committed_at.isoformat() == "2024-01-02T03:04:05+00:00"
    assert entry.commit.files_changed == {"x"}
    assert entry.commit.is_complete()


def test_function_file_survives_the_flag(tmp_path: Path):
    """`function_file` is identity and is never gated by the flag."""
    assert next(iter(StubIdentityFilesDataset(tmp_path))).function_file == "identity.c"


def test_function_file_and_commit_files_are_independent(tmp_path: Path):
    dataset = StubIdentityFilesDataset(tmp_path, include_dataset_commit_data=True)
    entry = next(iter(dataset))

    assert entry.function_file == "identity.c"
    assert entry.commit.files_changed == {"x"}
    assert entry.commit.message == "fix overflow"


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
        return next(iter(dataset)).commit.message

    # Writes the cache, then reads it back.
    assert first_message(include=False) is None
    assert first_message(include=False) is None

    # Opting in must not be served the stripped cache above.
    assert first_message(include=True) == "fix overflow"
    assert first_message(include=True) == "fix overflow"
