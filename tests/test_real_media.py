from __future__ import annotations

import importlib.util
import copy
import hashlib
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from integra_core.real_media import (
    JsonlProcessStageWorker,
    RealMediaError,
    aggregate_whisper_words,
    certify_deterministic_runs,
    determinism_run_record,
    validate_actual_evidence,
)
from integra_core.real_contracts import (
    RealStageContractError,
    validate_mp4_clip,
    validate_real_stage_document,
)


ROOT = Path(__file__).resolve().parents[1]


class RealMediaTests(unittest.TestCase):
    @staticmethod
    def stage_document(stage, result, stage_data, *, parents=1):
        return {
            "input_artifact_ids": [f"artifact-{index}" for index in range(parents)],
            "input_content_sha256": [str(index) * 64 for index in range(parents)],
            "result": result,
            "schema_version": "1.0",
            "semantic_status": "PROVISIONAL" if stage == "knowledge" else "REVIEW_REQUIRED",
            "stage": stage,
            "stage_data": stage_data,
        }

    @staticmethod
    def machine_provenance():
        return {
            "method": "machine",
            "origin": "machine_generated",
            "reviewer": None,
            "verification_ranges": [],
            "verification_state": "machine_unverified",
        }

    @classmethod
    def _valid_knowledge_document(cls):
        content = "# knowledge\n"
        canonical_evidence = {"artifact_id": "evidence", "topics": [], "evidence_refs": []}
        canonical_evidence_hash = hashlib.sha256(
            (json.dumps(canonical_evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
        ).hexdigest()
        canonical_knowledge = {
            "artifact_id": "knowledge",
            "canonical_evidence": {
                "artifact_id": "evidence",
                "sha256": canonical_evidence_hash,
            },
        }
        canonical_knowledge_hash = hashlib.sha256(
            (json.dumps(canonical_knowledge, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
        ).hexdigest()
        coverage = {
            "artifact_type": "seminartext.project_knowledge_coverage",
            "full_seminar_coverage": True,
            "project_id": "project",
            "schema_version": 1,
            "sources": [{
                "evidence_ids": ["evidence"],
                "reason": "covered",
                "source_id": "source",
                "status": "COVERED",
                "topic_ids": ["topic"],
                "transcript_revision_ids": ["revision"],
                "word_count": 1,
            }],
        }
        manifest = {
            "artifact_type": "seminartext.managed_generated_export",
            "canonical_evidence_artifact_id": "evidence",
            "canonical_evidence_sha256": canonical_evidence_hash,
            "canonical_knowledge_artifact_id": "knowledge",
            "canonical_knowledge_sha256": canonical_knowledge_hash,
            "coverage": coverage,
            "files": {"Topics/topic.md": hashlib.sha256(content.encode()).hexdigest()},
            "kind": "obsidian_derived_view",
            "ownership_classes": ["MANAGED_GENERATED", "USER_OWNED"],
            "resolver_states": {"source": "RESOLVER_UNAVAILABLE"},
            "schema_version": 1,
        }
        manifest_text = json.dumps(manifest, sort_keys=True)
        return cls.stage_document(
            "knowledge",
            {"lifecycle": "PROVISIONAL", "manifest_sha256": hashlib.sha256(manifest_text.encode()).hexdigest()},
            {
                "canonical_evidence_document": canonical_evidence,
                "canonical_knowledge_document": canonical_knowledge,
                "coverage_document": coverage,
                "export_files": {"Topics/topic.md": content},
                "export_manifest": manifest,
                "export_manifest_text": manifest_text,
            },
            parents=3,
        )

    @classmethod
    def _valid_review_document(cls):
        text = "слово"
        text_hash = hashlib.sha256(text.encode()).hexdigest()
        provenance = cls.machine_provenance()
        source_hash = "a" * 64
        revision_id = "revision"
        word_id = "word"
        run_id = "alignment"
        cue_id = "cue"
        word = {
            "alignment_status": "aligned",
            "char_end": len(text),
            "char_start": 0,
            "confidence": 0.9,
            "end_seconds": 0.9,
            "id": word_id,
            "lifecycle_status": "active",
            "normalized_text": None,
            "qa_flags": [],
            "sequence": 0,
            "source_cue_ids": [cue_id],
            "source_id": "source",
            "speaker_id": None,
            "start_seconds": 0.1,
            "text": text,
            "timing_provenance": {
                "alignment_run_id": run_id,
                "kind": "forced_alignment",
                "method": "native_word_intervals",
            },
            "transcript_revision_id": revision_id,
        }
        bundle = {
            "alignment_runs": [{
                "aligner": "aligner",
                "aligner_version": "1",
                "config_sha256": "b" * 64,
                "id": run_id,
                "model": "model",
                "model_revision": "revision",
                "model_sha256": "c" * 64,
                "source_content_sha256": source_hash,
                "source_id": "source",
                "status": "valid",
                "transcript_revision_id": revision_id,
                "transcript_text_sha256": text_hash,
            }],
            "artifact_id": "bundle",
            "artifact_type": "seminartext.canonical_evidence",
            "benchmark_segments": [{
                "id": "segment",
                "lifecycle_status": "active",
                "sequence": 0,
                "transcript_revision_id": revision_id,
                "word_count": 1,
                "word_end_id": word_id,
                "word_start_id": word_id,
            }],
            "cues": [{
                "char_end": len(text),
                "char_start": 0,
                "id": cue_id,
                "lifecycle_status": "active",
                "sequence": 0,
                "source_locator": {"type": "time_interval", "start_seconds": 0.1, "end_seconds": 0.9},
                "text": text,
                "transcript_revision_id": revision_id,
            }],
            "evidence_refs": [],
            "project": {"id": "project", "lifecycle_status": "active", "title": "Project"},
            "schema_version": "1.0.0",
            "sources": [{
                "content_sha256": source_hash,
                "duration_seconds": 1.0,
                "id": "source",
                "kind": "video",
                "lifecycle_status": "active",
                "project_id": "project",
                "sequence": 0,
                "title": "Source",
            }],
            "topics": [],
            "transcript_revisions": [{
                "authority": "candidate",
                "canonical_text": text,
                "id": revision_id,
                "lifecycle_status": "active",
                "parent_revision_id": None,
                "revision_kind": "asr",
                "revision_number": 1,
                "source_id": "source",
                "text_sha256": text_hash,
                "transcript_provenance": provenance,
            }],
            "words": [word],
        }
        evidence = {
            "claim": "claim",
            "id": "evidence",
            "locator": {"type": "time_interval", "start_seconds": 0.1, "end_seconds": 0.9},
            "quote": text,
            "source_id": "source",
            "transcript_provenance": provenance,
            "transcript_revision_id": revision_id,
            "word_end_id": word_id,
            "word_end_sequence": 0,
            "word_start_id": word_id,
            "word_start_sequence": 0,
        }
        topic = {
            "evidence_refs": ["evidence"],
            "evidence_sha256": hashlib.sha256(cls._canonical_bytes([evidence])).hexdigest(),
            "generator": {"configuration_sha256": "d" * 64, "id": "generator", "version": "1"},
            "id": "topic",
            "lifecycle_status": "REVIEW_REQUIRED",
            "locator": {"type": "time_interval", "start_seconds": 0.1, "end_seconds": 0.9},
            "proposed_summary": "summary",
            "proposed_title": "title",
            "quote": text,
            "review_history": [],
            "semantic_origin": "machine_assisted",
            "seminar_id": "seminar",
            "sequence": 0,
            "source_id": "source",
            "topic_set_id": "set",
            "transcript_provenance": provenance,
            "transcript_revision_id": revision_id,
            "word_end_id": word_id,
            "word_end_sequence": 0,
            "word_start_id": word_id,
            "word_start_sequence": 0,
        }
        topic["topic_sha256"] = hashlib.sha256(cls._canonical_bytes(topic)).hexdigest()
        draft = {"artifact_id": "draft"}
        package = {
            "artifact_id": "review",
            "artifact_type": "seminartext.topic_review_package",
            "canonical_evidence": {
                "artifact_id": "bundle",
                "sha256": hashlib.sha256(cls._canonical_bytes(bundle)).hexdigest(),
            },
            "draft_input": {
                "artifact_id": "draft",
                "sha256": hashlib.sha256(cls._canonical_bytes(draft)).hexdigest(),
            },
            "evidence": [evidence],
            "project": {"id": "project", "title": "Project"},
            "review_policy": {"authoring_gate": "DOMAIN_AUTHORING", "automatic_acceptance": False, "machine_assisted_default": "REVIEW_REQUIRED", "review_gate": "DOMAIN_REVIEW"},
            "schema_version": "1.0.0",
            "seminar": {"id": "seminar", "title": "Seminar"},
            "topics": [topic],
        }
        return cls.stage_document(
            "review",
            {"human_decision_required": True, "technical_status": "REVIEW_REQUIRED", "unreviewed": 1},
            {
                "alignment_result": {"alignment_run_id": run_id, "bundle": "evidence/canonical_bundle.json", "status": "review_required", "unaligned_words": []},
                "canonical_bundle": bundle,
                "draft_input_document": draft,
                "review_package": package,
            },
            parents=2,
        )

    @staticmethod
    def _canonical_bytes(value):
        return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()

    def test_whisper_subwords_are_aggregated_without_fabricating_zero_duration(self) -> None:
        document = {
            "transcription": [
                {
                    "tokens": [
                        {"text": "[_BEG_]", "offsets": {"from": 0, "to": 0}},
                        {"text": " Провер", "offsets": {"from": 100, "to": 300}, "p": 0.8},
                        {"text": "ка", "offsets": {"from": 300, "to": 500}, "p": 1.0},
                        {"text": " ноль", "offsets": {"from": 600, "to": 600}, "p": 0.7},
                        {"text": " готова", "offsets": {"from": 700, "to": 900}, "p": 0.9},
                    ]
                }
            ]
        }
        words, omitted = aggregate_whisper_words(document)
        self.assertEqual([item["word"] for item in words], ["Проверка", "готова"])
        self.assertEqual(words[0]["start"], 0.1)
        self.assertEqual(words[0]["end"], 0.5)
        self.assertEqual(words[0]["score"], 0.9)
        self.assertEqual(omitted[0]["word"], "ноль")
        self.assertEqual(omitted[0]["reason"], "WHISPER_ZERO_DURATION_TOKEN")

    def test_failed_lease_heartbeat_kills_and_reaps_worker(self) -> None:
        worker = JsonlProcessStageWorker.__new__(JsonlProcessStageWorker)
        worker._lease_heartbeat = mock.Mock(side_effect=RuntimeError("lease lost"))
        worker.lease_heartbeats = 0
        process = SimpleNamespace(pid=321, communicate=mock.Mock(return_value=(b"", b"")))
        with mock.patch("integra_core.real_media.os.killpg") as killpg:
            with self.assertRaisesRegex(RuntimeError, "lease lost"):
                worker._refresh_active_lease(process, "topics")
        killpg.assert_called_once_with(321, 9)
        process.communicate.assert_called_once_with()
        self.assertEqual(worker.lease_heartbeats, 0)

    def test_actual_evidence_requires_provisional_semantic_authority(self) -> None:
        document = json.loads((ROOT / "state/core_alpha_real_v1.json").read_text(encoding="utf-8"))
        self.assertEqual(validate_actual_evidence(document), [])
        document["human_decisions_applied"] = 1
        document["stages"]["topics"]["semantic_status"] = "ACCEPTED"
        errors = validate_actual_evidence(document)
        self.assertTrue(any("human_decisions" in item or "human decisions" in item for item in errors))
        self.assertTrue(any("topics" in item for item in errors))

    def test_actual_evidence_rejects_unknown_fields_and_tampered_identity(self) -> None:
        base = json.loads((ROOT / "state/core_alpha_real_v1.json").read_text(encoding="utf-8"))
        cases = []
        extra = copy.deepcopy(base)
        extra["unexpected"] = True
        cases.append(extra)
        stage = copy.deepcopy(base)
        stage["stages"]["topics"]["sha256"] = "0" * 63
        cases.append(stage)
        model = copy.deepcopy(base)
        model["models"]["topics"].pop("digest")
        cases.append(model)
        lineage = copy.deepcopy(base)
        lineage["provenance"]["artifact_lineage"]["topics"]["parent_artifact_ids"] = [1]
        cases.append(lineage)
        for document in cases:
            with self.subTest(document=document):
                self.assertTrue(validate_actual_evidence(document))

    def test_topic_adapter_invokes_pinned_engine_functions(self) -> None:
        path = ROOT / "workers/seminartext_topics_worker.py"
        spec = importlib.util.spec_from_file_location("topic_worker", path)
        assert spec and spec.loader
        worker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(worker)
        items = [
            {"id": 1, "start": "00:00:00,000", "end": "00:00:01,000", "text": "Один"},
            {"id": 2, "start": "00:00:01,000", "end": "00:00:02,000", "text": "Два"},
        ]
        fake = SimpleNamespace(
            parse_srt=lambda _: items,
            make_windows=lambda value: [value],
            analyze_window_boundaries=lambda *_args, **_kwargs: [1],
            topic_range_prompt=lambda value: value,
            run_ollama_topic_label=lambda _model, _prompt, start, end: {
                "start_id": start,
                "evidence_start_id": start,
                "evidence_end_id": end,
                "title": "Черновик",
                "summary": "Требует проверки",
                "qa_status": "ok",
                "qa_attempt": "test",
            },
            make_topics=lambda _items, rows: [{"title": rows[0]["title"]}],
        )
        result = worker.run_topics(fake, Path("unused.srt"), "local-model")
        self.assertEqual(result["topics"][0]["semantic_status"], "REVIEW_REQUIRED")
        self.assertEqual(result["component"], "seminartext")

    def test_transcript_contract_rejects_empty_nested_word(self) -> None:
        text = "слово"
        document = self.stage_document(
            "transcript",
            {
                "assurance": "MACHINE_UNVERIFIED",
                "language": "ru",
                "model_sha256": "a" * 64,
                "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                "word_count": 1,
            },
            {
                "review_checkpoint": "SOURCE_TRANSCRIPT",
                "srt_text": "1\n00:00:00,000 --> 00:00:01,000\nслово\n",
                "transcript_text": text,
                "whisper_document": {
                    "result": {"language": "ru"},
                    "transcription": [{"text": text}],
                },
                "word_intervals": [{}],
                "omitted_zero_duration_tokens": [],
            },
        )
        with self.assertRaisesRegex(RealStageContractError, "word 0 fields"):
            validate_real_stage_document("transcript", document)

    def test_topics_contract_rejects_missing_start_seconds(self) -> None:
        topic = {
            "end": "00:00:01,000",
            "end_seconds": 1.0,
            "evidence_end_id": 1,
            "evidence_start_id": 1,
            "number": 1,
            "qa_attempt": "first",
            "qa_status": "ok",
            "semantic_status": "REVIEW_REQUIRED",
            "start": "00:00:00,000",
            "start_segment_id": 1,
            "summary": "summary",
            "title": "title",
        }
        row = {
            "evidence_end_id": 1,
            "evidence_start_id": 1,
            "qa_attempt": "first",
            "qa_status": "ok",
            "semantic_status": "REVIEW_REQUIRED",
            "start_id": 1,
            "summary": "summary",
            "title": "title",
        }
        document = self.stage_document(
            "topics",
            {
                "model_digest": "a" * 64,
                "model_weights_sha256": "b" * 64,
                "topic_count": 1,
            },
            {
                "topics_document": {
                    "component": "seminartext",
                    "component_entrypoint": "engine",
                    "model": "model",
                    "schema_version": "1.0",
                    "topics": [topic],
                    "windows": [{"boundaries": [], "rows": [row], "window": 1}],
                }
            },
        )
        with self.assertRaisesRegex(RealStageContractError, "topic 0 fields"):
            validate_real_stage_document("topics", document)

    def test_review_contract_rejects_empty_canonical_word(self) -> None:
        text = "слово"
        provenance = self.machine_provenance()
        bundle = {
            "alignment_runs": [{"id": "alignment"}],
            "artifact_id": "bundle",
            "artifact_type": "seminartext.canonical_evidence",
            "benchmark_segments": [{"id": "segment"}],
            "cues": [{"id": "cue"}],
            "evidence_refs": [],
            "project": {"id": "project", "lifecycle_status": "active", "title": "Project"},
            "schema_version": "1.0.0",
            "sources": [{
                "content_sha256": "a" * 64,
                "duration_seconds": 1.0,
                "id": "source",
                "kind": "video",
                "lifecycle_status": "active",
                "project_id": "project",
                "sequence": 0,
                "title": "Source",
            }],
            "topics": [],
            "transcript_revisions": [{
                "authority": "candidate",
                "canonical_text": text,
                "id": "revision",
                "lifecycle_status": "active",
                "parent_revision_id": None,
                "revision_kind": "asr",
                "revision_number": 1,
                "source_id": "source",
                "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                "transcript_provenance": provenance,
            }],
            "words": [{}],
        }
        evidence = {
            "claim": "claim",
            "id": "evidence",
            "locator": {"type": "time_interval", "start_seconds": 0.1, "end_seconds": 0.9},
            "quote": text,
            "source_id": "source",
            "transcript_provenance": provenance,
            "transcript_revision_id": "revision",
            "word_end_id": "word",
            "word_end_sequence": 0,
            "word_start_id": "word",
            "word_start_sequence": 0,
        }
        topic = {
            "evidence_refs": ["evidence"],
            "evidence_sha256": "b" * 64,
            "generator": {"configuration_sha256": "c" * 64, "id": "generator", "version": "1"},
            "id": "topic",
            "lifecycle_status": "REVIEW_REQUIRED",
            "locator": {"type": "time_interval", "start_seconds": 0.1, "end_seconds": 0.9},
            "proposed_summary": "summary",
            "proposed_title": "title",
            "quote": text,
            "review_history": [],
            "semantic_origin": "machine_assisted",
            "seminar_id": "seminar",
            "sequence": 0,
            "source_id": "source",
            "topic_set_id": "set",
            "topic_sha256": "d" * 64,
            "transcript_provenance": provenance,
            "transcript_revision_id": "revision",
            "word_end_id": "word",
            "word_end_sequence": 0,
            "word_start_id": "word",
            "word_start_sequence": 0,
        }
        document = self.stage_document(
            "review",
            {"human_decision_required": True, "technical_status": "REVIEW_REQUIRED", "unreviewed": 1},
            {
                "alignment_result": {"alignment_run_id": "alignment", "bundle": "evidence/canonical_bundle.json", "status": "review_required", "unaligned_words": []},
                "canonical_bundle": bundle,
                "draft_input_document": {"artifact_id": "draft"},
                "review_package": {
                    "artifact_id": "review",
                    "artifact_type": "seminartext.topic_review_package",
                    "canonical_evidence": {"artifact_id": "bundle", "sha256": "e" * 64},
                    "draft_input": {"artifact_id": "draft", "sha256": "f" * 64},
                    "evidence": [evidence],
                    "project": {"id": "project", "title": "Project"},
                    "review_policy": {"authoring_gate": "DOMAIN_AUTHORING", "automatic_acceptance": False, "machine_assisted_default": "REVIEW_REQUIRED", "review_gate": "DOMAIN_REVIEW"},
                    "schema_version": "1.0.0",
                    "seminar": {"id": "seminar", "title": "Seminar"},
                    "topics": [topic],
                },
            },
            parents=2,
        )
        with self.assertRaisesRegex(RealStageContractError, "canonical word 0 fields"):
            validate_real_stage_document("review", document)

    def test_review_contract_binds_integrity_hashes(self) -> None:
        document = self._valid_review_document()
        validate_real_stage_document("review", document)
        for field in ("evidence_sha256", "topic_sha256"):
            mutated = copy.deepcopy(document)
            mutated["stage_data"]["review_package"]["topics"][0][field] = "0" * 64
            with self.subTest(field=field):
                with self.assertRaisesRegex(RealStageContractError, "hash differs"):
                    validate_real_stage_document("review", mutated)

    def test_review_contract_rejects_broken_canonical_references(self) -> None:
        for mutate, expected in (
            (
                lambda value: value["stage_data"]["canonical_bundle"]["words"][0].__setitem__("source_cue_ids", ["missing"]),
                "source cue is unknown",
            ),
            (
                lambda value: value["stage_data"]["canonical_bundle"]["cues"][0].__setitem__("transcript_revision_id", "missing"),
                "transcript revision is unknown",
            ),
            (
                lambda value: value["stage_data"]["alignment_result"].__setitem__("unaligned_words", [999]),
                "unaligned words differ",
            ),
        ):
            document = self._valid_review_document()
            mutate(document)
            bundle = document["stage_data"]["canonical_bundle"]
            document["stage_data"]["review_package"]["canonical_evidence"]["sha256"] = hashlib.sha256(
                self._canonical_bytes(bundle)
            ).hexdigest()
            with self.subTest(expected=expected):
                with self.assertRaisesRegex(RealStageContractError, expected):
                    validate_real_stage_document("review", document)

    def test_knowledge_contract_binds_all_export_bytes(self) -> None:
        document = self._valid_knowledge_document()
        validate_real_stage_document("knowledge", document)
        document["stage_data"]["export_files"]["Topics/topic.md"] = "tampered"
        with self.assertRaisesRegex(RealStageContractError, "export bytes differ"):
            validate_real_stage_document("knowledge", document)

    def test_knowledge_contract_rejects_unsafe_export_path(self) -> None:
        document = json.loads(json.dumps(self._valid_knowledge_document()))
        content = document["stage_data"]["export_files"].pop("Topics/topic.md")
        digest = document["stage_data"]["export_manifest"]["files"].pop("Topics/topic.md")
        document["stage_data"]["export_files"]["../topic.md"] = content
        document["stage_data"]["export_manifest"]["files"]["../topic.md"] = digest
        manifest = document["stage_data"]["export_manifest"]
        manifest_text = json.dumps(manifest, sort_keys=True)
        document["stage_data"]["export_manifest_text"] = manifest_text
        document["result"]["manifest_sha256"] = hashlib.sha256(manifest_text.encode()).hexdigest()
        with self.assertRaisesRegex(RealStageContractError, "export path is unsafe"):
            validate_real_stage_document("knowledge", document)

    def test_media_contract_rejects_arbitrary_nonempty_bytes(self) -> None:
        with self.assertRaises(RealStageContractError):
            validate_mp4_clip(b"not an mp4, but previously accepted")

    def test_media_contract_accepts_complete_iso_bmff_box_inventory(self) -> None:
        def box(kind: bytes, payload: bytes) -> bytes:
            return (8 + len(payload)).to_bytes(4, "big") + kind + payload

        validate_mp4_clip(
            box(b"ftyp", b"isom\x00\x00\x02\x00")
            + box(b"moov", b"metadata")
            + box(b"mdat", b"sample")
        )

    def test_determinism_certification_retains_two_run_identities(self) -> None:
        first = json.loads((ROOT / "state/core_alpha_real_v1.json").read_text())
        first["determinism"] = {
            "independent_runs_compared": 1,
            "all_stage_hashes_identical": None,
            "runs": [],
        }
        first["determinism"]["runs"] = [determinism_run_record(first)]
        second = copy.deepcopy(first)
        second["executed_at"] = "2026-09-10T23:59:59Z"
        second["control_plane"]["lease_heartbeats_during_workers"] += 1
        second["determinism"]["runs"] = [determinism_run_record(second)]
        certified = certify_deterministic_runs(first, second)
        self.assertEqual(certified["determinism"]["independent_runs_compared"], 2)
        self.assertTrue(certified["determinism"]["all_stage_hashes_identical"])
        self.assertEqual(len({item["run_id"] for item in certified["determinism"]["runs"]}), 2)

        second["stages"]["topics"]["sha256"] = "0" * 64
        second["determinism"]["runs"] = [determinism_run_record(second)]
        with self.assertRaisesRegex(RealMediaError, "independent run evidence differs"):
            certify_deterministic_runs(first, second)


if __name__ == "__main__":
    unittest.main()
