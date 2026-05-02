"""Discovery pipeline: find repository relationships via fork API and commit history."""

import asyncio
import hashlib
import json
import logging
import multiprocessing
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from itertools import combinations
from pathlib import Path
from typing import Any

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

from .models import RelationshipEdge, RepositoryRelationships, link_key

logger = logging.getLogger(__name__)

RELATIONSHIPS_PATH = BASE_DATA_PATH / "repo_relationships"
_REPO_CACHE_FILE_PATH = RELATIONSHIPS_PATH / "github_repo_cache.json"
_COMMIT_HISTORY_CACHE_DIR = RELATIONSHIPS_PATH / "commit_history_cache"


def compute_config_hash(
    entries: list[DatasetEntry],
    min_files_changed: int,
    num_recent_commits: int,
    num_early_commits: int,
    skip_oldest_commits: int,
    min_overlap_ratio: float,
) -> str:
    urls = sorted(e.project_url for e in entries if e.project_url)
    config = (
        f"{urls}|{min_files_changed}|{num_recent_commits}|{num_early_commits}"
        f"|{skip_oldest_commits}|{min_overlap_ratio}"
    )
    return hashlib.sha256(config.encode()).hexdigest()[:16]


def _load_repo_cache() -> dict[str, dict[str, Any]]:
    if not _REPO_CACHE_FILE_PATH.exists():
        return {}
    try:
        return json.loads(_REPO_CACHE_FILE_PATH.read_text())
    except Exception as e:
        logger.warning("Failed to load repo cache: %s", e)
        return {}


def _save_repo_cache(cache: dict[str, dict[str, Any]]) -> None:
    _REPO_CACHE_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _REPO_CACHE_FILE_PATH.write_text(json.dumps(cache, indent=2))
    logger.info("Saved repo cache (%d entries) to: %s", len(cache), _REPO_CACHE_FILE_PATH)


def _commit_history_cache_path(url: str) -> Path:
    url_hash = hashlib.sha256(url.encode()).hexdigest()[:16]
    return _COMMIT_HISTORY_CACHE_DIR / f"{url_hash}.json"


def _load_commit_history_for_url(url: str) -> dict[str, Any] | None:
    """Load cached commit history for one URL, or None if missing/invalid."""
    path = _commit_history_cache_path(url)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except Exception as e:
        logger.debug("Failed to load commit history cache for %s: %s", url, e)
        return None
    if data.get("url") != url:
        # Hash collision (vanishingly unlikely) or unrelated file: treat as miss.
        return None
    return data


def _save_commit_history_for_url(url: str, head: str, commits: list[str]) -> None:
    path = _commit_history_cache_path(url)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"url": url, "head": head, "commits": commits}))


def _repo_head(repo: Repo) -> str | None:
    try:
        return repo.head.commit.hexsha
    except Exception:
        return None


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


def scan_commit_histories(
    project_urls: set[str],
    url_to_path: dict[str, Path | None],
) -> dict[str, list[str]]:
    """Map URL to commit IDs (newest-first). Per-repo disk cache, invalidated by HEAD."""
    commit_history: dict[str, list[str]] = {}
    urls_to_scan: set[str] = set()

    for url in project_urls:
        path = url_to_path.get(url)
        if not path:
            continue
        with Repo(path) as repo:
            head = _repo_head(repo)
        cached = _load_commit_history_for_url(url)
        if head and cached and cached.get("head") == head:
            commit_history[url] = cached["commits"]
        else:
            urls_to_scan.add(url)

    logger.info(
        "Commit history: %d cached, %d to scan", len(commit_history), len(urls_to_scan)
    )

    if not urls_to_scan:
        return commit_history

    max_workers = min(multiprocessing.cpu_count(), 32, len(urls_to_scan))

    def scan_repo(url: str) -> tuple[str, list[str], str | None]:
        path = url_to_path[url]
        assert path is not None
        with Repo(path) as repo:
            return url, list(get_all_commit_ids(repo)), _repo_head(repo)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(scan_repo, url): url for url in urls_to_scan}
        with tqdm(total=len(futures), desc="Scanning commit history", unit="repos") as pbar:
            for future in as_completed(futures):
                url, commit_ids, head = future.result()
                if commit_ids:
                    commit_history[url] = commit_ids
                    if head:
                        _save_commit_history_for_url(url, head, commit_ids)
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
        if num_early_commits > 0 and len(commits) > num_early_commits + skip_oldest_commits:
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
    url_to_path: dict[str, Path | None],
    min_files_changed: int,
) -> dict[str, tuple[str, str] | None]:
    """Compute one signature per shared commit ID. Git commit IDs are content
    hashes, so any repo containing a commit produces the same signature; we only
    use the signature step to filter out tiny/template commits."""
    # Pick one repo per commit (sorted for determinism).
    url_to_commits: dict[str, list[str]] = defaultdict(list)
    for cid, urls in shared_commits:
        for url in sorted(urls):
            if url_to_path.get(url):
                url_to_commits[url].append(cid)
                break

    total_sigs = sum(len(commits) for commits in url_to_commits.values())
    logger.info(
        "Pre-computing %d signatures across %d repos in parallel...",
        total_sigs,
        len(url_to_commits),
    )
    sig_cache: dict[str, tuple[str, str] | None] = {}

    if not url_to_commits:
        return sig_cache

    repo_tasks = []
    for url, commits in url_to_commits.items():
        if path := url_to_path[url]:
            repo_tasks.append((url, path, commits, min_files_changed))

    max_workers = min(multiprocessing.cpu_count(), len(repo_tasks))

    with ProcessPoolExecutor(max_workers=max_workers) as pool:
        sig_futures = {
            pool.submit(_compute_signatures_for_repo, task): task[0] for task in repo_tasks
        }
        with tqdm(total=total_sigs, desc="Computing signatures", unit="sigs") as pbar:
            for sig_future in as_completed(sig_futures):
                url = sig_futures[sig_future]
                results = sig_future.result()
                for _, commit_id, sig in results:
                    sig_cache[commit_id] = sig
                    pbar.update(1)
                repo_name = url.rstrip("/").split("/")[-1][:20].ljust(20)
                pbar.set_postfix_str(f"{repo_name} done")

    return sig_cache


def _build_edges_from_signatures(
    shared_commits: list[tuple[str, set[str]]],
    sig_cache: dict[str, tuple[str, str] | None],
    commit_history: dict[str, list[str]],
    min_overlap_ratio: float,
) -> list[RelationshipEdge]:
    """Build edges for each substantial shared commit, gated by pairwise commit
    overlap. Real forks share a contiguous commit prefix (overlap close to 1);
    template-bootstrap collisions share only a handful of commits relative to
    each repo's full history. Pairs below ``min_overlap_ratio`` are rejected."""
    seen_pairs: dict[tuple[str, str], RelationshipEdge] = {}
    rejected_pairs: set[tuple[str, str]] = set()
    commit_sets: dict[str, set[str]] = {}

    def _commits_for(url: str) -> set[str]:
        if url not in commit_sets:
            commit_sets[url] = set(commit_history.get(url, []))
        return commit_sets[url]

    for commit_id, urls in tqdm(shared_commits, desc="Matching repos", unit="commits"):
        if not sig_cache.get(commit_id):
            continue
        for url1, url2 in combinations(sorted(urls), 2):
            key = link_key(url1, url2)
            if key in seen_pairs:
                seen_pairs[key].commit_ids.add(commit_id)
                continue
            if key in rejected_pairs:
                continue
            ca, cb = _commits_for(url1), _commits_for(url2)
            denom = min(len(ca), len(cb))
            if denom == 0 or len(ca & cb) / denom < min_overlap_ratio:
                rejected_pairs.add(key)
                continue
            seen_pairs[key] = RelationshipEdge(url1, url2, "local_history", {commit_id})

    edges = list(seen_pairs.values())
    logger.info(
        "Found %d local history edges (rejected %d pairs below overlap %.2f)",
        len(edges),
        len(rejected_pairs),
        min_overlap_ratio,
    )
    return edges


def find_related_by_local_history(
    entries: list[DatasetEntry],
    url_to_path: dict[str, Path | None],
    min_files_changed: int,
    num_recent_commits: int = 50,
    num_early_commits: int = 50,
    skip_oldest_commits: int = 10,
    min_overlap_ratio: float = 0.1,
) -> tuple[list[RelationshipEdge], dict[str, list[str]]]:
    """Find relationships by comparing local commit histories. Returns (edges, commit_history)."""
    project_urls = {e.project_url for e in entries if e.project_url}
    commit_history = scan_commit_histories(project_urls, url_to_path)
    sampled = _sample_commits(
        project_urls, commit_history, num_recent_commits, num_early_commits, skip_oldest_commits
    )
    shared = _find_shared_commits(project_urls, commit_history, sampled)
    if not shared:
        return [], commit_history
    sig_cache = _compute_signatures(shared, url_to_path, min_files_changed)
    edges = _build_edges_from_signatures(shared, sig_cache, commit_history, min_overlap_ratio)
    return edges, commit_history


async def discover_github_forks_async(
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


def discover_repository_relationships(
    entries: list[DatasetEntry],
    min_files_changed: int = 2,
    output_path: Path | None = None,
    num_recent_commits: int = 100,
    num_early_commits: int = 100,
    skip_oldest_commits: int = 10,
    min_overlap_ratio: float = 0.1,
) -> RepositoryRelationships:
    """Discover relationships between repositories via GitHub API and commit history."""
    if output_path is None:
        config_hash = compute_config_hash(
            entries,
            min_files_changed,
            num_recent_commits,
            num_early_commits,
            skip_oldest_commits,
            min_overlap_ratio,
        )
        output_path = RELATIONSHIPS_PATH / f"relationships_{config_hash}.json"
        logger.info("Auto-generated output path: %s", output_path)

    if output_path.exists():
        logger.info("Loading existing relationships from: %s", output_path)
        return RepositoryRelationships.load(output_path)

    project_urls = {e.project_url for e in entries if e.project_url}
    logger.info(
        "Discovering relationships among %d entries (%d repos)", len(entries), len(project_urls)
    )

    url_to_path = clone_repositories(entries)
    edges: list[RelationshipEdge] = []

    # GitHub API fork detection
    fork_edges, url_to_source = asyncio.run(discover_github_forks_async(project_urls))
    edges.extend(fork_edges)

    # Local commit history comparison
    local_edges, commit_history = find_related_by_local_history(
        entries,
        url_to_path,
        min_files_changed,
        num_recent_commits,
        num_early_commits,
        skip_oldest_commits,
        min_overlap_ratio,
    )
    edges.extend(local_edges)

    # Build groups from all edges (no false negatives)
    relationships = RepositoryRelationships.from_edges(edges, url_to_source, commit_history)

    # Save results
    relationships.save(output_path)

    logger.info(
        "Total: %d groups with %d related repositories",
        len(relationships.groups),
        len(relationships.url_to_group_id),
    )

    return relationships
