# VFC Datasets

A Python toolkit for loading, unifying, and enriching **Vulnerability-Fixing Commit (VFC)** datasets.

Plenty of VFC datasets exist, but schemas and completeness vary. `vfc_datasets` loads them through a single interface and yields a shared `DatasetEntry`. Optional transformations let you deduplicate, filter, sanitize, and enrich entries with commit data (message, diff, files changed, timestamp).

## Installation

Copy [`.env.example`](.env.example) to `.env` and adjust as needed — all settings are optional, with sensible defaults.

Then open the repo in VS Code and run **"Reopen in Container"** to use the provisioned devcontainer.

Alternatively, install into your own environment (requires Python 3.12+):

```bash
pip install -e .
```

## Quick Start

```python
from vfc_datasets import BigVulDataset, CVEFixesDataset
from vfc_datasets import transformations

entries = BigVulDataset() + CVEFixesDataset()
entries = transformations.collapse_to_commit_level(entries)
entries = transformations.deduplicate_within_repository(entries)
```

See [`examples/`](examples/) for more.

## Cite the Original Authors

If you use any of these datasets for your research, please cite the original authors. Paper titles and URLs are available via `DatasetClass.metadata.paper_url`.
