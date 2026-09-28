"""Excel #22: a persisted machine Topic translation is source-bound and reusable."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import uuid
from unittest.mock import patch

from integra_core.application_runtime import read_run, translate_saved_topics


class ProcessTopicTranslationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(); self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name) / "project"
        (self.project / "artifacts").mkdir(parents=True); (self.project / "runs").mkdir()
        self.run_id = f"urn:integra:run:{uuid.uuid4()}"; self.source_id = "urn:integra:source:topics"
        self.topics = self.project / "artifacts" / "topics.json"
        self.payload = {"component": "seminartext", "topic_detail": {"requested": "high", "executed": "high"}, "topics": [{
            "title": "Русская тема", "summary": "Русское описание", "semantic_status": "REVIEW_REQUIRED",
            "start_seconds": 1, "end_seconds": 2, "start_segment_id": 4,
        }]}
        self.topics.write_text(json.dumps(self.payload, ensure_ascii=False), encoding="utf-8")
        self.run_path = self.project / "runs" / f"{self.run_id.rsplit(':', 1)[-1]}.json"
        self.run_path.write_text(json.dumps({"run_id": self.run_id, "state": "COMPLETED", "source_results": [{
            "source_id": self.source_id, "state": "COMPLETED", "source_speech_language": {"requested": "ru", "executed": "ru"},
            "outputs": {"topics": str(self.topics)},
        }]}), encoding="utf-8")
        self.runtime = {"component": "videotext", "commit_sha": "pin", "adapter_sha256": "adapter", "model": "qwen3:8b"}

    def _translate(self, _source, output, *, target, runtime):
        payload = {"component": "videotext", "capability": "translation", "source_language": "ru",
                   "target_language": target, "model": runtime["model"], "issues": [],
                   "cues": [{"id": 1, "text": "Russian topic"}, {"id": 2, "text": "Russian summary"}]}
        output.write_text(json.dumps(payload), encoding="utf-8"); return payload

    def test_persists_source_bound_translation_and_reopens_without_provider(self):
        with patch("integra_core.application_runtime.videotext_translation_preflight", return_value=self.runtime), \
             patch("integra_core.topic_translation_runtime.translate_videotext", side_effect=self._translate) as provider:
            result = translate_saved_topics(self.project, self.run_id, self.source_id)
        provider.assert_called_once()
        run = read_run(self.project, self.run_id); outputs = run["source_results"][0]["outputs"]
        self.assertEqual(result["topic_detail"], self.payload["topic_detail"])
        self.assertEqual(json.loads(self.topics.read_text(encoding="utf-8")), self.payload)
        provenance = json.loads(Path(outputs["translated_topics_provenance"]).read_text(encoding="utf-8"))
        self.assertEqual(provenance["source_id"], self.source_id)
        self.assertEqual(provenance["translated_topics_sha256"], hashlib.sha256(Path(outputs["translated_topics"]).read_bytes()).hexdigest())
        with patch("integra_core.application_runtime.videotext_translation_preflight") as preflight:
            reopened = translate_saved_topics(self.project, self.run_id, self.source_id)
        preflight.assert_not_called()
        self.assertEqual(reopened["output_sha256"], result["output_sha256"])

    def test_wrong_source_language_fails_before_provider_and_preserves_run(self):
        record = json.loads(self.run_path.read_text(encoding="utf-8"))
        record["source_results"][0]["source_speech_language"]["executed"] = "en"
        self.run_path.write_text(json.dumps(record), encoding="utf-8")
        before = self.run_path.read_bytes()
        with patch("integra_core.application_runtime.videotext_translation_preflight") as preflight, \
             self.assertRaisesRegex(ValueError, "Russian"):
            translate_saved_topics(self.project, self.run_id, self.source_id)
        preflight.assert_not_called(); self.assertEqual(self.run_path.read_bytes(), before)

    def test_reviewed_topics_remain_the_only_process_authority(self):
        record = json.loads(self.run_path.read_text(encoding="utf-8"))
        record["source_results"][0]["outputs"]["process_reviewed_topics"] = "already-reviewed"
        self.run_path.write_text(json.dumps(record), encoding="utf-8")
        with patch("integra_core.application_runtime.videotext_translation_preflight") as preflight, \
             self.assertRaisesRegex(ValueError, "after Process Topic Review"):
            translate_saved_topics(self.project, self.run_id, self.source_id)
        preflight.assert_not_called()


if __name__ == "__main__":
    unittest.main()
