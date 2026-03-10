import logging
from pathlib import Path

from tqdm.auto import tqdm

from dataset_entry import DatasetEntry

logger = logging.getLogger(__name__)


def filter_by_extension(
    entries: list[DatasetEntry],
    extensions: set[str],
) -> list[DatasetEntry]:
    """Filter entries to those with at least one changed file matching the given extensions."""
    normalized = {(e if e.startswith(".") else f".{e}").lower() for e in extensions}

    filtered: list[DatasetEntry] = []
    skipped_no_files = 0

    for entry in tqdm(entries, desc="Filtering by extension", dynamic_ncols=True):
        if not entry.files_changed:
            skipped_no_files += 1
            continue
        if any(Path(f).suffix.lower() in normalized for f in entry.files_changed):
            filtered.append(entry)

    logger.info(
        "Extension filter: %d matched, %d skipped (no files_changed), %d excluded",
        len(filtered),
        skipped_no_files,
        len(entries) - len(filtered) - skipped_no_files,
    )

    return filtered
