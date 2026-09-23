"""Regression coverage for the Process-only Topic review boundary."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from integra_core.seminartext_topic_review_runtime import (
    PROCESS_TOPIC_AUTHORITY as AUTHORITY, apply_process_topic_review, prepare_process_topic_review,
)


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.environ.get("INTEGRA_TEST_SEMINARTEXT_CHECKOUT"),
                     "requires exact pinned SeminarText checkout")
class ProcessTopicReviewRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        self.environment = patch.dict(os.environ, {
            "INTEGRA_SEMINARTEXT_CHECKOUT": os.environ["INTEGRA_TEST_SEMINARTEXT_CHECKOUT"],
            "PYTHONDONTWRITEBYTECODE": "1",
        })
        self.environment.start(); self.addCleanup(self.environment.stop)
        (self.project / "source.mp4").write_bytes(b"owned synthetic fixture")
        words = [f"слово{index}" for index in range(100)]
        (self.project / "transcript.txt").write_text(" ".join(words), encoding="utf-8")
        (self.project / "timeline.json").write_text(json.dumps({
            "model": {"id": "fixture", "revision": "fixture", "weights_sha256": "0" * 64},
            "aligner": {"name": "fixture", "version": "1"},
            "words": [{"text": word, "start_seconds": index + .1, "end_seconds": index + .8,
                       "score": 1.0, "alignment_status": "ALIGNED"} for index, word in enumerate(words)],
        }), encoding="utf-8")
        (self.project / "topics.json").write_text(json.dumps({"component": "seminartext", "topics": [
            {"title": "Первая тема", "summary": "Первая", "start_seconds": .1, "end_seconds": 49.8,
             "semantic_status": "REVIEW_REQUIRED"},
            {"title": "Вторая тема", "summary": "Вторая", "start_seconds": 50.1, "end_seconds": 99.8,
             "semantic_status": "REVIEW_REQUIRED"},
        ]}, ensure_ascii=False), encoding="utf-8")
        self.args = {"source_id": "urn:integra:source:process-topic-fixture",
                     "media_path": str(self.project / "source.mp4"),
                     "transcript_path": str(self.project / "transcript.txt"),
                     "word_timeline_path": str(self.project / "timeline.json"),
                     "topics_path": str(self.project / "topics.json")}

    def test_real_pinned_contract_persists_process_review_not_knowledge(self):
        package = prepare_process_topic_review(self.project, **self.args)
        self.assertEqual(package["status"], "PROCESS_TOPIC_REVIEW_REQUIRED")
        self.assertEqual(package["authority"], AUTHORITY)
        self.assertEqual(len(package["topics"]), 2)
        decisions = [
            {"topic_id": package["topics"][0]["id"], "action": "RENAME", "reason": "fixture edit",
             "new_title": "Переименованная тема", "new_summary": "Изменённое описание"},
            {"topic_id": package["topics"][1]["id"], "action": "ACCEPT", "reason": "fixture confirm",
             "new_title": None, "new_summary": None},
        ]
        result = apply_process_topic_review(self.project, source_id=self.args["source_id"],
            expected_package_sha256=package["package_sha256"], reviewer_id="fixture-owner", decisions=decisions)
        self.assertEqual(result["status"], "PROCESS_REVIEWED_TOPICS_CREATED")
        self.assertEqual(result["actions"][package["topics"][0]["id"]], "RENAME")
        receipt = json.loads(Path(result["process_topic_review_receipt_path"]).read_text())
        self.assertEqual(receipt["authority"], AUTHORITY)
        self.assertFalse(list(self.project.rglob("canonical_knowledge.json")))
        self.assertEqual(apply_process_topic_review(self.project, source_id=self.args["source_id"],
            expected_package_sha256=package["package_sha256"], reviewer_id="fixture-owner", decisions=decisions), result)

    def test_unsupported_split_is_not_faked_by_process_v1_surface(self):
        package = prepare_process_topic_review(self.project, **self.args)
        decisions = [{"topic_id": item["id"], "action": "SPLIT", "reason": "not scoped",
                      "new_title": None, "new_summary": None} for item in package["topics"]]
        with self.assertRaisesRegex(ValueError, "unsupported Process Topic action"):
            apply_process_topic_review(self.project, source_id=self.args["source_id"],
                expected_package_sha256=package["package_sha256"], reviewer_id="fixture-owner", decisions=decisions)


if __name__ == "__main__":
    unittest.main()
