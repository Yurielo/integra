"""Real pinned component integration using only synthetic local test inputs."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from integra_core.seminartext_evidence_runtime import prepare_transcript_review, apply_human_transcript_review
from integra_core.seminartext_topic_review_runtime import prepare_topic_review, apply_topic_review, _choices

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless((ROOT / ".runtime-components/seminartext-pinned/seminartext_modules/human_review_workflow.py").is_file(), "requires pinned SeminarText integration checkout")
class TopicReviewRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name)
        self.environment = patch.dict(os.environ, {
            "INTEGRA_SEMINARTEXT_CHECKOUT": str(ROOT / ".runtime-components/seminartext-pinned"),
            "PYTHONPATH": str(ROOT / ".runtime-components/review-python"),
            "PYTHONDONTWRITEBYTECODE": "1",
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)
        media = self.project / "source.mp4"; media.write_bytes(b"synthetic owned media fixture")
        self.tokens = [f"слово{index}" for index in range(100)]
        text = self.project / "transcript.txt"; text.write_text(" ".join(self.tokens) + "\n", encoding="utf-8")
        timeline = self.project / "timeline.json"
        timeline.write_text(json.dumps({"model": {"id": "fixture", "revision": "fixture", "weights_sha256": "0" * 64},
            "aligner": {"name": "fixture", "version": "1"}, "words": [
            {"text": token, "start_seconds": index + 0.1, "end_seconds": index + 0.8, "score": 1.0, "alignment_status": "ALIGNED"}
            for index, token in enumerate(self.tokens)]}))
        self.source_id = "urn:integra:source:synthetic-topic-review"
        inputs = dict(source_id=self.source_id, media_path=str(media), transcript_path=str(text), word_timeline_path=str(timeline))
        request = prepare_transcript_review(self.project, **inputs)
        evidence = apply_human_transcript_review(self.project, **inputs, reviewer_id="synthetic-reviewer", acknowledged=True,
                                                expected_request_sha256=request["request_sha256"])
        self.evidence = evidence["seminartext"]["canonical_evidence_path"]
        self.topics = self.project / "topics.json"
        self.topics.write_text(json.dumps({"component": "seminartext", "topics": [
            {"title": "Первая тема", "summary": "Первая проверочная тема", "start_seconds": 0.1, "end_seconds": 49.8, "semantic_status": "REVIEW_REQUIRED"},
            {"title": "Вторая тема", "summary": "Вторая проверочная тема", "start_seconds": 50.1, "end_seconds": 99.8, "semantic_status": "REVIEW_REQUIRED"}]}))

    def prepare(self):
        return prepare_topic_review(self.project, source_id=self.source_id, canonical_evidence_path=self.evidence, topics_path=str(self.topics))

    def apply(self, package, decisions, **kwargs):
        return apply_topic_review(self.project, source_id=self.source_id, expected_package_sha256=package["package_sha256"],
                                  reviewer_id="synthetic-reviewer", decisions=decisions, **kwargs)

    def decisions(self, package):
        return [{"topic_id": item["id"], "action": "ACCEPT" if index == 0 else "REJECT", "reason": "Explicit synthetic test decision"}
                for index, item in enumerate(package["topics"])]

    def test_actual_evidence_to_package_to_explicit_decisions_to_knowledge(self):
        prepared = self.prepare()
        self.assertEqual(prepared["status"], "REVIEW_REQUIRED")
        self.assertEqual([item["quote"] for item in prepared["topics"]], [" ".join(self.tokens[:50]), " ".join(self.tokens[50:])])
        self.assertFalse(list(self.project.rglob("canonical_knowledge.json")))
        self.assertEqual(self.prepare()["package_sha256"], prepared["package_sha256"])
        result = self.apply(prepared, self.decisions(prepared))
        self.assertEqual((result["accepted"], result["rejected"]), (1, 1))
        self.assertFalse(result["automatic_acceptance"])
        knowledge = json.loads(Path(result["canonical_knowledge_path"]).read_text())
        self.assertEqual({item["status"] for item in knowledge["topics"]}, {"ACCEPTED", "REJECTED"})
        self.assertEqual(len(knowledge["review_decisions"]), 2)
        self.assertIn("Первая тема", Path(result["knowledge_markdown_path"]).read_text())
        self.assertEqual(self.apply(prepared, self.decisions(prepared)), result)

    def test_missing_or_partial_choices_never_create_knowledge(self):
        prepared = self.prepare()
        for decisions in ([], self.decisions(prepared)[:1]):
            with self.assertRaises(ValueError):
                self.apply(prepared, decisions)
        self.assertFalse(list(self.project.rglob("canonical_knowledge.json")))

    def test_changed_evidence_or_topics_rejects_stale_decision(self):
        prepared = self.prepare()
        self.topics.write_text(self.topics.read_text() + "\n")
        with self.assertRaisesRegex(ValueError, "topics changed"):
            self.apply(prepared, self.decisions(prepared))
        self.assertFalse(list(self.project.rglob("canonical_knowledge.json")))

    def test_rejects_changed_package_and_conflicting_second_decision(self):
        prepared = self.prepare()
        result = self.apply(prepared, self.decisions(prepared))
        other = self.decisions(prepared); other[0]["action"] = "REJECT"
        with self.assertRaisesRegex(ValueError, "different persisted decisions"):
            self.apply(prepared, other)
        package_path = Path(prepared["package_path"])
        package_path.write_text(package_path.read_text() + "\n")
        with self.assertRaisesRegex(ValueError, "package changed"):
            self.apply(prepared, self.decisions(prepared))
        self.assertTrue(Path(result["canonical_knowledge_path"]).exists())

    def prepare_fragments(self):
        topics = json.loads(self.topics.read_text())
        topics["topics"][0]["end_seconds"] = 10.8
        self.topics.write_text(json.dumps(topics))
        prepared = self.prepare()
        self.assertEqual(prepared["review_mode"], "EXACT_FRAGMENTS_V2")
        return prepared

    def test_arbitrary_ranges_create_real_reviewed_fragments_without_widening(self):
        canonical_bytes = Path(self.evidence).read_bytes()
        prepared = self.prepare_fragments()
        self.assertEqual(prepared["topics"][0]["quote"], " ".join(self.tokens[:11]))
        with self.assertRaisesRegex(ValueError, "exact boundaries"):
            self.apply(prepared, self.decisions(prepared))
        self.assertFalse(list(self.project.rglob("decisions.json")))
        result = self.apply(prepared, self.decisions(prepared), boundaries_acknowledged=True)
        self.assertEqual(result["status"], "REVIEWED_TOPICS_CREATED")
        self.assertNotIn("canonical_knowledge_path", result)
        self.assertFalse(list(self.project.rglob("canonical_knowledge.json")))
        self.assertEqual(Path(self.evidence).read_bytes(), canonical_bytes)
        payload = json.loads(Path(result["reviewed_topics_path"]).read_text())
        self.assertEqual(payload["artifact_type"], "seminartext.human_review_result")
        self.assertEqual(len(payload["semantic_knowledge"]), 1)
        self.assertEqual(len(payload["non_semantic_excluded"]), 1)
        self.assertEqual(payload["semantic_knowledge"][0]["word_end_sequence"], 10)
        self.assertIn(" ".join(self.tokens[:11]), Path(result["reviewed_topics_markdown_path"]).read_text())
        self.assertEqual(self.apply(prepared, self.decisions(prepared), boundaries_acknowledged=True), result)

    def test_arbitrary_ranges_all_excluded_and_failed_component_retry(self):
        prepared = self.prepare_fragments()
        decisions = self.decisions(prepared)
        for decision in decisions:
            decision["action"] = "REJECT"
        with patch("integra_core.seminartext_topic_review_runtime._invoke", side_effect=ValueError("injected V2 failure")):
            with self.assertRaisesRegex(ValueError, "injected V2 failure"):
                self.apply(prepared, decisions, boundaries_acknowledged=True)
        result = self.apply(prepared, decisions, boundaries_acknowledged=True)
        self.assertEqual((result["accepted"], result["rejected"]), (0, 2))
        payload = json.loads(Path(result["reviewed_topics_path"]).read_text())
        self.assertEqual(payload["semantic_knowledge"], [])
        self.assertFalse(list(self.project.rglob("canonical_knowledge.json")))

    def test_arbitrary_ranges_reject_changed_word_timeline(self):
        prepared = self.prepare_fragments()
        timeline = Path(self.evidence).parent / "word_timeline.json"
        timeline.write_bytes(timeline.read_bytes() + b"\n")
        with self.assertRaisesRegex(ValueError, "Word Timeline changed"):
            self.apply(prepared, self.decisions(prepared), boundaries_acknowledged=True)
        self.assertFalse(list(self.project.rglob("decisions.json")))

    def test_legacy_v1_binding_without_mode_reuses_package_and_applies(self):
        prepared = self.prepare()
        binding_path = Path(prepared["package_path"]).parent.parent / "binding.json"
        binding = json.loads(binding_path.read_text())
        del binding["review_mode"]
        binding_path.write_text(json.dumps(binding))
        self.assertEqual(self.prepare()["review_mode"], "CANONICAL_KNOWLEDGE_V1")
        result = self.apply(prepared, self.decisions(prepared))
        self.assertEqual(result["status"], "KNOWLEDGE_CREATED")
        decision_bytes = Path(result["decisions_path"]).read_bytes()
        self.assertEqual(self.prepare()["package_sha256"], prepared["package_sha256"])
        self.assertEqual(self.apply(prepared, self.decisions(prepared)), result)
        self.assertEqual(Path(result["decisions_path"]).read_bytes(), decision_bytes)

    def test_v2_binding_missing_mode_never_defaults(self):
        prepared = self.prepare_fragments()
        binding_path = Path(prepared["package_path"]).parent.parent / "binding.json"
        binding = json.loads(binding_path.read_text())
        del binding["review_mode"]
        binding_path.write_text(json.dumps(binding))
        with self.assertRaisesRegex(ValueError, "persisted review mode"):
            self.prepare()
        with self.assertRaisesRegex(ValueError, "persisted review mode"):
            self.apply(prepared, self.decisions(prepared), boundaries_acknowledged=True)
        self.assertFalse(list(self.project.rglob("decisions.json")))

    def test_all_rejected_topics_remain_rejected(self):
        prepared = self.prepare()
        decisions = self.decisions(prepared)
        for decision in decisions:
            decision["action"] = "REJECT"
        result = self.apply(prepared, decisions)
        self.assertEqual((result["accepted"], result["rejected"]), (0, 2))
        knowledge = json.loads(Path(result["canonical_knowledge_path"]).read_text())
        self.assertEqual({topic["status"] for topic in knowledge["topics"]}, {"REJECTED"})

    def test_component_failure_preserves_decision_and_allows_same_retry(self):
        prepared = self.prepare()
        with patch("integra_core.seminartext_topic_review_runtime._invoke", side_effect=ValueError("injected component failure")):
            with self.assertRaisesRegex(ValueError, "injected component failure"):
                self.apply(prepared, self.decisions(prepared))
        self.assertEqual(len(list(self.project.rglob("decisions.json"))), 1)
        self.assertFalse(list(self.project.rglob("canonical_knowledge.json")))
        result = self.apply(prepared, self.decisions(prepared))
        self.assertEqual(result["status"], "KNOWLEDGE_CREATED")


class ExplicitChoiceContractTests(unittest.TestCase):
    def test_no_default_acceptance_and_no_unknown_targets(self):
        package = {"topics": [{"id": "topic_1"}, {"id": "topic_2"}]}
        for choices in ([], [{"topic_id": "topic_1", "action": "ACCEPT", "reason": "explicit"}],
                        [{"topic_id": "unknown", "action": "ACCEPT", "reason": "explicit"}]):
            with self.assertRaises(ValueError):
                _choices(package, "test-reviewer", choices)


if __name__ == "__main__":
    unittest.main()
