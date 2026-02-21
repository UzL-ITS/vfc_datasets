import pytest

from vfc_datasets.parsing_helpers import (
    _resolve_symbolic_ref,
    normalize_commit_id,
    normalize_cwe_ids,
)


class TestNormalizeCweIds:
    """Tests for normalize_cwe_ids function."""

    def test_adds_prefix_for_numeric_string(self) -> None:
        assert normalize_cwe_ids("79") == {"CWE-79"}

    def test_adds_prefix_for_integer_in_list(self) -> None:
        assert normalize_cwe_ids([79]) == {"CWE-79"}

    def test_handles_plain_integer_input(self) -> None:
        assert normalize_cwe_ids(79) == {"CWE-79"}

    def test_preserves_existing_prefix_case_insensitively(self) -> None:
        assert normalize_cwe_ids(["cwe-89"]) == {"CWE-89"}

    def test_drops_non_numeric_values(self) -> None:
        assert normalize_cwe_ids(["custom"]) == set()

    def test_drops_non_numeric_prefixed_values(self) -> None:
        assert normalize_cwe_ids(["CWE-CUSTOM"]) == set()

    def test_strips_leading_zeroes(self) -> None:
        assert normalize_cwe_ids(["CWE-022"]) == {"CWE-22"}
        assert normalize_cwe_ids(["022"]) == {"CWE-22"}

    def test_ignores_na_and_empty_values(self) -> None:
        assert normalize_cwe_ids(["NA", " "]) == set()

    def test_handles_none_input(self) -> None:
        assert normalize_cwe_ids(None) == set()

    def test_handles_nan_input(self) -> None:
        assert normalize_cwe_ids(float("nan")) == set()


class TestNormalizeCommitId:
    """Tests for normalize_commit_id function."""

    def test_strips_url_fragments_and_whitespace(self) -> None:
        assert (
            normalize_commit_id(" abcdef1234567890?w=1#diff-abcdef1234567890L1")
            == "abcdef1234567890"
        )

    def test_invalid_sha_returns_none(self) -> None:
        assert normalize_commit_id("not-a-sha") is None


class TestResolveSymbolicRef:
    """Tests for _resolve_symbolic_ref function."""

    def test_non_github_url_returns_none(self) -> None:
        """Non-GitHub URLs should return None (API only supports github.com)."""
        assert _resolve_symbolic_ref("main", "https://gitlab.com/foo/bar") is None

    @pytest.mark.integration
    def test_resolves_curl_tag_to_commit_sha(self) -> None:
        """Resolve curl-7_50_0 tag to its commit SHA using real GitHub API.

        This tests both the API call logic AND the SHA normalization (lowercase).
        """
        sha = _resolve_symbolic_ref("curl-7_50_0", "https://github.com/curl/curl")

        # Known stable commit for curl-7_50_0 tag
        expected_sha = "79e63a53bb9598af863b0afe49ad662795faeef4"

        if sha:
            assert sha == expected_sha, f"Expected {expected_sha}, got {sha}"
        else:
            pytest.skip("Could not resolve (no local repo and API unavailable)")

    @pytest.mark.integration
    def test_nonexistent_ref_returns_none(self) -> None:
        """Non-existent refs should return None gracefully."""
        sha = _resolve_symbolic_ref("this-tag-does-not-exist-12345", "https://github.com/curl/curl")
        assert sha is None
