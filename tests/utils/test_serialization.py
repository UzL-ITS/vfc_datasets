"""Tests for JSONL and CSV serialization."""

import json

import pytest

from vfc_datasets.dataset_entry import DatasetEntry
from vfc_datasets.utils.core.serialization import load_entries, save_entries, save_entries_csv


def _entry(commit="abcdef12345", diff=None, files=None):
    return DatasetEntry(
        project_url="https://github.com/owner/repo",
        commit_id=commit,
        src_datasets={"test"},
        commit_diff=diff,
        files_changed=files,
    )


class TestSaveAndLoadEntries:
    def test_roundtrip(self, tmp_path):
        entries = [_entry(), _entry(commit="bcdef123456")]
        path = tmp_path / "test.jsonl"
        save_entries(entries, path)
        loaded = load_entries(path)
        assert len(loaded) == 2
        assert loaded[0].commit_id == "abcdef12345"

    def test_save_empty_raises(self, tmp_path):
        with pytest.raises(ValueError, match="empty"):
            save_entries([], tmp_path / "test.jsonl")

    def test_load_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            load_entries("/nonexistent/path.jsonl")

    def test_load_skips_invalid_lines(self, tmp_path):
        path = tmp_path / "test.jsonl"
        valid = _entry()
        with open(path, "w") as f:
            json.dump(valid.to_dict(), f)
            f.write("\n")
            # Invalid: missing required fields
            json.dump({"commit_id": "abc"}, f)
            f.write("\n")
        loaded = load_entries(path)
        assert len(loaded) == 1

    def test_creates_parent_directories(self, tmp_path):
        path = tmp_path / "sub" / "dir" / "test.jsonl"
        save_entries([_entry()], path)
        assert path.exists()


class TestSaveEntriesCsv:
    def test_basic_csv(self, tmp_path):
        path = tmp_path / "test.csv"
        save_entries_csv([_entry()], path)
        assert "project_url" in path.read_text()

    def test_empty_raises(self, tmp_path):
        with pytest.raises(ValueError, match="empty"):
            save_entries_csv([], tmp_path / "test.csv")

    def test_invalid_field_raises(self, tmp_path):
        with pytest.raises(ValueError, match="Invalid field"):
            save_entries_csv([_entry()], tmp_path / "test.csv", fields=["nonexistent_field"])

    def test_set_field_semicolon_separated(self, tmp_path):
        path = tmp_path / "test.csv"
        e = _entry(files={"src/a.py", "src/b.py"})
        save_entries_csv([e], path, fields=["files_changed"])
        content = path.read_text()
        assert "src/a.py;src/b.py" in content
