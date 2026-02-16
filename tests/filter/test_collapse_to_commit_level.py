from datetime import UTC, datetime

from dataset_entry import DatasetEntry
from transformations.filters import collapse_to_commit_level
from utils.owasp import OwaspCategory


class TestCollapseToCommitLevel:
    """Tests for collapse_to_commit_level function."""

    def test_empty_input_returns_empty_list(self):
        assert collapse_to_commit_level([]) == []

    def test_single_entry_clears_function_name(self):
        entry = DatasetEntry(
            project_url="https://github.com/test/repo",
            commit_id="abc123def456",
            src_datasets={"dataset1"},
            function_name="vulnerable_func",
        )

        result = collapse_to_commit_level([entry])

        assert len(result) == 1
        assert result[0].function_name is None
        assert result[0].commit_id == "abc123def456"
        assert result[0].src_datasets == {"dataset1"}

    def test_aggregates_is_vfc_with_or_logic(self):
        entries = [
            DatasetEntry(
                project_url="https://github.com/test/repo",
                commit_id="abc123def456",
                src_datasets={"ds1"},
                is_vfc=False,
                function_name="func1",
            ),
            DatasetEntry(
                project_url="https://github.com/test/repo",
                commit_id="abc123def456",
                src_datasets={"ds2"},
                is_vfc=True,
                function_name="func2",
            ),
            DatasetEntry(
                project_url="https://github.com/test/repo",
                commit_id="abc123def456",
                src_datasets={"ds3"},
                is_vfc=False,
                function_name="func3",
            ),
        ]

        result = collapse_to_commit_level(entries)

        assert len(result) == 1
        assert result[0].is_vfc is True

    def test_unions_set_fields(self):
        entries = [
            DatasetEntry(
                project_url="https://github.com/test/repo",
                commit_id="abc123def456",
                src_datasets={"ds1"},
                cve_ids={"CVE-2021-1111"},
                cwe_ids={"CWE-79"},
                owasp_categories={
                    OwaspCategory.BROKEN_ACCESS_CONTROL,
                    OwaspCategory.CRYPTOGRAPHIC_FAILURES,
                },
                files_changed={"file1.py"},
            ),
            DatasetEntry(
                project_url="https://github.com/test/repo",
                commit_id="abc123def456",
                src_datasets={"ds2"},
                cve_ids={"CVE-2021-2222"},
                cwe_ids={"CWE-89"},
                owasp_categories={OwaspCategory.INJECTION},
                files_changed={"file2.py"},
            ),
        ]

        result = collapse_to_commit_level(entries)

        assert len(result) == 1
        assert result[0].src_datasets == {"ds1", "ds2"}
        assert result[0].cve_ids == {"CVE-2021-1111", "CVE-2021-2222"}
        assert result[0].cwe_ids == {"CWE-79", "CWE-89"}
        assert result[0].owasp_categories == {
            OwaspCategory.BROKEN_ACCESS_CONTROL,
            OwaspCategory.CRYPTOGRAPHIC_FAILURES,
            OwaspCategory.INJECTION,
        }
        assert result[0].files_changed == {"file1.py", "file2.py"}

    def test_takes_first_non_none_for_scalar_fields(self):
        ts = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)

        entries = [
            DatasetEntry(
                project_url="https://github.com/test/repo",
                commit_id="abc123def456",
                src_datasets={"ds1"},
                commit_message=None,
                commit_diff=None,
                ghsa_id=None,
                commit_timestamp_utc=None,
            ),
            DatasetEntry(
                project_url="https://github.com/test/repo",
                commit_id="abc123def456",
                src_datasets={"ds2"},
                commit_message="Fix vulnerability",
                commit_diff="diff --git...",
                ghsa_id="GHSA-xxxx-yyyy",
                commit_timestamp_utc=ts,
            ),
            DatasetEntry(
                project_url="https://github.com/test/repo",
                commit_id="abc123def456",
                src_datasets={"ds3"},
                commit_message="ignored message",
                commit_diff="ignored diff",
                ghsa_id="GHSA-ignored",
                commit_timestamp_utc=datetime(2025, 1, 1, tzinfo=UTC),
            ),
        ]

        result = collapse_to_commit_level(entries)

        assert len(result) == 1
        assert result[0].commit_message == "Fix vulnerability"
        assert result[0].commit_diff == "diff --git..."
        assert result[0].ghsa_id == "GHSA-xxxx-yyyy"
        assert result[0].commit_timestamp_utc == ts

    def test_different_commits_stay_separate(self):
        entries = [
            DatasetEntry(
                project_url="https://github.com/test/repo",
                commit_id="aaa111bbb222",
                src_datasets={"ds1"},
            ),
            DatasetEntry(
                project_url="https://github.com/test/repo",
                commit_id="ccc333ddd444",
                src_datasets={"ds2"},
            ),
        ]

        result = collapse_to_commit_level(entries)

        assert len(result) == 2
        commit_ids = {e.commit_id for e in result}
        assert commit_ids == {"aaa111bbb222", "ccc333ddd444"}

    def test_different_projects_stay_separate(self):
        entries = [
            DatasetEntry(
                project_url="https://github.com/test/repo1",
                commit_id="abc123def456",
                src_datasets={"ds1"},
            ),
            DatasetEntry(
                project_url="https://github.com/test/repo2",
                commit_id="abc123def456",
                src_datasets={"ds2"},
            ),
        ]

        result = collapse_to_commit_level(entries)

        assert len(result) == 2
        urls = {e.project_url for e in result}
        assert urls == {
            "https://github.com/test/repo1",
            "https://github.com/test/repo2",
        }

    def test_empty_owasp_categories_becomes_none(self):
        """Empty owasp_categories should become None (triggers CWE derivation)."""
        entry = DatasetEntry(
            project_url="https://github.com/test/repo",
            commit_id="abc123def456",
            src_datasets={"ds1"},
            owasp_categories=None,
        )

        result = collapse_to_commit_level([entry])

        assert len(result) == 1
        assert result[0].owasp_categories is None

    def test_files_changed_is_always_set(self):
        """files_changed is normalized to set by DatasetEntry, never None."""
        entry = DatasetEntry(
            project_url="https://github.com/test/repo",
            commit_id="abc123def456",
            src_datasets={"ds1"},
            files_changed=None,
        )

        result = collapse_to_commit_level([entry])

        assert len(result) == 1
        assert result[0].files_changed == set()
