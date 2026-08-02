"""Base dataset class for vulnerability-fixing commit datasets."""

import hashlib
import inspect
import logging
from abc import ABC, abstractmethod
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast, override

import pandas as pd
from tqdm.auto import tqdm

import vfc_datasets.parsing_helpers as _parsing_helpers
import vfc_datasets.utils.git.url as _git_url_module
import vfc_datasets.utils.patterns as _patterns_module
from vfc_datasets.config import DATASET_PATH
from vfc_datasets.dataset_entry import DatasetEntry
from vfc_datasets.utils.core.serialization import load_cache, save_cache

logger = logging.getLogger(__name__)

_ENTRY_SCHEMA_FINGERPRINT = hashlib.blake2b(
    repr(DatasetEntry.__annotations__).encode(), digest_size=4
).hexdigest()

# Fingerprint the shared parsing helpers too, since _parse_row's bytecode misses changes in them.
_HELPERS_FINGERPRINT = hashlib.blake2b(
    b"".join(
        inspect.getsource(m).encode() for m in (_parsing_helpers, _git_url_module, _patterns_module)
    ),
    digest_size=4,
).hexdigest()


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

    Shipped `commit_message`/`commit_diff`/`commit_timestamp_utc` are stripped by default
    so they come uniformly from enrichment; pass `include_dataset_commit_data=True` to keep
    them. `files_changed`/`function_name` are entry identity and are never stripped.
    """

    metadata: DatasetMetadata

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # Skip private intermediate base classes (e.g., _FixSeekerBase, _JavaVFCBase)
        if not getattr(cls, "metadata", None) and not cls.__name__.startswith("_"):
            raise TypeError(f"{cls.__name__} must define a 'metadata' class attribute")

    def __init__(self, *, include_dataset_commit_data: bool = False) -> None:
        self._entries: list[DatasetEntry] | None = None
        self.include_dataset_commit_data = include_dataset_commit_data

    @property
    def _dataset_dir(self) -> Path:
        """Directory whose `cache/` subdirectory holds parsed entries."""
        return DATASET_PATH

    @abstractmethod
    def _load_data(self) -> pd.DataFrame:
        """Load raw data, downloading if needed."""
        ...

    @abstractmethod
    def _parse_row(self, row: dict[str, Any]) -> DatasetEntry | None:
        """Parse one row into DatasetEntry. Return None to skip."""
        ...

    def _cache_key(self) -> str:
        """Cache key over dataset name, entry-schema fingerprint, parser hash, shared
        parsing helpers, and the include_dataset_commit_data flag.

        A change to any of them yields a new key, so a stale cache can never shadow a fix
        or serve shipped commit data to a stripped instance.
        """
        parser_fingerprint = hashlib.blake2b(
            type(self)._parse_row.__code__.co_code, digest_size=4
        ).hexdigest()
        commit_data_flag = "d1" if self.include_dataset_commit_data else "d0"
        return (
            f"{self.metadata.name}-s{_ENTRY_SCHEMA_FINGERPRINT}-p{parser_fingerprint}"
            f"-h{_HELPERS_FINGERPRINT}-{commit_data_flag}"
        )

    def _parse(self) -> list[DatasetEntry]:
        """Parse dataset with caching."""
        if self._entries is not None:
            return self._entries

        name = self.metadata.name
        cache_key = self._cache_key()

        cached: list[DatasetEntry] | None = load_cache(cache_key, self._dataset_dir)
        if cached is not None:
            self._entries = cached
            return cached

        df = self._load_data()

        entries: list[DatasetEntry] = []
        records = cast(list[dict[str, Any]], df.to_dict(orient="records"))
        for row in tqdm(records, total=len(records), desc=f"Parsing {name}"):
            entry = self._parse_row(
                {k: None if isinstance(v, float) and v != v else v for k, v in row.items()}
            )
            if not entry:
                continue
            if not self.include_dataset_commit_data:
                entry.commit_message = None
                entry.commit_diff = None
                entry.commit_timestamp_utc = None
            entries.append(entry)

        if not entries:
            logger.warning("[%s] Parsed 0 entries; skipping cache write.", name)
            self._entries = entries
            return entries

        save_cache(entries, cache_key, self._dataset_dir)
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

    @override
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}()"

    @override
    def __str__(self) -> str:
        m = self.metadata
        langs = ", ".join(m.programming_languages) if m.programming_languages else "any"
        return f"{m.name} ({m.publication_year}, {langs})"
