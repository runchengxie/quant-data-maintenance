"""CLI contracts without mutating user data or invoking production writers."""

import json
from pathlib import Path

import pytest

from research_data_maintenance.cli import build_parser, main


def test_mutation_actions_are_mutually_exclusive():
    with pytest.raises(SystemExit) as error:
        build_parser().parse_args(["consolidate", ".", "--apply", "--restore", "receipt.json"])
    assert error.value.code == 2


@pytest.mark.parametrize("action", [["--apply"], ["--restore", "missing.json"]])
def test_mutation_requires_explicit_writer_confirmation(tmp_path, action):
    with pytest.raises(SystemExit, match="Stop writers and schedulers"):
        main(["consolidate", str(tmp_path), *action])
    assert list(tmp_path.iterdir()) == []


def test_restore_rejects_mismatched_root_before_locking(tmp_path):
    receipt = tmp_path / "receipt.json"
    receipt.write_text(json.dumps({"root": str(tmp_path / "another-root")}))
    with pytest.raises(SystemExit, match="Receipt root does not match"):
        main(["consolidate", str(tmp_path), "--restore", str(receipt), "--writers-stopped"])
    assert not (tmp_path / ".storage-maintenance.lock").exists()


def test_default_consolidation_prints_plan_without_creating_lock(tmp_path, capsys):
    assert main(["consolidate", str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out) == []
    assert list(tmp_path.iterdir()) == []


def test_audit_cli_writes_reports_only_under_audit_directory(tmp_path):
    data = tmp_path / "sample.bin"
    data.write_bytes(b"unchanged")
    assert main(["audit", str(tmp_path)]) == 0
    assert data.read_bytes() == b"unchanged"
    assert {path.name for path in tmp_path.iterdir()} == {"sample.bin", ".audit"}
    assert list(Path(tmp_path / ".audit").rglob("summary.json"))
