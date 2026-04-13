"""Tests for batch_processing clone-strategy selection."""

from vfc_datasets.config import FULL_CLONE_THRESHOLD
from vfc_datasets.transformations.enrichment.batch_processing import _pick_clone_strategy
from vfc_datasets.utils.git.repository import CloneStrategy


class TestPickCloneStrategy:
    def test_below_threshold_is_blobless(self):
        commits = {"https://github.com/a/a": {"c1", "c2", "c3"}}
        assert _pick_clone_strategy(commits, threshold=10) == {
            "https://github.com/a/a": CloneStrategy.BLOBLESS
        }

    def test_at_threshold_is_full(self):
        commits = {"https://github.com/a/a": {f"c{i}" for i in range(10)}}
        assert _pick_clone_strategy(commits, threshold=10) == {
            "https://github.com/a/a": CloneStrategy.FULL
        }

    def test_mixed_repos(self):
        commits = {
            "https://github.com/small/repo": {"c1"},
            "https://github.com/big/repo": {f"c{i}" for i in range(50)},
        }
        result = _pick_clone_strategy(commits, threshold=10)
        assert result["https://github.com/small/repo"] is CloneStrategy.BLOBLESS
        assert result["https://github.com/big/repo"] is CloneStrategy.FULL

    def test_default_threshold_matches_config(self):
        commits = {
            "https://github.com/a/a": {f"c{i}" for i in range(FULL_CLONE_THRESHOLD)},
            "https://github.com/b/b": {f"c{i}" for i in range(FULL_CLONE_THRESHOLD - 1)},
        }
        result = _pick_clone_strategy(commits)
        assert result["https://github.com/a/a"] is CloneStrategy.FULL
        assert result["https://github.com/b/b"] is CloneStrategy.BLOBLESS

    def test_empty_input(self):
        assert _pick_clone_strategy({}) == {}
