"""Excel #24: persisted Topic summaries remain a normal Process result."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import uuid

from integra_core.seminartext_topic_review_runtime import present_machine_process_topics


ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "macos" / "Resources" / "bridge.py"


def topic_payload(summary="Кратко объясняется практическое применение метода.", detail=None):
    payload = {
        "schema_version": "1.0", "component": "seminartext", "topics": [{
            "title": "Практическое применение метода", "summary": summary,
            "start_seconds": 12.5, "end_seconds": 42.0,
            "start_segment_id": 7, "evidence_start_id": 7,
            "evidence_end_id": 18, "semantic_status": "REVIEW_REQUIRED",
        }],
    }
    if detail is not None:
        payload["topic_detail"] = {"requested": detail, "executed": detail}
    return payload


class ProcessTopicSummaryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name) / "project"
        (self.project / "artifacts").mkdir(parents=True)
        self.topics = self.project / "artifacts" / "topics.json"
        self.topics.write_text(json.dumps(topic_payload(), ensure_ascii=False), encoding="utf-8")
        self.source_id = "urn:integra:source:topic-summary-fixture"

    def test_machine_summary_is_real_source_content_with_bound_span(self):
        result = present_machine_process_topics(
            self.project, source_id=self.source_id, topics_path=self.topics,
        )
        self.assertEqual(result["status"], "PROCESS_MACHINE_TOPICS")
        self.assertEqual(result["source_id"], self.source_id)
        self.assertFalse(result["automatic_acceptance"])
        self.assertEqual(result["topics_sha256"], hashlib.sha256(self.topics.read_bytes()).hexdigest())
        topic = result["topics"][0]
        self.assertEqual(topic["title"], "Практическое применение метода")
        self.assertEqual(topic["summary"], "Кратко объясняется практическое применение метода.")
        self.assertEqual((topic["start_seconds"], topic["end_seconds"]), (12.5, 42.0))
        self.assertEqual(topic["source_span"], {
            "start_segment_id": 7, "evidence_start_id": 7, "evidence_end_id": 18,
        })

    def test_missing_source_summary_fails_closed_without_a_title_fallback(self):
        self.topics.write_text(json.dumps(topic_payload(summary=""), ensure_ascii=False), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "no usable source summary"):
            present_machine_process_topics(self.project, source_id=self.source_id, topics_path=self.topics)

    def test_bridge_returns_persisted_summary_without_preparing_or_regenerating_topics(self):
        app = Path(self.temporary.name) / "app"
        token = uuid.uuid4()
        project_id = f"urn:integra:project:{token}"
        run_id = f"urn:integra:run:{uuid.uuid4()}"
        source_id = f"urn:integra:source:{uuid.uuid4()}"
        job_id = f"urn:integra:job:{uuid.uuid4()}"
        project = app / "projects" / str(token)
        artifact = project / "artifacts"
        (project / "sources").mkdir(parents=True)
        artifact.mkdir(); (project / "runs").mkdir()
        media = project / "sources" / "source.mp4"; media.write_bytes(b"owned fixture")
        transcript = artifact / "transcript.txt"; transcript.write_text("Текст", encoding="utf-8")
        timeline = artifact / "timeline.json"; timeline.write_text('{"words": []}', encoding="utf-8")
        topics = artifact / "topics.json"; topics.write_text(json.dumps(topic_payload(), ensure_ascii=False), encoding="utf-8")
        (project / "project.json").write_text(json.dumps({"project_id": project_id, "name": "Topics", "status": "READY"}))
        (project / "jobs.json").write_text(json.dumps({"jobs": [{"job_id": job_id, "source_id": source_id, "owned_path": str(media)}]}))
        run = {
            "run_id": run_id, "state": "COMPLETED", "source_results": [{
                "source_id": source_id, "state": "COMPLETED", "job_id": job_id,
                "outputs": {"transcript": str(transcript), "word_timeline": str(timeline), "topics": str(topics)},
            }],
        }
        (project / "runs" / f"{run_id.rsplit(':', 1)[-1]}.json").write_text(json.dumps(run), encoding="utf-8")
        environment = {"INTEGRA_APP_DATA_ROOT": str(app), "PYTHONDONTWRITEBYTECODE": "1"}
        response = subprocess.run(
            ["python3", str(BRIDGE), "process-topics"],
            input=json.dumps({"project_id": project_id, "run_id": run_id, "source_id": source_id}),
            text=True, capture_output=True, env=environment, check=False,
        )
        self.assertEqual(response.returncode, 0, response.stderr + response.stdout)
        result = json.loads(response.stdout)["result"]
        self.assertEqual(result["status"], "PROCESS_MACHINE_TOPICS")
        self.assertEqual(result["topics"][0]["summary"], topic_payload()["topics"][0]["summary"])
        self.assertEqual(result["topic_detail"], {"status": "UNAVAILABLE_LEGACY"})
        self.assertEqual(json.loads(topics.read_text(encoding="utf-8")), topic_payload())

    def test_bridge_returns_bound_detail_provenance_and_rejects_corruption(self):
        app = Path(self.temporary.name) / "app"
        token = uuid.uuid4(); project_id = f"urn:integra:project:{token}"
        run_id = f"urn:integra:run:{uuid.uuid4()}"; source_id = f"urn:integra:source:{uuid.uuid4()}"
        job_id = f"urn:integra:job:{uuid.uuid4()}"; project = app / "projects" / str(token)
        artifact = project / "artifacts"; (project / "sources").mkdir(parents=True); artifact.mkdir(); (project / "runs").mkdir()
        media = project / "sources" / "source.mp4"; media.write_bytes(b"owned fixture")
        transcript = artifact / "transcript.txt"; transcript.write_text("Текст", encoding="utf-8")
        timeline = artifact / "timeline.json"; timeline.write_text('{"words": []}', encoding="utf-8")
        topics = artifact / "topics.json"; topics.write_text(json.dumps(topic_payload(detail="high"), ensure_ascii=False), encoding="utf-8")
        (project / "project.json").write_text(json.dumps({"project_id": project_id, "name": "Topics", "status": "READY"}))
        (project / "jobs.json").write_text(json.dumps({"jobs": [{"job_id": job_id, "source_id": source_id, "owned_path": str(media)}]}))
        run = {"run_id": run_id, "state": "COMPLETED", "source_results": [{"source_id": source_id, "state": "COMPLETED", "job_id": job_id, "outputs": {"transcript": str(transcript), "word_timeline": str(timeline), "topics": str(topics)}}]}
        (project / "runs" / f"{run_id.rsplit(':', 1)[-1]}.json").write_text(json.dumps(run), encoding="utf-8")
        environment = {"INTEGRA_APP_DATA_ROOT": str(app), "PYTHONDONTWRITEBYTECODE": "1"}
        response = subprocess.run(["python3", str(BRIDGE), "process-topics"], input=json.dumps({"project_id": project_id, "run_id": run_id, "source_id": source_id}), text=True, capture_output=True, env=environment)
        self.assertEqual(response.returncode, 0, response.stderr + response.stdout)
        self.assertEqual(json.loads(response.stdout)["result"]["topic_detail"], {"requested": "high", "executed": "high"})
        topics.write_text(json.dumps(topic_payload(detail="invented"), ensure_ascii=False), encoding="utf-8")
        rejected = subprocess.run(["python3", str(BRIDGE), "process-topics"], input=json.dumps({"project_id": project_id, "run_id": run_id, "source_id": source_id}), text=True, capture_output=True, env=environment)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn("detail provenance", rejected.stdout)


if __name__ == "__main__":
    unittest.main()
