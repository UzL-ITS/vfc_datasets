"""
Filter commits by programming language using file extensions from DatasetEntry.files_changed.
"""

import logging
from pathlib import Path

from tqdm.auto import tqdm

from dataset_entry import DatasetEntry

logger = logging.getLogger(__name__)


def filter_by_extension(
    entries: list[DatasetEntry],
    extensions: list[str] | set[str],
) -> list[DatasetEntry]:
    # Validate inputs
    if entries is None:
        raise ValueError("entries cannot be None")

    if not extensions:
        raise ValueError("extensions cannot be empty")

    # Validate all extensions are strings
    for ext in extensions:
        if not isinstance(ext, str):
            raise TypeError(f"All extensions must be strings, got {type(ext).__name__}: {ext!r}")
        if not ext:
            raise ValueError("Extension cannot be an empty string")

    # Normalize extensions to lowercase and ensure they start with a dot
    normalized_extensions = set()
    for ext in extensions:
        ext = ext.lower().strip()
        if not ext.startswith("."):
            ext = "." + ext
        normalized_extensions.add(ext)

    filtered_entries: list[DatasetEntry] = []
    skipped_no_files = 0

    # Filter entries using files_changed from DatasetEntry
    for entry in tqdm(entries, desc="Filtering by extension", dynamic_ncols=True):
        # Check if any changed file has one of the specified extensions
        if not entry.files_changed:
            skipped_no_files += 1
            continue
        for file_path in entry.files_changed:
            ext = Path(file_path).suffix
            if ext.lower() in normalized_extensions:
                filtered_entries.append(entry)
                break  # No need to check other files once we found a match

    logger.info(
        "Extension filter: %d matched, %d skipped (no files_changed), %d excluded",
        len(filtered_entries),
        skipped_no_files,
        len(entries) - len(filtered_entries) - skipped_no_files,
    )

    return filtered_entries


# Predefined extension sets for common languages
C_CPP_EXTENSIONS = {
    # C source and headers
    ".c",
    ".h",
    # C++ source
    ".cpp",
    ".cc",
    ".cxx",
    ".c++",
    ".cp",
    # C++ headers
    ".hpp",
    ".hh",
    ".hxx",
    ".h++",
    ".hp",
}

PYTHON_EXTENSIONS = {
    ".py",
    ".pyw",
    ".pyx",
    ".pyi",
    # ".pyc", ".pyd",
}

JAVA_EXTENSIONS = {
    ".java",
    # ".class", ".jar",
}

JAVASCRIPT_EXTENSIONS = {
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".mjs",
    ".cjs",
}

GO_EXTENSIONS = {
    ".go",
}

RUST_EXTENSIONS = {
    ".rs",
}
