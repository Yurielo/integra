import copy
import hashlib
import json
from pathlib import Path
import unittest

from integra_core.knowledge import (
    KnowledgeError,
    build_knowledge_view,
    dumps_knowledge_view,
    knowledge_diff,
    loads_knowledge_view,
    navigate_knowledge,
    validate_knowledge_view,
    _validate_json_schema,
)
from integra_core.protocol import content_sha256


CREATED = "2026-09-11T00:00:00Z"


def _component() -> dict:
    return {
        "component_id": "seminartext", "repository": "Yurielo/seminartext",
        "commit_sha": "970bde598ddd649599295139986933e0e06cb9c0",
        "tree_sha": "6384533c5a41dc97e9fa36f57e7240ac825e411c", "version": "4.0.0",
        "contracts": ["canonical_evidence_v1", "canonical_knowledge_v1"],
        "runtime": {"kind": "python", "version": "3"},
    }


def _evidence() -> dict:
    source = "source:video-1"
    revision = "transcript:revision-1"
    word = "word:000001"
    evidence_id = "evidence:claim-1"
    transcript_text = "source term"
    transcript_hash = hashlib.sha256(transcript_text.encode()).hexdigest()
    return {
        "schema_version": "1.0.0", "artifact_type": "seminartext.canonical_evidence",
        "artifact_id": "artifact:canonical-evidence", "project": {
            "id": "project:course", "title": "Course", "lifecycle_status": "active",
        },
        "sources": [{
            "id": source, "project_id": "project:course", "sequence": 0,
            "kind": "video", "title": "Lesson", "content_sha256": "1" * 64,
            "duration_seconds": 10.0, "lifecycle_status": "active",
        }],
        "transcript_revisions": [{
            "id": revision, "source_id": source, "revision_number": 1,
            "revision_kind": "asr", "parent_revision_id": None,
            "canonical_text": transcript_text, "text_sha256": transcript_hash,
            "authority": "candidate", "lifecycle_status": "active",
            "transcript_provenance": {
                "origin": "machine_generated", "method": "fixture",
                "verification_state": "machine_unverified", "verification_ranges": [],
                "reviewer": None,
            },
        }],
        "cues": [{
            "id": "cue:000001", "transcript_revision_id": revision,
            "sequence": 0, "char_start": 0, "char_end": 11,
            "text": transcript_text,
            "source_locator": {"type": "time_interval", "start_seconds": 1.0, "end_seconds": 2.0},
            "lifecycle_status": "active",
        }],
        "alignment_runs": [{
            "id": "alignment:run-1", "source_id": source,
            "source_content_sha256": "1" * 64,
            "transcript_revision_id": revision,
            "transcript_text_sha256": transcript_hash,
            "aligner": "fixture", "aligner_version": "1", "model": "fixture",
            "model_revision": "1", "model_sha256": "3" * 64,
            "config_sha256": "4" * 64, "status": "valid",
        }],
        "words": [{
            "id": word, "source_id": source, "transcript_revision_id": revision,
            "sequence": 0, "char_start": 0, "char_end": 11, "text": "source term",
            "normalized_text": None, "source_cue_ids": ["cue:000001"],
            "start_seconds": 1.0, "end_seconds": 2.0, "alignment_status": "aligned",
            "confidence": 0.9, "speaker_id": None,
            "timing_provenance": {"kind": "forced_alignment", "alignment_run_id": "alignment:run-1", "method": "fixture"},
            "qa_flags": [], "lifecycle_status": "active",
        }],
        "benchmark_segments": [], "topics": [],
        "evidence_refs": [{
            "id": evidence_id, "project_id": "project:course", "source_id": source,
            "transcript_revision_id": revision,
            "target": {"entity_type": "word", "entity_id": word},
            "locator": {"type": "time_interval", "start_seconds": 1.0, "end_seconds": 2.0},
            "lifecycle_status": "active",
        }],
    }


def _source_evidence(evidence: dict) -> dict:
    source = evidence["sources"][0]
    revision = evidence["transcript_revisions"][0]
    evidence_id = "evidence:claim-1"
    topic_id = "topic:lesson"
    concept_id = "concept:source-term"
    return {
        "artifact_id": "artifact:source-slice",
        "artifact_type": "seminartext.golden_knowledge_slice",
        "canonical_evidence": {
            "artifact_id": evidence["artifact_id"], "path": "evidence.json",
            "schema_version": "1.0.0", "sha256": "",
        },
        "concepts": [{
            "aliases": ["source term"], "derivation_status": "provisional_manual_curation",
            "description": "Concept claim", "evidence_ids": [evidence_id],
            "id": concept_id, "identity_rationale": "fixture",
            "preferred_label": "Canonical term", "review_status": "product_review_required",
            "sequence": 0, "topic_ids": [topic_id],
        }],
        "evidence": [{
            "canonical_source_id": source["id"],
            "canonical_transcript_revision_id": revision["id"],
            "canonical_word_end_id": "word:000001",
            "canonical_word_start_id": "word:000001", "claim": "Substantive claim",
            "id": evidence_id,
            "locator": {"end_seconds": 2.0, "start_seconds": 1.0, "type": "time_interval"},
            "quote": "source term", "sequence": 0,
            "timing_status": "aligned_word_range", "unaligned_word_ids": [],
        }],
        "product_review": {"required": True, "status": "pending"},
        "schema_version": "1.0.0",
        "seminar": {
            "canonical_project_id": evidence["project"]["id"], "id": "seminar:course",
            "source_ids": [source["id"]], "title": "Course", "topic_ids": [topic_id],
        },
        "sources": [{
            "canonical_source_id": source["id"], "content_sha256": source["content_sha256"],
            "duration_seconds": source["duration_seconds"], "id": source["id"],
            "kind": source["kind"], "title": source["title"],
        }],
        "topics": [{
            "canonical_source_id": source["id"],
            "canonical_transcript_revision_id": revision["id"],
            "canonical_word_end_id": "word:000001", "canonical_word_start_id": "word:000001",
            "concept_ids": [concept_id], "coverage": "full", "evidence_ids": [evidence_id],
            "id": topic_id, "locator": {"end_seconds": 2.0, "start_seconds": 1.0, "type": "time_interval"},
            "sequence": 0, "structure_origin": "manual_issue_44",
            "structure_provenance": {"method": "fixture"}, "summary": "Substantive claim",
            "timing_status": "aligned_word_range", "title": "Topic", "unaligned_word_ids": [],
        }],
    }


def _pointer(artifact_id: str, value: dict, path: str) -> dict:
    return {"artifact_id": artifact_id, "schema_version": "1.0.0",
            "sha256": content_sha256(value), "path": path}


def _knowledge(
    evidence: dict, evidence_file_sha256: str,
    source_evidence: dict, source_evidence_file_sha256: str,
) -> dict:
    provenance = {"origin": "canonical_evidence", "source_artifact_id": evidence["artifact_id"]}
    slice_provenance = {
        "origin": "golden_slice", "source_artifact_id": source_evidence["artifact_id"],
        "source_status": "product_review_required",
    }
    concept_id = "concept:source-term"
    topic_id = "topic:lesson"
    return {
        "schema_version": "1.0.0", "artifact_type": "seminartext.canonical_knowledge",
        "artifact_id": "artifact:canonical-knowledge", "version": 1,
        "canonical_evidence": {"artifact_id": evidence["artifact_id"], "schema_version": "1.0.0", "sha256": evidence_file_sha256, "path": "evidence.json"},
        "source_evidence": {
            "artifact_id": source_evidence["artifact_id"], "schema_version": "1.0.0",
            "sha256": source_evidence_file_sha256, "path": "slice.json",
        },
        "project": {"id": "knowledge-project:course", "title": "Course", "status": "PROVISIONAL", "version": 1, "provenance": provenance},
        "seminars": [{
            "id": "seminar:course", "project_id": "knowledge-project:course", "title": "Course",
            "status": "PROVISIONAL", "version": 1, "provenance": provenance,
            "topic_refs": [topic_id], "evidence_refs": ["evidence:claim-1"],
        }],
        "topics": [{
            "id": topic_id, "seminar_id": "seminar:course",
            "source_scope": {"source_ids": ["source:video-1"], "transcript_revision_ids": ["transcript:revision-1"]},
            "title": "Topic", "summary": "Substantive claim",
            "evidence_refs": ["evidence:claim-1"], "concept_refs": [concept_id],
            "status": "PROVISIONAL", "provenance": slice_provenance, "version": 1,
        }],
        "concepts": [{
            "id": concept_id, "preferred_label": "Canonical term", "aliases": ["source term"],
            "status": "PROVISIONAL", "scope": "source-bound", "description": "Concept claim",
            "provenance": slice_provenance, "evidence_refs": ["evidence:claim-1"],
            "topic_refs": [topic_id], "version": 1, "created_from": [topic_id],
            "supersedes": [], "redirects": [],
        }],
        "relations": [], "review_decisions": [],
        "relation_type_registry": [
            {"id": item, "description": item}
            for item in ("supports", "contradicts", "refines", "depends_on", "associated_with")
        ],
    }


class KnowledgeIntegrationTests(unittest.TestCase):
    @staticmethod
    def _payload(value: dict) -> bytes:
        return json.dumps(value, sort_keys=True).encode()

    def setUp(self) -> None:
        self.evidence = _evidence()
        self.evidence_payload = json.dumps(self.evidence, sort_keys=True).encode()
        self.source_evidence = _source_evidence(self.evidence)
        self.source_evidence["canonical_evidence"]["sha256"] = hashlib.sha256(self.evidence_payload).hexdigest()
        self.source_evidence_payload = json.dumps(self.source_evidence, sort_keys=True).encode()
        self.knowledge = _knowledge(
            self.evidence, hashlib.sha256(self.evidence_payload).hexdigest(),
            self.source_evidence, hashlib.sha256(self.source_evidence_payload).hexdigest(),
        )
        self.knowledge_payload = json.dumps(self.knowledge, sort_keys=True).encode()
        self.component = _component()
        self.view = build_knowledge_view(
            self.evidence_payload, self.source_evidence_payload,
            self.knowledge_payload, created_at=CREATED
        )

    def test_claims_terms_graph_and_navigation_retain_exact_evidence(self) -> None:
        alias = next(item for item in self.view["terms"] if item["kind"] == "SOURCE_ALIAS")
        self.assertEqual(alias["value"], "source term")
        self.assertEqual(alias["evidence_refs"], ["evidence:claim-1"])
        term = navigate_knowledge(
            self.view, self.evidence_payload, self.source_evidence_payload,
            self.knowledge_payload, alias["term_id"],
        )
        self.assertEqual(term["node"]["kind"], "TERM")
        self.assertTrue(any(item["kind"] == "TERM_OF" for item in term["outgoing"]))
        concept = navigate_knowledge(
            self.view, self.evidence_payload, self.source_evidence_payload,
            self.knowledge_payload, "concept:source-term",
        )
        supported = next(item for item in concept["outgoing"] if item["kind"] == "SUPPORTED_BY")
        evidence_result = navigate_knowledge(
            self.view, self.evidence_payload, self.source_evidence_payload,
            self.knowledge_payload, supported["to_id"],
        )
        evidence = evidence_result["node"]
        self.assertEqual(evidence["kind"], "EVIDENCE")
        exact = evidence_result["exact_evidence"]
        self.assertEqual(exact["locator"], {
            "type": "time_interval", "start_seconds": 1.0, "end_seconds": 2.0,
        })

    def test_serialization_is_deterministic_and_requires_source_truth(self) -> None:
        payload = dumps_knowledge_view(
            self.view, self.evidence_payload, self.source_evidence_payload,
            self.knowledge_payload,
        )
        restored = loads_knowledge_view(
            payload, self.evidence_payload, self.source_evidence_payload,
            self.knowledge_payload,
        )
        self.assertEqual(dumps_knowledge_view(
            restored, self.evidence_payload, self.source_evidence_payload,
            self.knowledge_payload,
        ), payload)
        drifted = copy.deepcopy(self.knowledge)
        drifted["concepts"][0]["description"] = "Changed source truth"
        with self.assertRaisesRegex(KnowledgeError, "source binding|source Evidence"):
            validate_knowledge_view(
                self.view, self.evidence_payload, self.source_evidence_payload,
                self._payload(drifted),
            )

    def test_pinned_component_and_contract_identity_are_not_caller_controlled(self) -> None:
        binding = self.view["source_binding"]
        self.assertEqual(binding["component_id"], "seminartext")
        self.assertEqual(binding["commit_sha"], "970bde598ddd649599295139986933e0e06cb9c0")
        self.assertEqual(binding["tree_sha"], "6384533c5a41dc97e9fa36f57e7240ac825e411c")
        tampered = copy.deepcopy(self.view)
        tampered["source_binding"]["commit_sha"] = "f" * 40
        tampered["record_sha256"] = "0" * 64
        with self.assertRaises(KnowledgeError):
            validate_knowledge_view(
                tampered, self.evidence_payload, self.source_evidence_payload,
                self.knowledge_payload,
            )

    def test_pinned_canonical_evidence_cross_record_validator_is_enforced(self) -> None:
        invalid = copy.deepcopy(self.evidence)
        invalid["words"][0]["text"] = "fabricated"
        with self.assertRaisesRegex(KnowledgeError, "Canonical Evidence invalid"):
            build_knowledge_view(
                self._payload(invalid), self.source_evidence_payload,
                self.knowledge_payload, created_at=CREATED,
            )
        invalid = copy.deepcopy(self.evidence)
        provenance = invalid["transcript_revisions"][0]["transcript_provenance"]
        provenance.update({
            "origin": "human_verified", "verification_state": "fully_human_verified",
            "verification_ranges": [], "reviewer": None,
        })
        with self.assertRaisesRegex(KnowledgeError, "Canonical Evidence invalid"):
            build_knowledge_view(
                self._payload(invalid), self.source_evidence_payload,
                self.knowledge_payload, created_at=CREATED,
            )

    def test_source_evidence_quote_range_and_assurance_are_exact(self) -> None:
        invalid = copy.deepcopy(self.source_evidence)
        invalid["evidence"][0]["quote"] = "invented quote"
        with self.assertRaisesRegex(KnowledgeError, "quote does not match"):
            build_knowledge_view(
                self.evidence_payload, self._payload(invalid),
                self.knowledge_payload, created_at=CREATED,
            )
        exact = self.view["evidence"][0]
        self.assertEqual(exact["transcript_assurance"]["provenance"]["verification_state"], "machine_unverified")

    def test_alias_traceability_does_not_invent_literal_evidence(self) -> None:
        changed_source = copy.deepcopy(self.source_evidence)
        changed_source["concepts"][0]["aliases"] = ["term-never-present-in-source"]
        changed_source_payload = self._payload(changed_source)
        changed = copy.deepcopy(self.knowledge)
        changed["concepts"][0]["aliases"] = ["term-never-present-in-source"]
        changed["source_evidence"]["sha256"] = hashlib.sha256(changed_source_payload).hexdigest()
        view = build_knowledge_view(
            self.evidence_payload, changed_source_payload,
            self._payload(changed), created_at=CREATED,
        )
        alias = next(item for item in view["terms"] if item["kind"] == "SOURCE_ALIAS")
        self.assertEqual(alias["traceability"], "CONCEPT_SEMANTIC_EVIDENCE")
        original_alias = next(item for item in self.view["terms"] if item["kind"] == "SOURCE_ALIAS")
        self.assertEqual(original_alias["traceability"], "LITERAL_SOURCE_EVIDENCE")

        partial_source = copy.deepcopy(self.source_evidence)
        partial_source["concepts"][0]["aliases"] = ["our"]
        partial_source_payload = self._payload(partial_source)
        partial_knowledge = copy.deepcopy(self.knowledge)
        partial_knowledge["concepts"][0]["aliases"] = ["our"]
        partial_knowledge["source_evidence"]["sha256"] = hashlib.sha256(partial_source_payload).hexdigest()
        partial_view = build_knowledge_view(
            self.evidence_payload, partial_source_payload,
            self._payload(partial_knowledge), created_at=CREATED,
        )
        partial_alias = next(item for item in partial_view["terms"] if item["kind"] == "SOURCE_ALIAS")
        self.assertEqual(partial_alias["traceability"], "CONCEPT_SEMANTIC_EVIDENCE")

    def test_topic_evidence_must_lie_inside_topic_source_scope(self) -> None:
        evidence = copy.deepcopy(self.evidence)
        evidence["sources"].append({
            "id": "source:video-2", "project_id": "project:course", "sequence": 1,
            "kind": "video", "title": "Other", "content_sha256": "5" * 64,
            "duration_seconds": 10.0, "lifecycle_status": "active",
        })
        other_text = "other"
        evidence["transcript_revisions"].append({
            "id": "transcript:revision-2", "source_id": "source:video-2",
            "revision_number": 1, "revision_kind": "asr", "parent_revision_id": None,
            "canonical_text": other_text,
            "text_sha256": hashlib.sha256(other_text.encode()).hexdigest(),
            "authority": "candidate", "lifecycle_status": "active",
            "transcript_provenance": {
                "origin": "machine_generated", "method": "fixture",
                "verification_state": "machine_unverified", "verification_ranges": [],
                "reviewer": None,
            },
        })
        evidence_payload = self._payload(evidence)
        source = copy.deepcopy(self.source_evidence)
        source["canonical_evidence"]["sha256"] = hashlib.sha256(evidence_payload).hexdigest()
        source["sources"].append({
            "canonical_source_id": "source:video-2", "content_sha256": "5" * 64,
            "duration_seconds": 10.0, "id": "source:video-2", "kind": "video",
            "title": "Other",
        })
        source["seminar"]["source_ids"].append("source:video-2")
        source_payload = self._payload(source)
        knowledge = copy.deepcopy(self.knowledge)
        knowledge["canonical_evidence"]["sha256"] = hashlib.sha256(evidence_payload).hexdigest()
        knowledge["source_evidence"]["sha256"] = hashlib.sha256(source_payload).hexdigest()
        knowledge["topics"][0]["source_scope"] = {
            "source_ids": ["source:video-2"],
            "transcript_revision_ids": ["transcript:revision-2"],
        }
        knowledge["topics"][0]["provenance"] = {
            "origin": "derived", "source_artifact_id": "artifact:source-slice",
        }
        with self.assertRaisesRegex(KnowledgeError, "outside its source scope"):
            build_knowledge_view(
                evidence_payload, source_payload, self._payload(knowledge),
                created_at=CREATED,
            )

    def test_created_at_requires_real_rfc3339_utc_timestamp(self) -> None:
        for invalid in (
            "Z", "not-a-timeZ", "2026-99-99T00:00:00Z",
            "2026-09-11 00:00:00Z", "2026-09-11T24:00:00Z",
        ):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(KnowledgeError, "RFC3339"):
                build_knowledge_view(
                    self.evidence_payload, self.source_evidence_payload,
                    self.knowledge_payload, created_at=invalid,
                )

    def test_published_schema_rejects_unconstrained_source_records(self) -> None:
        schema = json.loads(
            (Path(__file__).resolve().parents[1] / "schemas/knowledge_view_v1.schema.json").read_text()
        )
        invalid = copy.deepcopy(self.view)
        invalid["records"]["concepts"] = [{}]
        errors: list[str] = []
        _validate_json_schema(invalid, schema, schema, "$", errors)
        self.assertTrue(errors)
        invalid = copy.deepcopy(self.view)
        invalid["evidence"][0]["transcript_assurance"]["provenance"] = {}
        invalid["evidence"][0]["transcript_assurance"]["lifecycle_status"] = "fabricated"
        errors = []
        _validate_json_schema(invalid, schema, schema, "$", errors)
        self.assertTrue(errors)
        invalid = copy.deepcopy(self.view)
        concept_node = next(item for item in invalid["graph"]["nodes"] if item["kind"] == "CONCEPT")
        concept_node["status"] = "fabricated"
        errors = []
        _validate_json_schema(invalid, schema, schema, "$", errors)
        self.assertTrue(errors)

    def test_navigation_rejects_resealed_view_without_exact_source_truth(self) -> None:
        tampered = copy.deepcopy(self.view)
        tampered["evidence"][0]["locator"]["start_seconds"] = 9.0
        tampered["evidence"][0]["evidence_sha256"] = content_sha256(tampered["evidence"][0])
        with self.assertRaisesRegex(KnowledgeError, "evidence projection differs"):
            navigate_knowledge(
                tampered, self.evidence_payload, self.source_evidence_payload,
                self.knowledge_payload, "evidence:claim-1",
            )

    def test_substantive_claim_without_evidence_fails_closed(self) -> None:
        invalid = copy.deepcopy(self.knowledge)
        invalid["concepts"][0]["evidence_refs"] = []
        with self.assertRaisesRegex(KnowledgeError, "lacks exact evidence"):
            build_knowledge_view(
                self.evidence_payload, self.source_evidence_payload,
                self._payload(invalid), created_at=CREATED
            )

    def test_machine_cannot_forge_accepted_lifecycle(self) -> None:
        invalid = copy.deepcopy(self.knowledge)
        invalid["concepts"][0]["status"] = "ACCEPTED"
        with self.assertRaisesRegex(KnowledgeError, "requires explicit ACCEPT DOMAIN_REVIEW"):
            build_knowledge_view(
                self.evidence_payload, self.source_evidence_payload,
                self._payload(invalid), created_at=CREATED
            )
        invalid["review_decisions"] = [{
            "id": "decision:auto", "action": "ACCEPT", "target_ids": ["concept:source-term"],
            "result_ids": ["concept:source-term"], "reason": "auto", "actor_type": "system_validator",
            "timestamp": CREATED, "input_version": 1, "output_version": 1,
            "provenance": {"origin": "derived", "source_artifact_id": "artifact:canonical-knowledge"},
        }]
        with self.assertRaisesRegex(KnowledgeError, "cannot perform|AUTO DEFER"):
            build_knowledge_view(
                self.evidence_payload, self.source_evidence_payload,
                self._payload(invalid), created_at=CREATED
            )

        forged = copy.deepcopy(self.knowledge)
        forged["concepts"][0]["status"] = "ACCEPTED"
        forged["review_decisions"] = [{
            "id": "decision:forged", "action": "ACCEPT",
            "target_ids": ["concept:source-term"], "result_ids": ["concept:source-term"],
            "reason": "caller-authored actor string", "actor_type": "human_domain_reviewer",
            "timestamp": CREATED, "input_version": 1, "output_version": 1,
            "provenance": {"origin": "human_review", "source_artifact_id": "artifact:source-slice"},
        }]
        with self.assertRaisesRegex(KnowledgeError, "pinned source artifact attestation"):
            build_knowledge_view(
                self.evidence_payload, self.source_evidence_payload,
                self._payload(forged), created_at=CREATED,
            )

    def test_knowledge_diff_is_mechanical(self) -> None:
        changed_source = copy.deepcopy(self.source_evidence)
        changed_source["concepts"][0]["description"] = "Revised provisional claim"
        changed_source_payload = self._payload(changed_source)
        changed = copy.deepcopy(self.knowledge)
        changed["concepts"][0]["description"] = "Revised provisional claim"
        changed["source_evidence"]["sha256"] = hashlib.sha256(changed_source_payload).hexdigest()
        after = build_knowledge_view(
            self.evidence_payload, changed_source_payload,
            self._payload(changed), created_at=CREATED
        )
        result = knowledge_diff(
            self.view, self.evidence_payload, self.source_evidence_payload,
            self.knowledge_payload, after, self.evidence_payload,
            changed_source_payload, self._payload(changed),
        )
        self.assertIn(
            {"kind": "CONCEPT", "id": "concept:source-term"}, result["changed_ids"]
        )
        self.assertEqual(result["semantic_interpretation"], "NOT_PERFORMED")

        seminar_changed = copy.deepcopy(self.knowledge)
        seminar_changed["seminars"][0]["title"] = "Revised seminar title"
        seminar_payload = self._payload(seminar_changed)
        seminar_view = build_knowledge_view(
            self.evidence_payload, self.source_evidence_payload,
            seminar_payload, created_at=CREATED,
        )
        seminar_diff = knowledge_diff(
            self.view, self.evidence_payload, self.source_evidence_payload,
            self.knowledge_payload, seminar_view, self.evidence_payload,
            self.source_evidence_payload, seminar_payload,
        )
        self.assertIn(
            {"kind": "SEMINAR", "id": "seminar:course"}, seminar_diff["changed_ids"]
        )


if __name__ == "__main__":
    unittest.main()
