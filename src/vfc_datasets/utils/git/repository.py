import enum
import errno
import logging
import shutil
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse

from git import GitCommandError, InvalidGitRepositoryError, Repo
from tqdm.auto import tqdm

from vfc_datasets.config import BLOB_SIZE_LIMIT, GIT_CLONE_TIMEOUT, MAX_CLONE_WORKERS
from vfc_datasets.dataset_entry import DatasetEntry

from .url import url_to_pathname

logger = logging.getLogger(__name__)


class CloneStrategy(enum.Enum):
    """How much of a repository to fetch.

    PARTIAL: partial clone filtered by BLOB_SIZE_LIMIT; large blobs fetched on demand.
    FULL: all objects local. Cheaper once commits/repo exceeds FULL_CLONE_THRESHOLD.
    """

    PARTIAL = "partial"
    FULL = "full"


def _delete_corrupted_repo(destination: Path) -> None:
    """Delete corrupted repository directory if possible."""

    try:
        shutil.rmtree(destination)
    except Exception as exc:
        logger.error("Failed to remove invalid repository at %s: %s", destination, exc)


def _fetch_updates(repo: Repo, timeout: int) -> None:
    """Fetch latest changes from origin for an existing repository."""

    try:
        git_cmd = repo.git
        git_cmd.fetch("origin", kill_after_timeout=timeout)
        if not repo.head.is_detached:
            git_cmd.pull("origin", kill_after_timeout=timeout)
    except Exception as exc:
        logger.debug("Failed to fetch updates for %s: %s", repo.working_dir, exc)


def _checkout_branch(repo: Repo, branch: str | None, checkout_files: bool) -> None:
    """Checkout requested branch or ensure working tree exists."""

    target = branch
    if not target:
        try:
            if repo.head.is_detached:
                return
            target = repo.active_branch.name
        except Exception:
            return

    try:
        kwargs = {"force": True} if checkout_files else {}
        repo.git.checkout(target, **kwargs)
        logger.info("Checked out branch %s", target)
    except GitCommandError as exc:
        logger.warning("Failed to checkout %s: %s", target, exc)


def _clone_with_auth_bypass(
    git_url: str,
    destination: Path,
    clone_options: list[str],
    timeout: int,
) -> Repo | None:
    """Retry cloning after stripping credentials from URL."""

    parsed = urlparse(git_url)
    if not parsed.scheme or not parsed.hostname:
        return None

    clean_url = f"{parsed.scheme}://{parsed.hostname}{parsed.path}"

    try:
        logger.debug("Retrying clone without auth: %s", clean_url)
        return Repo.clone_from(
            clean_url,
            str(destination),
            multi_options=clone_options,
            kill_after_timeout=timeout,
            allow_unsafe_options=True,  # Required for -c options
        )
    except Exception as exc:
        logger.error("Auth bypass clone failed for %s: %s", clean_url, exc)
        return None


def _is_partial_clone(repo: Repo) -> bool:
    """Return True if the repo was cloned with any --filter=... option."""
    try:
        repo.git.config("--get", "remote.origin.partialclonefilter")
    except GitCommandError:
        return False
    return True


def _upgrade_to_full(repo: Repo, timeout: int) -> bool:
    """Remove partial-clone filter and refetch all objects. Requires git >= 2.41."""
    try:
        for key in ("remote.origin.promisor", "remote.origin.partialclonefilter"):
            try:
                repo.git.config("--unset", key)
            except GitCommandError:
                pass
        repo.git.fetch("origin", "--refetch", kill_after_timeout=timeout)
        logger.info("Upgraded %s from partial to full clone", repo.working_dir)
        return True
    except GitCommandError as exc:
        logger.warning("Failed to upgrade %s to full clone: %s", repo.working_dir, exc)
        return False


def _handle_existing_repo(
    destination: Path,
    branch: str | None,
    timeout: int,
    strategy: CloneStrategy,
) -> Repo | None:
    """Return existing repo if valid, optionally checking out branch."""
    try:
        repo = Repo(destination)
        _ = repo.head.commit
    except (InvalidGitRepositoryError, ValueError, GitCommandError):
        logger.warning("Invalid repository at %s, removing and recloning", destination)
        _delete_corrupted_repo(destination)
        return None
    except Exception as exc:
        logger.warning("Failed to access repository %s: %s", destination, exc)
        return None

    if strategy is CloneStrategy.FULL and _is_partial_clone(repo):
        if not _upgrade_to_full(repo, timeout):
            # Upgrade mutates filter config before fetching; on fetch failure
            # the repo is in an inconsistent state and must be recloned.
            logger.warning("Upgrade failed for %s, discarding for reclone", destination)
            repo.close()
            _delete_corrupted_repo(destination)
            return None

    if branch is not None:
        _fetch_updates(repo, timeout)
        _checkout_branch(repo, branch, checkout_files=False)

    return repo


def _clone_new_repo(
    git_url: str,
    destination: Path,
    branch: str | None,
    timeout: int,
    strategy: CloneStrategy,
) -> Repo | None:
    """Clone repository to destination path."""
    parsed = urlparse(git_url)
    if not parsed.scheme or not parsed.hostname:
        logger.error("Invalid URL format: %s", git_url)
        return None
    if parsed.scheme not in {"http", "https"}:
        logger.error("Unsupported URL scheme: %s", parsed.scheme)
        return None

    destination.parent.mkdir(parents=True, exist_ok=True)

    clone_options = [
        "--quiet",
        "--no-checkout",
        # Disable credential helpers to prevent auth prompts
        "-c",
        "credential.helper=",
        # Increase network timeouts for large repos (Chromium, Linux kernel, etc.)
        "-c",
        "http.lowSpeedLimit=1000",  # 1KB/s minimum
        "-c",
        "http.lowSpeedTime=600",  # 10 min before timeout
    ]
    if strategy is CloneStrategy.PARTIAL:
        clone_options.extend(["--filter", f"blob:limit={BLOB_SIZE_LIMIT}"])

    try:
        repo = Repo.clone_from(
            git_url,
            str(destination),
            multi_options=clone_options,
            kill_after_timeout=timeout,
            allow_unsafe_options=True,  # Required for -c options
        )
        if branch:
            _checkout_branch(repo, branch, checkout_files=False)
        return repo
    except GitCommandError as exc:
        message = str(exc).lower()
        if "authentication" in message:
            return _clone_with_auth_bypass(git_url, destination, clone_options, timeout)
        elif "repository not found" in message or "does not exist" in message:
            logger.warning("Repository not found: %s", git_url)
        else:
            logger.error("Git error cloning %s: %s", git_url, exc)
    except OSError as exc:
        if exc.errno == errno.ENOSPC:
            logger.error("No disk space available to clone %s", git_url)
        else:
            logger.error("OS error cloning %s: %s", git_url, exc)
    except ValueError as exc:
        logger.error("Invalid URL or parameters for %s: %s", git_url, exc)

    return None


def clone_repository(
    git_url: str,
    branch: str | None = None,
    timeout: int | None = None,
    strategy: CloneStrategy = CloneStrategy.PARTIAL,
) -> Repo | None:
    """Clone or reuse a git repository with a simplified interface."""
    git_url = (git_url or "").strip()
    if not git_url:
        logger.error("Empty git URL provided")
        return None

    if timeout is None:
        timeout = GIT_CLONE_TIMEOUT

    destination = Path(url_to_pathname(git_url))

    if destination.exists():
        repo = _handle_existing_repo(destination, branch, timeout, strategy)
        if repo:
            return repo

    return _clone_new_repo(git_url, destination, branch, timeout, strategy)


def clone_repositories(
    entries: Iterable[DatasetEntry],
    max_workers: int | None = None,
    branch: str | None = None,
    timeout: int | None = None,
    strategy: CloneStrategy | dict[str, CloneStrategy] = CloneStrategy.PARTIAL,
) -> dict[str, Repo | None]:
    """Clone all repositories from dataset entries using parallel processing.

    ``strategy`` may be a single CloneStrategy applied to every URL, or a dict
    mapping project_url -> CloneStrategy. URLs missing from the dict fall back
    to PARTIAL.
    """
    project_urls = {entry.project_url for entry in entries if entry.project_url}

    if not project_urls:
        logger.warning("No project URLs found in entries")
        return {}

    if timeout is None:
        timeout = GIT_CLONE_TIMEOUT

    if max_workers is None:
        max_workers = min(MAX_CLONE_WORKERS, len(project_urls))

    def _strategy_for(url: str) -> CloneStrategy:
        if isinstance(strategy, dict):
            return strategy.get(url, CloneStrategy.PARTIAL)
        return strategy

    results = {}
    failed_urls = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_url = {
            executor.submit(
                clone_repository,
                url,
                branch=branch,
                timeout=timeout,
                strategy=_strategy_for(url),
            ): url
            for url in project_urls
        }

        with tqdm(
            total=len(project_urls),
            desc="Cloning repositories",
            unit="repos",
            dynamic_ncols=True,
        ) as pbar:
            for future in as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    repo = future.result()
                    results[url] = repo

                    if repo is None:
                        failed_urls.append(url)
                        pbar.set_postfix_str(f"Failed: {len(failed_urls)}")

                except Exception:
                    logger.exception("Exception cloning %s", url)
                    results[url] = None
                    failed_urls.append(url)
                    pbar.set_postfix_str(f"Failed: {len(failed_urls)}")

                pbar.update(1)

    # Summary logging
    successful = sum(1 for repo in results.values() if repo is not None)
    logger.info(
        "Clone complete: %d/%d successful, %d failed",
        successful,
        len(project_urls),
        len(failed_urls),
    )

    if failed_urls:
        preview = ", ".join(failed_urls[:5])
        suffix = f" and {len(failed_urls) - 5} more" if len(failed_urls) > 5 else ""
        logger.warning("Failed to clone: %s%s", preview, suffix)

    return results
