import json
from contextlib import nullcontext
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts import retention_governance as governance


class RetentionGovernanceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.current = {'current_id': 'now', 'records': [
            {'baseline_id': 'old', 'candidate': {'candidate_id': 'rollback', 'bundle_digest': 'r'},
             'acceptance': {'decision': 'USER_ACCEPTED'}},
            {'baseline_id': 'now', 'candidate': {'candidate_id': 'current', 'bundle_digest': 'c'},
             'acceptance': {'decision': 'USER_ACCEPTED'}}]}
        self.current_path = self.base / 'current.json'
        self.current_path.write_text(json.dumps(self.current))
        self.snapshot = {'repository': governance.REPOSITORY, 'main_sha': 'main',
                         'current': {'sha256': governance._sha(self.current_path.read_bytes()),
                                     'value': self.current}, 'open_prs': {}, 'policy': {},
                         'pin_requirements': {}}
        self.rollback = self.receipt('rollback', 'r')
        self.recovery = self.receipt('recovery', 'z')
        self.owner_ref = 'https://github.com/Yurielo/integra/issues/205#issuecomment-1'
        authority = {'decision': 'CONFIRMED_RECOVERY', 'candidate_id': 'recovery',
                     'bundle_digest': 'z', 'authority_ref': self.owner_ref}
        self.owner_comment = {'user': {'login': 'Yurielo'}, 'body': json.dumps(authority)}
        path = self.base / 'authority.json'; path.write_text(json.dumps(authority))
        self.authority = {'path': str(path), 'sha256': governance._sha(path.read_bytes())}

    @staticmethod
    def receipt(cid, bundle):
        return {'candidate_id': cid, 'bundle_digest': bundle, 'manifest_digest': 'm',
                'status': 'COMPLETE', 'verification': 'ARCHIVAL_BYTE_INTEGRITY',
                'archive_path': '/not-accessed/' + cid}

    def capture(self, **kwargs):
        authority = kwargs.get('authority', self.authority)
        api = (patch.object(governance, '_get', return_value=self.owner_comment)
               if isinstance(authority, dict) else nullcontext())
        with patch.object(governance, 'fetch_snapshot', return_value=self.snapshot), api:
            return governance.capture_protection(self.current_path, [],
                kwargs.get('rollback', self.rollback), self.recovery,
                kwargs.get('authority', self.authority), kwargs.get('pins'))

    def test_missing_canonical_pin_enumeration_never_authorizes_cleanup(self):
        self.snapshot['pin_requirements'] = None
        context = self.capture()
        self.assertFalse(context['complete'])
        self.assertIn('current', context['protected'])
        self.assertFalse(governance.validate_snapshot(context['authoritative_snapshot']))

    def test_exact_context_complete_and_selected_receipts_bound(self):
        context = self.capture()
        self.assertTrue(context['complete'])
        self.assertEqual(context['selected_receipts']['CONFIRMED_ROLLBACK'], self.rollback)
        self.assertEqual(context['authority_refs']['CONFIRMED_RECOVERY'], self.owner_ref)

    def test_local_sha_bound_self_assertion_does_not_establish_owner_authority(self):
        path = Path(self.authority['path'])
        value = json.loads(path.read_text()); value['authority_ref'] = 'made-up authority'
        path.write_text(json.dumps(value))
        authority = {'path': str(path), 'sha256': governance._sha(path.read_bytes())}
        with self.assertRaisesRegex(ValueError, 'explicit recovery'):
            self.capture(authority=authority)

    def test_same_candidate_different_rollback_bundle_rejected(self):
        with self.assertRaisesRegex(ValueError, 'exact immediate'):
            self.capture(rollback=self.receipt('rollback', 'different'))

    def test_arbitrary_recovery_ref_rejected(self):
        with self.assertRaisesRegex(ValueError, 'explicit recovery'):
            self.capture(authority='CI was green')

    def test_omitted_canonical_pin_rejected(self):
        self.snapshot['pin_requirements'] = {'pinned': 'accepted-main-requirement'}
        with self.assertRaisesRegex(ValueError, 'pins differ'):
            self.capture()

    def test_omitted_local_proposal_is_still_protected_from_canonical_inventory(self):
        self.snapshot['open_prs'] = {'206': {'head_sha': 'exact', 'proposal': {
            'sha256': 'proposal', 'value': {'artifact_type': 'integra.proposed_product_baseline',
                                          'candidate': {'candidate_id': 'pending', 'bundle_digest': 'p'}}}}}
        self.assertIn('pending', self.capture()['protected'])

    def test_same_candidate_conflicting_required_bundles_are_not_collapsed(self):
        self.snapshot['open_prs'] = {'206': {'head_sha': 'exact', 'proposal': {
            'sha256': 'proposal', 'value': {'artifact_type': 'integra.proposed_product_baseline',
                                          'candidate': {'candidate_id': 'current', 'bundle_digest': 'different'}}}}}
        identities = self.capture()['protected_identities']['current']
        self.assertEqual({identity['bundle_digest'] for identity in identities}, {'c', 'different'})

    def test_snapshot_drift_or_read_error_fails_closed(self):
        with patch.object(governance, 'fetch_snapshot', return_value={**self.snapshot, 'main_sha': 'new'}):
            self.assertFalse(governance.validate_snapshot(self.snapshot))
        with patch.object(governance, 'fetch_snapshot', side_effect=subprocess.TimeoutExpired('gh', 30)):
            self.assertFalse(governance.validate_snapshot(self.snapshot))

    def test_404_only_is_absent_not_permission_failure(self):
        with patch.object(governance.subprocess, 'run', return_value=subprocess.CompletedProcess(
                ['gh'], 1, '', 'gh: Not Found (HTTP 404)')):
            self.assertIsNone(governance._get('test', absent=True))
        with patch.object(governance.subprocess, 'run', return_value=subprocess.CompletedProcess(
                ['gh'], 1, '', 'gh: Forbidden (HTTP 403)')):
            with self.assertRaises(ValueError):
                governance._get('test', absent=True)

    def test_exhaustive_open_pr_pagination(self):
        first = [{'number': i, 'state': 'open', 'head': {'sha': str(i)}} for i in range(100)]
        last = [{'number': 100, 'state': 'open', 'head': {'sha': '100'}}]
        with patch.object(governance, '_get', side_effect=[first, last]) as get:
            heads = governance._open_heads()
        self.assertEqual(len(heads), 101)
        self.assertIn('page=2', get.call_args_list[1].args[0])

    def test_capture_uses_immutable_main_and_exact_pr_head_refs(self):
        def get(endpoint):
            if endpoint.endswith('/git/ref/heads/main'):
                return {'object': {'sha': 'main-exact'}}
            if endpoint.endswith('/commits/pr-exact'):
                return {'sha': 'pr-exact'}
            self.fail('unexpected endpoint: ' + endpoint)
        with patch.object(governance, '_get', side_effect=get), patch.object(
                governance, '_open_heads', return_value={206: 'pr-exact'}), patch.object(
                governance, '_content', side_effect=[self.snapshot['current'], None, None]) as content:
            snapshot = governance.fetch_snapshot()
        self.assertEqual(snapshot['main_sha'], 'main-exact')
        self.assertEqual(content.call_args_list[0].args, (governance.CURRENT, 'main-exact'))
        self.assertEqual(content.call_args_list[1].args, (governance.PROPOSAL, 'pr-exact'))
        self.assertIsNone(snapshot['pin_requirements'])

    def test_unreadable_pr_commit_is_not_treated_as_absent_proposal(self):
        def get(endpoint):
            if endpoint.endswith('/git/ref/heads/main'):
                return {'object': {'sha': 'main-exact'}}
            raise ValueError('PR commit unreadable')
        with patch.object(governance, '_get', side_effect=get), patch.object(
                governance, '_open_heads', return_value={206: 'fork-head'}), patch.object(
                governance, '_content', return_value=self.snapshot['current']) as content:
            with self.assertRaisesRegex(ValueError, 'unreadable'):
                governance.fetch_snapshot()
        self.assertEqual(content.call_count, 1)

    def test_owner_comment_edit_invalidates_snapshot(self):
        snapshot = {**self.snapshot, 'authority_comments': {'comment-endpoint': 'old'}}
        with patch.object(governance, 'fetch_snapshot', return_value=self.snapshot), patch.object(
                governance, '_get', return_value={'body': 'edited'}):
            self.assertFalse(governance.validate_snapshot(snapshot))

    def test_keyword_mentions_are_not_owner_recovery_confirmation(self):
        value = {'user': {'login': 'Yurielo'},
                 'body': 'Do not CONFIRMED_RECOVERY recovery z; only a hypothetical example.'}
        with patch.object(governance, '_get', return_value=value):
            with self.assertRaisesRegex(ValueError, 'structured confirmation'):
                self.capture(authority='https://github.com/Yurielo/integra/issues/205#issuecomment-1')

    def test_accepted_historical_recovery_evidence_needs_exact_main_binding(self):
        value = {'result': 'EXACT_RECORDED_BUNDLE_AND_MANIFEST_RECOVERED',
                 'recovered_candidate': 'recovery', 'recovered_bundle_digest': 'z',
                 'manifest_sha256': 'm'}
        path = self.base / 'accepted-recovery.json'; path.write_text(json.dumps(value))
        authority = {'path': str(path), 'sha256': governance._sha(path.read_bytes()),
                     'repository_path': 'docs/evidence/accepted-recovery.json'}
        with patch.object(governance, '_content', return_value={'sha256': authority['sha256']}):
            context = self.capture(authority=authority)
        self.assertIn('/blob/main/', context['authority_refs']['CONFIRMED_RECOVERY'])
        with patch.object(governance, '_content', return_value={'sha256': 'different'}):
            with self.assertRaisesRegex(ValueError, 'accepted recovery'):
                self.capture(authority=authority)
