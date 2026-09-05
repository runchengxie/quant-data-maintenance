import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research_data_maintenance import audit as audit_module


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def audit(self, **kwargs):
        change = kwargs.pop("before_final_scan", None)
        if change:
            original = audit_module.scan
            calls = 0

            def scan(*args):
                nonlocal calls
                calls += 1
                if calls == 2:
                    change()
                return original(*args)

            with patch.object(audit_module, "scan", side_effect=scan):
                return audit_module.audit(self.root, self.root / ".audit")
        return audit_module.audit(self.root, self.root / ".audit")

    def test_hard_links_are_not_duplicate_allocations(self):
        (self.root / "a").write_bytes(b"a" * 8192)
        os.link(self.root / "a", self.root / "b")
        (self.root / "c").write_bytes(b"a" * 8192)
        (self.root / "alias").symlink_to("a")
        result = self.audit()
        self.assertEqual(result["regular_paths"], 3)
        self.assertEqual(result["unique_inodes"], 2)
        self.assertEqual(result["duplicate_inode_copies"], 1)
        self.assertEqual(
            result["allocated_duplicate_upper_bound"],
            (self.root / "c").stat().st_blocks * 512,
        )
        self.assertEqual(result["symlinks"], 1)
        self.assertTrue(result["stable"])

    def test_cache_rechecks_same_size_rewrite_with_restored_mtime(self):
        (self.root / "a").write_bytes(b"abcd")
        (self.root / "b").write_bytes(b"abcd")
        self.assertEqual(self.audit()["duplicate_inode_copies"], 1)
        before = (self.root / "b").stat()
        (self.root / "b").write_bytes(b"wxyz")
        os.utime(self.root / "b", ns=(before.st_atime_ns, before.st_mtime_ns))
        self.assertEqual(self.audit()["duplicate_inode_copies"], 0)

    def test_empty_and_single_file(self):
        self.assertEqual(self.audit()["duplicate_inode_copies"], 0)
        (self.root / "a").write_bytes(b"one")
        self.assertTrue(self.audit()["stable"])

    def test_unchanged_hashes_are_cached(self):
        (self.root / "a").write_bytes(b"same")
        (self.root / "b").write_bytes(b"same")
        self.assertEqual(self.audit()["hashed_inodes"], 2)
        result = self.audit()
        self.assertEqual(result["hashed_inodes"], 0)
        self.assertEqual(result["cached_hashes"], 2)

    def test_matching_samples_require_full_hash(self):
        content = bytearray(b"a" * 24576)
        (self.root / "a").write_bytes(content)
        content[6000] = ord("b")
        (self.root / "b").write_bytes(content)
        result = self.audit()
        self.assertEqual(result["hashed_inodes"], 2)
        self.assertEqual(result["duplicate_inode_copies"], 0)

    def test_change_during_scan_invalidates_report(self):
        (self.root / "a").write_bytes(b"one")

        def change():
            (self.root / "a").write_bytes(b"two")

        self.assertFalse(self.audit(before_final_scan=change)["stable"])

    def test_external_hard_links_excluded_from_reclaim_estimate(self):
        (self.root / "a").write_bytes(b"abcd")
        (self.root / "b").write_bytes(b"abcd")
        outside = self.root / ".audit"
        outside.mkdir()
        os.link(self.root / "a", outside / "keep-a")
        os.link(self.root / "b", outside / "keep-b")
        self.assertEqual(self.audit()["allocated_duplicate_upper_bound"], 0)


if __name__ == "__main__":
    unittest.main()
