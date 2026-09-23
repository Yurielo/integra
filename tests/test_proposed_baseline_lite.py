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
from validate_governance import (  # noqa: E402
    _promoted_current_v2_supersedes_historical_hash,
    validate_native_macos_app_evidence,
    validate_ready_app_evidence,
)


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
            "historical_test_successors": [],
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

    def _r12_test_successor(self):
        return {
            "path": "tests/test_macos_app.py",
            "historical_authority": "R12",
            "before_sha256": "d85790e714fd7098c0b93082a093d231e981b5db5682cbc41477a7247ee0c584",
            "after_sha256": "ddb2ec1700a77abbe1a3efdda5c8f17927e85a543fb09fe6a891537bcc3fad17",
            "reason": "Approved Process result boundary removes downstream publication controls.",
        }

    def test_exact_r12_test_successor_is_accepted_but_wrong_authority_hashes_fail(self):
        proposal = self.proposal()
        proposal["historical_test_successors"] = [self._r12_test_successor()]
        self.assertEqual(validate_proposal(proposal, self.current, ROOT), [])
        proposal = self.proposal()
        successor = self._r12_test_successor(); successor["before_sha256"] = "0" * 64
        proposal["historical_test_successors"] = [successor]
        self.assertIn("PROPOSED historical test successor before hash differs from immutable authority",
                      validate_proposal(proposal, self.current, ROOT))
        proposal = self.proposal()
        successor = self._r12_test_successor(); successor["historical_authority"] = "R13"
        proposal["historical_test_successors"] = [successor]
        self.assertIn("PROPOSED historical test successor is not in immutable authority inventory",
                      validate_proposal(proposal, self.current, ROOT))

    def test_test_successor_cannot_authorize_wildcard_noninventory_or_executable_path(self):
        for path in ("tests/*.py", "tests/not-in-r12.py", "macos/IntegraApp.swift"):
            proposal = self.proposal()
            successor = self._r12_test_successor(); successor["path"] = path
            proposal["historical_test_successors"] = [successor]
            errors = validate_proposal(proposal, self.current, ROOT)
            self.assertTrue(any("historical test successor" in error for error in errors), path)

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

    def test_promoted_current_retains_exact_historical_test_successor(self):
        proposal = self.proposal()
        successor = self._r12_test_successor()
        proposal["historical_test_successors"] = [successor]
        result = next_current(self.current, proposal, "owner-ref", previous_current_path="state/history.json")
        governed = {item["path"]: item["sha256"] for item in result["records"][-1]["governed_files"]}
        self.assertEqual(governed[successor["path"]], successor["after_sha256"])

    def _sequential_current(self, governed):
        current = copy.deepcopy(self.current)
        active = current["records"][0]
        active["governed_files"] = [{"path": path, "sha256": value} for path, value in governed.items()]
        return current

    def _sequential_proposal(self, current, delta, identity):
        proposal = self.proposal()
        active = current["records"][0]
        proposal["base_current_id"] = active["baseline_id"]
        proposal["base_main"] = active["main"]
        proposal["candidate"] = {"candidate_id": "candidate-v1-" + identity * 64,
                                 "identity_sha256": identity * 64, "manifest_digest": "6" * 64,
                                 "bundle_digest": "4" * 64}
        proposal["delta"] = delta
        return proposal

    def test_sequential_promotion_accumulates_previous_and_new_governed_paths(self):
        current0 = self._sequential_current({"integra_core/a.py": "0" * 64})
        proposal1 = self._sequential_proposal(current0, [{"path": "integra_core/a.py", "before_sha256": "0" * 64, "after_sha256": "1" * 64}], "1")
        current1 = next_current(current0, proposal1, "owner-1", previous_current_path="state/current0.json")
        proposal2 = self._sequential_proposal(current1, [{"path": "integra_core/b.py", "before_sha256": "0" * 64, "after_sha256": "2" * 64}], "2")
        current2 = next_current(current1, proposal2, "owner-2", previous_current_path="state/current1.json")
        active = current2["records"][-1]
        self.assertEqual(active["governed_files"], [{"path": "integra_core/a.py", "sha256": "1" * 64},
                                                     {"path": "integra_core/b.py", "sha256": "2" * 64}])

    def test_sequential_promotion_replaces_existing_path_only_with_matching_current_hash(self):
        current1 = self._sequential_current({"integra_core/a.py": "1" * 64})
        proposal2 = self._sequential_proposal(current1, [{"path": "integra_core/a.py", "before_sha256": "1" * 64, "after_sha256": "2" * 64}], "2")
        current2 = next_current(current1, proposal2, "owner-2", previous_current_path="state/current1.json")
        self.assertEqual(current2["records"][-1]["governed_files"], [{"path": "integra_core/a.py", "sha256": "2" * 64}])
        proposal2["delta"][0]["before_sha256"] = "0" * 64
        self.assertIn("PROPOSED baseline delta does not start from active CURRENT hash", validate_proposal(proposal2, current1, ROOT))
        with self.assertRaisesRegex(ValueError, "does not start from active CURRENT hash"):
            next_current(current1, proposal2, "owner-2", previous_current_path="state/current1.json")

    def test_previously_governed_path_cannot_disappear_from_successor(self):
        current1 = self._sequential_current({"integra_core/a.py": "1" * 64})
        proposal2 = self._sequential_proposal(current1, [{"path": "integra_core/b.py", "before_sha256": "0" * 64, "after_sha256": "2" * 64}], "2")
        current2 = next_current(current1, proposal2, "owner-2", previous_current_path="state/current1.json")
        self.assertEqual({item["path"] for item in current2["records"][-1]["governed_files"]}, {"integra_core/a.py", "integra_core/b.py"})

    def test_historical_r12_r13_records_remain_unchanged_by_successor_generation(self):
        before = {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in
                  ("state/native_macos_app_v1.json", "state/ready_app_v1.json")}
        current = self._sequential_current({"integra_core/a.py": "1" * 64})
        proposal = self._sequential_proposal(current, [{"path": "integra_core/b.py", "before_sha256": "0" * 64, "after_sha256": "2" * 64}], "2")
        next_current(current, proposal, "owner", previous_current_path="state/current1.json")
        self.assertEqual(before, {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in before})

    def test_mutated_historical_r12_or_r13_evidence_is_not_accepted(self):
        r12 = json.loads((ROOT / "state/native_macos_app_v1.json").read_text())
        r12["implementation"][0]["sha256"] = "0" * 64
        self.assertTrue(validate_native_macos_app_evidence(r12, ROOT))
        r13 = json.loads((ROOT / "state/ready_app_v1.json").read_text())
        r13["implementation"][0]["sha256"] = "0" * 64
        self.assertTrue(validate_ready_app_evidence(r13, ROOT))

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

    def _lineage(self, *, overlay_product=False, historical_test_drift=False,
                 extra_historical_test_drift=False, declare_historical_test_successor=False):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self._git(root, "init", "-q")
        (root / "integra_core").mkdir(); (root / "state").mkdir(); (root / "tests").mkdir()
        product = root / "integra_core/runtime.py"; product.write_text("base\n")
        historical_test = root / "tests/historical.py"; historical_test.write_text("old\n")
        second_historical_test = root / "tests/other_historical.py"; second_historical_test.write_text("old-other\n")
        r12 = {"implementation": [
            {"path": "tests/historical.py", "sha256": hashlib.sha256(historical_test.read_bytes()).hexdigest()},
            {"path": "tests/other_historical.py", "sha256": hashlib.sha256(second_historical_test.read_bytes()).hexdigest()},
        ]}
        (root / "state/native_macos_app_v1.json").write_text(json.dumps(r12))
        base = self._commit(root, "base")
        product.write_text("recovery\n")
        if historical_test_drift:
            historical_test.write_text("new\n")
        if extra_historical_test_drift:
            second_historical_test.write_text("new-other\n")
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
            "historical_test_successors": ([{
                "path": "tests/historical.py", "historical_authority": "R12",
                "before_sha256": hashlib.sha256(b"old\n").hexdigest(),
                "after_sha256": hashlib.sha256(b"new\n").hexdigest(),
                "reason": "test-only successor",
            }] if declare_historical_test_successor else []),
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

    def test_undeclared_previously_governed_product_mutation_fails(self):
        root, proposal, path = self._lineage()
        proposal["delta"] = [{"path": "integra_core/other.py", "before_sha256": "0" * 64,
                              "after_sha256": "1" * 64}]
        self.assertIn("promotion governed CURRENT-to-source delta is undeclared or overstated",
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

    def test_exact_declared_historical_test_successor_passes(self):
        root, proposal, path = self._lineage(historical_test_drift=True,
                                             declare_historical_test_successor=True)
        self.assertEqual(verify_promotion_material(proposal, root, path), [])

    def test_historical_test_drift_without_successor_or_with_wrong_after_fails(self):
        root, proposal, path = self._lineage(historical_test_drift=True)
        self.assertIn("promotion historical test drift is undeclared or overstated",
                      verify_promotion_material(proposal, root, path))
        root, proposal, path = self._lineage(historical_test_drift=True,
                                             declare_historical_test_successor=True)
        proposal["historical_test_successors"][0]["after_sha256"] = "0" * 64
        self.assertIn("promotion historical test successor differs: tests/historical.py",
                      verify_promotion_material(proposal, root, path))

    def test_one_declared_historical_test_successor_cannot_hide_another_drift(self):
        root, proposal, path = self._lineage(historical_test_drift=True,
                                             extra_historical_test_drift=True,
                                             declare_historical_test_successor=True)
        self.assertIn("promotion historical test drift is undeclared or overstated",
                      verify_promotion_material(proposal, root, path))


if __name__ == "__main__":
    unittest.main()
