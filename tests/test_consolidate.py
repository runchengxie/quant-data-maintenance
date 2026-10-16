import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research_data_maintenance import consolidate as consolidate_module


class ConsolidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.payload = b"array-data" * 1000
        for seed in (0, 1):
            root = self.root / f"artifacts/experiment/materialized/seed{seed}"
            shards = []
            for partition in ("train", "validation"):
                path = root / f"shards/{partition}-202511/x.npy"
                path.parent.mkdir(parents=True)
                path.write_bytes(self.payload)
                shards.append(
                    {
                        "partition": partition,
                        "files": [
                            {
                                "path": str(path.relative_to(root)),
                                "bytes": len(self.payload),
                                "sha256": hashlib.sha256(self.payload).hexdigest(),
                            }
                        ],
                    }
                )
            (root / "manifest.json").write_text(
                json.dumps({"status": "complete", "shards": shards})
            )
        self.module = consolidate_module

    def test_symlinked_shard_directory_is_excluded(self):
        seed = self.root / "artifacts/experiment/materialized/seed0"
        original = seed / "shards/validation-202511"
        relocated = seed / "validation-files"
        original.rename(relocated)
        original.symlink_to(relocated, target_is_directory=True)
        self.assertEqual(self.module.plan(self.root), [])
        self.assertFalse((relocated / "x.npy").is_symlink())

    def test_symlinked_seed_directory_is_excluded(self):
        seed = self.root / "artifacts/experiment/materialized/seed0"
        relocated = self.root / "seed-files"
        seed.rename(relocated)
        seed.symlink_to(relocated, target_is_directory=True)
        self.assertEqual(self.module.plan(self.root), [])

    def test_in_root_parent_path_remains_compatible(self):
        seed = self.root / "artifacts/experiment/materialized/seed0"
        manifest = seed / "manifest.json"
        data = json.loads(manifest.read_text())
        data["shards"][1]["files"][0]["path"] = (
            "shards/train-202511/../validation-202511/x.npy"
        )
        manifest.write_text(json.dumps(data))
        self.assertEqual(len(self.module.plan(self.root)), 1)

    def test_parent_aliases_count_each_candidate_once(self):
        seed = self.root / "artifacts/experiment/materialized/seed0"
        manifest = seed / "manifest.json"
        data = json.loads(manifest.read_text())
        item = data["shards"][1]["files"][0]
        data["shards"][1]["files"].append({
            **item,
            "path": "shards/train-202511/../validation-202511/x.npy",
        })
        manifest.write_text(json.dumps(data))
        groups = self.module.plan(self.root)
        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups[0]["paths"]), 2)
        receipt = self.module.apply(self.root, groups)
        self.assertEqual(receipt["replaced_paths"], 2)
        self.module.restore(Path(receipt["journal"]))
        self.assertEqual(len(self.module.plan(self.root)[0]["paths"]), 2)

    def test_symlinked_manifest_is_excluded(self):
        seed = self.root / "artifacts/experiment/materialized/seed0"
        manifest = seed / "manifest.json"
        original = seed / "source-manifest.json"
        manifest.rename(original)
        manifest.symlink_to(original)
        self.assertEqual(self.module.plan(self.root), [])

    def assert_redirected_directory_refused(self, name):
        groups = self.module.plan(self.root)
        with tempfile.TemporaryDirectory() as outside:
            (self.root / name).symlink_to(outside, target_is_directory=True)
            with self.assertRaises(RuntimeError):
                self.module.apply(self.root, groups)
            self.assertEqual(list(Path(outside).iterdir()), [])
            if name != "archive":
                self.assertFalse((self.root / "archive").exists())
            for group in groups:
                for path in group["paths"]:
                    self.assertFalse(Path(path).is_symlink())
                    self.assertEqual(Path(path).read_bytes(), self.payload)

    def test_symlinked_shared_directory_fails_before_mutation(self):
        self.assert_redirected_directory_refused("shared")

    def test_symlinked_archive_directory_fails_before_mutation(self):
        self.assert_redirected_directory_refused("archive")

    def test_eval_only_reversible_and_idempotent(self):
        groups = self.module.plan(self.root)
        self.assertEqual(len(groups), 1)
        receipt = self.module.apply(self.root, groups)
        self.assertEqual(receipt["replaced_paths"], 2)
        for seed in (0, 1):
            base = self.root / f"artifacts/experiment/materialized/seed{seed}/shards"
            self.assertTrue((base / "validation-202511/x.npy").is_symlink())
            self.assertEqual(
                (base / "validation-202511/x.npy").read_bytes(), self.payload
            )
            self.assertFalse((base / "train-202511/x.npy").is_symlink())
        self.assertEqual(self.module.plan(self.root), [])
        self.module.restore(Path(receipt["journal"]))
        self.assertEqual(len(self.module.plan(self.root)), 1)

    def test_changed_candidate_fails_before_any_replacement(self):
        groups = self.module.plan(self.root)
        Path(groups[0]["paths"][1]).write_bytes(b"changed")
        with self.assertRaises(RuntimeError):
            self.module.apply(self.root, groups)
        self.assertFalse(Path(groups[0]["paths"][0]).is_symlink())

    def test_bad_manifest_hash_fails(self):
        path = (
            self.root
            / "artifacts/experiment/materialized/seed0/shards/validation-202511/x.npy"
        )
        path.write_bytes(b"bad")
        with self.assertRaises(RuntimeError):
            self.module.apply(self.root, self.module.plan(self.root))

    def test_open_candidate_refuses_mutation(self):
        groups = self.module.plan(self.root)
        with Path(groups[0]["paths"][0]).open("rb"), self.assertRaises(RuntimeError):
            self.module.apply(self.root, groups)
        self.assertFalse(Path(groups[0]["paths"][0]).is_symlink())

    def test_interruption_before_first_link_can_restore_modes(self):
        groups = self.module.plan(self.root)
        original_replace = self.module.os.replace

        def interrupted(source, target):
            if str(source).endswith(".link"):
                raise RuntimeError("simulated interruption")
            return original_replace(source, target)

        with (
            patch.object(self.module.os, "replace", side_effect=interrupted),
            self.assertRaises(RuntimeError),
        ):
            self.module.apply(self.root, groups)
        journal = next(self.root.glob("archive/*/receipt.json"))
        self.module.restore(journal)
        for p in groups[0]["paths"]:
            self.assertEqual(Path(p).stat().st_mode & 0o777, 0o644)
            self.assertEqual(Path(p).read_bytes(), self.payload)


if __name__ == "__main__":
    unittest.main()
