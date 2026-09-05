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
