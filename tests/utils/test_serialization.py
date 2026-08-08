"""Tests for JSONL and CSV serialization."""

import json
from pathlib import Path

import pytest

from vfc_datasets.commit_data import CommitData
from vfc_datasets.dataset_entry import DatasetEntry
from vfc_datasets.utils.core.serialization import load_entries, save_entries, save_entries_csv


def _entry(
    commit: str = "abcdef12345",
    diff: str | None = None,
    files: set[str] | None = None,
) -> DatasetEntry:
    return DatasetEntry(
        project_url="https://github.com/owner/repo",
        commit_id=commit,
        src_datasets={"test"},
        commit=CommitData(diff=diff, files_changed=frozenset(files or ())),
    )


class TestSaveAndLoadEntries:
    def test_roundtrip(self, tmp_path: Path) -> None:
        entries = [_entry(), _entry(commit="bcdef123456")]
        path = tmp_path / "test.jsonl"
        save_entries(entries, path)
        loaded = load_entries(path)
        assert len(loaded) == 2
        assert loaded[0].commit_id == "abcdef12345"

    def test_save_empty_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="empty"):
            save_entries([], tmp_path / "test.jsonl")

    def test_load_missing_file_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_entries("/nonexistent/path.jsonl")

    def test_load_skips_invalid_lines(self, tmp_path: Path) -> None:
        path = tmp_path / "test.jsonl"
        valid = _entry()
        path.write_text(
            json.dumps(valid.to_dict()) + "\n" + json.dumps({"commit_id": "abc"}) + "\n"
        )
        loaded = load_entries(path)
        assert len(loaded) == 1

    def test_metadata_header_written(self, tmp_path: Path) -> None:
        entries = [_entry(), _entry(commit="bcdef123456")]
        path = tmp_path / "test.jsonl"
        save_entries(entries, path)
        header = json.loads(path.read_text().splitlines()[0])
        meta = header["_metadata"]
        assert "version" in meta
        assert "created" in meta
        assert meta["entry_count"] == 2

    def test_roundtrip_with_metadata(self, tmp_path: Path) -> None:
        entries = [_entry(), _entry(commit="bcdef123456")]
        path = tmp_path / "test.jsonl"
        save_entries(entries, path)
        loaded = load_entries(path)
        assert len(loaded) == 2
        assert loaded[0].commit_id == "abcdef12345"
        assert loaded[1].commit_id == "bcdef123456"

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        path = tmp_path / "sub" / "dir" / "test.jsonl"
        save_entries([_entry()], path)
        assert path.exists()


class TestSaveEntriesCsv:
    def test_basic_csv(self, tmp_path: Path) -> None:
        path = tmp_path / "test.csv"
        save_entries_csv([_entry()], path)
        assert "project_url" in path.read_text()

    def test_empty_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="empty"):
            save_entries_csv([], tmp_path / "test.csv")

    def test_invalid_field_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="Invalid field"):
            save_entries_csv([_entry()], tmp_path / "test.csv", fields=["nonexistent_field"])

    def test_set_field_semicolon_separated(self, tmp_path: Path) -> None:
        path = tmp_path / "test.csv"
        e = _entry(files={"src/a.py", "src/b.py"})
        save_entries_csv([e], path, fields=["commit.files_changed"])
        content = path.read_text()
        assert "src/a.py;src/b.py" in content
