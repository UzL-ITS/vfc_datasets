"""Tests for dataset parsing functionality."""

import pytest

from datasets.commit_level.devign import DevignDataset

pytestmark = [pytest.mark.slow]


def test_parse_dataset():
    """Test parsing a dataset via iteration."""
    entries = list(DevignDataset())

    assert len(entries) > 0

    first_entry = entries[0]
    assert hasattr(first_entry, "project_url")
    assert hasattr(first_entry, "commit_id")
    assert hasattr(first_entry, "src_datasets")


def test_parse_dataset_cache_hit():
    """Test parsing the same dataset twice (cache hit on second parse)."""
    entries1 = list(DevignDataset())
    assert len(entries1) > 0

    entries2 = list(DevignDataset())

    assert len(entries1) == len(entries2)
