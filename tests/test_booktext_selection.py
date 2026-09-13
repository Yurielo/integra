import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from integra_core import booktext_runtime as runtime


class BookTextSelectionTests(unittest.TestCase):
    def test_selection_transport_is_strict_and_normalized(self):
        self.assertEqual(runtime.validate_page_selection("1-5, 8", "2"), {"pages": "1-5,8", "exclude_pages": "2"})
        self.assertEqual(runtime.validate_page_selection("", None), {"pages": None, "exclude_pages": None})
        for value in (True, 2, "0", "5-1", "1,", "-3", "1 --help", "1-100001", "1.2"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                runtime.validate_page_selection(value)

    def test_pinned_component_resolves_page_ranges_without_renumbering(self):
        import importlib.util
        source = Path(__file__).resolve().parents[1] / ".runtime-components/booktext-pinned/booktext.py"
        if not source.is_file():
            self.skipTest("pinned BookText checkout not available")
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), runtime.ENTRYPOINT_SHA256)
        spec = importlib.util.spec_from_file_location("booktext_selection_source", source)
        component = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(component)
        self.assertEqual(component.choose_pages(9, "3-7", "4,6"), [3, 5, 7])

    def test_runtime_forwards_selection_and_checks_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "input.pdf"
            source.write_bytes(b"fixture input")
            output = root / "out"
            state = {"surya": "/surya", "vision": "/vision", "model_sha256": "a" * 64,
                     "model_evidence": "AVAILABLE_LOCAL_MODEL_NOT_EXECUTION_ATTESTATION"}
            def invoke(command, **kwargs):
                self.assertEqual(command[-4:], ["--pages", "3-7", "--exclude-pages", "4,6"])
                (output / "integra_booktext_manifest.json").write_text(json.dumps({
                    "component": "booktext", "commit_sha": runtime.PINNED_COMMIT,
                    "blocks": [{"unit_index": 3}],
                    "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                    "selection": {"pages": "3-7", "exclude_pages": "4,6"}}))
                return SimpleNamespace(returncode=0)
            with patch.object(runtime, "preflight", return_value=state), patch.object(runtime.subprocess, "run", side_effect=invoke):
                result = runtime.run_ocr(source, output, pages="3-7", exclude_pages="4,6")
            self.assertEqual(result["blocks"][0]["unit_index"], 3)
            self.assertEqual(result["runtime"]["model_evidence"], state["model_evidence"])

    def test_invalid_selection_fails_before_runtime_or_output(self):
        with patch.object(runtime, "preflight") as preflight:
            with self.assertRaises(ValueError):
                runtime.run_ocr(Path("missing"), Path("unused"), pages="0")
            preflight.assert_not_called()

    def test_worker_rejects_invalid_confidence_instead_of_claiming_evidence(self):
        from workers.booktext_ocr_worker import _confidence
        for value in (float("nan"), float("inf"), -0.1, 1.1, True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                _confidence({"blocks": [{"confidence": value}]})
        self.assertEqual(_confidence({"blocks": [{"confidence": 0.8}, {"confidence": 1.0}]}), 0.9)

    def test_runtime_rejects_wrong_selection_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "input.pdf"
            source.write_bytes(b"fixture")
            output = root / "out"
            def invoke(*args, **kwargs):
                (output / "integra_booktext_manifest.json").write_text(json.dumps({
                    "component": "booktext", "commit_sha": runtime.PINNED_COMMIT,
                    "blocks": [{"unit_index": 1}], "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                    "selection": {"pages": None, "exclude_pages": None}}))
                return SimpleNamespace(returncode=0)
            with patch.object(runtime, "preflight", return_value={"surya": "/s", "vision": "/v"}), patch.object(runtime.subprocess, "run", side_effect=invoke):
                with self.assertRaisesRegex(ValueError, "provenance"):
                    runtime.run_ocr(source, output, pages="3")


if __name__ == "__main__":
    unittest.main()
