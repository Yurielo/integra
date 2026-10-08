import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from integra_core.documents import extract_document
from integra_core.identity import derive_imported_id
from integra_core.multi_source_alignment import (
    AlignmentError,
    add_link,
    add_node,
    dumps_alignment,
    loads_alignment,
    navigate,
    new_alignment,
    validate_alignment,
)
from integra_core.projects_sources import (
    new_registry,
    register_document,
    register_project,
    register_youtube_video,
)
from integra_core.protocol import canonical_json, content_sha256
from integra_core.translategemma_runtime import MODEL, MODEL_DIGEST
from integra_core.transcript_topic_studio import (
    add_quality_finding,
    new_studio,
    register_artifact,
    register_topic_set,
    register_transcript,
    register_word_timeline,
)


T0 = "2026-09-11T00:00:00Z"
T1 = "2026-09-11T00:01:00Z"
T2 = "2026-09-11T00:02:00Z"
ST_COMMIT = "a94936cd77cde13561c97c804ece1ac1134e01a6"
VT_COMMIT = "2e098d1705b6815628bee1e023f4742718eabf02"
R5_SHA = "38ec6db0172c6bd61d8515b71c32be0554e311684364758cf87c598723dc20c3"
VT_WHISPER_SHA = "64d182b440b98d5203c4f9bd541544d84c605196c4f7b845dfa11fb23594d1e2"
ST_TOPIC_SHA = "ed1e8a40017e648c133188919a5a0105ce1916726dbc657fecb5ccb5d717c46d"


def _studio_bindings() -> list[dict]:
    owners = {
        "media_preparation": ["videotext"], "asr": ["videotext"],
        "translation": ["integra.translation"], "word_timeline": ["seminartext"],
        "topics": ["seminartext"], "review_mechanics": ["seminartext", "videotext"],
        "quality_validation": ["seminartext", "videotext"],
    }
    result = []
    for capability, selected in owners.items():
        components = []
        for component_id in selected:
            contract = (
                "topic_review_workflow_v2"
                if component_id == "seminartext" and capability in {"topics", "review_mechanics"}
                else "canonical_evidence_v1" if component_id == "seminartext"
                else "integra_translation_v1" if component_id == "integra.translation"
                else "project_schema_v7"
            )
            model_id = model_hash = None
            if component_id == "videotext" and capability == "asr":
                model_id, model_hash = "ggml-large-v3.bin", VT_WHISPER_SHA
            if component_id == "seminartext" and capability == "topics":
                model_id, model_hash = "gemma3:4b", ST_TOPIC_SHA
            if component_id == "integra.translation":
                model_id, model_hash = MODEL, MODEL_DIGEST
            components.append({
                "component_id": component_id,
                "commit_sha": ST_COMMIT if component_id == "seminartext" else "f" * 40 if component_id == "integra.translation" else VT_COMMIT,
                "contract_id": contract,
                "model_id": model_id,
                "model_sha256": model_hash,
            })
        result.append({
            "capability": capability, "components": components,
            "config_sha256": "3" * 64, "r5_selection_sha256": R5_SHA,
        })
    return result


def _office_zip(members: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_STORED) as archive:
        for name in sorted(members):
            info = zipfile.ZipInfo(name, (2020, 1, 1, 0, 0, 0))
            archive.writestr(info, members[name])
    return output.getvalue()


def _pptx_bytes() -> bytes:
    return _office_zip({
        "[Content_Types].xml": b"<Types/>",
        "ppt/presentation.xml": (
            b'<p:presentation xmlns:p="urn:p" '
            b'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            b'<p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst>'
            b"</p:presentation>"
        ),
        "ppt/_rels/presentation.xml.rels": (
            b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            b'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" '
            b'Target="slides/slide1.xml"/></Relationships>'
        ),
        "ppt/slides/slide1.xml": (
            b'<p:sld xmlns:p="urn:p" xmlns:a="urn:a"><p:cSld>'
            b"<a:t>Aligned slide</a:t></p:cSld></p:sld>"
        ),
    })


def _pdf_bytes() -> bytes:
    stream = b"BT (Supporting evidence) Tj ET"
    objects = [
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj",
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj",
        b"3 0 obj << /Type /Page /Parent 2 0 R /Contents 4 0 R >> endobj",
        b"4 0 obj << /Length " + str(len(stream)).encode() + b" >>\nstream\n"
        + stream + b"\nendstream\nendobj",
    ]
    return b"%PDF-1.4\n" + b"\n".join(objects) + b"\n%%EOF\n"


class MultiSourceAlignmentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        registry = new_registry("alignment-tests", T0)
        registry, self.project_id = register_project(
            registry, project_key="course", kind="COURSE", title="Course", occurred_at=T0
        )
        registry, self.video_source_id = register_youtube_video(
            registry, self.project_id, video_id="video-1", title="Lesson",
            availability="AVAILABLE", captured_at=T1,
        )
        presentation = root / "slides.pptx"
        presentation.write_bytes(_pptx_bytes())
        self.slide_document = extract_document(presentation, captured_at=T1)
        registry, self.slide_source_id = register_document(
            registry, self.project_id, self.slide_document, captured_at=T1,
        )
        document = root / "support.pdf"
        document.write_bytes(_pdf_bytes())
        self.page_document = extract_document(document, captured_at=T1)
        registry, self.page_source_id = register_document(
            registry, self.project_id, self.page_document, captured_at=T1,
        )
        self.registry = registry
        self.revisions = {
            source["source_id"]: source["current_revision_id"] for source in registry["sources"]
        }
        self.revision_hashes = {
            source["source_id"]: source["revisions"][-1]["revision_sha256"]
            for source in registry["sources"]
        }
        media_locators = [self._time_locator(), self._revision_locator(self.video_source_id)]
        studio = new_studio(
            registry, project_id=self.project_id, source_id=self.video_source_id,
            source_revision_id=self.revisions[self.video_source_id],
            bindings=_studio_bindings(), created_at=T2,
        )
        studio, video_artifact = register_artifact(
            studio, registry=registry, kind="MEDIA_PREPARATION", native_id="video",
            content_sha256="1" * 64, created_at=T2, capability="media_preparation",
            parents=[self.revisions[self.video_source_id]], locators=media_locators,
            semantic_status="NOT_APPLICABLE",
        )
        studio, transcript_artifact = register_transcript(
            studio, registry=registry, native_id="transcript", content_sha256="2" * 64,
            created_at=T2, language="ru", word_count=9, confidence=0.95,
            locators=media_locators,
        )
        words = [
            {"word_id": f"word:{index:06d}", "sequence": index, "text": f"w{index}",
             "start_seconds": float(index), "end_seconds": float(index) + 0.5,
             "confidence": 0.95}
            for index in range(9)
        ]
        studio, timeline_id = register_word_timeline(
            studio, registry=registry, native_id="timeline", content_sha256="3" * 64,
            created_at=T2, transcript_id=transcript_artifact, words=words,
            locators=media_locators,
        )
        topic_locators = media_locators + [self._word_locator()]
        studio, _ = register_topic_set(
            studio, registry=registry, native_id="topic-set", content_sha256="4" * 64,
            created_at=T2, timeline_id=timeline_id, level="NORMAL", topics=[{
                "native_id": "topic", "title": "Topic", "summary": "Summary",
                "confidence": 0.95, "conflict": False, "locators": topic_locators,
                "evidence_refs": ["word:000001", "word:000008"],
            }],
        )
        studio, finding_id = add_quality_finding(
            studio, registry=registry, native_id="evidence", created_at=T2,
            capability="quality_validation", artifact_id=transcript_artifact,
            code="ALIGNMENT_EVIDENCE", severity="INFO", confidence=0.95,
            locators=topic_locators, detail="Alignment evidence",
        )
        topic_id = studio["topic_sets"][0]["topics"][0]["topic_id"]
        self.studio = studio
        records = [
            self._studio_reference("video", "VIDEO", video_artifact),
            self._studio_reference("transcript", "TRANSCRIPT", transcript_artifact),
            self._studio_reference("topic", "TOPIC", topic_id),
            self._studio_reference("evidence", "EVIDENCE", finding_id),
            self._document_reference(
                self.slide_document, self.slide_source_id, "slide", "SLIDE",
                [{"type": "SLIDE_RANGE", "start_slide": 1, "end_slide": 1}, self._revision_locator(self.slide_source_id)],
            ),
            self._document_reference(
                self.page_document, self.page_source_id, "page", "PAGE",
                [{"type": "PAGE_RANGE", "start_page": 1, "end_page": 1}, self._revision_locator(self.page_source_id)],
            ),
            self._document_reference(
                self.page_document, self.page_source_id, "document", "SUPPORTING_DOCUMENT",
                [{"type": "PAGE_RANGE", "start_page": 1, "end_page": 1}, self._revision_locator(self.page_source_id)],
            ),
        ]
        self.artifact_references = copy.deepcopy(records)
        self.upstream_records = [
            {"contract": "TRANSCRIPT_TOPIC_STUDIO_V1", "record_id": studio["studio_id"], "record_sha256": studio["record_sha256"], "record": studio},
            {"contract": "DOCUMENT_EXTRACTION_V1", "record_id": self.slide_document["document_id"], "record_sha256": self.slide_document["record_sha256"], "record": self.slide_document},
            {"contract": "DOCUMENT_EXTRACTION_V1", "record_id": self.page_document["document_id"], "record_sha256": self.page_document["record_sha256"], "record": self.page_document},
        ]
        self.alignment = new_alignment(
            registry, project_id=self.project_id,
            source_revision_ids=list(self.revisions.values()),
            artifact_references=records, upstream_records=self.upstream_records, created_at=T2,
        )
        self.nodes: dict[str, str] = {}
        for reference in records:
            source_locator = reference["provenance"]["source_locator"]
            name = source_locator["native_id"]
            source_id = source_locator["source_id"]
            self.alignment, node_id = add_node(
                self.alignment, registry=registry, upstream_records=self.upstream_records,
                native_id=name, kind=reference["kind"],
                source_id=source_id, source_revision_id=self.revisions[source_id],
                artifact_id=reference["artifact_id"], artifact_sha256=reference["content_sha256"],
                owner_component=reference["origin"]["component_id"],
                locators=list(reversed(source_locator["locators"])),
                lineage_ids=reference["provenance"]["parent_artifact_ids"] + [reference["artifact_id"]],
                semantic_status=reference["semantic_status"],
                created_at=T2,
            )
            self.nodes[name] = node_id

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def _time_locator() -> dict:
        return {"type": "TIME_INTERVAL", "start_seconds": 1.0, "end_seconds": 8.5}

    @staticmethod
    def _word_locator() -> dict:
        return {
            "type": "WORD_INTERVAL", "start_word_id": "word:000001",
            "end_word_id": "word:000008", "start_sequence": 1, "end_sequence": 8,
        }

    def _revision_locator(self, source_id: str) -> dict:
        return {
            "type": "ARTIFACT_REVISION", "artifact_id": source_id,
            "revision_id": self.revisions[source_id],
            "content_sha256": self.revision_hashes[source_id],
        }

    def _origin(self, capability: str) -> dict:
        binding = next(
            item for item in self.studio["component_bindings"].values()
            if item["capability"] == capability
        )
        component = binding["components"][0]
        origin = {
            "component_id": component["component_id"],
            "repository": f"Yurielo/{component['component_id']}",
            "commit_sha": component["commit_sha"],
            "tree_sha": "b" * 40,
            "version": "1.0",
            "contracts": [component["contract_id"]],
            "runtime": {"kind": "python", "version": "3"},
        }
        if component["model_id"] is not None:
            origin["models"] = [{
                "id": component["model_id"],
                "identity_sha256": component["model_sha256"],
            }]
        return origin

    def _studio_reference(self, name: str, kind: str, artifact_id: str) -> dict:
        matches = [item for item in self.studio["artifacts"] if item["artifact_id"] == artifact_id]
        if matches:
            entity = matches[0]
            artifact_hash = entity["content_sha256"]
            parents = entity["parent_ids"]
            capability = entity["capability"]
        else:
            topics = [
                (topic_set, topic) for topic_set in self.studio["topic_sets"]
                for topic in topic_set["topics"] if topic["topic_id"] == artifact_id
            ]
            if topics:
                topic_set, entity = topics[0]
                artifact_hash = content_sha256(entity)
                parents = [topic_set["topic_set_id"], topic_set["timeline_id"]]
                capability = "topics"
            else:
                entity = next(item for item in self.studio["quality_findings"] if item["finding_id"] == artifact_id)
                entity = copy.deepcopy(entity)
                entity["semantic_status"] = "REVIEW_REQUIRED" if entity["review_required"] else "PROVISIONAL"
                artifact_hash = entity["finding_sha256"]
                parents = [entity["artifact_id"]]
                capability = "quality_validation"
        source_id = self.video_source_id
        return {
            "artifact_id": artifact_id, "kind": kind,
            "schema_id": "transcript_topic_studio_v1", "schema_version": "1.0",
            "semantic_status": entity["semantic_status"],
            "content_sha256": artifact_hash, "size_bytes": 10,
            "storage_scope": "SOURCE_READ_ONLY", "relative_path": f"studio/{name}.json",
            "origin": self._origin(capability),
            "provenance": {
                "parent_artifact_ids": sorted(parents),
                "operation_id": derive_imported_id("operation", "fixture.studio", name, artifact_hash),
                "source_locator": {
                    "native_id": entity["native_id"], "source_id": source_id,
                    "source_revision_id": self.revisions[source_id],
                    "source_revision_sha256": self.revision_hashes[source_id],
                    "upstream_record_id": self.studio["studio_id"],
                    "upstream_record_sha256": self.studio["record_sha256"],
                    "upstream_entity_id": artifact_id,
                    "locators": entity["locators"],
                },
            },
        }

    def _document_reference(
        self, document: dict, source_id: str, name: str, kind: str,
        locators: list[dict],
    ) -> dict:
        locators = sorted(copy.deepcopy(locators), key=canonical_json)
        block = (document["native_extraction"]["blocks"] + document["ocr"]["blocks"])[0]
        selection_hash = content_sha256({
            "record_sha256": document["record_sha256"], "kind": kind,
            "native_id": name, "block_id": block["block_id"],
            "block_sha256": block["text_sha256"], "locators": locators,
        })
        artifact_id = derive_imported_id(
            "artifact", "integra.document_pipeline", name, selection_hash
        )
        artifact_hash = content_sha256({
            "record_sha256": document["record_sha256"],
            "block_id": block["block_id"], "block_sha256": block["text_sha256"],
            "locators": locators,
        })
        return {
            "artifact_id": artifact_id, "kind": kind,
            "schema_id": "document_extraction_v1", "schema_version": "1.0",
            "semantic_status": "PROVISIONAL", "content_sha256": artifact_hash,
            "size_bytes": 10, "storage_scope": "SOURCE_READ_ONLY",
            "relative_path": f"documents/{name}.json",
            "origin": {
                "component_id": "integra.document_pipeline", "repository": "Yurielo/integra",
                "commit_sha": "a" * 40, "tree_sha": "b" * 40, "version": "1.0",
                "contracts": ["document_extraction_v1"],
                "runtime": {"kind": "python", "version": "3"},
            },
            "provenance": {
                "parent_artifact_ids": [document["document_id"]],
                "operation_id": derive_imported_id("operation", "fixture.document", name, artifact_hash),
                "source_locator": {
                    "native_id": name, "source_id": source_id,
                    "source_revision_id": self.revisions[source_id],
                    "source_revision_sha256": self.revision_hashes[source_id],
                    "upstream_record_id": document["document_id"],
                    "upstream_record_sha256": document["record_sha256"],
                    "upstream_entity_id": block["block_id"],
                    "locators": locators,
                },
            },
        }

    @staticmethod
    def _reseal(value: dict) -> dict:
        result = copy.deepcopy(value)
        result["record_sha256"] = ""
        result["record_sha256"] = content_sha256(result)
        return result

    def _link(self, name: str, relation: str, source: str, target: str, *, confidence: float = 0.95, conflict: bool = False) -> str:
        self.alignment, link_id = add_link(
            self.alignment, registry=self.registry, upstream_records=self.upstream_records,
            native_id=name, relation=relation,
            from_node_id=self.nodes[source], to_node_id=self.nodes[target],
            evidence_node_ids=[self.nodes[source], self.nodes[target]],
            confidence=confidence, conflict=conflict, method="fixture_alignment", created_at=T2,
        )
        return link_id

    def test_required_navigation_is_deterministic_exact_and_reversible(self) -> None:
        relations = (
            ("video-transcript", "VIDEO_TO_TRANSCRIPT", "video", "transcript"),
            ("video-slide", "VIDEO_TO_SLIDE", "video", "slide"),
            ("topic-page", "TOPIC_TO_PAGE", "topic", "page"),
            ("topic-slide", "TOPIC_TO_SLIDE", "topic", "slide"),
            ("evidence-document", "EVIDENCE_TO_DOCUMENT", "evidence", "document"),
        )
        for values in relations:
            self._link(*values)
        forward = navigate(self.alignment, self.registry, self.upstream_records, self.nodes["video"])["forward"]
        self.assertEqual({item["relation"] for item in forward}, {"VIDEO_TO_TRANSCRIPT", "VIDEO_TO_SLIDE"})
        slide_hop = next(item for item in forward if item["relation"] == "VIDEO_TO_SLIDE")
        slide_node = next(item for item in self.alignment["nodes"] if item["node_id"] == self.nodes["slide"])
        self.assertEqual(slide_hop["locators"], slide_node["locators"])
        reverse = navigate(self.alignment, self.registry, self.upstream_records, self.nodes["slide"])["reverse"]
        self.assertEqual({item["node_id"] for item in reverse}, {self.nodes["video"], self.nodes["topic"]})
        payload = dumps_alignment(self.alignment, self.registry, self.upstream_records)
        self.assertEqual(
            dumps_alignment(
                loads_alignment(payload, self.registry, self.upstream_records),
                self.registry, self.upstream_records,
            ),
            payload,
        )

    def test_machine_alignment_never_claims_semantic_acceptance(self) -> None:
        first = self._link("high", "VIDEO_TO_SLIDE", "video", "slide")
        second = self._link("low", "TOPIC_TO_PAGE", "topic", "page", confidence=0.79)
        third = self._link("conflict", "EVIDENCE_TO_DOCUMENT", "evidence", "document", conflict=True)
        statuses = {item["link_id"]: item["semantic_status"] for item in self.alignment["links"]}
        self.assertEqual(statuses[first], "PROVISIONAL")
        self.assertEqual(statuses[second], "REVIEW_REQUIRED")
        self.assertEqual(statuses[third], "REVIEW_REQUIRED")
        self.assertNotIn("ACCEPTED", json.dumps(self.alignment))
        self.assertFalse(self.alignment["source_artifacts_modified"])

    def test_relation_and_cross_source_contract_fail_closed(self) -> None:
        self._link("video-transcript", "VIDEO_TO_TRANSCRIPT", "video", "transcript")
        with self.assertRaisesRegex(AlignmentError, "endpoints"):
            add_link(
                self.alignment, registry=self.registry, upstream_records=self.upstream_records,
                native_id="wrong-endpoints",
                relation="TOPIC_TO_SLIDE", from_node_id=self.nodes["video"],
                to_node_id=self.nodes["slide"], evidence_node_ids=[self.nodes["video"]],
                confidence=1.0, conflict=False, method="fixture", created_at=T2,
            )

    def test_registry_revision_and_native_locators_are_mandatory(self) -> None:
        artifact_hash = "a" * 64
        artifact_id = derive_imported_id("artifact", "fixture.invalid", "invalid", artifact_hash)
        with self.assertRaisesRegex(AlignmentError, "source-type-native"):
            add_node(
                self.alignment, registry=self.registry, upstream_records=self.upstream_records,
                native_id="invalid-native", kind="SLIDE",
                source_id=self.slide_source_id, source_revision_id=self.revisions[self.slide_source_id],
                artifact_id=artifact_id, artifact_sha256=artifact_hash, owner_component="fixture.invalid",
                locators=[self._time_locator(), self._revision_locator(self.slide_source_id)],
                lineage_ids=[artifact_id], semantic_status="NOT_APPLICABLE", created_at=T2,
            )
        bad_revision = self._revision_locator(self.page_source_id)
        bad_revision["content_sha256"] = "f" * 64
        with self.assertRaisesRegex(AlignmentError, "source revision exactly"):
            add_node(
                self.alignment, registry=self.registry, upstream_records=self.upstream_records,
                native_id="invalid-revision", kind="PAGE",
                source_id=self.page_source_id, source_revision_id=self.revisions[self.page_source_id],
                artifact_id=artifact_id, artifact_sha256=artifact_hash, owner_component="fixture.invalid",
                locators=[{"type": "PAGE_RANGE", "start_page": 1, "end_page": 1}, bad_revision],
                lineage_ids=[artifact_id], semantic_status="NOT_APPLICABLE", created_at=T2,
            )

    def test_tampering_and_registry_drift_are_detected_even_when_resealed(self) -> None:
        self._link("video-slide", "VIDEO_TO_SLIDE", "video", "slide")
        tampered = copy.deepcopy(self.alignment)
        video = next(item for item in tampered["nodes"] if item["kind"] == "VIDEO")
        video["semantic_status"] = "PROVISIONAL"
        with self.assertRaisesRegex(AlignmentError, "authoritative upstream artifact reference"):
            validate_alignment(self._reseal(tampered), self.registry, self.upstream_records)
        drifted, _ = register_youtube_video(
            self.registry, self.project_id, video_id="video-2", title="Other",
            availability="AVAILABLE", captured_at=T2,
        )
        with self.assertRaisesRegex(AlignmentError, "registry snapshot"):
            validate_alignment(self.alignment, drifted, self.upstream_records)

    def test_authoritative_registry_is_required_by_every_public_operation(self) -> None:
        for operation in (
            lambda: validate_alignment(self.alignment, {}, self.upstream_records),
            lambda: dumps_alignment(self.alignment, {}, self.upstream_records),
            lambda: loads_alignment(json.dumps(self.alignment).encode(), {}, self.upstream_records),
            lambda: navigate(self.alignment, {}, self.upstream_records, self.nodes["video"]),
        ):
            with self.subTest(operation=operation):
                with self.assertRaisesRegex(AlignmentError, "registry"):
                    operation()

    def test_malformed_containers_and_links_fail_as_alignment_errors(self) -> None:
        malformed = copy.deepcopy(self.alignment)
        malformed["nodes"] = {}
        with self.assertRaisesRegex(AlignmentError, "must be lists"):
            validate_alignment(self._reseal(malformed), self.registry, self.upstream_records)
        self._link("video-slide", "VIDEO_TO_SLIDE", "video", "slide")
        malformed = copy.deepcopy(self.alignment)
        malformed["links"][0]["relation"] = []
        with self.assertRaisesRegex(AlignmentError, "unsupported"):
            validate_alignment(self._reseal(malformed), self.registry, self.upstream_records)

    def test_catalog_rejects_self_attested_kind_and_inconsistent_region(self) -> None:
        references = copy.deepcopy(self.alignment["artifact_catalog"]["references"])
        slide = next(item for item in references if item["kind"] == "SLIDE")
        slide["kind"] = "VIDEO"
        with self.assertRaisesRegex(AlignmentError, "incompatible with source type"):
            new_alignment(
                self.registry, project_id=self.project_id,
                source_revision_ids=list(self.revisions.values()),
                artifact_references=references, upstream_records=self.upstream_records,
                created_at=T2,
            )

        references = copy.deepcopy(self.alignment["artifact_catalog"]["references"])
        page = next(item for item in references if item["kind"] == "PAGE")
        page["source_locator"]["locators"].append({
            "type": "REGION", "container_type": "PAGE", "container_index": 2,
            "x": 0.0, "y": 0.0, "width": 0.5, "height": 0.5,
        })
        with self.assertRaisesRegex(AlignmentError, "outside the node page range"):
            new_alignment(
                self.registry, project_id=self.project_id,
                source_revision_ids=list(self.revisions.values()),
                artifact_references=references, upstream_records=self.upstream_records,
                created_at=T2,
            )

    def test_external_upstream_records_are_required_and_not_serialized(self) -> None:
        with self.assertRaisesRegex(AlignmentError, "requires validated upstream records"):
            validate_alignment(self.alignment, self.registry, [])
        drifted = copy.deepcopy(self.upstream_records)
        drifted[0]["record_sha256"] = "f" * 64
        with self.assertRaisesRegex(AlignmentError, "identity or hash differs"):
            validate_alignment(self.alignment, self.registry, drifted)

        payload = dumps_alignment(self.alignment, self.registry, self.upstream_records)
        self.assertNotIn(b'"record":', payload)
        self.assertNotIn(b'"upstream_records":', payload)
        self.assertNotIn(b"Aligned slide", payload)
        self.assertIn(b'"upstream_record_bindings":', payload)

    def test_unverifiable_transport_metadata_is_not_persisted_as_authority(self) -> None:
        changed = copy.deepcopy(self.artifact_references)
        changed[0]["origin"]["repository"] = "mirror/example"
        changed[0]["origin"]["tree_sha"] = "f" * 40
        changed[0]["origin"]["version"] = "99.0"
        changed[0]["size_bytes"] = 999999
        changed[0]["relative_path"] = "alternate/video.json"
        changed[0]["provenance"]["operation_id"] = derive_imported_id(
            "operation", "fixture.transport", "alternate", "e" * 64
        )
        rebuilt = new_alignment(
            self.registry, project_id=self.project_id,
            source_revision_ids=list(self.revisions.values()),
            artifact_references=changed, upstream_records=self.upstream_records,
            created_at=T2,
        )
        self.assertEqual(rebuilt, self.alignment | {
            "nodes": [], "links": [], "revision": 0,
            "updated_at": T2,
            "record_sha256": rebuilt["record_sha256"],
        })
        payload = json.dumps(rebuilt, sort_keys=True)
        for value in ("mirror/example", "99.0", "alternate/video.json"):
            self.assertNotIn(value, payload)
        expected_fields = {
            "artifact_id", "kind", "content_sha256", "semantic_status",
            "owner_component", "parent_artifact_ids", "source_locator",
        }
        self.assertTrue(all(
            set(item) == expected_fields
            for item in rebuilt["artifact_catalog"]["references"]
        ))

    def test_runtime_catalog_shape_matches_json_schema(self) -> None:
        schema_path = (
            Path(__file__).resolve().parents[1]
            / "schemas" / "multi_source_alignment_v1.schema.json"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        catalog_schema = schema["properties"]["artifact_catalog"]
        self.assertEqual(
            catalog_schema["properties"]["references"]["items"]["$ref"],
            "#/$defs/catalog_reference",
        )
        reference = self.alignment["artifact_catalog"]["references"][0]
        self.assertEqual(set(reference), set(schema["$defs"]["catalog_reference"]["required"]))
        locator = reference["source_locator"]
        locator_schema = schema["$defs"]["catalog_reference"]["properties"]["source_locator"]
        self.assertEqual(set(locator), set(locator_schema["required"]))
        binding = self.alignment["artifact_catalog"]["upstream_record_bindings"][0]
        self.assertEqual(
            set(binding), set(schema["$defs"]["upstream_record_binding"]["required"])
        )


if __name__ == "__main__":
    unittest.main()
