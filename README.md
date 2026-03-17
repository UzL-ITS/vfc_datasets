# VFC Datasets

A Python toolkit for loading, parsing, and processing Vulnerability-Fixing Commit (VFC) datasets.

## Installation

```bash
pip install -e .
```

Requires Python 3.12+.

## Quick Start

```python
from vfc_datasets import BigVulDataset, CVEFixesDataset
from vfc_datasets.transformations import deduplicate_within_repository

# Load and combine datasets
entries = BigVulDataset() + CVEFixesDataset()

# Apply transformations
entries = deduplicate_within_repository(entries)
```

See [`examples/`](examples/) for more examples.


## Cite the Original Authors

If you use any of these datasets for your research, please cite the original authors. Paper titles and DOIs are available via `DatasetClass.metadata.paper_url`.
