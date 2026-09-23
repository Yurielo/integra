from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class TranscriptReviewUITests(unittest.TestCase):
    def test_process_ui_exposes_only_topic_review_and_excludes_other_knowledge_controls(self):
        source = (ROOT / "macos" / "IntegraApp.swift").read_text(encoding="utf-8")
        # Review/Evidence belongs to Knowledge, not to the primary Process
        # result surface. The local bridge contract remains bundled for the
        # later Knowledge phase; removing a Process control must not erase it.
        process_results = source.split("private func renderPrimaryProcessResults", 1)[1].split(
            "private func readableOutput", 1)[0]
        self.assertNotIn("Проверить TXT и создать Evidence", process_results)
        self.assertNotIn("Я проверил(а) весь TXT", process_results)
        self.assertIn('button("Проверить темы", #selector(prepareTopicReview(_:)))', process_results)
        self.assertNotIn("Canonical Evidence", process_results)
        self.assertNotIn("Knowledge Base", process_results)
        self.assertIn('bridge.json("prepare-transcript-review"', source)
        self.assertIn('bridge.json("apply-transcript-review"', source)
        self.assertIn('bridge.json("prepare-knowledge-review"', source)
        self.assertIn('bridge.json("apply-knowledge-review"', source)
        allowed = source.split("let allowed = [", 1)[1].split("]", 1)[0]
        for operation in ("prepare-transcript-review", "apply-transcript-review", "prepare-knowledge-review", "apply-knowledge-review"):
            self.assertIn('"' + operation + '"', allowed)

    def test_build_packages_the_exact_pinned_evidence_component(self):
        build = (ROOT / "scripts" / "build_macos_app.sh").read_text(encoding="utf-8")
        self.assertIn("evidence_foundation.py", build)
        self.assertIn("validate_canonical_evidence_v1.py", build)
        self.assertIn("6adcf15e9767c36ad2d0dfe3a6a995d90c41b5f1671b4c9434a4b48f590e3856", build)


if __name__ == "__main__":
    unittest.main()
