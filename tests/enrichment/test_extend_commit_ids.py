# Integration tests against curl/curl repository (real API calls and git operations).

import pytest

from vfc_datasets.dataset_entry import DatasetEntry
from vfc_datasets.transformations.enrichment.commit_id_enrichment import (
    _extend_commit_id_api_async,
    extend_commit_ids_api,
    extend_commit_ids_local,
)
from vfc_datasets.utils.git.github_client import AsyncGitHubClient

# Known stable commit from curl/curl repository (curl-7_50_0 tag)
# This commit is stable and will never change, making it ideal for testing
CURL_SHORT_COMMIT = "79e63a53"
CURL_FULL_COMMIT = "79e63a53bb9598af863b0afe49ad662795faeef4"
CURL_PROJECT_URL = "https://github.com/curl/curl"


class TestExtendCommitIdApiAsync:
    """Test async API-based commit ID extension."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_extends_short_commit_to_full(self):
        entry = DatasetEntry(
            project_url=CURL_PROJECT_URL,
            commit_id=CURL_SHORT_COMMIT,
            src_datasets={"test"},
        )

        async with AsyncGitHubClient() as client:
            result_entry, extended_id, was_updated = await _extend_commit_id_api_async(
                entry, client
            )

        assert was_updated is True
        assert extended_id == CURL_FULL_COMMIT
        assert result_entry is entry  # Same object returned

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_full_commit_unchanged(self):
        entry = DatasetEntry(
            project_url=CURL_PROJECT_URL,
            commit_id=CURL_FULL_COMMIT,
            src_datasets={"test"},
        )

        async with AsyncGitHubClient() as client:
            _, extended_id, was_updated = await _extend_commit_id_api_async(entry, client)

        assert was_updated is False
        assert extended_id == CURL_FULL_COMMIT

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_non_github_url_unchanged(self):
        entry = DatasetEntry(
            project_url="https://gitlab.com/example/project",
            commit_id="abc1234",
            src_datasets={"test"},
        )

        async with AsyncGitHubClient() as client:
            _, extended_id, was_updated = await _extend_commit_id_api_async(entry, client)

        assert was_updated is False
        assert extended_id == "abc1234"

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_nonexistent_commit_unchanged(self):
        entry = DatasetEntry(
            project_url=CURL_PROJECT_URL,
            commit_id="0000000",  # Unlikely to exist
            src_datasets={"test"},
        )

        async with AsyncGitHubClient() as client:
            _, extended_id, was_updated = await _extend_commit_id_api_async(entry, client)

        assert was_updated is False
        assert extended_id == "0000000"


class TestExtendCommitIdsApi:
    """Test API-only commit ID extension."""

    @pytest.mark.integration
    def test_extends_github_commits(self):
        entries = [
            DatasetEntry(
                project_url=CURL_PROJECT_URL,
                commit_id=CURL_SHORT_COMMIT,
                src_datasets={"test"},
            ),
        ]

        extend_commit_ids_api(entries)

        assert entries[0].commit_id == CURL_FULL_COMMIT

    def test_empty_list(self):
        entries: list[DatasetEntry] = []
        extend_commit_ids_api(entries)
        assert len(entries) == 0

    def test_full_length_commits_unchanged(self):
        entries = [
            DatasetEntry(
                project_url=CURL_PROJECT_URL,
                commit_id=CURL_FULL_COMMIT,
                src_datasets={"test"},
            ),
            DatasetEntry(
                project_url="https://github.com/example/repo",
                commit_id="a" * 40,
                src_datasets={"test"},
            ),
        ]
        original_ids = [e.commit_id for e in entries]

        extend_commit_ids_api(entries)

        assert [e.commit_id for e in entries] == original_ids


class TestExtendCommitIdsLocal:
    """Test local git-based batch commit ID extension."""

    def test_empty_list(self):
        entries: list[DatasetEntry] = []
        extend_commit_ids_local(entries)
        assert len(entries) == 0

    def test_full_length_commits_unchanged(self):
        entries = [
            DatasetEntry(
                project_url=CURL_PROJECT_URL,
                commit_id=CURL_FULL_COMMIT,
                src_datasets={"test"},
            ),
            DatasetEntry(
                project_url="https://github.com/example/repo",
                commit_id="a" * 40,
                src_datasets={"test"},
            ),
        ]
        original_ids = [e.commit_id for e in entries]

        extend_commit_ids_local(entries)

        assert [e.commit_id for e in entries] == original_ids

    @pytest.mark.integration
    @pytest.mark.slow
    def test_extends_short_commits(self):
        entries = [
            DatasetEntry(
                project_url=CURL_PROJECT_URL,
                commit_id=CURL_SHORT_COMMIT,
                src_datasets={"test"},
            ),
        ]

        extend_commit_ids_local(entries)

        assert entries[0].commit_id == CURL_FULL_COMMIT
