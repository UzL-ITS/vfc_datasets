"""Shared helpers for commit-data enrichment (API and local)."""

from typing import Any

from dataset_entry import DatasetEntry


def needs_enrichment(entry: DatasetEntry) -> bool:
    """Check if entry is missing any commit field that enrichment can provide."""
    return (
        entry.commit_message is None
        or entry.commit_diff is None
        or entry.commit_timestamp_utc is None
        or not entry.files_changed
    )


def apply_commit_data(entry: DatasetEntry, data: dict[str, Any]) -> None:
    """Update entry fields from commit data (only fills missing fields)."""
    if entry.commit_message is None:
        entry.commit_message = data.get("message")
    if entry.commit_timestamp_utc is None:
        entry.commit_timestamp_utc = data.get("timestamp")
    if entry.commit_diff is None:
        entry.commit_diff = data.get("diff")
    if not entry.files_changed:
        files = data.get("files_changed")
        if files:
            entry.files_changed = files if isinstance(files, set) else set(files)
