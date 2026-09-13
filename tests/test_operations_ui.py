"""Static architecture guards; native_operations_probe supplies runtime evidence."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class OperationsUITests(unittest.TestCase):
    def setUp(self):
        self.source = (ROOT / "macos/IntegraApp.swift").read_text()

    def test_polling_has_separate_queue_and_stale_response_guards(self):
        poll = self.source.split("private func pollOperations()", 1)[1].split("private func renderOperationsSnapshot", 1)[0]
        self.assertIn("operationsQueue.async", poll)
        self.assertIn("operationsRequestID == nil", poll)
        self.assertEqual(poll.count("self.operationsRequestID == requestID"), 2)
        self.assertEqual(poll.count("self.navigationGeneration == generation"), 2)
        self.assertEqual(poll.count("self.projectID == p, self.runID == r"), 2)
        self.assertIn('displayed["cancel_pending"]', poll)
        self.assertIn('displayed["retry_pending"]', poll)
        self.assertNotIn('"updated_at"', poll)
        self.assertNotIn('"progress"', poll)

    def test_cancel_is_async_and_duplicate_guarded(self):
        cancel = self.source.split("@objc private func cancelRun()", 1)[1].split("@objc private func retryRun()", 1)[0]
        self.assertIn("guard !cancelPending, !terminationPending", cancel)
        self.assertLess(cancel.index("cancelPending = true"), cancel.index("serviceQueue.async"))
        self.assertIn("control.isEnabled = false", cancel)
        self.assertIn("self.navigationGeneration == generation", cancel)

    def test_no_fake_percentage_and_native_probe_in_build_checks(self):
        render = self.source.split("private func renderOperationsSnapshot", 1)[1].split("private func renderResultRows", 1)[0]
        self.assertNotIn('run["progress"]', render)
        self.assertIn("self?.pollOperations()", render)
        self.assertIn("native_operations_probe.py", (ROOT / "scripts/test_macos_app.sh").read_text())
        self.assertIn("performKeyEquivalent(with: event)", self.source)
        self.assertIn("#selector(NSApplication.terminate(_:))", self.source)


if __name__ == "__main__":
    unittest.main()
