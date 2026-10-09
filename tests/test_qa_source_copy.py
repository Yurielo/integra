"""Issue #233: literal-only materialization and fail-closed copy security."""
import importlib.util
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("qa_source_copy", Path(__file__).parents[1] / "scripts/qa_source_copy.py")
qa = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = qa
SPEC.loader.exec_module(qa)


class QASourceCopyTests(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory()
        self.addCleanup(self.workspace.cleanup)
        self.root = Path(self.workspace.name).resolve()
        self.source = self.root / "source"
        self.source.mkdir()
        (self.source / "nested").mkdir()
        (self.source / "nested/data.txt").write_bytes(b"unchanged demo bytes")
        self.targets = self.root / "targets"
        self.targets.mkdir()
        self.specs = []
        for index in range(4):
            target = self.targets / str(index)
            target.write_bytes(("runtime-%s" % index).encode())
            relative = "bin/tool%s" % index
            (self.source / "bin").mkdir(exist_ok=True)
            (self.source / relative).symlink_to(target)
            self.specs.append(qa.LinkSpec(relative, str(target), str(target)))
        self.specs = tuple(self.specs)
        self.addCleanup(patch.stopall)
        patch.object(qa, "HISTORICAL_LINKS", self.specs).start()
        # snapshot's production default is immutable: patch wrapper only in fixtures.
        self.original_snapshot = qa.snapshot
        patch.object(qa, "snapshot", side_effect=lambda root, specs=None:
                     self.original_snapshot(root, self.specs if specs is None else specs)).start()
        self.destination = self.root / "copy"

    def reject(self):
        with self.assertRaises((qa.QACopyError, OSError)):
            qa.prepare_copy(self.source, self.destination)

    def test_materializes_exact_four_and_preserves_regular_bytes_and_original(self):
        before = qa.snapshot(self.source)
        result = qa.prepare_copy(self.source, self.destination)
        self.assertTrue(result["original_unchanged"])
        self.assertEqual(before, qa.snapshot(self.source))
        self.assertEqual(len(result["materialized_links"]), 4)
        self.assertFalse(any(path.is_symlink() for path in self.destination.rglob("*")))
        self.assertEqual((self.destination / "nested/data.txt").read_bytes(), b"unchanged demo bytes")
        for spec in self.specs:
            self.assertEqual((self.destination / spec.relative).read_bytes(), Path(spec.terminal).read_bytes())

    def test_unknown_symlink(self):
        (self.source / "other").symlink_to(self.targets / "0")
        self.reject()
        self.assertFalse(self.destination.exists())

    def test_right_basename_wrong_directory(self):
        (self.source / "tool0").symlink_to(self.targets / "0")
        self.reject()

    def test_missing_expected_link(self):
        (self.source / self.specs[0].relative).unlink()
        self.reject()

    def test_replaced_expected_link_with_regular_file(self):
        link = self.source / self.specs[0].relative
        link.unlink()
        link.write_bytes(b"replacement")
        self.reject()

    def test_changed_raw_target(self):
        link = self.source / self.specs[0].relative
        link.unlink()
        link.symlink_to(self.targets / "1")
        self.reject()

    def test_missing_terminal(self):
        (self.targets / "0").unlink()
        self.reject()

    def test_directory_terminal(self):
        (self.targets / "0").unlink()
        (self.targets / "0").mkdir()
        self.reject()

    def test_unexpected_terminal_symlink(self):
        (self.targets / "0").unlink()
        (self.targets / "0").symlink_to(self.targets / "1")
        self.reject()

    def test_cyclic_terminal(self):
        (self.targets / "0").unlink()
        (self.targets / "0").symlink_to(self.targets / "0")
        self.reject()

    def test_terminal_ancestor_symlink(self):
        actual = self.root / "renamed-targets"
        self.targets.rename(actual)
        self.targets.symlink_to(actual, target_is_directory=True)
        self.reject()

    def test_hardlinked_terminal(self):
        os.link(self.targets / "0", self.targets / "extra")
        self.reject()

    def test_hardlinked_source_file(self):
        os.link(self.source / "nested/data.txt", self.source / "extra")
        self.reject()

    def test_special_file(self):
        os.mkfifo(self.source / "fifo")
        self.reject()

    def test_source_root_symlink(self):
        alias = self.root / "alias"
        alias.symlink_to(self.source, target_is_directory=True)
        with self.assertRaises(OSError):
            qa.prepare_copy(alias, self.destination)

    def test_source_ancestor_symlink(self):
        alias = self.root / "alias"
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(OSError):
            qa.prepare_copy(alias / "source", self.destination)

    def test_destination_ancestor_symlink(self):
        alias = self.root / "alias"
        alias.symlink_to(self.root, target_is_directory=True)
        self.destination = alias / "copy"
        self.reject()

    def test_existing_destination(self):
        self.destination.mkdir()
        self.reject()

    def test_dangling_destination(self):
        self.destination.symlink_to(self.root / "missing")
        self.reject()

    def test_overlap(self):
        self.destination = self.source / "copy"
        self.reject()

    def test_case_alias_overlap_never_mutates_source(self):
        alias = self.root / "SOURCE"
        if not alias.exists():
            # Case-sensitive hosts still test the actual inode-containment gate.
            source_fd = qa._directory(self.source)
            child_fd = qa._directory(self.source / "nested")
            try:
                self.assertTrue(qa._contains_inode(source_fd, child_fd))
            finally:
                os.close(source_fd)
                os.close(child_fd)
            return
        before = qa.snapshot(self.source)
        self.destination = alias / "nested/copy"
        self.reject()
        self.assertFalse((self.source / "nested/copy").exists())
        self.assertEqual(before, qa.snapshot(self.source))

    def test_exact_chain_and_escape_rejected(self):
        first, second, terminal = self.targets / "first", self.targets / "second", self.targets / "0"
        first.symlink_to("second")
        second.symlink_to("0")
        spec = qa.LinkSpec("fixture", str(first), str(terminal),
                           ((str(first), "second"), (str(second), "0")))
        fd, record = qa._target(spec)
        os.close(fd)
        self.assertEqual(len(record["chain"]), 2)
        bad = qa.LinkSpec("fixture", str(first), str(terminal), ((str(first), "../escape"),))
        with self.assertRaises(qa.QACopyError):
            qa._target(bad)

    def test_target_swap_after_preflight(self):
        original = qa.snapshot
        def changed(root, specs=None):
            result = original(root, specs)
            if root == self.source:
                (self.targets / "0").write_bytes(b"changed target")
            return result
        with patch.object(qa, "snapshot", side_effect=changed):
            self.reject()

    def test_source_swap_after_preflight(self):
        original = qa.snapshot
        def changed(root, specs=None):
            result = original(root, specs)
            if root == self.source:
                (self.source / "nested/data.txt").unlink()
                (self.source / "nested/data.txt").symlink_to(self.targets / "0")
            return result
        with patch.object(qa, "snapshot", side_effect=changed):
            self.reject()

    def test_link_swap_after_preflight(self):
        original = qa.snapshot
        def changed(root, specs=None):
            result = original(root, specs)
            if root == self.source:
                link = self.source / self.specs[0].relative
                link.unlink()
                link.symlink_to(self.targets / "1")
            return result
        with patch.object(qa, "snapshot", side_effect=changed):
            self.reject()

    def test_directory_swap_after_preflight(self):
        original = qa.snapshot
        def changed(root, specs=None):
            result = original(root, specs)
            if root == self.source:
                (self.source / "nested").rename(self.root / "renamed-nested")
                (self.source / "nested").symlink_to(self.root / "renamed-nested", target_is_directory=True)
            return result
        with patch.object(qa, "snapshot", side_effect=changed):
            self.reject()

    def test_output_corruption(self):
        original = qa._copy_fd
        def corrupted(source, parent, name, expected):
            original(source, parent, name, expected)
            fd = os.open(name, os.O_WRONLY, dir_fd=parent)
            os.write(fd, b"corrupt")
            os.close(fd)
        with patch.object(qa, "_copy_fd", side_effect=corrupted):
            self.reject()

    def test_receipt_is_exclusive_no_follow(self):
        path = self.root / "receipt.json"
        qa.write_receipt(path, b"{}")
        with self.assertRaises(FileExistsError):
            qa.write_receipt(path, b"overwrite")
        alias = self.root / "receipt-alias"
        alias.symlink_to(path)
        with self.assertRaises(FileExistsError):
            qa.write_receipt(alias, b"overwrite")
        self.assertEqual(path.read_bytes(), b"{}")

    def test_cli_rejects_arbitrary_protected_output_root(self):
        script = Path(__file__).parents[1] / "scripts/prepare_k2_native_qa_copy.py"
        for value in (str(self.source), str(self.targets), "/Users/invalid/Build Archive"):
            result = subprocess.run([sys.executable, "-B", str(script)],
                                    env={**os.environ, "INTEGRA_OWNED_WORKSPACE": value},
                                    text=True, capture_output=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("exact disposable", result.stderr)
        self.assertFalse((self.source / "projects").exists())

    def test_cli_requires_governed_workspace_and_forbids_output_flags(self):
        script = Path(__file__).parents[1] / "scripts/prepare_k2_native_qa_copy.py"
        environment = {key: value for key, value in os.environ.items()
                       if key != "INTEGRA_OWNED_WORKSPACE"}
        result = subprocess.run([sys.executable, "-B", str(script)], env=environment,
                                text=True, capture_output=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("governed issue233-qa-copy", result.stderr)
        result = subprocess.run([sys.executable, "-B", str(script), "--receipt", str(self.source / "write")],
                                env=environment, text=True, capture_output=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unrecognized arguments", result.stderr)
        self.assertFalse((self.source / "write").exists())


if __name__ == "__main__":
    unittest.main()
