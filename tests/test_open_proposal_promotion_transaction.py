"""Unit coverage for the generic open-proposal promotion state machine."""
from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

from scripts import open_proposal_promotion_transaction as tx


CID_A = "candidate-v1-" + "a" * 64
CID_B = "candidate-v1-" + "b" * 64


def candidate(cid: str, bundle: str, manifest: str) -> dict:
    return {"candidate_id": cid, "bundle_digest": bundle * 64, "manifest_digest": manifest * 64}


class OpenProposalTransactionTests(unittest.TestCase):
    def setUp(self):
        self.target = candidate(CID_B, "2", "3")
        self.other = candidate(CID_A, "4", "5")
        self.proposal = {"proposal_id": "proposal-fixture", "candidate": self.target}
        self.registry = {"proposed": [{"pr": 19, "head_sha": "1" * 40, **self.other}],
                         "selected_survivors": {CID_A: "Validation/other"}}

    def test_01_pre_state_adds_only_target(self):
        virtual = tx._virtual_pre_registry(self.registry, self.proposal, 22, "6" * 40)
        self.assertEqual({row["pr"] for row in virtual["proposed"]}, {19, 22})
        self.assertEqual(self.registry["proposed"], [{"pr": 19, "head_sha": "1" * 40, **self.other}])

    def test_02_pre_state_preserves_unrelated_selector(self):
        virtual = tx._virtual_pre_registry(self.registry, self.proposal, 22, "6" * 40)
        self.assertEqual(virtual["selected_survivors"][CID_A], "Validation/other")

    def test_03_target_selector_is_candidate_bound(self):
        virtual = tx._virtual_pre_registry(self.registry, self.proposal, 22, "6" * 40)
        self.assertIn(CID_B, virtual["selected_survivors"])
        self.assertIn(CID_B, virtual["selected_survivors"][CID_B])

    def test_04_exact_registered_target_is_preserved(self):
        self.registry["proposed"].append({"pr": 22, "path": tx.PROPOSAL,
                                           "proposal_id": self.proposal["proposal_id"],
                                           "proposal_sha256": tx.digest(self.proposal), **self.target})
        virtual = tx._virtual_pre_registry(self.registry, self.proposal, 22, "6" * 40)
        self.assertEqual(len([row for row in virtual["proposed"] if row["pr"] == 22]), 1)
        self.assertEqual(virtual["proposed"][-1]["proposal_sha256"], tx.digest(self.proposal))

    def test_04a_registered_target_uses_immutable_file_digest_when_supplied(self):
        file_digest = "9" * 64
        self.registry["proposed"].append({"pr": 22, "path": tx.PROPOSAL,
                                           "proposal_id": self.proposal["proposal_id"],
                                           "proposal_sha256": file_digest, **self.target})
        virtual = tx._virtual_pre_registry(self.registry, self.proposal, 22, "6" * 40,
                                            proposal_sha256=file_digest)
        self.assertEqual(virtual["proposed"][-1]["proposal_sha256"], file_digest)

    def test_04b_partial_registered_target_is_rejected(self):
        self.registry["proposed"].append({"pr": 22, "head_sha": "6" * 40, **self.target})
        with self.assertRaisesRegex(ValueError, "binding differs"):
            tx._virtual_pre_registry(self.registry, self.proposal, 22, "6" * 40)

    def test_05_authorization_requires_promotion_token(self):
        with self.assertRaises(ValueError): tx._authority("nothing", self.proposal)

    def test_06_authorization_requires_proposal_identity(self):
        with self.assertRaises(ValueError): tx._authority("PROMOTE_CURRENT " + CID_B, self.proposal)

    def test_07_authorization_requires_candidate_identity(self):
        with self.assertRaises(ValueError): tx._authority("PROMOTE_CURRENT proposal-fixture", self.proposal)

    def test_08_exact_authorization_is_accepted(self):
        value = "PROMOTE_CURRENT proposal-fixture " + CID_B
        self.assertEqual(tx._authority(value, self.proposal), value)

    def test_09_paths_are_deterministic(self):
        self.assertEqual(tx._paths(self.proposal), tx._paths(copy.deepcopy(self.proposal)))

    def test_10_paths_do_not_contain_pr_number_special_case(self):
        self.assertNotIn("222", " ".join(tx._paths(self.proposal).values()))

    def test_11_pre_registry_does_not_mutate_input(self):
        before = copy.deepcopy(self.registry)
        tx._virtual_pre_registry(self.registry, self.proposal, 22, "6" * 40)
        self.assertEqual(self.registry, before)

    def test_12_wrong_target_head_changes_only_virtual_reference(self):
        first = tx._virtual_pre_registry(self.registry, self.proposal, 22, "6" * 40)
        second = tx._virtual_pre_registry(self.registry, self.proposal, 22, "7" * 40)
        self.assertNotEqual(first["proposed"][-1]["head_sha"], second["proposed"][-1]["head_sha"])

    def test_13_unrelated_proposal_remains(self):
        virtual = tx._virtual_pre_registry(self.registry, self.proposal, 22, "6" * 40)
        self.assertEqual(virtual["proposed"][0]["candidate_id"], CID_A)

    def test_14_candidate_archive_path_includes_bundle(self):
        virtual = tx._virtual_pre_registry(self.registry, self.proposal, 22, "6" * 40)
        self.assertIn("2" * 64, virtual["selected_survivors"][CID_B])

    def test_15_candidate_archive_path_is_not_empty(self):
        virtual = tx._virtual_pre_registry(self.registry, self.proposal, 22, "6" * 40)
        self.assertTrue(virtual["selected_survivors"][CID_B])

    def test_16_candidate_identity_is_copied(self):
        virtual = tx._virtual_pre_registry(self.registry, self.proposal, 22, "6" * 40)
        self.proposal["candidate"]["bundle_digest"] = "x" * 64
        self.assertEqual(virtual["proposed"][-1]["bundle_digest"], "2" * 64)

    def test_17_transaction_id_is_bound_to_authorization(self):
        first = tx.digest({"authorization": "PROMOTE_CURRENT proposal-fixture " + CID_B})
        second = tx.digest({"authorization": "PROMOTE_CURRENT proposal-fixture " + CID_A})
        self.assertNotEqual(first, second)

    def test_18_transaction_id_is_deterministic(self):
        self.assertEqual(tx.digest({"x": 1}), tx.digest({"x": 1}))

    def test_19_transaction_id_is_not_a_git_head(self):
        self.assertNotEqual(tx.digest({"x": 1}), "6" * 40)

    def test_20_no_global_audit_policy_is_changed(self):
        self.assertEqual(tx.protection._validate_registry.__module__, "scripts.candidate_protection_audit")


if __name__ == "__main__":
    unittest.main()
