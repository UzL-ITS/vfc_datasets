"""Generate cross-evaluation splits: train on DS1/DS3/DS4, evaluate on DS2 CVE val+test.

This is a standalone script for the paper experiments. It does NOT modify any
existing split files. The DS2 CVE val and test sets are used as fixed evaluation
sets for all dataset variants, so results are directly comparable.

Research question: does training on manually-validated data (DS1) lead to better
results than training on larger but noisier datasets (DS3, DS4)?
"""

import shutil
from pathlib import Path

import pandas as pd

from vfc_datasets.config import DATASET_PATH
from vfc_datasets.utils.core.logging import setup_logging
from vfc_datasets.utils.core.serialization import load_entries, save_entries_csv

setup_logging("crosseval_splits")

OUTPUT_PATH = DATASET_PATH / "new"

# Fixed evaluation source
DS2_NAME = "dataset2-mr-advisory-cpp"
DS2_CVE_VAL = OUTPUT_PATH / f"{DS2_NAME}-cve-val.csv"
DS2_CVE_TEST = OUTPUT_PATH / f"{DS2_NAME}-cve-test.csv"

# Dataset variants to create cross-eval train sets for
CROSS_EVAL_VARIANTS = [
    "dataset1-manually-reviewed-cpp",
    "dataset3-all-cpp",
    "dataset4-all",
]


def load_eval_keys(csv_path: Path) -> set[tuple[str, str]]:
    """Load (project_url, commit_id) pairs from a split CSV."""
    df = pd.read_csv(csv_path)
    return set(zip(df["project_url"], df["commit_id"], strict=True))


def main() -> None:
    # Load the DS2 val+test entry keys to exclude from training sets
    val_keys = load_eval_keys(DS2_CVE_VAL)
    test_keys = load_eval_keys(DS2_CVE_TEST)
    eval_keys = val_keys | test_keys
    print(f"DS2 CVE eval set: {len(val_keys)} val + {len(test_keys)} test = {len(eval_keys)} total")

    for variant_name in CROSS_EVAL_VARIANTS:
        jsonl_path = OUTPUT_PATH / f"{variant_name}.jsonl"
        if not jsonl_path.exists():
            print(f"SKIP {variant_name}: {jsonl_path} not found")
            continue

        entries = load_entries(jsonl_path)
        print(f"\n{'='*60}")
        print(f"{variant_name}: {len(entries)} total entries")

        # Train = entries from this variant that are NOT in DS2 val/test
        train_entries = [
            e for e in entries if (e.project_url, e.commit_id) not in eval_keys
        ]
        excluded = len(entries) - len(train_entries)
        print(f"  Train: {len(train_entries)} entries ({excluded} excluded as eval overlap)")

        # Save train split
        save_entries_csv(train_entries, OUTPUT_PATH / f"{variant_name}-crosseval-train.csv")

        # Copy DS2 val+test as this variant's eval splits
        shutil.copy2(DS2_CVE_VAL, OUTPUT_PATH / f"{variant_name}-crosseval-val.csv")
        shutil.copy2(DS2_CVE_TEST, OUTPUT_PATH / f"{variant_name}-crosseval-test.csv")

        print(f"  Saved: {variant_name}-crosseval-{{train,val,test}}.csv")


if __name__ == "__main__":
    main()
