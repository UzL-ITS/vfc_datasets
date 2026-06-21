import logging
from pathlib import Path
from typing import Any, cast, override

import pandas as pd
from git import Repo
from git.exc import BadName, GitCommandError
from tqdm.auto import tqdm

from vfc_datasets.base_dataset import BaseDataset, DatasetMetadata
from vfc_datasets.dataset_entry import DatasetEntry
from vfc_datasets.download_helper import download_file
from vfc_datasets.parsing_helpers import normalize_commit_id
from vfc_datasets.utils.git.commit import get_commit_diff
from vfc_datasets.utils.git.repository import clone_repository
from vfc_datasets.utils.git.url import GitURL

logger = logging.getLogger(__name__)


def _normalize_diff_for_comparison(diff: str) -> str:
    """Normalize diff for comparison by removing volatile elements."""
    lines = []
    for line in diff.replace("\r\n", "\n").split("\n"):
        # Skip index lines (contain blob hashes that vary)
        if line.startswith("index "):
            continue
        lines.append(line)
    return "\n".join(lines).rstrip("\n")


class SPIDBDataset(BaseDataset):
    metadata = DatasetMetadata(
        name="spidb",
        granularity="commit",
        paper_title="SPI: Automated Identification of Security Patches via Commits",
        paper_url="https://doi.org/10.1145/3468854",
        source_url="https://sites.google.com/view/du-commits/home",
        publication_year=2021,
        programming_languages=("C", "C++"),
        paper_quotes=(
            # TOSEM 2021 Paper - Page 1 (Abstract)
            "First, we design and build security patch datasets that include 38,291 security-related "
            "commits and 1,045 Common Vulnerabilities and Exposures (CVE) patches from four "
            "large-scale C programming language libraries.",
            # Page 9 (Section 4.3 - Manual Verification of Commits)
            "We use four popular and diversified open source libraries, i.e., Linux, FFmpeg, Qemu, "
            "and Wireshark. They are popular OSS from different applications.",
        ),
        projects=2,  # NOTE: 2 of 4 projects were released
        # Data from the released files:
        vfcs=10894,
        non_vfcs=14979,
    )

    PROJECTS = {
        "ffmpeg": {
            "url": "https://github.com/FFmpeg/FFmpeg",
            "file_id": "1duvUGvkdsCue7vbBmfCk2lMU4oVUIIpO",
            "checksum": "41b493273a011492583742bb28ce20a792bad530d0a30166624f9744ce77c723",
        },
        "qemu": {
            "url": "https://github.com/qemu/qemu",
            "file_id": "1Y9aADriLx0_e8YioZiteD7cvdON0carn",
            "checksum": "9c5ef634e1be936eb9131ff494f586957b6ab235b1a8f80d365b73583469dc8c",
        },
    }

    # SPI-DB uses this delimiter
    _COMMIT_MSG_DELIMITER = "&&&&"

    def _drop_unnamed_columns(self, dataframe: pd.DataFrame) -> pd.DataFrame:
        return dataframe.loc[:, ~dataframe.columns.str.startswith("Unnamed")]

    def _read_clean_csv(self, path: Path) -> pd.DataFrame:
        return self._drop_unnamed_columns(pd.read_csv(path))

    def _load_all_commit_messages(self, repo: Repo) -> dict[str, list[str]]:
        repo_dict: dict[str, list[str]] = {}
        for commit in repo.iter_commits():
            message = str(commit.message)
            c_key = message.replace("\n", "").replace(" ", "").strip()
            if c_key not in repo_dict:
                repo_dict[c_key] = []
            repo_dict[c_key].append(commit.hexsha)
        return repo_dict

    def _add_commit_id(
        self,
        project_dataframe: pd.DataFrame,
        commit_dict: dict[str, list[str]],
        repo: Repo,
    ) -> pd.DataFrame:
        project_dataframe = project_dataframe.copy()
        if "commit_id" not in project_dataframe.columns:
            project_dataframe.insert(len(project_dataframe.columns), "commit_id", None)

        commit_col_idx = cast(int, project_dataframe.columns.get_loc("commit_id"))

        for row_position, (_, row) in enumerate(
            tqdm(
                project_dataframe.iterrows(),
                total=project_dataframe.shape[0],
                desc="Restoring SPI-DB commit IDs",
            )
        ):
            commit_message = row.get("commit_msg")
            if commit_message is None:
                logger.warning("[spidb] Skipping row %d: missing commit_msg", row_position)
                continue

            normalized_message = (
                str(commit_message)
                .replace(self._COMMIT_MSG_DELIMITER, "")
                .replace("\n", "")
                .replace(" ", "")
                .strip()
            )
            if normalized_message not in commit_dict:
                logger.warning(
                    "[spidb] Skipping row %d: commit message not found in repo", row_position
                )
                continue

            candidate_shas = commit_dict[normalized_message]
            resolved_commit_id: str | None = None

            if len(candidate_shas) == 1:
                resolved_commit_id = candidate_shas[0]
            else:
                if len(candidate_shas) > 2:
                    logger.warning(
                        "[spidb] Skipping row %d: >2 commits match message", row_position
                    )
                    continue

                patch = row.get("patch")
                if patch is None:
                    logger.warning("[spidb] Skipping row %d: missing patch", row_position)
                    continue

                normalized_patch = _normalize_diff_for_comparison(str(patch))
                for sha in candidate_shas:
                    try:
                        diff_output = get_commit_diff(repo, sha)
                        normalized_diff = _normalize_diff_for_comparison(diff_output)
                        if normalized_diff == normalized_patch:
                            resolved_commit_id = sha
                            break
                    except (GitCommandError, BadName) as e:
                        logger.debug("[spidb] Failed to get diff for commit %s: %s", sha, e)
                        continue

                if resolved_commit_id is None:
                    logger.warning(
                        "[spidb] Skipping row %d: unable to disambiguate commit", row_position
                    )
                    continue

            project_dataframe.iat[row_position, commit_col_idx] = resolved_commit_id

        return project_dataframe

    def _add_project_data(
        self,
        file_id: str,
        project_url: str,
        raw_dataset_dir: Path,
        checksum: str | None = None,
    ) -> pd.DataFrame:
        git_url = GitURL.parse(project_url)
        project_name = (
            git_url.repo.lower() if git_url and git_url.repo else project_url.split("/")[-1].lower()
        )
        csv_path = raw_dataset_dir / f"{project_name}.csv"
        download_file(f"https://drive.google.com/uc?id={file_id}", csv_path, checksum=checksum)

        project_data = self._read_clean_csv(csv_path)
        path = clone_repository(project_url)
        if path is None:
            logger.warning("[spidb] Unable to clone %s", project_url)
            return project_data
        with Repo(path) as repo:
            commit_dict = self._load_all_commit_messages(repo)
            return self._add_commit_id(
                project_dataframe=project_data,
                commit_dict=commit_dict,
                repo=repo,
            )

    @override
    def _load_data(self) -> pd.DataFrame:
        raw_dataset_dir = self._raw_dir / "spi-db"
        all_data = []

        for project_name, project_info in self.PROJECTS.items():
            processed_file = raw_dataset_dir / f"{project_name}-commit-ids.csv"

            # Try to load cached data
            dataframe = None
            if processed_file.exists():
                dataframe = self._read_clean_csv(processed_file)
                if "commit_id" not in dataframe.columns:
                    dataframe = None  # Invalid cache, reprocess

            # Process if needed
            if dataframe is None:
                dataframe = self._add_project_data(
                    file_id=project_info["file_id"],
                    project_url=project_info["url"],
                    raw_dataset_dir=raw_dataset_dir,
                    checksum=project_info.get("checksum"),
                )
                dataframe.to_csv(processed_file, index=False)

            dataframe["project_url"] = project_info["url"]
            all_data.append(dataframe)

        return pd.concat(all_data, ignore_index=True)

    @override
    def _parse_row(self, row: dict[str, Any]) -> DatasetEntry | None:
        raw_commit_id = row.get("commit_id")
        project_url = row.get("project_url")
        is_vfc = row.get("vulnerability") == 1

        if not project_url or not raw_commit_id:
            logger.debug(
                "[%s] Skipping row: missing commit_id=%s or project_url=%s",
                self.metadata.name,
                raw_commit_id,
                project_url,
            )
            return None

        commit_id = normalize_commit_id(raw_commit_id)
        if not commit_id:
            return None

        return DatasetEntry(
            project_url=project_url,
            commit_id=commit_id,
            src_datasets={self.metadata.name},
            is_vfc=is_vfc,
        )
