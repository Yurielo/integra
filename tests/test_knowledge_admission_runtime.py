"""Exact owner-runtime pin checks, without downloading or changing runtimes."""
import copy
import json
from pathlib import Path
import tempfile
import subprocess
import unittest
from unittest.mock import patch

from integra_core import knowledge_admission_runtime as runtime
from integra_core import knowledge
from scripts.package_knowledge_admission_runtime import package_view_schema, _with_packaged_review_runtime


class KnowledgeAdmissionRuntimeTests(unittest.TestCase):
    def test_packaged_view_schema_is_exact_and_required_without_repo_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            resources = Path(directory) / "Contents/Resources"
            package_view_schema(resources)
            target = resources / "schemas/knowledge_view_v1.schema.json"
            self.assertEqual(target.read_bytes(), (Path(__file__).resolve().parents[1] /
                             "schemas/knowledge_view_v1.schema.json").read_bytes())
            with patch.object(knowledge, "__file__", str(resources / "integra_core/knowledge.py")):
                with self.assertRaisesRegex(knowledge.KnowledgeError, "schema differs"):
                    knowledge._validate_view_shape({})
                target.write_text("invalid JSON")
                with self.assertRaises(json.JSONDecodeError):
                    knowledge._validate_view_shape({})
                target.unlink()
                with self.assertRaises(FileNotFoundError):
                    knowledge._validate_view_shape({})

    def test_schema_packager_rejects_existing_or_symlink_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            resources = Path(directory)
            package_view_schema(resources)
            target = resources / "schemas/knowledge_view_v1.schema.json"
            original = target.read_bytes()
            with self.assertRaisesRegex(ValueError, "fresh owned destination"):
                package_view_schema(resources)
            self.assertEqual(target.read_bytes(), original)
            target.unlink()
            target.symlink_to(resources / "missing")
            with self.assertRaisesRegex(ValueError, "fresh owned destination"):
                package_view_schema(resources)

    def test_packager_exposes_fresh_review_runtime_only_for_preflight(self):
        with tempfile.TemporaryDirectory() as directory:
            resources = Path(directory)
            site_packages = resources / "runtime/review-python/site-packages"
            site_packages.mkdir(parents=True)
            with patch.dict("os.environ", {"PYTHONPATH": "existing"}, clear=False):
                previous = _with_packaged_review_runtime(resources)
                self.assertEqual(previous, "existing")
                self.assertEqual(runtime.os.environ["PYTHONPATH"],
                                 str(site_packages) + runtime.os.pathsep + "existing")

    def test_packager_rejects_missing_review_runtime_before_admission_preflight(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "packaged review runtime is unavailable"):
                _with_packaged_review_runtime(Path(directory))

    def test_accepted_source_pin_and_contract_are_exact(self):
        pin = runtime._pin()
        self.assertEqual(pin["commit_sha"], "61ee27de67174377afa0f4955b3cb5abeecb4f03")
        self.assertEqual(pin["source_pr"], 136)
        self.assertEqual(pin["contract"]["id"], "seminartext.reviewed_knowledge_admission_v1")
        self.assertEqual(len(pin["files"]), 12)

    def test_changed_pin_cannot_self_attest(self):
        pin = copy.deepcopy(runtime._pin())
        pin["commit_sha"] = "f" * 40
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "pin.json"
            target.write_text(json.dumps(pin))
            with patch.object(runtime, "PIN_PATH", target):
                with self.assertRaisesRegex(ValueError, "governed pin digest"):
                    runtime._pin()

    def test_missing_runtime_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict("os.environ", {"INTEGRA_KNOWLEDGE_ADMISSION_CHECKOUT": str(Path(directory) / "missing")}):
                with self.assertRaisesRegex(ValueError, "runtime unavailable"):
                    runtime.preflight()

    def test_bundled_dependency_tampering_is_rejected_before_execution(self):
        pin = runtime._pin()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "runtime.json").write_text(json.dumps(pin))
            first = root / next(iter(pin["files"]))
            first.parent.mkdir(parents=True)
            first.write_text("raise RuntimeError('must never execute')")
            with patch.dict("os.environ", {}, clear=True), patch.object(runtime, "BUNDLED_RUNTIME_ROOT", root):
                with self.assertRaisesRegex(ValueError, "runtime bytes differ"):
                    runtime.preflight()

    def test_symlinked_pin_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "link.json"
            target.symlink_to(runtime.PIN_PATH)
            with patch.object(runtime, "PIN_PATH", target):
                with self.assertRaisesRegex(ValueError, "unsafe"):
                    runtime._pin()

    def test_owner_executes_only_exact_snapshot_not_dependency_shadows(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            real = source / "schemas/exact.py"
            real.parent.mkdir(); real.write_bytes(b"verified dependency")
            (source / "jsonschema.py").write_text("raise RuntimeError('unbound dependency')")
            (source / "schemas/__init__.pyc").write_bytes(b"unbound bytecode")
            pin = {"runtime": str(source), "contract": {"id": "test", "sha256": "a"*64},
                   "files": {"schemas/exact.py": runtime.hashlib.sha256(real.read_bytes()).hexdigest()}}

            def execute(argv, **kwargs):
                snapshot = Path(argv[-1])
                self.assertNotEqual(snapshot, source)
                self.assertEqual([path.relative_to(snapshot).as_posix() for path in snapshot.rglob("*") if path.is_file()],
                                 ["schemas/exact.py"])
                self.assertEqual((snapshot / "schemas/exact.py").read_bytes(), real.read_bytes())
                return subprocess.CompletedProcess(argv, 0, "null", "")

            with patch.object(runtime, "preflight", return_value=pin), patch.object(runtime, "_python", return_value="python3"), \
                    patch.object(runtime.subprocess, "run", side_effect=execute):
                self.assertIsNone(runtime.owner()._call("validate_revision"))
