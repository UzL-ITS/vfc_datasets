from dataset_entry import DatasetEntry
from datasets.function_level.diversevul import DiverseVulDataset
from transformations.enrichment.project_urls.update_project_urls import (
    rm_entries_w_unreachable_project_urls,
    update_project_urls_inplace,
)


def test_diverse_vul_urls_loaded_from_json() -> None:
    urls = DiverseVulDataset._get_project_urls()
    assert urls["bash"][0] == "https://github.com/bminor/bash"


def test_update_project_urls_inplace_moves_known_url() -> None:
    entry = DatasetEntry(
        project_url="https://github.com/edx/edx-platform",
        commit_id="a" * 40,
        src_datasets={"test"},
    )
    update_project_urls_inplace([entry])
    assert entry.project_url == "https://github.com/openedx/edx-platform"


def test_rm_entries_w_unreachable_project_urls_filters_entries() -> None:
    unreachable = DatasetEntry(
        project_url="https://github.com/amrishc/crimemap",  # Known deleted repo
        commit_id="b" * 40,
        src_datasets={"test"},
    )
    ok = DatasetEntry(
        project_url="https://github.com/openai/openai-python",
        commit_id="c" * 40,
        src_datasets={"test"},
    )

    filtered = rm_entries_w_unreachable_project_urls([unreachable, ok])
    assert [entry.project_url for entry in filtered] == [ok.project_url]

