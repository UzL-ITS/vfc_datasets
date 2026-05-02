"""Data classes and connected-component logic for repository relationships."""

import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Self

logger = logging.getLogger(__name__)


def link_key(url1: str, url2: str) -> tuple[str, str]:
    """Create a canonical key for a URL pair (sorted for consistency)."""
    return (url1, url2) if url1 < url2 else (url2, url1)


@dataclass
class RelationshipEdge:
    """An edge connecting two related URLs."""

    url1: str
    url2: str
    method: str
    commit_ids: set[str] = field(default_factory=set)

    @property
    def key(self) -> tuple[str, str]:
        return link_key(self.url1, self.url2)


def reachable_from(start: str, adjacency: dict[str, set[str]]) -> set[str]:
    """DFS: return all nodes reachable from start."""
    reachable: set[str] = set()
    stack = [start]
    while stack:
        node = stack.pop()
        if node in reachable:
            continue
        reachable.add(node)
        stack.extend(adjacency[node] - reachable)
    return reachable


def _find_connected_groups(
    edges: list[RelationshipEdge],
) -> list[tuple[set[str], set[str], dict[str, set[str]]]]:
    """Find connected components. Each item is (urls, detection_methods, commit_id -> urls)."""
    adjacency: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        adjacency[edge.url1].add(edge.url2)
        adjacency[edge.url2].add(edge.url1)

    seen: set[str] = set()
    components: list[tuple[set[str], set[str], dict[str, set[str]]]] = []

    for start in adjacency:
        if start in seen:
            continue
        component = reachable_from(start, adjacency)
        seen.update(component)

        methods: set[str] = set()
        links: dict[str, set[str]] = {}
        for edge in edges:
            if edge.url1 in component:
                methods.add(edge.method)
                for commit_id in edge.commit_ids:
                    links.setdefault(commit_id, set()).update([edge.url1, edge.url2])

        components.append((component, methods, links))

    return components


@dataclass
class RepositoryGroup:
    group_id: int
    project_urls: set[str]
    detection_methods: set[str]
    canonical_url: str | None = None
    links: dict[str, set[str]] = field(default_factory=dict)  # commit_id -> URLs
    suspicious_urls: set[str] = field(default_factory=set)  # URLs not validated

    @property
    def shared_commits(self) -> set[str]:
        return set(self.links.keys())

    def add_link(self, url1: str, url2: str, commit_id: str) -> None:
        """Record that url1 and url2 share a commit."""
        self.links.setdefault(commit_id, set()).update([url1, url2])

    def to_dict(self) -> dict[str, Any]:
        result = {
            "group_id": self.group_id,
            "project_urls": sorted(self.project_urls),
            "canonical_url": self.canonical_url,
            "detection_methods": sorted(self.detection_methods),
            "links": {commit: sorted(urls) for commit, urls in sorted(self.links.items())},
        }
        if self.suspicious_urls:
            result["suspicious_urls"] = sorted(self.suspicious_urls)
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        return cls(
            group_id=data["group_id"],
            project_urls=set(data["project_urls"]),
            canonical_url=data.get("canonical_url"),
            detection_methods=set(data.get("detection_methods", [])),
            links={commit: set(urls) for commit, urls in data.get("links", {}).items()},
            suspicious_urls=set(data.get("suspicious_urls", [])),
        )


@dataclass
class RepositoryRelationships:
    groups: list[RepositoryGroup] = field(default_factory=list)
    url_to_group_id: dict[str, int] = field(default_factory=dict)
    _id_to_group: dict[int, RepositoryGroup] = field(
        default_factory=dict, repr=False, init=False
    )

    def __post_init__(self) -> None:
        self._id_to_group = {g.group_id: g for g in self.groups}

    def get_group(self, project_url: str) -> RepositoryGroup | None:
        group_id = self.url_to_group_id.get(project_url)
        return self._id_to_group.get(group_id) if group_id is not None else None

    def are_related(self, url1: str, url2: str) -> bool:
        group1 = self.url_to_group_id.get(url1)
        group2 = self.url_to_group_id.get(url2)
        return group1 is not None and group1 == group2

    def to_dict(self) -> dict[str, Any]:
        return {
            "groups": [g.to_dict() for g in self.groups],
            "url_to_group_id": self.url_to_group_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        groups = [RepositoryGroup.from_dict(g) for g in data.get("groups", [])]
        return cls(groups=groups, url_to_group_id=data.get("url_to_group_id", {}))

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2))
        logger.info("Saved relationships to: %s", path)

    @classmethod
    def load(cls, path: Path) -> Self:
        return cls.from_dict(json.loads(path.read_text()))

    @classmethod
    def from_edges(
        cls,
        edges: list[RelationshipEdge],
        url_to_source: dict[str, str] | None = None,
        commit_history: dict[str, list[str]] | None = None,
    ) -> Self:
        """Build relationships from edges using DFS to find connected components."""
        connected = _find_connected_groups(edges)
        source_urls = set(url_to_source.values()) if url_to_source else set()

        groups: list[RepositoryGroup] = []
        url_to_group_id: dict[str, int] = {}

        for group_id, (urls, methods, links) in enumerate(connected):
            if len(urls) < 2:
                continue

            group = RepositoryGroup(
                group_id=group_id,
                project_urls=urls,
                detection_methods=methods,
                canonical_url=_pick_canonical(urls, source_urls, commit_history),
                links=links,
            )
            groups.append(group)
            for url in urls:
                url_to_group_id[url] = group_id

        return cls(groups=groups, url_to_group_id=url_to_group_id)


def _pick_canonical(
    urls: set[str],
    source_urls: set[str],
    commit_history: dict[str, list[str]] | None,
) -> str | None:
    """Pick the canonical URL for a group.

    Prefers fork-chain roots (per GitHub API). Among ties — or when no fork data
    exists — picks the URL with the most commits, since upstreams accumulate more
    history than their forks. Tiebreaks alphabetically for determinism.
    """
    pool = (urls & source_urls) or urls
    if commit_history:
        ranked = sorted(pool, key=lambda u: (-len(commit_history.get(u, [])), u))
        if ranked and commit_history.get(ranked[0]):
            return ranked[0]
    return min(urls & source_urls) if urls & source_urls else None
