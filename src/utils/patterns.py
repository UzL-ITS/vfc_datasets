"""Regex patterns for vulnerability identifiers (CVE, CWE)."""

from __future__ import annotations

import re

# CVE IDs: CVE-YYYY-NNNN+ (4+ digits, unlimited)
CVE_PATTERN = re.compile(r"CVE-\d{4}-\d{4,}")

# CWE IDs: CWE-N (1-4 digits)
CWE_PATTERN = re.compile(r"CWE-\d{1,4}")

__all__ = [
    "CVE_PATTERN",
    "CWE_PATTERN",
]
