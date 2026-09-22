"""Anti-bypass regressions for Issue #165 Proposed Baseline Lite."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
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
from validate_governance import _promoted_current_v2_supersedes_historical_hash  # noqa: E402


class ProposedBaselineLiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stored = json.loads((ROOT / "state/current_product_baseline_v2.json").read_text())
        # These anti-bypass cases model a new proposal from the immutable
        # pre-promotion CURRENT, even when the repository's active CURRENT has
        # already advanced through a tested promotion transaction.
        if stored["current_id"] != "current-v2-156-160":
            original = next(item for item in stored["records"] if item["baseline_id"] == "current-v2-156-160")
            cls.current = {"schema_version": stored["schema_version"], "artifact_type": stored["artifact_type"],
                           "current_id": original["baseline_id"], "records": [copy.deepcopy(original)]}
        else:
            cls.current = stored

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
        # This checkout intentionally carries a product PROPOSED delta.  CURRENT
        # itself is verified against its recorded base when proposal mode is
        # active; the proposal verifier owns the exact delta proof.
        self.assertEqual(validate_current(self.current, ROOT, {}), [])
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

    def test_promoted_current_history_hash_matches_written_bytes(self):
        proposal = self.proposal()
        result = next_current(self.current, proposal, "owner-ref", previous_current_path="state/history.json")
        expected = json.dumps(self.current, ensure_ascii=False, sort_keys=True, indent=2).encode() + b"\n"
        self.assertEqual(result["records"][-1]["historical_predecessors"][0]["sha256"],
                         hashlib.sha256(expected).hexdigest())

    def test_promoted_current_exactly_supersedes_hash_closed_history(self):
        prior = copy.deepcopy(self.current)
        active = prior["records"][0]
        governed = active["governed_files"][0]
        actual = hashlib.sha256((ROOT / governed["path"]).read_bytes()).hexdigest()
        proposal = self.proposal()
        proposal["delta"] = [{"path": governed["path"], "before_sha256": governed["sha256"], "after_sha256": actual}]
        historical = {"implementation": [{"path": governed["path"], "sha256": governed["sha256"]}]}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / "state").mkdir()
            r12 = root / "state/r12.json"; r12.write_text(json.dumps(historical))
            active["historical_predecessors"] = [{"path": "state/r12.json", "sha256": hashlib.sha256(r12.read_bytes()).hexdigest()}]
            result = next_current(prior, proposal, "owner-ref", previous_current_path="state/history.json")
            history = root / "state/history.json"
            history.write_text(json.dumps(prior, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
            self.assertTrue(_promoted_current_v2_supersedes_historical_hash(
                result, root, governed["path"], governed["sha256"], actual))

    def test_branch_name_and_generic_technical_claim_are_not_authority_fields(self):
        proposal = self.proposal(); proposal["branch"] = "main"
        self.assertIn("PROPOSED baseline fields are invalid", validate_proposal(proposal, self.current, ROOT))
        current = copy.deepcopy(self.current); current["records"][0]["acceptance"]["decision"] = "TECHNICAL_GREEN"
        self.assertIn("CURRENT v2 acceptance is not an explicit scoped owner decision", validate_current(current, ROOT))

    def test_promotion_material_requires_exact_head_and_real_bound_artifacts(self):
        errors = verify_promotion_material(self.proposal(), ROOT)
        self.assertIn("promotion source/overlay lineage is invalid", errors)
        self.assertEqual(errors, ["promotion source/overlay lineage is invalid"])


class ProposedOverlayLineageTests(unittest.TestCase):
    """Anti-bypass contract for CURRENT → A → B → declaration lineage."""

    def _git(self, root, *args):
        return subprocess.run(["git", "-C", str(root), *args], check=True,
                              capture_output=True, text=True).stdout.strip()

    def _commit(self, root, message):
        self._git(root, "add", ".")
        self._git(root, "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                  "commit", "-m", message)
        return self._git(root, "rev-parse", "HEAD")

    def _lineage(self, *, overlay_product=False):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self._git(root, "init", "-q")
        (root / "integra_core").mkdir(); (root / "state").mkdir()
        product = root / "integra_core/runtime.py"; product.write_text("base\n")
        base = self._commit(root, "base")
        product.write_text("recovery\n")
        source = self._commit(root, "product A")
        source_id = {"commit_sha": source, "tree_sha": self._git(root, "rev-parse", "HEAD^{tree}")}
        (root / "docs").mkdir(); (root / "docs/evidence").mkdir()
        manifest = {
            "candidate_id": "candidate-v1-" + "a" * 64,
            "identity_sha256": "a" * 64,
            "bundle": {"digest": "b" * 64},
            "identity": {"source": {**source_id, "dirty": False}},
        }
        manifest_path = root / "docs/evidence/manifest.json"; manifest_path.write_text(json.dumps(manifest))
        evidence = {"candidate_id": manifest["candidate_id"], "manifest_identity_sha256": "a" * 64,
                    "bundle_digest": "b" * 64, "product_source": source_id}
        evidence_path = root / "docs/evidence/evidence.json"; evidence_path.write_text(json.dumps(evidence))
        report_path = root / "docs/report.json"; report_path.write_text("{}")
        if overlay_product:
            product.write_text("hidden overlay product change\n")
        overlay = self._commit(root, "evidence B")
        overlay_id = {"commit_sha": overlay, "tree_sha": self._git(root, "rev-parse", "HEAD^{tree}")}
        before = hashlib.sha256(b"base\n").hexdigest()
        after = hashlib.sha256(b"recovery\n").hexdigest()
        proposal = {
            "schema_version": "1.0", "artifact_type": "integra.proposed_product_baseline",
            "proposal_id": "test", "status": "PROPOSED_BASELINE_VALID",
            "base_current_id": "current-test", "base_main": {"commit_sha": base, "tree_sha": self._git(root, "rev-parse", f"{base}^{{tree}}")},
            "proposed_source": source_id, "proposed_head": overlay_id,
            "intended_scope": {"wp": "test", "journey": "test"},
            "candidate": {"candidate_id": manifest["candidate_id"], "identity_sha256": "a" * 64,
                          "manifest_digest": hashlib.sha256(manifest_path.read_bytes()).hexdigest(), "bundle_digest": "b" * 64},
            "delta": [{"path": "integra_core/runtime.py", "before_sha256": before, "after_sha256": after}],
            "gates": [{"name": "candidate", "result": "PASS", "evidence_ref": "docs/report.json"}],
            "evidence": {"candidate_manifest": {"path": "docs/evidence/manifest.json", "sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest()},
                         "candidate_evidence": {"path": "docs/evidence/evidence.json", "sha256": hashlib.sha256(evidence_path.read_bytes()).hexdigest()},
                         "report": {"path": "docs/report.json", "sha256": hashlib.sha256(report_path.read_bytes()).hexdigest()}},
            "owner_acceptance": None,
            "allowed_overlay_paths": ["docs/evidence/manifest.json", "docs/evidence/evidence.json", "docs/report.json"],
        }
        proposal_path = root / "state/proposal.json"; proposal_path.write_text(json.dumps(proposal))
        self._commit(root, "proposal declaration")
        return root, proposal, proposal_path

    def test_valid_product_source_and_evidence_overlay_pass(self):
        root, proposal, path = self._lineage()
        self.assertEqual(verify_promotion_material(proposal, root, path), [])

    def test_product_byte_in_overlay_fails(self):
        root, proposal, path = self._lineage(overlay_product=True)
        self.assertIn("promotion evidence overlay contains product/runtime bytes",
                      verify_promotion_material(proposal, root, path))

    def test_candidate_source_and_stale_evidence_fail(self):
        root, proposal, path = self._lineage()
        manifest = root / "docs/evidence/manifest.json"
        data = json.loads(manifest.read_text()); data["identity"]["source"]["commit_sha"] = "0" * 40
        manifest.write_text(json.dumps(data))
        self.assertIn("promotion candidate manifest does not bind PROPOSED candidate/bundle",
                      verify_promotion_material(proposal, root, path))
        # A changed evidence blob cannot silently retain its recorded digest.
        evidence = root / "docs/evidence/evidence.json"; evidence.write_text("{}")
        self.assertIn("promotion candidate evidence does not bind PROPOSED candidate/bundle",
                      verify_promotion_material(proposal, root, path))


if __name__ == "__main__":
    unittest.main()
