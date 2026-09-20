import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from integra_core import word_timeline_runtime as runtime
from integra_core.word_timeline_runtime import MODEL_SHA256, preflight


class WordTimelineRuntimeTests(unittest.TestCase):
    def test_worker_failure_persists_bounded_candidate_evidence_and_stays_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); audio = root / "audio.wav"; srt = root / "speech.srt"; output = root / "timeline.json"
            audio.write_bytes(b"audio"); srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nTest\n")
            identity = {"python": "/bin/echo", "worker": "/worker", "model_dir": "/model", "site_packages": "/packages"}
            failed = __import__("subprocess").CompletedProcess([], 19, "out" * 6000, "err" * 6000)
            with patch.object(runtime, "preflight", return_value=identity), patch("subprocess.run", return_value=failed):
                with self.assertRaisesRegex(ValueError, "did not produce"):
                    runtime.generate_word_timeline(audio, srt, output)
            evidence = json.loads(output.with_suffix(".worker-evidence.json").read_text())
        self.assertEqual(evidence["result"], "FAIL")
        self.assertEqual(evidence["details"]["exit_status"], 19)
        self.assertLessEqual(len(evidence["details"]["stdout_tail"]), 16384)
        self.assertLessEqual(len(evidence["details"]["stderr_tail"]), 16384)
    def test_preflight_reports_exact_personal_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); packages = root / "packages" / "whisperx"; packages.mkdir(parents=True)
            model = root / "model"; model.mkdir(); (model / "pytorch_model.bin").write_text("weights")
            worker = root / "worker.py"; worker.write_text("# worker")
            python = root / "python3.13"; python.write_text("#!/bin/sh\n[ \"$1\" = --version ] && { echo Python 3.13.15; exit 0; }; echo READY\n"); python.chmod(python.stat().st_mode | stat.S_IXUSR)
            with patch.dict(os.environ, {"INTEGRA_WORD_ALIGNMENT_PYTHON":str(python), "INTEGRA_WORD_ALIGNMENT_SITE_PACKAGES":str(root / "packages"), "INTEGRA_WORD_ALIGNMENT_MODEL_DIR":str(model)}, clear=True), \
                 patch("integra_core.word_timeline_runtime.WORKER", worker), \
                 patch("integra_core.word_timeline_runtime._sha256", return_value=MODEL_SHA256):
                result = preflight()
        self.assertEqual(result["capability"], "word_timeline")
        self.assertEqual(result["model_sha256"], MODEL_SHA256)
