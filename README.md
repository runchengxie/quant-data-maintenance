# quant-data-maintenance

[中文 README](README.zh-CN.md)

Audit research data and plan recoverable consolidation of duplicate evaluation arrays. The tool contains no project data, credentials, or personal paths.

Requires Python 3.11 or newer. Consolidation apply/restore uses Unix filesystem and locking interfaces and requires `fuser`; Windows mutation workflows are not supported.

## Start

```bash
uv sync --locked --extra dev
uv run research-data-maintenance --help
uv run research-data-maintenance audit /path/to/data
```

`audit` reads data and writes reports and a hash cache under the selected root's `.audit` directory. `consolidate` defaults to printing a metadata-based plan. The plan does not verify candidate bytes. Stop writers and schedulers before applying or restoring; read the [usage guide](docs/usage.md) and [maintenance model](docs/maintenance.md) first.

Runtime output is English or JSON. There is no locale option.

## Documentation

- [Usage](docs/usage.md): installation, CLI, reports, consolidation, and recovery
- [Maintenance model](docs/maintenance.md): validation and safety boundaries
- [Development rules](AGENTS.md): scope and required checks
