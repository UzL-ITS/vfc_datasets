import logging
import os
import random

import datasets
import transformations
from config import BASE_DATA_PATH, DATASET_PATH
from utils.core.logging import setup_logging
from utils.core.serialization import load_entries, save_entries
from utils.core.statistics import print_dataset_stats

log_filename = setup_logging("create_no_comment_dataset")

OUTPUT_PATH = DATASET_PATH / "new"

base_dataset_name = "no_comment_dataset_sample.jsonl"

def _create_no_comment_dataset():
    logging.info("Building a no-comment example")
    entries = datasets.BigVulDataset() + datasets.DevignDataset()
    entries = transformations.update_project_urls_inplace(entries)
    entries = transformations.filter_unreachable_project_urls(entries)
    entries = transformations.extend_commit_ids_local(entries)
    entries = transformations.collapse_to_commit_level(entries)
    entries = transformations.add_commit_information_local(entries)
    entries = transformations.deduplicate_within_repository(entries)
    save_entries(entries, OUTPUT_PATH / base_dataset_name)
    return entries


if __name__ == "__main__":
    if os.path.exists(OUTPUT_PATH / base_dataset_name):
        base_dataset = load_entries(OUTPUT_PATH / base_dataset_name)
    else:
        base_dataset = _create_no_comment_dataset()

    # no comments diff
    base_dataset = transformations.add_commit_diff_no_comment(base_dataset)
    no_comment_dataset = [e for e in base_dataset if e.commit_diff and e.commit_diff != e.commit_diff_no_comment]
    random.seed(42)
    no_comment_dataset = random.sample(no_comment_dataset, min(10, len(no_comment_dataset)))

    diff_path = os.path.join(BASE_DATA_PATH, "diffs")
    os.makedirs(diff_path, exist_ok=True)
    for i, entry in enumerate(no_comment_dataset):
        with open(os.path.join(diff_path, f"no_comment_diff_{i}_with_comments.txt"), "w") as f:
            f.write(entry.commit_diff or "")
        with open(os.path.join(diff_path, f"no_comment_diff_{i}_no_comments.txt"), "w") as f:
            f.write(entry.commit_diff_no_comment or "")
    print_dataset_stats(base_dataset)
