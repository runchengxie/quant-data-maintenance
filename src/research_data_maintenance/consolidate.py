"""Consolidate manifest-identical evaluation arrays during a maintenance window.

Default is a metadata-only plan. --apply requires writers to be stopped first.
Training partitions and existing hard links are deliberately excluded.
"""

import collections
import hashlib
import json
import os
import shutil
import stat
import subprocess
import uuid
from pathlib import Path

PARTITIONS = {"validation", "oos", "monitor_validation", "monitor_oos"}


def fingerprint(path):
    s = path.lstat()
    return [
        s.st_dev,
        s.st_ino,
        s.st_size,
        s.st_mtime_ns,
        s.st_ctime_ns,
        s.st_nlink,
        s.st_mode,
    ]


def digest(path):
    before = fingerprint(path)
    h = hashlib.sha256()
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), "rb") as stream:
        while chunk := stream.read(4 * 1024 * 1024):
            h.update(chunk)
    if fingerprint(path) != before:
        raise RuntimeError(f"Changed while hashing: {path}")
    return h.hexdigest()


def plan(root):
    root = Path(root).resolve()
    groups = collections.defaultdict(dict)
    for manifest in sorted(root.glob("artifacts/*/materialized/seed*/manifest.json")):
        data = json.loads(manifest.read_text())
        if data.get("status") != "complete":
            continue
        for shard in data["shards"]:
            if shard["partition"] not in PARTITIONS:
                continue
            for item in shard["files"]:
                path = manifest.parent / item["path"]
                if path.suffix != ".npy" or path.is_symlink():
                    continue
                if not manifest.parent.resolve().is_relative_to(
                    root
                ) or not path.resolve().is_relative_to(manifest.parent.resolve()):
                    raise RuntimeError(f"Escaping manifest path: {path}")
                s = path.lstat()
                if not stat.S_ISREG(s.st_mode) or s.st_nlink != 1:
                    continue
                groups[(item["sha256"], item["bytes"])][str(path)] = fingerprint(path)
    return [
        {"sha256": key[0], "bytes": key[1], "paths": list(paths), "signatures": paths}
        for key, paths in groups.items()
        if len(paths) > 1
    ]


def assert_idle(paths):
    # fuser also checks memory mappings. It does not replace stopping schedulers.
    if not shutil.which("fuser"):
        raise RuntimeError("fuser is required to check open files and mappings")
    for start in range(0, len(paths), 100):
        result = subprocess.run(
            ["fuser", *map(str, paths[start : start + 100])],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 1 or result.stdout.strip() or result.stderr.strip():
            raise RuntimeError(
                f"Open files or incomplete fuser check: {result.stdout} {result.stderr}"
            )


def save(path, data):
    temporary = path.with_suffix(".tmp")
    with temporary.open("w") as stream:
        json.dump(data, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    fd = os.open(path.parent, os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def apply(root, groups):
    root = Path(root).resolve()
    paths = [Path(p) for g in groups for p in g["paths"]]
    assert_idle(paths)
    # Validate the entire batch before creating shared files or changing any path.
    for group in groups:
        for path_string in group["paths"]:
            path = Path(path_string)
            if (
                fingerprint(path) != group["signatures"][path_string]
                or path.stat().st_size != group["bytes"]
                or digest(path) != group["sha256"]
            ):
                raise RuntimeError(f"Manifest or inventory mismatch: {path}")
    assert_idle(paths)
    archive = root / "archive" / f"eval-array-consolidation-{uuid.uuid4().hex[:12]}"
    archive.mkdir(parents=True)
    shared = root / "shared" / "materialized" / "sha256"
    shared.mkdir(parents=True, exist_ok=True)
    journal = archive / "receipt.json"
    receipt = {
        "schema_version": 1,
        "root": str(root),
        "journal": str(journal),
        "status": "in_progress",
        "replaced_paths": 0,
        "released_allocated_upper_bound": 0,
        "entries": [],
    }
    save(journal, receipt)
    for group in groups:
        target = shared / f"{group['sha256']}.npy"
        if target.exists() or target.is_symlink():
            raise RuntimeError(
                f"Shared target already exists; review before proceeding: {target}"
            )
        for path_string in group["paths"]:
            if fingerprint(Path(path_string)) != group["signatures"][path_string]:
                raise RuntimeError(f"Changed before replacement: {path_string}")
        assert_idle([Path(p) for p in group["paths"]])
        entries = []
        for index, path_string in enumerate(group["paths"]):
            path = Path(path_string)
            entry = {
                "path": path_string,
                "shared": str(target),
                "sha256": group["sha256"],
                "backup": str(
                    archive / f"backup-{len(receipt['entries']) + index}.npy"
                ),
                "mode": stat.S_IMODE(path.stat().st_mode),
                "mtime_ns": path.stat().st_mtime_ns,
                "allocated_bytes": path.stat().st_blocks * 512,
            }
            entries.append(entry)
        receipt["entries"].extend(entries)
        save(journal, receipt)
        # Backups are hard links, so this stage requires almost no additional space.
        for entry in entries:
            os.link(entry["path"], entry["backup"], follow_symlinks=False)
        os.link(entries[0]["backup"], target)
        target.chmod(0o444)
        for entry in entries:
            path = Path(entry["path"])
            temporary = path.with_name(f".{path.name}.{archive.name}.link")
            temporary.symlink_to(os.path.relpath(target, path.parent))
            os.replace(temporary, path)
        if digest(target) != group["sha256"] or any(
            Path(e["path"]).resolve() != target for e in entries
        ):
            raise RuntimeError(
                f"Post-replacement verification failed; backups retained: {journal}"
            )
        receipt["replaced_paths"] += len(entries)
        save(journal, receipt)
        # Only verified redundant inodes are removed. Shared content retains all bytes.
        for entry in entries:
            Path(entry["backup"]).unlink()
        receipt["released_allocated_upper_bound"] += sum(
            e["allocated_bytes"] for e in entries[1:]
        )
        save(journal, receipt)
        print(f"Consolidated {len(entries)} paths: {group['sha256'][:12]}", flush=True)
    receipt["status"] = "complete"
    save(journal, receipt)
    return receipt


def restore(journal):
    receipt = json.loads(Path(journal).read_text())
    root = Path(receipt["root"]).resolve()
    for entry in receipt["entries"]:
        path, shared, backup = map(
            Path, (entry["path"], entry["shared"], entry["backup"])
        )
        if not path.parent.resolve().is_relative_to(root) or not shared.is_relative_to(
            root / "shared"
        ):
            raise RuntimeError("Receipt path outside data root")
        if not path.is_symlink():
            if digest(path) != entry["sha256"]:
                raise RuntimeError(f"Refusing changed original: {path}")
            if not shared.exists() or not path.samefile(shared):
                continue
        elif path.resolve() != shared:
            raise RuntimeError(f"Refusing changed reference: {path}")
        if digest(shared) != entry["sha256"]:
            raise RuntimeError(f"Refusing changed reference: {path}")
        assert_idle([path, shared])
        temporary = path.with_name(f".{path.name}.restore-{uuid.uuid4().hex[:8]}")
        shutil.copyfile(backup if backup.exists() else shared, temporary)
        if digest(temporary) != entry["sha256"]:
            raise RuntimeError(f"Restore verification failed: {temporary}")
        temporary.chmod(entry["mode"])
        os.utime(temporary, ns=(entry["mtime_ns"], entry["mtime_ns"]))
        os.replace(temporary, path)
    receipt["status"] = "restored_shared_content_retained"
    save(Path(journal), receipt)
