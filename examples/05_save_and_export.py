"""Save a dataset to JSONL and export selected fields to CSV."""

from pathlib import Path

import vfc_datasets
from vfc_datasets.utils.core.logging import setup_logging
from vfc_datasets.utils.core.serialization import save_entries, save_entries_csv

setup_logging("save_and_export")

if __name__ == "__main__":
    entries = vfc_datasets.DevignDataset()

    output_dir = Path(".data/exports")
    save_entries(entries, output_dir / "devign.jsonl")
    save_entries_csv(
        entries,
        output_dir / "devign.csv",
        fields=["project_url", "commit_id", "is_vfc", "cve_ids", "cwe_ids"],
    )
