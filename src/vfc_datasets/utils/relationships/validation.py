"""Suspicious-URL validation for repository relationship groups."""

import asyncio
import json
import logging
from collections import defaultdict
from itertools import combinations
from pathlib import Path

from git import Repo
from tqdm.auto import tqdm

from vfc_datasets.dataset_entry import DatasetEntry
from vfc_datasets.utils.git.commit import get_commit_signature_if_substantial
from vfc_datasets.utils.git.repository import clone_repositories

from .discovery import discover_github_forks_async, scan_commit_histories
from .models import RelationshipEdge, RepositoryGroup, RepositoryRelationships, reachable_from

logger = logging.getLogger(__name__)


def _save_suspicious_groups(groups: list[RepositoryGroup], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "description": "Groups with URLs that could not be validated as related.",
        "count": len(groups),
        "total_urls": sum(len(g.project_urls) for g in groups),
        "groups": [g.to_dict() for g in groups],
    }
    path.write_text(json.dumps(data, indent=2))
    logger.info("Saved %d suspicious groups to: %s", len(groups), path)


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
        for url1, url2 in combinations(sorted(fork_group.project_urls), 2):
            validated_pairs.add(frozenset([url1, url2]))

    for group in relationships.groups:
        # Build validated adjacency for this group
        validated_adjacency: dict[str, set[str]] = defaultdict(set)

        # Add github_fork validated pairs
        for url1, url2 in combinations(group.project_urls, 2):
            if frozenset([url1, url2]) in validated_pairs:
                validated_adjacency[url1].add(url2)
                validated_adjacency[url2].add(url1)

        # Count commits per URL pair from links
        pair_commit_counts: dict[frozenset[str], int] = defaultdict(int)
        for link_urls in group.links.values():
            for url1, url2 in combinations(sorted(link_urls), 2):
                pair_commit_counts[frozenset([url1, url2])] += 1

        # Add pairs with enough shared commits as validated
        for pair, count in pair_commit_counts.items():
            if count >= min_shared_commits:
                url1, url2 = tuple(pair)
                validated_adjacency[url1].add(url2)
                validated_adjacency[url2].add(url1)

        # URLs not reachable via validated edges from canonical are suspicious
        start_url = group.canonical_url or sorted(group.project_urls)[0]
        reachable = reachable_from(start_url, validated_adjacency)
        group.suspicious_urls = group.project_urls - reachable


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
    url_to_path: dict[str, Path | None],
    commit_sets: dict[str, set[str]],
    min_files_changed: int,
    min_shared_commits: int,
) -> bool:
    """Try to validate a single suspicious URL against already-validated URLs."""
    path = url_to_path.get(url)
    if not path:
        return False

    url_commits = commit_sets.get(url)
    if not url_commits:
        return False

    with Repo(path) as repo:
        for validated_url in reachable:
            validated_path = url_to_path.get(validated_url)
            if not validated_path:
                continue

            validated_commits = commit_sets.get(validated_url)
            if not validated_commits:
                continue

            existing = sum(
                1 for urls in group.links.values() if url in urls and validated_url in urls
            )

            common = list(url_commits & validated_commits - group.shared_commits)
            if not common and existing < min_shared_commits:
                continue

            needed = min_shared_commits - existing
            with Repo(validated_path) as validated_repo:
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
    url_to_path: dict[str, Path | None],
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
                url_to_path,
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
) -> None:
    """Validate relationships and log warnings for suspicious groups."""
    relationships = RepositoryRelationships.load(relationships_path)
    logger.info("Loaded %d groups from %s", len(relationships.groups), relationships_path)

    project_urls = {e.project_url for e in entries if e.project_url}
    url_to_path = clone_repositories(entries)
    fork_edges, _ = asyncio.run(discover_github_forks_async(project_urls))
    commit_history = scan_commit_histories(project_urls, url_to_path)

    logger.info("Finding suspicious relationships in %d groups...", len(relationships.groups))
    _find_suspicious_project_relationships(relationships, fork_edges, min_shared_commits)
    _validate_suspicious_urls(
        relationships, commit_history, url_to_path, min_files_changed, min_shared_commits
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
