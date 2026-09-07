# 项目维护规则

## 项目定位

`research-data-maintenance` 提供研究数据和实验产物的安全维护工具。项目关注审计、重复内容识别、可验证的空间整理和可恢复操作。

工具不会默认删除数据，也不应包含具体项目的真实数据、凭证、个人路径或 checkpoint 迁移脚本。

## 代码边界

- `audit` 必须保持只读，只能在数据根目录的 `.audit` 下写入报告和哈希缓存。
- `consolidate` 的变更操作必须经过 manifest、文件元数据和 SHA-256 校验。
- 训练分区、符号链接、已有硬链接和越界路径不能进入合并计划。
- 修改文件路径前必须确认写入程序和调度任务已经停止。
- 不要改变现有 CLI 命令、参数和 `research-data-maintenance` 入口名称，除非同步更新 README、维护文档和测试。

## 验证命令

提交前运行：

```bash
uv run --locked --extra dev ruff check .
uv run --locked --extra dev pytest
uv run --locked --extra dev python -m build
```

涉及 CLI 时，还应检查：

```bash
uv run research-data-maintenance audit /path/to/data
uv run research-data-maintenance consolidate /path/to/project-data
```

默认的 `consolidate` 命令只生成计划。不要在没有维护窗口和恢复回执的情况下运行 `--apply`。

## 文档写作约定

- 说明文档以中文为主，使用自然、直接的表达。
- 中文正文使用中文标点。命令、路径、配置键、Python 名称和行内代码保留原样。
- 避免翻译腔、没有必要的英文缩写和复杂长句。
- 避免用双引号、粗体、分号和破折号堆叠重点。
- 说明限制时直接写出结论，减少重复的否定转折句。
- 行为发生变化时，同时更新 README、`docs/` 和相关测试说明。
