"""Pure canonical replay/retirement proof; no real archive or catalog access."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import candidate_lifecycle as lifecycle


class CandidateLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.identity = {'candidate_id': 'candidate-v1-' + 'a' * 64,
                         'bundle_digest': 'b' * 64, 'manifest_digest': 'c' * 64}
        self.snapshot = {'main_sha': 'd' * 40, 'registry_sha256': 'e' * 64}
        self.policy = {'status': 'PRODUCT_OWNER_AUTHORIZED_ACTIVE',
                       'authority_ref': 'exact Product Owner standing policy'}
        self.event = {**self.identity, 'immutable_history_complete': True,
                      'source': {'commit_sha': '1' * 40, 'tree_sha': '2' * 40},
                      'canonical_snapshot': self.snapshot,
                      'acceptance_refs': ['accepted exact Candidate'],
                      'promotion_refs': ['state/history/promotion.json'],
                      'proposal_refs': ['proposal-exact-a']}
        self.record = {**self.identity, 'status': 'AWAITING_OWNER_ACCEPTANCE',
                       'complete_sha256': 'f' * 64, 'inventory_sha256': '1' * 64}

    def replay(self, roles=()):
        return lifecycle.replay(self.record,
                                {self.identity['candidate_id']: self.event}, roles)

    def eligibility(self, record=None, roles=(), **overrides):
        args = dict(owned=True, integrity_verified=True, context_valid=True,
                    inactive=True, standing_policy=self.policy)
        args.update(overrides)
        return lifecycle.terminal_eligibility(self.identity, record or self.replay(),
                                               roles, **args)

    def test_stale_promoted_pending_is_reconciled_without_mutating_input(self):
        result = self.replay()
        self.assertEqual(result['status'], 'HISTORICAL_PROMOTED')
        self.assertEqual(self.record['status'], 'AWAITING_OWNER_ACCEPTANCE')
        self.assertEqual(result['lifecycle_evidence'], self.event)
        self.assertTrue(self.eligibility()['eligible'])

    def test_current_rollback_and_recovery_remain_protected(self):
        for role, state in [('CURRENT', 'CURRENT'), ('CONFIRMED_ROLLBACK', 'CONFIRMED_ROLLBACK'),
                            ('CONFIRMED_RECOVERY', 'CONFIRMED_RECOVERY')]:
            with self.subTest(role=role):
                result = self.replay([role])
                self.assertEqual(result['status'], state)
                self.assertFalse(self.eligibility(result, [role])['eligible'])

    def test_all_other_active_roles_protect_even_proven_historical_identity(self):
        for role in ['ACTIVE_PROPOSAL', 'ACCEPTED_UNPROMOTED', 'AWAITING_CURRENT_PROMOTION',
                     'UNRESOLVED_SUCCESSOR_TRANSACTION', 'HISTORICAL_GAP',
                     'EXPLICIT_GOVERNANCE_PROVENANCE', 'LATEST_ACCEPTED_BASELINE']:
            with self.subTest(role=role):
                result = self.replay([role])
                self.assertFalse(self.eligibility(result, [role])['eligible'])

    def test_unproved_pending_never_becomes_terminal_by_age_or_bundle(self):
        record = {**self.record, 'age': 100000, 'title': 'historical', 'path': '/archive/old'}
        self.assertEqual(lifecycle.replay(record, {}, [])['status'], 'AWAITING_OWNER_ACCEPTANCE')
        self.assertFalse(self.eligibility(record)['eligible'])

    def test_identity_bundle_and_manifest_substitution_cannot_replay(self):
        for key in lifecycle.IDENTITY:
            with self.subTest(key=key):
                event = {**self.event, key: ('candidate-v1-' if key == 'candidate_id' else '') + '9' * 64}
                record = lifecycle.replay(self.record, {self.record['candidate_id']: event}, [])
                self.assertEqual(record, self.record)
                self.assertFalse(self.eligibility(record)['eligible'])

    def test_unknown_integrity_activity_and_authority_each_fail_closed(self):
        for args in [{'owned': False}, {'integrity_verified': False},
                     {'inactive': False}, {'context_valid': False}, {'standing_policy': None}]:
            with self.subTest(args=args):
                self.assertFalse(self.eligibility(**args)['eligible'])

    def test_additional_obligations_each_fail_closed(self):
        for key in ['integrity_incident', 'pin_ref', 'unresolved_successor_transaction',
                    'historical_gap_obligation', 'required_rollback_or_recovery',
                    'sole_required_representation']:
            with self.subTest(key=key):
                self.assertFalse(self.eligibility({**self.replay(), key: True})['eligible'])

    def test_four_real_ambiguity_holds_are_absolute(self):
        for prefix in lifecycle.HOLDS:
            identity = {**self.identity, 'candidate_id': prefix + '0' * (77 - len(prefix))}
            evidence = {**self.event, **identity}
            record = {**self.record, **identity, 'status': 'HISTORICAL_PROMOTED',
                      'lifecycle_evidence': evidence}
            result = lifecycle.terminal_eligibility(identity, record, [], owned=True,
                integrity_verified=True, context_valid=True, inactive=True,
                standing_policy=self.policy)
            self.assertIn('EXPLICIT_TASK_HOLD', result['reasons'])

    def test_complete_immutable_history_is_required(self):
        for key in ['immutable_history_complete', 'canonical_snapshot', 'acceptance_refs',
                    'promotion_refs', 'proposal_refs']:
            with self.subTest(key=key):
                event = deepcopy(self.event); event.pop(key)
                record = {**self.replay(), 'lifecycle_evidence': event}
                self.assertFalse(self.eligibility(record)['eligible'])

    def test_exact_record_and_consumed_transaction_generate_replay_evidence(self):
        current = {'records': [{'baseline_id': 'current-v2-exact', 'candidate': self.identity,
                              'acceptance': {'decision': 'USER_ACCEPTED', 'authority_ref': 'PO'}}]}
        transaction = {'artifact_type': 'integra.open_proposal_promotion_transaction',
                       'transaction_id': 'txn-exact',
                       'inputs': {'candidate': self.identity, 'authorization': 'PROMOTE_CURRENT exact',
                                  'source': self.event['source'],
                                  'proposal_id': 'proposal-exact'},
                       'result': {'current_id': 'current-v2-exact'},
                       'semantics': {'post': 'CURRENT_PROTECTED_PROPOSAL_CONSUMED'}}
        result = lifecycle.collect_lifecycle_events(current, {'immutable-event.json': transaction}, self.snapshot)
        self.assertTrue(lifecycle.evidence_matches(self.identity, result[self.identity['candidate_id']]))
        bad = deepcopy(transaction); bad['inputs']['candidate']['bundle_digest'] = '0' * 64
        with self.assertRaises(ValueError):
            lifecycle.collect_lifecycle_events(current, {'event.json': bad}, self.snapshot)

    def receipt(self):
        manifest = {'candidate_id': self.identity['candidate_id'],
                    'bundle': {'digest': self.identity['bundle_digest']},
                    'identity': {'source': {**self.event['source'], 'dirty': False,
                                          'dirty_diff_sha256': '4' * 64}},
                    'runtime': {'version': 'exact'}, 'models': [{'digest': '3' * 64}]}
        return lifecycle.prepare_retirement(self.identity, self.replay(), manifest,
            {'status': 'COMPLETE'}, transaction_id='retirement-exact',
            canonical_snapshot=self.snapshot, policy=self.policy, timestamp='2026-10-09T00:00:00Z')

    def test_prepared_receipt_retains_full_manifest_history_not_completed_deletion(self):
        receipt = self.receipt()
        self.assertEqual(receipt['state'], 'PREPARED')
        self.assertTrue(receipt['physical_available'])
        self.assertEqual(receipt['retained_manifest']['models'], [{'digest': '3' * 64}])
        self.assertEqual(receipt['acceptance_refs'], self.event['acceptance_refs'])
        self.assertEqual(receipt['source']['tree_sha'], '2' * 40)
        self.assertFalse(receipt['source']['dirty'])

    def test_missing_source_or_wrong_source_cannot_claim_complete_history(self):
        record = self.replay()
        record['lifecycle_evidence'].pop('source')
        self.assertFalse(self.eligibility(record)['eligible'])
        manifest = {'candidate_id': self.identity['candidate_id'],
                    'bundle': {'digest': self.identity['bundle_digest']},
                    'identity': {'source': {'commit_sha': '9' * 40, 'tree_sha': '2' * 40}}}
        with self.assertRaisesRegex(ValueError, 'source differs'):
            lifecycle.prepare_retirement(self.identity, self.replay(), manifest, {},
                transaction_id='txn', canonical_snapshot=self.snapshot, policy=self.policy)

    def test_partial_and_completed_states_follow_actual_physical_availability(self):
        with tempfile.TemporaryDirectory() as root:
            source, trash = Path(root) / 'source', Path(root) / 'trash'
            source.mkdir()
            receipt = self.receipt()
            with self.assertRaises(ValueError):
                lifecycle.update_retirement(receipt, source=source, trash=trash, completed=True)
            source.rename(trash)
            partial = lifecycle.update_retirement(receipt, source=source, trash=trash, error='interrupted')
            self.assertEqual(partial['state'], 'PARTIAL'); self.assertTrue(partial['physical_available'])
            trash.rmdir()
            final = lifecycle.update_retirement(partial, source=source, trash=trash, completed=True)
            self.assertEqual(final['state'], 'RETIRED_NOT_AVAILABLE')
            self.assertFalse(final['physical_available'])

    def test_capacity_headroom_never_admits_build_when_canonical_transport_is_unavailable(self):
        from scripts import candidate_retention as retention
        from scripts import candidate_protection_audit as protection
        with tempfile.TemporaryDirectory(prefix='.integra-lifecycle-test-', dir=Path.home()) as name:
            root = Path(name)
            with patch.object(retention, 'catalog_path', return_value=root / 'catalog.json'), \
                    patch.object(retention, 'managed_roots', return_value=[]), \
                    patch.object(protection, '_api', side_effect=OSError('canonical transport unavailable')):
                with self.assertRaisesRegex(ValueError, 'fresh canonical protection unavailable'):
                    retention.build_preflight(root, 1)
                with self.assertRaisesRegex(ValueError, 'fresh canonical protection unavailable'):
                    with retention.reserved_build(root, 1, archive_copy=True):
                        self.fail('builder admitted without canonical authority')


if __name__ == '__main__':
    unittest.main()
