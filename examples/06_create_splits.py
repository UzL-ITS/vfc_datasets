"""Create a random train/val/test split and write each part to CSV."""

from pathlib import Path

import vfc_datasets
from vfc_datasets.utils.core.logging import setup_logging
from vfc_datasets.utils.split import create_random_split

setup_logging("create_splits")

if __name__ == "__main__":
    create_random_split(
        vfc_datasets.DevignDataset(),
        name="devign",
        output_path=Path(".data/splits"),
        seed=42,
        train_ratio=0.6,
        val_ratio=0.2,
        test_ratio=0.2,
    )
