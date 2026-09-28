"""Excel #22 / S15: Topic translation is an additive, source-bound result."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import uuid
from unittest.mock import patch

from integra_core.application_runtime import (
    execute_run,
    prepare_topic_translation_run,
    read_run,
)
from integra_core.topic_translation import load_topic_translation
from integra_core.user_media import atomic_json


def topic_payload() -> dict:
    return {
        "schema_version": "1.0", "component": "seminartext",
        "topic_detail": {"requested": "auto", "executed": "auto"},
        "topics": [
            {"title": "Первая тема", "summary": "Первое краткое описание.",
             "start_seconds": 1.25, "end_seconds": 12.5, "start_segment_id": 1,
             "evidence_start_id": 1, "evidence_end_id": 4, "semantic_status": "REVIEW_REQUIRED"},
            {"title": "Вторая тема", "summary": "Второе краткое описание.",
             "start_seconds": 12.5, "end_seconds": 28.0, "start_segment_id": 5,
             "evidence_start_id": 5, "evidence_end_id": 9, "semantic_status": "REVIEW_REQUIRED"},
        ],
    }


class ProcessTopicTranslationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(); self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name) / "project"
        (self.project / "artifacts").mkdir(parents=True)
        self.source_id = "urn:integra:source:topic-translation"
        self.parent_id = f"urn:integra:run:{uuid.uuid4()}"
        self.topics = self.project / "artifacts" / "topics.json"
        self.original = topic_payload()
        self.topics.write_text(json.dumps(self.original, ensure_ascii=False), encoding="utf-8")
        source = {"source_id": self.source_id, "display_name": "source.mp4", "source_type": "LOCAL_VIDEO", "kind": "MEDIA"}
        parent = {
            "run_id": self.parent_id, "state": "COMPLETED", "plan": {"sources": [source]},
            "recognition": {"requested_mode": "normal"},
            "source_speech_language": {"requested": "ru", "executed": "ru"},
            "topic_detail": {"requested": "auto"},
            "source_results": [{"source_id": self.source_id, "state": "COMPLETED", "outputs": {"topics": str(self.topics)},
                                "source_speech_language": {"requested": "ru", "executed": "ru"},
                                "topic_detail": {"requested": "auto", "executed": "auto"}}],
        }
        (self.project / "runs").mkdir()
        atomic_json(self.project / "runs" / (self.parent_id.rsplit(":", 1)[-1] + ".json"), parent)

    @staticmethod
    def _runtime():
        return {"state": "READY", "component": "videotext", "commit_sha": "pinned-video", "adapter_sha256": "adapter", "model": "qwen3:8b"}

    @staticmethod
    def _translation(_srt: Path, output: Path, *, target: str, runtime: dict):
        payload = {
            "schema_version": "1.0", "component": "videotext", "capability": "translation",
            "source_language": "ru", "target_language": target, "model": runtime["model"], "issues": [],
            "cues": [
                {"id": 1, "text": "First topic"}, {"id": 2, "text": "First short description."},
                {"id": 3, "text": "Second topic"}, {"id": 4, "text": "Second short description."},
            ],
        }
        output.write_text(json.dumps(payload), encoding="utf-8")
        return payload

    def _completed(self):
        run = prepare_topic_translation_run(self.project, self.parent_id, self.source_id)
        with patch("integra_core.topic_translation.preflight", side_effect=self._runtime), \
             patch("integra_core.topic_translation.translate", side_effect=self._translation) as provider:
            completed = execute_run(self.project, run["run_id"])
        provider.assert_called_once()
        return completed

    def test_translation_is_bound_additive_and_preserves_machine_topic_identity(self):
        completed = self._completed()
        result = completed["source_results"][0]
        outputs = result["outputs"]
        translated = json.loads(Path(outputs["topic_translation"]).read_text(encoding="utf-8"))
        provenance = json.loads(Path(outputs["topic_translation_provenance"]).read_text(encoding="utf-8"))
        self.assertEqual(json.loads(self.topics.read_text(encoding="utf-8")), self.original)
        self.assertEqual(translated["source_topics_sha256"], hashlib.sha256(self.topics.read_bytes()).hexdigest())
        self.assertEqual((translated["source_language"], translated["target_language"]), ("ru", "en"))
        self.assertEqual(translated["topic_detail"], {"requested": "auto", "executed": "auto"})
        self.assertEqual(translated["topics"][0]["topic_id"], f"machine-topic-{translated['source_topics_sha256'][:20]}-0000")
        self.assertEqual(translated["topics"][0]["original"], {"title": "Первая тема", "summary": "Первое краткое описание."})
        self.assertEqual(translated["topics"][0]["translation"], {"title": "First topic", "summary": "First short description."})
        self.assertEqual(translated["topics"][1]["source_span"], {"start_segment_id": 5, "evidence_start_id": 5, "evidence_end_id": 9})
        self.assertEqual((provenance["requested_target_language"], provenance["executed_target_language"]), ("en", "en"))
        self.assertEqual(provenance["runtime"]["commit_sha"], "pinned-video")
        self.assertTrue(Path(outputs["topic_translation_txt"]).read_text(encoding="utf-8").startswith("1.250–12.500\nFirst topic"))

    def test_reopen_reads_saved_translation_without_reinvoking_provider(self):
        completed = self._completed()
        outputs = completed["source_results"][0]["outputs"]
        parent = read_run(self.project, self.parent_id)
        original_outputs = parent["source_results"][0]["outputs"]
        with patch("integra_core.topic_translation.translate", side_effect=AssertionError("must not translate")):
            reopened = load_topic_translation(self.project, source_id=self.source_id, source_run_id=self.parent_id,
                                              source_outputs=original_outputs, outputs=outputs)
        self.assertEqual(reopened["topics"][1]["translation"]["title"], "Second topic")

    def test_damaged_binding_fails_closed_without_provider_fallback(self):
        completed = self._completed()
        outputs = completed["source_results"][0]["outputs"]
        original_outputs = read_run(self.project, self.parent_id)["source_results"][0]["outputs"]
        self.topics.write_text(json.dumps({**self.original, "topics": self.original["topics"][:1]}, ensure_ascii=False), encoding="utf-8")
        with patch("integra_core.topic_translation.translate", side_effect=AssertionError("must not translate")), \
            self.assertRaisesRegex(ValueError, "does not match|invalid topic count"):
            load_topic_translation(self.project, source_id=self.source_id, source_run_id=self.parent_id,
                                   source_outputs=original_outputs, outputs=outputs)

    def test_tampered_topic_timing_or_source_run_fails_closed(self):
        completed = self._completed()
        outputs = completed["source_results"][0]["outputs"]
        original_outputs = read_run(self.project, self.parent_id)["source_results"][0]["outputs"]
        translated_path = Path(outputs["topic_translation"])
        translated = json.loads(translated_path.read_text(encoding="utf-8"))
        translated["topics"][0]["start_seconds"] = 2.0
        translated_path.write_text(json.dumps(translated), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "does not match|invalid source binding"):
            load_topic_translation(self.project, source_id=self.source_id, source_run_id=self.parent_id,
                                   source_outputs=original_outputs, outputs=outputs)

    def test_provider_issues_cannot_publish_successful_topic_translation(self):
        run = prepare_topic_translation_run(self.project, self.parent_id, self.source_id)
        def invalid(_srt, output, *, target, runtime):
            payload = self._translation(_srt, output, target=target, runtime=runtime)
            payload["issues"] = [{"cue_id": 1, "reason_codes": ["target-language-mismatch"]}]
            output.write_text(json.dumps(payload), encoding="utf-8")
            return payload
        with patch("integra_core.topic_translation.preflight", side_effect=self._runtime), \
             patch("integra_core.topic_translation.translate", side_effect=invalid), \
             self.assertRaisesRegex(ValueError, "requires review"):
            execute_run(self.project, run["run_id"])
        failed = read_run(self.project, run["run_id"])
        self.assertEqual(failed["state"], "FAILED")
        self.assertEqual(failed["source_results"], [])
        self.assertEqual(json.loads(self.topics.read_text(encoding="utf-8")), self.original)

    def test_review_lineage_is_recorded_without_replacing_review_authority(self):
        review = self.project / "artifacts" / "reviewed.json"; review.write_text("{}", encoding="utf-8")
        receipt = self.project / "artifacts" / "receipt.json"; receipt.write_text("{}", encoding="utf-8")
        decisions = self.project / "artifacts" / "decisions.json"; decisions.write_text("{}", encoding="utf-8")
        parent_path = self.project / "runs" / (self.parent_id.rsplit(":", 1)[-1] + ".json")
        parent = json.loads(parent_path.read_text(encoding="utf-8"))
        parent["source_results"][0]["outputs"].update({"process_reviewed_topics": str(review), "process_topic_review_receipt": str(receipt), "process_topic_review_decisions": str(decisions)})
        atomic_json(parent_path, parent)
        completed = self._completed()
        translated = json.loads(Path(completed["source_results"][0]["outputs"]["topic_translation"]).read_text(encoding="utf-8"))
        self.assertEqual(translated["review_lineage"]["process_reviewed_topics_sha256"], hashlib.sha256(review.read_bytes()).hexdigest())
        self.assertEqual(json.loads(self.topics.read_text(encoding="utf-8")), self.original)


if __name__ == "__main__":
    unittest.main()
