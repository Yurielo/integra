"""Execute production AppKit dialog guards, not bridge mocks or semantic acceptance.

This narrow native-control probe is not a Candidate build or packaged E2E.
The actual interactive modal journey is separately required on each Candidate.
"""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def build_probe(root):
    source = (ROOT / "macos/IntegraApp.swift").read_text()
    helper = source[source.index("final class KnowledgeReviewDialog:"):source.index("final class Bridge:")]
    probe = root / "main.swift"
    probe.write_text("import AppKit\n" + helper + (ROOT / "tests/macos_knowledge_review_probe.swift").read_text())
    binary = root / "dialog-probe"
    subprocess.run(["xcrun", "swiftc", "-framework", "AppKit", str(probe), "-o", str(binary)],
                   check=True, capture_output=True, text=True, timeout=120)
    return binary


@unittest.skipUnless(sys.platform == "darwin", "requires macOS AppKit controls")
class KnowledgeReviewDialogTests(unittest.TestCase):
    def test_production_native_validation_keeps_inputs_and_confirmation(self):
        # Compile the exact production helper. No replacement implementation.
        with tempfile.TemporaryDirectory(prefix="integra-k2-dialog-unit-") as temporary:
            root = Path(temporary)
            binary = build_probe(root)
            result = subprocess.run([str(binary)], check=True, capture_output=True, text=True,
                                    timeout=30, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
            self.assertIn("NATIVE_DIALOG_GUARDS_PASS", result.stdout)
