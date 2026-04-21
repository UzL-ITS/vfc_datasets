"""VFC dataset loaders and base classes."""

from importlib.metadata import version

from . import commit_level, function_level
from .base_dataset import BaseDataset, DatasetMetadata
from .commit_level import *  # noqa: F403
from .function_level import *  # noqa: F403

__version__ = version(__name__)

__all__ = [
    "BaseDataset",
    "DatasetMetadata",
    *commit_level.__all__,
    *function_level.__all__,
]
