import json
import logging
from collections.abc import Sequence
from pathlib import Path

import pandas as pd

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
            json.dump(entry.to_dict(), f, allow_nan=False)
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

    valid_fields = {s.lstrip("_") for s in DatasetEntry.__slots__}
    if invalid_fields := set(fields) - valid_fields:
        raise ValueError(f"Invalid field names: {invalid_fields}")

    output_path = Path(file_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rows = [entry.to_dict() for entry in entries]
    for row in rows:
        for key, value in row.items():
            if isinstance(value, list):
                row[key] = ";".join(str(v) for v in value) if value else None

    csv_data = pd.DataFrame(rows, columns=fields)
    if "project_url" in csv_data.columns:
        csv_data = csv_data.sort_values(by=["project_url"]).reset_index(drop=True)
    csv_data.to_csv(output_path, index=False)
