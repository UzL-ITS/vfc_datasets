"""Combine multiple VFC datasets and print joint statistics."""

import vfc_datasets
from vfc_datasets.utils.core.logging import setup_logging
from vfc_datasets.utils.core.statistics import print_dataset_stats

setup_logging("combine_datasets")

if __name__ == "__main__":
    entries = (
        vfc_datasets.BigVulDataset()
        + vfc_datasets.TQRGDataset()
        + vfc_datasets.TracerDataset()
        + vfc_datasets.MSR2019Dataset()
        + vfc_datasets.VUDEncDataset()
        + vfc_datasets.CC900Dataset()
        + vfc_datasets.SecBenchDataset()
    )
    print_dataset_stats(entries)
