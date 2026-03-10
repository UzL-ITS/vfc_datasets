import gzip
import logging
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

import pandas as pd
from tqdm.auto import tqdm

from dataset_entry import DatasetEntry
from vfc_datasets.base_dataset import BaseDataset, DatasetMetadata
from vfc_datasets.download_helper import download_and_extract_zip
from vfc_datasets.parsing_helpers import (
    extract_url_and_commit,
    normalize_cve_ids,
    normalize_cwe_ids,
)

logger = logging.getLogger(__name__)


class CVEFixesDataset(BaseDataset):
    VERSION = "CVEfixes_v1.0.8"
    ZENODO_RECORD_ID = "13118970"

    metadata = DatasetMetadata(
        name="cvefixes",
        granularity="commit",
        paper_title="CVEfixes: Automated Collection of Vulnerabilities and Their Fixes from Open-Source Software",
        paper_url="https://doi.org/10.1145/3475960.3475985",
        source_url="https://doi.org/10.5281/zenodo.4476563",
        publication_year=2021,
        paper_quotes=(
            # PROMISE 2021 Paper - Page 1 (Abstract)
            "The initial release of CVEfixes spans all published CVEs up to 9 June 2021, "
            "covering 5365 CVE records for 1754 open-source projects that were addressed "
            "in a total of 5495 vulnerability fixing commits.",
            # Page 6 (Section 4 - Dataset Exploration)
            "This initial release covers 5365 unique CVEs in 1754 OSS projects, with 5495 "
            "unique vulnerability fixing commits. The CVEs are classified into 180 different "
            "CWE vulnerability types.",
            # Page 6 (Table 1 - Summary statistics)
            # CVEs: 5,365 | CWEs: 180 | projects: 1,754 | commits: 5,495 | files: 18,249 | methods: 50,322
        ),
        # NOTE: vfcs and projects reflect the Zenodo v1.0.8 dataset content without deduplication.
        vfcs=13297,
        non_vfcs=0,
        projects=4249,
    )

    def _get_database(self) -> Path:
        sql_file_path = self._raw_dir / "cvefixes.db"

        if not sql_file_path.exists():
            cve_fixes_url = f"https://zenodo.org/records/{self.ZENODO_RECORD_ID}/files/{self.VERSION}.zip?download=1"

            with tempfile.TemporaryDirectory() as tmp_folder:
                download_and_extract_zip(url=cve_fixes_url, extract_path=tmp_folder)
                db_gz_path = Path(tmp_folder) / self.VERSION / "Data" / f"{self.VERSION}.sql.gz"

                # Stream SQL from gzip directly to SQLite
                compressed_size = db_gz_path.stat().st_size
                with (
                    sqlite3.connect(sql_file_path) as conn,
                    open(db_gz_path, "rb") as raw_file,
                    gzip.open(raw_file, "rt", encoding="utf-8") as gz_file,
                ):
                    cursor = conn.cursor()
                    statement = []
                    last_pos = 0
                    try:
                        with tqdm(
                            total=compressed_size,
                            desc="Importing CVEFixes SQL",
                            unit="B",
                            unit_scale=True,
                            unit_divisor=1024,
                        ) as pbar:
                            for line in gz_file:
                                statement.append(line)
                                if line.strip().endswith(";"):
                                    cursor.execute("".join(statement))
                                    statement = []
                                # Update progress based on compressed file position
                                current_pos = raw_file.tell()
                                pbar.update(current_pos - last_pos)
                                last_pos = current_pos
                        conn.commit()
                    except sqlite3.Error as e:
                        logger.exception(
                            "Failed to execute CVEfixes SQL script: %s. "
                            "The database file may be corrupted. "
                            "Try deleting %s and re-running.",
                            e,
                            sql_file_path,
                        )
                        raise

        return sql_file_path

    def _load_data(self) -> pd.DataFrame:
        sql_file_path = self._get_database()

        query = """
        SELECT fixes.cve_id, fixes.hash as commit_id, fixes.repo_url,
               cwe_classification.cwe_id
        FROM fixes
        JOIN cwe_classification ON fixes.cve_id = cwe_classification.cve_id
        """

        with sqlite3.connect(sql_file_path) as conn:
            return pd.read_sql_query(query, conn)

    def _parse_row(self, row: dict[str, Any]) -> DatasetEntry | None:
        # Extract and validate project URL and commit ID
        project_url, commit_id = extract_url_and_commit(
            row, "repo_url", "commit_id", self.metadata.name
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
