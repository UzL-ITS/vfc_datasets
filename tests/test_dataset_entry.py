"""Tests for DatasetEntry core model."""

from datetime import UTC, datetime, timezone
from typing import Any

import pytest

from vfc_datasets.dataset_entry import DatasetEntry, normalize_commit_timestamp
from vfc_datasets.utils.owasp import OwaspCategory

VALID_KWARGS: dict[str, Any] = {
    "project_url": "https://github.com/owner/repo",
    "commit_id": "abcdef12345",
    "src_datasets": {"test_ds"},
}


class TestDatasetEntryInit:
    def test_valid_entry(self):
        e = DatasetEntry(**VALID_KWARGS)
        assert e.commit_id == "abcdef12345"
        assert e.project_url == "https://github.com/owner/repo"
        assert e.src_datasets == {"test_ds"}
        assert e.is_vfc is True

    def test_url_normalized_to_https(self):
        e = DatasetEntry(
            project_url="git://github.com/Owner/Repo",
            commit_id="abcdef12345",
            src_datasets={"ds"},
        )
        assert e.project_url == "https://github.com/owner/repo"

    def test_invalid_commit_id_raises(self):
        with pytest.raises(ValueError, match="commit_id"):
            DatasetEntry(project_url="https://github.com/o/r", commit_id="", src_datasets={"ds"})

    def test_short_commit_id_raises(self):
        with pytest.raises(ValueError, match="Invalid commit_id"):
            DatasetEntry(project_url="https://github.com/o/r", commit_id="abc", src_datasets={"ds"})

    def test_invalid_url_raises(self):
        with pytest.raises(ValueError, match="Invalid project URL"):
            DatasetEntry(project_url="not-a-url", commit_id="abcdef12345", src_datasets={"ds"})

    def test_empty_src_datasets_raises(self):
        with pytest.raises(ValueError, match="src_datasets must not be empty"):
            DatasetEntry(
                project_url="https://github.com/o/r", commit_id="abcdef12345", src_datasets=set()
            )

    def test_cve_ids_validated(self):
        e = DatasetEntry(**VALID_KWARGS, cve_ids={"CVE-2021-1234", "bad-id"})
        assert e.cve_ids == {"CVE-2021-1234"}

    def test_cwe_ids_validated(self):
        e = DatasetEntry(**VALID_KWARGS, cwe_ids={"CWE-79", "invalid"})
        assert e.cwe_ids == {"CWE-79"}

    def test_owasp_derived_from_cwe(self):
        e = DatasetEntry(**VALID_KWARGS, cwe_ids={"CWE-79"})
        assert e.owasp_categories is not None
        assert OwaspCategory.INJECTION in e.owasp_categories

    def test_owasp_explicit_overrides_derivation(self):
        e = DatasetEntry(
            **VALID_KWARGS,
            cwe_ids={"CWE-79"},
            owasp_categories={OwaspCategory.IDENTIFICATION_AND_AUTHENTICATION_FAILURES},
        )
        assert e.owasp_categories == {OwaspCategory.IDENTIFICATION_AND_AUTHENTICATION_FAILURES}

    def test_owasp_none_when_no_cwes(self):
        e = DatasetEntry(**VALID_KWARGS)
        assert e.owasp_categories is None

    def test_files_changed_defaults_to_empty_set(self):
        e = DatasetEntry(**VALID_KWARGS)
        assert e.files_changed == set()


class TestCommitTimestamp:
    def test_none(self):
        e = DatasetEntry(**VALID_KWARGS, commit_timestamp_utc=None)
        assert e.commit_timestamp_utc is None

    def test_naive_datetime_gets_utc(self):
        dt = datetime(2024, 1, 1, 12, 0, 0)
        e = DatasetEntry(**VALID_KWARGS, commit_timestamp_utc=dt)
        assert e.commit_timestamp_utc is not None
        assert e.commit_timestamp_utc.tzinfo == UTC

    def test_non_utc_tz_converted_to_utc(self):
        plus5 = timezone(offset=__import__("datetime").timedelta(hours=5))
        dt = datetime(2024, 1, 1, 15, 0, 0, tzinfo=plus5)
        e = DatasetEntry(**VALID_KWARGS, commit_timestamp_utc=dt)
        assert e.commit_timestamp_utc is not None
        assert e.commit_timestamp_utc.tzinfo == UTC
        assert e.commit_timestamp_utc.hour == 10


class TestNormalizeCommitTimestamp:
    def test_none(self):
        assert normalize_commit_timestamp(None) is None

    def test_iso_string_parsed(self):
        result = normalize_commit_timestamp("2024-01-15T10:30:00+00:00")
        assert result is not None
        assert result.year == 2024
        assert result.tzinfo == UTC

    def test_naive_datetime_gets_utc(self):
        result = normalize_commit_timestamp(datetime(2024, 1, 1, 12, 0, 0))
        assert result is not None
        assert result.tzinfo == UTC

    def test_non_utc_tz_converted_to_utc(self):
        plus5 = timezone(offset=__import__("datetime").timedelta(hours=5))
        result = normalize_commit_timestamp(datetime(2024, 1, 1, 15, 0, 0, tzinfo=plus5))
        assert result is not None
        assert result.tzinfo == UTC
        assert result.hour == 10


class TestToDict:
    def test_basic_roundtrip(self):
        e = DatasetEntry(**VALID_KWARGS, cve_ids={"CVE-2021-1234"})
        d = e.to_dict()
        assert d["commit_id"] == "abcdef12345"
        assert isinstance(d["cve_ids"], list)
        assert "CVE-2021-1234" in d["cve_ids"]

    def test_timestamp_serialized_as_iso(self):
        e = DatasetEntry(
            **VALID_KWARGS,
            commit_timestamp_utc=datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
        )
        d = e.to_dict()
        assert d["commit_timestamp_utc"].endswith("Z")

    def test_key_is_commit_timestamp_utc(self):
        d = DatasetEntry(**VALID_KWARGS).to_dict()
        assert "commit_timestamp_utc" in d


class TestFromDict:
    def test_lists_converted_to_sets(self):
        data = {
            "project_url": "https://github.com/owner/repo",
            "commit_id": "abcdef12345",
            "src_datasets": ["ds1", "ds2"],
            "cve_ids": ["CVE-2021-0001"],
            "cwe_ids": ["CWE-79"],
            "files_changed": ["src/a.py", "src/b.py"],
        }
        e = DatasetEntry.from_dict(data)
        assert isinstance(e.src_datasets, set)
        assert isinstance(e.cve_ids, set)
        assert isinstance(e.files_changed, set)

    def test_owasp_categories_converted_to_owasp_category_set(self):
        data = {
            "project_url": "https://github.com/owner/repo",
            "commit_id": "abcdef12345",
            "src_datasets": ["ds"],
            "owasp_categories": [1, 3],
        }
        e = DatasetEntry.from_dict(data)
        assert e.owasp_categories == {
            OwaspCategory.BROKEN_ACCESS_CONTROL,
            OwaspCategory.INJECTION,
        }

    def test_timestamp_string_parsed(self):
        data = {
            "project_url": "https://github.com/owner/repo",
            "commit_id": "abcdef12345",
            "src_datasets": ["ds"],
            "commit_timestamp_utc": "2024-01-15T10:30:00Z",
        }
        e = DatasetEntry.from_dict(data)
        assert e.commit_timestamp_utc is not None
        assert e.commit_timestamp_utc.year == 2024
