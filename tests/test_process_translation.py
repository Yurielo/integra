"""Transcript translation #18: real provider boundary, persistence and reuse."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
import uuid
from unittest.mock import patch

from integra_core.application_runtime import execute_run, prepare_run, prepare_transcript_translation_run
from integra_core.capabilities import TRANSLATION_TARGET_LANGUAGE, build_plan
from integra_core.user_media import import_source, run_job
from tests.asr_tools import media_environment


class ProcessTranslationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.project = self.root / "project"; self.project.mkdir()
        (self.project / "jobs.json").write_text('{"jobs": []}', encoding="utf-8")
        self.source = self.root / "source.wav"; self.source.write_bytes(b"translation fixture")
        self.environment = media_environment(self.root)
        self.patch = patch.dict(os.environ, self.environment); self.patch.start(); self.addCleanup(self.patch.stop)

    def _job(self, outputs, *, target_language="en", source_language="ru"):
        imported = import_source(self.project, self.source)
        job = {"job_id": f"urn:integra:job:{uuid.uuid4()}", "state": "QUEUED",
               "source_id": imported["source_id"], "source_sha256": imported["content_sha256"],
               "owned_path": imported["owned_path"], "requested_outputs": list(outputs),
               "source_speech_language": source_language,
               "translation_target_language": target_language}
        jobs = json.loads((self.project / "jobs.json").read_bytes()); jobs["jobs"].append(job)
        (self.project / "jobs.json").write_text(json.dumps(jobs), encoding="utf-8")
        return job

    @staticmethod
    def _translation(subtitles, output, *, source, target, runtime):
        payload = {"schema_version": "1.0", "component": "integra.translation", "capability": "translation",
                   "source_language": "ru", "target_language": target, "model": runtime["model"],
                   "semantic_status": "MACHINE_TRANSLATION_REVIEW_REQUIRED", "issues": [],
                   "cues": [{"id": "1", "start_seconds": 0.0, "end_seconds": 1.25,
                             "text": "Translated text for Integra verification."}]}
        output.write_text(json.dumps(payload), encoding="utf-8")
        return payload

    @staticmethod
    def _runtime():
        return {"component": "integra.translation", "provider": "ollama",
                "model": "translategemma:4b-it-q4_K_M", "model_id": "digest",
                "template_version": "translategemma-ollama-v1", "runtime_identity_sha256": "identity"}

    def test_translation_is_real_result_with_source_bound_provenance(self):
        job = self._job(("translation",))
        with patch("integra_core.user_media.translation_preflight", side_effect=self._runtime), \
             patch("integra_core.user_media.translate_translategemma", side_effect=self._translation) as translated:
            result = run_job(self.project, job["job_id"])
        self.assertEqual(result["state"], "COMPLETED")
        translated.assert_called_once()
        self.assertEqual(translated.call_args.kwargs["target"], "en")
        outputs = result["outputs"]
        self.assertIn("translation", outputs)
        self.assertIn("translation_txt", outputs)
        translated_text = Path(outputs["translation_txt"])
        self.assertEqual(translated_text.read_text(encoding="utf-8"),
                         "Translated text for Integra verification.\n")
        record = json.loads(Path(outputs["translation_provenance"]).read_bytes())
        self.assertEqual(record["source_id"], result["source_id"])
        self.assertEqual(record["source_language"], "ru")
        self.assertEqual(record["requested_target_language"], "en")
        self.assertEqual(record["executed_target_language"], "en")
        self.assertEqual(record["target_language"], "en")
        self.assertEqual(record["runtime"], self._runtime())
        self.assertEqual(record["output_sha256"], hashlib.sha256(Path(outputs["translation"]).read_bytes()).hexdigest())
        reopened = json.loads((self.project / "jobs.json").read_bytes())["jobs"][0]
        self.assertEqual(reopened["outputs"]["translation_txt"], outputs["translation_txt"])
        self.assertEqual(Path(reopened["outputs"]["translation_txt"]).read_bytes(), translated_text.read_bytes())

    def test_translation_accepts_json_timestamp_roundoff_within_half_millisecond(self):
        def rounded_translation(subtitles, output, *, source, target, runtime):
            payload = self._translation(subtitles, output, source=source, target=target, runtime=runtime)
            payload["cues"][0]["id"] = 1
            payload["cues"][0]["end_seconds"] = 1.2499999999999998
            output.write_text(json.dumps(payload), encoding="utf-8")
            return payload

        job = self._job(("translation",))
        with patch("integra_core.user_media.translation_preflight", side_effect=self._runtime), \
             patch("integra_core.user_media.translate_translategemma", side_effect=rounded_translation):
            result = run_job(self.project, job["job_id"])

        self.assertEqual(result["state"], "COMPLETED")

    def test_translation_failure_preserves_verified_transcript_for_a_later_retry(self):
        job = self._job(("translation",))
        with patch("integra_core.user_media.translation_preflight", side_effect=self._runtime), \
             patch("integra_core.user_media.translate_translategemma", side_effect=ValueError("translation unavailable")):
            with self.assertRaisesRegex(ValueError, "translation unavailable"):
                run_job(self.project, job["job_id"])
        failed = json.loads((self.project / "jobs.json").read_bytes())["jobs"][0]
        self.assertEqual(failed["state"], "FAILED")
        self.assertTrue(Path(failed["outputs"]["transcript"]).is_file())
        self.assertTrue(Path(failed["outputs"]["subtitles"]).is_file())
        self.assertNotIn("translation_txt", failed["outputs"])

    def test_text_materialization_failure_does_not_publish_translation_outputs(self):
        job = self._job(("translation",))
        with patch("integra_core.user_media.translation_preflight", side_effect=self._runtime), \
             patch("integra_core.user_media.translate_translategemma", side_effect=self._translation), \
             patch("integra_core.user_media._materialize_translation_txt", side_effect=ValueError("disk unavailable")):
            with self.assertRaisesRegex(ValueError, "disk unavailable"):
                run_job(self.project, job["job_id"])
        failed = json.loads((self.project / "jobs.json").read_bytes())["jobs"][0]
        self.assertEqual(failed["state"], "FAILED")
        self.assertNotIn("translation", failed["outputs"])
        self.assertNotIn("translation_txt", failed["outputs"])
        self.assertTrue(Path(failed["outputs"]["transcript"]).is_file())

    def test_translation_rejects_a_source_duplicate_or_runtime_substitution(self):
        job = self._job(("translation",))
        def duplicate(subtitles, output, *, source, target, runtime):
            payload = self._translation(subtitles, output, source=source, target=target, runtime=runtime)
            payload["cues"][0]["text"] = "Hello Integra, this is a complete test sentence."
            output.write_text(json.dumps(payload), encoding="utf-8")
            return payload
        with patch("integra_core.user_media.translation_preflight", side_effect=self._runtime), \
             patch("integra_core.user_media.translate_translategemma", side_effect=duplicate):
            with self.assertRaisesRegex(ValueError, "duplicates"):
                run_job(self.project, job["job_id"])

    def test_completed_transcript_starts_selected_target_translation_and_preserves_default(self):
        source = {"source_id": "source", "display_name": "source.wav", "source_type": "LOCAL_AUDIO",
                  "kind": "MEDIA", "input": str(self.source), "properties": {}}
        registry = [{"id": "translation", "title": "Перевод", "implementation_state": "IMPLEMENTED",
                     "runtime_available": True, "dependencies": ["transcript"], "source_types": ["LOCAL_AUDIO"]},
                    {"id": "transcript", "title": "Расшифровка", "implementation_state": "IMPLEMENTED",
                     "runtime_available": True, "dependencies": ["media_preparation"], "source_types": ["LOCAL_AUDIO"]}]
        with patch("integra_core.capabilities.capability_registry", return_value=registry):
            plan = build_plan([source], ["translation"])
        self.assertEqual(plan["translation_target_language"], TRANSLATION_TARGET_LANGUAGE)
        self.assertNotIn("translation_target_language", {"requested_by_user": True})

        # The helper accepts only a previously completed source, never a loose text file.
        run = prepare_run(self.project, plan)
        run["state"] = "COMPLETED"
        run["source_results"] = [{"source_id": "source", "state": "COMPLETED",
                                  "outputs": {"transcript": "/managed/transcript.txt", "subtitles": "/managed/full.srt"},
                                  "source_speech_language": {"requested": "ru", "executed": "ru"}}]
        run_path = self.project / "runs" / (run["run_id"].removeprefix("urn:integra:run:") + ".json")
        run_path.write_text(json.dumps(run), encoding="utf-8")
        with patch("integra_core.application_runtime.build_plan", return_value=plan):
            next_run = prepare_transcript_translation_run(self.project, run["run_id"], "source")
        self.assertEqual(next_run["plan"]["selected_outputs"], ["translation"])
        self.assertEqual(next_run["plan"]["translation_target_language"], "en")

    def test_unsupported_or_same_language_target_fails_without_fallback(self):
        job = self._job(("translation",), target_language="ru")
        with patch("integra_core.user_media.translation_preflight") as preflight, \
             self.assertRaisesRegex(ValueError, "не поддерживается"):
            run_job(self.project, job["job_id"])
        preflight.assert_not_called()

        source = {"source_id": "source", "display_name": "source.wav", "source_type": "LOCAL_AUDIO",
                  "kind": "MEDIA", "input": str(self.source), "properties": {}}
        registry = [{"id": "translation", "title": "Перевод", "implementation_state": "IMPLEMENTED",
                     "runtime_available": True, "dependencies": ["transcript"], "source_types": ["LOCAL_AUDIO"]},
                    {"id": "transcript", "title": "Расшифровка", "implementation_state": "IMPLEMENTED",
                     "runtime_available": True, "dependencies": ["media_preparation"], "source_types": ["LOCAL_AUDIO"]}]
        with patch("integra_core.capabilities.capability_registry", return_value=registry):
            plan = build_plan([source], ["translation"], translation_target_language="ru")
        run = prepare_run(self.project, plan)
        run["state"] = "COMPLETED"
        run["source_results"] = [{"source_id": "source", "state": "COMPLETED",
                                  "outputs": {"transcript": "/managed/transcript.txt", "subtitles": "/managed/full.srt"},
                                  "source_speech_language": {"requested": "ru", "executed": "ru"}}]
        run_path = self.project / "runs" / (run["run_id"].removeprefix("urn:integra:run:") + ".json")
        run_path.write_text(json.dumps(run), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "должен отличаться"):
            prepare_transcript_translation_run(self.project, run["run_id"], "source", "ru")

    def test_selected_target_is_carried_from_plan_to_execution_job(self):
        source = {"source_id": "source", "display_name": "source.wav", "source_type": "LOCAL_AUDIO",
                  "kind": "MEDIA", "input": str(self.source), "properties": {}}
        registry = [{"id": "translation", "title": "Перевод", "implementation_state": "IMPLEMENTED",
                     "runtime_available": True, "dependencies": ["transcript"], "source_types": ["LOCAL_AUDIO"]},
                    {"id": "transcript", "title": "Расшифровка", "implementation_state": "IMPLEMENTED",
                     "runtime_available": True, "dependencies": ["media_preparation"], "source_types": ["LOCAL_AUDIO"]}]
        imported = {"source_id": "source", "content_sha256": "sha", "owned_path": str(self.source)}
        with patch("integra_core.capabilities.capability_registry", return_value=registry), \
             patch("integra_core.application_runtime.import_source", return_value=imported), \
             patch("integra_core.application_runtime.run_job", return_value={"state": "COMPLETED", "outputs": {}}) as run:
            plan = build_plan([source], ["translation"], translation_target_language="en")
            prepared = prepare_run(self.project, plan)
            execute_run(self.project, prepared["run_id"])
        run.assert_called_once()
        jobs = json.loads((self.project / "jobs.json").read_bytes())["jobs"]
        self.assertEqual(jobs[0]["translation_target_language"], "en")


if __name__ == "__main__":
    unittest.main()
