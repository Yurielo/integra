"""Actual pinned SeminarText machine Evidence; all content is synthetic."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from integra_core import seminartext_evidence_runtime as runtime

ROOT = Path(__file__).resolve().parents[1]
CHECKOUT = ROOT / ".runtime-components/seminartext-pinned"


class MachineEvidenceIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name) / "project"
        self.project.mkdir()
        self.media = self.project / "source.wav"
        self.media.write_bytes(b"synthetic media fixture; alignment is supplied, no ASR")
        self.text = self.project / "transcript.txt"
        self.text.write_text("Раз проверка\n", encoding="utf-8")
        self.timeline = self.project / "timeline.json"
        self.timeline.write_text(json.dumps({"model": {"id": "test", "revision": "fixture",
            "weights_sha256": "0" * 64}, "aligner": {"name": "fixture", "version": "1"}, "words": [
            {"text": "Раз", "start_seconds": .1, "end_seconds": .3, "score": 1, "alignment_status": "ALIGNED"},
            {"text": "проверка", "start_seconds": .4, "end_seconds": .7, "score": 1, "alignment_status": "ALIGNED"}]}), encoding="utf-8")
        self.args = dict(source_id="urn:integra:source:machine-test", media_path=str(self.media),
            transcript_path=str(self.text), word_timeline_path=str(self.timeline))
        self.environment = patch.dict(os.environ, {"INTEGRA_SEMINARTEXT_CHECKOUT": str(CHECKOUT),
            "PYTHONPATH": os.environ.get("INTEGRA_TEST_REVIEW_PYTHONPATH", str(ROOT / ".runtime-components/review-python")),
            "PYTHONDONTWRITEBYTECODE": "1"})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def create(self):
        return runtime.create_machine_evidence(self.project, **self.args)

    @unittest.skipUnless((CHECKOUT / ".git").exists(), "requires pinned SeminarText checkout")
    def test_real_component_candidate_assurance_and_idempotency(self):
        before = self.text.read_bytes()
        result = self.create()
        self.assertEqual(result, self.create())
        self.assertEqual(result["decision"], "MACHINE_EVIDENCE_UNVERIFIED")
        self.assertIsNone(result["reviewer_id"])
        self.assertFalse(result["automatic_acceptance"])
        bundle = json.loads(Path(result["seminartext"]["canonical_evidence_path"]).read_text())
        revision = bundle["transcript_revisions"][0]
        self.assertEqual(revision["authority"], "candidate")
        self.assertEqual(revision["transcript_provenance"]["verification_state"], "machine_unverified")
        self.assertIsNone(revision["transcript_provenance"]["reviewer"])
        self.assertEqual(revision["transcript_provenance"]["verification_ranges"], [])
        self.assertEqual(self.text.read_bytes(), before)
        self.assertFalse(list(self.project.rglob("decisions.json")))
        self.assertFalse(list(self.project.rglob("canonical_knowledge.json")))
        topics = self.project / "topics.json"
        topics.write_text(json.dumps({"component": "seminartext", "topics": [{"semantic_status": "REVIEW_REQUIRED",
            "title": "Тема", "summary": "Черновик", "start_seconds": .1, "end_seconds": .7}]}))
        prepared = runtime.prepare_topic_review_input(self.project, source_id=self.args["source_id"],
            canonical_evidence_path=result["seminartext"]["canonical_evidence_path"], topics_path=str(topics))
        self.assertEqual(prepared["status"], "REVIEW_REQUIRED")
        from integra_core.seminartext_topic_review_runtime import prepare_topic_review
        review = prepare_topic_review(self.project, source_id=self.args["source_id"],
            canonical_evidence_path=result["seminartext"]["canonical_evidence_path"], topics_path=str(topics))
        self.assertTrue(review["topics"])
        self.assertIn("machine_unverified", Path(review["package_path"]).read_text())
        self.assertFalse(list(self.project.rglob("decisions.json")))

    @unittest.skipUnless((CHECKOUT / ".git").exists(), "requires pinned SeminarText checkout")
    def test_source_change_during_component_work_never_publishes(self):
        original = runtime._invoke
        def mutate(*args):
            result = original(*args)
            if args[1] == "evidence-check":
                self.text.write_text("changed during processing")
            return result
        with patch.object(runtime, "_invoke", side_effect=mutate):
            with self.assertRaisesRegex(ValueError, "inputs changed"):
                self.create()
        self.assertFalse(list(self.project.rglob("result.json")))

    def test_timeline_change_after_parse_never_binds_new_hash_to_old_alignment(self):
        original = runtime._alignment
        def mutate(payload):
            aligned = original(payload)
            changed = json.loads(self.timeline.read_bytes())
            changed["words"][0]["start_seconds"] = .2
            self.timeline.write_text(json.dumps(changed), encoding="utf-8")
            return aligned
        with patch.object(runtime, "_alignment", side_effect=mutate), \
                patch.object(runtime, "_runtime_root", return_value=(CHECKOUT, "TEST")), \
                patch.object(runtime, "_invoke") as invoke:
            with self.assertRaisesRegex(ValueError, "inputs changed"):
                self.create()
            invoke.assert_not_called()
        self.assertFalse(list(self.project.rglob("result.json")))

    @unittest.skipUnless((CHECKOUT / ".git").exists(), "requires pinned SeminarText checkout")
    def test_human_verification_remains_separate(self):
        machine = self.create()
        prepared = runtime.prepare_transcript_review(self.project, **self.args)
        human = runtime.apply_human_transcript_review(self.project, **self.args,
            reviewer_id="test-reviewer", acknowledged=True, expected_request_sha256=prepared["request_sha256"])
        self.assertNotEqual(machine["seminartext"]["canonical_evidence_path"], human["seminartext"]["canonical_evidence_path"])
        self.assertEqual(self.create(), machine)

    @unittest.skipUnless((CHECKOUT / ".git").exists(), "requires pinned SeminarText checkout")
    def test_changed_bundle_fails_closed(self):
        result = self.create()
        Path(result["seminartext"]["canonical_evidence_path"]).write_text("{}")
        with self.assertRaisesRegex(ValueError, "bundle changed"):
            self.create()

    @unittest.skipUnless((CHECKOUT / ".git").exists(), "requires pinned SeminarText checkout")
    def test_interrupted_component_leaves_no_published_result_and_retry_works(self):
        with patch.object(runtime, "_invoke", side_effect=ValueError("test interruption")):
            with self.assertRaisesRegex(ValueError, "test interruption"):
                self.create()
        self.assertFalse(list(self.project.rglob("result.json")))
        self.assertEqual(self.create()["status"], "EVIDENCE_CREATED")

    @unittest.skipUnless((CHECKOUT / ".git").exists(), "requires pinned SeminarText checkout")
    def test_mismatch_between_text_and_alignment_never_publishes(self):
        self.text.write_text("Другая расшифровка\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.create()
        self.assertFalse(list(self.project.rglob("result.json")))

    def test_external_input_rejected_before_component(self):
        outside = Path(self.temporary.name) / "outside.txt"
        outside.write_text("external")
        self.args["transcript_path"] = str(outside)
        with self.assertRaisesRegex(ValueError, "owned"):
            self.create()

    def test_output_symlink_rejected(self):
        outside = Path(self.temporary.name) / "outside"
        outside.mkdir()
        (self.project / "evidence").symlink_to(outside, target_is_directory=True)
        with patch.object(runtime, "_runtime_root", return_value=(CHECKOUT, "TEST")):
            with self.assertRaisesRegex(ValueError, "symlinks"):
                self.create()
        self.assertEqual(list(outside.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
