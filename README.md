# research-data-maintenance

研究数据和实验产物维护工具，重点关注可审计、可恢复和低风险操作。

项目提供两项能力：

- `audit`：只读扫描数据目录，生成 inode 感知的文件清单和重复文件报告。
- `consolidate`：根据完整 manifest 和 SHA-256 校验结果，规划、执行或恢复评估数组的重复内容合并。

工具不会自动删除数据。执行会改变文件路径的操作前，必须明确传入参数，并确认相关写入程序和调度任务已经停止。

## 当前能力

### `audit`

对指定数据根目录进行只读扫描，主要检查：

- 普通文件、符号链接、设备号、inode、大小、时间戳、硬链接数和磁盘分配空间。
- 同一 inode 的多个路径，以及内容相同但 inode 不同的文件。
- 小范围采样和完整 SHA-256 校验。
- inode 未发生变化时复用 `.audit/hash-cache-v2.json` 中的哈希结果。
- 扫描前后的清单是否一致。

报告写入数据根目录下的 `.audit`。每次运行都会创建独立目录，其中包括：

- `summary.json`：扫描统计、稳定性、错误和限制说明。
- `duplicates.json`：重复内容和 inode 分组。
- `inventory.jsonl`：扫描开始时的文件清单。
- `summary.md`：便于阅读的摘要。

报告中的 `stable: false` 表示扫描期间发生了错误或目录内容发生变化，需要人工检查。报告只提供审计结果，不代表任何文件已经获准删除。

示例：

```bash
uv run research-data-maintenance audit /path/to/data
```

扫描稳定时命令返回 `0`。扫描不稳定或出现错误时返回 `2`。

### `consolidate`

在以下分区中查找 manifest 标记为 `complete`、内容和大小均相同的 `.npy` 文件：

- `validation`
- `oos`
- `monitor_validation`
- `monitor_oos`

训练分区、符号链接、已有硬链接和路径越出 manifest 目录的文件都会被排除。

默认命令只生成计划，不修改文件：

```bash
uv run research-data-maintenance consolidate /path/to/project-data
```

审阅计划后，在确认相关写入程序和调度任务已经停止的维护窗口内执行：

```bash
uv run research-data-maintenance consolidate /path/to/project-data \
  --apply --writers-stopped
```

执行过程中，工具会：

1. 检查 `fuser` 是否能确认目标文件没有被打开或映射。
2. 再次校验 manifest、文件元数据和 SHA-256。
3. 创建维护日志和备份硬链接。
4. 在 `shared/materialized/sha256` 下创建只读共享文件。
5. 用相对符号链接替换经过验证的重复文件。
6. 校验替换结果，并保留恢复所需的回执。

CLI 会在数据根目录创建 `.storage-maintenance.lock`，避免多个维护操作同时运行。工具不会替用户停止写入程序或调度任务，`--writers-stopped` 表示调用者已经完成这项确认。

恢复必须使用 apply 操作生成的回执，并指定同一个数据根目录：

```bash
uv run research-data-maintenance consolidate /path/to/project-data \
  --restore /absolute/path/to/receipt.json --writers-stopped
```

恢复会重新写出原文件，同时保留共享内容和维护归档，便于继续审计和追溯。

## 安装

```bash
uv sync --locked --extra dev
```

项目要求 Python 3.11 或更高版本。

## 开发和验证

```bash
uv run --locked --extra dev ruff check .
uv run --locked --extra dev pytest
uv run --locked --extra dev python -m build
```

## 使用边界

项目只提供通用维护机制，不包含具体项目的 checkpoint 迁移脚本、真实研究数据或默认个人数据目录。所有路径都由调用者显式提供。

执行 `consolidate --apply` 或 `--restore` 前，应先完成写入方停机确认、维护窗口确认和恢复回执保存。

## 文档

- [维护模型](docs/maintenance.md)：说明扫描、合并和恢复的工作方式。
- [贡献和维护规则](AGENTS.md)：说明代码边界、验证命令和文档写作约定。
