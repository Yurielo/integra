"""Protected Candidate execution rejection, using only isolated small fixtures."""
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts import archive_execution_guard as guard

ROOT = Path(__file__).resolve().parents[1]


def inventory(root):
    return {str(path.relative_to(root)): (path.stat().st_mode,
            hashlib.sha256(path.read_bytes()).hexdigest())
            for path in root.rglob("*") if path.is_file()}


class ArchiveExecutionGuardTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="integra-guard-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.package = self.root / "archive/candidate-v1-fixture/bundle"
        self.resources = self.package / "Integra.app/Contents/Resources"
        self.resources.mkdir(parents=True)
        (self.package / "inventory.json").write_text("{}")
        (self.package / "COMPLETE.json").write_text("{}")

    def test_completed_archive_import_path_rejected_without_mutation(self):
        before = inventory(self.root)
        with self.assertRaisesRegex(ValueError, "PROTECTED_ARCHIVE_EXECUTION_REJECTED"):
            guard.require_execution_path(self.resources, roots=())
        self.assertEqual(inventory(self.root), before)

    def test_incomplete_archive_is_not_an_execution_workspace(self):
        (self.package / "COMPLETE.json").unlink()
        (self.package / "candidate-manifest.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "PROTECTED_ARCHIVE_EXECUTION_REJECTED"):
            guard.require_execution_path(self.resources, roots=())

    def test_archive_with_missing_inventory_is_still_not_executable(self):
        (self.package / "inventory.json").unlink()
        with self.assertRaisesRegex(ValueError, "PROTECTED_ARCHIVE_EXECUTION_REJECTED"):
            guard.require_execution_path(self.resources, roots=())

    def test_managed_retention_root_rejects_even_missing_payload(self):
        with self.assertRaisesRegex(ValueError, "PROTECTED_ARCHIVE_EXECUTION_REJECTED"):
            guard.require_execution_path(self.root / "managed/future/import", roots=(self.root / "managed",))
        guard.require_execution_path(self.root / "managed-other", roots=(self.root / "managed",))

    def test_symlink_alias_cannot_bypass_guard(self):
        alias = self.root / "apparently-safe"
        alias.symlink_to(self.resources, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "PROTECTED_ARCHIVE_EXECUTION_REJECTED"):
            guard.require_execution_path(alias, roots=())

    def test_isolated_execution_workspace_is_allowed(self):
        workspace = self.root / "owned-execution-copy/Contents/Resources"
        workspace.mkdir(parents=True)
        guard.require_execution_path(workspace, roots=())

    def test_review_inputs_guard_interpreter_import_path_arguments_and_app(self):
        interpreter = self.resources / "python"
        interpreter.write_text("#!/bin/sh\nexit 0\n")
        interpreter.chmod(0o755)
        base = {"PATH": os.environ["PATH"]}
        cases = [(str(interpreter), [], {}),
                 (sys.executable, [], {"PYTHONPATH": str(self.resources)}),
                 (sys.executable, [], {"INTEGRA_TEST_REVIEW_PYTHONPATH": str(self.resources)}),
                 (sys.executable, ["discover", "--start-directory=" + str(self.resources)], {}),
                 (sys.executable, ["discover", "-s" + str(self.resources)], {}),
                 (sys.executable, ["discover", "-t" + str(self.resources)], {}),
                 (sys.executable, [], {"INTEGRA_CANDIDATE_APP": str(self.resources.parent.parent)}),
                 (sys.executable, [], {"INTEGRA_OWNED_WORKSPACE": str(self.package)})]
        for executable, args, changes in cases:
            with self.subTest(changes=changes, args=args), self.assertRaisesRegex(ValueError, "PROTECTED_ARCHIVE_EXECUTION_REJECTED"):
                guard.validate_review_execution(ROOT, executable, args, {**base, **changes})

    def test_interpreter_unavailable_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "TEST_INTERPRETER_UNAVAILABLE"):
            guard.validate_review_execution(ROOT, "missing-integra-interpreter", [], {"PATH": ""})

    def test_review_launcher_rejects_before_sitecustomize_or_collection(self):
        marker = self.root / "forbidden-startup.txt"
        (self.resources / "sitecustomize.py").write_text(
            "from pathlib import Path\nPath(" + repr(str(marker)) + ").write_text('executed')\n")
        (self.resources / "test_unsafe.py").write_text("raise RuntimeError('must not collect')\n")
        before = inventory(self.root)
        environment = dict(os.environ, PYTHONPATH=str(self.resources),
                           INTEGRA_TEST_REVIEW_PYTHONPATH=str(self.resources),
                           INTEGRA_REVIEW_TEST_PYTHON=sys.executable)
        result = subprocess.run(["/bin/bash", str(ROOT / "scripts/run_review_tests.sh"),
                                 "discover", "-s", str(self.resources)], env=environment,
                                text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("PROTECTED_ARCHIVE_EXECUTION_REJECTED", result.stderr)
        self.assertFalse(marker.exists())
        self.assertEqual(inventory(self.root), before)
        self.assertFalse(list(self.root.rglob("*.pyc")))

    def test_direct_candidate_smoke_entrypoints_reject_before_import_or_output(self):
        output = self.root / "results"
        before = inventory(self.root)
        for script, args in (
                ("probe_process_executor_pilot.py", ["--app", str(self.package / "Integra.app"),
                    "--source-root", str(ROOT), "--output", str(output)]),
                ("smoke_source_components_bundle.py", [str(self.package / "Integra.app"), str(output)])):
            with self.subTest(script=script):
                result = subprocess.run([sys.executable, "-I", "-B", str(ROOT / "scripts" / script), *args],
                                        capture_output=True, text=True, timeout=30)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("PROTECTED_ARCHIVE_EXECUTION_REJECTED", result.stderr)
                self.assertFalse(output.exists())
        self.assertEqual(inventory(self.root), before)


if __name__ == "__main__":
    unittest.main()
