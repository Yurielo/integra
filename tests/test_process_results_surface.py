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
        self.assertIn('button("Открыть источник с расшифровкой"', self.source)

    def test_only_readable_translation_or_reviewable_topics_can_be_primary(self):
        surface = self.source.split("private func renderPrimaryProcessResults", 1)[1].split(
            "private func readableOutput", 1)[0]
        self.assertIn('keys: ["translation_txt", "translated_txt"]', surface)
        self.assertIn('outputs["topics"] is String', surface)
        self.assertIn('button("Проверить темы", #selector(prepareTopicReview(_:)))', surface)
        self.assertNotIn('outputs["translation"] as? String', surface)
        self.assertNotIn('outputs["topics"] as? String', surface)

    def test_translation_target_is_explicit_and_bound_to_the_plan(self):
        self.assertIn('private var translationTargetLanguage = "en"', self.source)
        self.assertIn('add(row("Язык перевода"', self.source)
        self.assertIn('request["translation_target_language"] = translationTargetLanguage', self.source)

    def test_reviewable_topics_use_process_only_review_path(self):
        review = self.source.split("@objc private func prepareTopicReview", 1)[1].split(
            "private func presentTopicReview", 1)[0]
        self.assertIn('bridge.json("prepare-process-topic-review"', review)
        self.assertIn('reviewStatus == "PROCESS_TOPIC_REVIEW_REQUIRED" || reviewStatus == "PROCESS_TOPIC_REVIEWED"', review)
        self.assertNotIn("create-machine-evidence", review)
        self.assertNotIn("knowledge-review", review)
        self.assertIn('self.presentTopicReview(result, identifiers: identifiers, readOnly: reviewStatus == "PROCESS_TOPIC_REVIEWED")', review)
        self.assertIn('sender.title = "Проверить темы"', review)

    def test_process_topic_dialog_uses_pinned_actions_without_knowledge_wording(self):
        dialog = self.source.split("private func presentTopicReview", 1)[1].split(
            "private func presentProcessTopicReviewLegacy", 1)[0]
        self.assertIn('"ACCEPT", "RENAME", "REJECT", "DEFER"', dialog)
        self.assertIn('bridge.json("apply-process-topic-review"', dialog)
        self.assertIn("Проверка тем", dialog)
        self.assertIn('selectedAction == "ACCEPT" && edited ? "RENAME" : selectedAction', dialog)
        self.assertIn('Сохранённые решения человека для этого источника.', dialog)
        self.assertIn('title.isEditable = false; summary.isEditable = false', dialog)
        self.assertNotIn("Идентификатор проверяющего", dialog)
        self.assertNotIn('"reviewer_id": reviewerID', dialog)
        for forbidden in ("Canonical Knowledge", "Включить фрагмент в знания", "Evidence", "семантическ"):
            self.assertNotIn(forbidden, dialog)

    def test_technical_artifacts_are_secondary_and_knowledge_actions_are_not_primary(self):
        render = self.source.split("private func renderResultRows", 1)[1].split(
            "private func renderPrimaryProcessResults", 1)[0]
        self.assertIn("renderTechnicalData(outputs)", render)
        self.assertNotIn("Проверить TXT и создать Evidence", render)
        self.assertNotIn("Подготовить темы к проверке", render)
        self.assertIn("final class TechnicalDisclosure", self.source)
        self.assertIn('checkboxWithTitle: "Технические данные"', self.source)

    def test_publication_actions_are_not_rendered_in_process_results(self):
        outputs = self.source.split("private func renderOutputs()", 1)[1].split(
            "@objc private func publishObsidian", 1)[0]
        self.assertNotIn("ПУБЛИКАЦИЯ ПРОВЕРЕННОГО PACKAGE", outputs)
        self.assertNotIn("Экспортировать в Obsidian", outputs)
        self.assertNotIn("Опубликовать в папку OneDrive", outputs)
        # The underlying reviewed-package implementation remains available to
        # its future Knowledge/Studio surface; this bounded Process change
        # only removes its normal-results entry point.
        self.assertIn("@objc private func publishObsidian", self.source)
        self.assertIn("@objc private func publishOneDrive", self.source)

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
