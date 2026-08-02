"""Tests for the README dataset-table generator."""

import importlib.util
from pathlib import Path
from typing import Any

import pytest

from vfc_datasets.base_dataset import BaseDataset, DatasetMetadata

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "generate_datasets_md.py"


def _load_generator() -> Any:
    """Import the generator; scripts/ is not an installed module."""
    spec = importlib.util.spec_from_file_location("generate_datasets_md", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gen = _load_generator()


def _stub(cls_name: str, module: str, vfcs: int) -> type[BaseDataset]:
    """A dataset class in a caller-chosen module."""
    return type(
        cls_name,
        (BaseDataset,),
        {
            "metadata": DatasetMetadata(
                name=cls_name.lower(),
                source_url="https://example.invalid",
                granularity="commit",
                publication_year=2026,
                vfcs=vfcs,
            ),
            "__module__": module,
            "_load_data": lambda self: None,
            "_parse_row": lambda self, row: None,
        },
    )


def test_readme_is_up_to_date():
    """The committed README must match the generator output."""
    committed = (REPO_ROOT / "README.md").read_text()

    assert gen.render_readme(committed) == committed, (
        "README.md is stale - run `python scripts/generate_datasets_md.py`"
    )


def test_variants_in_one_module_collapse_to_the_first_defined():
    """First defined wins, regardless of size."""
    small = _stub("AcmeBasic", "pkg.acme", vfcs=10)
    large = _stub("AcmeExtended", "pkg.acme", vfcs=999)

    rows = gen._collapse_variants([small, large])

    assert rows == [(small, "Acme")]


def test_lone_dataset_keeps_its_own_name():
    """A lone variant shares all its words, so its name is unchanged."""
    solo = _stub("AcmeBasic", "pkg.solo", vfcs=10)

    assert gen._collapse_variants([solo]) == [(solo, "AcmeBasic")]


def test_definition_order_selects_the_representative():
    """Reordering a module swaps the variant shown."""
    a = _stub("OrderAlpha", "pkg.order", vfcs=5)
    b = _stub("OrderBeta", "pkg.order", vfcs=5)

    assert gen._collapse_variants([a, b]) == [(a, "Order")]
    assert gen._collapse_variants([b, a]) == [(b, "Order")]


def test_acronyms_are_treated_as_whole_words():
    """Acronyms stay whole: no mid-acronym cut."""
    base = _stub("JavaVFC", "pkg.javavfc", vfcs=784)
    extended = _stub("JavaVFCExtended", "pkg.javavfc", vfcs=16837)

    assert gen._dataset_name([base, extended]) == "JavaVFC"


@pytest.mark.parametrize(
    ("granularity", "expected"),
    [("commit", 22), ("function", 8)],
)
def test_shipped_dataset_counts(granularity: str, expected: int):
    """Guards against an accidental merge or split."""
    shipped = [
        c for c in gen._concrete_datasets(BaseDataset) if c.metadata.granularity == granularity
    ]

    assert len(gen._collapse_variants(shipped)) == expected


def test_test_only_subclasses_are_excluded():
    """Test stubs must never reach the README."""
    modules = {c.__module__ for c in gen._concrete_datasets(BaseDataset)}

    assert all(m.startswith("vfc_datasets.") for m in modules)
