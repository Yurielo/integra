"""Synthetic explicit K2 decisions over real pinned K1 and owner admission.

These tests demonstrate mechanics, never real Product Owner semantic acceptance.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from integra_core import knowledge_k2 as k2
from integra_core import knowledge_admission_runtime as runtime
from integra_core.knowledge import KnowledgeError, build_knowledge_view, PINNED_REVIEWED_KNOWLEDGE_ARTIFACTS
from integra_core.reviewed_result_package import validate_reviewed_result_package
from integra_core.publishing import preview_obsidian_export, PublishingError
from tests import test_knowledge_notebook as k1_tests

ROOT = Path(__file__).resolve().parents[1]
ADMISSION = Path(os.environ.get("INTEGRA_KNOWLEDGE_ADMISSION_CHECKOUT", ROOT / "runtime/knowledge-admission"))
PINNED = k1_tests.PINNED


@unittest.skipUnless((PINNED / "seminartext_modules/human_review_workflow.py").is_file()
    and (ADMISSION / "seminartext_modules/reviewed_knowledge_admission.py").is_file()
    and runtime.PIN_PATH.is_file(), "requires exact pinned review and admission runtimes")
class KnowledgeK2Tests(unittest.TestCase):
    setUp = k1_tests.KnowledgeNotebookTests.setUp
    write = k1_tests.KnowledgeNotebookTests.write
    open = k1_tests.KnowledgeNotebookTests.open
    choices = k1_tests.KnowledgeNotebookTests.choices
    save = k1_tests.KnowledgeNotebookTests.save

    def reviewed(self):
        opened = self.open(create=True)
        return self.save(opened, self.choices(opened))

    def prepare(self, opened=None, **kwargs):
        opened = opened or self.reviewed()
        return k2.prepare_knowledge(self.root, **self.ids, notebook_id=opened["notebook_id"],
            expected_state_sha256=opened["state_sha256"],
            selected_fragment_ids=[item["id"] for item in opened["reviewed"]["fragment_lineage"]], **kwargs)

    def decisions(self, prepared, actions=None):
        return [{"proposal_id": item["id"], "action": (actions or {}).get(item["entity_kind"], "ACCEPT"),
                 "reason": "Explicit synthetic test decision; no product semantic acceptance"} for item in prepared["proposals"]]

    def apply(self, prepared, decisions=None, **overrides):
        arguments = {"package_sha256": prepared["package_sha256"], "decisions": decisions if decisions is not None else self.decisions(prepared),
            "reviewer_id": "synthetic-human", "explicit_confirmation": True,
            "confirmed_proposal_ids": prepared["confirmed_proposal_ids"], **overrides}
        return k2.apply_knowledge(self.root, **self.ids, **arguments)

    def revision_path(self, opened):
        base = k2._inputs(self.root, self.ids)[1]
        return base / "revisions" / (opened["revision_sha256"] + ".json")

    def test_owner_admission_reopen_exact_navigation_graph_terms_and_source_assurance(self):
        reviewed = self.reviewed()
        initial = k2.open_knowledge(self.root, **self.ids)
        self.assertIsNone(initial["revision_sha256"])
        self.assertFalse(initial["automatic_acceptance"])
        prepared = self.prepare(reviewed)
        self.assertEqual(len(prepared["proposals"]), 4)
        self.assertTrue(all(item["after"]["status"] == "PROVISIONAL" for item in prepared["proposals"]))
        self.assertIsNone(prepared["knowledge_view"])
        accepted = self.apply(prepared)
        view = accepted["knowledge_view"]
        self.assertEqual(view["semantic_authority"], "READ_ONLY_SOURCE_LIFECYCLE")
        self.assertEqual(len(view["records"]["concepts"]), 2)
        self.assertEqual(len(view["records"]["topics"]), 2)
        self.assertEqual(len(view["terms"]), 2)
        self.assertIsNone(accepted["diff"]["before_view_id"])
        self.assertTrue(any(item["kind"] == "CONCEPT" for item in accepted["diff"]["added_ids"]))
        self.assertTrue(any(item["kind"] == "SUPPORTED_BY" for item in view["graph"]["edges"]))
        self.assertTrue(all(item["transcript_assurance"]["provenance"]["verification_state"] == "machine_unverified" for item in view["evidence"]))
        with patch.object(k2, "prepare_knowledge", side_effect=AssertionError("must not regenerate")), patch("integra_core.application_runtime.execute_run", side_effect=AssertionError("must not process")):
            self.assertEqual(k2.open_knowledge(self.root, **self.ids), accepted)
        for evidence in view["evidence"]:
            navigation = k2.knowledge_navigation(self.root, **self.ids, revision_sha256=accepted["revision_sha256"], evidence_id=evidence["id"])
            self.assertEqual(navigation["quote"], evidence["quote"])
            self.assertEqual(navigation["word_start_id"], evidence["word_start_id"])
            self.assertEqual(navigation["start_seconds"], evidence["locator"]["start_seconds"])
        self.assertEqual(self.run_before, self.run_file.read_bytes())
        revision = json.loads(self.revision_path(accepted).read_bytes())
        runtime.owner().validate_revision(revision, k2._inputs(self.root, self.ids)[3])
        self.assertEqual(revision["owner"], "seminartext")

    def test_reject_defer_immutable_parent_label_edit_and_existing_diff(self):
        reviewed = self.reviewed()
        prepared = self.prepare(reviewed)
        deferred = self.apply(prepared, self.decisions(prepared, {"concepts": "DEFER", "topics": "REJECT"}))
        self.assertEqual(deferred["knowledge_view"]["records"]["concepts"], [])
        self.assertEqual(deferred["knowledge_view"]["records"]["topics"], [])
        self.assertEqual({item["action"] for item in deferred["semantic_decisions"]}, {"DEFER", "REJECT"})
        self.assertEqual(k2.open_knowledge(self.root, **self.ids), deferred)
        old_path = self.revision_path(deferred); old_bytes = old_path.read_bytes()
        prepared = self.prepare(reviewed)
        accepted = self.apply(prepared)
        self.assertEqual(accepted["parent_revision_sha256"], deferred["revision_sha256"])
        self.assertEqual(old_path.read_bytes(), old_bytes)
        self.assertTrue(any(item["kind"] == "CONCEPT" for item in accepted["diff"]["added_ids"]))
        prepared = self.prepare(reviewed)
        choices = self.decisions(prepared)
        target = next(item for item in prepared["proposals"] if item["entity_kind"] == "concepts")
        choice = next(item for item in choices if item["proposal_id"] == target["id"])
        choice.update(action="EDIT", edited_fields={"preferred_label": "Явно исправленный термин", "aliases": [target["after"]["preferred_label"]]})
        edited = self.apply(prepared, choices)
        concept = next(item for item in edited["knowledge_view"]["records"]["concepts"] if item["id"] == target["after"]["id"])
        self.assertEqual(concept["version"], 2)
        self.assertEqual(concept["preferred_label"], "Явно исправленный термин")
        self.assertTrue(any(item["kind"] == "CONCEPT" for item in edited["diff"]["changed_ids"]))

    def test_explicit_relation_has_exact_evidence_and_controlled_type(self):
        reviewed = self.reviewed(); first = self.prepare(reviewed)
        concepts = first["available_concepts"]
        relation = {"source_concept_id": concepts[0]["id"], "target_concept_id": concepts[1]["id"],
                    "relation_type": "associated_with", "fragment_ids": [first["eligible_fragments"][0]["id"]]}
        prepared = self.prepare(reviewed, relation_inputs=[relation])
        accepted = self.apply(prepared)
        self.assertEqual(accepted["knowledge_view"]["records"]["relations"][0]["relation_type"], "associated_with")
        self.assertTrue(any(item["kind"] == "RELATION_SOURCE" for item in accepted["knowledge_view"]["graph"]["edges"]))
        relation["relation_type"] = "invented_type"
        with self.assertRaisesRegex(ValueError, "unsupported Relation"):
            self.prepare(reviewed, relation_inputs=[relation])

    def test_missing_decisions_hidden_confirmation_invalid_edits_and_stale_package_fail(self):
        prepared = self.prepare()
        for overrides in ({"explicit_confirmation": False}, {"confirmed_proposal_ids": prepared["confirmed_proposal_ids"][:-1]},
                          {"decisions": []}, {"reviewer_id": ""}, {"package_sha256": "f"*64}):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                self.apply(prepared, **overrides)
        choices = self.decisions(prepared)
        choices[0].update(action="EDIT", edited_fields={"id": "concept_wrong_identity"})
        with self.assertRaises(ValueError):
            self.apply(prepared, choices)
        self.assertIsNone(k2.open_knowledge(self.root, **self.ids)["revision_sha256"])
        accepted = self.apply(prepared)
        with self.assertRaisesRegex(ValueError, "already applied"):
            self.apply(prepared)
        self.assertEqual(k2.open_knowledge(self.root, **self.ids), accepted)

    def test_changed_source_notebook_fragment_and_missing_evidence_fail_closed(self):
        reviewed = self.reviewed(); prepared = self.prepare(reviewed)
        original = self.media.read_bytes(); self.media.write_bytes(original + b"changed")
        with self.assertRaises(ValueError): self.apply(prepared)
        self.media.write_bytes(original)
        notebook_state = k2.k1._read_state(k2.k1._state_path(self.root, self.ids["source_id"], reviewed["notebook_id"]), self.root)
        reviewed_path = self.root / notebook_state["review_artifacts"]["reviewed_topics"]["path"]
        reviewed_bytes = reviewed_path.read_bytes(); changed = json.loads(reviewed_bytes)
        changed["fragment_lineage"][0]["word_end_id"] = changed["fragment_lineage"][0]["word_start_id"]
        reviewed_path.write_bytes(runtime.canonical_bytes(changed))
        with self.assertRaisesRegex(ValueError, "hash/receipt"):
            self.apply(prepared)
        reviewed_path.write_bytes(reviewed_bytes)
        with self.assertRaises(ValueError):
            k2.prepare_knowledge(self.root, **self.ids, notebook_id=reviewed["notebook_id"], expected_state_sha256="f"*64,
                                 selected_fragment_ids=[prepared["eligible_fragments"][0]["id"]])
        with self.assertRaises(ValueError):
            k2.prepare_knowledge(self.root, **self.ids, notebook_id=reviewed["notebook_id"], expected_state_sha256=reviewed["state_sha256"],
                                 selected_fragment_ids=["fragment_missing"])
        root, base, opened, evidence, _ = k2._inputs(self.root, self.ids)
        path = base / "packages" / (prepared["package_sha256"] + ".json")
        payload = path.read_bytes(); package = json.loads(payload)
        package["proposals"][0]["record"]["evidence_refs"] = []
        choices = {"schema_version": "1.0.0", "package_id": package["artifact_id"], "package_sha256": runtime.digest(package),
            "reviewer": {"actor_type": "human_domain_reviewer", "actor_id": "synthetic-human"}, "explicit_confirmation": True,
            "confirmed_proposal_ids": sorted(item["id"] for item in package["proposals"]),
            "decisions": [{"proposal_id": item["id"], "proposal_sha256": runtime.digest(item), "action": "ACCEPT",
                "reason": "Synthetic owner rejection test only", "timestamp": "2026-10-09T09:00:00Z"} for item in package["proposals"]]}
        with self.assertRaisesRegex(ValueError, "Evidence binding"):
            runtime.owner().compile_revision(evidence, reviewed_bytes, package, choices)
        path.write_bytes(runtime.canonical_bytes(package))
        with self.assertRaisesRegex(ValueError, "checksum"):
            self.apply(prepared)
        path.write_bytes(payload)
        accepted = self.apply(prepared)
        path = self.revision_path(accepted); original = path.read_bytes(); revision = json.loads(original)
        revision["semantic_decisions"][0]["reason"] = "tampered"
        path.write_bytes(runtime.canonical_bytes(revision))
        with self.assertRaises(ValueError): k2.open_knowledge(self.root, **self.ids)
        path.write_bytes(original)

    def test_source_attestation_is_deterministic_and_legacy_allowlist_unchanged(self):
        original_allowlist = copy.deepcopy(PINNED_REVIEWED_KNOWLEDGE_ARTIFACTS)
        accepted = self.apply(self.prepare())
        revision = json.loads(self.revision_path(accepted).read_bytes())
        evidence = k2._inputs(self.root, self.ids)[3]
        for key in ("canonical_knowledge", "source_evidence"):
            broken = copy.deepcopy(revision)
            if key == "canonical_knowledge": broken[key]["concepts"][0]["preferred_label"] = "forged"
            else: broken[key]["admission"]["decisions"]["decisions"][0]["proposal_sha256"] = "f"*64
            with self.assertRaises(KnowledgeError):
                build_knowledge_view(evidence, runtime.canonical_bytes(broken["source_evidence"]),
                    runtime.canonical_bytes(broken["canonical_knowledge"]), created_at="2026-10-09T09:00:00Z")
        self.assertEqual(PINNED_REVIEWED_KNOWLEDGE_ARTIFACTS, original_allowlist)

    def test_equal_labels_preserve_distinct_identities_without_automatic_merge(self):
        reviewed = self.reviewed(); prepared = self.prepare(reviewed)
        ids = [item["after"]["id"] for item in prepared["proposals"] if item["entity_kind"] == "concepts"]
        prepared = self.prepare(reviewed, entity_edits={item: {"preferred_label": "Одинаковый термин"} for item in ids})
        accepted = self.apply(prepared)
        records = accepted["knowledge_view"]["records"]["concepts"]
        self.assertEqual({item["id"] for item in records}, set(ids))
        self.assertEqual({item["preferred_label"] for item in records}, {"Одинаковый термин"})
        self.assertTrue(all(not item["redirects"] and not item["supersedes"] for item in records))

    def test_interrupted_owner_write_and_work_receipt_preserve_previous_revision(self):
        reviewed = self.reviewed(); accepted = self.apply(self.prepare(reviewed))
        path = self.revision_path(accepted); original = path.read_bytes()
        prepared = self.prepare(reviewed)
        with patch.object(runtime._Owner, "persist_revision", side_effect=OSError("interrupted owner write")):
            with self.assertRaises(OSError): self.apply(prepared)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(k2.open_knowledge(self.root, **self.ids)["revision_sha256"], accepted["revision_sha256"])
        with patch.object(k2.k1, "_persist", side_effect=OSError("interrupted working pointer")):
            with self.assertRaises(OSError): self.apply(prepared)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(k2.open_knowledge(self.root, **self.ids)["revision_sha256"], accepted["revision_sha256"])

    def test_existing_managed_export_validation_determinism_and_collision_preserve_user_notes(self):
        accepted = self.apply(self.prepare())
        package = k2.knowledge_package(self.root, **self.ids, revision_sha256=accepted["revision_sha256"])
        self.assertEqual(package, k2.knowledge_package(self.root, **self.ids, revision_sha256=accepted["revision_sha256"]))
        manifest, files = package
        validate_reviewed_result_package(manifest, files)
        self.assertEqual(manifest["result_kind"], "CANONICAL_KNOWLEDGE_ADMISSION_V1")
        self.assertTrue(any(name.startswith("view/Concepts/") for name in files))
        self.assertIn(b"integra://knowledge/fragment", files["view/_meta/integra_navigation.md"])
        altered = dict(files); altered["result/result.json"] += b" "
        with self.assertRaises(PublishingError): validate_reviewed_result_package(manifest, altered)
        vault = self.root / "vault"; vault.mkdir()
        unmanaged = vault / "Integra" / manifest["project_slug"]
        unmanaged.mkdir(parents=True); note = unmanaged / "user.md"; note.write_text("user-owned content")
        self.assertTrue(preview_obsidian_export(vault, manifest, files)["collisions"])
        self.assertEqual(note.read_text(), "user-owned content")

    def test_owner_valid_other_reviewed_payload_is_not_current_k1_attestation(self):
        accepted = self.apply(self.prepare())
        root, base, opened, evidence, actual_reviewed = k2._inputs(self.root, self.ids)
        original = json.loads(self.revision_path(accepted).read_bytes())
        owner = runtime.owner()
        for change in ("semantic_title", "artifact_id", "raw_serialization"):
            with self.subTest(change=change):
                request = copy.deepcopy(original["source_evidence"]["admission"])
                reviewed = json.loads(actual_reviewed)
                if change == "semantic_title":
                    reviewed["semantic_knowledge"][0]["title"] += " — unrelated reviewed artifact"
                if change == "artifact_id":
                    reviewed["artifact_id"] = "urn:integra:artifact:11111111-1111-4111-8111-111111111111"
                altered = actual_reviewed + b"\n" if change == "raw_serialization" else runtime.canonical_bytes(reviewed)
                request["package"]["k1_binding"].update(artifact_id=reviewed["artifact_id"],
                    sha256=hashlib.sha256(altered).hexdigest())
                request["decisions"]["package_sha256"] = runtime.digest(request["package"])
                other = owner.compile_revision(evidence, altered, request["package"], request["decisions"])
                owner.validate_revision(other, evidence)
                path = base / "revisions" / (other["revision_sha256"] + ".json")
                owner.persist_revision(path, other)
                with self.assertRaisesRegex(ValueError, "current K1 reviewed"):
                    k2._read_revision(root, base, other["revision_sha256"], owner, evidence, opened, actual_reviewed)
                with self.assertRaisesRegex(ValueError, "current K1 reviewed"):
                    k2.knowledge_navigation(root, **self.ids, revision_sha256=other["revision_sha256"],
                        evidence_id=other["source_evidence"]["evidence"][0]["id"])
                with self.assertRaisesRegex(ValueError, "current K1 reviewed"):
                    k2.knowledge_package(root, **self.ids, revision_sha256=other["revision_sha256"])
                # A valid working-pointer checksum cannot attest another K1 receipt.
                state_path = base / "state.json"; before = state_path.read_bytes()
                state = json.loads(before); state["revision_sha256"] = other["revision_sha256"]
                try:
                    k2.k1._persist(state_path, state)
                    with self.assertRaisesRegex(ValueError, "current K1 reviewed"):
                        k2.open_knowledge(root, **self.ids)
                finally:
                    state_path.write_bytes(before)
        self.assertEqual(k2.open_knowledge(root, **self.ids), accepted)

    def test_owner_valid_wrong_producer_is_rejected_on_direct_navigation_and_export(self):
        accepted = self.apply(self.prepare())
        root, base, opened, evidence, reviewed = k2._inputs(self.root, self.ids)
        original = json.loads(self.revision_path(accepted).read_bytes())
        owner = runtime.owner()
        for change in ("runtime_id", "runtime_sha256"):
            with self.subTest(change=change):
                request = copy.deepcopy(original["source_evidence"]["admission"])
                package, decisions = request["package"], request["decisions"]
                package["producer"][change] = "unknown_producer_v1" if change == "runtime_id" else "f" * 64
                if change == "runtime_sha256":
                    for proposal in package["proposals"]:
                        proposal["generation_provenance"]["producer_sha256"] = "f" * 64
                    proposals = {item["id"]: item for item in package["proposals"]}
                    for decision in decisions["decisions"]:
                        decision["proposal_sha256"] = runtime.digest(proposals[decision["proposal_id"]])
                decisions["package_sha256"] = runtime.digest(package)
                other = owner.compile_revision(evidence, reviewed, package, decisions)
                owner.validate_revision(other, evidence)
                owner.persist_revision(base / "revisions" / (other["revision_sha256"] + ".json"), other)
                with self.assertRaisesRegex(ValueError, "producer runtime changed"):
                    k2._read_revision(root, base, other["revision_sha256"], owner, evidence, opened, reviewed)
                with self.assertRaisesRegex(ValueError, "producer runtime changed"):
                    k2.knowledge_navigation(root, **self.ids, revision_sha256=other["revision_sha256"],
                        evidence_id=other["source_evidence"]["evidence"][0]["id"])
                with self.assertRaisesRegex(ValueError, "producer runtime changed"):
                    k2.knowledge_package(root, **self.ids, revision_sha256=other["revision_sha256"])
        self.assertEqual(k2.open_knowledge(root, **self.ids), accepted)

    def test_changed_adapter_bytes_fail_closed_without_rewriting_historical_revision(self):
        accepted = self.apply(self.prepare())
        path = self.revision_path(accepted); before = path.read_bytes()
        code = Path(k2.__file__).read_bytes()
        original_hash = k2._hash

        def changed_runtime_hash(payload):
            return "f" * 64 if payload == code else original_hash(payload)

        # Current contract requires independent exact producer bytes, including
        # read paths. A later adapter needs governed producer compatibility;
        # a changed executable cannot silently attest a historical producer.
        with patch.object(k2, "_hash", side_effect=changed_runtime_hash):
            with self.assertRaisesRegex(ValueError, "producer runtime changed"):
                k2.open_knowledge(self.root, **self.ids)
            evidence_id = accepted["knowledge_view"]["evidence"][0]["id"]
            with self.assertRaisesRegex(ValueError, "producer runtime changed"):
                k2.knowledge_navigation(self.root, **self.ids, revision_sha256=accepted["revision_sha256"], evidence_id=evidence_id)
            with self.assertRaisesRegex(ValueError, "producer runtime changed"):
                k2.knowledge_package(self.root, **self.ids, revision_sha256=accepted["revision_sha256"])
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(k2.open_knowledge(self.root, **self.ids), accepted)


if __name__ == "__main__": unittest.main()
