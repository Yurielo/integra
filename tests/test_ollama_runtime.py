import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from integra_core.ollama_runtime import listed_models, resolve_ollama


class OllamaRuntimeTests(unittest.TestCase):
    def fake_ollama(self, root: Path) -> Path:
        value = root / "ollama"
        value.write_text("#!/bin/sh\nprintf 'NAME ID SIZE MODIFIED\\ngemma3:4b x y z\\n'\n")
        value.chmod(value.stat().st_mode | stat.S_IXUSR)
        return value

    def test_gui_path_uses_standard_macos_location(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = self.fake_ollama(Path(directory))
            with patch.dict(os.environ, {"PATH": "/usr/bin:/bin"}, clear=True), \
                 patch("integra_core.ollama_runtime.MACOS_OLLAMA_PATHS", (executable,)):
                resolved, models = listed_models()
        self.assertEqual(resolved, executable.resolve())
        self.assertEqual(models, {"gemma3:4b"})

    def test_missing_ollama_is_a_factual_value_error(self):
        with patch.dict(os.environ, {"PATH": "/missing"}, clear=True), \
             patch("integra_core.ollama_runtime.MACOS_OLLAMA_PATHS", ()):
            with self.assertRaisesRegex(ValueError, "Ollama is unavailable"):
                resolve_ollama()
