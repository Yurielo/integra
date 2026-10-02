"""Exact owner-authorized legacy retirement uses only tiny disposable fixtures."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import issue214_exact_legacy_retirement as retire


class ExactLegacyRetirementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        path_patch = patch.object(retire.candidate_archive, '_path', side_effect=lambda path, **_: path)
        path_patch.start(); self.addCleanup(path_patch.stop)
        self.package = self.root / 'Build Archive' / 'old'
        self.app = self.package / 'Integra.app'
        self.app.mkdir(parents=True)
        (self.package / 'preserve-receipt.json').write_text('historical evidence')
        (self.app / 'one').write_text('one')
        (self.app / 'two').write_text('two')
        self.row = {'path': 'Build Archive/old', 'candidate_id': 'candidate-v1-' + 'a' * 64,
                    'bundle_digest': 'b' * 64, 'manifest_digest': 'c' * 64,
                    'allocated_bytes': retire._measure(self.package)}

    def test_real_catalog_is_exactly_bound_and_empty_regular_grants_remain(self):
        registry = json.loads(retire.authority.REGISTRY.read_text())
        self.assertEqual(len(retire._catalog(registry)), 6)
        registry['deletion_authorizations'] = {'foreign': {'authority_ref': 'fake'}}
        with self.assertRaisesRegex(ValueError, 'fail-closed'):
            retire._catalog(registry)

    def test_tampered_owner_comment_fails(self):
        with patch.object(retire.authority, '_api', return_value={
                'html_url': retire.DECISION_REF, 'user': {'login': 'Yurielo'},
                'body': 'PRODUCT_OWNER_AUTHORIZATION: other'}):
            with self.assertRaisesRegex(ValueError, 'not verified'):
                retire._owner_decision()

    def test_protected_or_changed_package_cannot_enter_retirement(self):
        with patch.object(retire, 'BASE', self.root), patch.object(retire, '_inactive'):
            with patch.object(retire.candidate_archive, '_identity', return_value={
                    key: self.row[key] for key in retire.IDENTITY}):
                audit = {'entries': [{**self.row, 'classification': 'PROTECTED'}]}
                with self.assertRaisesRegex(ValueError, 'newly protected'):
                    retire._verify_app(self.row, audit)
                audit['entries'][0]['classification'] = 'UNKNOWN'
                audit['entries'][0]['manifest_digest'] = 'd' * 64
                with self.assertRaisesRegex(ValueError, 'identity or allocation'):
                    retire._verify_app(self.row, audit)

    def _job(self):
        s = self.app.lstat()
        return {'path': self.row['path'], 'identity': {k: self.row[k] for k in retire.IDENTITY},
                'phase': 'PREPARED', 'device': s.st_dev, 'inode': s.st_ino,
                'entries': retire._entries(self.app)}

    def test_only_app_payload_is_removed_and_receipt_survives(self):
        journal = {'active': self._job(), 'completed': []}
        with patch.object(retire, 'BASE', self.root), patch.object(retire, 'JOURNAL', self.root / 'journal.json'), \
             patch.object(retire, '_inactive'):
            retire._delete_active(journal, {'entries': []}, [self.row])
        self.assertFalse(self.app.exists())
        self.assertEqual((self.package / 'preserve-receipt.json').read_text(), 'historical evidence')
        self.assertEqual(journal['completed'], [self.row['path']])

    def test_interrupted_unlink_resumes_only_recorded_entries(self):
        journal = {'active': self._job(), 'completed': []}
        original = os.unlink
        calls = 0

        def interrupt(name, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise KeyboardInterrupt()
            return original(name, **kwargs)

        with patch.object(retire, 'BASE', self.root), patch.object(retire, 'JOURNAL', self.root / 'journal.json'), \
             patch.object(retire, '_inactive'):
            with patch.object(retire.os, 'unlink', side_effect=interrupt):
                with self.assertRaises(KeyboardInterrupt):
                    retire._delete_active(journal, {'entries': []}, [self.row])
            self.assertEqual(journal['active']['phase'], 'DELETING')
            self.assertTrue(self.app.exists())
            retire._delete_active(journal, {'entries': []}, [self.row])
        self.assertFalse(self.app.exists())
        self.assertTrue((self.package / 'preserve-receipt.json').exists())

    def test_changed_remaining_entry_stops_resume(self):
        job = self._job(); job['phase'] = 'DELETING'
        (self.app / 'two').write_text('foreign replacement')
        journal = {'active': job, 'completed': []}
        with patch.object(retire, 'BASE', self.root), patch.object(retire, '_inactive'):
            with self.assertRaisesRegex(ValueError, 'remaining bytes changed'):
                retire._delete_active(journal, {'entries': []}, [self.row])
        self.assertTrue(self.app.exists())

    def test_stale_authority_before_unlink_preserves_app(self):
        journal = {'active': self._job(), 'completed': []}
        with patch.object(retire, 'BASE', self.root), patch.object(retire, '_inactive'), \
             patch.object(retire, '_snapshot', return_value=({}, {'registry_sha256': 'b' * 64}, [self.row])):
            with self.assertRaisesRegex(ValueError, 'changed before legacy unlink'):
                retire._delete_active(journal, {'entries': []}, [self.row], registry_sha='a' * 64)
        self.assertTrue((self.app / 'one').exists())

    def test_stale_registry_blocks_journal_resume(self):
        journal = {'schema_version': '1.0', 'catalog_sha256': retire.CATALOG_SHA,
                   'registry_sha256': 'a' * 64, 'completed': [], 'active': None}
        path = self.root / 'journal.json'; path.write_text(json.dumps(journal))
        with patch.object(retire, 'JOURNAL', path):
            with self.assertRaisesRegex(ValueError, 'stale or malformed'):
                retire._load('b' * 64)


if __name__ == '__main__':
    unittest.main()
