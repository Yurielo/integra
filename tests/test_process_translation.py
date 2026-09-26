"""Process translation integration without a semantic or Knowledge shortcut."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
import uuid
from unittest.mock import patch

from integra_core.application_runtime import prepare_run
from integra_core.capabilities import build_plan
from integra_core.user_media import import_source, run_job
from tests.asr_tools import media_environment


class ProcessTranslationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.project = self.root / "project"
        self.project.mkdir()
        self.jobs_path = self.project / "jobs.json"
        self.jobs_path.write_text('{"jobs": []}', encoding="utf-8")
        self.source = self.root / "source.wav"
        self.source.write_bytes(b"translation-fixture")
        self.environment = media_environment(self.root)
        self.environment_patch = patch.dict(os.environ, self.environment)
        self.environment_patch.start()
        self.addCleanup(self.environment_patch.stop)

    def _job(self, outputs, *, target="en"):
        imported = import_source(self.project, self.source)
        job = {
            "job_id": f"urn:integra:job:{uuid.uuid4()}", "state": "QUEUED",
            "source_id": imported["source_id"], "source_sha256": imported["content_sha256"],
            "owned_path": imported["owned_path"], "requested_outputs": list(outputs),
            "translation_target_language": target,
        }
        jobs = json.loads(self.jobs_path.read_bytes())
        jobs["jobs"].append(job)
        self.jobs_path.write_text(json.dumps(jobs), encoding="utf-8")
        return job

    @staticmethod
    def _translation(_subtitles, output, *, target):
        value = {
            "schema_version": "1.0", "component": "videotext", "capability": "translation",
            "source_language": "ru", "target_language": target,
            "model": "fixture", "semantic_status": "MACHINE_TRANSLATION_REVIEW_REQUIRED",
            "cues": [{"id": "1", "start_seconds": 0.0, "end_seconds": 1.0,
                      "text": "Translated fixture text"}], "issues": [],
        }
        output.write_text(json.dumps(value), encoding="utf-8")
        return value

    def test_translation_materializes_readable_source_linked_txt(self):
        job = self._job(("translation",), target="en")
        with patch("integra_core.user_media.translate_videotext", side_effect=self._translation) as translated:
            result = run_job(self.project, job["job_id"])
        self.assertEqual(result["state"], "COMPLETED")
        translated.assert_called_once()
        self.assertEqual(translated.call_args.kwargs["target"], "en")
        outputs = result["outputs"]
        self.assertEqual(Path(outputs["translation_txt"]).read_text(encoding="utf-8"), "Translated fixture text\n")
        record = json.loads(Path(outputs["translation"]).read_bytes())
        self.assertEqual(record["semantic_status"], "MACHINE_TRANSLATION_REVIEW_REQUIRED")
        self.assertNotIn("knowledge", outputs)
        self.assertNotIn("canonical_evidence", outputs)

    def test_plan_binds_selected_target_and_rejects_unrecognized_target(self):
        source = {"source_id": "source", "display_name": "source.wav", "source_type": "LOCAL_AUDIO",
                  "kind": "MEDIA", "input": "/safe/source.wav", "properties": {}}
        registry = [
            {"id": "translation", "title": "Перевод", "implementation_state": "IMPLEMENTED",
             "runtime_available": True, "dependencies": ["transcript"], "source_types": ["LOCAL_AUDIO"]},
            {"id": "transcript", "title": "Расшифровка", "implementation_state": "IMPLEMENTED",
             "runtime_available": True, "dependencies": ["media_preparation"], "source_types": ["LOCAL_AUDIO"]},
        ]
        with patch("integra_core.capabilities.capability_registry", return_value=registry):
            plan = build_plan([source], ["translation"], translation_target_language="ru")
            self.assertEqual(plan["translation_target_language"], "ru")
            self.assertEqual(plan["source_plans"][0]["translation_target_language"], "ru")
            with self.assertRaisesRegex(ValueError, "unsupported"):
                build_plan([source], ["translation"], translation_target_language="invented")
            prepared = prepare_run(self.project, plan)
        self.assertEqual(prepared["plan"]["translation_target_language"], "ru")


if __name__ == "__main__":
    unittest.main()
