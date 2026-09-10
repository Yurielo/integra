import copy
import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from integra_core.core_alpha import (
    CoreAlphaError,
    CoreAlphaPipeline,
    EXPECTED_REAL_COMPONENT_MODELS,
    ReplayStageWorker,
    STAGE_ORDER,
    StageOutput,
    validate_core_alpha_manifest,
)
from integra_core.identity import derive_imported_id
from integra_core.project_lease import LeaseStore


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/core_alpha_v1/worker_outputs.json"


class CoreAlphaTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "local-video.mp4"
        self.source.write_bytes(b"INTEGRA LOCAL VIDEO FIXTURE\x00\x01")
        self.store = self.root / "store"
        self.controller = {
            "component_id": "integra_control_plane",
            "repository": "Yurielo/integra",
            "commit_sha": "1" * 40,
            "tree_sha": "2" * 40,
            "version": "test",
            "contracts": ["worker_protocol_v1", "core_alpha_manifest_v1"],
            "runtime": {"kind": "python", "version": "test"},
        }
        self.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.worker = ReplayStageWorker(copy.deepcopy(self.fixture))
        self.pipeline = CoreAlphaPipeline(
            repository_root=ROOT,
            store_root=self.store,
            controller_identity=self.controller,
            worker=self.worker,
            writer_identity={
                "component_id": "integra_control_plane",
                "host_id": "test-host",
                "process_id": 100,
                "process_start_token": "test-process",
            },
            clock=lambda: datetime(2026, 9, 10, 17, 0, tzinfo=timezone.utc),
        )

    def tearDown(self):
        self.temporary.cleanup()

    def checkpoint(self, result):
        project = result["artifacts"]["source"]["relative_path"].split("/artifacts/")[0]
        return self.store / project / "checkpoint.json"

    def test_complete_vertical_slice_has_exact_lineage_and_pinned_components(self):
        result = self.pipeline.run(self.source)
        self.assertEqual(result["status"], "SUCCEEDED")
        self.assertEqual(result["completed_stages"], ["source", *STAGE_ORDER])
        self.assertEqual(result["semantic_authority"], "PROVISIONAL_ONLY")
        self.assertTrue(result["project_lease_enforced"])
        validate_core_alpha_manifest(result)
        self.assertEqual(result["artifacts"]["transcript"]["origin"]["component_id"], "videotext")
        self.assertEqual(result["artifacts"]["topics"]["origin"]["component_id"], "seminartext")
        self.assertEqual(result["artifacts"]["media_clip"]["origin"]["component_id"], "videotext")
        self.assertTrue(result["artifacts"]["media_clip"]["relative_path"].endswith(".bin"))
        expected_parents = [
            result["artifacts"][name]["artifact_id"]
            for name in ("transcript", "topics", "review")
        ]
        self.assertEqual(
            result["artifacts"]["knowledge"]["provenance"]["parent_artifact_ids"],
            expected_parents,
        )
        for artifact in result["artifacts"].values():
            self.assertTrue((self.store / artifact["relative_path"]).is_file())
            self.assertIn(
                artifact["semantic_status"],
                {"NOT_APPLICABLE", "PROVISIONAL", "REVIEW_REQUIRED"},
            )
        self.assertFalse(result["source_repositories_changed"])
        self.assertFalse(result["protected_data_accessed"])

    def test_repeated_run_is_deterministic(self):
        first = self.pipeline.run(self.source)
        second_worker = ReplayStageWorker(copy.deepcopy(self.fixture))
        second = CoreAlphaPipeline(
            repository_root=ROOT,
            store_root=self.store,
            controller_identity=self.controller,
            worker=second_worker,
        ).run(self.source)
        self.assertEqual(first, second)
        self.assertEqual(second_worker.calls, list(STAGE_ORDER))

    def test_cancel_and_resume_preserves_completed_artifacts(self):
        cancelled = self.pipeline.run(self.source, cancel_requested=lambda stage: stage == "topics")
        self.assertEqual(cancelled["status"], "CANCELLED")
        self.assertEqual(cancelled["next_stage"], "topics")
        self.assertEqual(self.worker.calls, ["transcript"])
        resumed_worker = ReplayStageWorker(copy.deepcopy(self.fixture))
        resumed = CoreAlphaPipeline(
            repository_root=ROOT,
            store_root=self.store,
            controller_identity=self.controller,
            worker=resumed_worker,
        ).run(self.source, resume_checkpoint=self.checkpoint(cancelled))
        self.assertEqual(resumed["status"], "SUCCEEDED")
        self.assertEqual(resumed_worker.calls, ["topics", "review", "knowledge", "media_clip"])

    def test_resume_rejects_changed_source(self):
        cancelled = self.pipeline.run(self.source, cancel_requested=lambda stage: stage == "topics")
        checkpoint = self.checkpoint(cancelled)
        self.source.write_bytes(b"changed")
        with self.assertRaisesRegex(CoreAlphaError, "source hash differs"):
            self.pipeline.run(self.source, resume_checkpoint=checkpoint)

    def test_resume_rejects_corrupted_retained_artifact(self):
        cancelled = self.pipeline.run(self.source, cancel_requested=lambda stage: stage == "topics")
        transcript = cancelled["artifacts"]["transcript"]
        (self.store / transcript["relative_path"]).write_bytes(b"corrupt")
        with self.assertRaisesRegex(CoreAlphaError, "artifact size changed"):
            self.pipeline.run(self.source, resume_checkpoint=self.checkpoint(cancelled))

    def test_semantic_acceptance_claim_fails_closed(self):
        fixture = copy.deepcopy(self.fixture)
        fixture["stages"]["knowledge"]["semantic_status"] = "ACCEPTED"
        pipeline = CoreAlphaPipeline(
            repository_root=ROOT,
            store_root=self.store,
            controller_identity=self.controller,
            worker=ReplayStageWorker(fixture),
        )
        with self.assertRaisesRegex(CoreAlphaError, "cannot assert semantic acceptance"):
            pipeline.run(self.source)

    def test_payload_lifecycle_cannot_contradict_provisional_authority(self):
        fixture = copy.deepcopy(self.fixture)
        fixture["stages"]["knowledge"]["payload"]["lifecycle"] = "ACCEPTED"
        pipeline = CoreAlphaPipeline(
            repository_root=ROOT,
            store_root=self.store,
            controller_identity=self.controller,
            worker=ReplayStageWorker(fixture),
        )
        with self.assertRaisesRegex(CoreAlphaError, "semantic acceptance"):
            pipeline.run(self.source)

    def test_review_payload_cannot_add_authoritative_decision(self):
        fixture = copy.deepcopy(self.fixture)
        fixture["stages"]["review"]["payload"]["authoritative_decision"] = (
            "ACCEPTED"
        )
        pipeline = CoreAlphaPipeline(
            repository_root=ROOT,
            store_root=self.store,
            controller_identity=self.controller,
            worker=ReplayStageWorker(fixture),
        )
        with self.assertRaisesRegex(CoreAlphaError, "result fields differ"):
            pipeline.run(self.source)

    def test_source_symlink_is_rejected(self):
        link = self.root / "linked-video.mp4"
        link.symlink_to(self.source)
        with self.assertRaisesRegex(CoreAlphaError, "not a symlink"):
            self.pipeline.run(link)

    def test_source_symlinked_ancestor_is_rejected(self):
        actual = self.root / "actual"
        actual.mkdir()
        source = actual / "video.mp4"
        source.write_bytes(b"video")
        alias = self.root / "alias"
        alias.symlink_to(actual, target_is_directory=True)
        with self.assertRaisesRegex(CoreAlphaError, "not a symlink"):
            self.pipeline.run(alias / "video.mp4")

    def test_symlinked_project_directory_cannot_escape_store(self):
        source_hash = hashlib.sha256(self.source.read_bytes()).hexdigest()
        project_id = derive_imported_id(
            "project", "integra", "core-alpha", source_hash
        )
        project_key = project_id.rsplit(":", 1)[-1]
        external = self.root / "external"
        external.mkdir()
        projects = self.store / "projects"
        projects.mkdir(parents=True)
        (projects / project_key).symlink_to(external, target_is_directory=True)
        with self.assertRaisesRegex(CoreAlphaError, "contains a symlink"):
            self.pipeline.run(self.source)
        self.assertEqual(list(external.iterdir()), [])

    def test_worker_output_contract_mismatch_fails_closed(self):
        base_worker = ReplayStageWorker(copy.deepcopy(self.fixture))

        class WrongContractWorker:
            def run(inner_self, stage, capability, component, inputs):
                output = base_worker.run(stage, capability, component, inputs)
                if stage == "topics":
                    return StageOutput(
                        payload=output.payload,
                        kind="media_clip",
                        schema_id="wrong_schema",
                        semantic_status=output.semantic_status,
                    )
                return output

        pipeline = CoreAlphaPipeline(
            repository_root=ROOT,
            store_root=self.store,
            controller_identity=self.controller,
            worker=WrongContractWorker(),
        )
        with self.assertRaisesRegex(CoreAlphaError, "output contract differs"):
            pipeline.run(self.source)

    def test_invalid_or_fabricated_stage_locator_fails_closed(self):
        for stage, locator in (
            ("topics", {"type": "time_interval", "start_seconds": 2, "end_seconds": 1}),
            ("knowledge", {"type": "fabricated", "value": "unknown"}),
            ("review", {"type": "time_interval", "start_seconds": 0, "end_seconds": 2}),
        ):
            with self.subTest(stage=stage):
                fixture = copy.deepcopy(self.fixture)
                fixture["stages"][stage]["source_locator"] = locator
                pipeline = CoreAlphaPipeline(
                    repository_root=ROOT,
                    store_root=self.store / stage,
                    controller_identity=self.controller,
                    worker=ReplayStageWorker(fixture),
                )
                with self.assertRaisesRegex(CoreAlphaError, "source locator|time interval"):
                    pipeline.run(self.source)

    def test_non_replay_worker_cannot_assert_semantic_acceptance(self):
        base_worker = ReplayStageWorker(copy.deepcopy(self.fixture))

        class AcceptedWorker:
            def run(inner_self, stage, capability, component, inputs):
                output = base_worker.run(stage, capability, component, inputs)
                if stage == "knowledge":
                    return StageOutput(
                        payload=output.payload,
                        kind=output.kind,
                        schema_id=output.schema_id,
                        semantic_status="ACCEPTED",
                    )
                return output

        pipeline = CoreAlphaPipeline(
            repository_root=ROOT,
            store_root=self.store,
            controller_identity=self.controller,
            worker=AcceptedWorker(),
        )
        with self.assertRaisesRegex(CoreAlphaError, "provisional authority"):
            pipeline.run(self.source)

    def test_manifest_rejects_tampered_stage_contract_and_provenance(self):
        result = self.pipeline.run(self.source)
        cases = []
        wrong_contract = copy.deepcopy(result)
        wrong_contract["artifacts"]["topics"]["kind"] = "media_clip"
        cases.append(wrong_contract)
        wrong_origin = copy.deepcopy(result)
        wrong_origin["artifacts"]["topics"]["origin"] = result[
            "component_identities"
        ]["videotext"]
        cases.append(wrong_origin)
        wrong_lineage = copy.deepcopy(result)
        wrong_lineage["artifacts"]["knowledge"]["provenance"][
            "parent_artifact_ids"
        ] = []
        cases.append(wrong_lineage)
        wrong_operation = copy.deepcopy(result)
        wrong_operation["artifacts"]["topics"]["provenance"]["operation_id"] = (
            wrong_operation["artifacts"]["source"]["provenance"]["operation_id"]
        )
        cases.append(wrong_operation)
        wrong_source_identity = copy.deepcopy(result)
        source_origin = copy.deepcopy(
            wrong_source_identity["artifacts"]["source"]["origin"]
        )
        source_origin["commit_sha"] = "f" * 40
        wrong_source_identity["artifacts"]["source"]["origin"] = source_origin
        cases.append(wrong_source_identity)
        wrong_selection = copy.deepcopy(result)
        wrong_selection["r5_selections"]["topics"]["semantic_superiority_claimed"] = True
        cases.append(wrong_selection)
        wrong_source_hash = copy.deepcopy(result)
        replacement_hash = "0" * 64
        source_reference = wrong_source_hash["artifacts"]["source"]
        source_reference["content_sha256"] = replacement_hash
        source_reference["artifact_id"] = derive_imported_id(
            "artifact", "integra_control_plane", "source", replacement_hash
        )
        source_reference["relative_path"] = source_reference["relative_path"].replace(
            result["source_sha256"], replacement_hash
        )
        source_reference["provenance"].pop("source_locator")
        cases.append(wrong_source_hash)
        for manifest in cases:
            with self.subTest(manifest=manifest):
                with self.assertRaises((CoreAlphaError, ValueError)):
                    validate_core_alpha_manifest(manifest)

    def test_manifest_rejects_coordinated_component_selection_and_project_tamper(self):
        result = self.pipeline.run(self.source)

        component_tamper = copy.deepcopy(result)
        component_tamper["component_identities"]["seminartext"]["commit_sha"] = (
            "f" * 40
        )
        for stage in ("topics", "review", "knowledge"):
            component_tamper["artifacts"][stage]["origin"]["commit_sha"] = "f" * 40

        selection_tamper = copy.deepcopy(result)
        selection_tamper["r5_selections"]["topics"]["basis"] = [
            "fabricated selection rationale"
        ]

        project_tamper = copy.deepcopy(result)
        other_project = derive_imported_id(
            "project", "integra", "core-alpha-tamper", result["source_sha256"]
        )
        old_key = result["project_id"].rsplit(":", 1)[-1]
        new_key = other_project.rsplit(":", 1)[-1]
        project_tamper["project_id"] = other_project
        for artifact in project_tamper["artifacts"].values():
            artifact["relative_path"] = artifact["relative_path"].replace(
                old_key, new_key, 1
            )

        for manifest in (component_tamper, selection_tamper, project_tamper):
            with self.subTest(manifest=manifest):
                with self.assertRaises(CoreAlphaError):
                    validate_core_alpha_manifest(manifest)

    def test_symlinked_store_ancestor_is_rejected(self):
        for relative in ("projects", ".leases"):
            with self.subTest(relative=relative):
                root = self.root / f"store-{relative.replace('.', 'dot')}"
                external = self.root / f"external-{relative.replace('.', 'dot')}"
                root.mkdir()
                external.mkdir()
                (root / relative).symlink_to(external, target_is_directory=True)
                with self.assertRaisesRegex(CoreAlphaError, "symlink"):
                    pipeline = CoreAlphaPipeline(
                        repository_root=ROOT,
                        store_root=root,
                        controller_identity=self.controller,
                        worker=ReplayStageWorker(copy.deepcopy(self.fixture)),
                    )
                    pipeline.run(self.source)

    def test_r5_selected_component_mismatch_fails_closed(self):
        fixture = copy.deepcopy(self.fixture)
        fixture["stages"]["topics"]["component_id"] = "videotext"
        pipeline = CoreAlphaPipeline(
            repository_root=ROOT,
            store_root=self.store,
            controller_identity=self.controller,
            worker=ReplayStageWorker(fixture),
        )
        with self.assertRaisesRegex(CoreAlphaError, "differs from R5 selection"):
            pipeline.run(self.source)

    def test_fixture_cannot_enable_protected_data_or_gold(self):
        for field in ("protected_data", "gold_labels"):
            with self.subTest(field=field):
                fixture = copy.deepcopy(self.fixture)
                fixture[field] = True
                with self.assertRaisesRegex(
                    CoreAlphaError, "deny protected data and Gold"
                ):
                    ReplayStageWorker(fixture)

    def test_invalid_media_payload_fails_as_core_alpha_error(self):
        fixture = copy.deepcopy(self.fixture)
        fixture["stages"]["media_clip"]["payload"] = "not base64!"
        pipeline = CoreAlphaPipeline(
            repository_root=ROOT,
            store_root=self.store,
            controller_identity=self.controller,
            worker=ReplayStageWorker(fixture),
        )
        with self.assertRaisesRegex(CoreAlphaError, "invalid base64 payload"):
            pipeline.run(self.source)

    def test_store_inside_repository_is_rejected(self):
        with self.assertRaisesRegex(CoreAlphaError, "outside the repository"):
            CoreAlphaPipeline(
                repository_root=ROOT,
                store_root=ROOT / "unsafe-store",
                controller_identity=self.controller,
                worker=ReplayStageWorker(copy.deepcopy(self.fixture)),
            )

    def test_non_video_extension_is_rejected(self):
        source = self.root / "not-video.txt"
        source.write_bytes(b"content")
        with self.assertRaisesRegex(CoreAlphaError, "local-video extension"):
            self.pipeline.run(source)

    def test_real_media_pipeline_requires_exact_model_identities(self):
        models = copy.deepcopy(EXPECTED_REAL_COMPONENT_MODELS)
        models["seminartext"][0]["identity_sha256"] = "0" * 64
        with self.assertRaisesRegex(CoreAlphaError, "exact component model pins"):
            CoreAlphaPipeline(
                repository_root=ROOT,
                store_root=self.root / "actual-store",
                controller_identity=self.controller,
                worker=ReplayStageWorker(copy.deepcopy(self.fixture)),
                execution_mode="PINNED_REAL_MEDIA",
                component_models=models,
            )

    def test_real_review_is_bound_to_transcript_topic_and_model_parents(self):
        source_hash = "a" * 64
        text_hash = hashlib.sha256(b"text").hexdigest()
        transcript = {
            "result": {"text_sha256": text_hash},
            "stage_data": {"transcript_text": "text"},
        }
        topics = {
            "stage_data": {"topics_document": {
                "model": "gemma3:4b",
                "topics": [{"title": "title", "summary": "summary", "semantic_status": "REVIEW_REQUIRED"}],
            }}
        }
        review = {
            "stage_data": {
                "canonical_bundle": {
                    "sources": [{"content_sha256": source_hash}],
                    "transcript_revisions": [{"id": "revision", "canonical_text": "text", "text_sha256": text_hash}],
                    "alignment_runs": [{
                        "model": "ggml-large-v3.bin",
                        "model_sha256": EXPECTED_REAL_COMPONENT_MODELS["videotext"][0]["identity_sha256"],
                        "source_content_sha256": source_hash,
                        "transcript_text_sha256": text_hash,
                        "transcript_revision_id": "revision",
                    }],
                },
                "draft_input_document": {
                    "topics": [{"proposed_title": "title", "proposed_summary": "summary", "lifecycle_status": "REVIEW_REQUIRED"}]
                },
            }
        }
        CoreAlphaPipeline._validate_review_upstream(review, transcript, topics, source_hash)
        for path, value in (
            (("canonical_bundle", "transcript_revisions", 0, "canonical_text"), "changed"),
            (("canonical_bundle", "alignment_runs", 0, "model_sha256"), "0" * 64),
            (("draft_input_document", "topics", 0, "proposed_title"), "changed"),
        ):
            mutated = copy.deepcopy(review)
            target = mutated["stage_data"]
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
            with self.subTest(path=path):
                with self.assertRaises(CoreAlphaError):
                    CoreAlphaPipeline._validate_review_upstream(
                        mutated, transcript, topics, source_hash
                    )

    def test_real_knowledge_is_bound_to_review_semantics(self):
        review_topic = {
            "id": "topic",
            "proposed_title": "title",
            "proposed_summary": "summary",
            "sequence": 0,
            "seminar_id": "seminar",
            "source_id": "source",
            "topic_set_id": "set",
            "transcript_revision_id": "revision",
            "word_start_id": "word-0",
            "word_end_id": "word-1",
            "word_start_sequence": 0,
            "word_end_sequence": 1,
            "evidence_refs": ["evidence"],
        }
        evidence = {
            "id": "evidence",
            "locator": {"type": "time_interval", "start_seconds": 0.1, "end_seconds": 0.9},
            "source_id": "source",
            "transcript_revision_id": "revision",
            "word_start_id": "word-0",
        }
        bundle = {
            "artifact_id": "upstream",
            "project": {"id": "project", "title": "Project"},
            "words": [
                {"id": "word-0", "start_seconds": 0.1},
                {"id": "word-1", "end_seconds": 0.9},
            ],
            "benchmark_segments": [{
                "id": "segment",
                "transcript_revision_id": "revision",
                "word_start_id": "word-0",
                "word_end_id": "word-1",
            }],
            "topics": [],
            "evidence_refs": [],
        }
        generated_topic = {
            "benchmark_segment_ids": ["segment"],
            "id": "topic",
            "lifecycle_status": "active",
            "origin": "semi_automatic",
            "sequence": 0,
            "title": "title",
            "topic_set_id": "set",
            "transcript_revision_id": "revision",
            "word_end_id": "word-1",
            "word_start_id": "word-0",
        }
        generated_evidence = {
            "id": "evidence",
            "lifecycle_status": "verified",
            "locator": evidence["locator"],
            "project_id": "project",
            "source_id": "source",
            "target": {"entity_id": "word-0", "entity_type": "word"},
            "transcript_revision_id": "revision",
        }
        knowledge_topic = {
            "concept_refs": [],
            "evidence_refs": ["evidence"],
            "id": "topic",
            "order_scope": {"sequence": 0},
            "seminar_id": "seminar",
            "source_scope": {
                "source_ids": ["source"],
                "transcript_revision_ids": ["revision"],
                "order_start": 0,
                "order_end": 1,
            },
            "status": "PROVISIONAL",
            "summary": "summary",
            "temporal_scope": {"start_seconds": 0.1, "end_seconds": 0.9},
            "title": "title",
        }
        review = {
            "stage_data": {
                "canonical_bundle": bundle,
                "review_package": {"topics": [review_topic], "evidence": [evidence]},
            }
        }
        document = {
            "stage_data": {
                "canonical_evidence_document": {
                    **{key: value for key, value in bundle.items() if key not in {"artifact_id", "topics", "evidence_refs"}},
                    "artifact_id": "generated",
                    "topics": [generated_topic],
                    "evidence_refs": [generated_evidence],
                },
                "canonical_knowledge_document": {
                    "artifact_type": "seminartext.canonical_knowledge",
                    "schema_version": "1.0.0",
                    "concepts": [],
                    "relations": [],
                    "review_decisions": [],
                    "topics": [knowledge_topic],
                },
            }
        }
        CoreAlphaPipeline._validate_knowledge_upstream(document, review)
        document["stage_data"]["canonical_evidence_document"]["topics"][0]["title"] = "fabricated"
        with self.assertRaisesRegex(CoreAlphaError, "Topic differs"):
            CoreAlphaPipeline._validate_knowledge_upstream(document, review)

    def test_resume_rejects_changed_lineage(self):
        cancelled = self.pipeline.run(
            self.source, cancel_requested=lambda stage: stage == "topics"
        )
        checkpoint = self.checkpoint(cancelled)
        content = json.loads(checkpoint.read_text(encoding="utf-8"))
        content["artifacts"]["transcript"]["provenance"]["parent_artifact_ids"] = []
        checkpoint.write_text(json.dumps(content), encoding="utf-8")
        with self.assertRaisesRegex(CoreAlphaError, "lineage changed"):
            self.pipeline.run(self.source, resume_checkpoint=checkpoint)

    def test_resume_rejects_changed_origin(self):
        cancelled = self.pipeline.run(
            self.source, cancel_requested=lambda stage: stage == "topics"
        )
        checkpoint = self.checkpoint(cancelled)
        content = json.loads(checkpoint.read_text(encoding="utf-8"))
        content["artifacts"]["transcript"]["origin"] = content[
            "component_identities"
        ]["seminartext"]
        checkpoint.write_text(json.dumps(content), encoding="utf-8")
        with self.assertRaisesRegex(CoreAlphaError, "origin changed"):
            self.pipeline.run(self.source, resume_checkpoint=checkpoint)

    def test_concurrent_writer_is_blocked_by_project_lease(self):
        source_hash = hashlib.sha256(self.source.read_bytes()).hexdigest()
        project_id = derive_imported_id(
            "project", "integra", "core-alpha", source_hash
        )
        lease_store = LeaseStore(self.store / ".leases")
        lease_store.acquire(
            {
                "schema_version": "1.0",
                "lease_id": derive_imported_id(
                    "lease", "other", "core-alpha", source_hash
                ),
                "project_id": project_id,
                "mutable_entity": {
                    "namespace": "project",
                    "entity_id": project_id,
                },
                "writer": {
                    "component_id": "other",
                    "host_id": "test-host",
                    "process_id": 200,
                    "process_start_token": "other-process",
                },
                "operation_id": derive_imported_id(
                    "operation", "other", "core-alpha", source_hash
                ),
                "acquired_at": "2026-09-10T17:00:00Z",
                "heartbeat_at": "2026-09-10T17:00:00Z",
                "expires_at": "2026-09-10T17:05:00Z",
                "artifact_precondition": {
                    "revision_id": source_hash,
                    "content_sha256": source_hash,
                },
                "readers": [],
            }
        )
        pipeline = CoreAlphaPipeline(
            repository_root=ROOT,
            store_root=self.store,
            controller_identity=self.controller,
            worker=ReplayStageWorker(copy.deepcopy(self.fixture)),
            lease_store=lease_store,
            writer_identity={
                "component_id": "integra_control_plane",
                "host_id": "test-host",
                "process_id": 100,
                "process_start_token": "test-process",
            },
            clock=lambda: datetime(2026, 9, 10, 17, 1, tzinfo=timezone.utc),
        )
        with self.assertRaisesRegex(CoreAlphaError, "project lease conflict"):
            pipeline.run(self.source)

    def test_worker_can_refresh_project_lease_during_each_stage(self):
        delegate = ReplayStageWorker(copy.deepcopy(self.fixture))

        class HeartbeatWorker:
            def __init__(inner_self):
                inner_self.callback = None
                inner_self.refreshes = 0

            def set_lease_heartbeat(inner_self, callback):
                inner_self.callback = callback

            def run(inner_self, stage, capability, component, inputs):
                self.assertIsNotNone(inner_self.callback)
                inner_self.callback()
                inner_self.refreshes += 1
                return delegate.run(stage, capability, component, inputs)

        worker = HeartbeatWorker()
        pipeline = CoreAlphaPipeline(
            repository_root=ROOT,
            store_root=self.store,
            controller_identity=self.controller,
            worker=worker,
            writer_identity={
                "component_id": "integra_control_plane",
                "host_id": "test-host",
                "process_id": 100,
                "process_start_token": "test-process",
            },
            clock=lambda: datetime(2026, 9, 10, 17, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(pipeline.run(self.source)["status"], "SUCCEEDED")
        self.assertEqual(worker.refreshes, len(STAGE_ORDER))
        self.assertIsNone(worker.callback)


if __name__ == "__main__":
    unittest.main()
