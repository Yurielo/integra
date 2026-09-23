"""The Process bridge records Topic review without a Knowledge transition."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "macos" / "Resources" / "bridge.py"


@unittest.skipUnless(os.environ.get("INTEGRA_TEST_SEMINARTEXT_CHECKOUT"),
                     "requires exact pinned SeminarText checkout")
class ProcessTopicReviewBridgeTests(unittest.TestCase):
    def test_real_process_bridge_binds_run_and_persists_no_knowledge_output(self):
        with tempfile.TemporaryDirectory() as directory:
            app = Path(directory) / "app"; token = uuid.uuid4()
            project_id = f"urn:integra:project:{token}"; run_id = f"urn:integra:run:{uuid.uuid4()}"
            source_id = f"urn:integra:source:{uuid.uuid4()}"; job_id = f"urn:integra:job:{uuid.uuid4()}"
            project = app / "projects" / str(token)
            (project / "sources").mkdir(parents=True); (project / "artifacts").mkdir(); (project / "runs").mkdir()
            (project / "sources/source.mp4").write_bytes(b"owned synthetic fixture")
            words = [f"слово{index}" for index in range(100)]
            (project / "artifacts/transcript.txt").write_text(" ".join(words), encoding="utf-8")
            (project / "artifacts/timeline.json").write_text(json.dumps({"model": {"id": "x", "revision": "x", "weights_sha256": "0" * 64}, "aligner": {"name": "x", "version": "1"}, "words": [{"text": word, "start_seconds": index + .1, "end_seconds": index + .8, "alignment_status": "ALIGNED"} for index, word in enumerate(words)]}), encoding="utf-8")
            (project / "artifacts/topics.json").write_text(json.dumps({"component": "seminartext", "topics": [{"title": "Первая", "summary": "s1", "start_seconds": .1, "end_seconds": 49.8, "semantic_status": "REVIEW_REQUIRED"}, {"title": "Вторая", "summary": "s2", "start_seconds": 50.1, "end_seconds": 99.8, "semantic_status": "REVIEW_REQUIRED"}]}, ensure_ascii=False), encoding="utf-8")
            (project / "project.json").write_text(json.dumps({"project_id": project_id, "name": "Topic", "status": "READY"}))
            (project / "jobs.json").write_text(json.dumps({"jobs": [{"job_id": job_id, "source_id": source_id, "owned_path": str(project / "sources/source.mp4")}]}))
            outputs = {key: str(project / "artifacts" / value) for key, value in {"transcript": "transcript.txt", "word_timeline": "timeline.json", "topics": "topics.json"}.items()}
            record = {"run_id": run_id, "state": "COMPLETED", "source_results": [{"source_id": source_id, "state": "COMPLETED", "job_id": job_id, "outputs": outputs}]}
            run_path = project / "runs" / (run_id.removeprefix("urn:integra:run:") + ".json")
            run_path.write_text(json.dumps(record))
            environment = dict(os.environ, INTEGRA_APP_DATA_ROOT=str(app), PYTHONDONTWRITEBYTECODE="1",
                INTEGRA_SEMINARTEXT_CHECKOUT=os.environ["INTEGRA_TEST_SEMINARTEXT_CHECKOUT"])
            request = {"project_id": project_id, "run_id": run_id, "source_id": source_id}
            def call(operation, payload):
                completed = subprocess.run(["python3", str(BRIDGE), operation], input=json.dumps(payload), text=True, capture_output=True, env=environment)
                if completed.returncode:
                    raise AssertionError(completed.stderr + completed.stdout)
                return json.loads(completed.stdout)["result"]
            package = call("prepare-process-topic-review", request)
            self.assertEqual(package["status"], "PROCESS_TOPIC_REVIEW_REQUIRED")
            decisions = [{"topic_id": topic["id"], "action": "RENAME" if index == 0 else "ACCEPT", "reason": "bridge fixture", "new_title": "Переименована" if index == 0 else None, "new_summary": "Изменена" if index == 0 else None} for index, topic in enumerate(package["topics"])]
            applied = call("apply-process-topic-review", request | {"expected_package_sha256": package["package_sha256"], "decisions": decisions})
            self.assertEqual(applied["status"], "PROCESS_REVIEWED_TOPICS_CREATED")
            persisted = json.loads(run_path.read_text())["source_results"][0]["outputs"]
            self.assertEqual(set(persisted) & {"canonical_evidence", "canonical_knowledge"}, set())
            self.assertTrue(Path(persisted["process_reviewed_topics"]).is_file())
            self.assertTrue(Path(persisted["process_topic_review_receipt"]).is_file())
            ledger = json.loads(Path(persisted["process_topic_review_decisions"]).read_text())
            self.assertEqual(ledger["reviewer"], {"actor_type": "product_owner", "actor_id": "integra-process-local-human"})


if __name__ == "__main__":
    unittest.main()
