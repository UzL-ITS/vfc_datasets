from dataset_entry import DatasetEntry
from transformations.enrichment.project_urls.update_project_urls import (
    filter_unreachable_project_urls,
    update_project_urls_inplace,
)
from vfc_datasets.function_level.diversevul import DiverseVulDataset


def test_diverse_vul_urls_loaded_from_json() -> None:
    urls = DiverseVulDataset._get_project_urls()
    assert urls["bash"][0] == "https://github.com/bminor/bash"


def test_update_project_urls_inplace_moves_known_url() -> None:
    entry = DatasetEntry(
        project_url="https://github.com/apache/tomcat70",
        commit_id="a" * 40,
        src_datasets={"test"},
    )
    update_project_urls_inplace([entry])
    assert entry.project_url == "https://github.com/apache/tomcat"


def test_filter_unreachable_project_urls_filters_entries() -> None:
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

    filtered = filter_unreachable_project_urls([unreachable, ok])
    assert [entry.project_url for entry in filtered] == [ok.project_url]
