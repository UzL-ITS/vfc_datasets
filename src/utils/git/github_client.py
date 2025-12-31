"""Direct GitHub API client with rate limiting and retry logic."""

import asyncio
import logging
import time
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from config import GITHUB_TOKEN

logger = logging.getLogger(__name__)

# Suppress verbose per-request httpx logs
logging.getLogger("httpx").setLevel(logging.WARNING)


class AsyncGitHubClient:
    """Async client for GitHub API with rate limiting."""

    __slots__ = ("_rate_limit_limit", "_rate_limit_remaining", "client", "semaphore", "token")

    max_retries = 3
    default_rate_limit_wait = 60  # seconds
    request_timeout = 120.0  # seconds
    connect_timeout = 30.0  # seconds

    def __init__(self, max_concurrent: int = 30) -> None:
        self.token = GITHUB_TOKEN
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.client: httpx.AsyncClient | None = None
        self._rate_limit_remaining: int | None = None
        self._rate_limit_limit: int | None = None

    async def __aenter__(self) -> "AsyncGitHubClient":
        headers: dict[str, str] = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "vfc-datasets/2.0",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        else:
            logger.warning("No GITHUB_TOKEN configured - rate limits will be very low")

        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(self.request_timeout, connect=self.connect_timeout),
            headers=headers,
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
                            logger.warning("Unexpected status %d for: %s", response.status_code, api_url)
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
            logger.debug("Rate limited, waiting %d seconds (Retry-After)", wait)
            await asyncio.sleep(wait)
            return

        if (reset := headers.get("x-ratelimit-reset")) and reset.isdigit():
            server_time = self._parse_date_header(headers.get("date"))
            wait = int(reset) - server_time
            if wait > 0:
                logger.debug("Rate limited, waiting %d seconds", wait)
                await asyncio.sleep(wait)
            return

        logger.debug("Rate limited, waiting %d seconds (default)", self.default_rate_limit_wait)
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
    """Synchronous wrapper to query GitHub API."""

    async def _query() -> dict[str, Any] | None:
        async with AsyncGitHubClient() as client:
            return await client.query_api(api_url)

    return asyncio.run(_query())
