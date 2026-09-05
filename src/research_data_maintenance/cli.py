"""Command-line interface for research data maintenance."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import consolidate
from .audit import audit as run_audit


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    audit_parser = subparsers.add_parser("audit", help="Run a read-only data audit.")
    audit_parser.add_argument("root", type=Path)

    consolidate_parser = subparsers.add_parser(
        "consolidate", help="Plan, apply, or restore evaluation-array consolidation."
    )
    consolidate_parser.add_argument("root", type=Path)
    action = consolidate_parser.add_mutually_exclusive_group()
    action.add_argument("--apply", action="store_true")
    action.add_argument("--restore", type=Path)
    consolidate_parser.add_argument("--writers-stopped", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "audit":
        result = run_audit(args.root, args.root / ".audit")
        return 0 if result["stable"] else 2

    if (args.apply or args.restore) and not args.writers_stopped:
        raise SystemExit(
            "Stop writers and schedulers, then pass --writers-stopped"
        )
    if args.restore:
        receipt_root = Path(json.loads(args.restore.read_text())["root"]).resolve()
        if receipt_root != args.root.resolve():
            raise SystemExit("Receipt root does not match the selected data root")
    if not args.apply and not args.restore:
        print(json.dumps(consolidate.plan(args.root), indent=2))
        return 0

    with (args.root / ".storage-maintenance.lock").open("a") as lock:
        import fcntl

        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.restore:
            consolidate.restore(args.restore)
        else:
            result = consolidate.apply(args.root, consolidate.plan(args.root))
            print(json.dumps({k: v for k, v in result.items() if k != "entries"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
