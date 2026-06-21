from vfc_datasets.parsing_helpers import normalize_commit_id, normalize_cwe_ids, pinned_commit


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

    SHA = "abcdef1234567890abcdef1234567890abcdef12"

    def test_strips_url_fragments_and_whitespace(self) -> None:
        assert (
            normalize_commit_id(" abcdef1234567890?w=1#diff-abcdef1234567890L1")
            == "abcdef1234567890"
        )

    def test_strips_patch_and_diff_extensions(self) -> None:
        assert normalize_commit_id(self.SHA + ".patch") == self.SHA
        assert normalize_commit_id(self.SHA + ".diff") == self.SHA

    def test_strips_trailing_punctuation(self) -> None:
        assert normalize_commit_id(self.SHA + ",") == self.SHA
        assert normalize_commit_id(self.SHA + ".") == self.SHA

    def test_extracts_sha_from_patch_url(self) -> None:
        assert normalize_commit_id(f"https://github.com/o/r/commit/{self.SHA}.patch") == self.SHA

    def test_symbolic_ref_is_not_resolved(self) -> None:
        # Branch/tag names are no longer resolved over the network during parsing.
        assert normalize_commit_id("master") is None

    def test_invalid_sha_returns_none(self) -> None:
        assert normalize_commit_id("not-a-sha") is None


class TestPinnedCommit:
    """Tests for the static pinned-commit lookup."""

    URL = "https://github.com/dom4j/dom4j"
    SHA = "177069f0e96a40ddab5ab7f41519ec29e5a39652"

    def test_returns_pinned_sha_for_known_ref(self) -> None:
        assert pinned_commit(self.URL, "version-2.0.3") == self.SHA

    def test_unknown_ref_returns_none(self) -> None:
        assert pinned_commit(self.URL, "not-pinned") is None

    def test_unknown_project_returns_none(self) -> None:
        assert pinned_commit("https://github.com/foo/bar", "version-2.0.3") is None

    def test_non_string_or_missing_inputs_return_none(self) -> None:
        assert pinned_commit(None, "version-2.0.3") is None
        assert pinned_commit(self.URL, 123) is None
