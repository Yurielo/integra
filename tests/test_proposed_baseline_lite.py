"""Anti-bypass regressions for Issue #165 Proposed Baseline Lite."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import shutil
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
    _governed_product_path,
    proposal_supersedes_r9a_hash,
)
from validate_governance import (  # noqa: E402
    _promoted_current_v2_supersedes_historical_hash,
    validate_native_macos_app_evidence,
    validate_ready_app_evidence,
    validate_knowledge_integration_evidence,
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
        self.assertIn("PROPOSED baseline pilot acceptance is invalid", validate_proposal(proposal, self.current, ROOT))
        with self.assertRaisesRegex(ValueError, "explicit owner acceptance reference"):
            next_current(self.current, self.proposal(), "", previous_current_path="state/history.json")

    def test_pilot_acceptance_is_not_current_promotion(self):
        proposal = self.proposal()
        proposal["owner_acceptance"] = {
            "decision": "PILOT_ACCEPTED",
            "authority_ref": "Product Owner test authority",
            "scope": "bounded pilot only",
            "promotion_authorized": False,
        }
        self.assertEqual(validate_proposal(proposal, self.current, ROOT), [])
        state, errors = proposal_state(proposal, self.current, ROOT)
        self.assertEqual(errors, [])
        self.assertEqual(state, "PILOT_ACCEPTED / AWAITING_CURRENT_PROMOTION_AUTHORIZATION")
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
                 extra_historical_test_drift=False, declare_historical_test_successor=False,
                 base_setup=None, source_setup=None, extra_delta=None):
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
        if base_setup:
            base_setup(root)
        base = self._commit(root, "base")
        base_id = {"commit_sha": base, "tree_sha": self._git(root, "rev-parse", f"{base}^{{tree}}")}
        stored = json.loads((ROOT / "state/current_product_baseline_v2.json").read_text())
        active = copy.deepcopy(stored["records"][0])
        active.update({"baseline_id": "current-test", "main": base_id,
                       "governed_files": [{"path": "integra_core/runtime.py",
                                           "sha256": hashlib.sha256(b"base\n").hexdigest()}],
                       "historical_predecessors": [{"path": "state/native_macos_app_v1.json",
                                                   "sha256": hashlib.sha256((root / "state/native_macos_app_v1.json").read_bytes()).hexdigest()}]})
        current = {"schema_version": "2.0", "artifact_type": "integra.current_product_baseline",
                   "current_id": "current-test", "records": [active]}
        (root / "state/current_product_baseline_v2.json").write_text(json.dumps(current))
        product.write_text("recovery\n")
        if source_setup:
            source_setup(root)
        if historical_test_drift:
            historical_test.write_text("new\n")
        if extra_historical_test_drift:
            second_historical_test.write_text("new-other\n")
        source = self._commit(root, "product A")
        source_id = {"commit_sha": source, "tree_sha": self._git(root, "rev-parse", "HEAD^{tree}")}
        (root / "docs").mkdir(exist_ok=True); (root / "docs/evidence").mkdir()
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
            "base_current_id": "current-test", "base_main": base_id,
            "proposed_source": source_id, "proposed_head": overlay_id,
            "intended_scope": {"wp": "test", "journey": "test"},
            "candidate": {"candidate_id": manifest["candidate_id"], "identity_sha256": "a" * 64,
                          "manifest_digest": hashlib.sha256(manifest_path.read_bytes()).hexdigest(), "bundle_digest": "b" * 64},
            "delta": [{"path": "integra_core/runtime.py", "before_sha256": before, "after_sha256": after}] + (extra_delta or []),
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

    def _r9a_lineage(self):
        stored = json.loads((ROOT / "state/current_product_baseline_v2.json").read_bytes())
        base_commit = next(item for item in stored["records"] if item["baseline_id"] == stored["current_id"])["main"]["commit_sha"]
        original = json.loads((ROOT / "state/knowledge_integration_v1.json").read_bytes())
        delta = []

        def base_setup(root):
            for path in ["state/knowledge_integration_v1.json"] + [item["path"] for item in original["implementation"]]:
                target = root / path; target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(subprocess.run(["git", "-C", str(ROOT), "show", f"{base_commit}:{path}"],
                    check=True, capture_output=True).stdout)

        def source_setup(root):
            for path, suffix in (("integra_core/knowledge.py", b"\n# Synthetic K2 successor\n"),
                                 ("schemas/knowledge_view_v1.schema.json", b"\n")):
                target = root / path; before = target.read_bytes(); after = before + suffix
                target.write_bytes(after)
                delta.append({"path": path, "before_sha256": hashlib.sha256(before).hexdigest(), "after_sha256": hashlib.sha256(after).hexdigest()})

        root, proposal, path = self._lineage(base_setup=base_setup, source_setup=source_setup, extra_delta=delta)
        current = json.loads((root / "state/current_product_baseline_v2.json").read_bytes())
        baselines = json.loads((ROOT / "state/component_baselines_v1.json").read_bytes())
        return root, proposal, path, current, original, baselines

    def _r9a_next(self, root, proposal, current):
        result = next_current(current, proposal, "Synthetic owner reference for tests only",
            previous_current_path="state/history-r9a.json", root=root)
        (root / "state/history-r9a.json").write_text(json.dumps(current, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
        return result

    def test_r9a_exact_proposed_and_promoted_successor_preserve_historical_authority(self):
        root, proposal, path, current, evidence, baselines = self._r9a_lineage()
        original_bytes = (root / "state/knowledge_integration_v1.json").read_bytes()
        original_current = (root / "state/current_product_baseline_v2.json").read_bytes()
        self.assertEqual(verify_promotion_material(proposal, root, path), [])
        self.assertEqual(validate_knowledge_integration_evidence(evidence, baselines, root,
            proposal=proposal, current_product_baseline=current), [])
        result = self._r9a_next(root, proposal, current)
        predecessors = result["records"][-1]["historical_predecessors"]
        self.assertEqual(predecessors[0]["path"], "state/history-r9a.json")
        self.assertIn({"path": "state/knowledge_integration_v1.json", "sha256": hashlib.sha256(original_bytes).hexdigest()}, predecessors)
        self.assertEqual(validate_current(result, root), [])
        self.assertEqual(validate_knowledge_integration_evidence(evidence, baselines, root, current_product_baseline=result), [])
        self.assertEqual((root / "state/knowledge_integration_v1.json").read_bytes(), original_bytes)
        self.assertEqual((root / "state/current_product_baseline_v2.json").read_bytes(), original_current)

    def test_r9a_undeclared_delta_wrong_before_after_and_current_forgery_fail_closed(self):
        root, proposal, _, current, evidence, baselines = self._r9a_lineage()
        for changed in (None, {**proposal, "delta": []}):
            self.assertTrue(validate_knowledge_integration_evidence(evidence, baselines, root,
                proposal=changed, current_product_baseline=current))
        for field in ("before_sha256", "after_sha256"):
            altered = copy.deepcopy(proposal); altered["delta"][1][field] = "0" * 64
            errors = validate_knowledge_integration_evidence(evidence, baselines, root,
                proposal=altered, current_product_baseline=current)
            self.assertIn("R9A implementation hash differs: integra_core/knowledge.py", errors)
        forged = copy.deepcopy(current); forged["records"][0]["main"]["tree_sha"] = "0" * 40
        self.assertTrue(validate_knowledge_integration_evidence(evidence, baselines, root,
            proposal=proposal, current_product_baseline=forged))
        result = self._r9a_next(root, proposal, current)
        wrong_main = copy.deepcopy(result); wrong_main["records"][-1]["main"] = proposal["base_main"]
        self.assertTrue(validate_knowledge_integration_evidence(evidence, baselines, root, current_product_baseline=wrong_main))
        result["records"][-1]["acceptance"]["decision"] = "TECHNICAL_GREEN"
        self.assertTrue(validate_knowledge_integration_evidence(evidence, baselines, root, current_product_baseline=result))

    def test_r9a_mutable_historical_forgery_and_missing_chain_are_rejected(self):
        root, proposal, _, current, evidence, baselines = self._r9a_lineage()
        result = self._r9a_next(root, proposal, current)
        result["records"][-1]["historical_predecessors"] = result["records"][-1]["historical_predecessors"][:1]
        self.assertTrue(validate_knowledge_integration_evidence(evidence, baselines, root, current_product_baseline=result))
        forged = copy.deepcopy(evidence); forged["limitations"] = ["Forged historical authority"]
        (root / "state/knowledge_integration_v1.json").write_text(json.dumps(forged))
        self.assertTrue(validate_knowledge_integration_evidence(forged, baselines, root,
            proposal=proposal, current_product_baseline=current))
        with self.assertRaisesRegex(ValueError, "immutable base commit"):
            self._r9a_next(root, proposal, current)

    def test_r9a_next_current_wrong_historical_before_hash_is_rejected(self):
        root, proposal, _, current, _, _ = self._r9a_lineage()
        original = copy.deepcopy(proposal)
        proposal["delta"][1]["before_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "immutable base"):
            self._r9a_next(root, proposal, current)
        original["delta"][1]["after_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "declared source"):
            self._r9a_next(root, original, current)

    def test_r9a_future_successor_retains_prior_current_chain(self):
        root, proposal, _, current, evidence, baselines = self._r9a_lineage()
        first = self._r9a_next(root, proposal, current)
        product = root / "integra_core/knowledge.py"; before = hashlib.sha256(product.read_bytes()).hexdigest()
        product.write_bytes(product.read_bytes() + b"\n# Synthetic next revision\n")
        head = self._commit(root, "synthetic future source")
        future = copy.deepcopy(proposal)
        future.update(base_current_id=first["current_id"], base_main=first["records"][-1]["main"],
                      proposed_source={"commit_sha": head, "tree_sha": self._git(root, "rev-parse", "HEAD^{tree}")},
                      proposed_head={"commit_sha": head, "tree_sha": self._git(root, "rev-parse", "HEAD^{tree}")})
        future["candidate"]["identity_sha256"] = "c" * 64; future["candidate"]["candidate_id"] = "candidate-v1-" + "c" * 64
        future["delta"] = [{"path": "integra_core/knowledge.py", "before_sha256": before,
                            "after_sha256": hashlib.sha256(product.read_bytes()).hexdigest()}]
        second = next_current(first, future, "Synthetic future owner", previous_current_path="state/history-r9a-next.json", root=root)
        (root / "state/history-r9a-next.json").write_text(json.dumps(first, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
        self.assertEqual(len(second["records"][-1]["historical_predecessors"]), 1)
        self.assertEqual(validate_current(second, root), [])
        self.assertEqual(validate_knowledge_integration_evidence(evidence, baselines, root, current_product_baseline=second), [])

    def test_k2_governed_scope_additions_are_exact_not_broad_schema_or_state_exemptions(self):
        for path in ("schemas/knowledge_view_v1.schema.json", "state/knowledge_admission_component_v1.json", "scripts/package_knowledge_admission_runtime.py"):
            self.assertTrue(_governed_product_path(path), path)
        for path in ("schemas/arbitrary.schema.json", "state/knowledge_integration_v1.json", "scripts/arbitrary.py"):
            self.assertFalse(_governed_product_path(path), path)

    def test_acceptance_lineage_survives_merge_without_proposal_change(self):
        root, proposal, path = self._lineage()
        accepted = copy.deepcopy(proposal)
        accepted["owner_acceptance"] = {
            "decision": "PILOT_ACCEPTED", "authority_ref": "Product Owner test authority",
            "scope": "bounded pilot only", "promotion_authorized": False,
        }
        path.write_text(json.dumps(accepted))
        self._commit(root, "pilot acceptance")
        self._git(root, "branch", "integration")
        self._git(root, "checkout", "-q", "-b", "authority")
        (root / "docs" / "authority.txt").write_text("canonical authority\n")
        self._commit(root, "authority integration")
        self._git(root, "checkout", "-q", "integration")
        self._git(root, "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                  "merge", "--no-ff", "authority", "-m", "merge authority")
        self.assertEqual(verify_promotion_material(accepted, root, path), [])

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

    def _entry(self, root, path, kind):
        target = root / path
        if target.is_symlink() or target.is_file():
            target.unlink()
        elif target.is_dir():
            shutil.rmtree(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        if kind == "absent":
            return
        if kind == "symlink":
            target.symlink_to("runtime.py")
        elif kind in {"directory", "gitlink"}:
            target.mkdir()
            (target / "child.py").write_bytes(b"new\x00bytes\n")
            if kind == "gitlink":
                self._git(target, "init", "-q")
                self._commit(target, "nested repository")
        else:
            target.write_bytes(b"new\x00bytes\n")
            target.chmod(0o755 if kind == "executable" else 0o644)

    def _addition_lineage(self, *, path="integra_core/new.py", base_kind="absent", after_kind="regular"):
        delta = {"path": path, "before_sha256": None,
                 "after_sha256": hashlib.sha256(b"new\x00bytes\n").hexdigest()}
        return self._lineage(base_setup=lambda root: self._entry(root, path, base_kind),
                             source_setup=lambda root: self._entry(root, path, after_kind),
                             extra_delta=[delta])

    def _current(self, root):
        return json.loads((root / "state/current_product_baseline_v2.json").read_text())

    def _assert_addition_rejected(self, root, proposal, path, current=None):
        current = self._current(root) if current is None else current
        self.assertTrue(validate_proposal(proposal, current, root))
        self.assertTrue(verify_promotion_material(proposal, root, path))
        with self.assertRaises(ValueError):
            next_current(current, proposal, "fixture-owner-only", previous_current_path="state/history.json", root=root)

    def test_regular_and_executable_additions_pass_entire_chain_without_writes(self):
        for kind in ("regular", "executable"):
            with self.subTest(kind=kind):
                root, proposal, path = self._addition_lineage(after_kind=kind)
                current = self._current(root)
                prior = copy.deepcopy(current)
                current_path = root / "state/current_product_baseline_v2.json"
                before_bytes = current_path.read_bytes()
                before_head = self._git(root, "rev-parse", "HEAD")
                self.assertEqual(validate_current(current, root, proposal), [])
                self.assertEqual(validate_proposal(proposal, current, root), [])
                self.assertEqual(verify_promotion_material(proposal, root, path), [])
                self.assertIn("CURRENT v2 unaccounted governed path: integra_core/new.py",
                              validate_current(current, root))
                result = next_current(current, proposal, "fixture-owner-only",
                                      previous_current_path="state/history.json", root=root)
                inventory = {item["path"]: item["sha256"] for item in result["records"][-1]["governed_files"]}
                self.assertEqual(inventory, {item["path"]: item["after_sha256"] for item in proposal["delta"]})
                self.assertEqual(result["records"][-1]["main"], proposal["proposed_head"])
                self.assertEqual(current, prior)
                self.assertEqual(current_path.read_bytes(), before_bytes)
                self.assertFalse((root / "state/history.json").exists())
                self.assertEqual(self._git(root, "rev-parse", "HEAD"), before_head)
                self.assertEqual(self._git(root, "status", "--porcelain"), "")

    def test_addition_paths_are_literal_including_git_pathspec_characters(self):
        for path in ("integra_core/new [a]*?.py", "integra_core/:(glob)new.py", "integra_core/nested/new.py"):
            with self.subTest(path=path):
                root, proposal, declaration = self._addition_lineage(path=path)
                self.assertEqual(validate_proposal(proposal, self._current(root), root), [])
                self.assertEqual(verify_promotion_material(proposal, root, declaration), [])

    def test_malformed_addition_deltas_fail_all_entry_points(self):
        root, proposal, path = self._addition_lineage()
        item = proposal["delta"][-1]
        bad_deltas = [None, {}, [], [None], ["unknown"],
                      [{**item, "unknown": True}], [{key: value for key, value in item.items() if key != "before_sha256"}],
                      [{**item, "before_sha256": ""}], [{**item, "before_sha256": False}],
                      [{**item, "after_sha256": None}], [{**item, "after_sha256": ""}],
                      [{**item, "after_sha256": 1}], [item, copy.deepcopy(item)]]
        for bad in bad_deltas:
            with self.subTest(delta=bad):
                changed = copy.deepcopy(proposal); changed["delta"] = bad
                self._assert_addition_rejected(root, changed, path)
        for bad in ("", "/integra_core/new.py", "integra_core//new.py", "integra_core/./new.py",
                    "integra_core/../new.py", "integra_core/new.py/", "integra_core\\new.py", "integra_core/new\n.py", None, []):
            with self.subTest(path=bad):
                changed = copy.deepcopy(proposal); changed["delta"][-1]["path"] = bad
                self._assert_addition_rejected(root, changed, path)

    def test_forged_absence_existing_in_base_but_not_inventory_fails(self):
        root, proposal, path = self._addition_lineage(base_kind="regular")
        self.assertNotIn("integra_core/new.py", [item["path"] for item in self._current(root)["records"][0]["governed_files"]])
        self._assert_addition_rejected(root, proposal, path)

    def test_forged_absence_existing_in_inventory_but_not_base_fails(self):
        root, proposal, path = self._addition_lineage()
        current = self._current(root)
        current["records"][0]["governed_files"].append({"path": "integra_core/new.py", "sha256": "a" * 64})
        (root / "state/current_product_baseline_v2.json").write_text(json.dumps(current))
        self._assert_addition_rejected(root, proposal, path, current)

    def test_nonregular_base_and_after_entries_are_not_additions(self):
        for side in ("base_kind", "after_kind"):
            for kind in ("directory", "symlink", "gitlink"):
                with self.subTest(side=side, kind=kind):
                    root, proposal, path = self._addition_lineage(**{side: kind})
                    self._assert_addition_rejected(root, proposal, path)

    def test_non_tree_ancestor_is_not_absence(self):
        for kind in ("regular", "symlink", "gitlink"):
            with self.subTest(kind=kind):
                def base_setup(root):
                    self._entry(root, "integra_core/parent", kind)

                def source_setup(root):
                    self._entry(root, "integra_core/parent", "absent")
                    self._entry(root, "integra_core/parent/new.py", "regular")

                root, proposal, path = self._lineage(base_setup=base_setup, source_setup=source_setup,
                    extra_delta=[{"path": "integra_core/parent/new.py", "before_sha256": None,
                                  "after_sha256": hashlib.sha256(b"new\x00bytes\n").hexdigest()}])
                self._assert_addition_rejected(root, proposal, path)

    def test_missing_or_mismatched_git_identities_do_not_prove_absence(self):
        root, proposal, path = self._addition_lineage()
        for identity in ("base_main", "proposed_source"):
            for field, value in (("commit_sha", "0" * 40), ("commit_sha", "HEAD"),
                                 ("commit_sha", proposal["proposed_source"]["tree_sha"]),
                                 ("tree_sha", "0" * 40)):
                with self.subTest(identity=identity, field=field, value=value):
                    changed = copy.deepcopy(proposal); changed[identity][field] = value
                    current = self._current(root)
                    if identity == "base_main":
                        current["records"][0]["main"] = changed[identity]
                    self._assert_addition_rejected(root, changed, path, current)
        changed = copy.deepcopy(proposal); changed["base_main"] = None
        self._assert_addition_rejected(root, changed, path)

    def test_missing_current_and_invalid_inventory_cannot_authorize_addition(self):
        root, proposal, path = self._addition_lineage()
        original = self._current(root)
        for inventory in (None, [], [{}], [original["records"][0]["governed_files"][0]] * 2):
            with self.subTest(inventory=inventory):
                current = copy.deepcopy(original); current["records"][0]["governed_files"] = inventory
                (root / "state/current_product_baseline_v2.json").write_text(json.dumps(current))
                self._assert_addition_rejected(root, proposal, path, current)
        (root / "state/current_product_baseline_v2.json").unlink()
        self.assertTrue(verify_promotion_material(proposal, root, path))

    def test_wrong_after_hash_and_missing_after_blob_fail(self):
        root, proposal, path = self._addition_lineage()
        proposal["delta"][-1]["after_sha256"] = "0" * 64
        self._assert_addition_rejected(root, proposal, path)
        root, proposal, path = self._addition_lineage(after_kind="absent")
        self._assert_addition_rejected(root, proposal, path)

    def test_unreadable_base_tree_or_source_blob_is_not_absence(self):
        for side, suffix in (("base_main", "integra_core"), ("proposed_source", "integra_core/new.py")):
            with self.subTest(side=side):
                root, proposal, path = self._addition_lineage()
                object_id = self._git(root, "rev-parse", f"{proposal[side]['commit_sha']}:{suffix}")
                (root / ".git/objects" / object_id[:2] / object_id[2:]).unlink()
                self._assert_addition_rejected(root, proposal, path)

    def test_rename_cannot_hide_unsupported_deletion(self):
        def source_setup(root):
            # Identical bytes make Git's default rename detection applicable.
            (root / "integra_core/runtime.py").write_bytes(b"base\n")
            (root / "integra_core/runtime.py").rename(root / "integra_core/renamed.py")

        root, proposal, path = self._lineage(source_setup=source_setup,
            extra_delta=[{"path": "integra_core/renamed.py", "before_sha256": None,
                          "after_sha256": hashlib.sha256(b"base\n").hexdigest()}])
        proposal["delta"].pop(0)
        self.assertIn("promotion governed CURRENT-to-source delta is undeclared or overstated",
                      verify_promotion_material(proposal, root, path))

    def test_omitted_addition_and_deletion_remain_unaccounted(self):
        root, proposal, path = self._addition_lineage()
        proposal["delta"].pop()
        self.assertIn("promotion governed CURRENT-to-source delta is undeclared or overstated",
                      verify_promotion_material(proposal, root, path))
        root, proposal, path = self._lineage(source_setup=lambda root: (root / "integra_core/runtime.py").unlink())
        self.assertIn("promotion declared delta differs: integra_core/runtime.py",
                      verify_promotion_material(proposal, root, path))
        proposal["delta"][0]["after_sha256"] = None
        self._assert_addition_rejected(root, proposal, path)


if __name__ == "__main__":
    unittest.main()
