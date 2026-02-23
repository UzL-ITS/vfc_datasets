from __future__ import annotations

from dataset_entry import DatasetEntry


def collapse_to_commit_level(entries: list[DatasetEntry]) -> list[DatasetEntry]:
    """Collapse function-level entries to commit-level by aggregating per-function rows.

    If any function in a commit is vulnerable, the commit is marked vulnerable.
    """
    # TODO: What happens when a dataset only includes benign functions of a VFC?
    if not entries:
        return []

    commits: dict[tuple[str, str], dict] = {}

    for entry in entries:
        key = (entry.project_url, entry.commit_id)
        if key not in commits:
            commits[key] = {
                "project_url": entry.project_url,
                "commit_id": entry.commit_id,
                "is_vfc": False,
                "src_datasets": set(),
                "cve_ids": set(),
                "cwe_ids": set(),
                "owasp_categories": set(),
                "files_changed": set(),
                "commit_message": None,
                "commit_diff": None,
                "ghsa_id": None,
                "commit_timestamp_utc": None,
            }

        commit_data = commits[key]
        commit_data["is_vfc"] = commit_data["is_vfc"] or entry.is_vfc
        commit_data["src_datasets"] |= entry.src_datasets
        commit_data["cve_ids"] |= entry.cve_ids
        commit_data["cwe_ids"] |= entry.cwe_ids
        commit_data["owasp_categories"] |= entry.owasp_categories or set()
        commit_data["files_changed"] |= entry.files_changed or set()
        commit_data["commit_message"] = commit_data["commit_message"] or entry.commit_message
        commit_data["commit_diff"] = commit_data["commit_diff"] or entry.commit_diff
        commit_data["ghsa_id"] = commit_data["ghsa_id"] or entry.ghsa_id
        commit_data["commit_timestamp_utc"] = (
            commit_data["commit_timestamp_utc"] or entry.commit_timestamp_utc
        )

    return [
        DatasetEntry(
            project_url=commit_data["project_url"],
            commit_id=commit_data["commit_id"],
            src_datasets=commit_data["src_datasets"],
            is_vfc=commit_data["is_vfc"],
            cve_ids=commit_data["cve_ids"],
            cwe_ids=commit_data["cwe_ids"],
            owasp_categories=commit_data["owasp_categories"] or None,
            files_changed=commit_data["files_changed"],
            commit_message=commit_data["commit_message"],
            commit_diff=commit_data["commit_diff"],
            ghsa_id=commit_data["ghsa_id"],
            commit_timestamp_utc=commit_data["commit_timestamp_utc"],
        )
        for commit_data in commits.values()
    ]
