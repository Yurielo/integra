"""Operation gate fixtures never publish, promote, or delete user bytes."""
from __future__ import annotations

from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

from scripts import candidate_protection_gate as gate


class OperationGateTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.base = Path.home() / 'Library/Application Support/Integra'
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

    def test_pending_real_registry_blocks_all_operations_before_network(self):
        with patch.object(gate.protection, 'fetch_canonical', side_effect=AssertionError('network')):
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
                gate.require_deletion(target)
            self.audit['entries'][-1]['classification'] = 'ELIGIBLE'
            gate.require_deletion(target)  # Contract check only; no unlink exists here.


if __name__ == '__main__':
    unittest.main()
