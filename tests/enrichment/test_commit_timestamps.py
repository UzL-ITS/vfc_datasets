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
        """This commit was authored ~6 months before it landed, so it pins both dates apart."""
        entry = DatasetEntry(
            project_url="https://github.com/torvalds/linux",
            commit_id="0184d2b386f836925ff2f9b4e6d4f9a8048cf58f",
            src_datasets={"test"},
        )
        add_commit_information_local([entry])

        assert entry.commit.authored_at == datetime.datetime(
            2025, 10, 17, 14, 51, 42, tzinfo=datetime.UTC
        )
        assert entry.commit.committed_at == datetime.datetime(
            2026, 4, 16, 2, 58, 23, tzinfo=datetime.UTC
        )
