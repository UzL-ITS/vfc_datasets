"""Base dataset class for vulnerability-fixing commit datasets."""

import logging
from abc import ABC, abstractmethod
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

import pandas as pd
from tqdm.auto import tqdm

from config import DATASET_PATH, RAW_DATA_PATH, USE_DATASET_CACHE
from dataset_entry import DatasetEntry
from utils.core.serialization import load_cache, save_cache

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DatasetMetadata:
    """Immutable metadata for a VFC dataset."""

    # Required
    name: str
    source_url: str
    granularity: Literal["commit", "function"]
    publication_year: int

    # Dataset characteristics
    programming_languages: tuple[str, ...] = ()
    license: str | None = None

    # Stats from paper
    vfcs: int | None = None
    non_vfcs: int | None = None
    projects: int | None = None
    vulnerable_functions: int | None = None
    benign_functions: int | None = None

    # Paper reference
    paper_title: str | None = None
    paper_url: str | None = None
    paper_quotes: tuple[str, ...] = ()


class BaseDataset(ABC):
    """Base class for VFC datasets.

    Subclasses must define `metadata` and implement `_load_data()` and `_parse_row()`.
    """

    metadata: DatasetMetadata

    def __init__(self) -> None:
        if not hasattr(self, "metadata"):
            raise ValueError(
                f"{self.__class__.__name__} must define 'metadata' class attribute "
                "with DatasetMetadata instance"
            )
        self._entries: list[DatasetEntry] | None = None

    @property
    def _raw_dir(self) -> Path:
        """Directory for raw dataset files."""
        return RAW_DATA_PATH

    @abstractmethod
    def _load_data(self) -> pd.DataFrame:
        """Load raw data, downloading if needed."""
        ...

    @abstractmethod
    def _parse_row(self, row: dict[str, Any]) -> DatasetEntry | None:
        """Parse one row into DatasetEntry. Return None to skip."""
        ...

    def _parse(self) -> list[DatasetEntry]:
        """Parse dataset with caching."""
        if self._entries is not None:
            return self._entries

        name = self.metadata.name

        if USE_DATASET_CACHE:
            cached: list[DatasetEntry] | None = load_cache(name, DATASET_PATH)
            if cached is not None:
                self._entries = cached
                return cached

        df = self._load_data()

        entries: list[DatasetEntry] = []
        records = cast(list[dict[str, Any]], df.to_dict(orient="records"))
        for row in tqdm(records, total=len(records), desc=f"Parsing {name}", dynamic_ncols=True):
            entry = self._parse_row(row)
            if entry:
                entries.append(entry)

        if not entries:
            logger.warning("[%s] Parsed 0 entries; skipping cache write.", name)
            self._entries = entries
            return entries

        if USE_DATASET_CACHE:
            save_cache(entries, name)
        self._entries = entries
        return entries

    def __iter__(self) -> Iterator[DatasetEntry]:
        yield from self._parse()

    def __add__(self, other: "BaseDataset | Iterable[DatasetEntry]") -> list[DatasetEntry]:
        """Combine datasets: `BigVulDataset() + DevignDataset()`"""
        self_entries = self._parse()
        if isinstance(other, BaseDataset):
            return self_entries + other._parse()
        return self_entries + list(other)

    def __radd__(self, other: list[DatasetEntry]) -> list[DatasetEntry]:
        """Support `existing_list + Dataset()`"""
        return list(other) + self._parse()

    def __len__(self) -> int:
        return len(self._parse())

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}()"

    def __str__(self) -> str:
        m = self.metadata
        langs = ", ".join(m.programming_languages) if m.programming_languages else "any"
        return f"{m.name} ({m.publication_year}, {langs})"
