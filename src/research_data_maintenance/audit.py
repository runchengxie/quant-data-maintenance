"""Read-only, inode-aware inventory and duplicate audit; standard library only."""

import collections
import datetime
import hashlib
import json
import os
import stat
import uuid
from pathlib import Path


def signature(s):
    return [
        s.st_dev,
        s.st_ino,
        s.st_size,
        s.st_mtime_ns,
        s.st_ctime_ns,
        s.st_nlink,
        s.st_mode,
        s.st_blocks * 512,
    ]


def scan(root, excluded):
    records, errors = {}, []

    def error(exc):
        errors.append(str(exc))

    for parent, dirs, files in os.walk(root, followlinks=False, onerror=error):
        dirs[:] = [d for d in dirs if Path(parent, d) != excluded]
        for name in files + [d for d in dirs if Path(parent, d).is_symlink()]:
            path = Path(parent, name)
            try:
                s = path.lstat()
                records[str(path.relative_to(root))] = signature(s)
            except OSError as exc:
                errors.append(f"{path}: {exc}")
    return records, errors


def checked_hash(path, expected, sample=False):
    # O_NOFOLLOW prevents a path replaced with a symlink from hashing another file.
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        if signature(os.fstat(stream.fileno())) != expected:
            raise RuntimeError(f"Changed before hashing: {path}")
        h = hashlib.sha256()
        if sample:
            for offset in sorted(
                {0, max(0, expected[2] // 2 - 2048), max(0, expected[2] - 4096)}
            ):
                stream.seek(offset)
                h.update(stream.read(4096))
        else:
            while chunk := stream.read(4 * 1024 * 1024):
                h.update(chunk)
        if (
            signature(os.fstat(stream.fileno())) != expected
            or signature(path.lstat()) != expected
        ):
            raise RuntimeError(f"Changed during hashing: {path}")
        return h.hexdigest()


def audit(root, audit_root):
    root, audit_root = Path(root).resolve(), Path(audit_root).resolve()
    if audit_root != root / ".audit":
        raise ValueError("Audit output must be ROOT/.audit")
    audit_root.mkdir(exist_ok=True)
    stamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")
    output = audit_root / f"v2-{stamp}-{uuid.uuid4().hex[:8]}"
    output.mkdir()
    initial, errors = scan(root, audit_root)
    inodes = {}
    for rel, sig in initial.items():
        if stat.S_ISREG(sig[6]):
            entry = inodes.setdefault(tuple(sig[:2]), {"signature": sig, "paths": []})
            entry["paths"].append(rel)
    cache_file = audit_root / "hash-cache-v2.json"
    try:
        cache = json.loads(cache_file.read_text())
    except (OSError, ValueError):
        cache = {}
    new_cache, sampled, hashed, hits = {}, 0, 0, 0
    size_groups = collections.defaultdict(list)
    for entry in inodes.values():
        if entry["signature"][2] > 0:
            size_groups[entry["signature"][2]].append(entry)
    matches = collections.defaultdict(list)
    for entries in size_groups.values():
        if len(entries) < 2:
            continue
        samples = collections.defaultdict(list)
        for entry in entries:
            sig = entry["signature"]
            path = root / entry["paths"][0]
            key = json.dumps(sig)
            try:
                if key in cache:
                    entry["sha256"] = cache[key]
                    hits += 1
                else:
                    entry["sample"] = checked_hash(path, sig, sample=True)
                    sampled += 1
                # Cached and uncached entries must be compared in the same sample groups.
                sample = entry.get("sample") or checked_hash(path, sig, sample=True)
                samples[sample].append(entry)
            except (OSError, RuntimeError) as exc:
                errors.append(str(exc))
        for candidates in samples.values():
            if len(candidates) < 2:
                continue
            for entry in candidates:
                sig = entry["signature"]
                path = root / entry["paths"][0]
                try:
                    if "sha256" not in entry:
                        entry["sha256"] = checked_hash(path, sig)
                        hashed += 1
                        if hashed % 200 == 0:
                            print(
                                f"Hashed {hashed} distinct candidate inodes", flush=True
                            )
                    new_cache[json.dumps(sig)] = entry["sha256"]
                    matches[entry["sha256"]].append(entry)
                except (OSError, RuntimeError) as exc:
                    errors.append(str(exc))
    final, final_errors = scan(root, audit_root)
    errors.extend(final_errors)
    changed = [
        p for p in initial.keys() | final.keys() if initial.get(p) != final.get(p)
    ]
    groups = []
    for digest, entries in matches.items():
        if len(entries) < 2:
            continue
        # External hard links mean removing all known paths does not free the inode.
        removable = [
            e["signature"][7] for e in entries if e["signature"][5] == len(e["paths"])
        ]
        retained_externally = len(removable) < len(entries)
        estimate = sum(removable) - (
            0 if retained_externally else min(removable, default=0)
        )
        groups.append(
            {
                "sha256": digest,
                "bytes_per_file": entries[0]["signature"][2],
                "allocated_duplicate_upper_bound": estimate,
                "inodes": entries,
            }
        )
    groups.sort(key=lambda g: g["allocated_duplicate_upper_bound"], reverse=True)
    summary = {
        "schema_version": 2,
        "root": str(root),
        "report": str(output),
        "regular_paths": sum(len(e["paths"]) for e in inodes.values()),
        "unique_inodes": len(inodes),
        "symlinks": sum(stat.S_ISLNK(s[6]) for s in initial.values()),
        "logical_path_bytes": sum(
            e["signature"][2] * len(e["paths"]) for e in inodes.values()
        ),
        "unique_logical_bytes": sum(e["signature"][2] for e in inodes.values()),
        "unique_allocated_bytes": sum(e["signature"][7] for e in inodes.values()),
        "duplicate_groups": len(groups),
        "duplicate_inode_copies": sum(len(g["inodes"]) - 1 for g in groups),
        "allocated_duplicate_upper_bound": sum(
            g["allocated_duplicate_upper_bound"] for g in groups
        ),
        "stable": not errors and not changed,
        "changed_paths": changed,
        "errors": errors,
        "hashed_inodes": hashed,
        "cached_hashes": hits,
        "limitations": "Allocation estimate excludes external hard links but not reflink sharing. "
        "A matching pre/post inventory is not a locked filesystem snapshot. "
        "No file is approved for deletion by this report.",
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2))
    (output / "duplicates.json").write_text(json.dumps(groups, indent=2))
    with (output / "inventory.jsonl").open("w") as stream:
        for rel, sig in initial.items():
            stream.write(json.dumps({"path": rel, "signature": sig}) + "\n")
    (output / "summary.md").write_text(
        "# Data audit v2\n\n"
        + "\n".join(
            f"- {key}: {value}"
            for key, value in summary.items()
            if key not in {"changed_paths", "errors"}
        )
        + "\n\nSee summary.json for changes/errors and duplicates.json for exact inode groups.\n"
    )
    # Cache only hashes whose inode was unchanged through the final scan.
    valid_signatures = {json.dumps(sig) for sig in final.values()}
    cached = {key: value for key, value in new_cache.items() if key in valid_signatures}
    temporary = audit_root / f".cache-{uuid.uuid4().hex}.json"
    temporary.write_text(json.dumps(cached))
    os.replace(temporary, cache_file)
    print(json.dumps(summary, indent=2), flush=True)
    return summary
