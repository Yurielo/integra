"""Optional real pinned-provider proof; never builds or processes media."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from integra_core import process_executor_pilot as pilot, videotext_subtitles


@unittest.skipUnless(os.environ.get("INTEGRA_PILOT_REFERENCE_APP"), "requires explicit reference Candidate")
class RealProviderReferenceTests(unittest.TestCase):
    def test_real_provider_expected_bytes_and_existing_adapter_equivalence(self):
        resources = Path(os.environ["INTEGRA_PILOT_REFERENCE_APP"]).resolve() / "Contents/Resources"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            source = root / "fixture.srt"
            source.write_bytes(("00:00:00,125 --> 00:00:02,750\r\n  Первый фрагмент.\r\nSecond line  \r\n\r\n"
                                "00:05:00,000 --> 00:05:01,250\r\nВторой фрагмент.\r\n").encode())
            before = source.read_bytes()
            request = {"schema_version": "1.0", "capability_id": pilot.CAPABILITY,
                       "project_id": "fixture-project", "run_id": "fixture-run",
                       "source": {"source_id": "fixture", "revision": "1"},
                       "input": {"artifact_id": "transcript", "format": "srt",
                                 "sha256": hashlib.sha256(before).hexdigest()},
                       "options": {"media_duration_ms": 301250}}
            envelope = pilot.execute(request, source, resources=resources)
            attempt = Path(envelope["attempt_path"])
            try:
                self.assertEqual(envelope["result"]["status"], "COMPLETED", envelope)
                produced = (attempt / "published/transcript.srt").read_bytes()
                expected = ("1\n00:00:00,125 --> 00:00:02,750\nПервый фрагмент.\nSecond line\n\n"
                            "2\n00:05:00,000 --> 00:05:01,250\nВторой фрагмент.\n").encode()
                self.assertEqual(produced, expected)
                with patch.dict(os.environ, {"INTEGRA_VIDEOTEXT_SUBTITLE_WORKER":
                        str(resources / "runtime/videotext/translation-worker")}):
                    videotext_subtitles.normalize(source, root / "legacy.srt")
                self.assertEqual(produced, (root / "legacy.srt").read_bytes())
                self.assertEqual(source.read_bytes(), before)
                public = json.dumps(envelope["result"]).lower()
                self.assertNotIn("videotext", public)
                self.assertNotIn("seminartext", public)
                self.assertEqual(envelope["evidence"]["runtime"]["provider_commit"],
                                 "2e098d1705b6815628bee1e023f4742718eabf02")
            finally:
                for path in attempt.rglob("*"):
                    if path.is_dir():
                        path.chmod(0o700)
                shutil.rmtree(attempt)


if __name__ == "__main__":
    unittest.main()
