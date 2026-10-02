"""Small synthetic authority fixtures: never touch user archives or CURRENT."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

from scripts import candidate_protection_audit as audit
from scripts import candidate_archive
from integra_core.candidate_identity import candidate_id, canonical_bytes, tree_sha256


class ProtectionAuditTests(unittest.TestCase):
    def setUp(self):
        self.registry = json.loads(audit.REGISTRY.read_text())
        self.registry['proposed'] = [item for item in self.registry['proposed'] if item['pr'] == 213]
        self.registry['selected_survivors'] = {
            cid: path for cid, path in self.registry['selected_survivors'].items()
            if cid in {self.registry['canonical_current']['candidate_id'],
                       self.registry['rollback']['candidate_id'],
                       self.registry['proposed'][0]['candidate_id']}}
        self.registry.update(status='PRODUCT_OWNER_AUTHORIZED_ACTIVE',
                             activation_authority_ref='issue-comment:fixture',
                             promotion_contract_integration_ref='pr:fixture',
                             explicit_governance_pins={},
                             deletion_authorizations={},
                             recovery={**self.registry['canonical_current'],
                                       'confirmation_ref': 'issue-comment:fixture'})
        self.registry['rollback']['confirmation_ref'] = 'issue-comment:fixture'
        self.current = json.loads((audit.ROOT / 'state/current_product_baseline_v2.json').read_text())
        self.proposals = {213: {'artifact_type': 'integra.proposed_product_baseline',
                                'candidate': {key: self.registry['proposed'][0][key] for key in audit.IDENTITY},
                                'owner_acceptance': {'promotion_authorized': True}}}
        self.registry['selected_survivors'] = {
            cid: 'Build Archive/' + cid for cid in self.registry['selected_survivors']}
        self.packages = [self.package(identity) for identity in (
            self.registry['canonical_current'], self.registry['rollback'], self.registry['proposed'][0])]
        self.canonical = {'current_sha256': self.registry['canonical_current']['sha256'],
                          'historical_receipts': {
                              gap['candidate_id']: {
                                  'record': json.loads((audit.ROOT / gap['receipt_path']).read_text()),
                                  'path': gap['receipt_path']}
                              for gap in self.registry['historical_gaps']}}

    def package(self, identity, *, allocated=100):
        cid = identity['candidate_id']
        return {'path': 'Build Archive/' + cid, 'absolute_path': '/fixture/' + cid,
                **{key: identity[key] for key in audit.IDENTITY},
                'allocated_bytes': allocated, 'publisher_owned': True,
                'lifecycle': 'COMPLETED', 'inactive': True, 'metadata_error': None}

    def resolve(self, *, verifier=None, free=40 * 1024**3):
        if verifier is None:
            verifier = lambda path, expected: {
                **expected, 'inventory_sha256': self.canonical['historical_receipts'].get(
                    expected['candidate_id'], {}).get('record', {}).get('inventory_sha256')}
        return audit.resolve(self.registry, self.current, self.proposals, self.packages,
                             free_bytes=free, verifier=verifier, canonical=self.canonical)

    def test_verified_current_and_rollback_recovery_archive(self):
        result = self.resolve()
        self.assertEqual(result['authority_state'], 'COMPLETE')
        self.assertTrue(result['promotion_ready'])
        self.assertEqual([r['classification'] for r in result['entries']], ['PROTECTED'] * 3)

    def test_missing_current_archive_blocks_and_never_eligible(self):
        self.packages.pop(0)
        result = self.resolve()
        self.assertIn('MISSING_PROTECTED_ARCHIVE:' + self.registry['canonical_current']['candidate_id'],
                      result['blockers'])
        self.assertFalse(result['promotion_ready'])
        self.assertEqual(result['eligible_bytes'], 0)

    def test_mismatched_bundle_or_manifest_fails_closed(self):
        for key in ('bundle_digest', 'manifest_digest'):
            with self.subTest(key=key):
                original = self.packages[0][key]
                self.packages[0][key] = 'f' * 64
                self.assertIn('PROTECTED_ARCHIVE_IDENTITY_CONFLICT:' +
                              self.registry['canonical_current']['candidate_id'], self.resolve()['blockers'])
                self.packages[0][key] = original
        result = self.resolve(verifier=lambda path, expected: (_ for _ in ()).throw(ValueError('byte mismatch')))
        self.assertTrue(any(b.startswith('PROTECTED_ARCHIVE_INTEGRITY_FAIL:') for b in result['blockers']))

    def test_unknown_historical_stays_unknown(self):
        self.packages.append(self.package({'candidate_id': 'candidate-v1-' + '9'*64,
                                           'bundle_digest': '8'*64, 'manifest_digest': '7'*64}))
        self.assertEqual(self.resolve()['entries'][-1]['classification'], 'UNKNOWN')

    def test_exact_deletion_grant_only_for_unprotected_owned_terminal(self):
        unknown = self.package({'candidate_id': 'candidate-v1-' + '9'*64,
                                'bundle_digest': '8'*64, 'manifest_digest': '7'*64})
        self.packages.append(unknown)
        self.registry['deletion_authorizations'][unknown['path']] = {
            **{k: unknown[k] for k in ('path', *audit.IDENTITY)},
            'authority_ref': 'issue-comment:fixture-grant'}
        self.assertEqual(self.resolve()['entries'][-1]['classification'], 'ELIGIBLE')
        self.assertEqual(self.resolve()['entries'][0]['classification'], 'PROTECTED')

    def test_explicit_pin_protects_and_missing_pin_enumeration_blocks(self):
        pinned = {'candidate_id': 'candidate-v1-' + '9'*64,
                  'bundle_digest': '8'*64, 'manifest_digest': '7'*64,
                  'authority_ref': 'issue-comment:pin'}
        self.registry['explicit_governance_pins'][pinned['candidate_id']] = pinned
        self.registry['selected_survivors'][pinned['candidate_id']] = 'Build Archive/' + pinned['candidate_id']
        self.packages.append(self.package(pinned))
        self.assertEqual(self.resolve()['entries'][-1]['classification'], 'PROTECTED')
        self.registry['explicit_governance_pins'] = None
        self.assertIn('EXPLICIT_PIN_ENUMERATION_MISSING', self.resolve()['blockers'])

    def test_conflicting_authority_and_open_proposal(self):
        self.proposals[213]['candidate']['bundle_digest'] = 'f' * 64
        self.assertIn('PROPOSAL_IDENTITY_CONFLICT:213', self.resolve()['blockers'])
        self.proposals[213]['candidate']['bundle_digest'] = self.registry['proposed'][0]['bundle_digest']
        current_id = self.registry['canonical_current']['candidate_id']
        self.registry['explicit_governance_pins'] = {current_id: {
            **self.registry['canonical_current'], 'bundle_digest': 'f'*64,
            'authority_ref': 'issue-comment:conflict'}}
        self.assertIn('CONFLICTING_PROTECTED_IDENTITY:' + current_id, self.resolve()['blockers'])
        self.registry['explicit_governance_pins'] = {}
        self.proposals[206] = copy.deepcopy(self.proposals[213])
        self.proposals[206]['candidate']['candidate_id'] = 'candidate-v1-' + '9'*64
        self.assertIn('UNREGISTERED_OPEN_PROPOSAL:206', self.resolve()['blockers'])

    def test_interrupted_archive_is_not_verified(self):
        result = self.resolve(verifier=lambda path, expected: (_ for _ in ()).throw(ValueError('COMPLETE missing')))
        self.assertEqual(result['authority_state'], 'BLOCKED_FAIL_CLOSED')
        self.assertEqual(result['eligible_bytes'], 0)

    def test_limits_and_reserve(self):
        self.registry['limits']['max_full_copies'] = 2
        self.registry['limits']['max_attributed_bytes'] = 200
        result = self.resolve(free=10 * 1024**3)
        for blocker in ('ARCHIVE_COPY_CAP_EXCEEDED', 'ARCHIVE_BYTE_CAP_EXCEEDED', 'DISK_RESERVE_BELOW_FLOOR'):
            self.assertIn(blocker, result['blockers'])
        self.assertFalse(result['bootstrap_plan']['can_create_recovery_now'])
        self.assertFalse(result['bootstrap_plan']['capacity_available_for_preflight'])

    def test_current_rollback_proposed_never_eligible_when_terminal(self):
        for item in self.resolve()['entries']:
            self.assertEqual(item['classification'], 'PROTECTED')
        self.proposals[213]['owner_acceptance'] = {'promotion_authorized': False}
        result = self.resolve()
        self.assertFalse(result['promotion_ready'])
        self.assertIn('PROMOTION_OWNER_AUTHORIZATION_MISSING:213', result['promotion_blockers'])
        self.assertEqual(result['eligible_bytes'], 0)

    def test_missing_promotion_integration_blocks_readiness(self):
        self.registry['promotion_contract_integration_ref'] = None
        result = self.resolve()
        self.assertIn('PROMOTION_CONTRACT_INTEGRATION_MISSING', result['blockers'])
        self.assertFalse(result['promotion_ready'])

    def test_exact_historical_recovery_source_requires_full_inventory(self):
        with tempfile.TemporaryDirectory(prefix='.integra-protection-test-', dir=Path.home()) as root:
            app = Path(root) / 'source/Integra.app'
            embedded = app / candidate_archive.EMBEDDED
            embedded.parent.mkdir(parents=True)
            executable = app / 'Contents/MacOS/Integra'
            executable.parent.mkdir()
            executable.write_bytes(b'fixture executable')
            identity = {'source': {'commit_sha': 'a'*40},
                        'execution': {'gui_python': {'path': '/fixture/python', 'sha256': 'b'*64}}}
            cid = candidate_id(identity)
            manifest = {'schema_version': '1.0', 'candidate_id': cid,
                        'identity_sha256': cid.removeprefix('candidate-v1-'),
                        'identity': identity,
                        'bundle': {'digest_algorithm': 'sha256-tree-excluding-candidate-manifest',
                                   'digest': tree_sha256(app, exclude={candidate_archive.EMBEDDED})},
                        'build': {'timestamp': 'fixture'}}
            embedded.write_bytes(canonical_bytes(manifest) + b'\n')
            receipt = candidate_archive.create_archive(app, Path(root) / 'archive')
            self.assertEqual(candidate_archive.verify_archive(Path(receipt['archive_path']))['status'], 'COMPLETE')
            self.assertEqual(audit.verify_exact_recovery_source(app, receipt)['source_verification'],
                             'EXACT_HISTORICAL_SOURCE_VERIFIED')
            (app / 'Contents/Resources/__pycache__').mkdir()
            (app / 'Contents/Resources/__pycache__/extra.pyc').write_bytes(b'extra byte')
            with self.assertRaisesRegex(ValueError, 'full-byte inventory'):
                audit.verify_exact_recovery_source(app, receipt)


if __name__ == '__main__':
    unittest.main()
