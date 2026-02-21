import logging
from typing import Any

import pandas as pd

from dataset_entry import DatasetEntry
from vfc_datasets.base_dataset import BaseDataset, DatasetMetadata
from vfc_datasets.download_helper import load_or_download_csv
from vfc_datasets.parsing_helpers import normalize_cve_ids, normalize_or_resolve_commit

logger = logging.getLogger(__name__)


class MSR2019Dataset(BaseDataset):
    metadata = DatasetMetadata(
        name="msr2019",
        granularity="commit",
        paper_title="A Manually-Curated Dataset of Fixes to Vulnerabilities of Open-Source Software",
        paper_url="https://doi.org/10.1109/MSR.2019.00064",
        download_url="https://github.com/SAP/project-kb/tree/main/MSR2019",
        publication_year=2019,
        programming_languages=("Java",),
        paper_quotes=(
            # Page 1 (Introduction)
            "Our dataset maps 624 publicly disclosed vulnerabilities affecting 205 distinct open-source "
            "Java projects used in SAP software (either products or internal tools) onto the 1282 commits "
            "that fix them.",
            # Page 2 (Section III - Dataset Description)
            # 205 projects | 1282 commits | 624 vulnerabilities | 29 without CVE | 46 not in NVD
        ),
        vfcs=1282,
        projects=205,
    )

    def _load_data(self) -> pd.DataFrame:
        return load_or_download_csv(
            output_path=self._raw_dir / "msr2019.csv",
            url="https://raw.githubusercontent.com/SAP/project-kb/main/MSR2019/dataset/vulas_db_msr2019_release.csv",
            names=["cve_id", "project_url", "commit_id", "pos"],
        )

    def _parse_row(self, row: dict[str, Any]) -> DatasetEntry | None:
        raw_commit_id = row.get("commit_id")
        project_url = row.get("project_url")

        if not project_url or not raw_commit_id:
            logger.debug(
                "[%s] Skipping row: missing project_url=%s or commit_id=%s",
                self.metadata.name,
                project_url,
                raw_commit_id,
            )
            return None

        commit_id = normalize_or_resolve_commit(raw_commit_id, project_url)
        if not commit_id:
            return None

        return DatasetEntry(
            project_url=project_url,
            commit_id=commit_id,
            src_datasets={self.metadata.name},
            is_vfc=True,  # All entries are 'pos' so.. is_vfc = True
            cve_ids=normalize_cve_ids(row.get("cve_id")),
        )
