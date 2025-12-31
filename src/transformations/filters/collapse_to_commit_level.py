from __future__ import annotations

from dataset_entry import DatasetEntry


def collapse_to_commit_level(entries: list[DatasetEntry]) -> list[DatasetEntry]:
    """Collapse function-level entries to commit-level by aggregating per-function rows.

    If any function in a commit is vulnerable, the commit is marked vulnerable.
    """
    if not entries:
        return []

    commits: dict[tuple[str, str], dict] = {}

    for e in entries:
        key = (e.project_url, e.commit_id)
        if key not in commits:
            commits[key] = {
                "project_url": e.project_url,
                "commit_id": e.commit_id,
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

        c = commits[key]
        c["is_vfc"] = c["is_vfc"] or e.is_vfc
        c["src_datasets"] |= e.src_datasets
        c["cve_ids"] |= e.cve_ids
        c["cwe_ids"] |= e.cwe_ids
        c["owasp_categories"] |= e.owasp_categories or set()
        c["files_changed"] |= e.files_changed or set()
        c["commit_message"] = c["commit_message"] or e.commit_message
        c["commit_diff"] = c["commit_diff"] or e.commit_diff
        c["ghsa_id"] = c["ghsa_id"] or e.ghsa_id
        c["commit_timestamp_utc"] = c["commit_timestamp_utc"] or e.commit_timestamp_utc

    return [
        DatasetEntry(
            project_url=c["project_url"],
            commit_id=c["commit_id"],
            src_datasets=c["src_datasets"],
            is_vfc=c["is_vfc"],
            cve_ids=c["cve_ids"],
            cwe_ids=c["cwe_ids"],
            owasp_categories=c["owasp_categories"] or None,
            files_changed=c["files_changed"],
            commit_message=c["commit_message"],
            commit_diff=c["commit_diff"],
            ghsa_id=c["ghsa_id"],
            commit_timestamp_utc=c["commit_timestamp_utc"],
        )
        for c in commits.values()
    ]
