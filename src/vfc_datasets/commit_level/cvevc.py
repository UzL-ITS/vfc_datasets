from collections import defaultdict
from typing import Any, override

import pandas as pd

from vfc_datasets.base_dataset import BaseDataset, DatasetCounts, DatasetMetadata
from vfc_datasets.config import RAW_DATA_PATH
from vfc_datasets.dataset_entry import DatasetEntry
from vfc_datasets.download_helper import download_file
from vfc_datasets.parsing_helpers import extract_url_and_commit, normalize_cve_ids

_HF_URL = "https://huggingface.co/datasets/andstor"
_COMMITS_REVISION = "a6ac86fcdff6042545e1bd88976aa577074a1aa0"
_PATCH_SHARDS = {"train": 13, "validation": 2, "test": 2}
_CVE_REVISION = "21feb647ed4f182a2ffc52694bb566a2a349ad16"
_CVE_SPLITS = {
    "train": "61034fe96a5d957c3fa959252ed85cfffc9391930e464dddda833422106d8184",
    "validation": "4d5381d42de9558deea67a90e14f9631834e674dada643db497fd6ea8b8735fb",
    "test": "8db855717b7ffc109c2877a57bb0b4dd574302c631ec58e3ece2b1eea02da99e",
}


class CVEVCDataset(BaseDataset):
    metadata = DatasetMetadata(
        name="cvevc",
        granularity="commit",
        paper_title="Favia: Forensic Agent for Vulnerability-fix Identification and Analysis",
        paper_url="https://doi.org/10.48550/arXiv.2602.12500",
        source_url="https://huggingface.co/datasets/andstor/cvevc_commits",
        publication_year=2026,
        paper_quotes=(
            # Abstract
            "We evaluate Favia on CVEVC, a large-scale dataset we made that comprises over "
            "8 million commits from 3,708 real-world repositories",
            # Section 5.2.3 (Datasets)
            "We get all patch commits, and select up to 5,000 non-patch commits at random.",
        ),
    )

    parsed_counts = DatasetCounts(
        vfcs=14526,
        non_vfcs=0,
        projects=3536,
    )

    @override
    def _load_data(self) -> pd.DataFrame:
        raw_dir = RAW_DATA_PATH / "cvevc"

        cves_by_commit: defaultdict[str, set[str]] = defaultdict(set)
        for split, checksum in _CVE_SPLITS.items():
            path = download_file(
                f"{_HF_URL}/cvevc_cve/resolve/{_CVE_REVISION}/data/{split}-00000-of-00001.parquet",
                raw_dir / "cve" / f"{split}.parquet",
                checksum=checksum,
            )
            cves = pd.read_parquet(path, columns=["cve", "commits"])
            for cve, commits in zip(cves["cve"], cves["commits"], strict=True):
                for commit_id in commits:
                    cves_by_commit[commit_id].add(cve)

        frames: list[pd.DataFrame] = []
        for split, shards in _PATCH_SHARDS.items():
            for shard in range(shards):
                name = f"{split}-{shard:05d}-of-{shards:05d}.parquet"
                path = download_file(
                    f"{_HF_URL}/cvevc_commits/resolve/{_COMMITS_REVISION}/patches/{name}",
                    raw_dir / "patches" / name,
                )
                frames.append(pd.read_parquet(path, columns=["commit_id", "repo", "label"]))

        df = pd.concat(frames, ignore_index=True)
        df["repo_url"] = "https://github.com/" + df["repo"]
        df["cve_ids"] = [sorted(cves_by_commit.get(c, ())) for c in df["commit_id"]]
        return df

    @override
    def _parse_row(self, row: dict[str, Any]) -> DatasetEntry | None:
        project_url, commit_id = extract_url_and_commit(
            row, "repo_url", "commit_id", self.metadata.name
        )
        if not project_url or not commit_id:
            return None

        return DatasetEntry(
            project_url=project_url,
            commit_id=commit_id,
            src_datasets={self.metadata.name},
            is_vfc=bool(row.get("label")),
            cve_ids=normalize_cve_ids(row.get("cve_ids")),
        )
