"""Tests for repository relationship detection."""

import pytest

from utils.git.commit import TEMPLATE_FILE_PATTERNS, is_template_file
from utils.split.repository_relationships import (
    RelationshipEdge,
    RepositoryGroup,
    RepositoryRelationships,
    _find_connected_groups,
    _find_suspicious_project_relationships,
    _link_key,
)


class TestLinkKey:
    def test_sorts_urls(self) -> None:
        assert _link_key("b", "a") == ("a", "b")
        assert _link_key("a", "b") == ("a", "b")

    def test_consistent_key(self) -> None:
        assert _link_key("x", "y") == _link_key("y", "x")


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
            _id_to_group={0: group},
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
            _id_to_group={0: group},
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
            _id_to_group={0: group},
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
            _id_to_group={0: group},
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
            _id_to_group={0: group},
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
            _id_to_group={0: group},
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
            _id_to_group={0: group},
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
            _id_to_group={0: group},
        )
        fork_edges = [RelationshipEdge(url1, url2, "github_fork")]

        _find_suspicious_project_relationships(relationships, fork_edges)
        # url1 and url2 validated via fork, url3 suspicious (single commit)
        assert group.suspicious_urls == {url3}
