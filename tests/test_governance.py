import copy
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "validate_governance.py"
SPEC = importlib.util.spec_from_file_location("validate_governance", MODULE_PATH)
VALIDATOR = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(VALIDATOR)


class GovernanceValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.state = json.loads(
            (ROOT / "state" / "integra_state_v1.json").read_text(encoding="utf-8")
        )
        cls.baselines = json.loads(
            (ROOT / "state" / "component_baselines_v1.json").read_text(encoding="utf-8")
        )
        cls.ownership = json.loads(
            (ROOT / "state" / "data_ownership_v1.json").read_text(encoding="utf-8")
        )
        cls.worker_protocol = json.loads(
            (ROOT / "state" / "worker_protocol_v1.json").read_text(encoding="utf-8")
        )
        cls.adapter_spike = json.loads(
            (ROOT / "state" / "adapter_spike_v1.json").read_text(encoding="utf-8")
        )
        cls.capability_benchmark = json.loads(
            (ROOT / "state" / "capability_benchmark_v1.json").read_text(encoding="utf-8")
        )
        cls.agent_team = json.loads(
            (ROOT / "state" / "agent_team_v1.json").read_text(encoding="utf-8")
        )
        cls.core_alpha = json.loads(
            (ROOT / "state" / "core_alpha_v1.json").read_text(encoding="utf-8")
        )
        cls.core_alpha_real = json.loads(
            (ROOT / "state" / "core_alpha_real_v1.json").read_text(encoding="utf-8")
        )
        cls.operations = json.loads(
            (ROOT / "state" / "operations_and_diagnostics_v1.json").read_text(
                encoding="utf-8"
            )
        )
        cls.playlist = json.loads(
            (ROOT / "state" / "playlist_v1.json").read_text(encoding="utf-8")
        )
        cls.document_pipeline = json.loads(
            (ROOT / "state" / "document_pipeline_v1.json").read_text(encoding="utf-8")
        )
        cls.projects_sources = json.loads(
            (ROOT / "state" / "projects_sources_v1.json").read_text(encoding="utf-8")
        )
        cls.transcript_topic_studio = json.loads(
            (ROOT / "state" / "transcript_topic_studio_v1.json").read_text(
                encoding="utf-8"
            )
        )
        cls.multi_source_alignment = json.loads(
            (ROOT / "state" / "multi_source_alignment_v1.json").read_text(
                encoding="utf-8"
            )
        )
        cls.knowledge_integration = json.loads(
            (ROOT / "state" / "knowledge_integration_v1.json").read_text(
                encoding="utf-8"
            )
        )
        cls.media_integration = json.loads(
            (ROOT / "state" / "media_integration_v1.json").read_text(
                encoding="utf-8"
            )
        )
        cls.cross_navigation = json.loads(
            (ROOT / "state" / "cross_navigation_v1.json").read_text(
                encoding="utf-8"
            )
        )
        cls.obsidian_export = json.loads(
            (ROOT / "state" / "obsidian_export_v1.json").read_text(encoding="utf-8")
        )
        cls.current_baseline = json.loads(
            (ROOT / "state" / "current_canonical_baseline_v1.json").read_text(
                encoding="utf-8"
            )
        )

    def _baseline_fixture_root(self) -> Path:
        """Build a tiny isolated root for current-baseline mutation tests."""
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        paths = {
            item["path"] for item in self.current_baseline["files"]
        } | {
            "schemas/candidate_manifest_v1.schema.json",
            "state/native_macos_app_v1.json",
            "state/ready_app_v1.json",
        }
        for relative in paths:
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, destination)
        return root

    def test_current_baseline_exact_contract_passes(self):
        self.assertEqual(
            VALIDATOR.validate_current_canonical_baseline(self.current_baseline), []
        )

    def test_current_governed_byte_mutation_fails_closed(self):
        root = self._baseline_fixture_root()
        target = root / "macos/Resources/bridge.py"
        target.write_bytes(target.read_bytes() + b"\\n# unauthorized mutation\\n")
        errors = VALIDATOR.validate_current_canonical_baseline(
            self.current_baseline, root=root
        )
        self.assertIn(
            "current canonical baseline hash differs: macos/Resources/bridge.py",
            errors,
        )

    def test_missing_current_baseline_does_not_bypass_historical_drift(self):
        errors = VALIDATOR.validate_current_canonical_baseline({})
        self.assertIn("current canonical baseline fields must match v1", errors)
        native = json.loads(
            (ROOT / "state" / "native_macos_app_v1.json").read_text(encoding="utf-8")
        )
        drift = VALIDATOR.validate_native_macos_app_evidence(native)
        self.assertIn("R12 implementation hash differs: macos/Resources/bridge.py", drift)

    def test_corrupt_current_baseline_record_fails_closed(self):
        baseline = copy.deepcopy(self.current_baseline)
        baseline["files"][0]["current_sha256"] = "0" * 64
        errors = VALIDATOR.validate_current_canonical_baseline(baseline)
        self.assertIn(
            "current canonical baseline record differs: macos/Resources/bridge.py",
            errors,
        )

    def test_candidate_identity_substitution_fails(self):
        baseline = copy.deepcopy(self.current_baseline)
        baseline["candidate"]["candidate_id"] = "candidate-v1-" + "0" * 64
        errors = VALIDATOR.validate_current_canonical_baseline(baseline)
        self.assertIn(
            "current canonical baseline candidate ID is not bound to identity hash",
            errors,
        )

    def test_valid_superseding_baseline_suppresses_only_explained_historical_drift(self):
        native = json.loads(
            (ROOT / "state" / "native_macos_app_v1.json").read_text(encoding="utf-8")
        )
        ready = json.loads(
            (ROOT / "state" / "ready_app_v1.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            VALIDATOR.validate_native_macos_app_evidence(
                native, current_baseline=self.current_baseline
            ),
            [],
        )
        self.assertEqual(
            VALIDATOR.validate_ready_app_evidence(
                ready, current_baseline=self.current_baseline
            ),
            [],
        )

    def test_historical_certification_records_are_not_rewritten(self):
        native_path = ROOT / "state" / "native_macos_app_v1.json"
        ready_path = ROOT / "state" / "ready_app_v1.json"
        native_before = native_path.read_bytes()
        ready_before = ready_path.read_bytes()
        self.assertEqual(
            VALIDATOR.validate_current_canonical_baseline(self.current_baseline), []
        )
        self.assertEqual(native_path.read_bytes(), native_before)
        self.assertEqual(ready_path.read_bytes(), ready_before)

    def test_repository_state_is_valid(self):
        self.assertEqual(VALIDATOR.validate_state(self.state), [])

    def test_obsidian_export_evidence_is_valid(self):
        self.assertEqual(
            VALIDATOR.validate_obsidian_export_evidence(self.obsidian_export), []
        )

    def test_obsidian_export_cannot_claim_external_or_user_vault_access(self):
        evidence = copy.deepcopy(self.obsidian_export)
        evidence["safety"]["real_user_vault_accessed"] = True
        errors = VALIDATOR.validate_obsidian_export_evidence(evidence)
        self.assertIn("R10 safety evidence differs", errors)

    def test_missing_deferred_social_platform_fails(self):
        state = copy.deepcopy(self.state)
        state["release_scope"]["deferred_social_platforms"].remove("tiktok")
        errors = VALIDATOR.validate_state(state)
        self.assertIn(
            "deferred social platforms differ from the Product Owner registry",
            errors,
        )

    def test_deferred_capability_registry_is_exact(self):
        capabilities = set(self.state["release_scope"]["deferred"])
        self.assertEqual(capabilities, VALIDATOR.REQUIRED_DEFERRED_CAPABILITIES)
        self.assertTrue(
            {
                "multi_user_server_edition",
                "personalized_adaptive_learning",
                "unrestricted_rag",
                "full_autonomous_semantic_authoring",
            }.issubset(capabilities)
        )
        state = copy.deepcopy(self.state)
        state["release_scope"]["deferred"].remove("multi_user_server_edition")
        state["release_scope"]["deferred"].append("unknown_future_capability")
        self.assertIn(
            "deferred capabilities differ from the Product Owner registry",
            VALIDATOR.validate_state(state),
        )

    def test_ready_app_priority_order_is_exact(self):
        state = copy.deepcopy(self.state)
        state["delivery_target"]["priority_order"][1:3] = reversed(
            state["delivery_target"]["priority_order"][1:3]
        )
        self.assertIn(
            "delivery_target does not match the authorized READY_APP_V1 chain",
            VALIDATOR.validate_state(state),
        )

    def test_standalone_products_cannot_be_disabled(self):
        state = copy.deepcopy(self.state)
        state["standalone_products_preserved"] = False
        errors = VALIDATOR.validate_state(state)
        self.assertIn("standalone_products_preserved must be true", errors)

    def test_merge_requires_fail_closed_automation_policy(self):
        state = copy.deepcopy(self.state)
        state["execution_policy"]["merge"] = "AUTHORIZED"
        errors = VALIDATOR.validate_state(state)
        self.assertIn(
            "execution_policy does not match the authorized boundary", errors
        )

    def test_runtime_reconciliation_requires_governed_fail_closed_policy(self):
        state = copy.deepcopy(self.state)
        state["execution_policy"]["runtime_reconciliation"] = "UNRESTRICTED"
        errors = VALIDATOR.validate_state(state)
        self.assertIn(
            "execution_policy does not match the authorized boundary", errors
        )

    def test_agent_team_contract_is_pinned(self):
        state = copy.deepcopy(self.state)
        state["agent_team_contract"] = "state/other.json"
        errors = VALIDATOR.validate_state(state)
        self.assertIn(
            "agent_team_contract must pin the governed agent registry", errors
        )

    def test_core_alpha_evidence_is_pinned(self):
        state = copy.deepcopy(self.state)
        state["core_alpha_evidence"] = "state/other.json"
        errors = VALIDATOR.validate_state(state)
        self.assertIn(
            "core_alpha_evidence must pin the R6 checkpoint record", errors
        )

    def test_core_alpha_evidence_is_valid(self):
        self.assertEqual(
            VALIDATOR.validate_core_alpha_evidence(self.core_alpha), []
        )

    def test_core_alpha_cannot_claim_semantic_acceptance(self):
        evidence = copy.deepcopy(self.core_alpha)
        evidence["acceptance"]["semantic_authority"] = "ACCEPTED"
        errors = VALIDATOR.validate_core_alpha_evidence(evidence)
        self.assertIn(
            "R6 checkpoint evidence differs from the fail-closed contract", errors
        )

    def test_core_alpha_fixture_hash_is_bound(self):
        evidence = copy.deepcopy(self.core_alpha)
        evidence["fixture"]["sha256"] = "0" * 64
        errors = VALIDATOR.validate_core_alpha_evidence(evidence)
        self.assertIn(
            "R6 replay fixture hash differs from the governed record", errors
        )

    def test_r6_acceptance_requires_pinned_real_media_evidence(self):
        state = copy.deepcopy(self.state)
        state["core_alpha_real_evidence"] = "state/other.json"
        errors = VALIDATOR.validate_state(state)
        self.assertIn(
            "core_alpha_real_evidence must pin the R6 actual execution record", errors
        )

    def test_core_alpha_real_evidence_is_valid(self):
        self.assertEqual(
            VALIDATOR.validate_core_alpha_real_evidence(
                self.core_alpha_real, self.baselines
            ),
            [],
        )

    def test_core_alpha_real_evidence_cannot_promote_semantics(self):
        evidence = copy.deepcopy(self.core_alpha_real)
        evidence["stages"]["topics"]["semantic_status"] = "ACCEPTED"
        errors = VALIDATOR.validate_core_alpha_real_evidence(
            evidence, self.baselines
        )
        self.assertTrue(any("topics" in error for error in errors))

    def test_core_alpha_real_evidence_requires_repeatable_stage_hashes(self):
        evidence = copy.deepcopy(self.core_alpha_real)
        evidence["determinism"]["all_stage_hashes_identical"] = False
        errors = VALIDATOR.validate_core_alpha_real_evidence(
            evidence, self.baselines
        )
        self.assertIn(
            "R6 actual stage hashes must match across two independent runs", errors
        )

    def test_core_alpha_real_implementation_inventory_is_exact(self):
        evidence = copy.deepcopy(self.core_alpha_real)
        evidence["implementation"].pop()
        errors = VALIDATOR.validate_core_alpha_real_evidence(
            evidence, self.baselines
        )
        self.assertIn(
            "R6 actual implementation inventory must be exact", errors
        )

    def test_core_alpha_real_record_is_immutably_bound(self):
        mutations = []
        for mutate in (
            lambda value: value["source"].__setitem__("size_bytes", value["source"]["size_bytes"] + 1),
            lambda value: value["models"]["topics"].__setitem__("name", "mutable-tag"),
            lambda value: value["alignment"].__setitem__("aligned_word_intervals", 38),
            lambda value: value["stages"]["topics"].__setitem__("sha256", "0" * 64),
            lambda value: value.__setitem__("executed_at", "2026-09-10T00:00:00Z"),
        ):
            evidence = copy.deepcopy(self.core_alpha_real)
            mutate(evidence)
            mutations.append(evidence)
        for evidence in mutations:
            with self.subTest(evidence=evidence):
                errors = VALIDATOR.validate_core_alpha_real_evidence(evidence, self.baselines)
                self.assertIn(
                    "R6 actual evidence differs from the independently reproduced governed record",
                    errors,
                )

    def test_core_alpha_real_rejects_unknown_top_level_field(self):
        evidence = copy.deepcopy(self.core_alpha_real)
        evidence["unexpected"] = True
        errors = VALIDATOR.validate_core_alpha_real_evidence(evidence, self.baselines)
        self.assertTrue(any("top-level fields" in error for error in errors))

    def test_operations_evidence_is_pinned_and_valid(self):
        self.assertEqual(VALIDATOR.validate_operations_evidence(self.operations), [])
        state = copy.deepcopy(self.state)
        state["operations_and_diagnostics_evidence"] = "state/other.json"
        self.assertIn(
            "operations_and_diagnostics_evidence must pin Issue #46 acceptance",
            VALIDATOR.validate_state(state),
        )

    def test_operations_implementation_and_fixtures_are_hash_bound(self):
        evidence = copy.deepcopy(self.operations)
        evidence["implementation"][0]["sha256"] = "0" * 64
        self.assertTrue(
            any(
                "Operations implementation hash differs" in error
                for error in VALIDATOR.validate_operations_evidence(evidence)
            )
        )
        evidence = copy.deepcopy(self.operations)
        evidence["fixture_inventory"].pop()
        self.assertIn(
            "Operations fixture inventory must be exact",
            VALIDATOR.validate_operations_evidence(evidence),
        )

    def test_operations_evidence_cannot_expand_protected_scope(self):
        evidence = copy.deepcopy(self.operations)
        evidence["protected_data_accessed"] = True
        self.assertIn(
            "Operations evidence must not access protected data",
            VALIDATOR.validate_operations_evidence(evidence),
        )

    def test_playlist_evidence_is_pinned_and_valid(self):
        self.assertEqual(VALIDATOR.validate_playlist_evidence(self.playlist), [])
        state = copy.deepcopy(self.state)
        state["playlist_evidence"] = "state/other.json"
        self.assertIn(
            "playlist_evidence must pin R8A acceptance",
            VALIDATOR.validate_state(state),
        )

    def test_playlist_implementation_and_fixtures_are_hash_bound(self):
        evidence = copy.deepcopy(self.playlist)
        evidence["implementation"][0]["sha256"] = "0" * 64
        self.assertTrue(
            any(
                "R8A implementation hash differs" in error
                for error in VALIDATOR.validate_playlist_evidence(evidence)
            )
        )
        evidence = copy.deepcopy(self.playlist)
        evidence["fixtures"].pop()
        self.assertIn(
            "R8A fixture inventory must be exact",
            VALIDATOR.validate_playlist_evidence(evidence),
        )

    def test_playlist_evidence_cannot_expand_external_scope(self):
        evidence = copy.deepcopy(self.playlist)
        evidence["acceptance"]["external_actions_performed"] = True
        self.assertIn(
            "R8A acceptance evidence differs from the governed contract",
            VALIDATOR.validate_playlist_evidence(evidence),
        )

    def test_document_pipeline_evidence_is_pinned_and_valid(self):
        self.assertEqual(
            VALIDATOR.validate_document_pipeline_evidence(self.document_pipeline), []
        )
        state = copy.deepcopy(self.state)
        state["document_pipeline_evidence"] = "state/other.json"
        self.assertIn(
            "document_pipeline_evidence must pin R8B acceptance",
            VALIDATOR.validate_state(state),
        )

    def test_document_pipeline_implementation_and_fixtures_are_hash_bound(self):
        evidence = copy.deepcopy(self.document_pipeline)
        evidence["implementation"][0]["sha256"] = "0" * 64
        self.assertTrue(
            any(
                "R8B implementation hash differs" in error
                for error in VALIDATOR.validate_document_pipeline_evidence(evidence)
            )
        )
        evidence = copy.deepcopy(self.document_pipeline)
        evidence["fixtures"].clear()
        self.assertIn(
            "R8B fixture inventory must be exact",
            VALIDATOR.validate_document_pipeline_evidence(evidence),
        )

    def test_document_pipeline_evidence_cannot_expand_protected_scope(self):
        evidence = copy.deepcopy(self.document_pipeline)
        evidence["acceptance"]["protected_data_accessed"] = True
        self.assertIn(
            "R8B acceptance evidence differs from the governed contract",
            VALIDATOR.validate_document_pipeline_evidence(evidence),
        )

    def test_projects_sources_evidence_is_pinned_and_valid(self):
        self.assertEqual(
            VALIDATOR.validate_projects_sources_evidence(self.projects_sources), []
        )
        state = copy.deepcopy(self.state)
        state["projects_sources_evidence"] = "state/other.json"
        self.assertIn(
            "projects_sources_evidence must pin Issue #47 acceptance",
            VALIDATOR.validate_state(state),
        )

    def test_projects_sources_implementation_is_hash_bound(self):
        evidence = copy.deepcopy(self.projects_sources)
        evidence["implementation"][0]["sha256"] = "0" * 64
        self.assertTrue(
            any(
                "Projects & Sources implementation hash differs" in error
                for error in VALIDATOR.validate_projects_sources_evidence(evidence)
            )
        )

    def test_projects_sources_evidence_cannot_expand_scope(self):
        evidence = copy.deepcopy(self.projects_sources)
        evidence["safety"]["network_access_performed"] = True
        self.assertIn(
            "Projects & Sources safety evidence differs from v1",
            VALIDATOR.validate_projects_sources_evidence(evidence),
        )

    def test_unknown_dependency_fails(self):
        state = copy.deepcopy(self.state)
        state["roadmap"][1]["depends_on"] = ["UNKNOWN"]
        errors = VALIDATOR.validate_state(state)
        self.assertTrue(any("unknown dependency" in error for error in errors))

    def test_roadmap_issue_inventory_is_complete(self):
        self.assertEqual(
            {
                entry["id"]: entry["issue"]
                for entry in self.state["roadmap"]
            },
            VALIDATOR.EXPECTED_ROADMAP_ISSUES,
        )

    def test_required_module_has_executable_stage(self):
        state = copy.deepcopy(self.state)
        state["roadmap"] = [
            entry
            for entry in state["roadmap"]
            if entry["id"] != "OPERATIONS_AND_DIAGNOSTICS_V1"
        ]
        errors = VALIDATOR.validate_state(state)
        self.assertTrue(
            any(
                "operations_and_diagnostics lacks executable roadmap coverage"
                in error
                for error in errors
            )
        )

    def test_module_completion_dependencies_are_required(self):
        state = copy.deepcopy(self.state)
        entry = next(
            item
            for item in state["roadmap"]
            if item["id"] == "TRANSCRIPT_AND_TOPIC_STUDIO_V1"
        )
        entry["depends_on"].remove("PROJECTS_AND_SOURCES_V1")
        errors = VALIDATOR.validate_state(state)
        self.assertTrue(
            any(
                "TRANSCRIPT_AND_TOPIC_STUDIO_V1 lacks required dependencies"
                in error
                for error in errors
            )
        )

    def test_native_app_requires_onedrive_publication(self):
        state = copy.deepcopy(self.state)
        entry = next(item for item in state["roadmap"] if item["id"] == "R12")
        entry["depends_on"].remove("ONEDRIVE_PUBLICATION_V1")
        errors = VALIDATOR.validate_state(state)
        self.assertTrue(
            any(
                "R12 dependencies differ from the exact READY_APP_V1 chain" in error
                for error in errors
            )
        )

    def test_native_app_cannot_depend_on_deferred_capability(self):
        state = copy.deepcopy(self.state)
        entry = next(item for item in state["roadmap"] if item["id"] == "R12")
        entry["depends_on"].append("R11")
        errors = VALIDATOR.validate_state(state)
        self.assertTrue(
            any("R12 must not depend on deferred roadmap items" in error for error in errors)
        )

    def test_active_chain_rejects_extra_accepted_dependency(self):
        state = copy.deepcopy(self.state)
        entry = next(item for item in state["roadmap"] if item["id"] == "R12")
        entry["depends_on"].append("R9C")
        errors = VALIDATOR.validate_state(state)
        self.assertTrue(
            any(
                "R12 dependencies differ from the exact READY_APP_V1 chain" in error
                for error in errors
            )
        )

    def test_deferred_capability_must_follow_r14(self):
        state = copy.deepcopy(self.state)
        deferred = next(item for item in state["roadmap"] if item["id"] == "R11")
        deferred["depends_on"].remove("R14")
        errors = VALIDATOR.validate_state(state)
        self.assertIn("R11 must be dependency-blocked until after R14", errors)

    def test_deferred_capability_status_is_enforced(self):
        state = copy.deepcopy(self.state)
        deferred = next(item for item in state["roadmap"] if item["id"] == "R11")
        deferred["status"] = "PLANNED"
        errors = VALIDATOR.validate_state(state)
        self.assertIn("R11 must remain DEFERRED_TO_LATER_WORK", errors)

    def test_r14_acceptance_cannot_regress_to_human_gate(self):
        state = copy.deepcopy(self.state)
        next(item for item in state["roadmap"] if item["id"] == "R14")["status"] = "HUMAN_GATE"
        errors = VALIDATOR.validate_state(state)
        self.assertIn("R14 must be ACCEPTED after the Product Owner decision", errors)

    def test_r15_is_deferred_after_r14(self):
        state = copy.deepcopy(self.state)
        r15 = next(item for item in state["roadmap"] if item["id"] == "R15")
        r15["status"] = "POST_1_0_DEFERRED"
        r15["depends_on"].remove("R14")
        errors = VALIDATOR.validate_state(state)
        self.assertIn("R15 must remain DEFERRED_TO_LATER_WORK", errors)
        self.assertIn("R15 must be dependency-blocked until after R14", errors)

    def test_forward_dependency_fails(self):
        state = copy.deepcopy(self.state)
        state["roadmap"][0]["depends_on"] = ["R1"]
        errors = VALIDATOR.validate_state(state)
        self.assertTrue(any("must appear earlier" in error for error in errors))

    def test_accepted_foundation_stage_cannot_regress(self):
        state = copy.deepcopy(self.state)
        next(entry for entry in state["roadmap"] if entry["id"] == "R3")["status"] = "PLANNED"
        errors = VALIDATOR.validate_state(state)
        self.assertIn("R3 must remain ACCEPTED", errors)

    def test_component_baselines_are_valid(self):
        self.assertEqual(VALIDATOR.validate_component_baselines(self.baselines), [])

    def test_unmerged_component_work_cannot_be_enabled(self):
        baselines = copy.deepcopy(self.baselines)
        baselines["integration_policy"]["unmerged_work_allowed"] = True
        errors = VALIDATOR.validate_component_baselines(baselines)
        self.assertTrue(any("read-only and pinned" in error for error in errors))

    def test_r1_cannot_pass_without_supported_standalone_gates(self):
        baselines = copy.deepcopy(self.baselines)
        baselines["r1_acceptance"]["supported_standalone_gates_pass"] = False
        errors = VALIDATOR.validate_component_baselines(baselines)
        self.assertTrue(any("cannot PASS" in error for error in errors))

    def test_r1_cannot_promote_source_application_release(self):
        baselines = copy.deepcopy(self.baselines)
        baselines["r1_acceptance"]["release_promotion_performed"] = True
        errors = VALIDATOR.validate_component_baselines(baselines)
        self.assertTrue(any("must not promote" in error for error in errors))

    def test_data_ownership_contract_is_valid(self):
        self.assertEqual(VALIDATOR.validate_data_ownership(self.ownership), [])

    def test_duplicate_field_owner_fails(self):
        ownership = copy.deepcopy(self.ownership)
        ownership["ownership"].append(copy.deepcopy(ownership["ownership"][0]))
        errors = VALIDATOR.validate_data_ownership(ownership)
        self.assertTrue(any("exactly one ownership" in error for error in errors))

    def test_protocol_trace_namespaces_are_registered(self):
        ownership = copy.deepcopy(self.ownership)
        ownership["id_policy"]["namespaces"].remove("message")
        errors = VALIDATOR.validate_data_ownership(ownership)
        self.assertTrue(any("trace namespaces" in error for error in errors))

    def test_operations_ownership_is_exact(self):
        ownership = copy.deepcopy(self.ownership)
        entry = next(
            item
            for item in ownership["ownership"]
            if item["field_pattern"] == "/operations/jobs/*"
        )
        entry["authoritative_owner"] = "worker"
        self.assertTrue(
            any(
                "operations ownership differs" in error
                for error in VALIDATOR.validate_data_ownership(ownership)
            )
        )

    def test_identity_hash_collision_must_hard_fail(self):
        ownership = copy.deepcopy(self.ownership)
        ownership["collision_policy"]["same_id_different_hash"] = "LAST_WRITER_WINS"
        errors = VALIDATOR.validate_data_ownership(ownership)
        self.assertTrue(any("must hard-fail" in error for error in errors))

    def test_worker_protocol_contract_is_valid(self):
        self.assertEqual(
            VALIDATOR.validate_worker_protocol(self.worker_protocol), []
        )

    def test_worker_protocol_cannot_enable_network_requirement(self):
        protocol = copy.deepcopy(self.worker_protocol)
        protocol["network_service_required"] = True
        errors = VALIDATOR.validate_worker_protocol(protocol)
        self.assertTrue(any("network service" in error for error in errors))

    def test_worker_protocol_unknown_outcome_retry_must_be_denied(self):
        protocol = copy.deepcopy(self.worker_protocol)
        protocol["job_policy"]["unknown_outcome_retry"] = "ALLOWED"
        errors = VALIDATOR.validate_worker_protocol(protocol)
        self.assertTrue(any("unknown outcomes" in error for error in errors))

    def test_worker_protocol_fixture_inventory_is_complete(self):
        protocol = copy.deepcopy(self.worker_protocol)
        protocol["fixtures"].pop("provenance")
        errors = VALIDATOR.validate_worker_protocol(protocol)
        self.assertTrue(any("fixture inventory" in error for error in errors))

    def test_worker_protocol_schema_registry_is_exact(self):
        protocol = copy.deepcopy(self.worker_protocol)
        protocol["schemas"].pop("artifact_reference")
        errors = VALIDATOR.validate_worker_protocol(protocol)
        self.assertTrue(any("all three accepted schemas" in error for error in errors))

    def test_adapter_spike_evidence_is_valid(self):
        self.assertEqual(
            VALIDATOR.validate_adapter_spike(self.adapter_spike, self.baselines), []
        )

    def test_adapter_spike_must_match_pinned_source_commit(self):
        evidence = copy.deepcopy(self.adapter_spike)
        evidence["components"][0]["commit_sha"] = "0" * 40
        errors = VALIDATOR.validate_adapter_spike(evidence, self.baselines)
        self.assertTrue(any("commit differs" in error for error in errors))

    def test_adapter_spike_source_mutation_is_forbidden(self):
        evidence = copy.deepcopy(self.adapter_spike)
        evidence["source_repositories_changed"] = True
        errors = VALIDATOR.validate_adapter_spike(evidence, self.baselines)
        self.assertTrue(any("must not modify" in error for error in errors))

    def test_adapter_spike_controller_identity_is_pinned(self):
        evidence = copy.deepcopy(self.adapter_spike)
        evidence["controller"]["tree_sha"] = "not-a-tree"
        errors = VALIDATOR.validate_adapter_spike(evidence, self.baselines)
        self.assertTrue(any("controller has invalid tree_sha" in error for error in errors))

    def test_capability_benchmark_is_valid(self):
        self.assertEqual(
            VALIDATOR.validate_capability_benchmark(
                self.capability_benchmark, self.baselines
            ),
            [],
        )

    def test_capability_benchmark_cannot_claim_semantic_superiority(self):
        evidence = copy.deepcopy(self.capability_benchmark)
        evidence["capabilities"][4]["selection"]["semantic_superiority_claimed"] = True
        errors = VALIDATOR.validate_capability_benchmark(evidence, self.baselines)
        self.assertTrue(any("semantic superiority" in error for error in errors))

    def test_capability_benchmark_cannot_mutate_source_repositories(self):
        evidence = copy.deepcopy(self.capability_benchmark)
        evidence["source_repositories_changed"] = True
        errors = VALIDATOR.validate_capability_benchmark(evidence, self.baselines)
        self.assertTrue(any("source repositories" in error for error in errors))

    def test_capability_benchmark_fixture_hash_is_bound(self):
        evidence = copy.deepcopy(self.capability_benchmark)
        evidence["fixture_manifest"]["sha256"] = "0" * 64
        errors = VALIDATOR.validate_capability_benchmark(evidence, self.baselines)
        self.assertTrue(any("fixture hash" in error for error in errors))

    def test_transcript_topic_studio_evidence_is_valid(self):
        self.assertEqual(
            VALIDATOR.validate_transcript_topic_studio_evidence(
                self.transcript_topic_studio, self.baselines
            ),
            [],
        )

    def test_transcript_topic_studio_cannot_accept_machine_semantics(self):
        evidence = copy.deepcopy(self.transcript_topic_studio)
        evidence["safety"]["machine_semantics_accepted"] = True
        errors = VALIDATOR.validate_transcript_topic_studio_evidence(
            evidence, self.baselines
        )
        self.assertTrue(any("safety boundary" in error for error in errors))

    def test_transcript_topic_studio_capability_owners_are_pinned(self):
        evidence = copy.deepcopy(self.transcript_topic_studio)
        evidence["capability_owners"]["topics"] = ["videotext"]
        errors = VALIDATOR.validate_transcript_topic_studio_evidence(
            evidence, self.baselines
        )
        self.assertTrue(any("capability owners" in error for error in errors))

    def test_transcript_topic_studio_implementation_hash_is_bound(self):
        evidence = copy.deepcopy(self.transcript_topic_studio)
        evidence["implementation"][0]["sha256"] = "0" * 64
        errors = VALIDATOR.validate_transcript_topic_studio_evidence(
            evidence, self.baselines
        )
        self.assertTrue(any("implementation hash differs" in error for error in errors))

    def test_multi_source_alignment_evidence_is_valid(self):
        self.assertEqual(
            VALIDATOR.validate_multi_source_alignment_evidence(
                self.multi_source_alignment, self.baselines
            ),
            [],
        )

    def test_multi_source_alignment_cannot_claim_semantic_acceptance(self):
        evidence = copy.deepcopy(self.multi_source_alignment)
        evidence["acceptance"]["semantic_acceptance_automatic"] = True
        errors = VALIDATOR.validate_multi_source_alignment_evidence(evidence, self.baselines)
        self.assertTrue(any("acceptance evidence" in error for error in errors))

    def test_multi_source_alignment_implementation_hash_is_bound(self):
        evidence = copy.deepcopy(self.multi_source_alignment)
        evidence["implementation"][0]["sha256"] = "0" * 64
        errors = VALIDATOR.validate_multi_source_alignment_evidence(evidence, self.baselines)
        self.assertTrue(any("implementation hash differs" in error for error in errors))

    def test_knowledge_integration_evidence_is_valid(self):
        self.assertEqual(
            VALIDATOR.validate_knowledge_integration_evidence(
                self.knowledge_integration, self.baselines
            ),
            [],
        )

    def test_knowledge_integration_cannot_claim_machine_acceptance(self):
        evidence = copy.deepcopy(self.knowledge_integration)
        evidence["acceptance"]["machine_semantic_acceptance"] = True
        errors = VALIDATOR.validate_knowledge_integration_evidence(evidence, self.baselines)
        self.assertTrue(any("acceptance evidence" in error for error in errors))

    def test_knowledge_integration_source_baseline_is_pinned(self):
        evidence = copy.deepcopy(self.knowledge_integration)
        evidence["source_component"]["commit_sha"] = "0" * 40
        errors = VALIDATOR.validate_knowledge_integration_evidence(evidence, self.baselines)
        self.assertTrue(any("source component" in error for error in errors))

    def test_media_integration_evidence_is_valid(self):
        self.assertEqual(
            VALIDATOR.validate_media_integration_evidence(
                self.media_integration, self.baselines
            ),
            [],
        )

    def test_media_integration_cannot_claim_knowledge_mutation(self):
        evidence = copy.deepcopy(self.media_integration)
        evidence["acceptance"]["knowledge_truth_immutable"] = False
        errors = VALIDATOR.validate_media_integration_evidence(evidence, self.baselines)
        self.assertTrue(any("acceptance evidence" in error for error in errors))

    def test_media_integration_source_baseline_and_hashes_are_pinned(self):
        evidence = copy.deepcopy(self.media_integration)
        evidence["source_component"]["commit_sha"] = "0" * 40
        errors = VALIDATOR.validate_media_integration_evidence(evidence, self.baselines)
        self.assertTrue(any("source component" in error for error in errors))
        evidence = copy.deepcopy(self.media_integration)
        evidence["implementation"][0]["sha256"] = "0" * 64
        errors = VALIDATOR.validate_media_integration_evidence(evidence, self.baselines)
        self.assertTrue(any("implementation hash differs" in error for error in errors))

    def test_cross_navigation_evidence_is_valid(self):
        self.assertEqual(
            VALIDATOR.validate_cross_navigation_evidence(self.cross_navigation), []
        )

    def test_cross_navigation_cannot_claim_semantic_promotion(self):
        evidence = copy.deepcopy(self.cross_navigation)
        evidence["acceptance"]["semantic_promotion_automatic"] = True
        errors = VALIDATOR.validate_cross_navigation_evidence(evidence)
        self.assertTrue(any("acceptance evidence" in error for error in errors))

    def test_cross_navigation_implementation_hashes_are_pinned(self):
        evidence = copy.deepcopy(self.cross_navigation)
        evidence["implementation"][0]["sha256"] = "0" * 64
        errors = VALIDATOR.validate_cross_navigation_evidence(evidence)
        self.assertTrue(any("implementation hash differs" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
