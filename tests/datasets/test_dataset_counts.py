"""Tests for validating dataset VFC/non-VFC counts."""

import inspect

import pytest

import vfc_datasets
from transformations.filters import collapse_to_commit_level
from vfc_datasets import BaseDataset

pytestmark = [pytest.mark.slow]


def get_datasets() -> list[type[BaseDataset]]:
    """Discover all datasets."""
    return sorted(
        [
            cls
            for name in vfc_datasets.__all__
            if inspect.isclass(cls := getattr(vfc_datasets, name))
            and issubclass(cls, BaseDataset)
            and hasattr(cls, "metadata")
        ],
        key=lambda d: d.metadata.name,
    )


@pytest.mark.parametrize("dataset_class", get_datasets(), ids=lambda c: c.metadata.name)
def test_vfc_counts(dataset_class: type[BaseDataset]):
    """Verify that parsed counts meet thresholds defined in metadata."""
    metadata = dataset_class.metadata
    entries = list(dataset_class())

    # Function-level datasets are aggregated to commit-level for VFC count validation
    if metadata.granularity == "function":
        entries = collapse_to_commit_level(entries)
        # De-duplicate and filter for VFCs
        entries = list({(e.project_url, e.commit_id): e for e in entries if e.is_vfc}.values())

    vfc_count = sum(1 for e in entries if e.is_vfc)
    non_vfc_count = sum(1 for e in entries if not e.is_vfc)

    assert vfc_count == metadata.vfcs, f"{metadata.name}: VFC count mismatch"
    assert non_vfc_count == metadata.non_vfcs, f"{metadata.name}: Non-VFC count mismatch"


@pytest.mark.parametrize(
    "dataset_class",
    [d for d in get_datasets() if d.metadata.granularity == "function"],
    ids=lambda c: c.metadata.name,
)
def test_function_counts(dataset_class: type[BaseDataset]):
    """Test unique function counts for function-level datasets."""
    metadata = dataset_class.metadata
    entries = list(dataset_class())

    # Basic integrity check: all entries must specify a function name
    assert all(e.function_name for e in entries), f"{metadata.name}: missing function_name"

    # Count unique functions by (URL, Commit, Name, Files)
    vulnerable_functions = {
        (e.project_url, e.commit_id, e.function_name, frozenset(e.files_changed))
        for e in entries
        if e.is_vfc
    }
    benign_functions = {
        (e.project_url, e.commit_id, e.function_name, frozenset(e.files_changed))
        for e in entries
        if not e.is_vfc
    }

    assert len(vulnerable_functions) == metadata.vulnerable_functions, (
        f"{metadata.name}: Vulnerable function count mismatch"
    )
    assert len(benign_functions) == metadata.benign_functions, (
        f"{metadata.name}: Benign function count mismatch"
    )
