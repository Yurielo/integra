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


if __name__ == "__main__":
    unittest.main()
