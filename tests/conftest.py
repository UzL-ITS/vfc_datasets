import pytest

from dataset_entry import DatasetEntry


@pytest.fixture
def sample_dataset() -> list[DatasetEntry]:
    """Small, deterministic DatasetEntry list for unit tests."""
    return [
        DatasetEntry(
            project_url="https://github.com/test/repo1",
            commit_id="abc1234",
            src_datasets={"test"},
            is_vfc=True,
            cve_ids={"CVE-2021-0001"},
        ),
        DatasetEntry(
            project_url="https://github.com/test/repo1",
            commit_id="def5678",
            src_datasets={"test"},
            is_vfc=True,
            cve_ids={"CVE-2021-0001"},
        ),
        DatasetEntry(
            project_url="https://github.com/test/repo2",
            commit_id="feedbee",
            src_datasets={"test"},
            is_vfc=False,
        ),
    ]
