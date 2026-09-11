from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from integra_core.cross_navigation import (
    CrossNavigationError, NavigationUnavailableError, build_cross_navigation,
    _add_bridges, _document_locators, _index_knowledge, _record_hash, dumps_cross_navigation,
    loads_cross_navigation, media_source_target_id, navigate,
)
from integra_core.identity import derive_imported_id
from integra_core.knowledge import build_knowledge_view
from integra_core.protocol import content_sha256


TESTS = Path(__file__).resolve().parent
NOW = "2026-09-11T00:03:00Z"
CROSS_FFPROBE = TESTS / "fixtures" / "cross_navigation_v1" / "ffprobe_fixture.py"


def _fixture_module(name: str):
    spec = importlib.util.spec_from_file_location(f"cross_nav_{name}", TESTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ALIGNMENT = _fixture_module("test_multi_source_alignment")
KNOWLEDGE = _fixture_module("test_knowledge")
MEDIA = _fixture_module("test_media")


def _replace_source_id(value, old: str, new: str):
    if isinstance(value, dict):
        return {key: _replace_source_id(item, old, new) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace_source_id(item, old, new) for item in value]
    return new if value == old else value


def _knowledge_view(source_id: str = "source:video-1") -> tuple[dict, bytes, bytes, bytes]:
    evidence = KNOWLEDGE._evidence()
    evidence = _replace_source_id(evidence, "source:video-1", source_id)
    evidence_payload = KNOWLEDGE.json.dumps(
        evidence, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    source = KNOWLEDGE._source_evidence(evidence)
    source["canonical_evidence"]["sha256"] = hashlib.sha256(evidence_payload).hexdigest()
    source_payload = KNOWLEDGE.json.dumps(
        source, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    knowledge = KNOWLEDGE._knowledge(
        evidence, hashlib.sha256(evidence_payload).hexdigest(), source,
        hashlib.sha256(source_payload).hexdigest(),
    )
    knowledge = _replace_source_id(knowledge, "source:video-1", source_id)
    knowledge_payload = KNOWLEDGE.json.dumps(
        knowledge, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return (
        build_knowledge_view(evidence_payload, source_payload, knowledge_payload, created_at=NOW),
        evidence_payload, source_payload, knowledge_payload,
    )


def _media_record(root: Path, parent_artifact_id: str) -> dict:
    original_probe = MEDIA.FFPROBE
    MEDIA.FFPROBE = CROSS_FFPROBE
    try:
        source = MEDIA._source()
        source["provenance"]["parent_artifact_ids"] = [parent_artifact_id]
        recipe = MEDIA.create_media_recipe(
            source=source, operation_id=MEDIA.OPERATION_ID,
            locator={"type": "time_interval", "start_seconds": 0.0, "end_seconds": 2.0},
            steps=[MEDIA._steps()[0], MEDIA._steps()[-1]], created_at=MEDIA.NOW,
        )
        plan = MEDIA._plan(recipe)
        output_payload = b"INTEGRA_TEST_VIDEO\0synthetic verified clip"
        output = MEDIA._output_reference(recipe, output_payload, kind="fragment")
        qa_payload = MEDIA._qa_payload(recipe, plan, output)
        qa_reference = MEDIA._qa_reference(recipe, output, qa_payload)
        job = MEDIA._succeeded_job(plan, output, qa_reference)
        derivative = MEDIA._register(
            root, recipe, plan, output, output_payload, qa_reference, qa_payload,
        )
    finally:
        MEDIA.FFPROBE = original_probe
    return {
        "recipe": recipe, "derivative": derivative, "operation_plan": plan,
        "job": job, "checkpoint": job["checkpoint"],
        "model_records": derivative["model_residency"], "qa_reference": qa_reference,
        "qa_report": json.loads(qa_payload),
    }


class CrossNavigationTests(unittest.TestCase):
    def setUp(self) -> None:
        fixture = ALIGNMENT.MultiSourceAlignmentTests(
            methodName="test_required_navigation_is_deterministic_exact_and_reversible"
        )
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        self.fixture = fixture
        media_temporary = tempfile.TemporaryDirectory()
        self.addCleanup(media_temporary.cleanup)
        for values in (
            ("video-transcript", "VIDEO_TO_TRANSCRIPT", "video", "transcript"),
            ("video-slide", "VIDEO_TO_SLIDE", "video", "slide"),
            ("topic-page", "TOPIC_TO_PAGE", "topic", "page"),
            ("topic-slide", "TOPIC_TO_SLIDE", "topic", "slide"),
            ("evidence-document", "EVIDENCE_TO_DOCUMENT", "evidence", "document"),
        ):
            fixture._link(*values)
        self.view, self.evidence_payload, self.source_payload, self.knowledge_payload = _knowledge_view()
        video_ref = next(
            item for item in fixture.artifact_references
            if item["provenance"]["source_locator"]["native_id"] == "video"
        )
        self.media = _media_record(Path(media_temporary.name), video_ref["artifact_id"])
        self.bridges = [
            {"from_id": "topic:lesson", "to_id": fixture.nodes["topic"],
             "relation": "KNOWLEDGE_TOPIC_TO_ALIGNMENT_TOPIC"},
            {"from_id": "evidence:claim-1", "to_id": fixture.nodes["evidence"],
             "relation": "KNOWLEDGE_EVIDENCE_TO_ALIGNMENT_EVIDENCE"},
            {"from_id": media_source_target_id(self.media["recipe"]),
             "to_id": fixture.nodes["video"],
             "relation": "MEDIA_SOURCE_TO_ALIGNMENT_MEDIA"},
        ]
        self.unavailable_targets = [
            {"target_id": "missing:audio", "kind": "AUDIO",
             "reason": "audio source revision is not locally available"},
            {"target_id": "missing:document", "kind": "DOCUMENT",
             "reason": "source revision is not locally available"},
        ]
        self.authority = {
            "alignment": fixture.alignment, "registry": fixture.registry,
            "upstream_records": fixture.upstream_records, "knowledge_view": self.view,
            "evidence_payload": self.evidence_payload,
            "source_evidence_payload": self.source_payload,
            "knowledge_payload": self.knowledge_payload, "media_records": [self.media],
            "bridges": self.bridges, "unavailable_targets": self.unavailable_targets,
        }
        self.index = build_cross_navigation(
            **self.authority, created_at=NOW,
        )

    def test_all_required_surfaces_and_exact_actions_are_indexed(self) -> None:
        kinds = {item["kind"] for item in self.index["targets"]}
        self.assertTrue({
            "KNOWLEDGE_ENTITY", "EVIDENCE", "TOPIC", "WORD_TIMELINE", "TRANSCRIPT", "AUDIO",
            "DOCUMENT", "PAGE", "SLIDE", "VIDEO", "MEDIA_SOURCE", "MEDIA_CLIP",
        }.issubset(kinds))
        topic = navigate(self.index, "topic:lesson", authority=self.authority)
        self.assertIn("SEEK_MEDIA", topic["origin"]["actions"])
        hop = next(item for item in topic["forward"]
                   if item["relation"] == "KNOWLEDGE_TOPIC_TO_ALIGNMENT_TOPIC")
        self.assertTrue(any(item["type"] == "TIME_INTERVAL" for item in hop["locators"]))

    def test_round_trip_preserves_stable_ids_locators_and_clip(self) -> None:
        source_id = media_source_target_id(self.media["recipe"])
        forward = navigate(self.index, source_id, authority=self.authority)
        clip = next(item for item in forward["forward"] if item["kind"] == "MEDIA_CLIP")
        reverse = navigate(self.index, clip["target_id"], authority=self.authority)["reverse"]
        back = next(item for item in reverse if item["target_id"] == source_id)
        self.assertEqual(back["locators"], forward["origin"]["locators"])
        self.assertIn("OPEN_CLIP", clip["actions"])
        payload = dumps_cross_navigation(self.index, authority=self.authority)
        self.assertEqual(
            dumps_cross_navigation(
                loads_cross_navigation(payload, authority=self.authority),
                authority=self.authority,
            ), payload,
        )
        schema = json.loads(
            (TESTS.parent / "schemas" / "cross_navigation_v1.schema.json").read_text()
        )
        errors = []
        KNOWLEDGE._validate_json_schema(self.index, schema, schema, "$", errors)
        self.assertEqual(errors, [])

    def test_unknown_and_unavailable_sources_fail_without_fabricated_route(self) -> None:
        with self.assertRaisesRegex(CrossNavigationError, "unknown"):
            navigate(self.index, "not:a:target", authority=self.authority)
        with self.assertRaisesRegex(NavigationUnavailableError, "not locally available"):
            navigate(self.index, "missing:document", authority=self.authority)
        with self.assertRaisesRegex(NavigationUnavailableError, "audio source revision"):
            navigate(self.index, "missing:audio", authority=self.authority)
        self.assertFalse(any(
            {item["from_id"], item["to_id"]} & {"missing:document", "missing:audio"}
            for item in self.index["routes"]
        ))

    def test_tampering_and_unverified_derivative_fail_closed(self) -> None:
        tampered = copy.deepcopy(self.index)
        tampered["targets"][0]["locators"] = []
        with self.assertRaises(CrossNavigationError):
            navigate(tampered, tampered["targets"][0]["target_id"], authority=self.authority)
        bad = copy.deepcopy(self.media)
        bad["derivative"]["knowledge_truth_modified"] = True
        with self.assertRaisesRegex(CrossNavigationError, "binding differs"):
            build_cross_navigation(
                alignment=self.fixture.alignment, registry=self.fixture.registry,
                upstream_records=self.fixture.upstream_records, knowledge_view=self.view,
                evidence_payload=self.evidence_payload,
                source_evidence_payload=self.source_payload,
                knowledge_payload=self.knowledge_payload, media_records=[bad], bridges=[],
                unavailable_targets=[], created_at=NOW,
            )

    def test_bridges_require_validated_source_revision_mapping(self) -> None:
        targets = {item["target_id"]: item for item in self.index["targets"]}
        bridge = {
            "from_id": "topic:lesson", "to_id": self.fixture.nodes["topic"],
            "relation": "KNOWLEDGE_TOPIC_TO_ALIGNMENT_TOPIC",
        }
        mappings = copy.deepcopy(self.index["sources"]["mappings"])
        knowledge_mapping = next(
            item for item in mappings if item["kind"] == "KNOWLEDGE_TO_PROJECT_SOURCE"
        )
        knowledge_mapping["from_revision_id"] = "transcript:wrong-revision"
        with self.assertRaisesRegex(CrossNavigationError, "source/revision mapping"):
            _add_bridges(targets, [], [bridge], mappings)
        self.assertEqual(
            {item["kind"] for item in self.index["sources"]["mappings"]},
            {"KNOWLEDGE_TO_PROJECT_SOURCE", "MEDIA_TO_ALIGNMENT_SOURCE"},
        )

    def test_cross_project_knowledge_source_fails_before_indexing(self) -> None:
        view, evidence, source, knowledge = _knowledge_view("source:outside-project")
        authority = {
            **self.authority,
            "knowledge_view": view,
            "evidence_payload": evidence,
            "source_evidence_payload": source,
            "knowledge_payload": knowledge,
            "bridges": [],
        }
        with self.assertRaisesRegex(
            CrossNavigationError, "lacks one exact project mapping"
        ):
            build_cross_navigation(**authority, created_at=NOW)

    def test_partial_media_mapping_coverage_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            unmatched = _media_record(
                Path(temporary),
                "urn:integra:artifact:00000000-0000-5000-8000-000000000000",
            )
            authority = {
                **self.authority,
                "media_records": [self.media, unmatched],
                "bridges": [],
            }
            with self.assertRaisesRegex(
                CrossNavigationError, "registered media source lacks one exact alignment mapping"
            ):
                build_cross_navigation(**authority, created_at=NOW)

    def test_multi_source_knowledge_aggregate_exposes_only_entity_action(self) -> None:
        evidence = [
            {
                "id": "evidence:one", "source_id": "source:one",
                "transcript_revision_id": "revision:one",
                "locator": {"type": "time_interval", "start_seconds": 1.0, "end_seconds": 2.0},
            },
            {
                "id": "evidence:two", "source_id": "source:two",
                "transcript_revision_id": "revision:two",
                "locator": {"type": "time_interval", "start_seconds": 3.0, "end_seconds": 4.0},
            },
        ]
        view = {
            "evidence": evidence,
            "records": {
                "seminars": [], "topics": [],
                "concepts": [{
                    "id": "concept:aggregate",
                    "evidence_refs": ["evidence:one", "evidence:two"],
                }],
                "relations": [], "review_decisions": [],
            },
            "graph": {
                "nodes": [
                    {"id": "concept:aggregate", "kind": "CONCEPT", "sha256": "1" * 64,
                     "status": "PROVISIONAL"},
                    {"id": "evidence:one", "kind": "EVIDENCE", "sha256": "2" * 64,
                     "status": "PROVISIONAL"},
                    {"id": "evidence:two", "kind": "EVIDENCE", "sha256": "3" * 64,
                     "status": "PROVISIONAL"},
                ],
                "edges": [],
            },
        }
        targets: dict[str, dict] = {}
        _index_knowledge(targets, [], view)
        aggregate = targets["concept:aggregate"]
        self.assertEqual(aggregate["actions"], ["OPEN_ENTITY"])
        self.assertEqual(aggregate["locators"], [])
        self.assertIsNone(aggregate["source_id"])
        self.assertIsNone(aggregate["source_revision_id"])
        self.assertIn("SEEK_MEDIA", targets["evidence:one"]["actions"])
        self.assertEqual(targets["evidence:one"]["source_id"], "source:one")

    def test_resigned_semantic_promotion_fails_against_authority(self) -> None:
        forged = copy.deepcopy(self.index)
        target = next(
            item for item in forged["targets"]
            if item["owner"] == "integra.multi_source_alignment"
            and item["semantic_status"] == "PROVISIONAL"
        )
        target["semantic_status"] = "ACCEPTED"
        target["target_sha256"] = _record_hash(target, "target_sha256")
        for route in forged["routes"]:
            if route["from_id"] == target["target_id"]:
                route["from_sha256"] = target["target_sha256"]
            if route["to_id"] == target["target_id"]:
                route["to_sha256"] = target["target_sha256"]
            route["route_sha256"] = _record_hash(route, "route_sha256")
        identity = content_sha256({
            "sources": forged["sources"],
            "targets": [
                {"target_id": item["target_id"], "target_sha256": item["target_sha256"]}
                for item in forged["targets"]
            ],
            "routes": [
                {"route_id": item["route_id"], "route_sha256": item["route_sha256"]}
                for item in forged["routes"]
            ],
        })
        forged["navigation_id"] = derive_imported_id(
            "artifact", "integra.cross_navigation", forged["project_id"], identity,
        )
        forged["record_sha256"] = _record_hash(forged)
        with self.assertRaisesRegex(CrossNavigationError, "authoritative sources"):
            navigate(forged, target["target_id"], authority=self.authority)

    def test_resigned_unavailable_source_fabrication_fails_against_catalog(self) -> None:
        forged = copy.deepcopy(self.index)
        target = next(item for item in forged["targets"] if not item["available"])
        target["target_id"] = "fabricated:source"
        target["content_sha256"] = "f" * 64
        target["unavailable_reason"] = "invented unavailable source"
        target["target_sha256"] = _record_hash(target, "target_sha256")
        forged["targets"] = sorted(forged["targets"], key=lambda item: item["target_id"])
        identity = content_sha256({
            "sources": forged["sources"],
            "targets": [
                {"target_id": item["target_id"], "target_sha256": item["target_sha256"]}
                for item in forged["targets"]
            ],
            "routes": [
                {"route_id": item["route_id"], "route_sha256": item["route_sha256"]}
                for item in forged["routes"]
            ],
        })
        forged["navigation_id"] = derive_imported_id(
            "artifact", "integra.cross_navigation", forged["project_id"], identity,
        )
        forged["record_sha256"] = _record_hash(forged)
        with self.assertRaisesRegex(CrossNavigationError, "authoritative sources"):
            navigate(forged, "fabricated:source", authority=self.authority)

    def test_document_projection_preserves_region_and_revision(self) -> None:
        record = copy.deepcopy(self.fixture.page_document)
        block = copy.deepcopy(record["native_extraction"]["blocks"][0])
        block["locator"]["region"] = {
            "x": 0.1, "y": 0.2, "width": 0.5, "height": 0.3,
        }
        locators = _document_locators(record, block)
        self.assertEqual(
            {item["type"] for item in locators},
            {"PAGE_RANGE", "CHARACTER_RANGE", "REGION", "ARTIFACT_REVISION"},
        )
        revision = next(item for item in locators if item["type"] == "ARTIFACT_REVISION")
        self.assertEqual(revision["revision_id"], record["source"]["revision_id"])


if __name__ == "__main__":
    unittest.main()
