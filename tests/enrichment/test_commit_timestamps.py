import datetime

import pytest

from vfc_datasets.dataset_entry import DatasetEntry
from vfc_datasets.transformations.enrichment.add_commit_data_local import (
    add_commit_information_local,
)


class TestTimestamps:
    @pytest.mark.integration
    @pytest.mark.slow
    def test_get_commit_info_linux_repo(self):
        entry = DatasetEntry(
            project_url="https://github.com/torvalds/linux",
            commit_id="0184d2b386f836925ff2f9b4e6d4f9a8048cf58f",
            src_datasets={"test"},
            files_changed=set(),
            commit_message=None,
            commit_diff=None,
        )
        add_commit_information_local([entry])

        expected_timestamp = datetime.datetime(2026, 4, 16, 2, 58, 23, tzinfo=datetime.UTC)
        assert entry.commit_timestamp_utc == expected_timestamp
