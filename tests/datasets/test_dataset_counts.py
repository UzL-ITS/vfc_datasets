"""Tests for validating dataset VFC/non-VFC counts."""

import inspect

import pytest

import vfc_datasets
from vfc_datasets import BaseDataset, DatasetCounts
from vfc_datasets.transformations.filters import collapse_to_commit_level

pytestmark = [pytest.mark.slow]


def _baseline_or_skip(dataset_class: type[BaseDataset]) -> DatasetCounts:
    """The dataset's baseline, or skip: `None` means it parses from live external state."""
    name = dataset_class.metadata.name
    counts = dataset_class.parsed_counts
    if counts is None:
        pytest.skip(f"{name}: no reproducible baseline (see module comment)")
    if counts == DatasetCounts():
        pytest.fail(f"{name}: no parsed_counts recorded; run the dataset and record them")
    return counts


def _get_datasets() -> list[type[BaseDataset]]:
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


@pytest.mark.parametrize("dataset_class", _get_datasets(), ids=lambda c: c.metadata.name)
def test_vfc_counts(dataset_class: type[BaseDataset]):
    """Verify the parsed VFC, non-VFC and project counts match the recorded baseline."""
    metadata = dataset_class.metadata
    counts = _baseline_or_skip(dataset_class)
    entries = list(dataset_class())

    # Before the collapse, which drops non-VFC rows a project may only appear in.
    project_count = len({e.project_url for e in entries})

    # Function-level datasets are aggregated to commit-level for VFC count validation
    if metadata.granularity == "function":
        entries = collapse_to_commit_level(entries)
        # De-duplicate and filter for VFCs
        entries = list({(e.project_url, e.commit_id): e for e in entries if e.is_vfc}.values())

    vfc_count = sum(1 for e in entries if e.is_vfc)
    non_vfc_count = sum(1 for e in entries if not e.is_vfc)

    assert vfc_count == counts.vfcs, f"{metadata.name}: VFC count mismatch"
    assert non_vfc_count == counts.non_vfcs, f"{metadata.name}: Non-VFC count mismatch"
    assert project_count == counts.projects, f"{metadata.name}: project count mismatch"


@pytest.mark.parametrize(
    "dataset_class",
    [d for d in _get_datasets() if d.metadata.granularity == "function"],
    ids=lambda c: c.metadata.name,
)
def test_function_counts(dataset_class: type[BaseDataset]):
    """Verify the parsed function counts match the recorded baseline."""
    metadata = dataset_class.metadata
    counts = _baseline_or_skip(dataset_class)
    entries = list(dataset_class())

    # Basic integrity check: all entries must specify a function name
    assert all(e.function_name for e in entries), f"{metadata.name}: missing function_name"

    # Identity uses `function_file`; `commit.files_changed` is empty without commit data.
    vulnerable_functions = {
        (e.project_url, e.commit_id, e.function_name, e.function_file) for e in entries if e.is_vfc
    }
    benign_functions = {
        (e.project_url, e.commit_id, e.function_name, e.function_file)
        for e in entries
        if not e.is_vfc
    }

    assert len(vulnerable_functions) == counts.vulnerable_functions, (
        f"{metadata.name}: Vulnerable function count mismatch"
    )
    assert len(benign_functions) == counts.benign_functions, (
        f"{metadata.name}: Benign function count mismatch"
    )
