"""Tests for validating dataset VFC/non-VFC counts."""

import pytest

from vfc_datasets.base_dataset import BaseDataset
from vfc_datasets.commit_level.bigvul import BigVulDataset
from vfc_datasets.commit_level.cc900 import CC900Dataset
from vfc_datasets.commit_level.cross_vul import CrossVulDataset
from vfc_datasets.commit_level.cvefixes import CVEFixesDataset
from vfc_datasets.commit_level.devign import DevignDataset
from vfc_datasets.commit_level.icvul import ICVulDataset
from vfc_datasets.commit_level.java_vfc import JavaVFCDataset, JavaVFCDatasetExtended
from vfc_datasets.commit_level.morefixes import MorefixesDataset
from vfc_datasets.commit_level.msr2019 import MSR2019Dataset
from vfc_datasets.commit_level.patchdb import PatchDBDataset
from vfc_datasets.commit_level.pysecdb import PySecDBDataset
from vfc_datasets.commit_level.repospd import RepoSPDDataset
from vfc_datasets.commit_level.secbench import SecBenchDataset
from vfc_datasets.commit_level.spidb import SPIDBDataset
from vfc_datasets.commit_level.tqrg import TQRGDataset
from vfc_datasets.commit_level.tracer import TracerDataset
from vfc_datasets.commit_level.vcmatch import VCMatchDataset
from vfc_datasets.commit_level.vudenc import VUDEncDataset
from vfc_datasets.function_level.diversevul import DiverseVulDataset
from vfc_datasets.function_level.megavul import MegaVulDataset
from vfc_datasets.function_level.primevul import PrimeVulDataset
from vfc_datasets.function_level.sven import SVENDataset

pytestmark = [pytest.mark.slow]


def _check_counts(
    dataset_class: type[BaseDataset], entries: list, min_vfcs: int, min_non_vfcs: int
) -> None:
    """Verify that parsed counts meet minimum thresholds."""
    metadata = dataset_class.metadata

    vfcs = [e for e in entries if e.is_vfc]
    non_vfcs = [e for e in entries if not e.is_vfc]

    assert len(vfcs) >= min_vfcs, (
        f"{metadata.name}: got {len(vfcs)} VFCs, expected >= {min_vfcs} "
        f"(paper claims {metadata.vfcs})"
    )
    assert len(non_vfcs) >= min_non_vfcs, (
        f"{metadata.name}: got {len(non_vfcs)} non-VFCs, expected >= {min_non_vfcs} "
        f"(paper claims {metadata.non_vfcs})"
    )


@pytest.mark.parametrize(
    ("dataset_class", "min_vfcs", "min_non_vfcs"),
    [
        (BigVulDataset, 4367, 0),
        (CC900Dataset, 3489, 6300),
        (CrossVulDataset, 5813, 0),
        (CVEFixesDataset, 12093, 0),
        (DevignDataset, 10894, 14978),
        (ICVulDataset, 4605, 0),
        (JavaVFCDataset, JavaVFCDataset.metadata.vfcs, JavaVFCDataset.metadata.non_vfcs),
        (
            JavaVFCDatasetExtended,
            JavaVFCDatasetExtended.metadata.vfcs,
            JavaVFCDatasetExtended.metadata.non_vfcs,
        ),
        (MorefixesDataset, 31883, 0),
        (MSR2019Dataset, 1217, 0),
        (PatchDBDataset, 10534, 23741),
        (PySecDBDataset, 877, 2073),
        (RepoSPDDataset, 18124, 31394),
        (SecBenchDataset, 676, 0),
        (SPIDBDataset, 10887, 14967),
        (TQRGDataset, 7589, 97531),
        (TracerDataset, 2895, 0),
        (VCMatchDataset, 1614, 0),
        (VUDEncDataset, 1009, 0),
    ],
)
def test_commit_level_counts(dataset_class: type[BaseDataset], min_vfcs: int, min_non_vfcs: int):
    assert dataset_class.metadata.granularity == "commit"
    entries = list(dataset_class())
    _check_counts(dataset_class, entries, min_vfcs, min_non_vfcs)


@pytest.mark.parametrize(
    ("dataset_class", "min_vfc_commits", "min_non_vfc_commits"),
    [
        (DiverseVulDataset, DiverseVulDataset.metadata.vfcs, 0),
        (MegaVulDataset, MegaVulDataset.metadata.vfcs, 0),
        (PrimeVulDataset, 5570, 0),
        (SVENDataset, 559, 0),
    ],
)
def test_function_level_counts(
    dataset_class: type[BaseDataset], min_vfc_commits: int, min_non_vfc_commits: int
):
    """Test unique commit counts for function-level datasets."""
    metadata = dataset_class.metadata
    assert metadata.granularity == "function"

    entries = list(dataset_class())

    # Verify entries have function_name (required for function-level)
    assert all(e.function_name for e in entries), (
        f"{metadata.name}: function-level entries must have function_name"
    )

    # Count unique commits (not entries)
    vfc_commits = {(e.project_url, e.commit_id) for e in entries if e.is_vfc}
    non_vfc_commits = {(e.project_url, e.commit_id) for e in entries if not e.is_vfc}

    assert len(vfc_commits) >= min_vfc_commits, (
        f"{metadata.name}: got {len(vfc_commits)} unique VFC commits, "
        f"expected >= {min_vfc_commits} (paper claims {metadata.vfcs})"
    )
    assert len(non_vfc_commits) >= min_non_vfc_commits, (
        f"{metadata.name}: got {len(non_vfc_commits)} unique non-VFC commits, "
        f"expected >= {min_non_vfc_commits} (paper claims {metadata.non_vfcs})"
    )
