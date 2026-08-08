import json
import logging
from collections.abc import Iterable
from dataclasses import fields as dc_fields
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any

import pandas as pd

from vfc_datasets.commit_data import CommitData
from vfc_datasets.config import DATASET_PATH
from vfc_datasets.dataset_entry import DatasetEntry

logger = logging.getLogger(__name__)

# Bump when the serialized entry shape changes meaning (not for additive fields).
SCHEMA_VERSION = 2


def load_entries(file_path: str | Path) -> list[DatasetEntry]:
    """Load dataset entries from a JSONL file."""
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    logger.info("Loading entries from %s", file_path)

    entries: list[DatasetEntry] = []

    skipped = 0
    last_error: Exception | None = None

    with open(file_path, encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            if not line.strip():  # Skip empty lines
                continue

            data = json.loads(line)

            if "_metadata" in data:
                logger.info("Dataset metadata: %s", data["_metadata"])
                if (schema := data["_metadata"].get("schema", 1)) != SCHEMA_VERSION:
                    raise ValueError(
                        f"{file_path} uses entry schema {schema}, this build reads "
                        f"{SCHEMA_VERSION}. Commit fields moved under `commit` and the "
                        "function's file moved out of `files_changed` into `function_file`, "
                        "so the old shape would load with the wrong meaning. Re-export it."
                    )
                continue

            try:
                entries.append(DatasetEntry.from_dict(data))
            except (TypeError, ValueError) as exc:
                skipped += 1
                last_error = exc
                if skipped <= 5:
                    logger.warning(
                        "Skipping invalid entry in %s (line %d): %s",
                        file_path,
                        line_number,
                        exc,
                    )
                continue

    if skipped:
        summary_msg = f"Skipped {skipped} invalid entr{'y' if skipped == 1 else 'ies'} while loading {file_path}."
        if last_error and skipped > 5:
            summary_msg += f" Last error: {last_error}"
        logger.warning(summary_msg)

    logger.info("Loaded %d entries from %s", len(entries), file_path)
    return entries


def save_entries(entries: Iterable[DatasetEntry], file_path: str | Path) -> None:
    """Save dataset entries to a JSONL file."""
    entries = list(entries)
    if not entries:
        raise ValueError(f"Cannot save empty entries to {file_path}. No entries to store.")

    file_path = Path(file_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Saving %d entries to %s", len(entries), file_path)

    with open(file_path, "w", encoding="utf-8") as f:
        metadata: dict[str, dict[str, Any]] = {
            "_metadata": {
                "version": version("vfc_datasets"),
                "schema": SCHEMA_VERSION,
                "created": datetime.now(UTC).isoformat(),
                "entry_count": len(entries),
            }
        }
        json.dump(metadata, f, allow_nan=False)
        f.write("\n")
        for entry in entries:
            json.dump(entry.to_dict(), f, allow_nan=False)
            f.write("\n")

    logger.info("Successfully saved %d entries to %s", len(entries), file_path)


def load_cache(cache_key: str, dataset_path: Path = DATASET_PATH) -> list[DatasetEntry] | None:
    """Load cached dataset entries if they exist. Returns None if cache doesn't exist."""
    cache_path = dataset_path / "cache" / f"{cache_key.lower()}.jsonl"

    if not cache_path.exists():
        return None

    return load_entries(cache_path)


def save_cache(
    entries: Iterable[DatasetEntry], cache_key: str, dataset_path: Path = DATASET_PATH
) -> None:
    """Save entries to cache file as JSONL."""
    cache_path = dataset_path / "cache" / f"{cache_key.lower()}.jsonl"
    save_entries(entries, cache_path)


def save_entries_csv(
    entries: Iterable[DatasetEntry],
    file_path: str | Path,
    fields: list[str] | None = None,
) -> None:
    """Save dataset entries to a CSV file."""
    entries = list(entries)
    if not entries:
        raise ValueError(f"Cannot export empty entries to {file_path}. No entries to export.")

    if fields is None:
        fields = ["project_url", "commit_id", "is_vfc", "commit.committed_at"]

    valid_fields = {f.name for f in dc_fields(DatasetEntry)} | {
        f"commit.{f.name}" for f in dc_fields(CommitData)
    }
    if invalid_fields := set(fields) - valid_fields:
        raise ValueError(f"Invalid field names: {invalid_fields}")

    output_path = Path(file_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    for entry in entries:
        row = entry.to_dict()
        # Flatten `commit` so its fields are addressable as `commit.<name>` columns.
        for key, value in row.pop("commit").items():
            row[f"commit.{key}"] = value
        rows.append(row)

    for row in rows:
        for key, value in row.items():
            if isinstance(value, list):
                row[key] = ";".join(str(v) for v in value) if value else None

    csv_data = pd.DataFrame(rows, columns=fields)
    if "project_url" in csv_data.columns:
        csv_data = csv_data.sort_values(by=["project_url"]).reset_index(drop=True)
    csv_data.to_csv(output_path, index=False)
