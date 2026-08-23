"""What datasets ship must mean the same as what enrichment produces.

Feeds git's own `show`/`diff` output for one commit to the shipped-format parsers, and
compares every field against the enrichment path.
"""

from collections.abc import Callable
from dataclasses import dataclass, fields
from pathlib import Path

import pytest
from git import Actor, Repo

from vfc_datasets.commit_data import CommitData, from_git_show, from_unified_diff
from vfc_datasets.transformations.enrichment.add_commit_data_local import _get_commit_info

AUTHOR = Actor("A B", "a@b.c")
MESSAGE = "Fix the overflow\n\nLonger body explaining why.\n"
# Not `config.MAX_DIFF_SIZE`: a small limit set in someone's `.env` would drop enrichment's
# diff and fail a test that is about formats, not size.
DIFF_LIMIT = 1_000_000


@pytest.fixture
def repo(tmp_path: Path):
    """A repo whose HEAD commit edits one file and adds another."""
    repo = Repo.init(tmp_path, initial_branch="main")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.c").write_text("old\nkeep\n")
    repo.index.add(["src/app.c"])
    repo.index.commit("Initial", author=AUTHOR, committer=AUTHOR)

    (tmp_path / "src" / "app.c").write_text("new\nkeep\n")
    (tmp_path / "docs.md").write_text("docs\n")
    repo.index.add(["src/app.c", "docs.md"])
    repo.index.commit(
        MESSAGE,
        author=AUTHOR,
        committer=AUTHOR,
        # Apart, so a field taking the wrong one shows up.
        author_date="1691155575 +0200",
        commit_date="1691155800 +0200",
    )
    with repo:
        yield repo


@dataclass(frozen=True)
class Format:
    """A format datasets ship in, and the fields it can carry."""

    name: str
    parse: Callable[[Repo, str], CommitData]
    supplies: frozenset[str]


FORMATS = [
    Format(
        "git-show",
        lambda repo, sha: from_git_show(repo.git.show(sha)),
        frozenset({"message", "diff", "files_changed", "authored_at"}),
    ),
    Format(
        "unified-diff",
        lambda repo, sha: from_unified_diff(repo.git.diff(f"{sha}~1", sha)),
        frozenset({"diff", "files_changed"}),
    ),
]


@pytest.mark.parametrize("fmt", FORMATS, ids=lambda fmt: fmt.name)
def test_shipped_format_agrees_with_enrichment(repo: Repo, fmt: Format):
    sha = repo.head.commit.hexsha
    enriched = _get_commit_info(repo, sha, max_diff_size=DIFF_LIMIT)
    assert enriched is not None

    shipped = fmt.parse(repo, sha)
    default = CommitData()
    carried = {
        f.name for f in fields(CommitData) if getattr(shipped, f.name) != getattr(default, f.name)
    }

    assert carried == fmt.supplies, "the format carries different fields than declared"
    for name in sorted(carried):
        assert getattr(shipped, name) == getattr(enriched, name), name


def test_only_a_rename_makes_the_file_lists_differ(repo: Repo):
    """`commit.stats` names both paths of a rename, a `diff --git` header only the new one."""
    repo.index.move(["docs.md", "guide.md"])
    sha = repo.index.commit("Rename docs", author=AUTHOR, committer=AUTHOR).hexsha

    enriched = _get_commit_info(repo, sha, max_diff_size=DIFF_LIMIT)
    assert enriched is not None
    shipped = from_git_show(repo.git.show(sha))

    assert shipped.files_changed == {"guide.md"}
    assert enriched.files_changed == {"docs.md", "guide.md"}
    assert shipped.message == enriched.message
    assert shipped.diff == enriched.diff
