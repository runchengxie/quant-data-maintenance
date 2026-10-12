# Maintenance model

[中文页面](zh-CN/maintenance.md)

Observation and mutation have separate contracts.

## Audit

Audit reads data files and writes only reports and the hash cache under `.audit`. It inventories device/inode, size, timestamps, link counts, and allocated space. Duplicate candidates are sampled and then hashed. Cached SHA-256 values are reused only when inode metadata is unchanged. Errors or differences in the final inventory set `stable` to `false`.

Reclaimable space is an estimate. External hard links are excluded from that estimate; reflink sharing is not modeled. Reports neither authorize deletion nor provide a filesystem snapshot.

## Evaluation-array consolidation

The planner reads complete `artifacts/*/materialized/seed*/manifest.json` files and selects `.npy` entries in `validation`, `oos`, `monitor_validation`, and `monitor_oos`. It excludes training data, symlinks, and existing hard links and rejects paths escaping the manifest directory or data root.

A plan groups manifest-declared hashes and sizes and captures file metadata. It does not verify actual bytes. Application checks open files and mappings, compares metadata with the plan, and hashes every candidate before creating shared files or replacing paths. It does not reread manifests, so callers must keep writers stopped from planning through application.

The CLI holds a maintenance lock during apply/restore. Application creates receipts and backup hard links, creates read-only shared content, replaces original paths with relative symlinks, and verifies the replacements. Redundant backup links are removed only after verification. Receipts and shared content remain. Interruptions can leave backups and a partial receipt for recovery.

Restore checks original paths and shared hashes, then reconstructs regular files with recorded permissions and timestamps. It retains shared content and archives. Both mutation commands require `--writers-stopped`, Unix filesystem/locking interfaces, and `fuser`; this is caller confirmation rather than process control.
