# Usage

[中文页面](zh-CN/usage.md)

The tool provides data audits and consolidation of duplicate evaluation arrays. Callers supply every data root explicitly. It is distributed independently; consumers do not need a runtime or development dependency. Check your manifest format and partition names before using it.

## Install and validate

Requires Python 3.11 or newer. CI runs on Linux with Python 3.11.

```bash
uv sync --locked --extra dev
uv run --locked --extra dev ruff check .
uv run --locked --extra dev pytest
uv run --locked --extra dev python -m build --outdir /path/to/generated/packages
```

There is no configured type checker, coverage threshold, or local dependency vulnerability gate. CI runs Ruff, tests, package build, and a public-path scan; GitHub also configures CodeQL and Dependabot. Runtime output is English or JSON and has no locale option.

## Audit

```bash
uv run research-data-maintenance audit /path/to/data
```

Audit records regular files, symlinks, device/inode identities, sizes, timestamps, link counts, and allocated space. It groups shared inodes separately from equal contents, uses sampling before full SHA-256, and reuses `.audit/hash-cache-v2.json` when inode metadata is unchanged. A second inventory detects changes during scanning.

Each run writes `summary.json`, `duplicates.json`, `inventory.jsonl`, and `summary.md` in its own directory under the root's `.audit`. Data files are not rewritten or deleted. `stable: false` means errors or inventory changes require review. Exit status is `0` for a stable scan and `2` otherwise. Reports do not authorize deletion or constitute a filesystem snapshot.

## Plan consolidation

```bash
uv run research-data-maintenance consolidate /path/to/project-data
```

The planner reads `artifacts/*/materialized/seed*/manifest.json` files whose `status` is `complete`. It groups `.npy` paths whose manifest SHA-256 and size match in `validation`, `oos`, `monitor_validation`, and `monitor_oos`. Training partitions, symlinks (including ancestor directories of manifests or arrays), existing hard links, and escaping paths are excluded or rejected.

Planning reads metadata and prints JSON without changing files. It does not hash candidate bytes and cannot establish content equality.

## Apply and restore

These workflows require Unix `fcntl`, `os.O_NOFOLLOW`, directory synchronization, hard links, and `fuser`. Windows mutation workflows are not supported. Stop writers and schedulers yourself; `--writers-stopped` records that confirmation and does not stop processes.

```bash
uv run research-data-maintenance consolidate /path/to/project-data --apply --writers-stopped
```

Apply takes `.storage-maintenance.lock`, checks open files and mappings with `fuser`, compares file metadata against the plan, and checks actual size and SHA-256 against manifest values. It creates a receipt and backup hard links, creates read-only shared content under `shared/materialized/sha256`, and replaces duplicate paths with relative symlinks. It verifies replacements and removes redundant backups after success. Receipts and shared content remain.

Apply does not reread manifests after planning. Keep writers stopped throughout planning and application. On failure, retain receipts and any surviving backups for review and recovery.

```bash
uv run research-data-maintenance consolidate /path/to/project-data --restore /absolute/path/to/receipt.json --writers-stopped
```

`--apply` and `--restore` are mutually exclusive. Restore requires the same resolved root recorded in the receipt. It verifies paths and content and reconstructs regular files with recorded permissions and timestamps, using backups when present or shared content otherwise. Shared files and maintenance archives are retained.

## Scope

This is a general mechanism, not a project-specific checkpoint migration tool. Do not add real data, credentials, private directory conventions, or automatic project migrations. Any future integration needs an explicit consumer, pinned version, and independently verified recovery contract.

See the [maintenance model](maintenance.md) and [development rules](../AGENTS.md).
