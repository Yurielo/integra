import json
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import uuid
import runpy
from concurrent.futures import ThreadPoolExecutor


ROOT = Path(__file__).resolve().parents[1]
BRIDGE = Path(os.environ.get("INTEGRA_TEST_BRIDGE", ROOT / "macos" / "Resources" / "bridge.py"))


class TranscriptReviewBridgeTests(unittest.TestCase):
    def test_review_inputs_rebase_only_same_project_after_data_root_relocation(self):
        bridge = runpy.run_path(str(BRIDGE))
        with tempfile.TemporaryDirectory() as directory:
            project_uuid = uuid.uuid4(); project_id = f"urn:integra:project:{project_uuid}"
            run_id = f"urn:integra:run:{uuid.uuid4()}"; source_id = f"urn:integra:source:{uuid.uuid4()}"
            old_project = Path(directory) / "old-app-data" / "projects" / str(project_uuid)
            project = Path(directory) / "current-app-data" / "projects" / str(project_uuid)
            for root in (old_project, project):
                (root / "artifacts").mkdir(parents=True); (root / "sources").mkdir()
            names = {"transcript": "transcript.txt", "word_timeline": "word_timeline.json", "media": "source.mp4"}
            (project / "artifacts" / names["transcript"]).write_text("Проверка\n", encoding="utf-8")
            (project / "artifacts" / names["word_timeline"]).write_text(json.dumps({"words": []}))
            (project / "sources" / names["media"]).write_bytes(b"owned media")
            for path in (old_project / "artifacts" / names["transcript"], old_project / "artifacts" / names["word_timeline"], old_project / "sources" / names["media"]):
                path.write_bytes(b"historical path placeholder")
            (project / "project.json").write_text(json.dumps({"project_id": project_id, "name": "Moved", "status": "READY"}))
            job_id = f"urn:integra:job:{uuid.uuid4()}"
            (project / "jobs.json").write_text(json.dumps({"jobs": [{"job_id": job_id, "source_id": source_id,
                "owned_path": str(old_project / "sources" / names["media"])}]}))
            (project / "runs").mkdir()
            (project / "runs" / (run_id.removeprefix("urn:integra:run:") + ".json")).write_text(json.dumps({"run_id": run_id,
                "source_results": [{"source_id": source_id, "state": "COMPLETED", "job_id": job_id, "outputs": {
                    "transcript": str(old_project / "artifacts" / names["transcript"]),
                    "word_timeline": str(old_project / "artifacts" / names["word_timeline"]),
                }}]}))
            values = bridge["_review_inputs"](project.parents[1], {"project_id": project_id, "run_id": run_id, "source_id": source_id})
            self.assertEqual(values["media_path"], str((project / "sources" / names["media"]).resolve()))
            self.assertEqual(values["transcript_path"], str((project / "artifacts" / names["transcript"]).resolve()))
            self.assertEqual(values["word_timeline_path"], str((project / "artifacts" / names["word_timeline"]).resolve()))

    def test_concurrent_source_output_updates_preserve_both_sources(self):
        bridge = runpy.run_path(str(BRIDGE))
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory); (project / "runs").mkdir()
            run_id = f"urn:integra:run:{uuid.uuid4()}"
            path = project / "runs" / f"{run_id.removeprefix('urn:integra:run:')}.json"
            path.write_text(json.dumps({"run_id": run_id, "source_results": [
                {"source_id": source, "state": "COMPLETED", "outputs": {}} for source in ("one", "two")]}))
            with ThreadPoolExecutor(max_workers=8) as executor:
                futures = [executor.submit(bridge["_record_review_outputs"], project, run_id, source, {f"output_{index}": str(index)})
                    for source in ("one", "two") for index in range(10)]
                for future in futures: future.result()
            for source in json.loads(path.read_text())["source_results"]:
                self.assertEqual(len(source["outputs"]), 10)

    def test_bridge_prepares_topic_review_only_from_persisted_evidence_and_real_drafts(self):
        with tempfile.TemporaryDirectory() as directory:
            app_data = Path(directory) / "app-data"; project_uuid = uuid.uuid4()
            project_id = f"urn:integra:project:{project_uuid}"; run_id = f"urn:integra:run:{uuid.uuid4()}"
            source_id = f"urn:integra:source:{uuid.uuid4()}"; project = app_data / "projects" / str(project_uuid)
            project.mkdir(parents=True); (project / "project.json").write_text(json.dumps({"project_id": project_id, "name": "Review", "status": "READY"}))
            artifact = project / "artifacts"; artifact.mkdir(); transcript = artifact / "transcript.txt"; transcript.write_text("Раз проверка\n", encoding="utf-8")
            media = artifact / "source.mp4"; media.write_bytes(b"owned media")
            timeline = artifact / "word_timeline.json"; timeline.write_text(json.dumps({"words": [{"text": "Раз", "start_seconds": 0.1, "end_seconds": 0.3, "alignment_status": "ALIGNED"}]}))
            evidence = artifact / "canonical_evidence.json"; evidence.write_text(json.dumps({"artifact_type": "seminartext.canonical_evidence", "project": {"id": "project_fixture", "title": "Fixture"}, "sources": [{"id": "source_fixture", "source_registry_id": source_id}], "transcript_revisions": [{"id": "revision_fixture", "source_id": "source_fixture"}], "words": [{"id": "revision_fixture:word:000000", "source_id": "source_fixture", "transcript_revision_id": "revision_fixture", "sequence": 0, "start_seconds": 0.1, "end_seconds": 0.3}], "benchmark_segments": [{"id": "benchmark_fixture_000000", "transcript_revision_id": "revision_fixture", "sequence": 0, "word_start_id": "revision_fixture:word:000000", "word_end_id": "revision_fixture:word:000000"}]}))
            evidence.write_text(evidence.read_text().replace("source_fixture", "source_source_" + hashlib.sha256(source_id.encode()).hexdigest()[:24]))
            topics = artifact / "topics.json"; topics.write_text(json.dumps({"component": "seminartext", "topics": [{"semantic_status": "REVIEW_REQUIRED", "title": "Тема", "summary": "Черновик", "start_seconds": 0.1, "end_seconds": 0.3}]}, ensure_ascii=False), encoding="utf-8")
            job_id = f"urn:integra:job:{uuid.uuid4()}"; (project / "jobs.json").write_text(json.dumps({"jobs": [{"job_id": job_id, "source_id": source_id, "owned_path": str(media)}]}))
            run = {"run_id": run_id, "state": "COMPLETED", "source_results": [{"source_id": source_id, "state": "COMPLETED", "job_id": job_id, "outputs": {"transcript": str(transcript), "word_timeline": str(timeline), "canonical_evidence": str(evidence), "topics": str(topics)}}]}
            (project / "runs").mkdir(); run_path = project / "runs" / f"{run_id.removeprefix('urn:integra:run:')}.json"; run_path.write_text(json.dumps(run))
            environment = {**os.environ, "INTEGRA_APP_DATA_ROOT": str(app_data), "PYTHONDONTWRITEBYTECODE": "1"}
            request = {"project_id": project_id, "run_id": run_id, "source_id": source_id}
            completed = subprocess.run(["python3", str(BRIDGE), "prepare-topic-review"], input=json.dumps(request), text=True, capture_output=True, check=True, env=environment)
            result = json.loads(completed.stdout)["result"]
            self.assertEqual(result["status"], "REVIEW_REQUIRED")
            self.assertTrue(Path(result["topic_drafts_path"]).is_file())
            persisted = json.loads(run_path.read_text())
            self.assertEqual(persisted["source_results"][0]["outputs"]["topic_review_drafts"], result["topic_drafts_path"])

    @unittest.skipUnless((ROOT / ".runtime-components/seminartext-pinned/.git").exists() or os.environ.get("INTEGRA_TEST_BRIDGE"), "requires pinned or bundled SeminarText runtime")
    def test_bridge_requires_explicit_review_then_persists_canonical_evidence_output(self):
        self._exercise_real_review(partial=False)

    @unittest.skipUnless((ROOT / ".runtime-components/seminartext-pinned/.git").exists() or os.environ.get("INTEGRA_TEST_BRIDGE"), "requires pinned or bundled SeminarText runtime")
    def test_bridge_preserves_arbitrary_review_as_fragments_not_canonical_knowledge(self):
        self._exercise_real_review(partial=True)

    def _exercise_real_review(self, partial):
        with tempfile.TemporaryDirectory() as directory:
            app_data = Path(directory) / "app-data"
            project_uuid = uuid.uuid4(); project_id = f"urn:integra:project:{project_uuid}"
            run_id = f"urn:integra:run:{uuid.uuid4()}"; source_id = f"urn:integra:source:{uuid.uuid4()}"
            project = app_data / "projects" / str(project_uuid); project.mkdir(parents=True)
            media = project / "sources" / "source.mp4"; media.parent.mkdir(); media.write_bytes(b"owned media")
            artifact = project / "artifacts" / "job"; artifact.mkdir(parents=True)
            transcript = artifact / "transcript.txt"; transcript.write_text("Раз проверка\n", encoding="utf-8")
            timeline = artifact / "word_timeline.json"; timeline.write_text(json.dumps({
                "capability": "word_timeline", "model": {"id": "fixture", "revision": "fixture", "weights_sha256": "0" * 64},
                "aligner": {"name": "fixture", "version": "1"}, "words": [
                    {"text": "Раз", "start_seconds": 0.1, "end_seconds": 0.3, "alignment_status": "ALIGNED"},
                    {"text": "проверка", "start_seconds": 0.35, "end_seconds": 0.75, "alignment_status": "ALIGNED"},
                ],
            }, ensure_ascii=False), encoding="utf-8")
            (project / "project.json").write_text(json.dumps({"project_id": project_id, "name": "Review", "status": "READY"}))
            job_id = f"urn:integra:job:{uuid.uuid4()}"
            (project / "jobs.json").write_text(json.dumps({"jobs": [{"job_id": job_id, "source_id": source_id, "owned_path": str(media)}]}))
            run = {"run_id": run_id, "state": "COMPLETED", "source_results": [{"source_id": source_id, "state": "COMPLETED", "job_id": job_id, "outputs": {"transcript": str(transcript), "word_timeline": str(timeline)}}]}
            (project / "runs").mkdir(); (project / "runs" / f"{run_id.removeprefix('urn:integra:run:')}.json").write_text(json.dumps(run))
            environment = {**os.environ, "INTEGRA_APP_DATA_ROOT": str(app_data)}
            checkout = os.environ.get("INTEGRA_TEST_SEMINARTEXT_CHECKOUT", str(ROOT / ".runtime-components" / "seminartext-pinned"))
            if checkout:
                environment["INTEGRA_SEMINARTEXT_CHECKOUT"] = checkout

            def invoke(operation, request):
                completed = subprocess.run([os.environ.get("INTEGRA_TEST_PYTHON", "python3"), str(BRIDGE), operation], input=json.dumps(request), text=True,
                                           capture_output=True, check=True, env=environment)
                return json.loads(completed.stdout)["result"]

            request = {"project_id": project_id, "run_id": run_id, "source_id": source_id}
            prepared = invoke("prepare-transcript-review", request)
            self.assertEqual(prepared["status"], "REVIEW_REQUIRED")
            self.assertFalse((project / "review" / "transcript-evidence" / "canonical_bundle.json").exists())
            result = invoke("apply-transcript-review", request | {"reviewer_id": "synthetic-test-reviewer", "acknowledged": True, "expected_request_sha256": prepared["request_sha256"]})
            self.assertEqual(result["status"], "EVIDENCE_CREATED")
            persisted = json.loads((project / "runs" / f"{run_id.removeprefix('urn:integra:run:')}.json").read_text())
            outputs = persisted["source_results"][0]["outputs"]
            self.assertTrue(Path(outputs["canonical_evidence"]).is_file())
            self.assertTrue(Path(outputs["transcript_review_result"]).is_file())
            repeated = invoke("prepare-transcript-review", request)
            self.assertEqual(repeated["request_sha256"], prepared["request_sha256"])
            recovered = invoke("apply-transcript-review", request | {"reviewer_id": "synthetic-test-reviewer", "acknowledged": True, "expected_request_sha256": repeated["request_sha256"]})
            self.assertEqual(recovered["seminartext"]["canonical_evidence_path"], outputs["canonical_evidence"])
            topic_file = artifact / "topics.json"
            topic_file.write_text(json.dumps({"component": "seminartext", "topics": [{
                "title": "Проверочная тема", "summary": "Синтетическая проверка", "semantic_status": "REVIEW_REQUIRED",
                "start_seconds": 0.1, "end_seconds": 0.3 if partial else 0.75}]}), encoding="utf-8")
            outputs["topics"] = str(topic_file)
            (project / "runs" / f"{run_id.removeprefix('urn:integra:run:')}.json").write_text(json.dumps(persisted))
            environment["PYTHONPATH"] = str(ROOT / ".runtime-components/review-python")
            package = invoke("prepare-knowledge-review", request)
            self.assertEqual(package["status"], "REVIEW_REQUIRED")
            self.assertEqual(package["media_path"], str(media.resolve()))
            knowledge = invoke("apply-knowledge-review", request | {"expected_package_sha256": package["package_sha256"],
                "boundaries_acknowledged": partial,
                "reviewer_id": "synthetic-test-reviewer", "decisions": [{"topic_id": item["id"], "action": "ACCEPT", "reason": "Explicit synthetic test decision"} for item in package["topics"]]})
            self.assertEqual(knowledge["status"], "REVIEWED_TOPICS_CREATED" if partial else "KNOWLEDGE_CREATED")
            self.assertTrue(Path(knowledge["reviewed_topics_path" if partial else "canonical_knowledge_path"]).is_file())
            if partial:
                self.assertNotIn("canonical_knowledge_path", knowledge)
                final_run = json.loads((project / "runs" / f"{run_id.removeprefix('urn:integra:run:')}.json").read_text())
                self.assertNotIn("canonical_knowledge", final_run["source_results"][0]["outputs"])
            exported = invoke("build-reviewed-package", request)
            self.assertEqual(exported["status"], "PACKAGE_CREATED")
            self.assertFalse(exported["published"])
            self.assertEqual(exported["result_kind"], "REVIEWED_FRAGMENTS_V2" if partial else "CANONICAL_KNOWLEDGE_V1")
            self.assertEqual(invoke("build-reviewed-package", request), exported)
            available = invoke("available-packages", {})
            self.assertEqual(available[0]["package_id"], exported["package_id"])
            for destination in ("obsidian", "onedrive"):
                target = Path(directory) / ("synthetic-" + destination)
                target.mkdir()
                publication = {"package_dir": exported["package_dir"], "target_dir": str(target), "publication_target": destination}
                preview = invoke("package-preview", publication)
                self.assertFalse(list(target.rglob("COMPLETE.json")))
                published = invoke("package-publish", publication)
                self.assertEqual(published["state"], "EXPORTED" if destination == "obsidian" else "LOCALLY_PUBLISHED")
                self.assertEqual(published["package_id"], preview["package_id"])
                self.assertFalse(published["cloud_verified"])
                self.assertEqual(len(list(target.rglob("COMPLETE.json"))), 1)


if __name__ == "__main__":
    unittest.main()
