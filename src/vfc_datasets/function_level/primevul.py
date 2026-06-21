import json
import logging
from pathlib import Path
from typing import Any, override

import pandas as pd

from vfc_datasets.base_dataset import BaseDataset, DatasetMetadata
from vfc_datasets.dataset_entry import DatasetEntry
from vfc_datasets.download_helper import download_file
from vfc_datasets.parsing_helpers import (
    normalize_commit_id,
    normalize_cve_ids,
    normalize_cwe_ids,
)
from vfc_datasets.transformations.enrichment.project_urls.url_mappings import get_moved_urls
from vfc_datasets.utils.git.url import GitURL

logger = logging.getLogger(__name__)


class PrimeVulDataset(BaseDataset):
    metadata = DatasetMetadata(
        name="primevul",
        granularity="function",
        paper_title="Vulnerability Detection with Code Language Models: How Far Are We?",
        paper_url="https://doi.org/10.48550/arXiv.2403.18624",
        source_url="https://github.com/DLVulDet/PrimeVul",
        publication_year=2024,
        programming_languages=("C", "C++"),
        paper_quotes=(
            # Section III-B (Table III context)
            "Our pipeline results in a collection of 6,968 vulnerable and 228,800 benign functions "
            "across 755 projects and 6,827 commits.",
        ),
        # NOTE: Currently used version (v0.1 from GDrive) has 224,533 total functions.
        vfcs=5657,
        non_vfcs=0,
        projects=755,
        vulnerable_functions=6003,
        benign_functions=218474,
    )

    # Special project name mappings for entries missing proper URLs
    PROJECT_URLS = {
        "binaryen": "https://github.com/WebAssembly/binaryen",
        "mjg59_linux": "https://github.com/torvalds/linux",
        "qemu_qemu": "https://github.com/qemu/qemu",
    }

    def _download_if_missing(self) -> Path:
        primevul_path = self._raw_dir / "primevul"
        primevul_path.mkdir(parents=True, exist_ok=True)

        # Skip if already downloaded
        if any(primevul_path.glob("*.jsonl")):
            return primevul_path

        gdrive_files = {
            "primevul_train.jsonl": "12b1QkCwW0SC6l9KvxSmMe4jHF7VhjwCa",
            "primevul_valid.jsonl": "1490USYtUtb5n3i3m3n2LaSfjTCiKhPoO",
            "primevul_test.jsonl": "1ABV5cIdtyNAzKlGxjW_BsFZOp9MFd-AH",
        }
        for filename, file_id in gdrive_files.items():
            jsonl_path = primevul_path / filename
            if not jsonl_path.exists():
                download_file(f"https://drive.google.com/uc?id={file_id}", jsonl_path)

        return primevul_path

    @override
    def _load_data(self) -> pd.DataFrame:
        primevul_path = self._download_if_missing()

        jsonl_files = sorted(primevul_path.glob("*.jsonl"))
        if not jsonl_files:
            raise FileNotFoundError(f"No .jsonl files found in {primevul_path}")

        # Read with stdlib json to handle arbitrarily large integers
        records: list[dict[str, Any]] = []
        for fp in jsonl_files:
            with open(fp, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    row = json.loads(line)
                    row["resolved_project_url"] = self._resolve_project_url(row)
                    records.append(row)

        return pd.DataFrame(records)

    def _resolve_project_url(self, row: dict[str, Any]) -> str | None:
        project_url = self._normalize_candidate_url(row.get("project_url"))
        if project_url:
            return project_url

        commit_url = self._normalize_candidate_url(row.get("commit_url"))
        if commit_url:
            return commit_url

        project = row.get("project")
        if project and project in self.PROJECT_URLS:
            mapped_project: str | None = self._normalize_candidate_url(self.PROJECT_URLS[project])
            if mapped_project:
                return mapped_project

        return None

    def _normalize_candidate_url(self, raw_url: Any) -> str | None:
        if not isinstance(raw_url, str):
            return None

        candidate = raw_url.strip()
        if not candidate or candidate.lower() == "none":
            return None

        moved_urls = get_moved_urls()
        mapped_candidate = moved_urls.get(candidate, candidate)

        git_url = GitURL.parse(mapped_candidate)
        if not git_url:
            logger.debug("[primevul] Unable to parse project URL candidate: %s", candidate)
            return None

        normalized = git_url.to_https_url()
        if not normalized:
            logger.debug(
                "[primevul] Failed to normalize project URL candidate: %s", mapped_candidate
            )
            return None

        mapped_normalized = moved_urls.get(normalized, normalized)
        if mapped_normalized != normalized:
            git_url = GitURL.parse(mapped_normalized)
            normalized = (git_url.to_https_url() or normalized) if git_url else mapped_normalized

        return normalized

    @override
    def _parse_row(self, row: dict[str, Any]) -> DatasetEntry | None:
        project_url = row.get("project_url")
        if project_url == "None" or not project_url:
            project_url = row.get("resolved_project_url")

        commit_id = normalize_commit_id(row.get("commit_id"))

        # TODO: get function name from func (function code)
        # WORKAROUND: use func_hash as function name
        function_name = row.get("func_hash")
        if not function_name:
            logger.debug(
                "[%s] Skipping row: missing func_hash for project=%s, commit=%s",
                self.metadata.name,
                project_url,
                commit_id,
            )
            return None

        if commit_id and project_url:
            return DatasetEntry(
                function_name=function_name,
                project_url=project_url,
                commit_id=commit_id,
                src_datasets={self.metadata.name},
                is_vfc=row.get("target") == 1,
                cve_ids=normalize_cve_ids(row.get("cve")),
                cwe_ids=normalize_cwe_ids(row.get("cwe")),
            )
        logger.debug(
            "[%s] Skipping row: missing commit_id=%s or project_url=%s",
            self.metadata.name,
            commit_id,
            project_url,
        )
        return None
