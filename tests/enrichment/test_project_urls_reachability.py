"""Verify moved/unreachable project URLs are correctly categorized."""

from __future__ import annotations

import subprocess
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed

import pytest
from tqdm import tqdm

from transformations.enrichment.project_urls.url_mappings import _load, get_moved_urls
from utils.git.repository import clone_repository


def _get_unreachable_urls() -> dict[str, dict]:
    """Get full unreachable URLs dict (not just keys)."""
    return _load("unreachable_project_urls.json")


def is_reachable(url: str, timeout: int = 600) -> bool:
    """Check if URL is reachable via git ls-remote (fast, no clone)."""
    try:
        result = subprocess.run(
            ["git", "ls-remote", "--heads", "--exit-code", url],
            capture_output=True,
            timeout=timeout,
        )
        return result.returncode in (0, 2)
    except (subprocess.TimeoutExpired, Exception):
        return False


def find_reachable(urls: list[str], desc: str = "Checking") -> str | None:
    """Return first reachable URL, or None if none are reachable."""
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(is_reachable, url): url for url in urls}
        for future in tqdm(as_completed(futures), total=len(urls), desc=desc):
            if future.result():
                executor.shutdown(wait=False, cancel_futures=True)
                return futures[future]
    return None


def clone_all(urls: list[str], desc: str = "Cloning") -> list[str]:
    """Clone all URLs, return list of failures."""
    failures = []
    with ProcessPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(clone_repository, url): url for url in urls}
        for future in tqdm(as_completed(futures), total=len(urls), desc=desc):
            if future.result() is None:
                failures.append(futures[future])
    return failures


class TestStructure:

    def test_moved_urls_format(self) -> None:
        for src, dst in get_moved_urls().items():
            assert src.startswith("https://"), f"Source should be https: {src}"
            assert dst.startswith("https://"), f"Target should be https: {dst}"

    def test_unreachable_urls_format(self) -> None:
        for url, info in _get_unreachable_urls().items():
            assert url.startswith("https://"), f"Should be https: {url}"
            assert "reason" in info and "checked" in info

    def test_no_overlap(self) -> None:
        moved_keys = set(get_moved_urls().keys())
        unreachable_keys = set(_get_unreachable_urls().keys())
        overlap = moved_keys & unreachable_keys
        assert not overlap, f"URLs in both moved and unreachable: {overlap}"


class TestReachability:

    @pytest.mark.slow
    @pytest.mark.network
    def test_moved_sources_not_reachable(self) -> None:
        url = find_reachable(list(get_moved_urls().keys()), desc="Checking moved sources")
        assert url is None, f"Reachable (remove from mapping): {url}"

    @pytest.mark.slow
    @pytest.mark.network
    def test_moved_targets_clonable(self) -> None:
        targets = list(set(get_moved_urls().values()))
        failures = clone_all(targets, desc="Cloning targets")
        real_failures = [url for url in failures if not is_reachable(url)]
        assert not real_failures, f"Broken targets: {real_failures}"

    @pytest.mark.slow
    @pytest.mark.network
    def test_unreachable_not_reachable(self) -> None:
        url = find_reachable(list(_get_unreachable_urls().keys()), desc="Checking unreachable")
        assert url is None, f"Now reachable (remove from list): {url}"
