"""Tests for repository relationship detection."""

import pytest

from vfc_datasets.dataset_entry import DatasetEntry
from vfc_datasets.utils.git.commit import TEMPLATE_FILE_PATTERNS, is_template_file
from vfc_datasets.utils.relationships.discovery import (
    _build_edges_from_signatures,
    _find_shared_commits,
    _sample_commits,
    compute_config_hash,
)
from vfc_datasets.utils.relationships.models import (
    RelationshipEdge,
    RepositoryGroup,
    RepositoryRelationships,
    _find_connected_groups,
    link_key,
)
from vfc_datasets.utils.relationships.validation import _find_suspicious_project_relationships


class TestLinkKey:
    def test_sorts_urls(self) -> None:
        assert link_key("b", "a") == ("a", "b")
        assert link_key("a", "b") == ("a", "b")

    def test_consistent_key(self) -> None:
        assert link_key("x", "y") == link_key("y", "x")


class TestRelationshipEdge:
    def test_key_property(self) -> None:
        edge = RelationshipEdge("b", "a", "local_history")
        assert edge.key == ("a", "b")

    def test_key_with_commit_ids(self) -> None:
        edge = RelationshipEdge("x", "y", "github_fork", {"c1", "c2"})
        assert edge.key == ("x", "y")
        assert edge.commit_ids == {"c1", "c2"}


class TestFindConnectedGroups:
    def test_single_edge(self) -> None:
        edges = [RelationshipEdge("a", "b", "github_fork")]
        groups = _find_connected_groups(edges)
        assert len(groups) == 1
        urls, methods, _ = groups[0]
        assert urls == {"a", "b"}
        assert methods == {"github_fork"}

    def test_multiple_disconnected_edges(self) -> None:
        edges = [
            RelationshipEdge("a", "b", "github_fork"),
            RelationshipEdge("c", "d", "local_history"),
        ]
        groups = _find_connected_groups(edges)
        assert len(groups) == 2

    def test_connected_edges_form_single_group(self) -> None:
        edges = [
            RelationshipEdge("a", "b", "github_fork"),
            RelationshipEdge("b", "c", "local_history"),
        ]
        groups = _find_connected_groups(edges)
        assert len(groups) == 1
        urls, methods, _ = groups[0]
        assert urls == {"a", "b", "c"}
        assert methods == {"github_fork", "local_history"}

    def test_collects_commit_ids(self) -> None:
        edges = [
            RelationshipEdge("a", "b", "local_history", {"c1", "c2"}),
        ]
        groups = _find_connected_groups(edges)
        assert len(groups) == 1
        _, _, links = groups[0]
        assert links["c1"] == {"a", "b"}
        assert links["c2"] == {"a", "b"}

    def test_merges_commit_urls(self) -> None:
        edges = [
            RelationshipEdge("a", "b", "local_history", {"c1"}),
            RelationshipEdge("b", "c", "local_history", {"c1"}),
        ]
        groups = _find_connected_groups(edges)
        assert len(groups) == 1
        _, _, links = groups[0]
        assert links["c1"] == {"a", "b", "c"}


class TestRepositoryGroup:
    def test_to_dict_serialization(self) -> None:
        group = RepositoryGroup(
            group_id=1,
            project_urls={"https://github.com/a/b", "https://github.com/c/d"},
            detection_methods={"github_fork", "local_history"},
            canonical_url="https://github.com/a/b",
            links={
                "abc123": {"https://github.com/a/b", "https://github.com/c/d"},
                "def456": {"https://github.com/a/b", "https://github.com/c/d"},
            },
        )
        d = group.to_dict()

        assert d["group_id"] == 1
        assert d["project_urls"] == ["https://github.com/a/b", "https://github.com/c/d"]
        assert d["detection_methods"] == ["github_fork", "local_history"]
        assert d["canonical_url"] == "https://github.com/a/b"
        assert "abc123" in d["links"]
        assert d["links"]["abc123"] == ["https://github.com/a/b", "https://github.com/c/d"]

    def test_to_dict_sorts_lists(self) -> None:
        group = RepositoryGroup(
            group_id=1,
            project_urls={"z", "a", "m"},
            detection_methods={"z", "a"},
            links={"commit1": {"z", "a"}},
        )
        d = group.to_dict()

        assert d["project_urls"] == ["a", "m", "z"]
        assert d["detection_methods"] == ["a", "z"]
        assert d["links"]["commit1"] == ["a", "z"]

    def test_from_dict_deserialization(self) -> None:
        data = {
            "group_id": 1,
            "project_urls": ["https://github.com/a/b", "https://github.com/c/d"],
            "detection_methods": ["github_fork"],
            "canonical_url": "https://github.com/a/b",
            "links": {"abc123": ["https://github.com/a/b", "https://github.com/c/d"]},
        }
        group = RepositoryGroup.from_dict(data)

        assert group.group_id == 1
        assert group.project_urls == {"https://github.com/a/b", "https://github.com/c/d"}
        assert group.detection_methods == {"github_fork"}
        assert group.canonical_url == "https://github.com/a/b"
        assert "abc123" in group.links
        assert group.links["abc123"] == {"https://github.com/a/b", "https://github.com/c/d"}

    def test_from_dict_handles_missing_optional_fields(self) -> None:
        data = {
            "group_id": 1,
            "project_urls": ["https://github.com/a/b"],
        }
        group = RepositoryGroup.from_dict(data)

        assert group.canonical_url is None
        assert group.detection_methods == set()
        assert group.links == {}
        assert group.shared_commits == set()

    def test_roundtrip_serialization(self) -> None:
        original = RepositoryGroup(
            group_id=42,
            project_urls={"https://github.com/a/b", "https://github.com/c/d"},
            detection_methods={"local_history"},
            canonical_url="https://github.com/a/b",
            links={"commit1": {"https://github.com/a/b", "https://github.com/c/d"}},
        )
        restored = RepositoryGroup.from_dict(original.to_dict())

        assert restored.group_id == original.group_id
        assert restored.project_urls == original.project_urls
        assert restored.detection_methods == original.detection_methods
        assert restored.links == original.links
        assert restored.canonical_url == original.canonical_url

    def test_shared_commits_property(self) -> None:
        group = RepositoryGroup(
            group_id=0,
            project_urls={"a", "b", "c"},
            detection_methods={"local_history"},
            links={
                "commit1": {"a", "b"},
                "commit2": {"a", "b"},
                "commit3": {"b", "c"},
            },
        )
        assert group.shared_commits == {"commit1", "commit2", "commit3"}

    def test_shared_commits_empty_when_no_links(self) -> None:
        group = RepositoryGroup(
            group_id=0,
            project_urls={"a", "b"},
            detection_methods={"github_fork"},
        )
        assert group.shared_commits == set()

    def test_add_link(self) -> None:
        group = RepositoryGroup(
            group_id=0,
            project_urls={"a", "b"},
            detection_methods={"local_history"},
        )
        group.add_link("a", "b", "commit1")
        group.add_link("b", "a", "commit2")

        assert len(group.links) == 2
        assert group.links["commit1"] == {"a", "b"}
        assert group.links["commit2"] == {"a", "b"}

    def test_add_link_accumulates_urls(self) -> None:
        group = RepositoryGroup(
            group_id=0,
            project_urls={"a", "b", "c"},
            detection_methods={"local_history"},
        )
        group.add_link("a", "b", "commit1")
        group.add_link("b", "c", "commit1")

        assert group.links["commit1"] == {"a", "b", "c"}


class TestRepositoryRelationships:
    def test_get_group_returns_correct_group(self) -> None:
        group = RepositoryGroup(
            group_id=0,
            project_urls={"https://github.com/a/b", "https://github.com/c/d"},
            detection_methods={"github_fork"},
        )
        relationships = RepositoryRelationships(
            groups=[group],
            url_to_group_id={
                "https://github.com/a/b": 0,
                "https://github.com/c/d": 0,
            },
        )

        result = relationships.get_group("https://github.com/a/b")
        assert result is not None
        assert result.group_id == 0
        assert "https://github.com/a/b" in result.project_urls

    def test_get_group_returns_none_for_unknown_url(self) -> None:
        relationships = RepositoryRelationships()
        assert relationships.get_group("https://github.com/unknown/repo") is None

    def test_are_related_true_for_same_group(self) -> None:
        relationships = RepositoryRelationships(
            groups=[],
            url_to_group_id={
                "https://github.com/a/b": 0,
                "https://github.com/c/d": 0,
            },
        )
        assert relationships.are_related(
            "https://github.com/a/b",
            "https://github.com/c/d",
        )

    def test_are_related_false_for_different_groups(self) -> None:
        relationships = RepositoryRelationships(
            groups=[],
            url_to_group_id={
                "https://github.com/a/b": 0,
                "https://github.com/c/d": 1,
            },
        )
        assert not relationships.are_related(
            "https://github.com/a/b",
            "https://github.com/c/d",
        )

    def test_are_related_false_for_unknown_urls(self) -> None:
        relationships = RepositoryRelationships(
            groups=[],
            url_to_group_id={"https://github.com/a/b": 0},
        )
        assert not relationships.are_related(
            "https://github.com/a/b",
            "https://github.com/unknown/repo",
        )
        assert not relationships.are_related(
            "https://github.com/unknown/repo",
            "https://github.com/a/b",
        )

    def test_from_edges_creates_groups(self) -> None:
        edges = [
            RelationshipEdge("a", "b", "github_fork"),
            RelationshipEdge("b", "c", "local_history", {"commit1"}),
        ]
        relationships = RepositoryRelationships.from_edges(edges)

        assert len(relationships.groups) == 1
        assert relationships.are_related("a", "b")
        assert relationships.are_related("b", "c")
        assert relationships.are_related("a", "c")

        group = relationships.get_group("a")
        assert group is not None
        assert group.detection_methods == {"github_fork", "local_history"}
        assert group.shared_commits == {"commit1"}

    def test_from_edges_with_canonical_urls(self) -> None:
        edges = [RelationshipEdge("fork", "source", "github_fork")]
        url_to_source = {"fork": "source"}
        relationships = RepositoryRelationships.from_edges(edges, url_to_source)

        group = relationships.get_group("fork")
        assert group is not None
        assert group.canonical_url == "source"

    def test_from_edges_canonical_falls_back_to_most_commits(self) -> None:
        """When fork API has no answer, prefer the URL with the most commits."""
        edges = [RelationshipEdge("fork1", "fork2", "local_history", {"c1"})]
        commit_history = {"fork1": ["c1", "c2"], "fork2": ["c1", "c2", "c3", "c4"]}
        relationships = RepositoryRelationships.from_edges(
            edges, commit_history=commit_history
        )
        group = relationships.get_group("fork1")
        assert group is not None
        assert group.canonical_url == "fork2"

    def test_from_edges_canonical_prefers_fork_root_over_commit_count(self) -> None:
        """A known fork-chain root wins even if a fork has more commits locally."""
        edges = [RelationshipEdge("fork", "source", "github_fork")]
        url_to_source = {"fork": "source"}
        commit_history = {"fork": ["c1", "c2", "c3"], "source": ["c1"]}
        relationships = RepositoryRelationships.from_edges(
            edges, url_to_source, commit_history=commit_history
        )
        group = relationships.get_group("fork")
        assert group is not None
        assert group.canonical_url == "source"

    def test_from_edges_canonical_none_without_commit_history(self) -> None:
        """No fork data and no commit history: canonical stays None."""
        edges = [RelationshipEdge("a", "b", "local_history")]
        relationships = RepositoryRelationships.from_edges(edges)
        group = relationships.get_group("a")
        assert group is not None
        assert group.canonical_url is None

    def test_from_edges_filters_singletons(self) -> None:
        edges = [RelationshipEdge("a", "b", "github_fork")]
        relationships = RepositoryRelationships.from_edges(edges)

        # Should have one group with 2 URLs
        assert len(relationships.groups) == 1
        assert len(relationships.url_to_group_id) == 2

    def test_to_dict_serialization(self) -> None:
        group = RepositoryGroup(
            group_id=0,
            project_urls={"a", "b"},
            detection_methods={"github_fork"},
        )
        relationships = RepositoryRelationships(
            groups=[group],
            url_to_group_id={"a": 0, "b": 0},
        )

        d = relationships.to_dict()
        assert "groups" in d
        assert "url_to_group_id" in d
        assert len(d["groups"]) == 1

    def test_from_dict_deserialization(self) -> None:
        data = {
            "groups": [
                {
                    "group_id": 0,
                    "project_urls": ["a", "b"],
                    "detection_methods": ["github_fork"],
                    "links": {},
                }
            ],
            "url_to_group_id": {"a": 0, "b": 0},
        }
        relationships = RepositoryRelationships.from_dict(data)

        assert len(relationships.groups) == 1
        assert relationships.are_related("a", "b")
        assert relationships.get_group("a") is not None


class TestIsTemplateFile:
    @pytest.mark.parametrize(
        "filename",
        [
            "README.md",
            "readme.md",
            "README",
            "LICENSE",
            "license.txt",
            ".gitignore",
            "package.json",
            "setup.py",
            "pyproject.toml",
            "requirements.txt",
            "Makefile",
            "Dockerfile",
            "go.mod",
            "Cargo.toml",
        ],
    )
    def test_template_files_detected(self, filename: str) -> None:
        assert is_template_file(filename)

    @pytest.mark.parametrize(
        "filename",
        ["main.py", "index.js", "app.go", "lib.rs", "utils.c", "handler.java", "component.tsx"],
    )
    def test_code_files_not_template(self, filename: str) -> None:
        assert not is_template_file(filename)

    def test_extracts_basename_from_path(self) -> None:
        assert is_template_file("src/README.md")
        assert is_template_file("deep/nested/path/LICENSE")
        assert not is_template_file("src/main.py")

    def test_case_insensitive(self) -> None:
        assert is_template_file("README.MD")
        assert is_template_file("License")
        assert is_template_file("MAKEFILE")

    def test_template_patterns_is_frozenset(self) -> None:
        assert isinstance(TEMPLATE_FILE_PATTERNS, frozenset)


class TestFindSuspiciousProjectRelationships:
    def test_github_fork_groups_not_suspicious(self) -> None:
        url1 = "https://github.com/a/foo"
        url2 = "https://github.com/b/bar"
        group = RepositoryGroup(
            group_id=0,
            project_urls={url1, url2},
            detection_methods={"github_fork"},
        )
        relationships = RepositoryRelationships(
            groups=[group],
            url_to_group_id={url1: 0, url2: 0},
        )
        fork_edges = [RelationshipEdge(url1, url2, "github_fork")]

        _find_suspicious_project_relationships(relationships, fork_edges)
        assert group.suspicious_urls == set()

    def test_multi_commit_groups_not_suspicious(self) -> None:
        url1 = "https://github.com/a/foo"
        url2 = "https://github.com/b/bar"
        group = RepositoryGroup(
            group_id=0,
            project_urls={url1, url2},
            detection_methods={"local_history"},
            links={"commit1": {url1, url2}, "commit2": {url1, url2}},
        )
        relationships = RepositoryRelationships(
            groups=[group],
            url_to_group_id={url1: 0, url2: 0},
        )

        _find_suspicious_project_relationships(relationships, [])
        assert group.suspicious_urls == set()

    def test_single_commit_not_in_fork_network_is_suspicious(self) -> None:
        url1 = "https://github.com/neovim/neovim"
        url2 = "https://github.com/rabbitmq/rabbitmq-server"
        group = RepositoryGroup(
            group_id=0,
            project_urls={url1, url2},
            detection_methods={"local_history"},
            links={"commit1": {url1, url2}},
        )
        relationships = RepositoryRelationships(
            groups=[group],
            url_to_group_id={url1: 0, url2: 0},
        )

        _find_suspicious_project_relationships(relationships, [])
        # One URL is reachable (start), other is suspicious
        assert len(group.suspicious_urls) == 1

    def test_single_commit_in_fork_network_not_suspicious(self) -> None:
        url1 = "https://github.com/numpy/numpy"
        url2 = "https://github.com/numpy/numpy-fork"
        group = RepositoryGroup(
            group_id=0,
            project_urls={url1, url2},
            detection_methods={"local_history"},
            links={"commit1": {url1, url2}},
        )
        relationships = RepositoryRelationships(
            groups=[group],
            url_to_group_id={url1: 0, url2: 0},
        )
        fork_edges = [RelationshipEdge(url1, url2, "github_fork")]

        _find_suspicious_project_relationships(relationships, fork_edges)
        assert group.suspicious_urls == set()

    def test_non_github_urls_flagged_with_single_commit(self) -> None:
        url1 = "https://bitbucket.org/owner/repo1"
        url2 = "https://gitlab.com/owner/repo2"
        group = RepositoryGroup(
            group_id=0,
            project_urls={url1, url2},
            detection_methods={"local_history"},
            links={"commit1": {url1, url2}},
        )
        relationships = RepositoryRelationships(
            groups=[group],
            url_to_group_id={url1: 0, url2: 0},
        )

        _find_suspicious_project_relationships(relationships, [])
        # One URL reachable (start), other suspicious
        assert len(group.suspicious_urls) == 1

    def test_url_not_in_links_is_suspicious(self) -> None:
        """URL in group but not connected via any links is suspicious."""
        url1 = "https://github.com/owner/repo1"
        url2 = "https://github.com/other/repo2"
        url3 = "https://gitlab.com/third/repo3"
        group = RepositoryGroup(
            group_id=0,
            project_urls={url1, url2, url3},
            detection_methods={"local_history"},
            links={"commit1": {url1, url2}, "commit2": {url1, url2}},  # url3 not in links
        )
        relationships = RepositoryRelationships(
            groups=[group],
            url_to_group_id={url1: 0, url2: 0, url3: 0},
        )

        _find_suspicious_project_relationships(relationships, [])
        assert group.suspicious_urls == {url3}

    def test_fork_validated_but_third_url_suspicious(self) -> None:
        """Two URLs validated via fork, third URL only has 1 commit."""
        url1 = "https://github.com/numpy/numpy"
        url2 = "https://github.com/numpy/numpy-fork"
        url3 = "https://gitlab.com/unrelated/repo"
        group = RepositoryGroup(
            group_id=0,
            project_urls={url1, url2, url3},
            detection_methods={"github_fork", "local_history"},
            links={"commit1": {url1, url3}},  # url3 connected via single commit only
        )
        relationships = RepositoryRelationships(
            groups=[group],
            url_to_group_id={url1: 0, url2: 0, url3: 0},
        )
        fork_edges = [RelationshipEdge(url1, url2, "github_fork")]

        _find_suspicious_project_relationships(relationships, fork_edges)
        # url1 and url2 validated via fork, url3 suspicious (single commit)
        assert group.suspicious_urls == {url3}


class TestSampleCommits:
    def test_empty_history_returns_empty(self) -> None:
        assert _sample_commits(set(), {}, num_recent_commits=10, num_early_commits=10, skip_oldest_commits=0) == set()

    def test_url_with_no_commits_skipped(self) -> None:
        sampled = _sample_commits({"a"}, {"a": []}, num_recent_commits=10, num_early_commits=10, skip_oldest_commits=0)
        assert sampled == set()

    def test_short_history_returns_only_recent(self) -> None:
        # 5 commits, num_recent=10: all 5 are recent. Early sampling skipped because
        # len(commits) <= num_early + skip_oldest.
        commits = [f"c{i}" for i in range(5)]
        sampled = _sample_commits(
            {"a"}, {"a": commits}, num_recent_commits=10, num_early_commits=10, skip_oldest_commits=0
        )
        assert sampled == set(commits)

    def test_recent_commits_sampled_from_start(self) -> None:
        # Commit history is newest-first. num_early > len(commits) so early branch skipped.
        commits = [f"c{i}" for i in range(100)]
        sampled = _sample_commits(
            {"a"}, {"a": commits}, num_recent_commits=3, num_early_commits=200, skip_oldest_commits=0
        )
        assert sampled == {"c0", "c1", "c2"}

    def test_num_early_zero_skips_early_branch(self) -> None:
        # num_early=0 must not pull any early commits regardless of skip_oldest.
        commits = [f"c{i}" for i in range(100)]
        sampled = _sample_commits(
            {"a"}, {"a": commits}, num_recent_commits=3, num_early_commits=0, skip_oldest_commits=0
        )
        assert sampled == {"c0", "c1", "c2"}

    def test_early_commits_sampled_from_end_with_skip(self) -> None:
        # 100 commits, num_early=3, skip_oldest=2 → take c95, c96, c97 (skip c98, c99).
        commits = [f"c{i}" for i in range(100)]
        sampled = _sample_commits(
            {"a"}, {"a": commits}, num_recent_commits=0, num_early_commits=3, skip_oldest_commits=2
        )
        assert sampled == {"c95", "c96", "c97"}

    def test_early_commits_no_skip_uses_full_tail(self) -> None:
        commits = [f"c{i}" for i in range(100)]
        sampled = _sample_commits(
            {"a"}, {"a": commits}, num_recent_commits=0, num_early_commits=3, skip_oldest_commits=0
        )
        assert sampled == {"c97", "c98", "c99"}

    def test_combines_across_repos(self) -> None:
        sampled = _sample_commits(
            {"a", "b"},
            {"a": ["c1", "c2"], "b": ["c3", "c4"]},
            num_recent_commits=2,
            num_early_commits=0,
            skip_oldest_commits=0,
        )
        assert sampled == {"c1", "c2", "c3", "c4"}


class TestFindSharedCommits:
    def test_no_shared_returns_empty(self) -> None:
        result = _find_shared_commits(
            {"a", "b"},
            {"a": ["c1"], "b": ["c2"]},
            sampled_commits={"c1", "c2"},
        )
        assert result == []

    def test_pair_sharing_one_commit(self) -> None:
        result = _find_shared_commits(
            {"a", "b"},
            {"a": ["c1"], "b": ["c1"]},
            sampled_commits={"c1"},
        )
        assert result == [("c1", {"a", "b"})]

    def test_three_repos_sharing_commit(self) -> None:
        result = _find_shared_commits(
            {"a", "b", "c"},
            {"a": ["c1"], "b": ["c1"], "c": ["c1"]},
            sampled_commits={"c1"},
        )
        assert len(result) == 1
        assert result[0] == ("c1", {"a", "b", "c"})

    def test_unsampled_commits_ignored(self) -> None:
        result = _find_shared_commits(
            {"a", "b"},
            {"a": ["c1", "c2"], "b": ["c1", "c2"]},
            sampled_commits={"c1"},  # c2 shared but not sampled
        )
        assert result == [("c1", {"a", "b"})]

    def test_results_sorted_by_url_count(self) -> None:
        # c2 is in 3 repos, c1 in 2 → c1 first (smaller group), then c2.
        result = _find_shared_commits(
            {"a", "b", "c"},
            {"a": ["c1", "c2"], "b": ["c1", "c2"], "c": ["c2"]},
            sampled_commits={"c1", "c2"},
        )
        assert [cid for cid, _ in result] == ["c1", "c2"]


class TestBuildEdgesFromSignatures:
    HIGH_OVERLAP = {"a": ["c1", "c2", "c3"], "b": ["c1", "c2", "c3"], "c": ["c1", "c2", "c3"]}

    def test_empty_input_returns_no_edges(self) -> None:
        assert _build_edges_from_signatures([], {}, {}, 0.1) == []

    def test_substantial_signature_creates_edge(self) -> None:
        edges = _build_edges_from_signatures(
            [("c1", {"a", "b"})],
            {"c1": ("content_hash", "files_hash")},
            self.HIGH_OVERLAP,
            0.1,
        )
        assert len(edges) == 1
        assert edges[0].key == ("a", "b")
        assert edges[0].method == "local_history"
        assert edges[0].commit_ids == {"c1"}

    def test_missing_signature_no_edge(self) -> None:
        edges = _build_edges_from_signatures(
            [("c1", {"a", "b"})], {}, self.HIGH_OVERLAP, 0.1
        )
        assert edges == []

    def test_none_signature_no_edge(self) -> None:
        edges = _build_edges_from_signatures(
            [("c1", {"a", "b"})], {"c1": None}, self.HIGH_OVERLAP, 0.1
        )
        assert edges == []

    def test_multiple_commits_same_pair_accumulate_commit_ids(self) -> None:
        sig = ("h", "f")
        edges = _build_edges_from_signatures(
            [("c1", {"a", "b"}), ("c2", {"a", "b"})],
            {"c1": sig, "c2": sig},
            self.HIGH_OVERLAP,
            0.1,
        )
        assert len(edges) == 1
        assert edges[0].commit_ids == {"c1", "c2"}

    def test_three_url_commit_creates_pairwise_edges(self) -> None:
        edges = _build_edges_from_signatures(
            [("c1", {"a", "b", "c"})],
            {"c1": ("h", "f")},
            self.HIGH_OVERLAP,
            0.1,
        )
        assert {e.key for e in edges} == {("a", "b"), ("a", "c"), ("b", "c")}

    def test_low_overlap_pair_rejected(self) -> None:
        # b shares only 1/100 commits with a, well below threshold.
        commit_history = {"a": [f"c{i}" for i in range(100)], "b": ["c0"] + [f"x{i}" for i in range(99)]}
        edges = _build_edges_from_signatures(
            [("c0", {"a", "b"})],
            {"c0": ("h", "f")},
            commit_history,
            0.1,
        )
        assert edges == []

    def test_overlap_threshold_at_zero_disables_gate(self) -> None:
        # Same low-overlap data as above, but threshold=0 admits everything.
        commit_history = {"a": [f"c{i}" for i in range(100)], "b": ["c0"] + [f"x{i}" for i in range(99)]}
        edges = _build_edges_from_signatures(
            [("c0", {"a", "b"})],
            {"c0": ("h", "f")},
            commit_history,
            0.0,
        )
        assert len(edges) == 1

    def test_mixed_cluster_only_high_overlap_pairs_kept(self) -> None:
        # 'real_a' and 'real_b' overlap fully; 'unrelated' shares only c0 with each.
        # Sizing matters: with 100-commit repos and one shared commit, overlap is
        # 1/100 = 0.01 — below the 0.1 threshold.
        shared_history = ["c0"] + [f"y{i}" for i in range(99)]
        commit_history = {
            "real_a": shared_history,
            "real_b": shared_history,
            "unrelated": ["c0"] + [f"x{i}" for i in range(99)],
        }
        edges = _build_edges_from_signatures(
            [("c0", {"real_a", "real_b", "unrelated"})],
            {"c0": ("h", "f")},
            commit_history,
            0.1,
        )
        assert {e.key for e in edges} == {("real_a", "real_b")}


class TestComputeConfigHash:
    def _entry(self, url: str) -> DatasetEntry:
        return DatasetEntry(project_url=url, commit_id="abc123", src_datasets={"test"})

    def test_deterministic(self) -> None:
        entries = [self._entry("https://github.com/a/b")]
        h1 = compute_config_hash(entries, 2, 100, 100, 10, 0.1)
        h2 = compute_config_hash(entries, 2, 100, 100, 10, 0.1)
        assert h1 == h2

    def test_returns_16_char_hex(self) -> None:
        h = compute_config_hash([self._entry("https://github.com/a/b")], 2, 100, 100, 10, 0.1)
        assert len(h) == 16
        assert all(c in "0123456789abcdef" for c in h)

    def test_entry_order_does_not_affect_hash(self) -> None:
        # URLs are sorted internally before hashing.
        a, b = self._entry("https://github.com/a/a"), self._entry("https://github.com/b/b")
        assert compute_config_hash([a, b], 2, 100, 100, 10, 0.1) == compute_config_hash(
            [b, a], 2, 100, 100, 10, 0.1
        )

    def test_different_urls_differ(self) -> None:
        h1 = compute_config_hash([self._entry("https://github.com/a/b")], 2, 100, 100, 10, 0.1)
        h2 = compute_config_hash([self._entry("https://github.com/c/d")], 2, 100, 100, 10, 0.1)
        assert h1 != h2

    @pytest.mark.parametrize("kwargs", [
        {"min_files_changed": 3},
        {"num_recent_commits": 50},
        {"num_early_commits": 50},
        {"skip_oldest_commits": 5},
        {"min_overlap_ratio": 0.05},
    ])
    def test_each_param_changes_hash(self, kwargs: dict[str, int | float]) -> None:
        entries = [self._entry("https://github.com/a/b")]
        defaults: dict[str, int | float] = {
            "min_files_changed": 2,
            "num_recent_commits": 100,
            "num_early_commits": 100,
            "skip_oldest_commits": 10,
            "min_overlap_ratio": 0.1,
        }
        baseline = compute_config_hash(entries, **defaults)  # pyright: ignore[reportArgumentType]
        modified = compute_config_hash(entries, **(defaults | kwargs))  # pyright: ignore[reportArgumentType]
        assert baseline != modified
