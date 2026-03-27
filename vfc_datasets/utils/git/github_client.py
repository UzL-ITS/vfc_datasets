"""Direct GitHub API client with rate limiting and retry logic."""

import asyncio
import logging
import time
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Any, Self

import httpx
from tqdm.asyncio import tqdm as async_tqdm

from vfc_datasets.config import GITHUB_TOKEN

from .url import GitURL

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = httpx.Timeout(120.0, connect=30.0)


def _github_headers() -> dict[str, str]:
    """Build GitHub API request headers (with auth if configured)."""
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "vfc-datasets/2.0",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return headers


class AsyncGitHubClient:
    """Async client for GitHub API with rate limiting."""

    __slots__ = (
        "_rate_limit_limit",
        "_rate_limit_remaining",
        "client",
        "max_retries",
        "semaphore",
    )

    default_rate_limit_wait = 60  # seconds

    def __init__(self, max_concurrent: int = 30, max_retries: int = 3) -> None:
        self.max_retries = max_retries
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.client: httpx.AsyncClient | None = None
        self._rate_limit_remaining: int | None = None
        self._rate_limit_limit: int | None = None

    async def __aenter__(self) -> Self:
        logging.getLogger("httpx").setLevel(logging.WARNING)
        if not GITHUB_TOKEN:
            logger.warning(
                "No GITHUB_TOKEN configured - API rate limits will be severely restricted"
            )

        self.client = httpx.AsyncClient(
            timeout=_DEFAULT_TIMEOUT,
            headers=_github_headers(),
            follow_redirects=True,
        )
        return self

    async def __aexit__(self, *_: Any) -> None:
        if self.client:
            await self.client.aclose()

    async def query_api(self, api_url: str) -> dict[str, Any] | None:
        """Query GitHub API with retry and rate limit handling."""
        async with self.semaphore:
            for attempt in range(self.max_retries):
                try:
                    if self.client is None:
                        raise RuntimeError("Client not initialized. Use as context manager.")

                    response = await self.client.get(api_url)
                    self._update_rate_limit(response.headers)

                    match response.status_code:
                        case 200:
                            data = response.json()
                            return data if isinstance(data, dict) else None
                        case 403 | 429:
                            await self._wait_for_rate_limit(response.headers)
                            continue
                        case 404:
                            return None
                        case 500 | 502 | 503 | 504:
                            if attempt < self.max_retries - 1:
                                await asyncio.sleep(1 << attempt)
                                continue
                        case _:
                            logger.warning(
                                "Unexpected status %d for: %s", response.status_code, api_url
                            )
                            return None

                except httpx.TimeoutException:
                    if attempt < self.max_retries - 1:
                        continue
                except httpx.HTTPError as e:
                    logger.debug("HTTP error: %s", e)
                    if attempt < self.max_retries - 1:
                        continue
                except Exception:
                    logger.exception("Unexpected error for: %s", api_url)
                    return None

        return None

    async def _wait_for_rate_limit(self, headers: httpx.Headers) -> None:
        """Wait until rate limit resets."""
        if (retry_after := headers.get("retry-after")) and retry_after.isdigit():
            wait = int(retry_after)
            logger.warning("GitHub API rate limited, waiting %d seconds (Retry-After)", wait)
            await asyncio.sleep(wait)
            return

        if (reset := headers.get("x-ratelimit-reset")) and reset.isdigit():
            server_time = self._parse_date_header(headers.get("date"))
            wait = int(reset) - server_time
            if wait > 0:
                logger.warning("GitHub API rate limited, waiting %d seconds", wait)
                await asyncio.sleep(wait)
            return

        logger.warning(
            "GitHub API rate limited, waiting %d seconds (default)", self.default_rate_limit_wait
        )
        await asyncio.sleep(self.default_rate_limit_wait)

    def _update_rate_limit(self, headers: httpx.Headers) -> None:
        """Update rate limit tracking from response headers."""
        if remaining := headers.get("x-ratelimit-remaining"):
            self._rate_limit_remaining = int(remaining)
        if limit := headers.get("x-ratelimit-limit"):
            self._rate_limit_limit = int(limit)

    def get_rate_limit_status(self) -> str:
        """Get human-readable rate limit status."""
        if self._rate_limit_remaining is None or self._rate_limit_limit is None:
            return "Rate: ?/?"
        return f"Rate: {self._rate_limit_remaining}/{self._rate_limit_limit}"

    @staticmethod
    def _parse_date_header(date_str: str | None) -> int:
        """Parse HTTP Date header to Unix timestamp."""
        if date_str:
            try:
                return int(parsedate_to_datetime(date_str).timestamp())
            except (ValueError, TypeError):
                pass
        # Fallback: assume no clock skew
        return int(time.time())


def query_github_api_sync(api_url: str) -> dict[str, Any] | None:
    """Synchronous single-request GitHub API query."""
    try:
        response = httpx.get(
            api_url,
            headers=_github_headers(),
            timeout=_DEFAULT_TIMEOUT,
            follow_redirects=True,
        )
        if response.status_code == 200:
            data = response.json()
            return data if isinstance(data, dict) else None
        if response.status_code == 404:
            return None
        logger.warning("GitHub API returned %d for: %s", response.status_code, api_url)
    except httpx.HTTPError as e:
        logger.debug("GitHub API sync request failed: %s", e)

    return None


@dataclass
class ForkInfo:
    """Fork relationship info for a GitHub repository."""

    parent: str | None = None
    source: str | None = None
    is_fork: bool = False


async def _fetch_single_repo_info(
    project_url: str,
    client: AsyncGitHubClient,
) -> tuple[str, ForkInfo]:
    """Fetch fork info for a single GitHub repository."""
    result = ForkInfo()

    git_url = GitURL.parse(project_url)
    api_url = git_url.to_github_api_url() if git_url else None
    if not api_url:
        return project_url, result

    try:
        data = await client.query_api(api_url)

        if data:
            result.is_fork = data.get("fork", False)

            if data.get("fork") and data.get("parent"):
                parent_url = data["parent"].get("html_url")
                if parent_url:
                    result.parent = parent_url.lower()

            if data.get("source"):
                source_url = data["source"].get("html_url")
                if source_url:
                    result.source = source_url.lower()

    except (httpx.HTTPError, KeyError, ValueError) as e:
        logger.debug("Failed to fetch repo info for %s: %s", project_url, e)

    return project_url, result


async def fetch_github_fork_info(project_urls: set[str]) -> dict[str, ForkInfo]:
    """Fetch fork info for multiple GitHub URLs."""
    result: dict[str, ForkInfo] = {}

    github_urls = {
        url for url in project_urls if (parsed := GitURL.parse(url)) and parsed.host == "github.com"
    }

    for url in project_urls - github_urls:
        result[url] = ForkInfo()

    if not github_urls:
        logger.info("No GitHub URLs to check for fork relationships")
        return result

    async with AsyncGitHubClient() as client:
        tasks = [_fetch_single_repo_info(url, client) for url in github_urls]

        pbar = async_tqdm(
            total=len(tasks),
            desc="Fetching GitHub repo info",
            dynamic_ncols=True,
            unit="repos",
        )

        for task in asyncio.as_completed(tasks):
            url, info = await task
            pbar.update(1)
            pbar.set_postfix_str(client.get_rate_limit_status())
            result[url] = info

        pbar.close()

    return result
