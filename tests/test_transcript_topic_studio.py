import copy
from datetime import datetime, timedelta, timezone
import io
from pathlib import Path
import tempfile
import unittest
import zipfile

from integra_core.documents import extract_document
from integra_core.identity import derive_imported_id
from integra_core.protocol import content_sha256
from integra_core.project_lease import LeaseStore
from integra_core.projects_sources import (
    new_registry,
    register_document,
    register_project,
    register_youtube_video,
)
from integra_core.transcript_topic_studio import (
    StudioError,
    add_quality_finding,
    apply_review_decision,
    build_exception_package,
    dumps_studio,
    loads_studio,
    new_studio,
    register_artifact,
    register_hierarchy,
    register_topic_set,
    register_transcript,
    register_translation,
    register_word_timeline,
    validate_studio,
)


H = "1" * 64
H2 = "2" * 64
H3 = "3" * 64
ST_COMMIT = "970bde598ddd649599295139986933e0e06cb9c0"
VT_COMMIT = "2e098d1705b6815628bee1e023f4742718eabf02"
R5_SHA = "38ec6db0172c6bd61d8515b71c32be0554e311684364758cf87c598723dc20c3"
VT_WHISPER_SHA = "64d182b440b98d5203c4f9bd541544d84c605196c4f7b845dfa11fb23594d1e2"
ST_TOPIC_SHA = "ed1e8a40017e648c133188919a5a0105ce1916726dbc657fecb5ccb5d717c46d"
T0 = "2026-09-11T00:00:00Z"
_REGISTRIES = {}


def _with_registry(function):
    def call(studio, *args, **kwargs):
        if "registry" not in kwargs:
            kwargs["registry"] = _REGISTRIES[studio["studio_id"]]
        return function(studio, *args, **kwargs)
    return call


for _function_name in (
    "register_artifact", "register_transcript", "register_translation",
    "register_word_timeline", "add_quality_finding", "register_topic_set",
    "register_hierarchy", "build_exception_package", "apply_review_decision",
    "dumps_studio", "validate_studio",
):
    globals()[_function_name] = _with_registry(globals()[_function_name])


def uid(namespace, native, digest=H):
    return derive_imported_id(namespace, "test", native, digest)


def component(component_id, capability):
    seminartext_contract = "topic_review_workflow_v2" if capability in {"topics", "review_mechanics"} else "canonical_evidence_v1"
    contract = seminartext_contract if component_id == "seminartext" else "project_schema_v7"
    model_id = None
    model_sha = None
    if component_id == "videotext" and capability == "asr":
        model_id, model_sha = "ggml-large-v3.bin", VT_WHISPER_SHA
    elif component_id == "seminartext" and capability == "topics":
        model_id, model_sha = "gemma3:4b", ST_TOPIC_SHA
    return {
        "component_id": component_id,
        "commit_sha": ST_COMMIT if component_id == "seminartext" else VT_COMMIT,
        "contract_id": contract,
        "model_id": model_id,
        "model_sha256": model_sha,
    }


def bindings():
    owners = {
        "media_preparation": ["videotext"],
        "asr": ["videotext"],
        "translation": ["videotext"],
        "word_timeline": ["seminartext"],
        "topics": ["seminartext"],
        "review_mechanics": ["seminartext", "videotext"],
        "quality_validation": ["seminartext", "videotext"],
    }
    return [
        {
            "capability": capability,
            "components": [component(owner, capability) for owner in selected],
            "config_sha256": H3,
            "r5_selection_sha256": R5_SHA,
        }
        for capability, selected in owners.items()
    ]


def _office_zip(members):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_STORED) as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
    return output.getvalue()


def registry(source_type="YOUTUBE_VIDEO"):
    value = new_registry("studio-tests", T0)
    value, project_id = register_project(
        value, project_key="project", kind="SEMINAR", title="Project", occurred_at=T0
    )
    if source_type == "YOUTUBE_VIDEO":
        value, source_id = register_youtube_video(
            value, project_id, video_id="fixture-video", title="Fixture video",
            availability="AVAILABLE", captured_at="2026-09-11T00:00:01Z",
        )
    else:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            if source_type == "TXT":
                path = root / "notes.txt"
                path.write_text("Exact text", encoding="utf-8")
                image_role = None
            elif source_type == "PDF":
                path = root / "paper.pdf"
                path.write_bytes(
                    b"%PDF-1.4\n1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
                    b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
                    b"3 0 obj << /Type /Page /Parent 2 0 R /Contents 4 0 R >> endobj\n"
                    b"4 0 obj << /Length 19 >>\nstream\nBT (Page) Tj ET\nendstream\nendobj\n%%EOF\n"
                )
                image_role = None
            elif source_type == "PPTX":
                path = root / "slides.pptx"
                path.write_bytes(_office_zip({
                    "[Content_Types].xml": b"<Types/>",
                    "ppt/presentation.xml": b'<p:presentation xmlns:p="urn:p" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst></p:presentation>',
                    "ppt/_rels/presentation.xml.rels": b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide1.xml"/></Relationships>',
                    "ppt/slides/slide1.xml": b'<p:sld xmlns:p="urn:p" xmlns:a="urn:a"><p:cSld><a:t>Slide</a:t></p:cSld></p:sld>',
                }))
                image_role = None
            elif source_type == "SCAN":
                path = root / "scan.png"
                path.write_bytes(bytes.fromhex(
                    "89504e470d0a1a0a0000000d49484452000000010000000108000000003a7e9b55"
                    "0000000a49444154789c636000000002000148afa4710000000049454e44ae426082"
                ))
                image_role = "SCAN"
            else:
                raise AssertionError(source_type)
            document = extract_document(path, captured_at="2026-09-11T00:00:01Z")
            value, source_id = register_document(
                value, project_id, document,
                captured_at="2026-09-11T00:00:01Z", image_role=image_role,
            )
    source = next(item for item in value["sources"] if item["source_id"] == source_id)
    return value, project_id, source_id, source["current_revision_id"]


def time_locator(start=0.0, end=10.0):
    return {"type": "TIME_INTERVAL", "start_seconds": start, "end_seconds": end}


def artifact_locator(source_id, revision_id, digest=H):
    return {
        "type": "ARTIFACT_REVISION",
        "artifact_id": source_id,
        "revision_id": revision_id,
        "content_sha256": digest,
    }


def word_locator(start, end):
    return {
        "type": "WORD_INTERVAL",
        "start_word_id": f"word:{start:06d}",
        "end_word_id": f"word:{end:06d}",
        "start_sequence": start,
        "end_sequence": end,
    }


def make_studio(source_type="YOUTUBE_VIDEO"):
    value, project_id, source_id, revision_id = registry(source_type)
    studio = new_studio(
        value,
        project_id=project_id,
        source_id=source_id,
        source_revision_id=revision_id,
        bindings=bindings(),
        created_at=T0,
    )
    _REGISTRIES[studio["studio_id"]] = value
    return studio, project_id, source_id, revision_id


def build_media_studio():
    studio, project_id, source_id, revision_id = make_studio()
    locators = [
        time_locator(),
        artifact_locator(source_id, revision_id, studio["source"]["source_revision_sha256"]),
    ]
    studio, transcript_id = register_transcript(
        studio,
        native_id="transcript-r1",
        content_sha256=H2,
        created_at="2026-09-11T00:01:00Z",
        language="ru",
        word_count=4,
        confidence=0.92,
        locators=locators,
    )
    words = [
        {
            "word_id": f"word:{index:06d}",
            "sequence": index,
            "text": text,
            "start_seconds": float(index),
            "end_seconds": float(index) + 0.5,
            "confidence": 0.9,
        }
        for index, text in enumerate(("один", "два", "три", "четыре"))
    ]
    studio, timeline_id = register_word_timeline(
        studio,
        native_id="timeline-r1",
        content_sha256=H3,
        created_at="2026-09-11T00:02:00Z",
        transcript_id=transcript_id,
        words=words,
        locators=locators,
    )
    return studio, project_id, source_id, revision_id, transcript_id, timeline_id


def topic(native_id, start, end, *, studio, confidence=0.9, conflict=False):
    return {
        "native_id": native_id,
        "title": f"Topic {native_id}",
        "summary": "Traceable machine proposal",
        "confidence": confidence,
        "conflict": conflict,
        "locators": [
            time_locator(float(start), float(end) + 0.5),
            word_locator(start, end),
            artifact_locator(
                studio["source"]["source_id"],
                studio["source"]["source_revision_id"],
                studio["source"]["source_revision_sha256"],
            ),
        ],
        "evidence_refs": sorted({f"word:{start:06d}", f"word:{end:06d}"}),
    }


def review_lease(project_id, package):
    now = datetime.now(timezone.utc)
    acquired = (now - timedelta(minutes=1)).isoformat().replace("+00:00", "Z")
    expires = (now + timedelta(minutes=10)).isoformat().replace("+00:00", "Z")
    return {
        "schema_version": "1.0",
        "lease_id": uid("lease", "lease"),
        "project_id": project_id,
        "mutable_entity": {"namespace": "review", "entity_id": package["package_id"]},
        "writer": {
            "component_id": "integra.review_service",
            "host_id": "test-host",
            "process_id": 123,
            "process_start_token": "test-process",
        },
        "operation_id": uid("operation", "review"),
        "acquired_at": acquired,
        "heartbeat_at": acquired,
        "expires_at": expires,
        "artifact_precondition": {
            "revision_id": package["package_id"],
            "content_sha256": package["scope_sha256"],
        },
        "readers": [],
        "generation": 1,
        "state": "ACTIVE",
    }


def reseal(studio):
    studio["record_sha256"] = ""
    studio["record_sha256"] = content_sha256(studio)
    return studio


class TranscriptTopicStudioTests(unittest.TestCase):
    def test_media_preparation_is_exposed_with_exact_component_and_source_revision(self):
        studio, _, source_id, revision_id = make_studio()
        studio, artifact_id = register_artifact(
            studio, kind="MEDIA_PREPARATION", native_id="prepared-media-r1",
            content_sha256=H2, created_at="2026-09-11T00:01:00Z",
            capability="media_preparation", parents=[revision_id],
            locators=[time_locator(), artifact_locator(
                source_id, revision_id, studio["source"]["source_revision_sha256"]
            )],
            semantic_status="NOT_APPLICABLE",
            metadata={"operation": "READ_ONLY_PREPARATION"},
        )
        record = next(item for item in studio["artifacts"] if item["artifact_id"] == artifact_id)
        self.assertEqual(record["capability"], "media_preparation")
        self.assertEqual(
            studio["component_bindings"]["media_preparation"]["components"][0]["component_id"],
            "videotext",
        )

    def test_new_studio_binds_exact_current_source_and_r5_owners(self):
        studio, project_id, source_id, revision_id = make_studio()
        self.assertEqual(studio["project_id"], project_id)
        self.assertEqual(studio["source"]["source_id"], source_id)
        self.assertEqual(studio["source"]["source_revision_id"], revision_id)
        self.assertEqual(
            [item["component_id"] for item in studio["component_bindings"]["quality_validation"]["components"]],
            ["seminartext", "videotext"],
        )
        self.assertEqual(studio["cross_source_alignment"], "OUT_OF_SCOPE_R8C")
        validate_studio(studio)

    def test_studio_rejects_stale_source_revision(self):
        value, project_id, source_id, revision_id = registry()
        value["sources"][0]["current_revision_id"] = uid("revision", "new")
        with self.assertRaisesRegex(StudioError, "registry is invalid"):
            new_studio(value, project_id=project_id, source_id=source_id, source_revision_id=revision_id, bindings=bindings(), created_at=T0)

    def test_composed_owner_order_is_fail_closed(self):
        value, project_id, source_id, revision_id = registry()
        bad = bindings()
        selected = next(item for item in bad if item["capability"] == "quality_validation")
        selected["components"].reverse()
        with self.assertRaisesRegex(StudioError, "accepted R5"):
            new_studio(value, project_id=project_id, source_id=source_id, source_revision_id=revision_id, bindings=bad, created_at=T0)

    def test_component_baseline_and_r5_selection_are_fail_closed(self):
        value, project_id, source_id, revision_id = registry()
        for field, replacement, message in (
            ("commit_sha", "f" * 40, "accepted R1"),
            ("contract_id", "fabricated.contract", "accepted R1"),
        ):
            bad = bindings()
            bad[0]["components"][0][field] = replacement
            with self.assertRaisesRegex(StudioError, message):
                new_studio(value, project_id=project_id, source_id=source_id, source_revision_id=revision_id, bindings=bad, created_at=T0)
        bad = bindings()
        bad[0]["r5_selection_sha256"] = H
        with self.assertRaisesRegex(StudioError, "accepted R5"):
            new_studio(value, project_id=project_id, source_id=source_id, source_revision_id=revision_id, bindings=bad, created_at=T0)
        bad = bindings()
        topics_binding = next(item for item in bad if item["capability"] == "topics")
        topics_binding["components"][0]["model_id"] = None
        topics_binding["components"][0]["model_sha256"] = None
        with self.assertRaisesRegex(StudioError, "Topic model"):
            new_studio(value, project_id=project_id, source_id=source_id, source_revision_id=revision_id, bindings=bad, created_at=T0)

    def test_low_confidence_transcript_and_translation_remain_review_required(self):
        studio, _, source_id, revision_id = make_studio()
        locators = [time_locator(), artifact_locator(source_id, revision_id, studio["source"]["source_revision_sha256"])]
        studio, transcript_id = register_transcript(
            studio, native_id="t1", content_sha256=H2,
            created_at="2026-09-11T00:01:00Z", language="ru", word_count=3,
            confidence=0.4, locators=locators,
        )
        transcript = studio["artifacts"][0]
        self.assertEqual(transcript["semantic_status"], "REVIEW_REQUIRED")
        studio, translation_id = register_translation(
            studio, native_id="tr1", content_sha256=H3,
            created_at="2026-09-11T00:02:00Z", transcript_id=transcript_id,
            source_language="ru", target_language="en", confidence=0.7,
            locators=locators,
        )
        translation = next(item for item in studio["artifacts"] if item["artifact_id"] == translation_id)
        self.assertEqual(translation["semantic_status"], "REVIEW_REQUIRED")
        self.assertEqual(translation["metadata"]["original_transcript_id"], transcript_id)
        self.assertEqual(translation["metadata"]["wording"], "DERIVED_TRANSLATION")
        studio, package_id = build_exception_package(
            studio, native_id="language-review", created_at="2026-09-11T00:03:00Z",
            member_ids=[transcript_id, translation_id],
        )
        package = next(item for item in studio["review_packages"] if item["package_id"] == package_id)
        self.assertEqual(package["member_ids"], sorted([transcript_id, translation_id]))

    def test_translation_language_lineage_must_match(self):
        studio, _, source_id, revision_id = make_studio()
        locators = [time_locator(), artifact_locator(source_id, revision_id, studio["source"]["source_revision_sha256"])]
        studio, transcript_id = register_transcript(
            studio, native_id="t1", content_sha256=H2,
            created_at="2026-09-11T00:01:00Z", language="ru", word_count=3,
            confidence=0.9, locators=locators,
        )
        with self.assertRaisesRegex(StudioError, "source language differs"):
            register_translation(
                studio, native_id="tr1", content_sha256=H3,
                created_at="2026-09-11T00:02:00Z", transcript_id=transcript_id,
                source_language="de", target_language="en", confidence=0.9,
                locators=locators,
            )

    def test_artifact_locator_must_match_exact_studio_source_revision(self):
        studio, _, source_id, revision_id = make_studio()
        with self.assertRaisesRegex(StudioError, "source revision exactly"):
            register_transcript(
                studio, native_id="t1", content_sha256=H2,
                created_at="2026-09-11T00:01:00Z", language="ru", word_count=3,
                confidence=0.9,
                locators=[time_locator(), artifact_locator(source_id, revision_id, H)],
            )

    def test_word_timeline_requires_contiguous_order_and_original_text(self):
        studio, _, source_id, revision_id = make_studio()
        locators = [time_locator(), artifact_locator(source_id, revision_id, studio["source"]["source_revision_sha256"])]
        studio, transcript_id = register_transcript(
            studio, native_id="t1", content_sha256=H2,
            created_at="2026-09-11T00:01:00Z", language="ru", word_count=2,
            confidence=0.9, locators=locators,
        )
        words = [
            {"word_id": "word:1", "sequence": 1, "text": "слово", "start_seconds": 0.0, "end_seconds": 0.5, "confidence": 0.9}
        ]
        with self.assertRaisesRegex(StudioError, "sequence"):
            register_word_timeline(
                studio, native_id="w1", content_sha256=H3,
                created_at="2026-09-11T00:02:00Z", transcript_id=transcript_id,
                words=words, locators=locators,
            )

    def test_topic_levels_hierarchy_and_per_source_locators(self):
        studio, _, _, _, _, timeline_id = build_media_studio()
        studio, detailed_id = register_topic_set(
            studio, native_id="detail", content_sha256="4" * 64,
            created_at="2026-09-11T00:03:00Z", timeline_id=timeline_id,
            level="DETAILED", topics=[topic("d1", 0, 1, studio=studio), topic("d2", 2, 3, studio=studio)],
        )
        studio, normal_id = register_topic_set(
            studio, native_id="normal", content_sha256="5" * 64,
            created_at="2026-09-11T00:04:00Z", timeline_id=timeline_id,
            level="NORMAL", topics=[topic("n1", 0, 3, studio=studio)],
        )
        studio, coarse_id = register_topic_set(
            studio, native_id="coarse", content_sha256="6" * 64,
            created_at="2026-09-11T00:05:00Z", timeline_id=timeline_id,
            level="COARSE", topics=[topic("c1", 0, 3, studio=studio)],
        )
        self.assertEqual([item["level"] for item in studio["topic_sets"]], ["DETAILED", "NORMAL", "COARSE"])
        ids = {
            item["native_id"]: item["topic_id"]
            for topic_set in studio["topic_sets"]
            for item in topic_set["topics"]
        }
        studio, hierarchy_id = register_hierarchy(
            studio, native_id="h1", created_at="2026-09-11T00:06:00Z",
            edges=[
                {"child_topic_id": ids["d1"], "parent_topic_id": ids["n1"]},
                {"child_topic_id": ids["d2"], "parent_topic_id": ids["n1"]},
                {"child_topic_id": ids["n1"], "parent_topic_id": ids["c1"]},
            ],
        )
        self.assertTrue(hierarchy_id.startswith("urn:integra:artifact:"))
        self.assertEqual(len(studio["hierarchies"][0]["edges"]), 3)
        self.assertEqual({detailed_id, normal_id, coarse_id}, {item["topic_set_id"] for item in studio["topic_sets"]})
        validate_studio(studio)

    def test_overlapping_topics_fail_closed(self):
        studio, _, _, _, _, timeline_id = build_media_studio()
        with self.assertRaisesRegex(StudioError, "overlap"):
            register_topic_set(
                studio, native_id="detail", content_sha256="4" * 64,
                created_at="2026-09-11T00:03:00Z", timeline_id=timeline_id,
                level="DETAILED", topics=[topic("d1", 0, 2, studio=studio), topic("d2", 2, 3, studio=studio)],
            )

    def test_topic_word_and_evidence_refs_must_resolve_in_timeline(self):
        studio, _, _, _, _, timeline_id = build_media_studio()
        invalid_word = topic("bad-word", 0, 1, studio=studio)
        invalid_word["locators"][1]["end_word_id"] = "word:999999"
        with self.assertRaisesRegex(StudioError, "does not resolve"):
            register_topic_set(
                studio, native_id="detail", content_sha256="4" * 64,
                created_at="2026-09-11T00:03:00Z", timeline_id=timeline_id,
                level="DETAILED", topics=[invalid_word],
            )
        invalid_evidence = topic("bad-evidence", 0, 1, studio=studio)
        invalid_evidence["evidence_refs"] = ["word:000003"]
        with self.assertRaisesRegex(StudioError, "evidence does not resolve"):
            register_topic_set(
                studio, native_id="detail", content_sha256="4" * 64,
                created_at="2026-09-11T00:03:00Z", timeline_id=timeline_id,
                level="DETAILED", topics=[invalid_evidence],
            )

    def test_hierarchy_parent_must_contain_child(self):
        studio, _, _, _, _, timeline_id = build_media_studio()
        studio, _ = register_topic_set(
            studio, native_id="detail", content_sha256="4" * 64,
            created_at="2026-09-11T00:03:00Z", timeline_id=timeline_id,
            level="DETAILED", topics=[topic("d1", 0, 1, studio=studio)],
        )
        studio, _ = register_topic_set(
            studio, native_id="normal", content_sha256="5" * 64,
            created_at="2026-09-11T00:04:00Z", timeline_id=timeline_id,
            level="NORMAL", topics=[topic("n1", 2, 3, studio=studio)],
        )
        ids = {item["native_id"]: item["topic_id"] for group in studio["topic_sets"] for item in group["topics"]}
        with self.assertRaisesRegex(StudioError, "does not contain"):
            register_hierarchy(
                studio, native_id="h1", created_at="2026-09-11T00:05:00Z",
                edges=[{"child_topic_id": ids["d1"], "parent_topic_id": ids["n1"]}],
            )

    def test_document_topics_preserve_page_slide_region_and_revision_locators(self):
        for source_type, specific in (
            ("PDF", {"type": "PAGE_RANGE", "start_page": 1, "end_page": 2}),
            ("PPTX", {"type": "SLIDE_RANGE", "start_slide": 2, "end_slide": 3}),
            ("SCAN", {"type": "REGION", "container_type": "PAGE", "container_index": 1, "x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4}),
            ("TXT", {"type": "CHARACTER_RANGE", "start_char": 0, "end_char": 10}),
        ):
            studio, _, source_id, revision_id = make_studio(source_type)
            locators = [specific, artifact_locator(source_id, revision_id, studio["source"]["source_revision_sha256"])]
            studio, transcript_id = register_transcript(
                studio, native_id=f"t-{source_type}", content_sha256=H2,
                created_at="2026-09-11T00:01:00Z", language="ru", word_count=2,
                confidence=0.9, locators=locators,
            )
            studio, timeline_id = register_word_timeline(
                studio, native_id=f"w-{source_type}", content_sha256=H3,
                created_at="2026-09-11T00:02:00Z", transcript_id=transcript_id,
                words=[
                    {"word_id": "word:000000", "sequence": 0, "text": "a", "start_seconds": 0.0, "end_seconds": 0.1, "confidence": 0.9}
                ],
                locators=locators,
            )
            studio, _ = register_topic_set(
                studio, native_id=f"s-{source_type}", content_sha256="4" * 64,
                created_at="2026-09-11T00:03:00Z", timeline_id=timeline_id,
                level="NORMAL",
                topics=[{
                    "native_id": "topic", "title": "Document Topic", "summary": "summary",
                    "confidence": 0.9, "conflict": False,
                    "locators": locators + [word_locator(0, 0)],
                    "evidence_refs": ["word:000000"],
                }],
            )
            validate_studio(studio)

    def test_document_artifacts_require_source_native_locator(self):
        studio, _, source_id, revision_id = make_studio("PDF")
        for locators in (
            [artifact_locator(source_id, revision_id, studio["source"]["source_revision_sha256"])],
            [
                {"type": "SLIDE_RANGE", "start_slide": 1, "end_slide": 1},
                artifact_locator(source_id, revision_id, studio["source"]["source_revision_sha256"]),
            ],
            [
                {"type": "REGION", "container_type": "IMAGE", "container_index": 1, "x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0},
                artifact_locator(source_id, revision_id, studio["source"]["source_revision_sha256"]),
            ],
        ):
            with self.assertRaisesRegex(StudioError, "document artifact lacks|region locator container"):
                register_transcript(
                    studio, native_id="t-pdf", content_sha256=H2,
                    created_at="2026-09-11T00:01:00Z", language="ru", word_count=1,
                    confidence=0.9, locators=locators,
                )

    def test_hierarchy_requires_consistent_containment_across_all_locators(self):
        studio, _, _, _, _, timeline_id = build_media_studio()
        studio, _ = register_topic_set(
            studio, native_id="detail", content_sha256="4" * 64,
            created_at="2026-09-11T00:03:00Z", timeline_id=timeline_id,
            level="DETAILED", topics=[topic("d1", 0, 1, studio=studio)],
        )
        parent = topic("n1", 2, 3, studio=studio)
        parent["locators"][0] = time_locator(0.0, 3.5)
        studio, _ = register_topic_set(
            studio, native_id="normal", content_sha256="5" * 64,
            created_at="2026-09-11T00:04:00Z", timeline_id=timeline_id,
            level="NORMAL", topics=[parent],
        )
        ids = {item["native_id"]: item["topic_id"] for group in studio["topic_sets"] for item in group["topics"]}
        with self.assertRaisesRegex(StudioError, "does not contain"):
            register_hierarchy(
                studio, native_id="h-conflict", created_at="2026-09-11T00:05:00Z",
                edges=[{"child_topic_id": ids["d1"], "parent_topic_id": ids["n1"]}],
            )

    def test_quality_finding_requires_source_locator(self):
        studio, _, _, _, transcript_id, _ = build_media_studio()
        with self.assertRaisesRegex(StudioError, "quality finding requires"):
            add_quality_finding(
                studio, native_id="missing-locator", created_at="2026-09-11T00:03:00Z",
                capability="quality_validation", artifact_id=transcript_id,
                code="LOW_CONFIDENCE", severity="WARN", confidence=0.5,
                locators=[], detail="must be located",
            )

    def test_quality_exception_clustering_includes_neighbors(self):
        studio, _, _, _, transcript_id, timeline_id = build_media_studio()
        studio, finding_id = add_quality_finding(
            studio, native_id="low-asr", created_at="2026-09-11T00:03:00Z",
            capability="quality_validation", artifact_id=transcript_id,
            code="LOW_CONFIDENCE", severity="WARN", confidence=0.5,
            locators=[time_locator(1, 2)], detail="ASR confidence below threshold",
        )
        studio, _ = register_topic_set(
            studio, native_id="detail", content_sha256="4" * 64,
            created_at="2026-09-11T00:04:00Z", timeline_id=timeline_id,
            level="DETAILED", topics=[
                topic("d1", 0, 0, studio=studio),
                topic("d2", 1, 1, studio=studio, conflict=True),
                topic("d3", 2, 2, studio=studio),
            ],
        )
        ids = {item["native_id"]: item["topic_id"] for item in studio["topic_sets"][0]["topics"]}
        studio, package_id = build_exception_package(
            studio, native_id="exceptions-1", created_at="2026-09-11T00:05:00Z",
            member_ids=[finding_id, ids["d2"]], neighbor_count=1,
        )
        package = next(item for item in studio["review_packages"] if item["package_id"] == package_id)
        self.assertEqual(package["member_ids"], sorted([finding_id, ids["d2"]]))
        self.assertEqual(package["neighbor_topic_ids"], sorted([ids["d1"], ids["d3"]]))

    def test_authorized_bulk_decision_is_deterministic_and_does_not_mutate_sources(self):
        studio, project_id, _, _, _, timeline_id = build_media_studio()
        studio, _ = register_topic_set(
            studio, native_id="detail", content_sha256="4" * 64,
            created_at="2026-09-11T00:03:00Z", timeline_id=timeline_id,
            level="DETAILED", topics=[topic("d1", 0, 2, studio=studio, confidence=0.5)],
        )
        topic_id = studio["topic_sets"][0]["topics"][0]["topic_id"]
        studio, package_id = build_exception_package(
            studio, native_id="p1", created_at="2026-09-11T00:04:00Z",
            member_ids=[topic_id], neighbor_count=1,
        )
        package = studio["review_packages"][0]
        with tempfile.TemporaryDirectory() as directory:
            store = LeaseStore(Path(directory))
            lease = store.acquire(review_lease(project_id, package))
            before_artifacts = copy.deepcopy(studio["artifacts"])
            before_topics = copy.deepcopy(studio["topic_sets"])
            args = dict(
                package_id=package_id, native_id="decision-1",
                decided_at=lease["heartbeat_at"], authority="HUMAN_DOMAIN_REVIEW",
                scope_sha256=package["scope_sha256"],
                resolutions=[{"member_id": topic_id, "resolution": "ACCEPT", "decision_payload_sha256": H}],
                lease=lease, lease_store=store,
            )
            decided, decision_id = apply_review_decision(studio, **args)
            self.assertEqual(decided["artifacts"], before_artifacts)
            self.assertEqual(decided["topic_sets"], before_topics)
            self.assertFalse(decided["review_decisions"][0]["source_artifacts_modified"])
            self.assertEqual(decided["review_packages"][0]["decision_id"], decision_id)
            with self.assertRaisesRegex(StudioError, "stale or already resolved"):
                apply_review_decision(decided, **args)

    def test_decision_rejects_wrong_authority_scope_or_lease(self):
        studio, project_id, _, _, _, timeline_id = build_media_studio()
        studio, _ = register_topic_set(
            studio, native_id="detail", content_sha256="4" * 64,
            created_at="2026-09-11T00:03:00Z", timeline_id=timeline_id,
            level="DETAILED", topics=[topic("d1", 0, 2, studio=studio, confidence=0.5)],
        )
        member = studio["topic_sets"][0]["topics"][0]["topic_id"]
        studio, package_id = build_exception_package(
            studio, native_id="p1", created_at="2026-09-11T00:04:00Z",
            member_ids=[member],
        )
        package = studio["review_packages"][0]
        with tempfile.TemporaryDirectory() as directory:
            store = LeaseStore(Path(directory))
            lease = store.acquire(review_lease(project_id, package))
            common = dict(package_id=package_id, native_id="d", decided_at=lease["heartbeat_at"], scope_sha256=package["scope_sha256"], resolutions=[{"member_id": member, "resolution": "ACCEPT", "decision_payload_sha256": H}], lease=lease, lease_store=store)
            with self.assertRaisesRegex(StudioError, "human domain authority"):
                apply_review_decision(studio, authority="MACHINE", **common)
            common["scope_sha256"] = H
            with self.assertRaisesRegex(StudioError, "scope"):
                apply_review_decision(studio, authority="HUMAN_DOMAIN_REVIEW", **common)
            common["scope_sha256"] = package["scope_sha256"]
            common["lease"] = copy.deepcopy(lease)
            common["lease"]["state"] = "RELEASED"
            with self.assertRaisesRegex(StudioError, "authoritative LeaseStore"):
                apply_review_decision(studio, authority="HUMAN_DOMAIN_REVIEW", **common)

    def test_review_decision_rejects_expired_lease_and_stale_candidate_content(self):
        studio, project_id, _, _, _, timeline_id = build_media_studio()
        studio, _ = register_topic_set(
            studio, native_id="detail", content_sha256="4" * 64,
            created_at="2026-09-11T00:03:00Z", timeline_id=timeline_id,
            level="DETAILED", topics=[topic("d1", 0, 1, studio=studio, confidence=0.5)],
        )
        member = studio["topic_sets"][0]["topics"][0]["topic_id"]
        studio, package_id = build_exception_package(
            studio, native_id="p1", created_at="2026-09-11T00:04:00Z", member_ids=[member],
        )
        package = studio["review_packages"][0]
        with tempfile.TemporaryDirectory() as directory:
            store = LeaseStore(Path(directory))
            lease = store.acquire(review_lease(project_id, package))
            args = dict(
                package_id=package_id, native_id="d", authority="HUMAN_DOMAIN_REVIEW",
                scope_sha256=package["scope_sha256"], lease=lease, lease_store=store,
                resolutions=[{"member_id": member, "resolution": "ACCEPT", "decision_payload_sha256": H}],
            )
            expired_candidate = review_lease(project_id, package)
            expired_candidate["acquired_at"] = "2020-01-01T00:00:00Z"
            expired_candidate["heartbeat_at"] = "2020-01-01T00:00:00Z"
            expired_candidate["expires_at"] = "2020-01-01T00:10:00Z"
            with tempfile.TemporaryDirectory() as expired_directory:
                expired_store = LeaseStore(Path(expired_directory))
                expired = expired_store.acquire(expired_candidate)
                expired_args = {**args, "lease": expired, "lease_store": expired_store}
                with self.assertRaisesRegex(StudioError, "expired at execution time"):
                    apply_review_decision(studio, decided_at="2020-01-01T00:05:00Z", **expired_args)
            tampered = copy.deepcopy(studio)
            tampered["topic_sets"][0]["topics"][0]["title"] = "Changed after review"
            tampered["topic_sets"][0]["payload_sha256"] = content_sha256(tampered["topic_sets"][0]["topics"])
            reseal(tampered)
            with self.assertRaisesRegex(StudioError, "candidate content is stale"):
                apply_review_decision(tampered, decided_at=lease["heartbeat_at"], **args)

    def test_studio_does_not_create_a_competing_job_store(self):
        studio, *_ = make_studio()
        self.assertNotIn("jobs", studio)

    def test_serialization_round_trip_and_tampering_detection(self):
        value, project_id, source_id, revision_id = registry()
        studio = new_studio(value, project_id=project_id, source_id=source_id, source_revision_id=revision_id, bindings=bindings(), created_at=T0)
        _REGISTRIES[studio["studio_id"]] = value
        payload = dumps_studio(studio)
        self.assertEqual(loads_studio(payload, value), studio)
        tampered = copy.deepcopy(studio)
        tampered["source_artifacts_modified"] = True
        with self.assertRaisesRegex(StudioError, "source artifact mutation"):
            validate_studio(tampered)

    def test_authoritative_registry_rejects_rebound_source_even_when_resealed(self):
        value, project_id, source_id, revision_id = registry()
        studio = new_studio(value, project_id=project_id, source_id=source_id, source_revision_id=revision_id, bindings=bindings(), created_at=T0)
        tampered = copy.deepcopy(studio)
        tampered["source"]["source_type"] = "LOCAL_AUDIO"
        tampered["source"]["source_binding_sha256"] = content_sha256({
            "project_id": project_id,
            "source_id": source_id,
            "source_revision_id": revision_id,
            "source_revision_sha256": tampered["source"]["source_revision_sha256"],
            "source_type": "LOCAL_AUDIO",
            "registry_binding": tampered["registry_binding"],
        })
        tampered["studio_id"] = derive_imported_id(
            "artifact", "integra.transcript_topic_studio", revision_id,
            tampered["source"]["source_binding_sha256"],
        )
        reseal(tampered)
        with self.assertRaisesRegex(StudioError, "not present in authoritative registry"):
            validate_studio(tampered, registry=value)

    def test_resealed_topic_authority_tampering_still_fails_semantic_validation(self):
        studio, _, _, _, _, timeline_id = build_media_studio()
        studio, _ = register_topic_set(
            studio, native_id="detail", content_sha256="4" * 64,
            created_at="2026-09-11T00:03:00Z", timeline_id=timeline_id,
            level="DETAILED", topics=[topic(
                "d1", 0, 2, studio=studio, confidence=0.5
            )],
        )
        tampered = copy.deepcopy(studio)
        tampered["topic_sets"][0]["topics"][0]["semantic_status"] = "PROVISIONAL"
        reseal(tampered)
        with self.assertRaisesRegex(StudioError, "deterministic proposal"):
            validate_studio(tampered)

    def test_machine_topic_cannot_be_marked_accepted(self):
        studio, _, _, _, _, timeline_id = build_media_studio()
        studio, _ = register_topic_set(
            studio, native_id="detail", content_sha256="4" * 64,
            created_at="2026-09-11T00:03:00Z", timeline_id=timeline_id,
            level="DETAILED", topics=[topic("d1", 0, 2, studio=studio)],
        )
        self.assertEqual(studio["topic_sets"][0]["semantic_status"], "PROVISIONAL")
        self.assertNotIn("ACCEPTED", dumps_studio(studio).decode())


if __name__ == "__main__":
    unittest.main()
