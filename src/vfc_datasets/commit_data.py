"""What one source knows about one commit.

Datasets ship commit data in a handful of wire formats; enrichment reads it from git or the
GitHub API. Every source produces a `CommitData`, which `DatasetEntry` holds as `entry.commit`,
so the fields are declared and merged in exactly one place.
"""

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Self

__all__ = [
    "CommitData",
    "files_changed_from_diff",
    "from_git_show",
    "from_unified_diff",
    "normalize_commit_timestamp",
]

# `diff --git a/old b/new`; paths may be quoted and either side may be /dev/null.
# `\r?` keeps CRLF diffs from leaving a carriage return inside the captured path.
_DIFF_HEADER = re.compile(r'^diff --git ("?a/.*?"?) ("?b/.*?"?)\r?$', re.MULTILINE)
_DIFF_START = re.compile(r"^diff --git ", re.MULTILINE)
_SHOW_DATE = re.compile(r"^Date:\s+(.+)$", re.MULTILINE)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat().replace("+00:00", "Z") if value else None


def normalize_commit_timestamp(value: datetime | str | None) -> datetime | None:
    """Coerce a timestamp to a tz-aware UTC datetime.

    Accepts ISO-format strings, naive datetimes, and tz-aware datetimes.
    """
    if value is None:
        return None
    dt = datetime.fromisoformat(value) if isinstance(value, str) else value
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class CommitData:
    """Commit information from one source. Partial by nature; immutable so it can cross the
    process boundary from enrichment workers and fan out to several entries."""

    message: str | None = None
    diff: str | None = None
    files_changed: frozenset[str] = frozenset()
    authored_at: datetime | None = None
    committed_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "authored_at", normalize_commit_timestamp(self.authored_at))
        object.__setattr__(self, "committed_at", normalize_commit_timestamp(self.committed_at))

    def is_complete(self) -> bool:
        """Whether every field enrichment could supply is already present."""
        return (
            self.message is not None
            and self.diff is not None
            and self.authored_at is not None
            and self.committed_at is not None
            and bool(self.files_changed)
        )

    def merge(self, other: "CommitData") -> "CommitData":
        """Fill this one's gaps from `other`. Values already set here win."""
        return CommitData(
            message=self.message if self.message is not None else other.message,
            diff=self.diff if self.diff is not None else other.diff,
            files_changed=self.files_changed or other.files_changed,
            authored_at=self.authored_at if self.authored_at is not None else other.authored_at,
            committed_at=self.committed_at if self.committed_at is not None else other.committed_at,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "message": self.message,
            "diff": self.diff,
            "files_changed": sorted(self.files_changed),
            "authored_at": _iso(self.authored_at),
            "committed_at": _iso(self.committed_at),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Self:
        if not data:
            return cls()
        return cls(
            message=data.get("message"),
            diff=data.get("diff"),
            files_changed=frozenset(data.get("files_changed") or []),
            authored_at=normalize_commit_timestamp(data.get("authored_at")),
            committed_at=normalize_commit_timestamp(data.get("committed_at")),
        )


def files_changed_from_diff(diff: object) -> frozenset[str]:
    """Paths touched by a unified diff."""
    if not isinstance(diff, str):
        return frozenset()

    files: set[str] = set()
    for old, new in _DIFF_HEADER.findall(diff):
        # Deletions have b/ as /dev/null, so fall back to the a/ side.
        path = new if not new.endswith("/dev/null") else old
        files.add(path.strip('"')[2:])
    files.discard("")
    return frozenset(files)


def from_unified_diff(diff: object) -> CommitData:
    """Commit data from a plain `git diff` patch."""
    if not isinstance(diff, str) or not diff.strip():
        return CommitData()
    return CommitData(diff=diff, files_changed=files_changed_from_diff(diff))


def from_git_show(text: object) -> CommitData:
    """Commit data from `git show` output: header block, blank line, indented message, diff."""
    if not isinstance(text, str) or not text.strip():
        return CommitData()

    head, diff = _split_diff(text)
    lines = head.split("\n")
    index = 0
    while index < len(lines) and lines[index].strip():  # header block
        index += 1
    while index < len(lines) and not lines[index].strip():  # blank separator
        index += 1
    message = "\n".join(line.removeprefix("    ") for line in lines[index:]).strip("\n")

    return CommitData(
        message=message or None,
        diff=diff,
        files_changed=files_changed_from_diff(diff),
        authored_at=_git_show_date(head),
    )


def _git_show_date(head: str) -> datetime | None:
    """`git show` prints the author date as `Date:   Fri Aug 4 15:26:15 2023 +0200`."""
    match = _SHOW_DATE.search(head)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1).strip(), "%a %b %d %H:%M:%S %Y %z")
    except ValueError:
        return None


def _split_diff(text: str) -> tuple[str, str | None]:
    match = _DIFF_START.search(text)
    if not match:
        return text, None
    return text[: match.start()], text[match.start() :]
