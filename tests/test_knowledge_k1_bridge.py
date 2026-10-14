"""Independent K1 bridge regressions using the real pinned review adapter.

Synthetic artifacts here exercise contracts only; they are not native acceptance.
"""
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fixture = _load("k1_contract_fixture", ROOT / "tests/test_knowledge_notebook.py")
bridge = _load("k1_native_bridge", ROOT / "macos/Resources/bridge.py")
notebook = fixture.notebook


@unittest.skipUnless((fixture.PINNED / "seminartext_modules/human_review_workflow.py").is_file(),
                     "requires exact pinned review runtime")
class KnowledgeK1BridgeTests(unittest.TestCase):
    write = fixture.KnowledgeNotebookTests.write
    open = fixture.KnowledgeNotebookTests.open
    choices = fixture.KnowledgeNotebookTests.choices
    save = fixture.KnowledgeNotebookTests.save

    def setUp(self):
        fixture.KnowledgeNotebookTests.setUp(self)
        self.app = self.root / "app"
        self.app.mkdir()
        self.project = json.loads((self.root / "project.json").read_bytes())
        for name, value in (("_project_dir", self.root), ("_project", self.project)):
            mocked = patch.object(bridge, name, return_value=value)
            mocked.start()
            self.addCleanup(mocked.stop)

    def call(self, action, **request):
        return bridge._knowledge(self.app, self.ids | request, action)

    def test_discovery_does_not_reconcile_or_prepare_missing_upstream(self):
        item = {"project": self.project, "run": json.loads(self.run_file.read_bytes())}
        with patch.object(bridge, "_recent_runs", return_value=[item]) as runs, \
                patch.object(bridge, "_reconcile_stale", side_effect=AssertionError("no job reconciliation")), \
                patch.object(notebook, "create_machine_evidence", side_effect=AssertionError("no Evidence preparation")), \
                patch.object(bridge, "execute_run", side_effect=AssertionError("no Process execution")):
            found = bridge._knowledge_sources(self.app)
        runs.assert_called_once_with(self.app, reconcile=False)
        self.assertTrue(found[0]["eligible"])
        self.assertEqual(found[0]["notebook_status"], "NOT_ADDED")
        self.assertEqual(self.run_file.read_bytes(), self.run_before)
        self.assertFalse((self.root / "evidence").exists())

    def test_bridge_defer_edit_reopen_package_never_reruns_process(self):
        with patch.object(bridge, "execute_run", side_effect=AssertionError("no Process")), \
                patch.object(bridge, "_spawn_plan", side_effect=AssertionError("no provider job")):
            opened = self.call("open", create=True)
            choices = self.choices(opened)
            choices[0]["action"] = "DEFER"
            deferred = self.call("save", expected_state_sha256=opened["state_sha256"],
                                 decisions=choices, reviewer_id="bridge-reviewer")
            self.assertEqual(deferred["status"], "REVIEW_REQUIRED")
            self.assertEqual(self.call("open"), deferred)
            with self.assertRaisesRegex(ValueError, "deferred"):
                self.call("package")
            choices[0].update(action="EDIT", new_title="Изменённый конспект", new_summary="Решение человека")
            reviewed = self.call("save", expected_state_sha256=deferred["state_sha256"],
                                 decisions=choices, reviewer_id="bridge-reviewer")
            self.assertEqual(reviewed["status"], "REVIEWED_FRAGMENTS_V2")
            self.assertEqual(self.call("open"), reviewed)
            package = self.call("package")
            manifest, files = bridge._package(package["package_dir"])
            self.assertEqual(manifest["result_kind"], "REVIEWED_FRAGMENTS_V2")
            self.assertIn(b"integra://knowledge/fragment?", files["view/notebook.md"])
            self.assertEqual(self.call("package"), package)
        self.assertEqual(self.run_file.read_bytes(), self.run_before)
        self.assertFalse(list(self.root.rglob("canonical_knowledge.json")))

    def test_existing_evidence_must_bind_the_current_saved_timeline(self):
        evidence = notebook.create_machine_evidence(self.root, source_id=self.ids["source_id"],
            media_path=str(self.media), transcript_path=str(self.text), word_timeline_path=str(self.timeline))
        record = json.loads(self.run_file.read_bytes())
        record["source_results"][0]["outputs"]["canonical_evidence"] = evidence["canonical_evidence_path"]
        self.write(self.run_file, record)
        changed = json.loads(self.timeline.read_bytes())
        for word in changed["words"]:
            word["start_seconds"] += 10
            word["end_seconds"] += 10
        self.write(self.timeline, changed)
        with self.assertRaises(ValueError):
            self.call("open", create=True)

    def test_exported_navigation_rejects_wrong_notebook_revision(self):
        opened = self.call("open", create=True)
        reviewed = self.call("save", expected_state_sha256=opened["state_sha256"],
                             decisions=self.choices(opened), reviewer_id="bridge-reviewer")
        fragment = reviewed["reviewed"]["fragment_lineage"][0]
        request = {"fragment_id": fragment["id"], "source_revision_sha256": opened["source_revision_sha256"],
                   "notebook_id": "urn:integra:artifact:00000000-0000-0000-0000-000000000000"}
        with self.assertRaises(ValueError):
            self.call("navigation", **request)

    def test_exported_navigation_rejects_changed_source_revision(self):
        opened = self.call("open", create=True)
        with self.assertRaisesRegex(ValueError, "different source revision"):
            self.call("navigation", fragment_id=opened["topics"][0]["id"],
                      source_revision_sha256="0" * 64)

    def discovery(self):
        item = {"project": self.project, "run": json.loads(self.run_file.read_bytes())}
        with patch.object(bridge, "_recent_runs", return_value=[item]), \
                patch.object(bridge, "_reconcile_stale", side_effect=AssertionError("no reconciliation")), \
                patch.object(notebook, "create_machine_evidence", side_effect=AssertionError("no Evidence regeneration")):
            return bridge._knowledge_sources(self.app)[0]

    def test_saved_notebook_remains_visible_when_source_missing_or_stale(self):
        opened = self.call("open", create=True)
        before = self.media.read_bytes()
        self.media.unlink()
        unavailable = self.discovery()
        self.assertFalse(unavailable["eligible"])
        self.assertFalse(unavailable["notebook_available"])
        self.assertEqual(unavailable["notebook_id"], opened["notebook_id"])
        self.assertEqual(unavailable["notebook_status"], "MACHINE_DERIVED_FRAGMENTS_V1")
        self.assertIn("reason", unavailable)
        self.media.write_bytes(before)
        self.media.write_bytes(before + b"changed")
        stale = self.discovery()
        self.assertEqual(stale["notebook_id"], opened["notebook_id"])
        self.assertFalse(stale["notebook_available"])
        self.assertIn("hash/revision", stale["reason"])
        self.assertEqual(self.run_file.read_bytes(), self.run_before)

    def test_saved_prior_notebook_is_not_mistaken_for_current_revision(self):
        opened = self.call("open", create=True)
        self.topics.write_bytes(self.topics.read_bytes() + b" ")
        found = self.discovery()
        self.assertTrue(found["eligible"])
        self.assertFalse(found["notebook_available"])
        self.assertEqual(found["notebook_id"], opened["notebook_id"])
        self.assertEqual(found["saved_notebook_count"], 1)
        self.assertIn("артефакты Process изменились", found["reason"])

    def test_invalid_saved_receipt_stays_visible_but_never_available(self):
        opened = self.call("open", create=True)
        path = notebook._state_path(self.root, self.ids["source_id"], opened["notebook_id"])
        state = json.loads(path.read_bytes())
        state["status"] = "REVIEWED_FRAGMENTS_V2"
        self.write(path, state)
        found = self.discovery()
        self.assertEqual(found["notebook_status"], "UNAVAILABLE")
        self.assertFalse(found["notebook_available"])
        self.assertIn("receipt", found["reason"])

    def test_material_title_revisions_and_assurance_come_from_persisted_contracts(self):
        record = json.loads(self.run_file.read_bytes())
        record["source_results"][0]["display_name"] = "Публичная демонстрационная запись"
        self.write(self.run_file, record)
        opened = self.call("open", create=True)
        self.assertEqual(opened["source_title"], "Публичная демонстрационная запись")
        self.assertEqual(opened["source_processing_state"], "COMPLETED")
        self.assertEqual(opened["topics_revision_sha256"], notebook._sha256(self.topics))
        self.assertEqual(opened["transcript_artifact_sha256"], notebook._sha256(self.text))
        self.assertEqual(opened["transcript_revisions"][0]["transcript_provenance"]["verification_state"], "machine_unverified")
        self.assertEqual(self.call("open"), opened)


if __name__ == "__main__":
    unittest.main()
