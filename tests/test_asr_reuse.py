"""Production run_job + pinned CLI; only media executables are test fixtures."""
import json
import fcntl
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
import uuid
from unittest.mock import patch

from integra_core import asr_reuse, seminartext_asr_runtime as asr
from integra_core.user_media import import_source, run_job
from tests.asr_tools import media_environment, TRANSCRIPT


class ASRReuseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.project = self.root / "project"; self.project.mkdir()
        self.jobs_path = self.project / "jobs.json"; self.jobs_path.write_text('{"jobs":[]}')
        self.environment = media_environment(self.root)
        self.counter = self.root / "recognizer-calls"
        self.whisper = Path(self.environment["INTEGRA_WHISPER_CLI"])
        original = self.whisper.read_text().split("\n", 1)
        self.whisper.write_text(original[0] + "\nfrom pathlib import Path\n"
                               f"with Path({str(self.counter)!r}).open('a') as calls: calls.write('call\\n')\n" + original[1])
        environment = patch.dict(os.environ, self.environment)
        environment.start(); self.addCleanup(environment.stop)
        self.source = self.root / "audio.wav"; self.source.write_bytes(b"test audio")

    def job(self, outputs=("transcript",), source=None, recognition_mode="normal"):
        imported = import_source(self.project, source or self.source)
        job = {"job_id": f"urn:integra:job:{uuid.uuid4()}", "state": "QUEUED",
               "source_id": imported["source_id"], "source_sha256": imported["content_sha256"],
               "owned_path": imported["owned_path"], "requested_outputs": list(outputs),
               "recognition_mode": recognition_mode}
        jobs = json.loads(self.jobs_path.read_bytes()); jobs["jobs"].append(job)
        self.jobs_path.write_text(json.dumps(jobs))
        return job

    def execute(self, outputs=("transcript",), source=None, recognition_mode="normal"):
        job = self.job(outputs, source, recognition_mode)
        return run_job(self.project, job["job_id"])

    def calls(self):
        return len(self.counter.read_text().splitlines()) if self.counter.is_file() else 0

    def test_real_job_reuses_verified_asr_without_second_recognizer_launch(self):
        first = self.execute(); before = Path(first["outputs"]["transcript_asr_record"]).read_bytes()
        second = self.execute(("subtitles",))
        self.assertEqual(self.calls(), 1)
        self.assertEqual(first["asr_reuse"]["state"], "CREATED")
        self.assertEqual(second["asr_reuse"]["state"], "REUSED")
        self.assertEqual(second["outputs"]["subtitles"], first["outputs"]["subtitles"])
        self.assertEqual(Path(first["outputs"]["transcript_asr_record"]).read_bytes(), before)
        transcript = json.loads(Path(second["outputs"]["transcript_json"]).read_bytes())
        self.assertEqual(transcript["assurance"], "MACHINE_TRANSCRIPT_UNREVIEWED")
        self.assertEqual(transcript["asr_reuse"]["state"], "REUSED")

    def test_careful_mode_is_a_distinct_verified_reuse_binding(self):
        normal = self.execute()
        careful = self.execute(recognition_mode="careful")
        careful_reused = self.execute(("subtitles",), recognition_mode="careful")
        self.assertEqual(self.calls(), 2)
        self.assertEqual(normal["asr_reuse"]["state"], "CREATED")
        self.assertEqual(careful["asr_reuse"]["state"], "CREATED")
        self.assertEqual(careful_reused["asr_reuse"]["state"], "REUSED")
        self.assertEqual(careful["recognition"]["executed_mode"], "careful")

    def test_downstream_failure_does_not_discard_successful_asr(self):
        with patch("integra_core.user_media.translate_translategemma", side_effect=ValueError("downstream unavailable")):
            with self.assertRaisesRegex(ValueError, "downstream unavailable"):
                self.execute(("translation",))
        failed = json.loads(self.jobs_path.read_bytes())["jobs"][0]
        self.assertEqual(failed["state"], "FAILED")
        self.assertEqual(failed["asr_reuse"]["state"], "CREATED")
        retry = self.execute()
        self.assertEqual(retry["asr_reuse"]["state"], "REUSED")
        self.assertEqual(self.calls(), 1)

    def test_source_model_and_engine_bytes_each_invalidate_reuse(self):
        self.execute()
        self.source.write_bytes(b"new source audio")
        self.assertEqual(self.execute()["asr_reuse"]["state"], "CREATED")
        Path(self.environment["INTEGRA_WHISPER_MODEL"]).write_bytes(b"new model")
        self.assertEqual(self.execute()["asr_reuse"]["state"], "CREATED")
        self.whisper.write_text(self.whisper.read_text() + "\n# revised test recognizer\n")
        self.assertEqual(self.execute()["asr_reuse"]["state"], "CREATED")
        self.assertEqual(self.calls(), 4)

    def test_configuration_is_included_in_identity(self):
        runtime = asr.preflight(Path(self.environment["INTEGRA_FFMPEG"]), self.whisper,
                                Path(self.environment["INTEGRA_WHISPER_MODEL"]))
        original = asr_reuse._binding(self.source, runtime)
        for name, value in (("language", "en"), ("chunk_seconds", 600), ("mode", "other")):
            modified = {**runtime, name: value}
            self.assertNotEqual(original, asr_reuse._binding(self.source, modified), name)

    def test_changed_cached_artifact_is_preserved_but_not_reused(self):
        first = self.execute()
        subtitle = Path(first["outputs"]["subtitles"]); subtitle.write_text("tampered subtitle")
        second = self.execute()
        self.assertEqual(second["asr_reuse"]["state"], "CREATED")
        self.assertEqual(self.calls(), 2)
        self.assertEqual(subtitle.read_text(), "tampered subtitle")

    def test_incomplete_and_symlinked_manifests_are_not_reused(self):
        first = self.execute(); manifest = Path(first["asr_reuse"]["manifest_path"])
        manifest.write_text('{"state":"VERIFIED_COMPLETE"}')
        second = self.execute()
        self.assertEqual(second["asr_reuse"]["state"], "CREATED")
        second_manifest = Path(second["asr_reuse"]["manifest_path"])
        retained = second_manifest.with_suffix(".retained"); second_manifest.rename(retained)
        second_manifest.symlink_to(retained)
        third = self.execute()
        self.assertEqual(third["asr_reuse"]["state"], "CREATED")
        self.assertEqual(self.calls(), 3)
        self.assertTrue(second_manifest.is_symlink())

    def test_quality_failure_is_never_cached(self):
        self.whisper.write_text(self.whisper.read_text().replace(repr(TRANSCRIPT), repr("Неполное восстановление. " * 30)))
        with self.assertRaises(asr.ASRQualityError):
            self.execute()
        self.assertFalse(list((self.project / "asr-cache-v1").glob("*.json")))
        first_calls = self.calls()
        with self.assertRaises(asr.ASRQualityError):
            self.execute()
        self.assertGreater(self.calls(), first_calls)

    def test_typed_malformed_manifest_is_preserved_and_retranscribed(self):
        first = self.execute()
        manifest = Path(first["asr_reuse"]["manifest_path"])
        record = json.loads(manifest.read_bytes()); record["files"] = list(asr_reuse.FILE_KEYS)
        manifest.write_text(json.dumps(record))
        before = manifest.read_bytes()
        second = self.execute()
        self.assertEqual(second["asr_reuse"]["state"], "CREATED")
        self.assertEqual(manifest.read_bytes(), before)
        self.assertEqual(self.calls(), 2)

    def test_incomplete_pending_entry_is_ignored(self):
        first = self.execute(); manifest = Path(first["asr_reuse"]["manifest_path"])
        pending = manifest.with_suffix(".pending"); manifest.rename(pending)
        second = self.execute()
        self.assertEqual(second["asr_reuse"]["state"], "CREATED")
        self.assertEqual(self.calls(), 2)
        self.assertTrue(pending.is_file())

    def test_held_cache_lock_rejects_duplicate_asr_launch(self):
        args = self.direct_args()
        runtime = asr.preflight(args["ffmpeg"], args["whisper"], args["model"])
        binding = asr_reuse._binding(args["source"], runtime)
        key = hashlib.sha256(asr_reuse._canonical(binding)).hexdigest()
        cache = self.project / "asr-cache-v1"; cache.mkdir()
        with (cache / (key + ".lock")).open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            with self.assertRaisesRegex(ValueError, "already being processed"):
                asr_reuse.transcribe_or_reuse(**args)
        self.assertEqual(self.calls(), 0)

    def direct_args(self):
        job = self.job(); work = self.project / "artifacts" / uuid.uuid4().hex; work.mkdir(parents=True)
        return {"project_dir": self.project, "source": Path(job["owned_path"]), "work": work,
                "ffmpeg": Path(self.environment["INTEGRA_FFMPEG"]), "whisper": self.whisper,
                "model": Path(self.environment["INTEGRA_WHISPER_MODEL"]),
                "expected_source_sha256": job["source_sha256"]}

    def test_cancelled_recognition_and_reuse_do_not_return_success(self):
        args = self.direct_args()
        with self.assertRaises(asr.ASRCancelled):
            asr_reuse.transcribe_or_reuse(**args, cancelled=lambda: self.counter.exists())
        self.assertFalse(list((self.project / "asr-cache-v1").glob("*.json")))
        self.execute()
        calls = self.calls(); args = self.direct_args(); cancelled = False
        def progress(message):
            nonlocal cancelled
            if "повторное ASR не требуется" in message: cancelled = True
        with self.assertRaises(asr.ASRCancelled):
            asr_reuse.transcribe_or_reuse(**args, cancelled=lambda: cancelled, progress=progress)
        self.assertEqual(self.calls(), calls)

    def test_mutation_during_cache_validation_fails_closed(self):
        self.execute(); args = self.direct_args()
        original = asr_reuse._load
        def mutate_after_load(*values, **options):
            result = original(*values, **options)
            args["model"].write_bytes(b"changed during validation")
            return result
        with patch.object(asr_reuse, "_load", side_effect=mutate_after_load):
            with self.assertRaisesRegex(ValueError, "changed while validating reuse"):
                asr_reuse.transcribe_or_reuse(**args)
        self.assertEqual(self.calls(), 1)


if __name__ == "__main__":
    unittest.main()
