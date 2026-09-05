# research-data-maintenance

Safe, reversible maintenance utilities for research data and experiment artifacts.

This project provides two deliberately conservative operations:

- `audit`: a read-only, inode-aware inventory and duplicate audit.
- `consolidate`: a manifest- and hash-validated plan/apply/restore workflow for duplicate evaluation arrays.

It does not delete data automatically. Mutation requires an explicit flag and a confirmation that relevant writers and schedulers are stopped.

## Install

```bash
uv sync --locked --extra dev
```

## Audit a data root

```bash
uv run research-data-maintenance audit /path/to/data
```

Each audit writes a new report under `/path/to/data/.audit`. The report compares inventories before and after hashing, protects against symlink replacement while hashing, and reports duplicate allocation as an upper bound. It is not a filesystem snapshot or deletion approval.

## Consolidate evaluation arrays

Generate a metadata-only plan:

```bash
uv run research-data-maintenance consolidate /path/to/project-data
```

Apply a reviewed plan only after stopping relevant writers and schedulers:

```bash
uv run research-data-maintenance consolidate /path/to/project-data \
  --apply --writers-stopped
```

Restore from a receipt while retaining the shared content:

```bash
uv run research-data-maintenance consolidate /path/to/project-data \
  --restore /absolute/path/to/receipt.json --writers-stopped
```

Only complete manifests and validation/OOS partitions qualify. Training partitions, symlinks, and pre-existing hard links are excluded. Every candidate is checked against its manifest hash and current filesystem metadata before replacement.

## Development

```bash
uv run --locked --extra dev ruff check .
uv run --locked --extra dev pytest
uv run --locked --extra dev python -m build
```

The repository intentionally excludes project-specific checkpoint migration scripts and real research data. Paths are supplied by the caller; no personal data directory is assumed.
