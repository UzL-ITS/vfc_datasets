import logging
import os
from typing import Any, override

import pandas as pd
import psycopg2
from tqdm.auto import tqdm

from vfc_datasets.base_dataset import BaseDataset, DatasetMetadata
from vfc_datasets.dataset_entry import DatasetEntry
from vfc_datasets.parsing_helpers import (
    normalize_cve_ids,
    normalize_cwe_ids,
    normalize_or_resolve_commit,
)
from vfc_datasets.utils.git.url import GitURL

logger = logging.getLogger(__name__)


class MorefixesDataset(BaseDataset):
    min_prospector_score: int = 65

    metadata = DatasetMetadata(
        name="morefixes",
        granularity="commit",
        paper_title="MoreFixes: A Large-Scale Dataset of CVE Fix Commits Mined through Enhanced Repository Discovery",
        paper_url="https://doi.org/10.1145/3663533.3664036",
        source_url="https://github.com/JafarAkhondali/Morefixes",
        publication_year=2024,
        paper_quotes=(
            # Page 1 (Abstract)
            "Our dataset containing 26,617 unique CVEs coming from 6,945 unique GitHub projects is, "
            "to the best of our knowledge, by far the biggest CVE vulnerability dataset with fix commits "
            "available today. These CVEs are associated with 31,883 unique commits that fixed those "
            "vulnerabilities.",
            # Table 5: MoreFixes | 26,617 CVEs | 6,945 Projects | 31,883 Commits | CVE Years 1999-2024
        ),
        vfcs=35130,  # NOTE: Zenodo reports 35,276
        non_vfcs=0,
        projects=6945,
    )

    @override
    def _load_data(self) -> pd.DataFrame:
        """
        Extract VFC data from MoreFixes PostgreSQL dump.

        Requires a local PostgreSQL instance with the MoreFixes dump imported.
        See: https://github.com/JafarAkhondali/Morefixes
        """
        # Default credentials from the public MoreFixes DB dump
        connection_params: dict[str, Any] = {
            "dbname": "postgrescvedumper",
            "user": "postgrescvedumper",
            "password": "a42a18537d74c3b7e584c769152c3d",
            "host": os.getenv("MOREFIXES_DB_HOST", "localhost"),
            "port": int(os.getenv("MOREFIXES_DB_PORT", "5432")),
        }
        try:
            connection = psycopg2.connect(**connection_params)
        except psycopg2.OperationalError as e:
            raise ConnectionError(
                f"Failed to connect to MoreFixes database. "
                f"Please check your database configuration in .env or environment variables. "
                f"Connection parameters: {connection_params}"
            ) from e

        query_from = f"""
            FROM public.commits c
            JOIN public.fixes f ON c.hash = f.hash
            LEFT JOIN public.cwe_classification cw ON f.cve_id = cw.cve_id
            WHERE score >= {self.min_prospector_score}
        """

        try:
            with connection:
                with connection.cursor() as count_cur:
                    count_cur.execute("SELECT COUNT(*) " + query_from)
                    row = count_cur.fetchone()
                    total_rows = row[0] if row else 0

                # Server-side cursor for memory efficiency
                with connection.cursor(name="morefixes_cursor") as cur:
                    cur.itersize = 1000
                    cur.execute("SELECT c.hash, f.repo_url, f.cve_id, cw.cwe_id " + query_from)

                    vfcs = []
                    for commit_id, repo_url, cve_id, cwe_id in tqdm(
                        cur,
                        total=total_rows,
                        desc="Parsing MOREFIXES",
                        dynamic_ncols=True,
                    ):
                        vfcs.append(
                            {
                                "commit_id": commit_id,
                                "project_url": repo_url,
                                "cve_id": cve_id,
                                "cwe_id": cwe_id,
                            }
                        )

                df = pd.DataFrame(vfcs)
        except psycopg2.Error as e:
            raise RuntimeError(
                f"Database query failed for MOREFIXES dataset. "
                f"This may indicate an issue with the database schema or permissions. "
                f"Error: {e}"
            ) from e
        finally:
            connection.close()

        if df.empty:
            raise ValueError(f"Failed to extract data from {self.metadata.name} dump")

        df = df.drop_duplicates(subset="commit_id")

        return df

    @override
    def _parse_row(self, row: dict[str, Any]) -> DatasetEntry | None:
        raw_cve_id = row.get("cve_id")
        cve_ids = normalize_cve_ids(raw_cve_id)

        raw_cwe_id = row.get("cwe_id")
        cwe_ids = normalize_cwe_ids(raw_cwe_id)

        project_url = row.get("project_url")
        if not project_url:
            logger.debug("[%s] Skipping row: missing project_url", self.metadata.name)
            return None

        git_url = GitURL.parse(project_url)
        raw_commit_id = git_url.commit_id if git_url else None
        project_url = git_url.to_https_url() if git_url else None

        # Fall back to commit_id field
        if not raw_commit_id:
            raw_commit_id = row.get("commit_id")

        if not project_url or not raw_commit_id:
            logger.debug(
                "[%s] Skipping row: missing project_url=%s or commit_id=%s",
                self.metadata.name,
                project_url,
                raw_commit_id,
            )
            return None

        # Some commit IDs have a trailing 'C' appended
        if raw_commit_id.endswith("C") and len(raw_commit_id) == 41:
            logger.warning(
                "Correcting commit_id ending with 'C': %s -> %s",
                raw_commit_id,
                raw_commit_id[:-1],
            )
            raw_commit_id = raw_commit_id[:-1]

        commit_id = normalize_or_resolve_commit(raw_commit_id, project_url)
        if not commit_id:
            return None

        return DatasetEntry(
            project_url=project_url,
            commit_id=commit_id,
            src_datasets={self.metadata.name},
            is_vfc=True,
            cve_ids=cve_ids,
            cwe_ids=cwe_ids,
        )
