"""Discover relationships between repositories (forks, mirrors, shared commits)."""

import asyncio
import hashlib
import json
import logging
import multiprocessing
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, NamedTuple, Self

from git import Repo
from tqdm.auto import tqdm

from vfc_datasets.config import BASE_DATA_PATH
from vfc_datasets.dataset_entry import DatasetEntry
from vfc_datasets.utils.git.commit import (
    get_all_commit_ids,
    get_commit_signature_if_substantial,
)
from vfc_datasets.utils.git.github_client import fetch_github_fork_info
from vfc_datasets.utils.git.repository import clone_repositories
from vfc_datasets.utils.git.url import GitURL

logger = logging.getLogger(__name__)

_RELATIONSHIPS_PATH = BASE_DATA_PATH / "repo_relationships"
_REPO_CACHE_FILE_PATH = _RELATIONSHIPS_PATH / "github_repo_cache.json"


def _link_key(url1: str, url2: str) -> tuple[str, str]:
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
        return _link_key(self.url1, self.url2)


class _ConnectedComponent(NamedTuple):
    urls: set[str]
    methods: set[str]
    links: dict[str, set[str]]


def _find_connected_groups(
    edges: list[RelationshipEdge],
) -> list[_ConnectedComponent]:
    """Find connected components via DFS."""
    adjacency: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        adjacency[edge.url1].add(edge.url2)
        adjacency[edge.url2].add(edge.url1)

    seen: set[str] = set()
    groups: list[_ConnectedComponent] = []

    for start in adjacency:
        if start in seen:
            continue
        component: set[str] = set()
        stack = [start]
        while stack:
            node = stack.pop()
            if node in seen:
                continue
            seen.add(node)
            component.add(node)
            stack.extend(adjacency[node] - seen)

        methods: set[str] = set()
        links: dict[str, set[str]] = {}  # commit_id -> URLs
        for edge in edges:
            if edge.url1 in component:
                methods.add(edge.method)
                for commit_id in edge.commit_ids:
                    links.setdefault(commit_id, set()).update([edge.url1, edge.url2])

        groups.append(_ConnectedComponent(component, methods, links))

    return groups


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
    _id_to_group: dict[int, RepositoryGroup] = field(default_factory=dict, repr=False)

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
        return cls(
            groups=groups,
            url_to_group_id=data.get("url_to_group_id", {}),
            _id_to_group={g.group_id: g for g in groups},
        )

    @classmethod
    def from_edges(
        cls,
        edges: list[RelationshipEdge],
        url_to_source: dict[str, str] | None = None,
    ) -> Self:
        """Build relationships from edges using DFS to find connected components."""
        connected = _find_connected_groups(edges)
        source_urls = set(url_to_source.values()) if url_to_source else set()

        groups: list[RepositoryGroup] = []
        url_to_group_id: dict[str, int] = {}

        for group_id, (urls, methods, links) in enumerate(connected):
            if len(urls) < 2:
                continue

            # Find canonical URL (prefer source repos over forks)
            canonical = None
            for url in urls:
                if url in source_urls:
                    canonical = url
                    break

            group = RepositoryGroup(
                group_id=group_id,
                project_urls=urls,
                detection_methods=methods,
                canonical_url=canonical,
                links=links,
            )
            groups.append(group)
            for url in urls:
                url_to_group_id[url] = group_id

        return cls(
            groups=groups,
            url_to_group_id=url_to_group_id,
            _id_to_group={g.group_id: g for g in groups},
        )


def _compute_signatures_for_repo(
    args: tuple[str, str | Path, list[str], int],
) -> list[tuple[str, str, tuple[str, str] | None]]:
    """Compute signatures for all commits in one repo."""
    url, repo_path, commit_ids, min_files_changed = args
    results: list[tuple[str, str, tuple[str, str] | None]] = []

    try:
        repo = Repo(repo_path)
        for commit_id in commit_ids:
            sig = get_commit_signature_if_substantial(repo, commit_id, min_files_changed)
            results.append((url, commit_id, sig))
    except Exception as exc:
        logger.debug("Failed to compute signatures for %s: %s", url, exc)
        for commit_id in commit_ids:
            results.append((url, commit_id, None))

    return results


def _scan_commit_histories(
    project_urls: set[str],
    url_to_repo: dict[str, Repo | None],
) -> dict[str, list[str]]:
    """Scan repos in parallel and return mapping of URL to commit IDs (newest-first)."""
    urls_to_scan = {url for url in project_urls if url_to_repo.get(url)}
    logger.info("Scanning commit history for %d repos...", len(urls_to_scan))

    commit_history: dict[str, list[str]] = {}
    if not urls_to_scan:
        return commit_history

    max_workers = min(multiprocessing.cpu_count(), 32, len(urls_to_scan))

    def scan_repo(url: str) -> tuple[str, list[str]]:
        repo = url_to_repo.get(url)
        if repo:
            return url, list(get_all_commit_ids(repo))
        return url, []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(scan_repo, url): url for url in urls_to_scan}
        with tqdm(total=len(futures), desc="Scanning commit history", unit="repos") as pbar:
            for future in as_completed(futures):
                url, commit_ids = future.result()
                if commit_ids:
                    commit_history[url] = commit_ids
                pbar.update(1)

    return commit_history


def _sample_commits(
    project_urls: set[str],
    commit_history: dict[str, list[str]],
    num_recent_commits: int,
    num_early_commits: int,
    skip_oldest_commits: int,
) -> set[str]:
    """Sample recent and early commits from each repo's history."""
    logger.info(
        "Sampling %d recent + %d early (skipping first %d) commits per repo...",
        num_recent_commits,
        num_early_commits,
        skip_oldest_commits,
    )
    sampled: set[str] = set()
    for url in project_urls:
        # commits is newest-first from git rev-list
        commits = commit_history.get(url, [])
        if not commits:
            continue
        # Sample recent commits (from the start of the list)
        sampled.update(commits[:num_recent_commits])
        # Sample early commits (from the end), skipping the very oldest
        # which are often template/skeleton setup commits
        if len(commits) > num_early_commits + skip_oldest_commits:
            early_start = -(num_early_commits + skip_oldest_commits)
            early_end = -skip_oldest_commits if skip_oldest_commits else None
            sampled.update(commits[early_start:early_end])

    logger.info("Sampled %d unique commits from %d repos", len(sampled), len(project_urls))
    return sampled


def _find_shared_commits(
    project_urls: set[str],
    commit_history: dict[str, list[str]],
    sampled_commits: set[str],
) -> list[tuple[str, set[str]]]:
    """Find sampled commits that appear in 2+ repos. Returns sorted (commit_id, urls) pairs."""
    commit_to_urls: dict[str, set[str]] = defaultdict(set)
    for url in tqdm(project_urls, desc="Mapping commits to repos", unit="repos"):
        for commit_id in commit_history.get(url, []):
            if commit_id in sampled_commits:
                commit_to_urls[commit_id].add(url)

    shared = sorted(
        [(cid, urls) for cid, urls in commit_to_urls.items() if len(urls) >= 2],
        key=lambda x: len(x[1]),
    )
    logger.info("Found %d sampled commits shared by 2+ repos", len(shared))
    return shared


def _compute_signatures(
    shared_commits: list[tuple[str, set[str]]],
    url_to_repo: dict[str, Repo | None],
    min_files_changed: int,
) -> dict[tuple[str, str], tuple[str, str] | None]:
    """Compute commit signatures in parallel for all shared commits."""
    url_to_commits: dict[str, list[str]] = defaultdict(list)
    for cid, urls in shared_commits:
        for url in urls:
            if url_to_repo.get(url):
                url_to_commits[url].append(cid)

    total_sigs = sum(len(commits) for commits in url_to_commits.values())
    logger.info(
        "Pre-computing %d signatures across %d repos in parallel...",
        total_sigs,
        len(url_to_commits),
    )
    sig_cache: dict[tuple[str, str], tuple[str, str] | None] = {}

    if not url_to_commits:
        return sig_cache

    repo_tasks = []
    for url, commits in url_to_commits.items():
        if repo := url_to_repo[url]:
            repo_tasks.append((url, Path(repo.working_dir), commits, min_files_changed))

    max_workers = min(multiprocessing.cpu_count(), len(repo_tasks))

    with ProcessPoolExecutor(max_workers=max_workers) as pool:
        sig_futures = {
            pool.submit(_compute_signatures_for_repo, task): task[0] for task in repo_tasks
        }
        with tqdm(total=total_sigs, desc="Computing signatures", unit="sigs") as pbar:
            for sig_future in as_completed(sig_futures):
                url = sig_futures[sig_future]
                results = sig_future.result()
                for result_url, commit_id, sig in results:
                    sig_cache[(result_url, commit_id)] = sig
                    pbar.update(1)
                repo_name = url.rstrip("/").split("/")[-1][:20].ljust(20)
                pbar.set_postfix_str(f"{repo_name} done")

    return sig_cache


def _build_edges_from_signatures(
    shared_commits: list[tuple[str, set[str]]],
    sig_cache: dict[tuple[str, str], tuple[str, str] | None],
) -> list[RelationshipEdge]:
    """Compare signatures for shared commits and build relationship edges."""
    edges: list[RelationshipEdge] = []
    seen_pairs: dict[tuple[str, str], RelationshipEdge] = {}

    for commit_id, urls in tqdm(shared_commits, desc="Matching repos", unit="commits"):
        sorted_urls = sorted(urls)
        for i, url1 in enumerate(sorted_urls):
            for url2 in sorted_urls[i + 1 :]:
                sig1 = sig_cache.get((url1, commit_id))
                sig2 = sig_cache.get((url2, commit_id))

                if sig1 and sig2 and sig1 == sig2:
                    key = _link_key(url1, url2)
                    if key in seen_pairs:
                        seen_pairs[key].commit_ids.add(commit_id)
                    else:
                        edge = RelationshipEdge(url1, url2, "local_history", {commit_id})
                        seen_pairs[key] = edge
                        edges.append(edge)

    logger.info("Found %d local history edges", len(edges))
    return edges


def _find_related_by_local_history(
    entries: list[DatasetEntry],
    url_to_repo: dict[str, Repo | None],
    min_files_changed: int,
    num_recent_commits: int = 50,
    num_early_commits: int = 50,
    skip_oldest_commits: int = 10,
) -> tuple[list[RelationshipEdge], dict[str, list[str]]]:
    """Find relationships by comparing local commit histories. Returns (edges, commit_history)."""
    project_urls = {e.project_url for e in entries if e.project_url}
    commit_history = _scan_commit_histories(project_urls, url_to_repo)
    sampled = _sample_commits(
        project_urls, commit_history, num_recent_commits, num_early_commits, skip_oldest_commits
    )
    shared = _find_shared_commits(project_urls, commit_history, sampled)
    if not shared:
        return [], commit_history
    sig_cache = _compute_signatures(shared, url_to_repo, min_files_changed)
    edges = _build_edges_from_signatures(shared, sig_cache)
    return edges, commit_history


async def _discover_github_forks_async(
    project_urls: set[str],
) -> tuple[list[RelationshipEdge], dict[str, str]]:
    """Discover fork relationships via GitHub API. Returns (edges, url_to_source)."""
    github_urls = {
        url for url in project_urls if (parsed := GitURL.parse(url)) and parsed.host == "github.com"
    }

    if not github_urls:
        logger.info("No GitHub URLs to check for fork relationships")
        return [], {}

    repo_cache = _load_repo_cache()
    urls_to_query = {url for url in github_urls if url not in repo_cache}

    logger.info(
        "Repo cache: %d cached, %d to query",
        len(github_urls) - len(urls_to_query),
        len(urls_to_query),
    )

    if urls_to_query:
        fork_info = await fetch_github_fork_info(urls_to_query)
        for url, info in fork_info.items():
            repo_cache[url] = {
                "parent": info.parent,
                "source": info.source,
                "is_fork": info.is_fork,
            }
        _save_repo_cache(repo_cache)

    edges: list[RelationshipEdge] = []
    url_to_source: dict[str, str] = {}

    for url in github_urls:
        cached_info = repo_cache.get(url, {})
        if cached_info.get("parent"):
            edges.append(RelationshipEdge(url, cached_info["parent"], "github_fork"))
        if cached_info.get("source"):
            url_to_source[url] = cached_info["source"]
            edges.append(RelationshipEdge(url, cached_info["source"], "github_fork"))

    logger.info("Found %d GitHub fork edges", len(edges))
    return edges, url_to_source


def _save_relationships(relationships: RepositoryRelationships, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(relationships.to_dict(), f, indent=2)
    logger.info("Saved relationships to: %s", path)


def _save_suspicious_groups(groups: list[RepositoryGroup], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "description": "Groups with URLs that could not be validated as related.",
        "count": len(groups),
        "total_urls": sum(len(g.project_urls) for g in groups),
        "groups": [g.to_dict() for g in groups],
    }
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    logger.info("Saved %d suspicious groups to: %s", len(groups), path)


def _load_repo_cache() -> dict[str, dict[str, Any]]:
    if not _REPO_CACHE_FILE_PATH.exists():
        return {}
    try:
        with open(_REPO_CACHE_FILE_PATH) as f:
            return json.load(f)
    except Exception as e:
        logger.warning("Failed to load repo cache: %s", e)
        return {}


def _save_repo_cache(cache: dict[str, dict[str, Any]]) -> None:
    _REPO_CACHE_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_REPO_CACHE_FILE_PATH, "w") as f:
        json.dump(cache, f, indent=2)
    logger.info("Saved repo cache (%d entries) to: %s", len(cache), _REPO_CACHE_FILE_PATH)


def _compute_config_hash(
    entries: list[DatasetEntry],
    min_files_changed: int,
    num_recent_commits: int,
    num_early_commits: int,
    skip_oldest_commits: int,
) -> str:
    urls = sorted(e.project_url for e in entries if e.project_url)
    config = (
        f"{urls}|{min_files_changed}|{num_recent_commits}|{num_early_commits}|{skip_oldest_commits}"
    )
    return hashlib.sha256(config.encode()).hexdigest()[:16]


def _find_suspicious_project_relationships(
    relationships: RepositoryRelationships,
    fork_edges: list[RelationshipEdge],
    min_shared_commits: int = 2,
) -> None:
    """Mark URLs as suspicious if not validated by fork network or shared commits."""
    # Build validated pairs: github_fork connections
    validated_pairs: set[frozenset[str]] = set()
    fork_relationships = RepositoryRelationships.from_edges(fork_edges)
    for fork_group in fork_relationships.groups:
        urls = sorted(fork_group.project_urls)
        for i, url1 in enumerate(urls):
            for url2 in urls[i + 1 :]:
                validated_pairs.add(frozenset([url1, url2]))

    for group in relationships.groups:
        # Build validated adjacency for this group
        validated_adjacency: dict[str, set[str]] = defaultdict(set)

        # Add github_fork validated pairs
        for url in group.project_urls:
            for other_url in group.project_urls:
                if url != other_url and frozenset([url, other_url]) in validated_pairs:
                    validated_adjacency[url].add(other_url)
                    validated_adjacency[other_url].add(url)

        # Count commits per URL pair from links
        pair_commit_counts: dict[frozenset[str], int] = defaultdict(int)
        for link_urls in group.links.values():
            sorted_urls = sorted(link_urls)
            for i, url1 in enumerate(sorted_urls):
                for url2 in sorted_urls[i + 1 :]:
                    pair_commit_counts[frozenset([url1, url2])] += 1

        # Add pairs with enough shared commits as validated
        for pair, count in pair_commit_counts.items():
            if count >= min_shared_commits:
                url1, url2 = tuple(pair)
                validated_adjacency[url1].add(url2)
                validated_adjacency[url2].add(url1)

        # DFS from canonical URL (or first URL) to find reachable URLs
        start_url = group.canonical_url or sorted(group.project_urls)[0]
        reachable: set[str] = set()
        stack = [start_url]
        while stack:
            url = stack.pop()
            if url in reachable:
                continue
            reachable.add(url)
            stack.extend(validated_adjacency[url] - reachable)

        # URLs not reachable via validated edges are suspicious
        group.suspicious_urls = group.project_urls - reachable


def discover_repository_relationships(
    entries: list[DatasetEntry],
    min_files_changed: int = 2,
    output_path: Path | None = None,
    num_recent_commits: int = 100,
    num_early_commits: int = 100,
    skip_oldest_commits: int = 10,
) -> RepositoryRelationships:
    """Discover relationships between repositories via GitHub API and commit history."""
    if output_path is None:
        config_hash = _compute_config_hash(
            entries, min_files_changed, num_recent_commits, num_early_commits, skip_oldest_commits
        )
        output_path = _RELATIONSHIPS_PATH / f"relationships_{config_hash}.json"
        logger.info("Auto-generated output path: %s", output_path)

    if output_path.exists():
        logger.info("Loading existing relationships from: %s", output_path)
        with open(output_path) as f:
            return RepositoryRelationships.from_dict(json.load(f))

    project_urls = {e.project_url for e in entries if e.project_url}
    logger.info(
        "Discovering relationships among %d entries (%d repos)", len(entries), len(project_urls)
    )

    url_to_repo = clone_repositories(entries)
    edges: list[RelationshipEdge] = []

    # GitHub API fork detection
    fork_edges, url_to_source = asyncio.run(_discover_github_forks_async(project_urls))
    edges.extend(fork_edges)

    # Local commit history comparison
    local_edges, _ = _find_related_by_local_history(
        entries,
        url_to_repo,
        min_files_changed,
        num_recent_commits,
        num_early_commits,
        skip_oldest_commits,
    )
    edges.extend(local_edges)

    # Build groups from all edges (no false negatives)
    relationships = RepositoryRelationships.from_edges(edges, url_to_source)

    # Save results
    _save_relationships(relationships, output_path)

    logger.info(
        "Total: %d groups with %d related repositories",
        len(relationships.groups),
        len(relationships.url_to_group_id),
    )

    return relationships


def _count_matching_signatures(
    repo: Repo,
    validated_repo: Repo,
    common_commits: list[str],
    url: str,
    validated_url: str,
    group: RepositoryGroup,
    min_files_changed: int,
    needed: int,
) -> int:
    """Compare commit signatures between two repos, adding links for matches."""
    matched = 0
    for commit_id in common_commits:
        sig1 = get_commit_signature_if_substantial(repo, commit_id, min_files_changed)
        if not sig1:
            continue
        sig2 = get_commit_signature_if_substantial(validated_repo, commit_id, min_files_changed)
        if sig2 and sig1 == sig2:
            group.add_link(url, validated_url, commit_id)
            matched += 1
            if matched >= needed:
                break
    return matched


def _try_validate_url(
    url: str,
    reachable: set[str],
    group: RepositoryGroup,
    url_to_repo: dict[str, Repo | None],
    commit_sets: dict[str, set[str]],
    min_files_changed: int,
    min_shared_commits: int,
) -> bool:
    """Try to validate a single suspicious URL against already-validated URLs."""
    repo = url_to_repo.get(url)
    if not repo:
        return False

    url_commits = commit_sets.get(url)
    if not url_commits:
        return False

    for validated_url in reachable:
        validated_repo = url_to_repo.get(validated_url)
        if not validated_repo:
            continue

        validated_commits = commit_sets.get(validated_url)
        if not validated_commits:
            continue

        existing = sum(1 for urls in group.links.values() if url in urls and validated_url in urls)

        common = list(url_commits & validated_commits - group.shared_commits)
        if not common and existing < min_shared_commits:
            continue

        needed = min_shared_commits - existing
        new = _count_matching_signatures(
            repo,
            validated_repo,
            common,
            url,
            validated_url,
            group,
            min_files_changed,
            needed,
        )
        if existing + new >= min_shared_commits:
            return True

    return False


def _validate_suspicious_urls(
    relationships: RepositoryRelationships,
    commit_history: dict[str, list[str]],
    url_to_repo: dict[str, Repo | None],
    min_files_changed: int,
    min_shared_commits: int,
) -> None:
    """Try to validate suspicious URLs by finding additional shared commits."""
    for group in tqdm(relationships.groups, desc="Validating suspicious URLs", unit="groups"):
        if not group.suspicious_urls:
            continue

        reachable = group.project_urls - group.suspicious_urls
        unvalidated_urls = set(group.suspicious_urls)

        logger.info(
            "Group %d: validating %d suspicious URLs against %d validated",
            group.group_id,
            len(unvalidated_urls),
            len(reachable),
        )

        commit_sets = {
            url: set(commits) for url in group.project_urls if (commits := commit_history.get(url))
        }

        for url in list(unvalidated_urls):
            if _try_validate_url(
                url,
                reachable,
                group,
                url_to_repo,
                commit_sets,
                min_files_changed,
                min_shared_commits,
            ):
                unvalidated_urls.discard(url)
                reachable.add(url)

        group.suspicious_urls = unvalidated_urls


def validate_relationships(
    entries: list[DatasetEntry],
    relationships_path: Path,
    min_files_changed: int = 2,
    min_shared_commits: int = 2,
    num_recent_commits: int = 100,
    num_early_commits: int = 100,
    skip_oldest_commits: int = 10,
) -> None:
    """Validate relationships and log warnings for suspicious groups."""
    with open(relationships_path) as f:
        data = json.load(f)
    relationships = RepositoryRelationships.from_dict(data)
    logger.info("Loaded %d groups from %s", len(relationships.groups), relationships_path)

    project_urls = {e.project_url for e in entries if e.project_url}
    url_to_repo = clone_repositories(entries)
    fork_edges, _ = asyncio.run(_discover_github_forks_async(project_urls))
    _, commit_history = _find_related_by_local_history(
        entries,
        url_to_repo,
        min_files_changed,
        num_recent_commits,
        num_early_commits,
        skip_oldest_commits,
    )

    logger.info("Finding suspicious relationships in %d groups...", len(relationships.groups))
    _find_suspicious_project_relationships(relationships, fork_edges, min_shared_commits)
    _validate_suspicious_urls(
        relationships, commit_history, url_to_repo, min_files_changed, min_shared_commits
    )

    suspicious_count = sum(1 for g in relationships.groups if g.suspicious_urls)
    if suspicious_count:
        total_suspicious_urls = sum(len(g.suspicious_urls) for g in relationships.groups)
        logger.warning(
            "%d groups have %d suspicious URLs after validation",
            suspicious_count,
            total_suspicious_urls,
        )
        # Save suspicious groups for review
        suspicious_groups = [g for g in relationships.groups if g.suspicious_urls]
        suspicious_path = relationships_path.with_name(
            relationships_path.stem + "_suspicious" + relationships_path.suffix
        )
        _save_suspicious_groups(suspicious_groups, suspicious_path)
    else:
        logger.info("All relationships validated successfully")
