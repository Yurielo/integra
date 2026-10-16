"""The accepted historical gap is a single exact transition, never recovery."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import candidate_protection_gate as gate
import prepare_historical_gap_transition as prepare


class HistoricalGapGateTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / 'state').mkdir()
        self.data = b'{"current_id":"old"}\n'
        (self.root / 'state/current_product_baseline_v2.json').write_bytes(self.data)
        self.registry_data = b'{"status":"PRODUCT_OWNER_AUTHORIZED_ACTIVE"}\n'
        self.registry_path = self.root / 'state/candidate_protection_registry_v1.json'
        self.registry_path.write_bytes(self.registry_data)
        self.registry_sha = hashlib.sha256(self.registry_data).hexdigest()
        self.current = {'current_id': 'old'}
        self.candidate = {'candidate_id': gate.HISTORICAL_SUCCESSOR,
                          'bundle_digest': 'a' * 64, 'manifest_digest': 'b' * 64}
        self.proposal = {'candidate': self.candidate}
        self.archive = self.root / 'proposed'
        self.ref = 'https://github.com/Yurielo/integra/issues/216#issuecomment-123456'
        self.registry = {
            'canonical_current': {'path': 'state/current_product_baseline_v2.json',
                                  'sha256': hashlib.sha256(self.data).hexdigest(),
                                  'current_id': 'old', 'candidate_id': gate.HISTORICAL_CURRENT},
            'rollback': {'candidate_id': gate.HISTORICAL_ROLLBACK},
            'decision_authority_ref': 'https://github.com/Yurielo/integra/issues/214#issuecomment-1',
            'recovery_selection': {'state': 'NO_VERIFIED_ARCHIVE_ACCEPTED_HISTORICAL_GAP',
                                   'candidate_id': gate.HISTORICAL_CURRENT,
                                   'decision_ref': 'https://github.com/Yurielo/integra/issues/214#issuecomment-1',
                                   'archive_path': None},
            'historical_gaps': [
                {'role': role, 'candidate_id': cid,
                 'observed_state': 'MISSING_WITH_AVAILABLE_EVIDENCE'}
                for role, cid in [('CURRENT', gate.HISTORICAL_CURRENT),
                                  ('ROLLBACK', gate.HISTORICAL_ROLLBACK)]],
            'selected_survivors': {gate.HISTORICAL_CURRENT: None,
                                   gate.HISTORICAL_ROLLBACK: None,
                                   gate.HISTORICAL_SUCCESSOR: 'Validation/proposed'},
            'proposed': [{'pr': 213, 'head_sha': gate.HISTORICAL_PROPOSAL_HEAD,
                          'candidate_id': gate.HISTORICAL_SUCCESSOR}],
            'unknown_historical': 'RETAIN_FAIL_CLOSED',
            'deletion_enabled': False, 'deletion_authorizations': {},
        }
        self.audit = {
            'authority_state': 'COMPLETE',
            'canonical': {'main_sha': 'c' * 40,
                          'proposal_heads': {'213': gate.HISTORICAL_PROPOSAL_HEAD}},
            'registry_sha256': self.registry_sha,
            'promotion_blockers': ['OUTGOING_CURRENT_EXACT_ARCHIVE_MISSING',
                                   'PROMOTION_OWNER_AUTHORIZATION_MISSING:213'],
            'entries': [{'classification': 'UNKNOWN'}],
        }
        self.token = ('PRODUCT_OWNER_AUTHORIZATION: ISSUE_216_HISTORICAL_GAP_TRANSITION '
                      f'FROM={gate.HISTORICAL_CURRENT} TO={gate.HISTORICAL_SUCCESSOR} '
                      f'PROPOSAL_PR_213_HEAD={gate.HISTORICAL_PROPOSAL_HEAD} '
                      f'REGISTRY_SHA256={self.registry_sha} '
                      'CURRENT_RECOVERY=MISSING_WITH_AVAILABLE_EVIDENCE '
                      'ROLLBACK_RECOVERY=MISSING_WITH_AVAILABLE_EVIDENCE '
                      'UNKNOWN=RETAIN_FAIL_CLOSED DELETION=FORBIDDEN')
        self.enterContext(patch.object(gate.protection, 'REGISTRY', self.registry_path))
        self.enterContext(patch.object(gate.protection, 'ROOT', self.root))
        self.snapshot = self.enterContext(patch.object(gate, '_snapshot',
                               side_effect=lambda: (self.registry, self.audit)))
        self.remote = self.enterContext(patch.object(gate.protection, '_remote_file',
                           side_effect=lambda *_: (self.registry_data, {})))
        self.api = self.enterContext(patch.object(gate.protection, '_api',
                        side_effect=lambda *_: {'html_url': self.ref,
                                                 'user': {'login': 'Yurielo'},
                                                 'body': self.token}))
        self.selected = self.enterContext(patch.object(gate, '_selected_verified'))

    def require(self):
        return gate.require_historical_gap_transition(self.proposal, self.current,
                                                      self.archive, self.ref)

    def test_exact_approved_gap_and_candidate_with_separate_owner_authorization(self):
        result = self.require()
        self.assertEqual(result['outgoing_recovery'], 'MISSING_WITH_AVAILABLE_EVIDENCE')
        self.assertEqual(result['rollback_recovery'], 'MISSING_WITH_AVAILABLE_EVIDENCE')
        self.selected.assert_called_once_with(self.registry, self.audit,
                                              self.candidate, self.archive)

    def test_wrong_candidate_or_later_current_cannot_reuse_exception(self):
        self.proposal['candidate'] = {**self.candidate, 'candidate_id': 'candidate-v1-' + 'f' * 64}
        with self.assertRaisesRegex(ValueError, 'exact scope'):
            self.require()
        self.proposal['candidate'] = self.candidate
        self.current['current_id'] = 'next-current'
        with self.assertRaisesRegex(ValueError, 'exact scope'):
            self.require()

    def test_unaccepted_gap_or_false_recovery_claim_fails(self):
        self.registry['historical_gaps'][0]['observed_state'] = 'RECOVERED'
        with self.assertRaisesRegex(ValueError, 'historical recovery gap'):
            self.require()
        self.registry['historical_gaps'][0]['observed_state'] = 'MISSING_WITH_AVAILABLE_EVIDENCE'
        self.registry['selected_survivors'][gate.HISTORICAL_CURRENT] = 'Recovery Archive/lookalike'
        with self.assertRaisesRegex(ValueError, 'historical recovery gap'):
            self.require()

    def test_incomplete_or_stale_authority_fails(self):
        self.snapshot.side_effect = ValueError('canonical protection authority is incomplete')
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            self.require()
        self.snapshot.side_effect = lambda: (self.registry, self.audit)
        self.remote.side_effect = lambda *_: (b'stale registry', {})
        with self.assertRaisesRegex(ValueError, 'not published unchanged'):
            self.require()

    def test_unknown_remains_unknown_and_deletion_without_grant_fails(self):
        self.assertEqual(self.audit['entries'][0]['classification'], 'UNKNOWN')
        self.registry['deletion_authorizations'] = {'Build Archive/unknown': {}}
        with self.assertRaisesRegex(ValueError, 'protection or promotion blockers'):
            self.require()
        self.registry['deletion_authorizations'] = {}
        self.audit['entries'][0]['classification'] = 'ELIGIBLE'
        with self.assertRaisesRegex(ValueError, 'protection or promotion blockers'):
            self.require()

    def test_unrelated_blocker_or_bad_owner_token_fails(self):
        self.audit['promotion_blockers'].append('PROPOSED_CANDIDATE_EXACT_ARCHIVE_MISSING:213')
        with self.assertRaisesRegex(ValueError, 'blockers differ'):
            self.require()
        self.audit['promotion_blockers'].pop()
        self.api.side_effect = lambda *_: {'html_url': self.ref, 'user': {'login': 'Yurielo'},
                                           'body': self.token.replace('DELETION=FORBIDDEN', 'DELETION=ALLOW')}
        with self.assertRaisesRegex(ValueError, 'authorization is absent'):
            self.require()

    def test_registry_tampering_during_check_fails(self):
        def mutate(*_):
            self.registry_path.write_text('tampered')
            return {'html_url': self.ref, 'user': {'login': 'Yurielo'}, 'body': self.token}
        self.api.side_effect = mutate
        with self.assertRaisesRegex(ValueError, 'changed after'):
            self.require()


class HistoricalGapPrepareTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / 'state').mkdir()
        self.current = {'current_id': 'old', 'records': []}
        (self.root / 'state/current_product_baseline_v2.json').write_text(json.dumps(self.current))
        self.candidate = {'candidate_id': gate.HISTORICAL_SUCCESSOR,
                          'bundle_digest': 'a' * 64, 'manifest_digest': 'b' * 64}
        self.proposal = self.root / 'state/proposed_baseline_lite_v1.json'
        self.proposal.write_text(json.dumps({'candidate': self.candidate}))
        self.archive = self.root / 'archive'
        self.archive.mkdir()
        self.output = self.root / 'next.json'
        self.history = self.root / 'history.json'
        self.evidence = self.root / 'evidence.json'
        self.args = ['--proposal', str(self.proposal), '--proposal-checkout', str(self.root),
                     '--candidate-archive', str(self.archive),
                     '--transition-authority-ref', 'https://github.com/Yurielo/integra/issues/216#issuecomment-123',
                     '--output', str(self.output), '--history-output', str(self.history),
                     '--evidence-output', str(self.evidence)]
        self.enterContext(patch.object(prepare, 'ROOT', self.root))
        self.git = self.enterContext(patch.object(prepare.subprocess, 'run', side_effect=[
            type('Result', (), {'stdout': gate.HISTORICAL_PROPOSAL_HEAD + '\n'})(),
            type('Result', (), {'stdout': ''})()] * 3))
        for name in ('validate_current', 'validate_proposal', 'verify_promotion_material'):
            self.enterContext(patch.object(prepare, name, return_value=[]))
        self.verify = self.enterContext(patch.object(prepare, 'verify_archive', return_value={'verified': True}))
        self.gate = self.enterContext(patch.object(prepare, 'require_historical_gap_transition',
                                    return_value={'outgoing_recovery': 'MISSING_WITH_AVAILABLE_EVIDENCE'}))
        self.enterContext(patch.object(prepare, 'next_current', return_value={'next': True}))

    def run_main(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return prepare.main(self.args)

    def test_prepares_distinct_evidence_without_changing_current(self):
        self.assertEqual(self.run_main(), 0)
        self.assertEqual(json.loads(self.output.read_text()), {'next': True})
        self.assertEqual(json.loads(self.history.read_text()), self.current)
        self.assertEqual(json.loads(self.evidence.read_text())['status'], 'PREPARED_NOT_PROMOTED')
        self.assertEqual(json.loads((self.root / 'state/current_product_baseline_v2.json').read_text()),
                         self.current)

    def test_missing_proposed_bytes_blocks_all_writes(self):
        self.verify.side_effect = FileNotFoundError('missing proposed bytes')
        self.assertEqual(self.run_main(), 1)
        self.assertFalse(any(p.exists() for p in (self.output, self.history, self.evidence)))
        self.gate.assert_not_called()

    def test_missing_owner_authorization_blocks_all_writes(self):
        self.gate.side_effect = ValueError('owner transition authorization absent')
        self.assertEqual(self.run_main(), 1)
        self.assertFalse(any(p.exists() for p in (self.output, self.history, self.evidence)))

    def test_moved_or_dirty_proposal_checkout_blocks_all_writes(self):
        for head, dirty in (('f' * 40, ''), (gate.HISTORICAL_PROPOSAL_HEAD, ' M proposal')):
            with self.subTest(head=head, dirty=dirty):
                self.git.side_effect = [type('Result', (), {'stdout': head})(),
                                        type('Result', (), {'stdout': dirty})()]
                self.assertEqual(self.run_main(), 1)
                self.assertFalse(any(p.exists() for p in (self.output, self.history, self.evidence)))


if __name__ == '__main__':
    unittest.main()
