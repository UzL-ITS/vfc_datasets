import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any, NamedTuple
from urllib.parse import quote

import pandas as pd
from tqdm.auto import tqdm

from config import GITHUB_API_URL
from dataset_entry import DatasetEntry
from utils.git.github_client import AsyncGitHubClient
from utils.git.url import GitURL, normalize_commit_id
from vfc_datasets.base_dataset import BaseDataset, DatasetMetadata
from vfc_datasets.download_helper import download_file
from vfc_datasets.parsing_helpers import normalize_cve_ids

logger = logging.getLogger(__name__)


class _CommitInfo(NamedTuple):
    commit_id: str
    author_email: str | None
    author_username: str | None
    subject: str | None


def _extract_commit_info(dataset_commit_content: str) -> _CommitInfo | None:
    if not dataset_commit_content:
        return None

    first_line, *rest = dataset_commit_content.splitlines()
    m = re.match(r"^From\s+([0-9a-f]{5,40})\s+", first_line.strip(), re.IGNORECASE)
    if not m:
        return None

    commit_id = normalize_commit_id(m.group(1))
    if not commit_id:
        return None

    author_email: str | None = None
    author_username: str | None = None
    subject: str | None = None

    if rest:
        limited = "\n".join(rest[:512])
        if email_match := re.search(r"^From:\s+[\s\S]*?<([^>]+)>", limited, re.M):
            author_email = email_match.group(1).strip()
        # Extract username when From line has single word before < (e.g., "From: vivainio <...>")
        if username_match := re.search(r"^From:\s+(\w+)\s+<", limited, re.M):
            author_username = username_match.group(1)
        if subject_match := re.search(r"^Subject:\s+(.*)$", limited, re.M):
            subject = re.sub(r"^(?:\s*\[[^\]]+]\s*)+", "", subject_match.group(1).strip()).strip()

    return _CommitInfo(
        commit_id=commit_id,
        author_email=author_email,
        author_username=author_username,
        subject=subject or None,
    )


def _decode_mime_header(value: str) -> str:
    """Decode RFC 2047 MIME-encoded header (e.g., =?utf-8?q?...?=)."""
    from email.header import decode_header

    if "=?" not in value:
        return value
    try:
        parts = decode_header(value)
        decoded = []
        for data, charset in parts:
            if isinstance(data, bytes):
                decoded.append(data.decode(charset or "utf-8", errors="replace"))
            else:
                decoded.append(data)
        return "".join(decoded)
    except Exception:
        return value


def _normalize_subject(subject: str) -> str:
    # Decode MIME-encoded headers (e.g., =?utf-8?q?...?=)
    decoded = _decode_mime_header(subject)
    # Strip [prefix] tags (e.g., "[sos_collector] Fix bug" -> "Fix bug")
    stripped = re.sub(r"^(?:\s*\[[^\]]+]\s*)+", "", decoded.strip())
    # Remove emojis and other non-ASCII (encoding differences cause mismatches)
    ascii_only = stripped.encode("ascii", errors="ignore").decode("ascii")
    return re.sub(r"\s+", " ", ascii_only.lower()).strip()


def _extract_repo_url(item: dict[str, Any]) -> str | None:
    repo = item.get("repository")
    if isinstance(repo, dict):
        url = repo.get("html_url")
        if isinstance(url, str) and url:
            return url
    return None


def _repo_url_from_search_result(
    response: dict[str, Any] | None,
    *,
    commit_id: str,
    subject: str | None,
) -> str | None:
    if not isinstance(response, dict):
        return None
    items = response.get("items")
    if not isinstance(items, list) or not items:
        return None

    commit_id_lower = commit_id.lower()
    candidates = [
        item
        for item in items
        if isinstance(item, dict) and str(item.get("sha", "")).lower().startswith(commit_id_lower)
    ]
    if not candidates:
        return None

    # Verify commit message matches the subject from dataset
    subject_norm = _normalize_subject(subject) if subject else None
    verified = []
    for item in candidates:
        commit = item.get("commit")
        message = commit.get("message") if isinstance(commit, dict) else None
        if not isinstance(message, str) or not message:
            continue
        first_line = message.splitlines()[0].strip()
        # Accept if subject matches
        first_line_norm = _normalize_subject(first_line)
        if (
            not subject_norm
            or first_line_norm.startswith(subject_norm)
            or subject_norm.startswith(first_line_norm)
        ):
            verified.append(item)

    if not verified:
        return None

    # Among verified, prefer non-fork repos
    non_forks = [
        item
        for item in verified
        if isinstance(item.get("repository"), dict) and not item["repository"].get("fork", False)
    ]

    return _extract_repo_url(non_forks[0] if non_forks else verified[0])


async def _resolve_project_urls(
    metas: list[_CommitInfo],
    *,
    repo_map: dict[str, str],
) -> dict[str, str]:
    async with AsyncGitHubClient() as client:

        async def _resolve_one(meta: _CommitInfo) -> tuple[str, str | None]:
            query_parts = [f"hash:{meta.commit_id}"]
            if meta.author_email:
                query_parts.append(f"author-email:{quote(meta.author_email)}")
            elif meta.author_username:
                query_parts.append(f"author:{meta.author_username}")
            api_url = f"{GITHUB_API_URL}/search/commits?q={'+'.join(query_parts)}"

            response = await client.query_api(api_url)
            repo_url = _repo_url_from_search_result(
                response,
                commit_id=meta.commit_id,
                subject=meta.subject,
            )
            if repo_url:
                git_url = GitURL.parse(repo_url)
                if git_url and git_url.owner and git_url.repo:
                    https_url = git_url.to_https_url()
                    if https_url:
                        return meta.commit_id, https_url

            return meta.commit_id, None

        tasks = [asyncio.create_task(_resolve_one(meta)) for meta in metas]
        for completed_fut in tqdm(
            asyncio.as_completed(tasks),
            total=len(tasks),
            desc="Resolving PYSECDB project URLs",
            unit=" commits",
            dynamic_ncols=True,
        ):
            commit_id, project_url = await completed_fut
            # Store empty string for failed lookups
            repo_map[commit_id] = project_url or ""

    return repo_map


def _index_commits_by_id(records: list[dict[str, Any]]) -> dict[str, _CommitInfo]:
    result: dict[str, _CommitInfo] = {}
    for row in records:
        meta = _extract_commit_info(str(row.get("content") or ""))
        if not meta:
            continue

        existing = result.get(meta.commit_id)
        if existing is None:
            result[meta.commit_id] = meta
            continue

        result[meta.commit_id] = _CommitInfo(
            commit_id=meta.commit_id,
            author_email=existing.author_email or meta.author_email,
            author_username=existing.author_username or meta.author_username,
            subject=existing.subject or meta.subject,
        )

    return result


class PySecDBDataset(BaseDataset):
    metadata = DatasetMetadata(
        name="pysecdb",
        granularity="commit",
        paper_title="Exploring Security Commits in Python",
        paper_url="https://doi.org/10.48550/arXiv.2307.11853",
        source_url="https://huggingface.co/datasets/sunlab/PySecDB",
        publication_year=2023,
        programming_languages=("Python",),
        paper_quotes=(
            # ICSME 2023 Paper - Page 1 (Abstract)
            "After manual verification by three security experts, PySecDB consists of 1,258 security "
            "commits and 2,791 non-security commits.",
            # Page 3 (Section II-D - Novelty)
            "We build the first security commit dataset in Python, which contains 1,258 security commits "
            "and 2,791 non-security commits extracted from over 351 popular GitHub projects, "
            "covering 119 more CWEs.",
            # Page 6 (Table II): Base 729 + Pilot 400 + Augmented 129 = 1,258 security commits
        ),
        vfcs=1142,  # 1258 NOTE: not all available yet
        non_vfcs=2721,  # 2791, NOTE: not all available yet
        projects=351,
    )

    def __init__(self) -> None:
        super().__init__()
        self._repo_map: dict[str, str] | None = None

    @staticmethod
    def _load_records(raw_dir: Path) -> list[dict[str, Any]]:
        pysecdb_dump = raw_dir / "pysecdb.json"
        if not pysecdb_dump.exists():
            download_file(
                url="https://huggingface.co/datasets/sunlab/PySecDB/resolve/main/pysecdb.json",
                output_path=pysecdb_dump,
                checksum="79027471e5863d11032c27d2862800862dba53ad5173ff7aa878cd556902d7b9",
            )
        records = json.loads(pysecdb_dump.read_text(encoding="utf-8"))
        if not isinstance(records, list):
            raise ValueError(f"[pysecdb] Unexpected pysecdb.json format: {type(records).__name__}")
        return [r for r in records if isinstance(r, dict)]

    @staticmethod
    def _load_repo_map(repo_map_path: Path) -> dict[str, str]:
        if not repo_map_path.exists():
            return {}
        try:
            loaded = json.loads(repo_map_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            logger.warning("[pysecdb] Invalid JSON in %s; rebuilding.", repo_map_path)
            return {}
        if not isinstance(loaded, dict):
            return {}
        return {str(k): str(v) for k, v in loaded.items() if k}

    def _load_data(self) -> pd.DataFrame:
        raw_dataset_dir = self._raw_dir / "pysecdb"
        raw_dataset_dir.mkdir(parents=True, exist_ok=True)

        records = self._load_records(raw_dataset_dir)

        repo_map_path = raw_dataset_dir / "pysecdb_repo_map.json"
        repo_map = self._load_repo_map(repo_map_path)

        commits_by_id = _index_commits_by_id(records)
        unresolved = [meta for meta in commits_by_id.values() if meta.commit_id not in repo_map]
        if unresolved:
            logger.info(
                "[%s] Resolving %d/%d commit repository URLs (cache hit: %d)",
                self.metadata.name,
                len(unresolved),
                len(commits_by_id),
                len(repo_map),
            )
            repo_map = asyncio.run(_resolve_project_urls(unresolved, repo_map=repo_map))
            repo_map_path.write_text(json.dumps(repo_map, sort_keys=True), encoding="utf-8")

        self._repo_map = repo_map
        return pd.DataFrame.from_records(records)

    def _parse_row(self, row: dict[str, Any]) -> DatasetEntry | None:
        if not self._repo_map:
            return None

        content = row.get("content")
        if not isinstance(content, str) or not content:
            return None

        meta = _extract_commit_info(content)
        if not meta:
            return None

        project_url = self._repo_map.get(meta.commit_id)
        if not project_url:
            return None

        return DatasetEntry(
            project_url=project_url,
            commit_id=meta.commit_id,
            src_datasets={self.metadata.name},
            is_vfc=row.get("label") == "security",
            cve_ids=normalize_cve_ids(row.get("CVE-ID")),
        )
