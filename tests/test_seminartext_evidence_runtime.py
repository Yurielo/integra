import json
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from integra_core.seminartext_evidence_runtime import (
    apply_human_transcript_review,
    prepare_transcript_review,
    prepare_topic_review_input,
)


ROOT = Path(__file__).resolve().parents[1]


class SeminarTextEvidenceRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.project = Path(self.temporary.name) / "project"
        self.project.mkdir()
        self.media = self.project / "source.mp4"; self.media.write_bytes(b"real owned media")
        self.transcript = self.project / "transcript.txt"; self.transcript.write_text("Раз проверка\n", encoding="utf-8")
        self.timeline = self.project / "word_timeline.json"
        self.timeline.write_text(json.dumps({
            "capability": "word_timeline",
            "model": {"id": "fixture-model", "revision": "fixture-revision", "weights_sha256": "0" * 64},
            "aligner": {"name": "fixture-alignment-service", "version": "1.0.0"},
            "words": [
                {"text": "Раз", "start_seconds": 0.1, "end_seconds": 0.3, "score": 1.0, "alignment_status": "ALIGNED"},
                {"text": "проверка", "start_seconds": 0.35, "end_seconds": 0.75, "score": 1.0, "alignment_status": "ALIGNED"},
            ],
        }, ensure_ascii=False), encoding="utf-8")
        self.previous = os.environ.get("INTEGRA_SEMINARTEXT_CHECKOUT")
        os.environ["INTEGRA_SEMINARTEXT_CHECKOUT"] = str(ROOT / ".runtime-components" / "seminartext-pinned")

    def tearDown(self):
        if self.previous is None:
            os.environ.pop("INTEGRA_SEMINARTEXT_CHECKOUT", None)
        else:
            os.environ["INTEGRA_SEMINARTEXT_CHECKOUT"] = self.previous
        self.temporary.cleanup()

    def test_prepare_requires_review_and_creates_no_canonical_evidence(self):
        request = prepare_transcript_review(
            self.project, source_id="urn:integra:source:fixture", media_path=str(self.media),
            transcript_path=str(self.transcript), word_timeline_path=str(self.timeline),
        )
        self.assertEqual(request["status"], "REVIEW_REQUIRED")
        self.assertFalse(request["automatic_acceptance"])
        self.assertTrue(Path(request["review_request_path"]).is_file())
        self.assertFalse((self.project / "review" / "transcript-evidence" / "evidence").exists())

    def test_apply_requires_explicit_acknowledgement(self):
        with self.assertRaisesRegex(ValueError, "acknowledgement"):
            apply_human_transcript_review(
                self.project, source_id="urn:integra:source:fixture", media_path=str(self.media),
                transcript_path=str(self.transcript), word_timeline_path=str(self.timeline),
                reviewer_id="test-reviewer", acknowledged=False,
            )

    @unittest.skipUnless((ROOT / ".runtime-components/seminartext-pinned/.git").exists(), "requires pinned SeminarText checkout")
    def test_apply_uses_pinned_component_after_explicit_test_decision(self):
        prepared = prepare_transcript_review(
            self.project, source_id="urn:integra:source:fixture", media_path=str(self.media),
            transcript_path=str(self.transcript), word_timeline_path=str(self.timeline))
        result = apply_human_transcript_review(
            self.project, source_id="urn:integra:source:fixture", media_path=str(self.media),
            transcript_path=str(self.transcript), word_timeline_path=str(self.timeline),
            reviewer_id="synthetic-test-reviewer", acknowledged=True,
            expected_request_sha256=prepared["request_sha256"],
        )
        self.assertEqual(result["status"], "EVIDENCE_CREATED")
        self.assertEqual(result["decision"], "HUMAN_CONFIRMED_WHOLE_TRANSCRIPT")
        bundle = Path(result["seminartext"]["canonical_evidence_path"])
        self.assertTrue(bundle.is_file())
        payload = json.loads(bundle.read_text(encoding="utf-8"))
        self.assertEqual(payload["artifact_type"], "seminartext.canonical_evidence")
        self.assertEqual(payload["transcript_revisions"][0]["authority"], "authoritative")
        topics = self.project / "topics.json"
        topics.write_text(json.dumps({"component": "seminartext", "topics": [{
            "semantic_status": "REVIEW_REQUIRED", "title": "Тема", "summary": "Черновик",
            "start_seconds": 0.1, "end_seconds": 0.75}]}), encoding="utf-8")
        reviewed = prepare_topic_review_input(self.project, source_id="urn:integra:source:fixture",
            canonical_evidence_path=str(bundle), topics_path=str(topics))
        self.assertEqual(reviewed["topic_count"], 1)

    def test_changed_transcript_cannot_be_accepted_with_previous_confirmation(self):
        prepared = prepare_transcript_review(self.project, source_id="urn:integra:source:fixture",
            media_path=str(self.media), transcript_path=str(self.transcript), word_timeline_path=str(self.timeline))
        self.transcript.write_text("Изменённый текст", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "artifact changed"):
            apply_human_transcript_review(self.project, source_id="urn:integra:source:fixture",
                media_path=str(self.media), transcript_path=str(self.transcript), word_timeline_path=str(self.timeline),
                reviewer_id="test-reviewer", acknowledged=True, expected_request_sha256=prepared["request_sha256"])
        self.assertFalse(list(self.project.glob("review/**/seminartext-project")))

    @unittest.skipUnless((ROOT / ".runtime-components/seminartext-pinned/.git").exists(), "requires pinned SeminarText checkout")
    def test_component_failure_can_be_retried_without_accepting_partial_evidence(self):
        arguments = dict(source_id="urn:integra:source:fixture", media_path=str(self.media),
            transcript_path=str(self.transcript), word_timeline_path=str(self.timeline))
        prepared = prepare_transcript_review(self.project, **arguments)
        confirmation = dict(reviewer_id="test-reviewer", acknowledged=True,
            expected_request_sha256=prepared["request_sha256"])
        with patch("integra_core.seminartext_evidence_runtime._invoke", side_effect=ValueError("injected interruption")):
            with self.assertRaisesRegex(ValueError, "injected interruption"):
                apply_human_transcript_review(self.project, **arguments, **confirmation)
        self.assertFalse(list(self.project.glob("review/**/review_result.json")))
        result = apply_human_transcript_review(self.project, **arguments, **confirmation)
        self.assertEqual(result["status"], "EVIDENCE_CREATED")

    def test_binds_real_review_required_topic_drafts_to_canonical_evidence(self):
        evidence_path = self.project / "canonical_evidence.json"
        evidence_path.write_text(json.dumps({
            "artifact_type": "seminartext.canonical_evidence",
            "project": {"id": "project_fixture", "title": "Fixture"},
            "sources": [{"id": "source_fixture", "source_registry_id": "urn:integra:source:fixture"}],
            "transcript_revisions": [{"id": "transcript_fixture_r1", "source_id": "source_fixture"}],
            "words": [
                {"id": "transcript_fixture_r1:word:000000", "source_id": "source_fixture", "transcript_revision_id": "transcript_fixture_r1", "sequence": 0, "start_seconds": 0.1, "end_seconds": 0.3},
                {"id": "transcript_fixture_r1:word:000001", "source_id": "source_fixture", "transcript_revision_id": "transcript_fixture_r1", "sequence": 1, "start_seconds": 0.35, "end_seconds": 0.75},
            ],
        }, ensure_ascii=False), encoding="utf-8")
        evidence_path.write_text(evidence_path.read_text().replace("source_fixture", "source_source_" + hashlib.sha256(b"urn:integra:source:fixture").hexdigest()[:24]))
        topics = self.project / "topics.json"
        topics.write_text(json.dumps({"component": "seminartext", "topics": [{
            "semantic_status": "REVIEW_REQUIRED", "title": "Проверочная тема",
            "summary": "Реальный черновик для проверки.", "start_seconds": 0.1, "end_seconds": 0.75,
        }]}, ensure_ascii=False), encoding="utf-8")
        review_input = prepare_topic_review_input(
            self.project, source_id="urn:integra:source:fixture",
            canonical_evidence_path=str(evidence_path), topics_path=str(topics),
        )
        self.assertEqual(review_input["status"], "REVIEW_REQUIRED")
        self.assertFalse(review_input["automatic_acceptance"])
        payload = json.loads(Path(review_input["topic_drafts_path"]).read_text(encoding="utf-8"))
        self.assertEqual(payload["artifact_type"], "seminartext.topic_drafts")
        self.assertEqual(payload["topics"][0]["proposed_title"], "Проверочная тема")
        self.assertEqual(payload["topics"][0]["lifecycle_status"], "REVIEW_REQUIRED")


if __name__ == "__main__":
    unittest.main()
