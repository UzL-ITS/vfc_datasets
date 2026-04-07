import hashlib
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Self, override
from urllib.parse import ParseResult, parse_qs, unquote, urlparse

logger = logging.getLogger(__name__)

GITHUB_API_URL = os.getenv("GITHUB_API_URL", "https://api.github.com")

# Commit hash validation
MIN_COMMIT_LENGTH = 5
_COMMIT_HASH_PATTERN = re.compile(rf"^[a-f0-9]{{{MIN_COMMIT_LENGTH},40}}$", re.IGNORECASE)

# Pattern for git-describe style identifiers: tag-N-g<hash>
_GIT_DESCRIBE_PATTERN = re.compile(r".+-g(?P<hash>[a-f0-9]{7,40})$", re.IGNORECASE)

# GitLab URL patterns
_GITLAB_COMMIT_PATTERN = re.compile(r"/-/commit/([^/]+)", re.IGNORECASE)
_GITLAB_SPLIT_PATTERN = re.compile(r"/-/|/tree/|/blob/|/commit/|/merge_requests/", re.IGNORECASE)

# cgit repo extraction
_CGIT_REPO_PATTERN = re.compile(r"/cgit/([^/]+)")

# Common VCS path delimiters used for stripping web UI paths
_VCS_DELIMITERS = ("/commit/", "/commits/", "/tree/", "/blob/", "/src/", "/browse/")


@dataclass(slots=True)
class GitURL:
    """Unified representation of a Git repository URL."""

    scheme: str
    host: str
    path: str
    owner: str | None = None
    repo: str | None = None
    commit_id: str | None = None

    @classmethod
    def parse(cls, url: str, prefer_https: bool = True) -> Self | None:
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
    def _parse_ssh_url(cls, ssh_url: str) -> Self | None:
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
            case h if "gitlab" in h:
                self._extract_gitlab(path)
            case h if "bitbucket" in h:
                self._extract_bitbucket(path)
            case h if h.endswith("googlesource.com"):
                self._extract_googlesource(path)
            case h if h.startswith("git.savannah."):
                self._extract_savannah(path, parsed_url)
            case "git.kernel.org":
                self._extract_kernel_org(parsed_url)
            case "cgit.freedesktop.org":
                self._extract_cgit_freedesktop(parsed_url)
            case _:
                self._extract_generic(path, parsed_url)

    def _try_parse_gitweb(self, parsed_url: ParseResult | None) -> bool:
        """Try to extract repo from gitweb ?p= parameter. Returns True if handled."""
        if not parsed_url or not parsed_url.query or "p=" not in parsed_url.query:
            return False
        query = parsed_url.query.replace(";", "&")
        params = parse_qs(query)
        if "p" not in params:
            return False
        repo = params["p"][0]
        if repo.endswith(".git"):
            repo = repo[:-4]
        self.repo = repo
        if "h" in params and _COMMIT_HASH_PATTERN.fullmatch(params["h"][0]):
            self.commit_id = params["h"][0].lower()
        return True

    def _normalized_path(self) -> str:
        path = self.path.rstrip("/")
        if path.endswith(".git"):
            return path[:-4]
        return path

    def _extract_github(self, path: str) -> None:
        parts = [p for p in path.split("/") if p]
        if len(parts) >= 2:
            self.owner, self.repo = parts[0], parts[1]
        if len(parts) >= 4 and parts[2] == "commit":
            commit_part = parts[3]
            if _COMMIT_HASH_PATTERN.fullmatch(commit_part):
                self.commit_id = commit_part.lower()
            elif match := _GIT_DESCRIBE_PATTERN.fullmatch(commit_part):
                self.commit_id = match.group("hash").lower()
            else:
                self.commit_id = commit_part

    def _extract_gitlab(self, path: str) -> None:
        commit_match = _GITLAB_COMMIT_PATTERN.search(path)
        if commit_match and _COMMIT_HASH_PATTERN.fullmatch(commit_match.group(1)):
            self.commit_id = commit_match.group(1).lower()

        repo_path = _GITLAB_SPLIT_PATTERN.split(path)[0]

        parts = [p for p in repo_path.split("/") if p]
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
        if len(parts) >= 4 and parts[2] == "commits" and _COMMIT_HASH_PATTERN.fullmatch(parts[3]):
            self.commit_id = parts[3].lower()

    def _extract_googlesource(self, path: str) -> None:
        if (idx := path.find("/+/")) >= 0:
            commit_part = path[idx + 3 :].split("/")[0]
            # Strip common git revision suffixes (e.g., ^!, ~1)
            commit_hash = re.split(r"[\^~!]", commit_part)[0]
            if _COMMIT_HASH_PATTERN.fullmatch(commit_hash):
                self.commit_id = commit_hash.lower()
            path = path[:idx]
        self.repo = path.lstrip("/")

    def _extract_savannah(self, path: str, parsed_url: ParseResult | None) -> None:
        """Extract repo from GNU Savannah URLs (cgit, gitweb, or direct git paths)."""
        if self._try_parse_gitweb(parsed_url):
            return

        # Handle cgit URLs: /cgit/project.git or /cgit/group/project.git
        if (cgit_idx := path.find("/cgit/")) >= 0:
            cgit_path = path[cgit_idx + 6 :]
            # Remove /commit suffix if present (with or without trailing slash)
            if (ci := cgit_path.find("/commit")) >= 0:
                cgit_path = cgit_path[:ci]
            # Extract commit hash if present (with or without trailing slash)
            if (commit_idx := path.find("/commit")) >= 0:
                after_commit = path[commit_idx + 7 :].lstrip("/")
                commit_part = after_commit.split("/")[0].split("?")[0] if after_commit else ""
                if commit_part and _COMMIT_HASH_PATTERN.fullmatch(commit_part):
                    self.commit_id = commit_part.lower()
            self.repo = cgit_path.removesuffix(".git") if cgit_path else None
            return

        # Handle direct git URLs: /git/project.git
        if (git_idx := path.find("/git/")) >= 0:
            git_path = path[git_idx + 5 :]
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
            if "id" in params and _COMMIT_HASH_PATTERN.fullmatch(params["id"][0]):
                self.commit_id = params["id"][0].lower()

        if self._try_parse_gitweb(parsed_url):
            return

        if (commit_idx := path.find("/commit/")) >= 0:
            commit_part = path[commit_idx + 8 :].split("/")[0].split("?")[0]
            if _COMMIT_HASH_PATTERN.fullmatch(commit_part):
                self.commit_id = commit_part.lower()

        # Extract repo path from /pub/scm/ or /cgit/ format
        git_end = path.find(".git")
        if (scm_idx := path.find("/pub/scm/")) >= 0 and git_end >= 0:
            self.repo = path[scm_idx + 9 : git_end]
        elif (cgit_idx := path.find("/cgit/")) >= 0 and git_end >= 0:
            self.repo = path[cgit_idx + 6 : git_end]

    def _extract_cgit_freedesktop(self, parsed_url: ParseResult | None) -> None:
        """Extract repo from cgit.freedesktop.org URLs, stripping web paths."""
        path = self.path.rstrip("/")

        # Extract commit ID from query string (?id=HASH)
        if parsed_url and parsed_url.query:
            params = parse_qs(parsed_url.query)
            if "id" in params and _COMMIT_HASH_PATTERN.fullmatch(params["id"][0]):
                self.commit_id = params["id"][0].lower()

        # Strip cgit web paths to get repo
        for suffix in ("/commit", "/tree", "/log", "/diff", "/refs", "/snapshot", "/patch"):
            if (idx := path.find(suffix)) >= 0:
                path = path[:idx]
                break

        # Update self.path to the normalized form for to_https_url()
        self.path = path
        self.repo = path.lstrip("/") if path and path != "/" else None

    def _extract_generic(self, path: str, parsed_url: ParseResult | None) -> None:
        if self._try_parse_gitweb(parsed_url):
            return

        if "/cgit/" in path:
            match = _CGIT_REPO_PATTERN.search(path)
            if match:
                repo = match.group(1)
                if repo.endswith(".git"):
                    repo = repo[:-4]
                self.repo = repo

        for delimiter in _VCS_DELIMITERS:
            if (idx := path.find(delimiter)) >= 0:
                commit_part = path[idx + len(delimiter) :].split("/")[0]
                if _COMMIT_HASH_PATTERN.fullmatch(commit_part):
                    self.commit_id = commit_part.lower()
                elif match := _GIT_DESCRIBE_PATTERN.fullmatch(commit_part):
                    self.commit_id = match.group("hash").lower()
                break

        if not self.repo and path:
            parts = [p for p in path.split("/") if p]
            if parts:
                self.repo = parts[-1]

    def to_github_api_url(self, path: str = "") -> str | None:
        """Build GitHub API URL for this repo, e.g. path='/commits/{sha}'.

        Returns None if not a GitHub URL or missing owner/repo.
        """
        if self.host != "github.com" or not self.owner or not self.repo:
            return None
        return f"{GITHUB_API_URL}/repos/{self.owner}/{self.repo}{path}"

    def to_https_url(self) -> str | None:
        """Convert to HTTPS URL format."""
        base_url = f"https://{self.host}"

        match self.host:
            case h if h.startswith("git.savannah.") and self.repo:
                return f"{base_url}/git/{self.repo}.git"
            case "git.kernel.org" if self.repo:
                return f"{base_url}/pub/scm/{self.repo}.git"
            case "cgit.freedesktop.org" if self.repo:
                return f"{base_url}/{self.repo}"
            case "github.com" if self.owner and self.repo:
                return f"{base_url}/{self.owner.lower()}/{self.repo.lower()}"
            case h if ("gitlab" in h or "bitbucket" in h) and self.owner and self.repo:
                return f"{base_url}/{self.owner}/{self.repo}"
            case h if h.endswith("googlesource.com") and self.repo:
                return f"{base_url}/{self.repo}"

        # Gitweb URLs: repo was extracted from ?p= query param, not from the path
        if self.repo and self.repo not in self.path:
            return f"{base_url}/?p={self.repo}.git"

        # Generic format - strip .git suffix and VCS paths
        path = self.path.rstrip("/").removesuffix(".git")
        if not path or path == "/":
            return None

        # Strip common VCS path segments (but not if at root)
        for delim in _VCS_DELIMITERS:
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

    @override
    def __str__(self) -> str:
        """String representation (defaults to HTTPS URL)."""
        # to_https_url may return None for generic hosts; ensure __str__ returns a string
        return self.to_https_url() or f"https://{self.host}"

    @override
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

    if _COMMIT_HASH_PATTERN.fullmatch(value):
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

        dir_name += hashlib.sha256(url.encode()).hexdigest()

    repo_path = Path(os.getenv("REPOSITORY_PATH", ".data/repositories"))
    return str(repo_path / dir_name)
