from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ProcessResultsSurfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "macos" / "IntegraApp.swift").read_text(encoding="utf-8")

    def test_primary_surface_is_responsive_and_user_facing(self):
        self.assertIn("final class ResponsiveResultsGrid", self.source)
        self.assertIn("wideBreakpoint: CGFloat = 720", self.source)
        self.assertIn("? .horizontal : .vertical", self.source)
        self.assertIn('add(grid)\n      // `content` aligns arranged subviews', self.source)
        self.assertIn('grid.widthAnchor.constraint(equalTo: content.widthAnchor, constant: -76)', self.source)
        for label in ("Расшифровка", "Очищенный текст", "Перевод", "Темы и таймкоды"):
            self.assertIn(f'processCard("{label}"', self.source)
        self.assertIn('button("Открыть видео/аудио с расшифровкой"', self.source)

    def test_only_readable_translation_or_topics_can_be_primary(self):
        surface = self.source.split("private func renderPrimaryProcessResults", 1)[1].split(
            "private func readableOutput", 1)[0]
        self.assertIn('keys: ["translation_txt", "translated_txt"]', surface)
        self.assertIn('keys: ["topics_txt", "topics_markdown"]', surface)
        self.assertNotIn('outputs["translation"] as? String', surface)
        self.assertNotIn('outputs["topics"] as? String', surface)

    def test_technical_artifacts_are_secondary_and_knowledge_actions_are_not_primary(self):
        render = self.source.split("private func renderResultRows", 1)[1].split(
            "private func renderPrimaryProcessResults", 1)[0]
        self.assertIn("renderTechnicalData(outputs)", render)
        self.assertNotIn("Проверить TXT и создать Evidence", render)
        self.assertNotIn("Подготовить темы к проверке", render)
        self.assertIn("final class TechnicalDisclosure", self.source)
        self.assertIn('checkboxWithTitle: "Технические данные"', self.source)

    def test_export_uses_native_save_panel_and_never_mutates_managed_source(self):
        export = self.source.split("private func exportManagedFile", 1)[1].split(
            "@objc private func showMediaNavigation", 1)[0]
        self.assertIn("NSSavePanel()", export)
        self.assertIn("guard panel.runModal() == .OK", export)
        self.assertIn("FileManager.default.copyItem(at: source, to: destination)", export)
        self.assertIn("FileManager.default.fileExists(atPath: destination.path)", export)
        self.assertNotIn("removeItem", export)
        self.assertNotIn("moveItem", export)

    def test_transcript_uses_existing_managed_text_resolver_for_open_and_export(self):
        self.assertIn('bridge.json("transcript-text"', self.source)
        self.assertIn("@objc private func exportTranscript", self.source)
        self.assertIn('button("Экспортировать…", #selector(exportTranscript(_:)))', self.source)


if __name__ == "__main__":
    unittest.main()
