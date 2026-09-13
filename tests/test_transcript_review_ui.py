from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class TranscriptReviewUITests(unittest.TestCase):
    def test_native_ui_exposes_explicit_txt_review_without_automatic_acceptance(self):
        source = (ROOT / "macos" / "IntegraApp.swift").read_text(encoding="utf-8")
        self.assertIn("Проверить TXT и создать Evidence", source)
        self.assertIn("Я проверил(а) весь TXT", source)
        self.assertIn("NSSound.beep()", source)
        self.assertIn('bridge.json("prepare-transcript-review"', source)
        self.assertIn('bridge.json("apply-transcript-review"', source)
        self.assertIn("Эти границы тем — В разработке", source)
        self.assertIn("Подготовить темы к проверке", source)
        self.assertIn('bridge.json("prepare-knowledge-review"', source)
        self.assertIn('bridge.json("apply-knowledge-review"', source)
        self.assertIn('"Выберите решение", "Принять", "Отклонить"', source)
        self.assertIn('"expected_request_sha256": requestHash', source)
        self.assertIn("Подтверждаю точные границы показанных цитат", source)
        self.assertIn("Включить фрагмент в знания", source)
        self.assertIn("Исключить фрагмент из знаний", source)
        self.assertIn("Прослушать цитату", source)
        self.assertIn("forwardPlaybackEndTime", source)
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
