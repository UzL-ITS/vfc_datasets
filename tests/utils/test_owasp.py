"""Tests for OWASP CWE mapping."""

from vfc_datasets.utils.owasp import OwaspCategory, cwes_to_owasp


class TestCwesToOwasp:
    def test_known_cwe_maps_to_category(self) -> None:
        assert cwes_to_owasp({"CWE-79"}) == {OwaspCategory.INJECTION}

    def test_multiple_cwes_multiple_categories(self) -> None:
        result = cwes_to_owasp({"CWE-79", "CWE-22"})
        assert result == {OwaspCategory.INJECTION, OwaspCategory.BROKEN_ACCESS_CONTROL}

    def test_unknown_cwe_returns_zero(self) -> None:
        assert cwes_to_owasp({"CWE-99999"}) == {OwaspCategory.UNKNOWN}

    def test_mix_known_and_unknown(self) -> None:
        result = cwes_to_owasp({"CWE-79", "CWE-99999"})
        assert OwaspCategory.INJECTION in result
        assert OwaspCategory.UNKNOWN not in result  # known CWEs found, so UNKNOWN not returned
