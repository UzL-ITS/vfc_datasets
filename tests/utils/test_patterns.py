from __future__ import annotations

import pytest

from utils.git.url import COMMIT_HASH_PATTERN
from utils.patterns import CVE_PATTERN, CWE_PATTERN


class TestCVEPattern:
    """Tests for CVE ID pattern validation."""

    @pytest.mark.parametrize(
        "cve_id",
        [
            "CVE-2021-1234",  # Standard 4-digit ID
            "CVE-2024-12345",  # 5-digit ID
            "CVE-2025-123456",  # 6-digit ID
            "CVE-2025-1234567",  # 7-digit ID
            "CVE-2025-12345678",  # 8-digit ID (testing unbounded)
            "CVE-2025-123456789",  # 9-digit ID
            "CVE-2025-12345678901234567890",  # Very long ID (20+ digits)
            "CVE-1999-0001",  # Minimum year
            "CVE-9999-9999",  # Future year
        ],
    )
    def test_valid_cve_ids(self, cve_id: str) -> None:
        match = CVE_PATTERN.match(cve_id)
        assert match is not None, f"Valid CVE ID '{cve_id}' should match"
        assert match.group() == cve_id

    @pytest.mark.parametrize(
        "invalid_cve",
        [
            "CVE-2021-123",  # Too few digits (only 3)
            "CVE-21-1234",  # Year too short
            "CVE-20211-1234",  # Year too long
            "CVE-2021-",  # Missing ID number
            "CVE-2021",  # Missing dash and ID
            "cve-2021-1234",  # Lowercase (pattern is case-sensitive)
            "2021-1234",  # Missing CVE prefix
            "CVE-ABCD-1234",  # Non-numeric year
            "CVE-2021-ABCD",  # Non-numeric ID
        ],
    )
    def test_invalid_cve_ids(self, invalid_cve: str) -> None:
        match = CVE_PATTERN.match(invalid_cve)
        assert match is None, f"Invalid CVE ID '{invalid_cve}' should not match"

    def test_cve_partial_match(self) -> None:
        """Test that CVE pattern can extract valid CVE from longer string."""
        # This is expected behavior - pattern is for extraction/searching
        text = "CVE-2021-1234-5678"
        match = CVE_PATTERN.match(text)
        assert match is not None
        assert match.group() == "CVE-2021-1234"  # Matches the valid part


class TestCWEPattern:
    """Tests for CWE ID pattern validation."""

    @pytest.mark.parametrize(
        "cwe_id",
        [
            "CWE-1",  # Single digit
            "CWE-79",  # Common XSS
            "CWE-89",  # Common SQL injection
            "CWE-123",  # 3 digits
            "CWE-1234",  # Maximum 4 digits
        ],
    )
    def test_valid_cwe_ids(self, cwe_id: str) -> None:
        match = CWE_PATTERN.match(cwe_id)
        assert match is not None, f"Valid CWE ID '{cwe_id}' should match"
        assert match.group() == cwe_id

    @pytest.mark.parametrize(
        "invalid_cwe",
        [
            "CWE-",  # Missing number
            "cwe-79",  # Lowercase
            "79",  # Missing CWE prefix
            "CWE-ABC",  # Non-numeric
        ],
    )
    def test_invalid_cwe_ids(self, invalid_cwe: str) -> None:
        match = CWE_PATTERN.match(invalid_cwe)
        assert match is None, f"Invalid CWE ID '{invalid_cwe}' should not match"

    def test_cwe_partial_match(self) -> None:
        """Test that CWE pattern can extract valid CWE from longer string."""
        # This is expected behavior - pattern is for extraction/searching
        # CWE-0 exists in the database, so it's valid
        text1 = "CWE-12345"
        match1 = CWE_PATTERN.match(text1)
        assert match1 is not None
        assert match1.group() == "CWE-1234"  # Matches first 4 digits

        text2 = "CWE-79-89"
        match2 = CWE_PATTERN.match(text2)
        assert match2 is not None
        assert match2.group() == "CWE-79"  # Matches the valid part


class TestCommitHashPattern:
    """Tests for commit hash pattern validation."""

    @pytest.mark.parametrize(
        "commit_id",
        [
            "abc12",  # 5 chars (minimum)
            "abc1234",  # 7 chars (git default)
            "abc123456",  # 9 chars
            "abc1234567890",  # 12 chars
            "abc1234567890abcdef1234567890abcdef12",  # 40 chars (full SHA)
            "ABCDEF1234567",  # Uppercase
            "AbCdEf1234567",  # Mixed case
        ],
    )
    def test_valid_commit_ids(self, commit_id: str) -> None:
        assert COMMIT_HASH_PATTERN.fullmatch(commit_id), f"'{commit_id}' should match"

    @pytest.mark.parametrize(
        "invalid_commit",
        [
            "abc1",  # Too short (only 4 chars)
            "abc",  # Too short (only 3 chars)
            "ghij1234567",  # Invalid hex chars (g, h, i, j)
            "abc1234567890abcdef1234567890abcdef123456",  # 41 chars (too long)
            "prefix_abc1234567",  # Has prefix
            "abc1234567_suffix",  # Has suffix
            " abc1234567 ",  # Has whitespace
        ],
    )
    def test_invalid_commit_ids(self, invalid_commit: str) -> None:
        assert not COMMIT_HASH_PATTERN.fullmatch(invalid_commit), (
            f"'{invalid_commit}' should not match"
        )
