"""Fault-injected process tests, not evidence of native provider parity."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

from integra_core import _timed_transcript_provider as provider


class ProviderProcessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / "input.srt"
        self.source.write_text("1\n00:00:00,000 --> 00:00:01,000\nFixture\n")
        self.target = self.root / "output.srt"

    def worker(self, body):
        path = self.root / "worker"
        path.write_text(f"#!{sys.executable}\n" + body)
        path.chmod(0o700)
        return {"worker": str(path), "worker_sha256": provider.digest(path)}

    def run_worker(self, runtime, **kwargs):
        return provider.run(runtime, self.source, self.target,
                            cancelled=kwargs.get("cancelled", lambda: False),
                            timeout_seconds=kwargs.get("timeout_seconds", 2),
                            max_output_bytes=kwargs.get("max_output_bytes", 4096))

    def test_runtime_changed_before_launch_is_rejected(self):
        runtime = self.worker("print('{}')\n")
        Path(runtime["worker"]).write_text("changed")
        with self.assertRaises(provider.PilotFailure) as caught:
            self.run_worker(runtime)
        self.assertEqual(caught.exception.code, "RUNTIME_IDENTITY_MISMATCH")

    def test_malformed_and_foreign_response_is_rejected(self):
        for payload in ["not json", "[]", "{}", json.dumps({"provider": "wrong"})]:
            with self.subTest(payload=payload):
                runtime = self.worker(f"print({payload!r})\n")
                with self.assertRaises(provider.PilotFailure) as caught:
                    self.run_worker(runtime)
                self.assertEqual(caught.exception.code, "INVALID_PROVIDER_RESULT")

    def test_output_limit_terminates_worker(self):
        marker = self.root / "pid"
        runtime = self.worker(f"import os,time\nfrom pathlib import Path\nPath({str(marker)!r}).write_text(str(os.getpid()))\nprint('x'*100000,flush=True)\ntime.sleep(60)\n")
        with self.assertRaises(provider.PilotFailure) as caught:
            self.run_worker(runtime, max_output_bytes=128)
        self.assertEqual(caught.exception.code, "OUTPUT_LIMIT")
        self.assert_gone(int(marker.read_text()))

    def assert_gone(self, pid):
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)

    def test_cancel_after_launch_and_timeout_preserve_unrelated_process(self):
        unrelated = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        self.addCleanup(lambda: unrelated.poll() is None and unrelated.kill())
        try:
            for reason in ("CANCELLED", "TIMED_OUT"):
                marker = self.root / "pid"
                marker.unlink(missing_ok=True)
                runtime = self.worker(f"import os,time\nfrom pathlib import Path\nPath({str(marker)!r}).write_text(str(os.getpid()))\ntime.sleep(60)\n")
                callback = (lambda: marker.exists()) if reason == "CANCELLED" else (lambda: False)
                with self.assertRaises(provider.PilotFailure) as caught:
                    self.run_worker(runtime, cancelled=callback,
                                    timeout_seconds=3 if reason == "CANCELLED" else .8)
                self.assertEqual(caught.exception.code, reason)
                self.assert_gone(int(marker.read_text()))
                self.assertIsNone(unrelated.poll())
                self.assertFalse(self.target.exists())
        finally:
            unrelated.kill()
            unrelated.wait()

    def test_next_attempt_after_timeout_can_complete(self):
        runtime = self.worker("import time; time.sleep(60)\n")
        with self.assertRaises(provider.PilotFailure):
            self.run_worker(runtime, timeout_seconds=.1)
        payload = {"schema_version": "1.0", "component": "videotext", "capability": "subtitles",
                   "operation": "normalize", "cue_count": 1, "output_srt": str(self.target),
                   "skipped_zero_duration_count": 0, "warnings": []}
        runtime = self.worker(f"print({json.dumps(payload)!r})\n")
        self.assertEqual(self.run_worker(runtime), payload)


if __name__ == "__main__":
    unittest.main()
