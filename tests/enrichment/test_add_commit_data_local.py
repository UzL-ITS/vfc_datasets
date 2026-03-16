"""Tests for add_commit_data_local module."""

from datetime import UTC, datetime

import pytest

from dataset_entry import DatasetEntry
from transformations.enrichment.add_commit_data_local import (
    _get_commit_info,
    add_commit_information_local,
)
from transformations.enrichment.commit_data_common import CommitData, apply_commit_data


class TestApplyCommitData:
    """Tests for apply_commit_data helper."""

    def test_updates_all_empty_fields(self):
        entry = DatasetEntry(
            project_url="https://github.com/test/repo",
            commit_id="abc1234",
            src_datasets={"test"},
        )
        data = CommitData(
            message="Fix bug",
            timestamp="2024-01-15T10:30:00+00:00",
            diff="diff --git a/file.py",
            files_changed={"file.py", "test.py"},
        )

        apply_commit_data(entry, data)

        assert entry.commit_message == "Fix bug"
        assert entry.commit_timestamp_utc == datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
        assert entry.commit_diff == "diff --git a/file.py"
        assert entry.files_changed == {"file.py", "test.py"}

    def test_does_not_overwrite_existing_fields(self):
        entry = DatasetEntry(
            project_url="https://github.com/test/repo",
            commit_id="abc1234",
            src_datasets={"test"},
            commit_message="Original message",
            commit_timestamp_utc="2023-06-01T12:00:00+00:00",
            commit_diff="original diff",
            files_changed={"original.py"},
        )
        data = CommitData(
            message="New message",
            timestamp="2024-01-15T10:30:00+00:00",
            diff="new diff",
            files_changed={"new.py"},
        )

        apply_commit_data(entry, data)

        assert entry.commit_message == "Original message"
        assert entry.commit_timestamp_utc == datetime(2023, 6, 1, 12, 0, 0, tzinfo=UTC)
        assert entry.commit_diff == "original diff"
        assert entry.files_changed == {"original.py"}

    def test_partial_update_message_exists(self):
        entry = DatasetEntry(
            project_url="https://github.com/test/repo",
            commit_id="abc1234",
            src_datasets={"test"},
            commit_message="Existing message",
        )
        data = CommitData(
            message="New message",
            timestamp="2024-01-15T10:30:00+00:00",
            diff="new diff",
            files_changed={"new.py"},
        )

        apply_commit_data(entry, data)

        assert entry.commit_message == "Existing message"  # Not overwritten
        assert entry.commit_timestamp_utc == datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
        assert entry.commit_diff == "new diff"
        assert entry.files_changed == {"new.py"}

    def test_partial_update_diff_exists(self):
        entry = DatasetEntry(
            project_url="https://github.com/test/repo",
            commit_id="abc1234",
            src_datasets={"test"},
            commit_diff="Existing diff",
        )
        data = CommitData(
            message="New message",
            timestamp="2024-01-15T10:30:00+00:00",
            diff="new diff",
            files_changed={"new.py"},
        )

        apply_commit_data(entry, data)

        assert entry.commit_message == "New message"
        assert entry.commit_diff == "Existing diff"  # Not overwritten

    def test_empty_files_changed_is_updated(self):
        """Empty set for files_changed should be treated as needing update."""
        entry = DatasetEntry(
            project_url="https://github.com/test/repo",
            commit_id="abc1234",
            src_datasets={"test"},
            files_changed=set(),  # Empty set
        )
        data = CommitData(
            message="msg",
            timestamp="2024-01-15T10:30:00+00:00",
            diff="diff",
            files_changed={"file.py"},
        )

        apply_commit_data(entry, data)

        assert entry.files_changed == {"file.py"}

    def test_non_empty_files_changed_not_overwritten(self):
        entry = DatasetEntry(
            project_url="https://github.com/test/repo",
            commit_id="abc1234",
            src_datasets={"test"},
            files_changed={"existing.py"},
        )
        data = CommitData(
            message="msg",
            timestamp="2024-01-15T10:30:00+00:00",
            diff="diff",
            files_changed={"new.py"},
        )

        apply_commit_data(entry, data)

        assert entry.files_changed == {"existing.py"}  # Not overwritten


class TestAddCommitInformationLocal:
    """Tests for add_commit_information_local main function."""

    def test_returns_entries_when_all_have_commit_info(self):
        entries = [
            DatasetEntry(
                project_url="https://github.com/test/repo",
                commit_id="abc1234",
                src_datasets={"test"},
                commit_message="msg",
                commit_diff="diff",
                commit_timestamp_utc="2024-01-15T10:30:00+00:00",
                files_changed={"file.py"},
            ),
        ]

        result = add_commit_information_local(entries)

        assert result is entries
        assert len(result) == 1
        # Verify nothing changed
        assert result[0].commit_message == "msg"
        assert result[0].commit_diff == "diff"

    def test_returns_empty_list_unchanged(self):
        entries: list[DatasetEntry] = []
        result = add_commit_information_local(entries)
        assert result == []


class TestGetCommitInfo:
    """Tests for _get_commit_info - verifies files_changed works for all commits."""

    @pytest.fixture
    def curl_repo(self):
        """Get curl repo (clone if needed)."""
        from utils.git.repository import clone_repository

        repo = clone_repository("https://github.com/curl/curl")
        assert repo is not None
        yield repo
        repo.close()

    @pytest.mark.integration
    @pytest.mark.slow
    def test_commit_with_parents_has_files_changed(self, curl_repo):
        """Commit with parents should have files_changed populated."""
        result = _get_commit_info(
            curl_repo, "79e63a53bb9598af863b0afe49ad662795faeef4", max_diff_size=256 * 1024
        )

        assert result is not None
        assert result["files_changed"]

    @pytest.mark.integration
    @pytest.mark.slow
    def test_root_commit_has_files_changed(self, curl_repo):
        """Root commit (no parents) should also have files_changed populated."""
        root_commit = curl_repo.git.rev_list("--max-parents=0", "HEAD").strip().split("\n")[0]
        result = _get_commit_info(curl_repo, root_commit, max_diff_size=256 * 1024)

        assert result is not None
        assert result["files_changed"]


class TestAddCommitInformationLocalIntegration:
    """Integration tests for add_commit_information_local."""

    CURL_PROJECT_URL = "https://github.com/curl/curl"
    # Known stable commits from curl repository
    CURL_COMMIT = "79e63a53bb9598af863b0afe49ad662795faeef4"  # curl-7_50_0 tag
    CURL_COMMIT_2 = "dac98ccfa27a392edd946227483bfac8f466219a"  # mqtt: better too-big-message-check
    CURL_EXPECTED_DATE = datetime(2016, 7, 21, 8, 53, 38, tzinfo=UTC)
    CURL_EXPECTED_MESSAGE = "RELEASE-NOTES: version 7.50.0 ready"

    @pytest.mark.integration
    @pytest.mark.slow
    def test_enriches_entry_from_real_repo(self):
        """Test enrichment using a real git repository."""
        entry = DatasetEntry(
            project_url=self.CURL_PROJECT_URL,
            commit_id=self.CURL_COMMIT,
            src_datasets={"test"},
        )

        result = add_commit_information_local([entry])

        assert len(result) == 1
        assert result[0].commit_message is not None
        assert self.CURL_EXPECTED_MESSAGE in result[0].commit_message
        assert result[0].commit_timestamp_utc == self.CURL_EXPECTED_DATE
        assert result[0].files_changed  # Should have files

    @pytest.mark.integration
    @pytest.mark.slow
    def test_multiple_entries_same_repo(self):
        """Test enriching multiple commits from the same repository."""
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

        result = add_commit_information_local(entries)

        assert len(result) == 2
        for entry in result:
            assert entry.commit_message is not None
            assert entry.commit_timestamp_utc is not None

    @pytest.mark.integration
    @pytest.mark.slow
    def test_preserves_existing_data(self):
        """Existing commit data should not be overwritten."""
        original_message = "Original message preserved"
        entry = DatasetEntry(
            project_url=self.CURL_PROJECT_URL,
            commit_id=self.CURL_COMMIT,
            src_datasets={"test"},
            commit_message=original_message,
        )

        result = add_commit_information_local([entry])

        assert len(result) == 1
        assert result[0].commit_message == original_message  # Preserved
        assert result[0].commit_timestamp_utc is not None  # Still enriched

    @pytest.mark.integration
    @pytest.mark.slow
    def test_handles_invalid_commit(self):
        """Invalid commits should not crash the process."""
        entries = [
            DatasetEntry(
                project_url=self.CURL_PROJECT_URL,
                commit_id=self.CURL_COMMIT,
                src_datasets={"test"},
            ),
            DatasetEntry(
                project_url=self.CURL_PROJECT_URL,
                commit_id="0000000000000000000000000000000000000000",
                src_datasets={"test"},
            ),
        ]

        result = add_commit_information_local(entries)

        assert len(result) == 2
        # Valid commit should be enriched
        assert result[0].commit_message is not None
        # Invalid commit should not crash, just not be enriched
        assert result[1].commit_message is None

    @pytest.mark.integration
    @pytest.mark.slow
    def test_duplicate_entries_same_commit(self):
        """Multiple entries for the same commit should all be enriched."""
        entries = [
            DatasetEntry(
                project_url=self.CURL_PROJECT_URL,
                commit_id=self.CURL_COMMIT,
                src_datasets={"dataset1"},
            ),
            DatasetEntry(
                project_url=self.CURL_PROJECT_URL,
                commit_id=self.CURL_COMMIT,
                src_datasets={"dataset2"},
            ),
        ]

        result = add_commit_information_local(entries)

        assert len(result) == 2
        # Both entries should have the same commit data
        assert result[0].commit_message == result[1].commit_message
        assert result[0].commit_timestamp_utc == result[1].commit_timestamp_utc
