"""Tests for the include_dataset_commit_data flag and the datasets that ship commit data."""

import inspect
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, override

import pandas as pd
import pytest

import vfc_datasets
from vfc_datasets.base_dataset import BaseDataset, DatasetMetadata
from vfc_datasets.commit_data import CommitData
from vfc_datasets.dataset_entry import DatasetEntry

from ..test_commit_data import DIFF, SHA


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


MESSAGE = "Fix the overflow"
FILES = frozenset({"src/app.c"})
AUTHORED_AT = datetime(2023, 8, 4, 13, 26, 15, tzinfo=UTC)
COMMITTED_AT = datetime(2023, 8, 4, 13, 30, 0, tzinfo=UTC)

GIT_SHOW = (
    f"commit {SHA}\n"
    "Author: A B <a@b.c>\n"
    "Date:   Fri Aug 4 15:26:15 2023 +0200\n"
    "\n"
    f"    {MESSAGE}\n"
    "\n" + DIFF
)


@dataclass(frozen=True)
class ShippedCase:
    """One real dataset's `_shipped_commit_data`, the raw row it reads, and what it yields."""

    dataset: type[BaseDataset]
    row: dict[str, Any] = field(default_factory=dict)
    expected: CommitData = field(default_factory=CommitData)


SHIPPED_CASES = [
    ShippedCase(
        vfc_datasets.CC900Dataset,
        {"message": MESSAGE, "diff": DIFF},
        CommitData(message=MESSAGE, diff=DIFF, files_changed=FILES),
    ),
    ShippedCase(
        vfc_datasets.DiverseVulDataset,
        {"message": MESSAGE},
        CommitData(message=MESSAGE),
    ),
    ShippedCase(
        vfc_datasets.ICVulDataset,
        {"msg": MESSAGE, "author_date": AUTHORED_AT.isoformat()},
        CommitData(message=MESSAGE, authored_at=AUTHORED_AT),
    ),
    ShippedCase(
        vfc_datasets.JavaVFCDataset,
        {"diff_raw": GIT_SHOW, "date": int(COMMITTED_AT.timestamp())},
        CommitData(
            message=MESSAGE,
            diff=DIFF,
            files_changed=FILES,
            authored_at=AUTHORED_AT,
            committed_at=COMMITTED_AT,
        ),
    ),
    ShippedCase(
        vfc_datasets.JavaVFCDatasetExtended,
        {"diff_raw": GIT_SHOW, "date": int(COMMITTED_AT.timestamp())},
        CommitData(
            message=MESSAGE,
            diff=DIFF,
            files_changed=FILES,
            authored_at=AUTHORED_AT,
            committed_at=COMMITTED_AT,
        ),
    ),
    ShippedCase(
        vfc_datasets.PatchDBDataset,
        {"diff_code": DIFF},
        CommitData(diff=DIFF, files_changed=FILES),
    ),
    ShippedCase(
        vfc_datasets.RepoSPDDataset,
        {"diff_code": DIFF},
        CommitData(diff=DIFF, files_changed=FILES),
    ),
    ShippedCase(
        vfc_datasets.SecVulEvalDataset,
        {"commit_id": SHA, "commit_message": MESSAGE},
        CommitData(message=MESSAGE),
    ),
    ShippedCase(
        # `commit_msg` deliberately unused; see `spidb.py`.
        vfc_datasets.SPIDBDataset,
        {"patch": DIFF, "commit_msg": f" {MESSAGE}&&&&&&&&Longer body explaining why.&&&& "},
        CommitData(diff=DIFF, files_changed=FILES),
    ),
]


@pytest.mark.parametrize("case", SHIPPED_CASES, ids=lambda case: case.dataset.metadata.name)
def test_shipped_commit_data_of_real_datasets(case: ShippedCase):
    """Each hook reads its own columns and yields exactly the fields it has."""
    assert case.dataset()._shipped_commit_data(case.row) == case.expected


OTHER_SHA = "e2b7d0e5c9dbb1f0a3f4c5d6e7a8b9c0d1e2f3a4"
BACKPORT_LINES = [
    f"commit {SHA} upstream.",
    f"[ Upstream commit {SHA} ]",
    f"(cherry picked from commit {SHA})",
]


@pytest.mark.parametrize("line", BACKPORT_LINES, ids=["upstream", "bracketed", "cherry-picked"])
def test_secvuleval_drops_a_backports_message(line: str):
    """Naming this row's own commit as the source marks the text as the backport's."""
    dataset = vfc_datasets.SecVulEvalDataset()
    backport = f"{MESSAGE}\n\n{line}\n\nLonger body explaining why."

    assert (
        dataset._shipped_commit_data({"commit_id": SHA, "commit_message": backport}) == CommitData()
    )
    # A different sha means the row is the backport itself, so its message stays.
    other = backport.replace(SHA, OTHER_SHA)
    assert (
        dataset._shipped_commit_data({"commit_id": SHA, "commit_message": other}).message == other
    )


def test_secvuleval_reads_past_a_backport_line_naming_another_commit():
    """`finditer`, not `search`: the first idiom in a message need not be the telling one."""
    dataset = vfc_datasets.SecVulEvalDataset()
    message = f"{MESSAGE}\n\n(cherry picked from commit {OTHER_SHA})\n\ncommit {SHA} upstream."

    assert (
        dataset._shipped_commit_data({"commit_id": SHA, "commit_message": message}) == CommitData()
    )


def test_missing_columns_yield_no_commit_data():
    """A row without the expected columns is empty, never a crash or a half-built value."""
    for case in SHIPPED_CASES:
        assert case.dataset()._shipped_commit_data({}) == CommitData(), case.dataset.metadata.name


def test_every_dataset_shipping_commit_data_is_covered():
    """A new `_shipped_commit_data` override needs a row above, or nothing tests it."""
    overriding = {
        cls
        for name in vfc_datasets.__all__
        if inspect.isclass(cls := getattr(vfc_datasets, name))
        and issubclass(cls, BaseDataset)
        and cls._shipped_commit_data is not BaseDataset._shipped_commit_data
    }

    assert overriding == {case.dataset for case in SHIPPED_CASES}
