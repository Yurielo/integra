"""Operation gate fixtures never publish, promote, or delete user bytes."""
from __future__ import annotations

from pathlib import Path
import hashlib
import json
import tempfile
import unittest
from unittest.mock import patch

from scripts import candidate_protection_gate as gate
from scripts import candidate_retention as retention, retention_cleanup as executor


class OperationGateTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.base = self.root / 'Library/Application Support/Integra'
        home_patch = patch.object(gate.Path, 'home', return_value=self.root)
        home_patch.start(); self.addCleanup(home_patch.stop)
        self.current = {'candidate_id': 'candidate-v1-' + 'a'*64,
                        'bundle_digest': 'b'*64, 'manifest_digest': 'c'*64}
        self.proposed = {'candidate_id': 'candidate-v1-' + 'd'*64,
                         'bundle_digest': 'e'*64, 'manifest_digest': 'f'*64}
        self.current_path = self.base / 'Build Archive/current'
        self.proposed_path = self.base / 'Validation/proposed'
        current_record = {'current_id': 'current-fixture'}
        record_path = self.root / 'state/current_product_baseline_v2.json'
        record_path.parent.mkdir()
        record_path.write_text(json.dumps(current_record))
        self.registry = {'canonical_current': {'current_id': 'current-fixture', **self.current,
                                                'path': 'state/current_product_baseline_v2.json',
                                                'sha256': gate.protection.sha(record_path.read_bytes())},
                         'selected_survivors': {
                             self.current['candidate_id']: 'Build Archive/current',
                             self.proposed['candidate_id']: 'Validation/proposed'},
                         'deletion_authorizations': {},
                         'managed_roots': ['Build Archive', 'Validation'],
                         'limits': {'max_full_copies': 8, 'max_attributed_bytes': 20*1024**3,
                                    'minimum_free_after_reservations': 15*1024**3}}
        self.audit = {'authority_state': 'COMPLETE', 'promotion_ready': True,
                      'full_copies': 2, 'archive_bytes': 200,
                      'free_bytes': 40*1024**3,
                      'entries': [self.row(self.current, 'Build Archive/current'),
                                  self.row(self.proposed, 'Validation/proposed')]}

    def row(self, identity, path, classification='PROTECTED'):
        return {'path': path, **identity, 'classification': classification,
                'verified_protected_archive': True}

    def test_pending_registry_blocks_all_operations_before_network(self):
        path = self.root / 'pending-registry.json'
        path.write_text(json.dumps({'status': 'PRODUCT_OWNER_ACCEPTED_PENDING_INTEGRATION'}))
        with patch.object(gate.protection, 'REGISTRY', path), \
                patch.object(gate.protection, 'fetch_canonical', side_effect=AssertionError('network')):
            for operation in (
                    lambda: gate.require_promotion({'candidate': self.proposed},
                                                   {'current_id': 'current-fixture'},
                                                   self.proposed_path, self.current_path),
                    lambda: gate.require_archive_publication(self.base / 'Build Archive', 10),
                    lambda: gate.require_deletion(self.current_path)):
                with self.subTest(operation=operation):
                    with self.assertRaisesRegex(ValueError, 'not activated and integrated'):
                        operation()

    def test_promotion_requires_exact_verified_selected_archives(self):
        with patch.object(gate, '_snapshot', return_value=(self.registry, self.audit)), \
                patch.object(gate.protection, 'ROOT', self.root):
            gate.require_promotion({'candidate': self.proposed}, {'current_id': 'current-fixture'},
                                   self.proposed_path, self.current_path)
            with self.assertRaisesRegex(ValueError, 'differs from canonical selected survivor'):
                gate.require_promotion({'candidate': self.proposed}, {'current_id': 'current-fixture'},
                                       self.base / 'Validation/wrong', self.current_path)
            self.audit['entries'][1]['verified_protected_archive'] = False
            with self.assertRaisesRegex(ValueError, 'not byte verified'):
                gate.require_promotion({'candidate': self.proposed}, {'current_id': 'current-fixture'},
                                       self.proposed_path, self.current_path)

    def test_archive_publication_enforces_both_caps_and_reserve(self):
        with patch.object(gate, '_snapshot', return_value=(self.registry, self.audit)):
            gate.require_archive_publication(self.base / 'Build Archive', 100)
            for key, value in [('full_copies', 8), ('archive_bytes', 20*1024**3),
                               ('free_bytes', 15*1024**3)]:
                with self.subTest(key=key):
                    old = self.audit[key]; self.audit[key] = value
                    with self.assertRaisesRegex(ValueError, 'cap blocks publication'):
                        gate.require_archive_publication(self.base / 'Build Archive', 100)
                    self.audit[key] = old

    def test_retention_publication_reservation_uses_canonical_gate_first(self):
        with patch.object(gate, 'require_archive_publication', side_effect=ValueError('authority unavailable')):
            with self.assertRaisesRegex(ValueError, 'authority unavailable'):
                retention.reserve_archive(self.base / 'Build Archive', 100)
        self.assertFalse((self.base / 'Retention').exists())

    def test_deletion_requires_exact_grant_and_eligible_row(self):
        target = self.base / 'Build Archive/old'
        identity = {'candidate_id': 'candidate-v1-' + '1'*64,
                    'bundle_digest': '2'*64, 'manifest_digest': '3'*64}
        self.audit['entries'].append(self.row(identity, 'Build Archive/old', 'UNKNOWN'))
        with patch.object(gate, '_snapshot', return_value=(self.registry, self.audit)):
            with self.assertRaisesRegex(ValueError, 'disables deletion'):
                gate.require_deletion(target)
            self.registry['deletion_authorizations']['Build Archive/old'] = {
                'path': 'Build Archive/old', **identity, 'authority_ref': 'fixture-owner'}
            with self.assertRaisesRegex(ValueError, 'disables deletion'):
                gate.require_deletion(target)
            self.registry['deletion_enabled'] = True
            with self.assertRaisesRegex(ValueError, 'forbids deletion'):
                gate.require_deletion(self.current_path)
            with self.assertRaisesRegex(ValueError, 'forbids deletion'):
                gate.require_deletion(target)
            self.audit['entries'][-1]['classification'] = 'ELIGIBLE'
            with patch.object(gate.protection, 'REGISTRY', self.root / 'registry.json'):
                (self.root / 'registry.json').write_text(json.dumps(self.registry))
                self.audit['registry_sha256'] = gate.protection.sha(
                    (self.root / 'registry.json').read_bytes())
                for relative in self.registry['selected_survivors'].values():
                    receipt = self.base / relative / 'COMPLETE.json'
                    receipt.parent.mkdir(parents=True, exist_ok=True)
                    receipt.write_text('fixture receipt')
                self.audit['canonical'] = {'fixture': 'verified-current-and-proposals'}
                lease = gate.require_deletion(target)
                self.assertEqual(lease['identity'], identity)

    def test_executor_uses_registry_for_plan_and_withdrawal(self):
        target = self.root / 'Build Archive/old'
        target.mkdir(parents=True)
        context = {'protected': {}, 'selected_archives': {}}
        job = {'source': str(target), 'trash': str(target.parent / '.retention-trash-fixture'),
               'identity': {'candidate_id': 'candidate-v1-' + '1'*64},
               'record': {}, 'device': target.stat().st_dev, 'inode': target.stat().st_ino,
               'canonical_deletion_lease': {'fixture': True}}
        catalog = {'protection': context}
        with patch.object(executor.canonical_gate, 'require_deletion', side_effect=ValueError('UNKNOWN')):
            with self.assertRaisesRegex(ValueError, 'UNKNOWN'):
                executor._guard(retention, catalog, job, target)
        with patch.object(executor.canonical_gate, 'require_deletion', return_value={'fixture': True}), \
                patch.object(retention, '_context_valid', return_value=False):
            with self.assertRaisesRegex(ValueError, 'protection authority'):
                executor._guard(retention, catalog, job, target)

    def test_missing_malformed_and_stale_registry_block_continuation(self):
        registry_path = self.root / 'registry.json'
        lease = {'registry_sha256': '0'*64, 'path': 'Build Archive/old',
                 'identity': {'candidate_id': 'candidate-v1-' + '1'*64}, 'grant': {}}
        with patch.object(gate.protection, 'REGISTRY', registry_path):
            with self.assertRaises(FileNotFoundError):
                gate.require_deletion_continuation(lease)
            registry_path.write_text('{broken')
            with self.assertRaisesRegex(ValueError, 'registry changed'):
                gate.require_deletion_continuation(lease)
            lease['registry_sha256'] = hashlib.sha256(registry_path.read_bytes()).hexdigest()
            with self.assertRaises(json.JSONDecodeError):
                gate.require_deletion_continuation(lease)

    def test_registry_drift_during_snapshot_fails_closed(self):
        registry_path = self.root / 'drifting-registry.json'
        registry_path.write_text(json.dumps({'status': 'PRODUCT_OWNER_AUTHORIZED_ACTIVE',
            'activation_authority_ref': 'fixture',
            'promotion_contract_integration_ref': 'fixture', 'deletion_enabled': False}))
        def drift(*args, **kwargs):
            registry_path.write_text(registry_path.read_text() + ' ')
            return {'authority_state': 'COMPLETE'}
        with patch.object(gate.protection, 'REGISTRY', registry_path), \
                patch.object(gate.protection, 'fetch_canonical', return_value=({}, {}, {})), \
                patch.object(gate.protection, 'scan_local', return_value=[]), \
                patch.object(gate.protection, 'resolve', side_effect=drift), \
                patch.object(gate.shutil, 'disk_usage', return_value=type('D', (), {'free': 1})()):
            with self.assertRaisesRegex(ValueError, 'registry changed during capture'):
                gate._snapshot()

    def test_resume_revalidates_current_authority_and_selected_survivor(self):
        registry_path = self.root / 'active-registry.json'
        cid = self.current['candidate_id']
        registry = {'status': 'PRODUCT_OWNER_AUTHORIZED_ACTIVE',
                    'activation_authority_ref': 'fixture-owner',
                    'promotion_contract_integration_ref': 'fixture-integration',
                    'deletion_enabled': True,
                    'deletion_authorizations': {'Build Archive/old': {'authority_ref': 'fixture-grant'}},
                    'selected_survivors': {cid: 'Build Archive/current'}}
        registry_path.write_text(json.dumps(registry))
        receipt = self.base / 'Build Archive/current/COMPLETE.json'
        receipt.parent.mkdir(parents=True)
        receipt.write_text('verified fixture survivor receipt')
        canonical = {'current_sha256': 'a'*64}
        lease = {'registry_sha256': hashlib.sha256(registry_path.read_bytes()).hexdigest(),
                 'canonical_sha256': gate.protection.digest(canonical),
                 'path': 'Build Archive/old', 'identity': {'candidate_id': 'candidate-v1-' + '1'*64},
                 'grant': registry['deletion_authorizations']['Build Archive/old'],
                 'survivors': {cid: {'path': 'Build Archive/current',
                                     'receipt_sha256': gate.protection.sha(receipt.read_bytes())}}}
        with patch.object(gate.protection, 'REGISTRY', registry_path), \
                patch.object(gate.protection, 'fetch_canonical', return_value=({}, {}, canonical)) as fetch, \
                patch.object(gate.protection, '_accepted_historical_gaps', return_value=set()), \
                patch.object(gate.protection, '_validate_registry', return_value={cid: {'identity': self.current}}):
            gate.require_deletion_continuation(lease)
            fetch.return_value = ({}, {}, {'current_sha256': 'changed'})
            with self.assertRaisesRegex(ValueError, 'canonical deletion inputs changed'):
                gate.require_deletion_continuation(lease)
            fetch.return_value = ({}, {}, canonical)
            receipt.unlink()
            with self.assertRaises(FileNotFoundError):
                gate.require_deletion_continuation(lease)
            registry_path.write_text(json.dumps({'deletion_enabled': False}))
            with self.assertRaisesRegex(ValueError, 'registry changed'):
                gate.require_deletion_continuation(lease)


if __name__ == '__main__':
    unittest.main()
