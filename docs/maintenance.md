# Maintenance model

[中文页面](zh-CN/maintenance.md)

Observation and mutation have separate contracts.

## Audit

Audit reads data files and writes only reports and the hash cache under `.audit`. It inventories device/inode, size, timestamps, link counts, and allocated space. Duplicate candidates are sampled and then hashed. Cached SHA-256 values are reused only when inode metadata is unchanged. Errors or differences in the final inventory set `stable` to `false`.

The optional cache must be a JSON object with lowercase 64-character hexadecimal SHA-256 values. Invalid containers and digest entries are ignored and recomputed from file contents; valid entries keep the existing inode checks. Regression tests cover malformed containers and invalid digests for different files with matching samples.

Reclaimable space is an estimate. External hard links are excluded from that estimate; reflink sharing is not modeled. Reports neither authorize deletion nor provide a filesystem snapshot.

## Evaluation-array consolidation

The planner reads `artifacts/*/materialized/seed*/manifest.json` files whose `status` is `complete` and selects `.npy` entries in `validation`, `oos`, `monitor_validation`, and `monitor_oos`. It excludes training data, symlinks, manifests or arrays reached through symlink directories, and existing hard links, and rejects paths escaping the manifest directory or data root. Before creating directories or replacing files, application checks candidate paths and the shared/archive path components and rejects symlinks or escaping paths.

A plan normalizes validated paths so repeated manifest entries and `..` aliases count each candidate once, then groups manifest-declared hashes and sizes and captures file metadata. It does not verify actual bytes. Application checks open files and mappings, compares metadata with the plan, and hashes every candidate before creating shared files or replacing paths. It does not reread manifests, so callers must keep writers stopped from planning through application.

The CLI holds a maintenance lock during apply/restore. Application creates receipts and backup hard links, creates read-only shared content, replaces original paths with relative symlinks, and verifies the replacements. Redundant backup links are removed only after verification. Receipts and shared content remain. Interruptions can leave backups and a partial receipt for recovery.

Restore checks original paths and shared hashes, then reconstructs regular files with recorded permissions and timestamps. It retains shared content and archives. Both mutation commands require `--writers-stopped`, Unix filesystem/locking interfaces, and `fuser`; this is caller confirmation rather than process control.

Path checks do not replace the maintenance window. Stop writers and schedulers so directories and files remain unchanged between checks and filesystem operations.
