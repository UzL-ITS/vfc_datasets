import pytest

from utils.git.repository import clone_repositories, clone_repository


class TestCloneRepository:
    """Tests for clone_repository function."""

    def test_empty_url_returns_none(self) -> None:
        assert clone_repository("") is None

    def test_invalid_url_returns_none(self) -> None:
        assert clone_repository("not-a-url") is None

    @pytest.mark.integration
    def test_nonexistent_repo_returns_none(self) -> None:
        result = clone_repository("https://github.com/this-org-does-not-exist-12345/fake-repo")
        assert result is None

    @pytest.mark.integration
    def test_private_repo_without_auth_returns_none(self) -> None:
        result = clone_repository("https://github.com/ghost/ghost-private-repo")
        assert result is None


class TestCloneRepositories:
    def test_empty_set_returns_empty_dict(self) -> None:
        assert clone_repositories(set()) == {}
