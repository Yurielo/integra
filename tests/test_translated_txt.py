"""Excel #20: user-facing translated TXT is a verified Process derivative."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
import uuid
from unittest.mock import patch

from integra_core.application_runtime import read_run
from integra_core.user_media import atomic_json, import_source, run_job


class TranslatedTextTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.project = self.root / "project"
        self.project.mkdir()
        (self.project / "jobs.json").write_text('{"jobs": []}', encoding="utf-8")
        self.source = self.root / "source.wav"
        self.source.write_bytes(b"source")
        self.ffmpeg = self.root / "ffmpeg"
        self.ffmpeg.write_text("#!/bin/sh\n", encoding="utf-8")
        self.ffmpeg.chmod(0o700)
        self.whisper = self.root / "whisper-cli"
        self.whisper.write_text("#!/bin/sh\n", encoding="utf-8")
        self.whisper.chmod(0o700)
        self.model = self.root / "model.bin"
        self.model.write_bytes(b"model")
        self.environment = {
            "INTEGRA_FFMPEG": str(self.ffmpeg),
            "INTEGRA_WHISPER_CLI": str(self.whisper),
            "INTEGRA_WHISPER_MODEL": str(self.model),
        }

    def _job(self):
        imported = import_source(self.project, self.source)
        job = {
            "job_id": f"urn:integra:job:{uuid.uuid4()}",
            "state": "QUEUED",
            "source_id": imported["source_id"],
            "source_sha256": imported["content_sha256"],
            "owned_path": imported["owned_path"],
            "requested_outputs": ["translation"],
            "source_speech_language": "ru",
            "translation_target_language": "en",
        }
        jobs = json.loads((self.project / "jobs.json").read_bytes())
        jobs["jobs"].append(job)
        (self.project / "jobs.json").write_text(json.dumps(jobs), encoding="utf-8")
        return job

    def _recognized(self, work: Path):
        subtitles = work / "full.srt"
        subtitles.write_text(
            "1\n00:00:00,000 --> 00:00:01,250\nПривет, Integra.\n",
            encoding="utf-8",
        )
        cleaned = work / "cleaned.txt"
        cleaned.write_text("Привет, Integra.\n", encoding="utf-8")
        review = work / "review.txt"
        review.write_text("OK\n", encoding="utf-8")
        record = work / "asr.json"
        record.write_text("{}\n", encoding="utf-8")
        provenance = {
            "mode": "normal",
            "executed_source_speech_language": "ru",
            "source_speech_language_mode": "FIXED",
            "quality_diagnostics": {
                "status": "PASSED", "suspicious_chunks": 0,
                "protective_retry_count": 0, "recovered_after_retry_count": 0,
            },
            "component": "seminartext", "commit_sha": "pinned",
            "entrypoint_sha256": "entry", "whisper_sha256": "whisper",
            "model_sha256": "model",
        }
        return {
            "srt": str(subtitles), "cleaned_txt": str(cleaned), "review_txt": str(review),
            "record": str(record), "provenance": provenance,
            "reuse": {"state": "REUSED"},
        }

    @staticmethod
    def _runtime():
        return {"component": "integra.translation", "provider": "ollama",
                "model": "translategemma:4b-it-q4_K_M", "model_id": "digest",
                "template_version": "translategemma-ollama-v1", "runtime_identity_sha256": "identity"}

    @staticmethod
    def _translation(subtitles: Path, output: Path, *, source: str, target: str, runtime: dict):
        payload = {
            "schema_version": "1.0", "component": "integra.translation", "capability": "translation",
            "source_language": "ru", "target_language": target, "model": runtime["model"],
            "semantic_status": "MACHINE_TRANSLATION_REVIEW_REQUIRED", "issues": [],
            "cues": [{"id": "1", "start_seconds": 0.0, "end_seconds": 1.25,
                      "text": "Hello, Integra."}],
        }
        output.write_text(json.dumps(payload), encoding="utf-8")
        return payload

    def _run(self, *, materialize=None):
        job = self._job()
        def recognize(*args, **kwargs):
            return self._recognized(args[2])
        patches = [
            patch("integra_core.user_media.asr_reuse.transcribe_or_reuse", side_effect=recognize),
            patch("integra_core.user_media.translation_preflight", side_effect=self._runtime),
            patch("integra_core.user_media.translate_translategemma", side_effect=self._translation),
        ]
        if materialize is not None:
            patches.append(patch("integra_core.user_media._materialize_translation_txt", side_effect=materialize))
        with patch.dict(os.environ, self.environment, clear=False):
            with patches[0], patches[1], patches[2]:
                if len(patches) == 4:
                    with patches[3]:
                        return run_job(self.project, job["job_id"])
                return run_job(self.project, job["job_id"])

    def test_verified_translation_publishes_utf8_text_and_persists_for_reopen(self):
        result = self._run()
        self.assertEqual(result["state"], "COMPLETED")
        outputs = result["outputs"]
        translated = Path(outputs["translation_txt"])
        self.assertEqual(translated.read_text(encoding="utf-8"), "Hello, Integra.\n")
        self.assertNotIn("videotext", translated.read_text(encoding="utf-8").lower())
        provenance = json.loads(Path(outputs["translation_provenance"]).read_bytes())
        self.assertEqual((provenance["source_language"], provenance["requested_target_language"], provenance["executed_target_language"]),
                         ("ru", "en", "en"))
        reopened = json.loads((self.project / "jobs.json").read_bytes())["jobs"][0]["outputs"]
        self.assertEqual(Path(reopened["translation_txt"]).read_bytes(), translated.read_bytes())

    def test_materialization_failure_cannot_publish_a_successful_translated_text(self):
        with self.assertRaisesRegex(ValueError, "disk full"):
            self._run(materialize=ValueError("disk full"))
        failed = json.loads((self.project / "jobs.json").read_bytes())["jobs"][0]
        self.assertEqual(failed["state"], "FAILED")
        self.assertNotIn("translation_txt", failed["outputs"])
        self.assertTrue(Path(failed["outputs"]["transcript"]).is_file())

    def test_reopen_recovers_legacy_translation_text_without_calling_provider(self):
        artifact = self.project / "artifacts" / "legacy-job"
        artifact.mkdir(parents=True)
        transcript = artifact / "transcript.json"
        transcript.write_text('{"segments": []}\n', encoding="utf-8")
        subtitles = artifact / "full.srt"
        subtitles.write_text("1\n00:00:00,000 --> 00:00:01,250\nПривет, Integra.\n", encoding="utf-8")
        translation = artifact / "translation.json"
        translation.write_text(json.dumps({
            "source_language": "ru", "target_language": "en",
            "cues": [{"text": "Hello, Integra."}],
        }), encoding="utf-8")
        source_id = "urn:integra:source:legacy"
        provenance = artifact / "translation_provenance.json"
        atomic_json(provenance, {
            "status": "COMPLETED", "source_id": source_id,
            "source_transcript_sha256": hashlib.sha256(transcript.read_bytes()).hexdigest(),
            "source_subtitles_sha256": hashlib.sha256(subtitles.read_bytes()).hexdigest(),
            "output_sha256": hashlib.sha256(translation.read_bytes()).hexdigest(),
            "source_language": "ru", "requested_target_language": "en",
            "executed_target_language": "en", "translated_cue_count": 1,
        })
        run_id = f"urn:integra:run:{uuid.uuid4()}"
        run_path = self.project / "runs" / f"{run_id.rsplit(':', 1)[-1]}.json"
        run_path.parent.mkdir()
        atomic_json(run_path, {
            "run_id": run_id, "state": "COMPLETED", "source_results": [{
                "source_id": source_id, "state": "COMPLETED", "outputs": {
                    "translation": str(translation), "translation_provenance": str(provenance),
                    "transcript_json": str(transcript), "subtitles": str(subtitles),
                },
            }],
        })

        with patch("integra_core.user_media.translate_translategemma", side_effect=AssertionError("must not translate")):
            reopened = read_run(self.project, run_id)
        outputs = reopened["source_results"][0]["outputs"]
        translated_text = Path(outputs["translation_txt"])
        self.assertEqual(translated_text.read_text(encoding="utf-8"), "Hello, Integra.\n")
        self.assertEqual(json.loads(translation.read_text(encoding="utf-8"))["cues"][0]["text"], "Hello, Integra.")
        self.assertEqual(read_run(self.project, run_id)["source_results"][0]["outputs"]["translation_txt"], str(translated_text))

    def test_reopen_refuses_legacy_translation_when_source_hash_does_not_bind(self):
        artifact = self.project / "artifacts" / "invalid-legacy-job"
        artifact.mkdir(parents=True)
        transcript = artifact / "transcript.json"
        transcript.write_text('{"segments": []}\n', encoding="utf-8")
        subtitles = artifact / "full.srt"
        subtitles.write_text("1\n00:00:00,000 --> 00:00:01,250\nПривет.\n", encoding="utf-8")
        translation = artifact / "translation.json"
        translation.write_text('{"source_language":"ru","target_language":"en","cues":[{"text":"Hello."}]}', encoding="utf-8")
        provenance = artifact / "translation_provenance.json"
        atomic_json(provenance, {"status": "COMPLETED", "source_id": "source", "source_transcript_sha256": "wrong",
                                 "source_subtitles_sha256": "wrong", "output_sha256": "wrong", "source_language": "ru",
                                 "requested_target_language": "en", "executed_target_language": "en", "translated_cue_count": 1})
        run_id = f"urn:integra:run:{uuid.uuid4()}"
        run_path = self.project / "runs" / f"{run_id.rsplit(':', 1)[-1]}.json"
        run_path.parent.mkdir()
        atomic_json(run_path, {"run_id": run_id, "state": "COMPLETED", "source_results": [{
            "source_id": "source", "state": "COMPLETED", "outputs": {"translation": str(translation),
            "translation_provenance": str(provenance), "transcript_json": str(transcript), "subtitles": str(subtitles)}}]})

        with self.assertRaisesRegex(ValueError, "does not match"):
            read_run(self.project, run_id)
        self.assertFalse((artifact / "translation.txt").exists())


if __name__ == "__main__":
    unittest.main()
