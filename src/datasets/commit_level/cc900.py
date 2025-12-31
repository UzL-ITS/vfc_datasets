from typing import Any

import pandas as pd

from dataset_entry import DatasetEntry
from datasets.base_dataset import BaseDataset, DatasetMetadata
from datasets.download_helper import load_or_download_csv
from datasets.parsing_helpers import (
    extract_from_commit_url,
    extract_url_and_commit,
    normalize_cve_ids,
    normalize_cwe_ids,
    normalize_or_resolve_commit,
)


class CC900Dataset(BaseDataset):
    metadata = DatasetMetadata(
        name="cc900",
        granularity="commit",
        paper_title="Co-training for Commit Classification",
        paper_url="https://doi.org/10.18653/v1/2021.wnut-1.43",
        download_url="https://github.com/davidleejy/wnut21-cotrain/tree/main",
        publication_year=2021,
        paper_quotes=(
            # Page 3 (Section 3 - The 900Repo Dataset)
            "We extracted all 3,765 positive samples belonging to these 910 overlapping repositories "
            "and randomly sampled twice as many negative samples from the same 910 repositories, "
            "giving a total of 10,000 commits.",
            # Page 3 (Section 3)
            "The result is a dataset with 3,765 positive samples and roughly 6,300 negative samples "
            "that we refer to as 900Repo.",
        ),
        vfcs=3765,
        non_vfcs=6300,
        projects=910,
    )

    def _load_data(self) -> pd.DataFrame:
        raw_dataset_dir = self._raw_dir / "cc900"

        # Load positive (vulnerability fixing commits)
        df_positive = load_or_download_csv(
            output_path=raw_dataset_dir / "positive.csv",
            url="https://media.githubusercontent.com/media/davidleejy/wnut21-cotrain/main/positive%2BCC-900repos.csv",
        )
        df_positive["dataset_type"] = "positive"

        # Load negative (non-vulnerability commits)
        df_negative = load_or_download_csv(
            output_path=raw_dataset_dir / "negative.csv",
            url="https://media.githubusercontent.com/media/davidleejy/wnut21-cotrain/main/negative%2BCC-900repos.csv",
        )
        df_negative["dataset_type"] = "negative"

        # Combine both dataframes
        return pd.concat([df_positive, df_negative], ignore_index=True)

    def _parse_row(self, row: dict[str, Any]) -> DatasetEntry | None:
        dataset_type = row.get("dataset_type")
        is_vfc = dataset_type == "positive"

        if is_vfc:
            project_url, commit_id = extract_url_and_commit(
                row, "project", "sha", self.metadata.name
            )
            if not project_url or not commit_id:
                return None
        else:
            project_url, raw_commit_id = extract_from_commit_url(
                row, "github", self.metadata.name
            )
            if not project_url or not raw_commit_id:
                return None
            commit_id = normalize_or_resolve_commit(raw_commit_id, project_url)
            if not commit_id:
                return None

        return DatasetEntry(
            project_url=project_url,
            commit_id=commit_id,
            src_datasets={self.metadata.name},
            is_vfc=is_vfc,
            cve_ids=normalize_cve_ids(row.get("cve_id")),
            cwe_ids=normalize_cwe_ids(row.get("cwe_id")),
        )
