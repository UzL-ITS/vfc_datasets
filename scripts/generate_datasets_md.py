"""Update the Supported Datasets section of the root README from DatasetMetadata."""

from pathlib import Path

import vfc_datasets
from vfc_datasets.base_dataset import BaseDataset, DatasetMetadata

REPO_ROOT = Path(__file__).resolve().parents[1]
ROOT_README = REPO_ROOT / "README.md"


def _concrete_datasets(base: type[BaseDataset]) -> list[type[BaseDataset]]:
    result: list[type[BaseDataset]] = []
    for sub in base.__subclasses__():
        if getattr(sub, "metadata", None) is not None:
            result.append(sub)
        result.extend(_concrete_datasets(sub))
    return result


def _pretty_name(cls: type[BaseDataset]) -> str:
    return cls.__name__.replace("Dataset", "")


def _sort_key(cls: type[BaseDataset]) -> tuple[int, str]:
    return (cls.metadata.publication_year, _pretty_name(cls))


def _fmt_int(value: int | None) -> str:
    return f"{value:,}" if value is not None else "—"


def _fmt_paper(m: DatasetMetadata) -> str:
    return f"[link]({m.paper_url})" if m.paper_url else "—"


def _fmt_name(cls: type[BaseDataset]) -> str:
    name = _pretty_name(cls)
    return f"[{name}]({cls.metadata.source_url})"


def _render_commit_table(classes: list[type[BaseDataset]]) -> str:
    lines = [
        "| Year | Dataset | VFCs | Non-VFCs | Projects | Paper |",
        "|------|---------|------|----------|----------|-------|",
    ]
    for cls in classes:
        m = cls.metadata
        lines.append(
            f"| {m.publication_year} | {_fmt_name(cls)} "
            f"| {_fmt_int(m.vfcs)} | {_fmt_int(m.non_vfcs)} | {_fmt_int(m.projects)} "
            f"| {_fmt_paper(m)} |"
        )
    return "\n".join(lines) + "\n"


def _render_function_table(classes: list[type[BaseDataset]]) -> str:
    lines = [
        "| Year | Dataset | Vuln. Fns | Benign Fns | Projects | Paper |",
        "|------|---------|-----------|------------|----------|-------|",
    ]
    for cls in classes:
        m = cls.metadata
        lines.append(
            f"| {m.publication_year} | {_fmt_name(cls)} "
            f"| {_fmt_int(m.vulnerable_functions)} | {_fmt_int(m.benign_functions)} "
            f"| {_fmt_int(m.projects)} | {_fmt_paper(m)} |"
        )
    return "\n".join(lines) + "\n"


def _render_collapsed(title: str, count: int, table: str) -> str:
    return (
        f"<details>\n"
        f"<summary>{title} ({count} datasets)</summary>\n\n"
        f"{table}\n"
        f"</details>\n"
    )


def _replace_block(text: str, marker: str, content: str) -> str:
    start = f"<!-- {marker}:START -->"
    end = f"<!-- {marker}:END -->"
    start_idx = text.index(start) + len(start)
    end_idx = text.index(end)
    return text[:start_idx] + "\n" + content + text[end_idx:]


if __name__ == "__main__":
    _ = vfc_datasets  # ensure subclasses register

    all_classes = _concrete_datasets(BaseDataset)
    commit = sorted(
        (c for c in all_classes if c.metadata.granularity == "commit"), key=_sort_key
    )
    function = sorted(
        (c for c in all_classes if c.metadata.granularity == "function"), key=_sort_key
    )

    commit_table = _render_commit_table(commit)
    function_table = _render_function_table(function)

    root = ROOT_README.read_text()
    root = _replace_block(
        root, "COMMIT_DATASETS", _render_collapsed("Commit-level", len(commit), commit_table)
    )
    root = _replace_block(
        root,
        "FUNCTION_DATASETS",
        _render_collapsed("Function-level", len(function), function_table),
    )
    ROOT_README.write_text(root)

    print(f"Updated root README with {len(commit)} commit-level and {len(function)} function-level datasets.")
