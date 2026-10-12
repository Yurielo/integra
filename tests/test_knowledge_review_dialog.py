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

    def test_k1_review_uses_the_same_persistent_modal_and_hides_internal_coordinates(self):
        source = (ROOT / "macos/IntegraApp.swift").read_text()
        review = source[source.index("@objc private func reviewKnowledge()"):source.index("@objc private func exportKnowledge()")]
        self.assertIn("let reviewDialog = KnowledgeReviewDialog()", review)
        self.assertIn("reviewDialog.validate = { reviewDialog.validateSelections(forms.map { $0.1 }) }", review)
        self.assertIn('reviewDialog.configure(primaryTitle: "Сохранить решения")', review)
        self.assertIn("guard reviewDialog.run() == .alertFirstButtonReturn", review)
        self.assertNotIn("while true", review)
        self.assertNotIn("Идентификатор проверяющего", review)
        self.assertNotIn("Точные границы — первый и последний ID слова", review)
        self.assertNotIn('NSTextField(string: prior["word_start_id"]', review)
        self.assertNotIn('NSTextField(string: prior["word_end_id"]', review)
        self.assertIn('decision["word_start_id"] = form.4["word_start_id"] as? String ?? ""', review)
        self.assertIn('decision["word_end_id"] = form.4["word_end_id"] as? String ?? ""', review)
        self.assertIn('request["reviewer_id"] = knowledgeOwnerReviewerID', review)
