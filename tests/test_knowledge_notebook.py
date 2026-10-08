"""K1 integration over the real pinned review adapter; no provider execution."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid

from integra_core import knowledge_notebook as notebook
from integra_core.protocol import canonical_json

ROOT = Path(__file__).resolve().parents[1]
PINNED = Path(os.environ.get("INTEGRA_TEST_SEMINARTEXT_CHECKOUT", ROOT / ".runtime-components/seminartext-pinned"))


@unittest.skipUnless((PINNED / "seminartext_modules/human_review_workflow.py").is_file(), "requires pinned review runtime")
class KnowledgeNotebookTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.ids = {"project_id": f"urn:integra:project:{uuid.uuid4()}", "run_id": f"urn:integra:run:{uuid.uuid4()}", "source_id": f"urn:integra:source:{uuid.uuid4()}"}
        env = patch.dict(os.environ, {"INTEGRA_SEMINARTEXT_CHECKOUT": str(PINNED),
            "PYTHONPATH": os.environ.get("INTEGRA_TEST_REVIEW_PYTHONPATH", str(ROOT / ".runtime-components/review-python")),
            "PYTHONDONTWRITEBYTECODE": "1"})
        env.start(); self.addCleanup(env.stop)
        self.media = self.root / "source.mp4"; self.media.write_bytes(b"synthetic owned media; not native acceptance")
        self.text = self.root / "transcript.txt"; tokens = [f"слово{index}" for index in range(100)]
        self.text.write_text(" ".join(tokens) + "\n")
        self.timeline = self.root / "timeline.json"
        self.write(self.timeline, {"model": {"id": "fixture", "revision": "fixture", "weights_sha256": "0"*64},
            "aligner": {"name": "fixture", "version": "1"}, "words": [{"text": token, "start_seconds": index+.1,
            "end_seconds": index+.8, "alignment_status": "ALIGNED"} for index, token in enumerate(tokens)]})
        self.topics = self.root / "topics.json"
        self.write(self.topics, {"component": "seminartext", "topics": [
            {"title": "Тема один", "summary": "Первый фрагмент", "start_seconds": 2.1, "end_seconds": 49.8, "semantic_status": "REVIEW_REQUIRED"},
            {"title": "Тема два", "summary": "Второй фрагмент", "start_seconds": 50.1, "end_seconds": 97.8, "semantic_status": "REVIEW_REQUIRED"}]})
        job_id = f"urn:integra:job:{uuid.uuid4()}"
        self.write(self.root / "project.json", {"project_id": self.ids["project_id"], "name": "K1 test"})
        self.write(self.root / "jobs.json", {"jobs": [{"job_id": job_id, "source_id": self.ids["source_id"],
            "owned_path": str(self.media), "source_sha256": hashlib.sha256(self.media.read_bytes()).hexdigest()}]})
        (self.root / "runs").mkdir()
        self.run_file = self.root / "runs" / (self.ids["run_id"].removeprefix("urn:integra:run:") + ".json")
        self.write(self.run_file, {"run_id": self.ids["run_id"], "state": "COMPLETED", "source_results": [
            {"source_id": self.ids["source_id"], "state": "COMPLETED", "job_id": job_id, "outputs": {
                "transcript": str(self.text), "word_timeline": str(self.timeline), "topics": str(self.topics)}}]})
        self.run_before = self.run_file.read_bytes()

    def write(self, path, value): path.write_bytes(canonical_json(value) + b"\n")
    def open(self, create=False): return notebook.open_notebook(self.root, **self.ids, create=create)
    def choices(self, opened): return [{"topic_id": topic["id"], "action": "ACCEPT", "reason": "Explicit synthetic reviewer choice"} for topic in opened["topics"]]
    def save(self, opened, choices): return notebook.save_notebook(self.root, **self.ids,
        expected_state_sha256=opened["state_sha256"], decisions=choices, reviewer_id="test-human")

    def test_create_defer_edit_reopen_exact_navigation_and_deterministic_package(self):
        opened = self.open(create=True)
        self.assertEqual(opened["precision"], "WORD_RANGE")
        self.assertEqual(opened["topics"][0]["start_seconds"], 2.1)
        self.assertEqual(opened["topics"][1]["end_seconds"], 97.8)
        self.assertTrue(all(revision["transcript_provenance"]["verification_state"] == "machine_unverified" for revision in opened["transcript_revisions"]))
        choices = self.choices(opened); choices[1]["action"] = "DEFER"
        pending = self.save(opened, choices)
        self.assertEqual(pending["status"], "REVIEW_REQUIRED")
        self.assertEqual(self.open(), pending)
        with self.assertRaisesRegex(ValueError, "deferred"):
            notebook.notebook_package(self.root, **self.ids)
        choices[1]["action"] = "ACCEPT"
        choices[0].update(action="EDIT", new_title="Исправленное название", new_summary="Человеческий конспект")
        reviewed = self.save(pending, choices)
        self.assertEqual(reviewed["status"], "REVIEWED_FRAGMENTS_V2")
        self.assertFalse(reviewed["automatic_acceptance"])
        with patch("integra_core.application_runtime.execute_run", side_effect=AssertionError("must not process")), patch.object(notebook, "create_machine_evidence", side_effect=AssertionError("must not recreate")), patch.object(notebook, "prepare_topic_review", side_effect=AssertionError("must not prepare")):
            self.assertEqual(self.open(), reviewed)
            fragment = reviewed["reviewed"]["fragment_lineage"][0]
            navigation = notebook.notebook_navigation(self.root, **self.ids, fragment_id=fragment["id"])
            self.assertEqual(navigation["word_start_id"], fragment["word_start_id"])
            self.assertEqual(navigation["start_seconds"], 2.1)
            self.assertEqual(navigation["quote"], fragment["quote"])
        first = notebook.notebook_package(self.root, **self.ids)
        self.assertEqual(first, notebook.notebook_package(self.root, **self.ids))
        self.assertEqual(first[0]["result_kind"], "REVIEWED_FRAGMENTS_V2")
        self.assertIn(b"Canonical Knowledge", first[1]["result/result.md"])
        self.assertEqual(self.run_file.read_bytes(), self.run_before)
        self.assertFalse(list(self.root.rglob("canonical_knowledge.json")))

    def test_changed_inputs_missing_source_and_timing_fail_closed(self):
        self.open(create=True)
        for path in (self.media, self.text, self.topics, self.timeline):
            original = path.read_bytes()
            path.write_bytes(original + b" ")
            with self.assertRaises(ValueError): self.open()
            path.write_bytes(original)
        self.media.unlink()
        with self.assertRaises(ValueError): self.open()

    def test_incomplete_process_and_missing_timing_are_not_eligible(self):
        run = json.loads(self.run_file.read_bytes()); run["state"] = "RUNNING"; self.write(self.run_file, run)
        with self.assertRaisesRegex(ValueError, "completed"): self.open(create=True)
        run["state"] = "COMPLETED"; self.write(self.run_file, run)
        self.write(self.timeline, {"words": []})
        with self.assertRaisesRegex(ValueError, "timing"): self.open(create=True)

    def test_stale_revision_receipt_and_cas_fail_closed(self):
        opened = self.open(create=True)
        path = notebook._state_path(self.root, self.ids["source_id"], opened["notebook_id"])
        original = path.read_bytes(); state = json.loads(original); state["status"] = "REVIEWED_FRAGMENTS_V2"; self.write(path, state)
        with self.assertRaisesRegex(ValueError, "receipt"): self.open()
        path.write_bytes(original)
        choices = self.choices(opened); choices[0]["action"] = "DEFER"
        self.save(opened, choices)
        with self.assertRaisesRegex(ValueError, "changed"): self.save(opened, self.choices(opened))
        jobs = json.loads((self.root / "jobs.json").read_bytes()); jobs["jobs"][0]["source_sha256"] = "0"*64
        self.write(self.root / "jobs.json", jobs)
        with self.assertRaisesRegex(ValueError, "revision"): self.open()

    def test_interrupted_persistence_preserves_previous_notebook(self):
        opened = self.open(create=True)
        choices = self.choices(opened); choices[0]["action"] = "DEFER"
        with patch.object(notebook.os, "replace", side_effect=OSError("interrupted")):
            with self.assertRaises(OSError): self.save(opened, choices)
        self.assertEqual(self.open(), opened)

    def test_missing_timing_field_and_untrusted_source_revision_are_rejected(self):
        jobs = json.loads((self.root / "jobs.json").read_bytes()); jobs["jobs"][0].pop("source_sha256")
        self.write(self.root / "jobs.json", jobs)
        with self.assertRaisesRegex(ValueError, "revision"): self.open(create=True)


if __name__ == "__main__": unittest.main()
