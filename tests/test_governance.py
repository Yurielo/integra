import copy
import importlib.util
import json
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

    def test_repository_state_is_valid(self):
        self.assertEqual(VALIDATOR.validate_state(self.state), [])

    def test_missing_social_platform_fails(self):
        state = copy.deepcopy(self.state)
        state["release_scope"]["social_platforms"].remove("tiktok")
        errors = VALIDATOR.validate_state(state)
        self.assertTrue(any("missing social platforms" in error for error in errors))

    def test_standalone_products_cannot_be_disabled(self):
        state = copy.deepcopy(self.state)
        state["standalone_products_preserved"] = False
        errors = VALIDATOR.validate_state(state)
        self.assertIn("standalone_products_preserved must be true", errors)

    def test_merge_is_not_implicitly_authorized(self):
        state = copy.deepcopy(self.state)
        state["execution_policy"]["merge"] = "AUTHORIZED"
        errors = VALIDATOR.validate_state(state)
        self.assertIn(
            "execution_policy does not match the authorized boundary", errors
        )

    def test_unknown_dependency_fails(self):
        state = copy.deepcopy(self.state)
        state["roadmap"][1]["depends_on"] = ["UNKNOWN"]
        errors = VALIDATOR.validate_state(state)
        self.assertTrue(any("unknown dependency" in error for error in errors))

    def test_roadmap_issue_inventory_is_complete(self):
        self.assertEqual(
            {entry["issue"] for entry in self.state["roadmap"]}, set(range(2, 32))
        )

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


if __name__ == "__main__":
    unittest.main()
