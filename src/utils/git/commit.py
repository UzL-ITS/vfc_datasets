"""Git commit analysis utilities."""

import hashlib
import logging

from git import Repo
from git.exc import GitCommandError

logger = logging.getLogger(__name__)

# Template/config files to exclude from "substantial" commit checks.
# Commits touching ONLY these files are not considered substantial.
TEMPLATE_FILE_PATTERNS = frozenset(
    {
        # Git/repo files
        ".gitignore",
        ".gitattributes",
        ".gitmodules",
        # Documentation
        "readme",
        "readme.md",
        "readme.txt",
        "readme.rst",
        "license",
        "license.md",
        "license.txt",
        "licence",
        "changelog",
        "changelog.md",
        "changes",
        "history",
        "contributing",
        "contributing.md",
        "code_of_conduct",
        "code_of_conduct.md",
        "authors",
        "authors.md",
        "contributors",
        # Python
        "setup.py",
        "setup.cfg",
        "pyproject.toml",
        "requirements.txt",
        "requirements-dev.txt",
        "manifest.in",
        "tox.ini",
        ".flake8",
        ".pylintrc",
        # JavaScript/Node
        "package.json",
        "package-lock.json",
        "yarn.lock",
        ".npmrc",
        ".nvmrc",
        ".eslintrc",
        ".prettierrc",
        "tsconfig.json",
        "jsconfig.json",
        # Ruby
        "gemfile",
        "gemfile.lock",
        ".ruby-version",
        # Rust
        "cargo.toml",
        "cargo.lock",
        # Go
        "go.mod",
        "go.sum",
        # Build/CI
        "makefile",
        "dockerfile",
        ".dockerignore",
        ".travis.yml",
        ".github",
        ".gitlab-ci.yml",
        "jenkinsfile",
        "azure-pipelines.yml",
        # Editor/IDE
        ".editorconfig",
        ".vscode",
        ".idea",
    }
)


def get_all_commit_ids(repo: Repo) -> list[str]:
    """Get all commit IDs from a repository."""
    try:
        result = repo.git.rev_list("--all")
        return result.strip().split("\n") if result.strip() else []
    except GitCommandError as e:
        logger.debug("Failed to get commit IDs: %s", e)
        return []


def is_template_file(filename: str) -> bool:
    """Check if a filename is a template/config file."""
    basename = filename.rsplit("/", 1)[-1].lower()
    return basename in TEMPLATE_FILE_PATTERNS


def get_commit_signature_if_substantial(
    repo: Repo,
    commit_id: str,
    min_files: int = 2,
    max_files: int = 20,
) -> tuple[str, str] | None:
    """Get commit signature if substantial, else None.

    Uses only fast git operations (no diff computation).
    Returns (content_hash, files_hash) or None if not substantial.
    """
    try:
        # Fast: get file names only (tree traversal, no diff computation)
        names = repo.git.diff_tree("--name-only", "-r", commit_id).strip()
        if not names:
            return None

        # First line is commit hash, rest are file names
        changed_files = [f for f in names.split("\n")[1:] if f]

        # Filter by file count (skip tiny and huge commits)
        if len(changed_files) < min_files or len(changed_files) > max_files:
            return None

        # Filter out template-only commits
        non_template_files = [f for f in changed_files if not is_template_file(f)]
        if len(non_template_files) < min_files:
            return None

        # Fast: get message + author + timestamp in one call (no diff)
        # Format: message, then separator, then author|email|timestamp
        output = repo.git.show(commit_id, format="%B%n--SIG--%n%an|%ae|%at", no_patch=True).strip()
        if not output or "--SIG--" not in output:
            return None

        parts = output.split("--SIG--")
        message = parts[0].strip()
        metadata = parts[1].strip() if len(parts) > 1 else ""

        # Signature: hash(message + author metadata) + hash(sorted files)
        content = f"{message}\n{metadata}"
        content_hash = hashlib.sha256(content.encode(errors="surrogatepass")).hexdigest()
        files_str = "\n".join(sorted(non_template_files))
        files_hash = hashlib.sha256(files_str.encode(errors="surrogatepass")).hexdigest()

        return (content_hash, files_hash)

    except GitCommandError as e:
        logger.debug("Failed to get signature for %s: %s", commit_id, e)
        return None
