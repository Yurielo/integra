"""Independent QA: synthetic tempfile archives only; never call recovery.main."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("i01_exact_cache_recovery", HERE / "exact_cache_recovery.py")
RECOVERY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RECOVERY)


def inventory(root):
    result = []
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in sorted(dirs + files):
            path = Path(directory) / name
            info = path.lstat()
            entry = dict(path=path.relative_to(root).as_posix(), mode=stat.S_IMODE(info.st_mode))
            if stat.S_ISDIR(info.st_mode):
                entry["type"] = "directory"
            elif stat.S_ISREG(info.st_mode):
                entry.update(type="file", size=info.st_size,
                             sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            else:
                raise ValueError("nonregular inventory entry")
            result.append(entry)
    return sorted(result, key=lambda item: item["path"])


class ExactCacheRecoveryQA(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="i01-recovery-independent-qa-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.archive = self.base / "archive"
        self.archive.mkdir()
        self.parent = self.base / "quarantine"
        self.roots = ["Contents/core/__pycache__", "Contents/core/vendor/__pycache__",
                      "Contents/core/vendor/owner/__pycache__"]
        for root in self.roots:
            (self.archive / root).parent.mkdir(parents=True, exist_ok=True)
        (self.archive / "Contents/core/knowledge.py").write_bytes(b"recorded source payload\n")
        self.expected = inventory(self.archive)
        for number, root in enumerate(self.roots):
            cache = self.archive / root
            cache.mkdir()
            (cache / "module.cpython-314.pyc").write_bytes(bytes([number]) * (100 + number))
        self.extras = self.extra_inventory()
        self.original_payload = (self.archive / "Contents/core/knowledge.py").read_bytes()
        self.moves = []
        self.authority = dict(authority_ref="synthetic-qa-only", plan_sha256="1" * 64)

    def extra_inventory(self):
        recorded = {entry["path"] for entry in self.expected}
        result = []
        for entry in inventory(self.archive):
            if entry["path"] not in recorded:
                info = (self.archive / entry["path"]).lstat()
                result.append(dict(entry, uid=info.st_uid, nlink=info.st_nlink))
        return result

    def mover(self, source, destination):
        self.assertFalse(destination.exists())
        source.rename(destination)
        self.moves.append((source, destination))

    def verifier(self, archive):
        self.assertEqual(inventory(archive), self.expected)
        return {"status": "SYNTHETIC_STRICT_PASS"}

    def recover(self, **overrides):
        kwargs = dict(archive=self.archive, expected=self.expected, extras=self.extras,
                      roots=self.roots, parent=self.parent, authority=self.authority,
                      inventory=inventory, inactive=lambda _: True,
                      mover=self.mover, verifier=self.verifier)
        kwargs.update(overrides)
        return RECOVERY.recover_exact(**kwargs)

    def assert_preflight_rejects(self, **kwargs):
        before = inventory(self.archive)
        with self.assertRaises((ValueError, OSError)):
            self.recover(**kwargs)
        self.assertEqual(self.moves, [])
        self.assertEqual(inventory(self.archive), before)

    def journal(self):
        paths = list(self.parent.glob("issue279-*/recovery-journal.json"))
        self.assertEqual(len(paths), 1)
        return json.loads(paths[0].read_bytes())

    def test_preserves_all_extra_bytes_modes_and_original_payload(self):
        result = self.recover()
        self.assertEqual(result["state"], "VERIFIED")
        self.assertEqual(len(self.moves), 3)
        self.assertFalse(result["quarantine_deletion_authorized"])
        self.assertEqual(result["unexpected_files"], 3)
        self.assertEqual(result["unexpected_file_bytes"], 303)
        for extra in self.extras:
            old = self.archive / extra["path"]
            saved = Path(result["quarantine_path"]) / "preserved" / extra["path"]
            self.assertFalse(old.exists())
            self.assertEqual(stat.S_IMODE(saved.stat().st_mode), extra["mode"])
            if extra["type"] == "file":
                self.assertEqual(hashlib.sha256(saved.read_bytes()).hexdigest(), extra["sha256"])
        self.assertEqual(self.journal()["state"], "VERIFIED")
        retained_inventory = Path(result["quarantine_path"]) / "preserved-inventory.json"
        self.assertEqual(result["preserved_inventory_sha256"],
                         hashlib.sha256(retained_inventory.read_bytes()).hexdigest())
        self.assertEqual((self.archive / "Contents/core/knowledge.py").read_bytes(), self.original_payload)

    def test_unknown_extra_entry_fails_before_any_move(self):
        (self.archive / "unrecognized.bin").write_bytes(b"unapproved")
        self.assert_preflight_rejects()

    def test_changed_extra_bytes_fail_before_any_move(self):
        (self.archive / self.roots[0] / "module.cpython-314.pyc").write_bytes(b"changed")
        self.assert_preflight_rejects()

    def test_changed_recorded_bytes_fail_before_any_move(self):
        (self.archive / "Contents/core/knowledge.py").write_bytes(b"changed recorded payload")
        self.assert_preflight_rejects()

    def test_recorded_payload_cannot_be_inside_move_root(self):
        target = next(e for e in self.extras if e["type"] == "file")
        expected = self.expected + [RECOVERY.canonical_entry(target)]
        extras = [e for e in self.extras if e != target]
        self.assert_preflight_rejects(expected=expected, extras=extras)

    def test_bad_and_overlapping_roots_fail_before_moves(self):
        for roots in [self.roots[:2], [self.roots[0]] * 3,
                      ["/absolute", *self.roots[1:]], ["../escape", *self.roots[1:]],
                      ["Contents", *self.roots[1:]]]:
            with self.subTest(roots=roots):
                self.assert_preflight_rejects(roots=roots)

    def test_wrong_extra_owner_and_changed_mode_fail(self):
        extras = copy.deepcopy(self.extras)
        extras[0]["uid"] += 1
        self.assert_preflight_rejects(extras=extras)
        (self.archive / self.roots[0]).chmod(0o700 if extras[0]["mode"] != 0o700 else 0o755)
        self.assert_preflight_rejects()

    def test_hardlinked_cache_fails_even_if_diff_declares_link_count(self):
        cache = self.archive / self.roots[0] / "module.cpython-314.pyc"
        os.link(cache, self.base / "external-link")
        extras = self.extra_inventory()
        self.assert_preflight_rejects(extras=extras)

    def test_linked_archive_or_quarantine_parent_is_rejected(self):
        link = self.base / "archive-link"
        link.symlink_to(self.archive, target_is_directory=True)
        self.assert_preflight_rejects(archive=link)
        actual = self.base / "actual-quarantine"
        actual.mkdir()
        self.parent.symlink_to(actual, target_is_directory=True)
        self.assert_preflight_rejects()

    def test_symlink_cache_entry_is_rejected_before_moves(self):
        cache = self.archive / self.roots[0] / "module.cpython-314.pyc"
        cache.unlink()
        cache.symlink_to(self.archive / "Contents/core/knowledge.py")
        with self.assertRaises(ValueError):
            self.recover()
        self.assertEqual(self.moves, [])
        self.assertTrue(cache.is_symlink())

    def test_missing_authority_and_active_consumer_fail_before_moves(self):
        self.assert_preflight_rejects(authority={})
        self.assert_preflight_rejects(inactive=lambda _: False)

    def test_activity_change_between_moves_preserves_partial_journal(self):
        calls = iter([True, True, False])
        with self.assertRaisesRegex(ValueError, "activity changed"):
            self.recover(inactive=lambda _: next(calls))
        self.assertEqual(len(self.moves), 1)
        journal = self.journal()
        self.assertEqual(journal["state"], "PARTIAL_PRESERVED")
        self.assertEqual(journal["moved"], self.roots[:1])
        self.assertTrue((self.archive / self.roots[1]).is_dir())
        self.assertTrue((Path(journal["quarantine_path"]) / "preserved" / self.roots[0]).is_dir())

    def test_second_move_failure_preserves_every_file_and_durable_pending_root(self):
        def failing_move(source, destination):
            if len(self.moves) == 1:
                raise OSError("synthetic second move failure")
            self.mover(source, destination)
        with self.assertRaisesRegex(OSError, "second move failure"):
            self.recover(mover=failing_move)
        journal = self.journal()
        self.assertEqual(journal["state"], "PARTIAL_PRESERVED")
        self.assertEqual(journal["moved"], self.roots[:1])
        self.assertEqual(journal["pending_root"], self.roots[1])
        preserved = Path(journal["quarantine_path"]) / "preserved"
        for extra in self.extras:
            if extra["type"] == "file":
                original, quarantine = self.archive / extra["path"], preserved / extra["path"]
                self.assertEqual(sum(path.exists() for path in [original, quarantine]), 1)
                self.assertEqual(hashlib.sha256((original if original.exists() else quarantine).read_bytes()).hexdigest(), extra["sha256"])

    def test_final_verifier_failure_keeps_all_moved_bytes(self):
        def fail(_):
            raise ValueError("synthetic strict verifier failure")
        with self.assertRaisesRegex(ValueError, "strict verifier failure"):
            self.recover(verifier=fail)
        journal = self.journal()
        self.assertEqual(journal["state"], "PARTIAL_PRESERVED")
        self.assertEqual(journal["moved"], self.roots)
        self.assertEqual(inventory(self.archive), self.expected)
        for extra in self.extras:
            self.assertTrue((Path(journal["quarantine_path"]) / "preserved" / extra["path"]).exists())

    def test_move_committed_then_exception_retains_pending_root_for_recovery(self):
        def committed_then_failed(source, destination):
            self.mover(source, destination)
            raise OSError("synthetic failure after rename")
        with self.assertRaisesRegex(OSError, "after rename"):
            self.recover(mover=committed_then_failed)
        journal = self.journal()
        self.assertEqual(journal["state"], "PARTIAL_PRESERVED")
        self.assertEqual(journal["pending_root"], self.roots[0])
        self.assertFalse((self.archive / self.roots[0]).exists())
        self.assertTrue((Path(journal["quarantine_path"]) / "preserved" / self.roots[0]).is_dir())
        self.assertEqual((self.archive / "Contents/core/knowledge.py").read_bytes(), self.original_payload)

    def test_cache_changed_during_first_move_stops_before_second_move(self):
        def mutate_second(source, destination):
            self.mover(source, destination)
            (self.archive / self.roots[1] / "module.cpython-314.pyc").write_bytes(b"concurrent change")
        with self.assertRaisesRegex(ValueError, "subtree changed"):
            self.recover(mover=mutate_second)
        self.assertEqual(len(self.moves), 1)
        journal = self.journal()
        self.assertEqual(journal["state"], "PARTIAL_PRESERVED")
        self.assertTrue((self.archive / self.roots[1]).is_dir())
        self.assertTrue((Path(journal["quarantine_path"]) / "preserved" / self.roots[0]).is_dir())

    def test_ancestor_quarantine_parent_is_rejected_before_mutation(self):
        self.assert_preflight_rejects(parent=self.base)

    def test_quarantine_parent_inside_archive_is_rejected_before_mutation(self):
        parent = self.archive / "quarantine"
        self.assert_preflight_rejects(parent=parent)
        self.assertFalse(parent.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
