"""Native K2 route contracts. Synthetic route tests are not semantic acceptance."""
import importlib.util
import json
import os
from pathlib import Path
import types
import unittest
from unittest.mock import Mock, patch
from tests import test_knowledge_notebook as fixture


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("k2_native_bridge", ROOT / "macos/Resources/bridge.py")
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


class KnowledgeK2BridgeRouteTests(unittest.TestCase):
    def setUp(self):
        self.ids = {"project_id": "project-exact", "run_id": "run-exact", "source_id": "source-exact"}
        self.project = Path("/synthetic/owned-project")
        self.adapter = types.ModuleType("integra_core.knowledge_k2")
        for name in ("open_knowledge", "prepare_knowledge", "apply_knowledge", "knowledge_navigation", "knowledge_package"):
            setattr(self.adapter, name, Mock(return_value={"synthetic_contract_test": True}))
        self.store = Mock()
        self.lease = {"project_id": self.ids["project_id"], "mutable_entity": {"entity_id": "k2-write"},
                      "lease_id": "lease-exact", "writer": {"component_id": "integra.knowledge_review"}, "generation": 1}
        for mocked in (
            patch.dict("sys.modules", {"integra_core.knowledge_k2": self.adapter}),
            patch.object(bridge, "_project", return_value={"project_id": self.ids["project_id"]}),
            patch.object(bridge, "_project_dir", return_value=self.project),
            patch.object(bridge, "_lease", return_value=(self.lease, self.store)),
            patch.object(bridge, "execute_run", side_effect=AssertionError("K2 cannot rerun Process")),
            patch.object(bridge, "_spawn_plan", side_effect=AssertionError("K2 cannot spawn generation")),
        ):
            mocked.start(); self.addCleanup(mocked.stop)

    def call(self, action, **request):
        return bridge._knowledge_k2(Path("/synthetic/app"), self.ids | request, action)

    def test_closed_operations_and_read_only_reopen(self):
        self.assertTrue({"knowledge-k2-open", "knowledge-k2-prepare", "knowledge-k2-apply",
                         "knowledge-k2-navigation", "knowledge-k2-package"}.issubset(bridge.OPERATIONS))
        self.call("open")
        self.adapter.open_knowledge.assert_called_once_with(self.project, **self.ids)
        bridge._lease.assert_not_called()
        self.adapter.prepare_knowledge.assert_not_called()
        self.adapter.apply_knowledge.assert_not_called()

    def test_prepare_forwards_exact_selected_fragments_and_current_k1_binding(self):
        self.call("prepare", notebook_id="notebook-exact", expected_state_sha256="a" * 64,
                  selected_fragment_ids=["fragment-exact"], relation_inputs=[], entity_edits=[])
        self.adapter.prepare_knowledge.assert_called_once_with(self.project, **self.ids,
            notebook_id="notebook-exact", expected_state_sha256="a" * 64,
            selected_fragment_ids=["fragment-exact"], relation_inputs=[], entity_edits=[])
        self.assertEqual(bridge._lease.call_args.args[2], "integra.knowledge_review")
        self.store.release.assert_called_once()

    def test_apply_preserves_each_explicit_decision_and_package_enumeration(self):
        decisions = [{"proposal_id": "one", "action": "REJECT", "reason": "synthetic rejection"},
                     {"proposal_id": "two", "action": "DEFER", "reason": "synthetic deferral"}]
        self.call("apply", package_sha256="b" * 64, decisions=decisions, reviewer_id="synthetic-reviewer",
                  explicit_confirmation=True, confirmed_proposal_ids=["one", "two"])
        self.adapter.apply_knowledge.assert_called_once_with(self.project, **self.ids,
            package_sha256="b" * 64, decisions=decisions, reviewer_id="synthetic-reviewer",
            explicit_confirmation=True, confirmed_proposal_ids=["one", "two"])
        self.store.release.assert_called_once()

    def test_missing_confirmation_is_never_invented(self):
        self.adapter.apply_knowledge.side_effect = ValueError("explicit semantic confirmation is required")
        with self.assertRaisesRegex(ValueError, "confirmation"):
            self.call("apply", package_sha256="b" * 64, decisions=[])
        self.assertIsNone(self.adapter.apply_knowledge.call_args.kwargs["explicit_confirmation"])
        self.assertIsNone(self.adapter.apply_knowledge.call_args.kwargs["confirmed_proposal_ids"])
        self.store.release.assert_called_once()

    def test_exact_navigation_is_read_only_and_revision_bound(self):
        self.call("navigation", revision_sha256="c" * 64, evidence_id="evidence-exact")
        self.adapter.knowledge_navigation.assert_called_once_with(self.project, **self.ids,
            revision_sha256="c" * 64, evidence_id="evidence-exact")
        bridge._lease.assert_not_called()

    def test_package_uses_shared_managed_store_and_never_publishes(self):
        manifest, files = {"package_id": "synthetic-package"}, {"view/note.md": b"Synthetic test only"}
        self.adapter.knowledge_package.return_value = manifest, files
        with patch.object(bridge, "_store_reviewed_package", return_value={"published": False}) as store, \
                patch.object(bridge, "_publication", side_effect=AssertionError("no automatic publication")):
            self.assertFalse(self.call("package", revision_sha256="d" * 64)["published"])
            store.assert_called_once_with(self.project, manifest, files)
        self.adapter.knowledge_package.assert_called_once_with(self.project, **self.ids, revision_sha256="d" * 64)
        self.store.release.assert_called_once()

    def test_native_ui_has_no_default_semantic_acceptance_and_confirmed_identity(self):
        source = (ROOT / "macos/IntegraApp.swift").read_text()
        review = source[source.index("@objc private func reviewCanonicalKnowledge()"):source.index("private func knowledgeRelationTitle")]
        self.assertIn('"Выберите решение", "Принять", "Изменить и принять", "Отклонить", "Отложить"', review)
        self.assertNotIn("action.selectItem(at:", review)
        self.assertIn("explicit.state = .off", review)
        self.assertIn('request["confirmed_proposal_ids"] = proposals.compactMap { $0["id"] as? String }.sorted()', review)
        self.assertIn('request["package_sha256"] = hash', review)
        self.assertIn('guard confirmationDialog.run() == .alertFirstButtonReturn', review)
        self.assertIn('guard explicit.state == .on else', review)
        self.assertNotIn('while true', review)
        self.assertLess(review.index('enumeration.addArrangedSubview(explicit)'), review.index('for decision in decisions'))
        self.assertIn("Машинный результат не становится человеческим или авторитетным", source)

    def test_native_ui_uses_owner_identity_without_exposing_technical_review_fields(self):
        source = (ROOT / "macos/IntegraApp.swift").read_text()
        review = source[source.index("@objc private func reviewCanonicalKnowledge()"):source.index("private func knowledgeRelationTitle")]
        presentation = source[source.index("private func knowledgeRecordText"):source.index("private func renderCanonicalKnowledge()")]
        render = source[source.index("private func renderCanonicalKnowledge()"):source.index("private func returnToKnowledgeNotebook()")]
        relation = source[source.index("@objc private func proposeKnowledgeRelation()"):source.index("private func playCanonicalKnowledgeEvidence")]
        self.assertIn('knowledgeOwnerReviewerID = "integra-local-owner"', source)
        self.assertIn('request["reviewer_id"] = knowledgeOwnerReviewerID', review)
        self.assertIn("Этот вопрос нельзя решить автоматически без риска изменить смысл", review)
        self.assertNotIn("ID проверяющего", review)
        self.assertNotIn("reviewer = NSTextField", review)
        self.assertNotIn("Пакет SHA-256", review)
        self.assertNotIn('knowledgeText(decision["proposal_id"])', review)
        self.assertNotIn("Происхождение предложения", presentation)
        self.assertNotIn("Возможные совпадения названий:", presentation)
        self.assertNotIn('knowledgeText(evidence["source_id"])', presentation)
        self.assertNotIn('knowledgeText(evidence["evidence_id"]', presentation)
        self.assertNotIn("Пакет предложений:", render)
        self.assertNotIn("Каноническая версия:", render)
        self.assertNotIn("Граф знаний ·", render)
        self.assertNotIn("ID понятий", relation)
        self.assertNotIn('concept["id"])', relation)

    def test_normal_path_requires_no_fragment_or_proposal_decision(self):
        source = (ROOT / "macos/IntegraApp.swift").read_text()
        notebook = source[source.index("private func renderKnowledgeNotebook()"):source.index("@objc private func reviewKnowledge()")]
        knowledge = source[source.index("private func renderCanonicalKnowledge()"):source.index("@objc private func returnToKnowledgeNotebook()")]
        self.assertIn('let machineReady = notebook["status"] as? String == "MACHINE_DERIVED_FRAGMENTS_V1"', notebook)
        self.assertIn("Готово — решений от вас не требуется", notebook)
        self.assertIn('if !humanReviewed && !machineReady { add(button("Решить смысловое исключение"', notebook)
        self.assertIn("Готово — решений от вас не требуется", knowledge)
        self.assertIn('add(button("Уточнить связь между понятиями"', knowledge)
        self.assertIn('action == "open", result["package_sha256"] as? String == nil', source)
        self.assertIn('self.prepareCanonicalKnowledge()', source)
        self.assertIn('let automaticCompleted = automaticReady && current["package_applied"] as? Bool == true', source)
        self.assertIn('if automaticCompleted {', source)

    def test_exception_path_hides_unrelated_machine_queue_from_the_product_surface(self):
        source = (ROOT / "macos/IntegraApp.swift").read_text()
        knowledge = source[source.index("private func renderCanonicalKnowledge()"):source.index("private func returnToKnowledgeNotebook()")]
        exception = knowledge[knowledge.index('if let questions = current["exception_questions"]'):
                              knowledge.index('if !automaticReady')]
        self.assertIn('add(button("Ответить на смысловой вопрос", #selector(reviewCanonicalKnowledge)))', exception)
        self.assertIn('status.stringValue = "Нужно ваше решение: \\(questions.count)"', exception)
        self.assertIn('return', exception)
        self.assertLess(knowledge.index('if let questions = current["exception_questions"]'),
                        knowledge.index('if !automaticReady'))


@unittest.skipUnless((fixture.PINNED / "seminartext_modules/human_review_workflow.py").is_file()
                     and (os.environ.get("INTEGRA_KNOWLEDGE_ADMISSION_CHECKOUT") or
                          (ROOT / "runtime/knowledge-admission/runtime.json").is_file()),
                     "requires exact pinned review and owner admission runtimes")
class KnowledgeK2RealBridgeTests(unittest.TestCase):
    """Actual owner contract; all semantic decisions here concern synthetic QA data."""
    write = fixture.KnowledgeNotebookTests.write
    open = fixture.KnowledgeNotebookTests.open
    choices = fixture.KnowledgeNotebookTests.choices
    save = fixture.KnowledgeNotebookTests.save

    def setUp(self):
        fixture.KnowledgeNotebookTests.setUp(self)
        self.app = self.root / "app"; self.app.mkdir()
        for mocked in (
            patch.object(bridge, "_project", return_value=json.loads((self.root / "project.json").read_bytes())),
            patch.object(bridge, "_project_dir", return_value=self.root),
            patch.object(bridge, "execute_run", side_effect=AssertionError("no upstream execution")),
            patch.object(bridge, "_spawn_plan", side_effect=AssertionError("no upstream provider")),
        ):
            mocked.start(); self.addCleanup(mocked.stop)
        opened = bridge._knowledge(self.app, self.ids | {"create": True}, "open")
        self.k1 = bridge._knowledge(self.app, self.ids | {
            "expected_state_sha256": opened["state_sha256"], "decisions": self.choices(opened),
            "reviewer_id": "synthetic-qa-k1-reviewer"}, "save")

    def call(self, action, **request):
        return bridge._knowledge_k2(self.app, self.ids | request, action)

    def test_real_owner_native_route_review_reopen_navigation_managed_package(self):
        opened = self.call("open")
        fragments = [item["id"] for item in opened["eligible_fragments"]]
        prepared = self.call("prepare", notebook_id=opened["notebook_id"],
            expected_state_sha256=opened["state_sha256"], selected_fragment_ids=fragments)
        concepts = [item for item in prepared["proposals"] if item["entity_kind"] == "concepts"]
        relation = {"source_concept_id": concepts[0]["after"]["id"],
                    "target_concept_id": concepts[1]["after"]["id"], "relation_type": "associated_with",
                    "fragment_ids": fragments}
        prepared = self.call("prepare", notebook_id=opened["notebook_id"],
            expected_state_sha256=opened["state_sha256"], selected_fragment_ids=fragments,
            relation_inputs=[relation])
        decisions = []
        topic_index = 0
        for proposal in prepared["proposals"]:
            action = "ACCEPT"
            if proposal["entity_kind"] == "topics":
                action = "REJECT" if topic_index == 0 else "DEFER"; topic_index += 1
            decision = {"proposal_id": proposal["id"], "action": action,
                        "reason": "Synthetic QA decision only; no production semantic authority"}
            if proposal["entity_kind"] == "concepts" and not any(item["action"] == "EDIT" for item in decisions):
                decision.update(action="EDIT", edited_fields={"preferred_label": "Synthetic QA edited label"})
            decisions.append(decision)
        accepted = self.call("apply", package_sha256=prepared["package_sha256"], decisions=decisions,
            reviewer_id="synthetic-qa-k2-reviewer", explicit_confirmation=True,
            confirmed_proposal_ids=sorted(item["id"] for item in prepared["proposals"]))
        self.assertEqual(accepted["status"], "CANONICAL_KNOWLEDGE")
        self.assertTrue(accepted["package_applied"])
        self.assertEqual(len(accepted["knowledge_view"]["records"]["concepts"]), 2)
        self.assertEqual(len(accepted["knowledge_view"]["records"]["relations"]), 1)
        self.assertEqual(accepted["knowledge_view"]["records"]["topics"], [])
        self.assertEqual(self.call("open"), accepted)
        evidence = prepared["proposals"][0]["evidence"][0]
        navigation = self.call("navigation", revision_sha256=accepted["revision_sha256"],
                               evidence_id=evidence["evidence_id"])
        self.assertEqual(navigation["quote"], evidence["quote"])
        self.assertEqual(navigation["fragment_id"], evidence["id"])
        package = self.call("package", revision_sha256=accepted["revision_sha256"])
        manifest, files = bridge._package(package["package_dir"])
        self.assertEqual(manifest["result_kind"], "CANONICAL_KNOWLEDGE_ADMISSION_V1")
        self.assertFalse(package["published"])
        self.assertTrue(any(b"integra://knowledge/fragment?" in content for name, content in files.items() if name.endswith(".md")))
        vault = self.root / "vault"; vault.mkdir()
        preview = bridge._publication(self.app, {"package_dir": package["package_dir"],
            "target_dir": str(vault), "publication_target": "obsidian"}, False)
        self.assertEqual(preview["state"], "DRY_RUN")
        self.assertEqual(list(vault.iterdir()), [])
        self.assertEqual(self.run_file.read_bytes(), self.run_before)

    def test_unconfirmed_package_does_not_create_canonical_revision(self):
        opened = self.call("open")
        prepared = self.call("prepare", notebook_id=opened["notebook_id"],
            expected_state_sha256=opened["state_sha256"],
            selected_fragment_ids=[item["id"] for item in opened["eligible_fragments"]])
        with self.assertRaisesRegex(ValueError, "explicit confirmation"):
            self.call("apply", package_sha256=prepared["package_sha256"], decisions=[],
                reviewer_id="synthetic-qa-k2-reviewer", explicit_confirmation=False,
                confirmed_proposal_ids=prepared["confirmed_proposal_ids"])
        self.assertIsNone(self.call("open")["revision_sha256"])


class KnowledgeK2PackagedSchemaBridgeTests(KnowledgeK2RealBridgeTests):
    """Real apply/reopen/export with packaged schema lookup, no repo fallback."""

    def setUp(self):
        super().setUp()
        import shutil
        from integra_core import knowledge
        from scripts.package_knowledge_admission_runtime import package_view_schema
        resources = self.root / "schema-layout/Contents/Resources"
        package_view_schema(resources)
        shutil.copytree(ROOT / "integra_core/_vendor", resources / "integra_core/_vendor",
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        projection = patch.object(knowledge, "__file__", str(resources / "integra_core/knowledge.py"))
        projection.start()
        self.addCleanup(projection.stop)


if __name__ == "__main__":
    unittest.main()
