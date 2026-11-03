import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from integra_core import semantic_review_runtime as runtime


class SemanticReviewRuntimeTests(unittest.TestCase):
    def package(self, root: Path) -> Path:
        root.mkdir()
        for name in runtime.ROLE_FILENAMES.values():
            (root / name).write_bytes(("synthetic " + name).encode())
        return root

    def provider(self, root: Path) -> Path:
        provider = root / "runtime" / "seminartext-semantic"
        entrypoint = provider / "seminartext_modules" / "semantic_workflow.py"
        entrypoint.parent.mkdir(parents=True)
        entrypoint.write_text("# synthetic packaged provider", encoding="utf-8")
        files = {"seminartext_modules/semantic_workflow.py": hashlib.sha256(entrypoint.read_bytes()).hexdigest()}
        (provider / "runtime.json").write_text(json.dumps({
            "component": "seminartext.semantic_workflow", "schema_version": "1.0.0", "files": files,
        }), encoding="utf-8")
        return provider

    def test_package_requires_absolute_regular_role_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); package = self.package(root / "package")
            selected, files, package_id = runtime._package(str(package))
            self.assertEqual(selected, package.resolve())
            self.assertEqual(set(files), set(runtime.ROLE_FILENAMES))
            self.assertEqual(len(package_id), 64)
            with self.assertRaisesRegex(ValueError, "select a local"):
                runtime._package("relative-package")
            (package / "source.bin").unlink()
            (package / "source.bin").symlink_to(root / "outside")
            with self.assertRaisesRegex(ValueError, "unsafe"):
                runtime._package(str(package))

    def test_provider_manifest_is_hash_locked(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); provider = self.provider(root / "resources")
            self.assertEqual(runtime._provider_root(root / "resources"), provider)
            (provider / "seminartext_modules" / "semantic_workflow.py").write_text("tampered")
            with self.assertRaisesRegex(ValueError, "bytes do not match"):
                runtime._provider_root(root / "resources")

    def test_submission_reuses_one_timestamped_receipt_after_lost_response(self):
        projection = {"package": {"id": "review_fixture", "sha256": "a" * 64}, "proposals": [{
            "proposal_id": "proposal_fixture", "proposal_sha256": "b" * 64, "saved_decision": None,
        }]}
        current = {"package_id": "c" * 64, "projection": projection}
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(runtime, "review_projection", return_value=current), \
             patch.object(runtime, "_run", return_value={}):
            root = Path(directory); package = self.package(root / "package")
            decision = {"proposal_id": "proposal_fixture", "action": "ACCEPT", "reason": "Явное решение"}
            runtime.submit_review(root / "resources", root / "data", package_dir=str(package), reviewer_id="Проверяющий", decisions=[decision])
            runtime.submit_review(root / "resources", root / "data", package_dir=str(package), reviewer_id="Проверяющий", decisions=[decision])
            receipts = list((root / "data" / "semantic-reviews" / ("c" * 64)).glob("submission-*.json"))
            self.assertEqual(len(receipts), 1)
            envelope = json.loads(receipts[0].read_text(encoding="utf-8"))
            self.assertEqual(envelope["decisions"][0]["action"], "ACCEPT")
            self.assertIn("timestamp", envelope["decisions"][0])

    def test_edit_requires_editable_fields(self):
        projection = {"package": {"id": "review_fixture", "sha256": "a" * 64}, "proposals": [{
            "proposal_id": "proposal_fixture", "proposal_sha256": "b" * 64, "saved_decision": None,
        }]}
        with tempfile.TemporaryDirectory() as directory, patch.object(runtime, "review_projection", return_value={"package_id": "c" * 64, "projection": projection}):
            package = self.package(Path(directory) / "package")
            with self.assertRaisesRegex(ValueError, "editable fields"):
                runtime.submit_review(Path(directory) / "resources", Path(directory) / "data", package_dir=str(package),
                                      reviewer_id="Проверяющий", decisions=[{"proposal_id": "proposal_fixture", "action": "EDIT", "reason": "Правка"}])


if __name__ == "__main__":
    unittest.main()
