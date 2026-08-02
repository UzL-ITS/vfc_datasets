"""Update the Supported Datasets section of the root README from DatasetMetadata."""

import re
from collections import defaultdict
from pathlib import Path

import vfc_datasets
from vfc_datasets.base_dataset import BaseDataset, DatasetMetadata

REPO_ROOT = Path(__file__).resolve().parents[1]
ROOT_README = REPO_ROOT / "README.md"

# CamelCase word, treating runs of capitals (VFC) as one word.
_WORD = re.compile(r"[A-Z]+(?![a-z])|[A-Z][a-z]*|\d+")


def _concrete_datasets(base: type[BaseDataset]) -> list[type[BaseDataset]]:
    """Package datasets in definition order; `__subclasses__()` yields creation order."""
    result: list[type[BaseDataset]] = []
    for sub in base.__subclasses__():
        if getattr(sub, "metadata", None) is not None and sub.__module__.startswith(
            "vfc_datasets."
        ):
            result.append(sub)
        result.extend(_concrete_datasets(sub))
    return result


def _variant_name(cls: type[BaseDataset]) -> str:
    return cls.__name__.replace("Dataset", "")


def _dataset_name(variants: list[type[BaseDataset]]) -> str:
    """Leading CamelCase words all variants share: FixSeekerBalanced/Imbalanced -> FixSeeker."""
    shared: list[str] = []
    for words in zip(*(_WORD.findall(_variant_name(c)) for c in variants), strict=False):
        if len(set(words)) != 1:
            break
        shared.append(words[0])
    return "".join(shared)


def _collapse_variants(
    variants: list[type[BaseDataset]],
) -> list[tuple[type[BaseDataset], str]]:
    """One (variant, name) row per module, showing the variant defined first."""
    by_module: dict[str, list[type[BaseDataset]]] = defaultdict(list)
    for cls in variants:
        by_module[cls.__module__].append(cls)

    return [(group[0], _dataset_name(group)) for group in by_module.values()]


def _sort_key(row: tuple[type[BaseDataset], str]) -> tuple[int, str]:
    cls, name = row
    return (cls.metadata.publication_year, name)


def _fmt_int(value: int | None) -> str:
    return f"{value:,}" if value is not None else "—"


def _fmt_paper(m: DatasetMetadata) -> str:
    return f"[link]({m.paper_url})" if m.paper_url else "—"


def _fmt_name(cls: type[BaseDataset], name: str) -> str:
    return f"[{name}]({cls.metadata.source_url})"


def _render_commit_table(rows: list[tuple[type[BaseDataset], str]]) -> str:
    lines = [
        "| Year | Dataset | VFCs | Non-VFCs | Projects | Paper |",
        "|------|---------|------|----------|----------|-------|",
    ]
    for cls, name in rows:
        m = cls.metadata
        lines.append(
            f"| {m.publication_year} | {_fmt_name(cls, name)} "
            f"| {_fmt_int(m.vfcs)} | {_fmt_int(m.non_vfcs)} | {_fmt_int(m.projects)} "
            f"| {_fmt_paper(m)} |"
        )
    return "\n".join(lines) + "\n"


def _render_function_table(rows: list[tuple[type[BaseDataset], str]]) -> str:
    lines = [
        "| Year | Dataset | Vuln. Fns | Benign Fns | Projects | Paper |",
        "|------|---------|-----------|------------|----------|-------|",
    ]
    for cls, name in rows:
        m = cls.metadata
        lines.append(
            f"| {m.publication_year} | {_fmt_name(cls, name)} "
            f"| {_fmt_int(m.vulnerable_functions)} | {_fmt_int(m.benign_functions)} "
            f"| {_fmt_int(m.projects)} | {_fmt_paper(m)} |"
        )
    return "\n".join(lines) + "\n"


def _variant_note(rows: list[tuple[type[BaseDataset], str]], total: int) -> str:
    """Footnote for collapsed rows; empty when nothing collapsed."""
    if len(rows) == total:
        return ""
    return "\n> Datasets shipping several variants are listed once, showing one variant.\n"


def _render_collapsed(title: str, count: int, table: str, note: str = "") -> str:
    return (
        f"<details>\n<summary>{title} ({count} datasets)</summary>\n\n{table}{note}\n</details>\n"
    )


def _replace_block(text: str, marker: str, content: str) -> str:
    start = f"<!-- {marker}:START -->"
    end = f"<!-- {marker}:END -->"
    start_idx = text.index(start) + len(start)
    end_idx = text.index(end)
    return text[:start_idx] + "\n" + content + text[end_idx:]


def render_readme(text: str) -> str:
    """Return `text` with both dataset blocks regenerated."""
    _ = vfc_datasets  # ensure subclasses register

    all_classes = _concrete_datasets(BaseDataset)
    for marker, title, render in (
        ("COMMIT_DATASETS", "Commit-level", _render_commit_table),
        ("FUNCTION_DATASETS", "Function-level", _render_function_table),
    ):
        granularity = "commit" if marker == "COMMIT_DATASETS" else "function"
        classes = [c for c in all_classes if c.metadata.granularity == granularity]
        rows = sorted(_collapse_variants(classes), key=_sort_key)
        block = _render_collapsed(title, len(rows), render(rows), _variant_note(rows, len(classes)))
        text = _replace_block(text, marker, block)
    return text


if __name__ == "__main__":
    updated = render_readme(ROOT_README.read_text())
    ROOT_README.write_text(updated)
    print(f"Updated root README from {len(_concrete_datasets(BaseDataset))} datasets.")
