from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import ParseResult, parse_qs, unquote, urlparse

from config import REPOSITORY_PATH

logger = logging.getLogger(__name__)

# Commit hash validation
MIN_COMMIT_LENGTH = 5
COMMIT_HASH_PATTERN = re.compile(rf"^[a-f0-9]{{{MIN_COMMIT_LENGTH},40}}$", re.IGNORECASE)


@dataclass(slots=True)
class GitURL:
    """Unified representation of a Git repository URL."""

    scheme: str
    host: str
    path: str
    owner: str | None = None
    repo: str | None = None
    commit_id: str | None = None
    _is_gitweb: bool = False

    @classmethod
    def parse(cls, url: str, prefer_https: bool = True) -> GitURL | None:
        """Parse any Git URL format into a GitURL object."""
        if not url:
            return None

        url = unquote(url.strip())
        git_url: GitURL | None = None

        # Handle SSH URLs
        if url.startswith(("git@", "ssh://")):
            git_url = cls._parse_ssh_url(url)
            if git_url and prefer_https:
                git_url.scheme = "https"
        else:
            # Handle git:// protocol
            if url.startswith("git://"):
                url = url.replace("git://", "https://" if prefer_https else "http://", 1)

            # Parse standard URLs
            try:
                parsed = urlparse(url)
                if not parsed.scheme or not parsed.netloc or not parsed.hostname:
                    return None
                if parsed.scheme not in ("http", "https"):
                    return None

                hostname = parsed.hostname.removeprefix("www.")
                git_url = cls(scheme=parsed.scheme, host=hostname, path=parsed.path)
                git_url._extract_components(parsed)
            except (ValueError, TypeError, AttributeError):
                logger.exception("Failed to parse URL: %s", url)
                return None

        if git_url and not git_url.is_valid():
            logger.debug("Invalid URL: %s (owner=%s, repo=%s)", url, git_url.owner, git_url.repo)

        return git_url

    @classmethod
    def _parse_ssh_url(cls, ssh_url: str) -> GitURL | None:
        """Parse SSH URL formats (SCP-style or URL-style)."""
        for pattern in (
            r"^(?P<user>\w+)@(?P<host>[^:]+):(?P<path>.+)$",  # git@host:path
            r"^ssh://(?P<user>\w+)@(?P<host>[^/]+)/(?P<path>.+)$",  # ssh://git@host/path
        ):
            if match := re.match(pattern, ssh_url):
                path = match.group("path").removesuffix(".git")
                git_url = cls(scheme="ssh", host=match.group("host"), path="/" + path)
                git_url._extract_components(None)
                return git_url
        return None

    def _extract_components(self, parsed_url: ParseResult | None) -> None:
        """Extract owner, repo, and commit_id based on platform patterns."""

        path = self._normalized_path()

        match self.host:
            case "github.com":
                self._extract_github(path)
            case host if "gitlab" in host:
                self._extract_gitlab(path)
            case host if "bitbucket" in host:
                self._extract_bitbucket(path)
            case host if host.endswith("googlesource.com"):
                self._extract_googlesource(path)
            case host if host.startswith("git.savannah."):
                self._extract_savannah(path, parsed_url)
            case "git.kernel.org":
                self._extract_kernel_org(parsed_url)
            case "cgit.freedesktop.org":
                self._extract_cgit_freedesktop(parsed_url)
            case _:
                self._extract_generic(path, parsed_url)

    def _normalized_path(self) -> str:
        path = self.path.rstrip("/")
        if path.endswith(".git"):
            return path[:-4]
        return path

    def _extract_github(self, path: str) -> None:
        parts = [p for p in path.split("/") if p]
        if len(parts) >= 2:
            self.owner, self.repo = parts[0], parts[1]
        if len(parts) >= 4 and parts[2] == "commit" and COMMIT_HASH_PATTERN.fullmatch(parts[3]):
            self.commit_id = parts[3].lower()

    def _extract_gitlab(self, path: str) -> None:
        path_lower = path.lower()
        for delimiter in ["/-/", "/tree/", "/blob/", "/commit/", "/merge_requests/"]:
            if delimiter in path_lower:
                repo_path = path[: path_lower.index(delimiter)]
                if "/-/commit/" in path_lower:
                    commit_start = path_lower.index("/-/commit/") + len("/-/commit/")
                    commit_part = path[commit_start:].split("/")[0]
                    if COMMIT_HASH_PATTERN.fullmatch(commit_part):
                        self.commit_id = commit_part.lower()
                path = repo_path
                break

        parts = [p for p in path.split("/") if p]
        if not parts:
            return
        if len(parts) >= 2:
            self.owner = "/".join(parts[:-1])
            self.repo = parts[-1]
        else:
            self.repo = parts[0]

    def _extract_bitbucket(self, path: str) -> None:
        parts = [p for p in path.split("/") if p]
        if len(parts) >= 2:
            self.owner, self.repo = parts[0], parts[1]
        if len(parts) >= 4 and parts[2] == "commits" and COMMIT_HASH_PATTERN.fullmatch(parts[3]):
            self.commit_id = parts[3].lower()

    def _extract_googlesource(self, path: str) -> None:
        if "/+/" in path:
            repo_path = path[: path.index("/+/")]
            commit_part = path[path.index("/+/") + 3 :].split("/")[0]
            if COMMIT_HASH_PATTERN.fullmatch(commit_part):
                self.commit_id = commit_part.lower()
            path = repo_path
        self.repo = path.lstrip("/")

    def _extract_savannah(self, path: str, parsed_url: ParseResult | None) -> None:
        """Extract repo from GNU Savannah URLs (cgit, gitweb, or direct git paths)."""
        # Handle gitweb URLs: ?p=project.git
        if parsed_url and parsed_url.query and "p=" in parsed_url.query:
            query = parsed_url.query.replace(";", "&")
            params = parse_qs(query)
            if "p" in params:
                repo = params["p"][0]
                if repo.endswith(".git"):
                    repo = repo[:-4]
                self.repo = repo
                self._is_gitweb = True
                return

        # Handle cgit URLs: /cgit/project.git or /cgit/group/project.git
        if "/cgit/" in path:
            cgit_path = path[path.index("/cgit/") + 6 :]
            # Remove /commit suffix if present
            if "/commit" in cgit_path:
                cgit_path = cgit_path[: cgit_path.index("/commit")]
            # Extract commit hash if present
            if "/commit/" in path:
                commit_part = path[path.index("/commit/") + 8 :].split("/")[0]
                if COMMIT_HASH_PATTERN.fullmatch(commit_part):
                    self.commit_id = commit_part.lower()
            self.repo = cgit_path.removesuffix(".git") if cgit_path else None
            return

        # Handle direct git URLs: /git/project.git
        if "/git/" in path:
            git_path = path[path.index("/git/") + 5 :]
            self.repo = git_path.removesuffix(".git") if git_path else None
            return

        # Fallback to generic extraction
        self._extract_generic(path, parsed_url)

    def _extract_kernel_org(self, parsed_url: ParseResult | None) -> None:
        """Extract repo from git.kernel.org URLs.

        Clone URL:  https://git.kernel.org/pub/scm/PATH.git
        Web URL:    https://git.kernel.org/pub/scm/PATH.git/commit/?id=HASH
        cgit URL:   https://git.kernel.org/cgit/PATH.git
        gitweb URL: https://git.kernel.org/?p=PATH.git
        """
        path = self.path

        # Extract commit ID from query string (?id=HASH) or path (/commit/HASH)
        if parsed_url and parsed_url.query:
            query = parsed_url.query.replace(";", "&")
            params = parse_qs(query)
            if "id" in params and COMMIT_HASH_PATTERN.fullmatch(params["id"][0]):
                self.commit_id = params["id"][0].lower()

            # Handle gitweb-style URLs: ?p=linux/kernel/git/torvalds/linux.git;h=HASH
            if "p" in params:
                repo = params["p"][0]
                if repo.endswith(".git"):
                    repo = repo[:-4]
                self.repo = repo
                self._is_gitweb = True
                # Extract commit from h parameter (gitweb uses h= for commit hash)
                if "h" in params and COMMIT_HASH_PATTERN.fullmatch(params["h"][0]):
                    self.commit_id = params["h"][0].lower()
                return

        if "/commit/" in path:
            commit_part = path[path.index("/commit/") + 8 :].split("/")[0].split("?")[0]
            if COMMIT_HASH_PATTERN.fullmatch(commit_part):
                self.commit_id = commit_part.lower()

        # Extract repo path from /pub/scm/ or /cgit/ format
        if "/pub/scm/" in path and ".git" in path:
            start = path.index("/pub/scm/") + 9
            end = path.index(".git")
            self.repo = path[start:end]
        elif "/cgit/" in path and ".git" in path:
            start = path.index("/cgit/") + 6
            end = path.index(".git")
            self.repo = path[start:end]

    def _extract_cgit_freedesktop(self, parsed_url: ParseResult | None) -> None:
        """Extract repo from cgit.freedesktop.org URLs, stripping web paths."""
        path = self.path.rstrip("/")

        # Extract commit ID from query string (?id=HASH)
        if parsed_url and parsed_url.query:
            params = parse_qs(parsed_url.query)
            if "id" in params and COMMIT_HASH_PATTERN.fullmatch(params["id"][0]):
                self.commit_id = params["id"][0].lower()

        # Strip cgit web paths to get repo
        for suffix in ("/commit", "/tree", "/log", "/diff", "/refs", "/snapshot", "/patch"):
            if suffix in path:
                path = path[: path.index(suffix)]
                break

        # Update self.path to the normalized form for to_https_url()
        self.path = path
        self.repo = path.lstrip("/") if path and path != "/" else None

    def _extract_generic(self, path: str, parsed_url: ParseResult | None) -> None:
        if parsed_url and parsed_url.query and "p=" in parsed_url.query:
            query = parsed_url.query.replace(";", "&")
            params = parse_qs(query)
            if "p" in params:
                repo = params["p"][0]
                if repo.endswith(".git"):
                    repo = repo[:-4]
                self.repo = repo
                self._is_gitweb = True
                return

        if "/cgit/" in path:
            match = re.search(r"/cgit/([^/]+)", path)
            if match:
                repo = match.group(1)
                if repo.endswith(".git"):
                    repo = repo[:-4]
                self.repo = repo

        for delimiter in ["/commit/", "/commits/", "/tree/", "/blob/", "/src/", "/browse/"]:
            if delimiter in path:
                commit_part = path[path.index(delimiter) + len(delimiter) :].split("/")[0]
                if COMMIT_HASH_PATTERN.fullmatch(commit_part):
                    self.commit_id = commit_part.lower()
                break

        if not self.repo and path:
            parts = [p for p in path.split("/") if p]
            if parts:
                self.repo = parts[-1]

    def to_https_url(self) -> str | None:
        """Convert to HTTPS URL format."""
        base_url = f"https://{self.host}"

        # GNU Savannah: always return the clone URL format (/git/repo.git)
        if self.host.startswith("git.savannah.") and self.repo:
            return f"{base_url}/git/{self.repo}.git"

        # git.kernel.org: clone URL is /pub/scm/REPO.git
        if self.host == "git.kernel.org" and self.repo:
            return f"{base_url}/pub/scm/{self.repo}.git"

        # cgit.freedesktop.org: return normalized URL (repos moved to gitlab)
        if self.host == "cgit.freedesktop.org" and self.repo:
            return f"{base_url}/{self.repo}"

        # Special handling for gitweb URLs (non-Savannah)
        if self._is_gitweb and self.repo:
            return f"{base_url}/?p={self.repo}.git"

        # Platform-specific formats with owner/repo
        if self.owner and self.repo:
            if self.host == "github.com":
                return f"{base_url}/{self.owner.lower()}/{self.repo.lower()}"
            if "gitlab" in self.host or "bitbucket" in self.host:
                return f"{base_url}/{self.owner}/{self.repo}"

        if self.host.endswith("googlesource.com") and self.repo:
            return f"{base_url}/{self.repo}"

        # Generic format - strip .git suffix and VCS paths
        path = self.path.rstrip("/").removesuffix(".git")
        if not path or path == "/":
            return None

        # Strip common VCS path segments (but not if at root)
        for delim in ("/commit/", "/commits/", "/tree/", "/blob/", "/src/", "/browse/"):
            if (idx := path.find(delim)) > 0:
                path = path[:idx]
                break

        return None if not path or path == "/" else f"{base_url}{path}"

    def is_valid(self) -> bool:
        """Check if the parsed URL has sufficient components."""
        if not self.scheme or not self.host:
            return False
        # Major platforms require owner and repo
        if self.host in ("github.com", "gitlab.com", "bitbucket.org"):
            return bool(self.owner and self.repo)
        # Other platforms need at least a path or repo
        return bool(self.path or self.repo)

    def __str__(self) -> str:
        """String representation (defaults to HTTPS URL)."""
        # to_https_url may return None for generic hosts; ensure __str__ returns a string
        return self.to_https_url() or f"https://{self.host}"

    def __repr__(self) -> str:
        """Detailed representation for debugging."""
        return (
            f"GitURL(scheme={self.scheme!r}, host={self.host!r}, "
            f"owner={self.owner!r}, repo={self.repo!r}, "
            f"commit_id={self.commit_id!r})"
        )


def normalize_commit_id(url_or_commit_id: str | None) -> str | None:
    """Normalize and validate a commit hash (optionally extracted from a URL)."""
    if not url_or_commit_id or not isinstance(url_or_commit_id, str):
        return None

    value = url_or_commit_id.strip()
    if not value:
        return None

    # Remove any URL fragment (e.g., #diff-...) or query parameters (e.g., ?w=1)
    value = value.split("#", 1)[0]
    value = value.split("?", 1)[0]
    value = value.strip()
    if not value:
        return None

    if COMMIT_HASH_PATTERN.fullmatch(value):
        return value.lower()

    git_url = GitURL.parse(value)
    if git_url and git_url.commit_id:
        return git_url.commit_id

    logger.debug("Invalid commit ID format: %r", url_or_commit_id)
    return None


def url_to_pathname(url: str) -> str:
    """Convert a Git URL to a local filesystem pathname."""
    git_url = GitURL.parse(url)

    if git_url and git_url.host == "github.com" and git_url.owner and git_url.repo:
        dir_name = f"gh_{git_url.owner.lower()}_{git_url.repo.lower()}"
    else:
        # Fallback to hash-based naming
        dir_name = ""
        if git_url and git_url.owner and git_url.repo:
            dir_name = f"{git_url.owner}_{git_url.repo}_"

        # Add hash for uniqueness
        hasher = hashlib.sha256()
        hasher.update(url.encode("utf-8"))
        dir_name += hasher.hexdigest()

    return str(Path(REPOSITORY_PATH) / dir_name)
