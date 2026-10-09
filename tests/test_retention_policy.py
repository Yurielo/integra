import copy
import json
from pathlib import Path
import unittest

from scripts.validate_retention_policy import validate


class StandingPolicyContractTests(unittest.TestCase):
    def setUp(self):
        self.policy = json.loads((Path(__file__).resolve().parents[1] /
            'state/candidate_lifecycle_retention_policy_v1.json').read_bytes())

    def test_complete_authorized_policy_validates(self):
        self.assertEqual(validate(self.policy), [])

    def test_predicate_removal_or_additional_authority_fails(self):
        for key in ('requires', 'does_not_authorize'):
            for operation in ('remove', 'duplicate'):
                value = copy.deepcopy(self.policy)
                if operation == 'remove': value[key].pop()
                else: value[key].append(value[key][0])
                with self.subTest(key=key, operation=operation): self.assertTrue(validate(value))

    def test_capacity_and_hold_changes_fail(self):
        for key in ('max_full_copies', 'max_attributed_bytes', 'minimum_free_after_reservations'):
            value = copy.deepcopy(self.policy); value[key] += 1
            with self.subTest(key=key): self.assertTrue(validate(value))
        value = copy.deepcopy(self.policy); value['absolute_hold_prefixes'].pop()
        self.assertTrue(validate(value))

    def test_missing_authority_and_unknown_fields_fail(self):
        for key in ('authority_ref', 'authority_payload_sha256'):
            value = copy.deepcopy(self.policy); value[key] = ''
            with self.subTest(key=key): self.assertTrue(validate(value))
        value = copy.deepcopy(self.policy); value['may_withdraw_acceptance'] = True
        self.assertTrue(validate(value))
