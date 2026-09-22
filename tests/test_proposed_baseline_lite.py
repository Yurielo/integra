"""Anti-bypass regressions for Issue #165 Proposed Baseline Lite."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from proposed_baseline_lite import (  # noqa: E402
    next_current,
    proposal_state,
    validate_current,
    validate_proposal,
    verify_promotion_material,
)


class ProposedBaselineLiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.current = json.loads((ROOT / "state/current_product_baseline_v2.json").read_text())

    def proposal(self):
        active = self.current["records"][0]
        changed = active["governed_files"][0]
        return {
            "schema_version": "1.0",
            "artifact_type": "integra.proposed_product_baseline",
            "proposal_id": "proposal-recovery-example",
            "status": "PROPOSED_BASELINE_VALID",
            "base_current_id": active["baseline_id"],
            "base_main": active["main"],
            "proposed_source": {"commit_sha": "1" * 40, "tree_sha": "2" * 40},
            "proposed_head": {"commit_sha": "1" * 40, "tree_sha": "2" * 40},
            "intended_scope": {"wp": "Recovery #162", "journey": "failure/cancel/timeout recovery"},
            "candidate": {"candidate_id": "candidate-v1-" + "3" * 64, "identity_sha256": "3" * 64, "manifest_digest": "6" * 64, "bundle_digest": "4" * 64},
            "delta": [{"path": changed["path"], "before_sha256": changed["sha256"], "after_sha256": "5" * 64}],
            "gates": [{"name": "candidate-manifest", "result": "PASS", "evidence_ref": "evidence/candidate.json"}],
            "evidence": {
                "candidate_manifest": {"path": "manifest.json", "sha256": "6" * 64},
                "candidate_evidence": {"path": "evidence.json", "sha256": "7" * 64},
                "report": {"path": "docs/report.md", "sha256": "8" * 64},
            },
            "owner_acceptance": None,
            "allowed_overlay_paths": ["state/proposed_baseline_lite_v1.json"],
        }

    def test_current_v2_passes_and_is_not_v1_rewrite(self):
        self.assertEqual(validate_current(self.current, ROOT), [])
        predecessor = self.current["records"][0]["historical_predecessors"]
        self.assertEqual({item["path"] for item in predecessor}, {
            "state/current_canonical_baseline_v1.json", "state/native_macos_app_v1.json", "state/ready_app_v1.json",
        })

    def test_governed_byte_drift_without_proposal_fails_closed(self):
        current = copy.deepcopy(self.current)
        current["records"][0]["governed_files"][0]["sha256"] = "0" * 64
        self.assertIn("CURRENT v2 governed byte drift: macos/Resources/bridge.py", validate_current(current, ROOT))

    def test_malformed_or_stale_current_cannot_be_selected(self):
        current = copy.deepcopy(self.current)
        current["current_id"] = "missing"
        self.assertIn("CURRENT v2 current_id does not select exactly one record", validate_current(current, ROOT))

    def test_valid_proposal_is_awaiting_owner_acceptance_not_current(self):
        proposal = self.proposal()
        state, errors = proposal_state(proposal, self.current, ROOT)
        self.assertEqual(errors, [])
        self.assertEqual(state, "PROPOSED_BASELINE_VALID / AWAITING_OWNER_ACCEPTANCE")
        self.assertEqual(self.current["current_id"], "current-v2-156-160")

    def test_proposal_cannot_substitute_current_or_candidate(self):
        proposal = self.proposal(); proposal["base_current_id"] = "other"
        self.assertIn("PROPOSED baseline does not bind CURRENT", validate_proposal(proposal, self.current, ROOT))
        proposal = self.proposal(); proposal["candidate"]["candidate_id"] = "candidate-v1-" + "0" * 64
        self.assertIn("PROPOSED baseline candidate ID is not bound to identity hash", validate_proposal(proposal, self.current, ROOT))

    def test_malformed_delta_missing_gate_or_unbound_evidence_fails(self):
        proposal = self.proposal(); proposal["delta"] = []
        self.assertIn("PROPOSED baseline exact delta is required", validate_proposal(proposal, self.current, ROOT))
        proposal = self.proposal(); proposal["gates"][0]["result"] = "SKIPPED"
        self.assertIn("PROPOSED baseline mandatory gates are not all PASS with evidence", validate_proposal(proposal, self.current, ROOT))
        proposal = self.proposal(); proposal["evidence"]["candidate_manifest"]["path"] = ""
        self.assertIn("PROPOSED baseline candidate-bound evidence is invalid", validate_proposal(proposal, self.current, ROOT))

    def test_technical_green_never_self_accepts_or_promotes(self):
        proposal = self.proposal(); proposal["owner_acceptance"] = "ci-green"
        self.assertIn("PROPOSED baseline must await a separate explicit owner acceptance reference", validate_proposal(proposal, self.current, ROOT))
        with self.assertRaisesRegex(ValueError, "explicit owner acceptance reference"):
            next_current(self.current, self.proposal(), "", previous_current_path="state/history.json")
        current = copy.deepcopy(self.current)
        current["records"][0]["promotion_policy"] = "TECHNICAL_GREEN_CAN_MERGE"
        self.assertIn("CURRENT v2 promotion policy does not require explicit human owner authorization", validate_current(current, ROOT))

    def test_explicit_owner_reference_constructs_next_current_without_mutating_prior(self):
        proposal = self.proposal()
        result = next_current(self.current, proposal, "https://github.com/Yurielo/integra/issues/999#issuecomment-owner", previous_current_path="state/current-history.json")
        self.assertEqual(self.current["current_id"], "current-v2-156-160")
        self.assertEqual(len(result["records"]), 2)
        self.assertEqual(result["current_id"], "current-v2-" + "3" * 64)
        self.assertEqual(result["records"][0], self.current["records"][0])

    def test_branch_name_and_generic_technical_claim_are_not_authority_fields(self):
        proposal = self.proposal(); proposal["branch"] = "main"
        self.assertIn("PROPOSED baseline fields are invalid", validate_proposal(proposal, self.current, ROOT))
        current = copy.deepcopy(self.current); current["records"][0]["acceptance"]["decision"] = "TECHNICAL_GREEN"
        self.assertIn("CURRENT v2 acceptance is not an explicit scoped owner decision", validate_current(current, ROOT))

    def test_promotion_material_requires_exact_head_and_real_bound_artifacts(self):
        errors = verify_promotion_material(self.proposal(), ROOT)
        self.assertIn("promotion source HEAD/tree differs from PROPOSED baseline", errors)
        self.assertIn("promotion candidate_manifest is unavailable or invalid", errors)
        self.assertIn("promotion candidate_evidence is unavailable or invalid", errors)


if __name__ == "__main__":
    unittest.main()
