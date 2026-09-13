from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ASRReuseUIGuardrails(unittest.TestCase):
    def test_retry_is_serial_asynchronous_and_reentrant_safe(self):
        source = (ROOT / "macos/IntegraApp.swift").read_text()
        handler = source.split("@objc private func retryRun()", 1)[1].split("private func renderProjects", 1)[0]
        self.assertIn("guard !retryPending else { return }", handler)
        self.assertLess(handler.index("retryPending = true"), handler.index("serviceQueue.async"))
        self.assertEqual(handler.count("self.retryPending = false"), 2)

    def test_reuse_display_requires_service_evidence_and_probe_is_isolated(self):
        source = (ROOT / "macos/IntegraApp.swift").read_text()
        self.assertIn('reuse["state"] as? String == "REUSED"', source)
        self.assertIn('dataRoot == directory + "/app-data"', source)
        self.assertIn('let allowedOutputs: Set<String> = retryProbe ? ["word_timeline"]', source)
        self.assertIn("retry.performClick(nil)", source)
        self.assertIn("native_asr_retry_probe.py", (ROOT / "scripts/test_macos_app.sh").read_text())
