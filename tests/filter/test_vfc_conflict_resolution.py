from dataset_entry import DatasetEntry
from transformations.filters.duplicates import (
    deduplicate_function_level,
    deduplicate_within_repository,
)


def test_vfc_conflict_excludes_entries():
    entries = [
        DatasetEntry(
            project_url="https://github.com/test/repo",
            commit_id="abc123",
            is_vfc=True,
            src_datasets={"dataset1"},
        ),
        DatasetEntry(
            project_url="https://github.com/test/repo",
            commit_id="abc123",
            is_vfc=False,  # Conflicting VFC status
            src_datasets={"dataset2"},
        ),
    ]

    result = deduplicate_function_level(entries)

    # Conflicting entries should be excluded entirely
    assert len(result) == 0


def test_successful_merge_same_vfc_status():
    entries = [
        DatasetEntry(
            project_url="https://github.com/test/repo",
            commit_id="abc123",
            is_vfc=True,
            src_datasets={"dataset1"},
            cve_ids={"CVE-2021-1234"},
        ),
        DatasetEntry(
            project_url="https://github.com/test/repo",
            commit_id="abc123",
            is_vfc=True,
            src_datasets={"dataset2"},
            cve_ids={"CVE-2021-5678"},
        ),
    ]

    result = deduplicate_function_level(entries)

    assert len(result) == 1
    merged = result[0]
    assert merged.is_vfc
    assert merged.commit_id == "abc123"
    assert merged.src_datasets == {"dataset1", "dataset2"}
    assert merged.cve_ids == {"CVE-2021-1234", "CVE-2021-5678"}


def test_merge_duplicates_excludes_vfc_conflicts():
    entries = [
        # Group 1: No conflict, should be merged
        DatasetEntry(
            project_url="https://github.com/test/repo1",
            commit_id="aaa111",
            is_vfc=True,
            src_datasets={"dataset1"},
        ),
        DatasetEntry(
            project_url="https://github.com/test/repo1",
            commit_id="aaa111",
            is_vfc=True,
            src_datasets={"dataset2"},
        ),
        # Group 2: VFC conflict, should be excluded
        DatasetEntry(
            project_url="https://github.com/test/repo2",
            commit_id="bbb222",
            is_vfc=True,
            src_datasets={"dataset1"},
        ),
        DatasetEntry(
            project_url="https://github.com/test/repo2",
            commit_id="bbb222",
            is_vfc=False,  # Conflict!
            src_datasets={"dataset3"},
        ),
        # Group 3: Single entry, no conflict
        DatasetEntry(
            project_url="https://github.com/test/repo3",
            commit_id="ccc333",
            is_vfc=False,
            src_datasets={"dataset4"},
        ),
    ]

    filtered = deduplicate_function_level(entries)

    # Should have 2 entries: merged group 1 and single entry from group 3
    # Group 2 should be excluded due to VFC conflict
    assert len(filtered) == 2

    # Check that conflicting entries are not in the result
    repo2_entries = [e for e in filtered if "repo2" in e.project_url]
    assert len(repo2_entries) == 0

    # Check that non-conflicting entries are present
    repo1_entries = [e for e in filtered if "repo1" in e.project_url]
    assert len(repo1_entries) == 1
    assert repo1_entries[0].src_datasets == {"dataset1", "dataset2"}

    repo3_entries = [e for e in filtered if "repo3" in e.project_url]
    assert len(repo3_entries) == 1


def test_merge_unions_files_changed():
    entries = [
        DatasetEntry(
            project_url="https://github.com/test/repo",
            commit_id="abc123",
            is_vfc=True,
            src_datasets={"dataset1"},
            files_changed={"file1.py", "file2.py"},
        ),
        DatasetEntry(
            project_url="https://github.com/test/repo",
            commit_id="abc123",
            is_vfc=True,
            src_datasets={"dataset2"},
            files_changed={"file2.py", "file3.py"},
        ),
    ]

    result = deduplicate_function_level(entries)

    assert len(result) == 1
    assert result[0].files_changed == {"file1.py", "file2.py", "file3.py"}


def test_function_level_keeps_separate_functions():
    entries = [
        DatasetEntry(
            project_url="https://github.com/test/repo",
            commit_id="abc123",
            is_vfc=True,
            src_datasets={"dataset1"},
            function_name="func_a",
        ),
        DatasetEntry(
            project_url="https://github.com/test/repo",
            commit_id="abc123",
            is_vfc=True,
            src_datasets={"dataset2"},
            function_name="func_b",
        ),
    ]

    result = deduplicate_function_level(entries)

    # Different functions stay separate
    assert len(result) == 2
    assert {e.function_name for e in result} == {"func_a", "func_b"}


def test_commit_level_merges_different_functions():
    entries = [
        DatasetEntry(
            project_url="https://github.com/test/repo",
            commit_id="abc123",
            is_vfc=True,
            src_datasets={"dataset1"},
            function_name="func_a",
            cve_ids={"CVE-2021-1111"},
        ),
        DatasetEntry(
            project_url="https://github.com/test/repo",
            commit_id="abc123",
            is_vfc=True,
            src_datasets={"dataset2"},
            function_name="func_b",
            cve_ids={"CVE-2021-2222"},
        ),
    ]

    result = deduplicate_within_repository(entries)

    # Same commit merged, function_name cleared
    assert len(result) == 1
    assert result[0].function_name is None
    assert result[0].src_datasets == {"dataset1", "dataset2"}
    assert result[0].cve_ids == {"CVE-2021-1111", "CVE-2021-2222"}
