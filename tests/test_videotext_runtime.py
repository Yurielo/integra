import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from integra_core.videotext_runtime import preflight


class VideoTextRuntimeTests(unittest.TestCase):
    def test_preflight_requires_executable_and_supported_local_model(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            worker = root / "translation-worker"; worker.write_text("#!/bin/sh\n")
            worker.chmod(worker.stat().st_mode | stat.S_IXUSR)
            ollama = root / "ollama"; ollama.write_text("#!/bin/sh\nprintf 'NAME ID SIZE MODIFIED\\nqwen3:8b x y z\\n'\n")
            ollama.chmod(ollama.stat().st_mode | stat.S_IXUSR)
            with patch.dict(os.environ, {"INTEGRA_VIDEOTEXT_TRANSLATION_WORKER": str(worker), "INTEGRA_OLLAMA": str(ollama)}, clear=True):
                runtime = preflight()
        self.assertEqual(runtime["component"], "videotext")
        self.assertEqual(runtime["model"], "qwen3:8b")
