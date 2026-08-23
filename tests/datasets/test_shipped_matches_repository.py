"""Does what a dataset ships describe the commit it names?

Samples raw rows and compares them against the commit in a local clone. Diff text is not
compared: it varies with the context and rename options whoever generated it used.

The only test reading real rows, so a column renamed upstream shows up here — the parse
cache keys off module source and cannot notice one.
"""

from pathlib import Path
from typing import Any

import pytest
from git import Repo

from vfc_datasets.base_dataset import BaseDataset
from vfc_datasets.commit_data import CommitData
from vfc_datasets.config import MAX_DIFF_SIZE
from vfc_datasets.parsing_helpers import scrub_missing
from vfc_datasets.transformations.enrichment.add_commit_data_local import _get_commit_info
from vfc_datasets.utils.git.url import url_to_pathname

from .test_dataset_commit_data import SHIPPED_CASES

pytestmark = [pytest.mark.slow, pytest.mark.integration]

ROWS_TO_SCAN = 3000
SAMPLE_SIZE = 25

# No allowances: a dataset that cannot match gives the field up instead. See `cleanvul.py`.


def _squash(text: str | None) -> str:
    """Whitespace-insensitive form: sources reflow a message, they must not reword it."""
    return "".join((text or "").split())


def _local_clone(project_url: str) -> Path | None:
    """The clone, if already on disk — this never clones anything itself."""
    path = Path(url_to_pathname(project_url))
    return path if path.exists() else None


def _sample_rows(dataset: BaseDataset) -> list[dict[str, Any]]:
    frame = dataset._load_data()
    if len(frame) > ROWS_TO_SCAN:
        frame = frame.sample(ROWS_TO_SCAN, random_state=0)
    # `scrub_missing`, not a copy of it: these rows must reach the hooks as `_parse` feeds them.
    return [scrub_missing(row) for row in frame.to_dict(orient="records")]


@pytest.mark.parametrize(
    "dataset_class",
    [case.dataset for case in SHIPPED_CASES],
    ids=lambda cls: cls.metadata.name,
)
def test_shipped_commit_data_matches_the_repository(dataset_class: type[BaseDataset]):
    dataset = dataset_class()
    repos: dict[Path, Repo] = {}
    mismatches: list[str] = []
    compared = shipped_rows = uncloned = unresolved = 0

    try:
        for row in _sample_rows(dataset):
            if compared >= SAMPLE_SIZE:
                break
            entry = dataset._parse_row(dict(row))
            if entry is None:
                continue
            shipped = dataset._shipped_commit_data(dict(row))
            if shipped == CommitData():
                continue
            shipped_rows += 1
            path = _local_clone(entry.project_url)
            if path is None:
                uncloned += 1
                continue
            if path not in repos:
                repos[path] = Repo(path)
            actual = _get_commit_info(repos[path], entry.commit_id, max_diff_size=MAX_DIFF_SIZE)
            if actual is None:
                unresolved += 1
                continue

            compared += 1
            renamed = _has_rename(repos[path], entry.commit_id)
            mismatches += _compare(entry.commit_id, shipped, actual, renamed=renamed)
    finally:
        for repo in repos.values():
            repo.close()

    # A renamed source column ships nothing, which the skip below would blame on clones.
    assert shipped_rows, "no sampled row ships commit data; check the source column names"

    if not compared:
        pytest.skip(f"nothing to compare: {uncloned} uncloned, {unresolved} not in the clone")

    assert not mismatches, f"{len(mismatches)} of {compared}\n" + "\n".join(mismatches)


def _has_rename(repo: Repo, commit_id: str) -> bool:
    """Whether the commit renames a file.

    Asked of the tree, not of `actual.diff`, which is empty for a commit over `MAX_DIFF_SIZE`.
    """
    commit = repo.commit(commit_id)
    return bool(commit.parents) and any(d.renamed_file for d in commit.parents[0].diff(commit))


def _compare(
    commit_id: str, shipped: CommitData, actual: CommitData, *, renamed: bool
) -> list[str]:
    """Every shipped field that disagrees with the repository, as readable lines."""
    problems: list[str] = []

    if shipped.message is not None and _squash(shipped.message) != _squash(actual.message):
        problems.append(
            f"{commit_id[:10]} message: {shipped.message!r:.80} != {actual.message!r:.80}"
        )

    # Renames are the one thing counted differently: `commit.stats` names both paths.
    if shipped.files_changed and not renamed and shipped.files_changed != actual.files_changed:
        problems.append(
            f"{commit_id[:10]} files_changed: "
            f"{sorted(shipped.files_changed)} != {sorted(actual.files_changed)}"
        )

    for field in ("authored_at", "committed_at"):
        value = getattr(shipped, field)
        if value is not None and value != getattr(actual, field):
            problems.append(f"{commit_id[:10]} {field}: {value} != {getattr(actual, field)}")

    return problems
