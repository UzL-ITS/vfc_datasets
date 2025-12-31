import json
import logging
import math
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from config import DATASET_PATH
from dataset_entry import DatasetEntry

logger = logging.getLogger(__name__)


def load_entries(file_path: str | Path) -> list[DatasetEntry]:
    """Load dataset entries from a JSONL file."""
    from dataset_entry import create_dataset_entry

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

            # Handle None/NaN values for pandas compatibility
            for key, value in data.items():
                if value is None or (isinstance(value, float) and math.isnan(value)):
                    data[key] = None

            try:
                entries.append(create_dataset_entry(data))
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


def save_entries(entries: Sequence[DatasetEntry], file_path: str | Path) -> None:
    """Save dataset entries to a JSONL file."""
    if not entries:
        raise ValueError(f"Cannot save empty entries to {file_path}. No entries to store.")

    file_path = Path(file_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Saving %d entries to %s", len(entries), file_path)

    with open(file_path, "w", encoding="utf-8") as f:
        for entry in entries:
            json.dump(entry.to_dict(), f)
            f.write("\n")

    logger.info("Successfully saved %d entries to %s", len(entries), file_path)


def load_cache(dataset_name: str, dataset_path: Path = DATASET_PATH) -> list[DatasetEntry] | None:
    """Load cached dataset entries if they exist. Returns None if cache doesn't exist."""
    cache_path = dataset_path / "cache" / f"{dataset_name.lower()}.jsonl"

    if not cache_path.exists():
        return None

    return load_entries(cache_path)


def save_cache(entries: Sequence[DatasetEntry], dataset_name: str) -> None:
    """Save entries to cache file as JSONL."""
    cache_path = DATASET_PATH / "cache" / f"{dataset_name.lower()}.jsonl"
    save_entries(entries, cache_path)


def save_entries_csv(
    entries: Sequence[DatasetEntry],
    file_path: str | Path,
    fields: list[str] | None = None,
) -> None:
    """Save dataset entries to a CSV file."""
    if not entries:
        raise ValueError(f"Cannot export empty entries to {file_path}. No entries to export.")

    if fields is None:
        fields = ["project_url", "commit_id", "is_vfc", "commit_timestamp_utc"]

    # Check against class attributes (slots + properties)
    if invalid_fields := {f for f in fields if not hasattr(DatasetEntry, f)}:
        raise ValueError(f"Invalid field names: {invalid_fields}")

    output_path = Path(file_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    import pandas as pd

    rows: list[dict[str, Any]] = []
    for entry in entries:
        row: dict[str, Any] = {}
        for field in fields:
            value = getattr(entry, field, None)

            if value is None:
                row[field] = None
            elif isinstance(value, set):
                row[field] = ";".join(str(v) for v in sorted(value)) if value else None
            elif hasattr(value, "isoformat"):
                row[field] = value.isoformat()
            else:
                row[field] = value

        rows.append(row)

    csv_data = pd.DataFrame(rows)
    if "project_url" in csv_data.columns:
        csv_data = csv_data.sort_values(by=["project_url"]).reset_index(drop=True)
    csv_data.to_csv(output_path, index=False)
