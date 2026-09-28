import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from integra_core.topic_translation_runtime import load_topic_translation, translate_topics


class TopicTranslationRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(); self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.topics = self.root / "topics.json"
        self.original = {
            "component": "seminartext", "topic_detail": {"requested": "auto", "executed": "auto"},
            "topics": [{"title": "Первая тема", "summary": "Первое краткое описание", "semantic_status": "REVIEW_REQUIRED",
                        "start_seconds": 0, "end_seconds": 10, "start_segment_id": 1}],
        }
        self.topics.write_text(json.dumps(self.original, ensure_ascii=False), encoding="utf-8")
        self.runtime = {"component": "videotext", "commit_sha": "pin", "adapter_sha256": "adapter", "model": "qwen3:8b"}

    def _translated(self, _srt, output, *, target, runtime):
        value = {"component": "videotext", "capability": "translation", "source_language": "ru", "target_language": target,
                 "model": runtime["model"], "issues": [], "cues": [
                     {"id": 1, "text": "First topic"}, {"id": 2, "text": "First brief summary"},
                 ]}
        output.write_text(json.dumps(value), encoding="utf-8"); return value

    def test_translates_only_text_and_preserves_source_structure(self):
        target = self.root / "translated_topics.json"
        with patch("integra_core.topic_translation_runtime.translate_videotext", side_effect=self._translated) as translated:
            result = translate_topics(self.topics, target, target_language="en", runtime=self.runtime)
        translated.assert_called_once()
        self.assertEqual(json.loads(self.topics.read_text(encoding="utf-8")), self.original)
        self.assertEqual(result["topic_detail"], self.original["topic_detail"])
        self.assertEqual(result["translations"], [{"topic_id": result["translations"][0]["topic_id"], "title": "First topic", "summary": "First brief summary"}])
        self.assertTrue(target.is_file())
        self.assertEqual(load_topic_translation(self.topics, target)["translations"], result["translations"])

    def test_rejects_partial_or_source_text_results_without_writing_output(self):
        target = self.root / "translated_topics.json"
        def invalid(_srt, output, *, target, runtime):
            value = self._translated(_srt, output, target=target, runtime=runtime)
            value["issues"] = [{"cue_id": 1}]
            output.write_text(json.dumps(value), encoding="utf-8"); return value
        with patch("integra_core.topic_translation_runtime.translate_videotext", side_effect=invalid), \
             self.assertRaisesRegex(ValueError, "complete verified"):
            translate_topics(self.topics, target, target_language="en", runtime=self.runtime)
        self.assertFalse(target.exists())

    def test_rejects_unsupported_target_before_provider_execution(self):
        with patch("integra_core.topic_translation_runtime.translate_videotext") as translated, \
             self.assertRaisesRegex(ValueError, "unsupported"):
            translate_topics(self.topics, self.root / "output.json", target_language="ru", runtime=self.runtime)
        translated.assert_not_called()

    def test_refuses_to_overwrite_or_reopen_a_tampered_translation(self):
        target = self.root / "translated_topics.json"
        target.write_text("{}", encoding="utf-8")
        with patch("integra_core.topic_translation_runtime.translate_videotext") as translated, \
             self.assertRaisesRegex(ValueError, "already exists"):
            translate_topics(self.topics, target, target_language="en", runtime=self.runtime)
        translated.assert_not_called()
        with self.assertRaisesRegex(ValueError, "does not match"):
            load_topic_translation(self.topics, target)


if __name__ == "__main__":
    unittest.main()
