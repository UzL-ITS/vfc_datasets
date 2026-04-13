"""Tests for CloneStrategy helpers in utils.git.repository."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from git import Repo

from vfc_datasets.utils.git.repository import _is_partial_clone, _upgrade_to_full


def _init_bare_source(path: Path) -> Path:
    """Create a small bare source repo with a couple of commits to clone from."""
    work = Repo.init(path / "work")
    with work.config_writer() as cw:
        cw.set_value("user", "email", "t@t")
        cw.set_value("user", "name", "t")
    file = Path(work.working_dir) / "a.txt"
    file.write_text("hello\n")
    work.index.add(["a.txt"])
    work.index.commit("first")
    file.write_text("hello world\n")
    work.index.add(["a.txt"])
    work.index.commit("second")

    bare = Repo.clone_from(work.working_dir, path / "src.git", bare=True)
    with bare.config_writer() as cw:
        cw.set_value("uploadpack", "allowFilter", "true")
    return Path(bare.git_dir)


def _blobless_clone(bare: Path, dest: Path) -> Repo:
    return Repo.clone_from(
        f"file://{bare}", dest, multi_options=["--filter=blob:none", "--no-checkout"]
    )


def _full_clone(bare: Path, dest: Path) -> Repo:
    return Repo.clone_from(f"file://{bare}", dest, multi_options=["--no-checkout"])


@pytest.mark.integration
class TestIsPartialClone:
    def test_blobless_clone_detected(self, tmp_path):
        bare = _init_bare_source(tmp_path)
        repo = _blobless_clone(bare, tmp_path / "clone")
        assert _is_partial_clone(repo) is True

    def test_full_clone_not_partial(self, tmp_path):
        bare = _init_bare_source(tmp_path)
        repo = _full_clone(bare, tmp_path / "clone")
        assert _is_partial_clone(repo) is False


@pytest.mark.integration
class TestUpgradeToFull:
    def test_unsets_filter_config(self, tmp_path):
        bare = _init_bare_source(tmp_path)
        repo = _blobless_clone(bare, tmp_path / "clone")
        assert _is_partial_clone(repo)

        assert _upgrade_to_full(repo, timeout=60) is True
        assert not _is_partial_clone(repo)

    def test_returns_false_when_remote_gone(self, tmp_path):
        """If fetch fails, caller needs False so it can recover."""
        bare = _init_bare_source(tmp_path)
        repo = _blobless_clone(bare, tmp_path / "clone")
        shutil.rmtree(bare)  # Destroy the source so --refetch fails.
        assert _upgrade_to_full(repo, timeout=10) is False
