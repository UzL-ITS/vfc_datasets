"""Tests for add_commit_data_api module."""

import pytest

from dataset_entry import DatasetEntry
from transformations.enrichment.add_commit_data_api import (
    _apply_api_response,
    add_commit_information_api,
)


class TestApplyApiResponse:
    """Tests for _apply_api_response helper."""

    def test_populates_all_fields_from_api_response(self):
        entry = DatasetEntry(
            project_url="https://github.com/test/repo",
            commit_id="abc1234",
            src_datasets={"test"},
        )
        api_data = {
            "commit": {
                "message": "Fix security vulnerability\n\nDetailed description.",
                "author": {"date": "2024-01-15T10:30:00Z"},
            },
            "files": [
                {"filename": "src/auth.py", "patch": "@@ -1,3 +1,5 @@\n+new line"},
                {"filename": "tests/test_auth.py", "patch": "@@ -10,2 +10,4 @@\n+test"},
            ],
        }

        _apply_api_response(entry, api_data)

        assert entry.commit_message == "Fix security vulnerability\n\nDetailed description."
        assert entry.commit_timestamp_utc is not None
        assert entry.files_changed == {"src/auth.py", "tests/test_auth.py"}
        assert entry.commit_diff is not None
        assert "@@ -1,3 +1,5 @@" in entry.commit_diff
        assert "@@ -10,2 +10,4 @@" in entry.commit_diff

    def test_handles_empty_files_list(self):
        entry = DatasetEntry(
            project_url="https://github.com/test/repo",
            commit_id="abc1234",
            src_datasets={"test"},
        )
        api_data = {
            "commit": {
                "message": "Merge commit",
                "author": {"date": "2024-01-15T10:30:00Z"},
            },
            "files": [],
        }

        _apply_api_response(entry, api_data)

        assert entry.commit_message == "Merge commit"
        assert entry.files_changed == set()
        assert entry.commit_diff is None

    def test_handles_files_without_patches(self):
        """Binary files may not have patches."""
        entry = DatasetEntry(
            project_url="https://github.com/test/repo",
            commit_id="abc1234",
            src_datasets={"test"},
        )
        api_data = {
            "commit": {
                "message": "Add image",
                "author": {"date": "2024-01-15T10:30:00Z"},
            },
            "files": [
                {"filename": "image.png"},  # No patch field
                {"filename": "src/main.py", "patch": "@@ -1 +1 @@\n-old\n+new"},
            ],
        }

        _apply_api_response(entry, api_data)

        assert entry.files_changed == {"image.png", "src/main.py"}
        assert entry.commit_diff == "@@ -1 +1 @@\n-old\n+new"

    def test_handles_missing_author_date(self):
        entry = DatasetEntry(
            project_url="https://github.com/test/repo",
            commit_id="abc1234",
            src_datasets={"test"},
        )
        api_data = {
            "commit": {
                "message": "Commit",
                "author": {},
            },
            "files": [],
        }

        _apply_api_response(entry, api_data)

        assert entry.commit_message == "Commit"
        assert entry.commit_timestamp_utc is None

    def test_handles_missing_commit_section(self):
        entry = DatasetEntry(
            project_url="https://github.com/test/repo",
            commit_id="abc1234",
            src_datasets={"test"},
        )
        api_data: dict[str, list[str]] = {"files": []}

        _apply_api_response(entry, api_data)

        assert entry.commit_message is None
        assert entry.commit_timestamp_utc is None

    def test_handles_no_files_key(self):
        entry = DatasetEntry(
            project_url="https://github.com/test/repo",
            commit_id="abc1234",
            src_datasets={"test"},
        )
        api_data = {
            "commit": {
                "message": "No files",
                "author": {"date": "2024-01-15T10:30:00Z"},
            },
        }

        _apply_api_response(entry, api_data)

        assert entry.commit_message == "No files"
        assert entry.files_changed == set()

    def test_multiple_patches_joined_with_newline(self):
        entry = DatasetEntry(
            project_url="https://github.com/test/repo",
            commit_id="abc1234",
            src_datasets={"test"},
        )
        api_data = {
            "commit": {"message": "msg", "author": {}},
            "files": [
                {"filename": "a.py", "patch": "patch1"},
                {"filename": "b.py", "patch": "patch2"},
                {"filename": "c.py", "patch": "patch3"},
            ],
        }

        _apply_api_response(entry, api_data)

        assert entry.commit_diff == "patch1\npatch2\npatch3"

    def test_files_without_filename_ignored(self):
        entry = DatasetEntry(
            project_url="https://github.com/test/repo",
            commit_id="abc1234",
            src_datasets={"test"},
        )
        api_data = {
            "commit": {"message": "msg", "author": {}},
            "files": [
                {"filename": "valid.py"},
                {},  # Missing filename
                {"filename": ""},  # Empty filename
            ],
        }

        _apply_api_response(entry, api_data)

        assert entry.files_changed == {"valid.py"}


class TestAddCommitInformationApi:
    """Tests for add_commit_information_api main function."""

    def test_returns_entries_when_all_complete(self):
        """Entries with both message and diff should not be processed."""
        entries = [
            DatasetEntry(
                project_url="https://github.com/test/repo",
                commit_id="abc1234",
                src_datasets={"test"},
                commit_message="Already has message",
                commit_diff="Already has diff",
            ),
        ]

        result = add_commit_information_api(entries)

        assert result is entries
        assert result[0].commit_message == "Already has message"
        assert result[0].commit_diff == "Already has diff"

    def test_returns_empty_list_unchanged(self):
        entries: list[DatasetEntry] = []
        result = add_commit_information_api(entries)
        assert result == []

    def test_multiple_complete_entries_skipped(self):
        """Multiple complete entries should all be skipped."""
        entries = [
            DatasetEntry(
                project_url="https://github.com/test/repo1",
                commit_id="abc1234",
                src_datasets={"test"},
                commit_message="msg1",
                commit_diff="diff1",
            ),
            DatasetEntry(
                project_url="https://github.com/test/repo2",
                commit_id="def5678",
                src_datasets={"test"},
                commit_message="msg2",
                commit_diff="diff2",
            ),
        ]

        result = add_commit_information_api(entries)

        assert result is entries
        assert len(result) == 2


class TestAddCommitInformationApiIntegration:
    """Integration tests for add_commit_information_api."""

    CURL_PROJECT_URL = "https://github.com/curl/curl"
    # Known stable commits from curl repository
    CURL_COMMIT = "79e63a53bb9598af863b0afe49ad662795faeef4"  # curl-7_50_0 tag
    CURL_COMMIT_2 = "dac98ccfa27a392edd946227483bfac8f466219a"  # mqtt: better too-big-message-check

    @pytest.mark.integration
    def test_enriches_entry_from_github_api(self):
        """Test enrichment using real GitHub API."""
        entry = DatasetEntry(
            project_url=self.CURL_PROJECT_URL,
            commit_id=self.CURL_COMMIT,
            src_datasets={"test"},
        )

        result = add_commit_information_api([entry])

        assert len(result) == 1
        assert result[0].commit_message is not None
        assert len(result[0].commit_message) > 0
        assert result[0].commit_timestamp_utc is not None

    @pytest.mark.integration
    def test_handles_nonexistent_commit(self):
        """API should handle 404 gracefully."""
        entry = DatasetEntry(
            project_url=self.CURL_PROJECT_URL,
            commit_id="0000000000000000000000000000000000000000",
            src_datasets={"test"},
        )

        result = add_commit_information_api([entry])

        assert len(result) == 1
        # Entry should still exist but not be enriched
        assert result[0].commit_message is None

    @pytest.mark.integration
    def test_skips_non_github_urls(self):
        """Non-GitHub URLs should be skipped gracefully."""
        entry = DatasetEntry(
            project_url="https://gitlab.com/example/project",
            commit_id="abc1234",
            src_datasets={"test"},
        )

        result = add_commit_information_api([entry])

        assert len(result) == 1
        assert result[0].commit_message is None

    @pytest.mark.integration
    def test_mixed_github_and_non_github(self):
        """Should process GitHub URLs and skip others."""
        entries = [
            DatasetEntry(
                project_url=self.CURL_PROJECT_URL,
                commit_id=self.CURL_COMMIT,
                src_datasets={"test"},
            ),
            DatasetEntry(
                project_url="https://gitlab.com/example/project",
                commit_id="abc1234",
                src_datasets={"test"},
            ),
        ]

        result = add_commit_information_api(entries)

        assert len(result) == 2
        assert result[0].commit_message is not None  # GitHub - enriched
        assert result[1].commit_message is None  # GitLab - skipped

    @pytest.mark.integration
    def test_preserves_existing_data(self):
        """Entries with existing data should have new fields added."""
        entry = DatasetEntry(
            project_url=self.CURL_PROJECT_URL,
            commit_id=self.CURL_COMMIT,
            src_datasets={"test"},
            # Note: _populate_entry overwrites, but entry only goes to API
            # if it's missing message AND diff
        )

        result = add_commit_information_api([entry])

        assert len(result) == 1
        assert result[0].commit_message is not None
        assert result[0].files_changed  # Should have files

    @pytest.mark.integration
    def test_multiple_entries_same_repo(self):
        """Multiple entries from same repo should all be enriched."""
        entries = [
            DatasetEntry(
                project_url=self.CURL_PROJECT_URL,
                commit_id=self.CURL_COMMIT,
                src_datasets={"test"},
            ),
            DatasetEntry(
                project_url=self.CURL_PROJECT_URL,
                commit_id=self.CURL_COMMIT_2,
                src_datasets={"test"},
            ),
        ]

        result = add_commit_information_api(entries)

        assert len(result) == 2
        for entry in result:
            assert entry.commit_message is not None
            assert entry.commit_timestamp_utc is not None
