import copy
import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "check_agents.py"
SPEC = importlib.util.spec_from_file_location("check_agents", MODULE_PATH)
CHECKER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(CHECKER)


class AgentTeamValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = json.loads(
            (ROOT / "state" / "agent_team_v1.json").read_text(encoding="utf-8")
        )

    def test_agent_team_is_valid(self):
        self.assertEqual(CHECKER.validate_agent_team(self.registry), [])

    def test_product_owner_must_remain_lead(self):
        registry = copy.deepcopy(self.registry)
        registry["lead_agent"] = "backend-developer"
        errors = CHECKER.validate_agent_team(registry)
        self.assertIn("product-owner must remain the lead agent", errors)

    def test_human_authority_cannot_be_removed(self):
        registry = copy.deepcopy(self.registry)
        registry["human_product_owner_authority"] = "DELEGATED"
        errors = CHECKER.validate_agent_team(registry)
        self.assertIn("human Product Owner authority must remain explicit", errors)

    def test_every_role_is_required_exactly_once(self):
        registry = copy.deepcopy(self.registry)
        registry["roles"].pop()
        errors = CHECKER.validate_agent_team(registry)
        self.assertIn(
            "agent role inventory must contain exactly the nine governed roles", errors
        )

    def test_routine_human_dispatch_cannot_be_enabled(self):
        registry = copy.deepcopy(self.registry)
        registry["safeguards"]["routine_human_dispatch_required"] = True
        errors = CHECKER.validate_agent_team(registry)
        self.assertIn(
            "agent safeguards differ from the authorized operating model", errors
        )

    def test_external_systems_are_not_inferred(self):
        registry = copy.deepcopy(self.registry)
        registry["safeguards"]["external_system_access_inferred_from_role_name"] = True
        errors = CHECKER.validate_agent_team(registry)
        self.assertIn(
            "agent safeguards differ from the authorized operating model", errors
        )

    def test_role_paths_are_exact_and_cannot_escape_registry(self):
        registry = copy.deepcopy(self.registry)
        registry["roles"][0]["registration"] = "/tmp/product-owner.toml"
        errors = CHECKER.validate_agent_team(registry)
        self.assertIn("registration path mismatch for product-owner", errors)

    def test_execution_policy_cannot_weaken_genuine_gate_boundary(self):
        registry = copy.deepcopy(self.registry)
        registry["execution_policy"] = "UNRESTRICTED"
        errors = CHECKER.validate_agent_team(registry)
        self.assertIn(
            "agent execution must remain autonomous until a genuine gate", errors
        )

    def test_role_mode_must_match_contract(self):
        registry = copy.deepcopy(self.registry)
        registry["roles"][0]["mode"] = "IMPLEMENTATION"
        errors = CHECKER.validate_agent_team(registry)
        self.assertIn("role mode mismatch for product-owner", errors)

    def test_handoff_inventory_is_exact(self):
        registry = copy.deepcopy(self.registry)
        registry["handoff_required_fields"].remove("authority")
        errors = CHECKER.validate_agent_team(registry)
        self.assertIn("handoff fields must match the governed v1 contract", errors)

    def test_external_system_defaults_are_exact(self):
        registry = copy.deepcopy(self.registry)
        registry["default_systems"]["jira"] = "DEFAULT"
        errors = CHECKER.validate_agent_team(registry)
        self.assertIn("default systems differ from the governed v1 contract", errors)

    def test_unexpected_registry_field_fails_closed(self):
        registry = copy.deepcopy(self.registry)
        registry["unreviewed"] = True
        errors = CHECKER.validate_agent_team(registry)
        self.assertIn(
            "agent registry top-level fields must match the v1 contract", errors
        )


if __name__ == "__main__":
    unittest.main()
