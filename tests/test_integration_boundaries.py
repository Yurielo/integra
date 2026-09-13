"""Regression checks for cross-component UI and persisted ownership boundaries."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import uuid
from unittest.mock import patch

from integra_core.capabilities import build_plan

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("integration_test_bridge", ROOT / "macos/Resources/bridge.py")
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


class IntegrationBoundaries(unittest.TestCase):
    def test_downstream_publication_compares_evidence_under_lock(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); (root / "runs").mkdir()
            run_id = "urn:integra:run:" + str(uuid.uuid4())
            path = root / "runs" / (run_id.split(":")[-1] + ".json")
            record = {"state": "COMPLETED", "source_results": [{"state": "COMPLETED", "source_id": "source",
                "outputs": {"canonical_evidence": "human"}}]}
            path.write_text(json.dumps(record))
            for output in ("topic_review_drafts", "topic_review_package", "reviewed_topics", "package_dir"):
                with self.subTest(output=output), self.assertRaisesRegex(ValueError, "inputs changed"):
                    bridge._record_review_outputs(root, run_id, "source", {output: "bound-to-machine"},
                        expected_outputs={"canonical_evidence": "machine"})
                self.assertEqual(json.loads(path.read_text()), record)
            bridge._record_review_outputs(root, run_id, "source", {"topic_review_drafts": "bound-to-human"},
                expected_outputs={"canonical_evidence": "human"})

    def test_topic_preparation_cannot_publish_after_concurrent_evidence_upgrade(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); (root / "runs").mkdir()
            run_id = "urn:integra:run:" + str(uuid.uuid4())
            path = root / "runs" / (run_id.split(":")[-1] + ".json")
            record = {"state": "COMPLETED", "source_results": [{"state": "COMPLETED", "source_id": "source",
                "outputs": {"canonical_evidence": "machine", "topics": "topics"}}]}
            path.write_text(json.dumps(record))
            def prepare(*args, **kwargs):
                self.assertEqual(kwargs["canonical_evidence_path"], "machine")
                bridge._record_review_outputs(root, run_id, "source", {"canonical_evidence": "human"})
                return {"topic_drafts_path": "stale-drafts"}
            with patch.object(bridge, "_review_inputs", return_value={"project_dir": root, "source_id": "source"}), \
                 patch.object(bridge, "prepare_topic_review_input", side_effect=prepare):
                with self.assertRaisesRegex(ValueError, "inputs changed"):
                    bridge._prepare_topic_review(root, {"run_id": run_id})
            outputs = json.loads(path.read_text())["source_results"][0]["outputs"]
            self.assertEqual(outputs["canonical_evidence"], "human")
            self.assertNotIn("topic_review_drafts", outputs)

    def test_human_upgrade_rejects_dependents_before_semantic_component_invocation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); (root / "runs").mkdir()
            run_id = "urn:integra:run:" + str(uuid.uuid4())
            path = root / "runs" / (run_id.split(":")[-1] + ".json")
            record = {"state": "COMPLETED", "source_results": [{"state": "COMPLETED", "source_id": "source",
                "outputs": {"canonical_evidence": "machine", "reviewed_topics": "reviewed"}}]}
            path.write_text(json.dumps(record))
            with patch.object(bridge, "_review_inputs", return_value={"project_dir": root, "source_id": "source"}), \
                 patch.object(bridge, "apply_human_transcript_review") as apply:
                with self.assertRaisesRegex(ValueError, "dependent review results"):
                    bridge._apply_transcript_review(root, {"run_id": run_id, "reviewer_id": "tester", "acknowledged": True})
                apply.assert_not_called()
            self.assertEqual(json.loads(path.read_text()), record)

    def test_machine_pointer_cannot_replace_reviewed_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); (root / "runs").mkdir()
            run_id = "urn:integra:run:" + str(uuid.uuid4())
            path = root / "runs" / (run_id.split(":")[-1] + ".json")
            record = {"state": "COMPLETED", "source_results": [{"state": "COMPLETED", "source_id": "source",
                       "outputs": {"canonical_evidence": "human", "canonical_knowledge": "reviewed"}}]}
            path.write_text(json.dumps(record))
            with self.assertRaisesRegex(ValueError, "cannot be replaced"):
                bridge._record_review_outputs(root, run_id, "source", {"canonical_evidence": "machine"}, preserve_existing_evidence=True)
            self.assertEqual(json.loads(path.read_text()), record)

    def test_machine_evidence_operation_is_native_and_bridge_allowed(self):
        self.assertIn("create-machine-evidence", bridge.OPERATIONS)
        source = (ROOT / "macos/IntegraApp.swift").read_text()
        self.assertIn('"create-machine-evidence"', source.split("guard allowed.contains")[0])
        self.assertIn('bridge.json("create-machine-evidence"', source)

    def test_evidence_replacement_cannot_retain_stale_dependents(self):
        for dependent in ("topic_review_drafts", "topic_review_package", "topic_review_decisions",
                          "reviewed_topics", "canonical_knowledge", "package_dir"):
            with self.subTest(dependent=dependent), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary); (root / "runs").mkdir()
                run_id = "urn:integra:run:" + str(uuid.uuid4())
                path = root / "runs" / (run_id.split(":")[-1] + ".json")
                record = {"state": "COMPLETED", "source_results": [{"state": "COMPLETED", "source_id": "source",
                    "outputs": {"canonical_evidence": "machine", dependent: "bound-to-machine"}}]}
                path.write_text(json.dumps(record))
                with self.assertRaisesRegex(ValueError, "dependent review results"):
                    bridge._record_review_outputs(root, run_id, "source", {"canonical_evidence": "human"})
                self.assertEqual(json.loads(path.read_text()), record)
                bridge._record_review_outputs(root, run_id, "source", {"canonical_evidence": "machine"})
                self.assertEqual(json.loads(path.read_text()), record)

    def test_evidence_can_be_upgraded_before_dependents_exist(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); (root / "runs").mkdir()
            run_id = "urn:integra:run:" + str(uuid.uuid4())
            path = root / "runs" / (run_id.split(":")[-1] + ".json")
            path.write_text(json.dumps({"state": "COMPLETED", "source_results": [{"state": "COMPLETED",
                "source_id": "source", "outputs": {"canonical_evidence": "machine"}}]}))
            bridge._record_review_outputs(root, run_id, "source", {"canonical_evidence": "human"})
            self.assertEqual(json.loads(path.read_text())["source_results"][0]["outputs"]["canonical_evidence"], "human")

    def test_page_selection_is_plan_bound_and_adds_real_ocr_dependency(self):
        source = {"source_id": "pdf", "source_type": "PDF", "kind": "DOCUMENT", "input": "/fixture.pdf",
                  "display_name": "fixture.pdf", "properties": {"ocr_status": "NOT_REQUIRED"}}
        with patch("integra_core.capabilities.booktext_preflight", return_value={"state": "READY"}):
            first = build_plan([{**source, "booktext_pages": "1"}], ["document_text"])
            second = build_plan([{**source, "booktext_pages": "2"}], ["document_text"])
            self.assertNotEqual(first["plan_id"], second["plan_id"])
            self.assertIn("ocr", [stage["id"] for stage in first["stages"]])
            with self.assertRaises(ValueError):
                build_plan([{**source, "booktext_pages": "0"}], ["document_text"])
        with patch("integra_core.capabilities.booktext_preflight", side_effect=ValueError("missing")):
            with self.assertRaisesRegex(ValueError, "dependency"):
                build_plan([{**source, "booktext_pages": "1"}], ["document_text"])
