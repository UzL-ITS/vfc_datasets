from typing import Any

import pandas as pd

from dataset_entry import DatasetEntry
from vfc_datasets.base_dataset import BaseDataset, DatasetMetadata
from vfc_datasets.download_helper import load_or_download_csv
from vfc_datasets.parsing_helpers import (
    extract_url_and_commit,
    normalize_cve_ids,
    normalize_cwe_ids,
)


class BigVulDataset(BaseDataset):
    metadata = DatasetMetadata(
        name="bigvul",
        granularity="commit",
        paper_title="A C/C++ Code Vulnerability Dataset with Code Changes and CVE Summaries",
        paper_url="https://doi.org/10.1145/3379597.3387501",
        download_url="https://github.com/ZeoVan/MSR_20_Code_vulnerability_CSV_Dataset",
        publication_year=2020,
        programming_languages=("C", "C++"),
        paper_quotes=(
            # Page 1 (Abstract)
            "In total, Big-Vul contains 3,754 code vulnerabilities spanning 91 different vulnerability "
            "types. All these code vulnerabilities are extracted from 348 Github projects.",
            # Page 2 (Section 3 - Data Description)
            "Our Big-Vul dataset covers 348 different projects that are linked to 4,432 unique code "
            "commits. The 4,432 code commits contain the code fixes for 3,754 vulnerabilities in 91 CWE types.",
            # Page 3 (Table 2 - Descriptive statistics)
            # Number of Commits: 4432, Vulnerable Functions: 11823, Non-vulnerable Functions: 253096
        ),
        vfcs=4432,
        projects=348,
        vulnerable_functions=11823,
        benign_functions=253096,
    )

    def _load_data(self) -> pd.DataFrame:
        return load_or_download_csv(
            output_path=str(self._raw_dir / "bigvul.csv"),
            url="https://raw.githubusercontent.com/ZeoVan/MSR_20_Code_Vulnerability_CSV_Dataset/master/all_c_cpp_release2.0.csv",
        )

    def _parse_row(self, row: dict[str, Any]) -> DatasetEntry | None:
        project_url, commit_id = extract_url_and_commit(
            row, "ref_link", "commit_id", self.metadata.name
        )
        if not project_url or not commit_id:
            return None

        return DatasetEntry(
            project_url=project_url,
            commit_id=commit_id,
            src_datasets={self.metadata.name},
            is_vfc=True,
            cve_ids=normalize_cve_ids(row.get("cve_id")),
            cwe_ids=normalize_cwe_ids(row.get("cwe_id")),
        )
