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
            commit_id="2b38afce25c4e1b8f943ff4f0a2b51d6c40f2ed2",
            src_datasets={"test"},
            files_changed=set(),
            commit_message=None,
            commit_diff=None,
        )
        add_commit_information_local([entry])

        expected_timestamp = datetime.datetime(2025, 8, 10, 6, 2, 36, tzinfo=datetime.UTC)
        assert entry.commit_timestamp_utc == expected_timestamp
