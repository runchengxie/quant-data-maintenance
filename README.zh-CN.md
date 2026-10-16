# quant-data-maintenance

[English README](README.md)

`quant-data-maintenance` 提供研究数据和实验产物的审计与整理工具，帮助使用者检查文件状态、发现重复内容，并在充分校验后生成可恢复的整理操作。

本项目属于 Quant Research 项目系列，为各研究仓库提供通用维护工具。它不包含具体项目的数据、凭证或个人路径。

## 开始使用

需要 Python 3.11 或更新版本，以及 `uv`：

```bash
uv sync --locked --extra dev
uv run research-data-maintenance --help
```

建议先从只读审计开始：

```bash
uv run research-data-maintenance audit /path/to/data
```

整理操作的默认行为是生成计划。同一文件的重复清单条目和带 `..` 的路径别名只计入一次。实际改动文件前，必须确认写入程序已停止，并准备好恢复回执。请先阅读完整的[使用指南](docs/zh-CN/usage.md)和[维护模型](docs/zh-CN/maintenance.md)。

## 文档

- [使用指南](docs/zh-CN/usage.md)：安装、命令示例、审计结果、整理与恢复
- [维护模型](docs/zh-CN/maintenance.md)：校验规则和安全边界
- [开发规则](AGENTS.md)：测试和开发约定

`consolidate --apply` 和 `--restore` 使用 Unix 文件锁及文件系统接口，并要求系统提供 `fuser`。这些变更流程没有 Windows 支持。运行输出为英文或 JSON，当前没有 locale 选项。
