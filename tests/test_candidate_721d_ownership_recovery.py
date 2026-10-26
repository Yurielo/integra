"""Causal exact-recovery fixtures: no real archives, catalogs, or GitHub writes."""
from __future__ import annotations

import base64
from copy import deepcopy
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

try:
    from tests import test_candidate_archive as fixtures
except ImportError:
    import test_candidate_archive as fixtures
from scripts import candidate_721d_ownership_recovery as recovery
from scripts import candidate_archive as archive, candidate_retention as retention


class Exact721dRecoveryTests(unittest.TestCase):
    def setUp(self):
        fixtures.CandidateArchiveTests.setUp(self)
        self.destination = self.root / 'managed' / 'Build Archive'
        self.base = self.destination.parent
        with patch.object(recovery.gate, 'require_archive_publication', return_value=None), \
                patch.object(archive, 'MANAGED_BASE', self.base), \
                patch.object(retention, '_context_valid', return_value=False), \
                patch.object(retention, 'maintenance', return_value=[]):
            self.package = Path(fixtures.CandidateArchiveTests._create(self)['archive_path'])
        self.catalog_file = self.root / 'retention/catalog.json'
        self.identity = {key: archive.verify_archive(self.package)[key]
                         for key in archive.IDENTITY_KEYS}
        self.relative = self.package.relative_to(self.base).as_posix()
        self.info = self.package.stat()
        self.previous_device = self.info.st_dev + 1
        self.volume = {'mount_point': '/System/Volumes/Data', 'uuid': 'A' * 8 + '-BBBB-CCCC-DDDD-' + 'E' * 12,
                       'device': self.info.st_dev}
        self.repo = self.root / 'repo'
        self.repo.mkdir()
        raw = json.loads(self.catalog_file.read_bytes())
        record = raw['artifacts'][str(self.package)]
        record['device'] = self.previous_device
        self.original = deepcopy(record)
        self.other = {'candidate_id': 'candidate-v1-' + 'f' * 64,
                      'bundle_digest': 'e' * 64, 'manifest_digest': 'd' * 64,
                      'status': 'AWAITING_OWNER_ACCEPTANCE',
                      'device': self.previous_device, 'preserve': ['CURRENT', 'K1', 'K2']}
        raw['artifacts'][str(self.base / 'another-package')] = deepcopy(self.other)
        retention._persist(self.catalog_file, raw)
        self.before_catalog = self.catalog_file.read_bytes()
        self.request = b'Exact owner-reviewed fixture request\n'
        self.request_sha = recovery._sha(self.request)
        self.history_raw = b'{"artifact_type":"fixture-immutable-withdrawal"}\n'
        self.body = '\n'.join((recovery.TOKEN, self.request_sha, 'WITHDRAW_OWNER_ACCEPTANCE_REQUEST',
                               'does not accept this Candidate', 'does not intend to promote',
                               *self.identity.values()))
        self.comment = {'html_url': 'https://github.com/Yurielo/integra/issues/293#issuecomment-1',
                        'user': {'login': 'Yurielo'}, 'body': self.body}
        self.auth = {
            'schema_version': '1.0', 'artifact_type': 'integra.exact_721d_ownership_recovery_authorization',
            'status': 'PRODUCT_OWNER_AUTHORIZED_ACTIVE', 'identity': self.identity, 'path': self.relative,
            'authority_ref': self.comment['html_url'], 'authority_body_sha256': recovery._sha(self.body.encode()),
            'owner_decision_request': {'path': recovery.REQUEST, 'sha256': self.request_sha},
            'withdrawal_history': {'path': recovery.WITHDRAWAL, 'sha256': recovery._sha(self.history_raw)},
            'publisher_attestation_sha256': retention._digest(self.original),
            'previous_device': self.previous_device, 'expected_device': self.info.st_dev,
            'expected_inode': self.info.st_ino, 'owner_uid': os.getuid(), 'scope': recovery.SCOPE,
            'expected_volume': self.volume,
        }
        self.main = 'a' * 40
        self.remote = {recovery.AUTHORIZATION: recovery._bytes(self.auth),
                       recovery.REQUEST: self.request, recovery.WITHDRAWAL: self.history_raw,
                       recovery.SCRIPT: Path(recovery.__file__).read_bytes()}
        for name, module in (('candidate_retention', retention), ('candidate_archive', archive),
                             ('candidate_protection_gate', recovery.gate),
                             ('candidate_protection_audit', recovery.protection),
                             ('candidate_lifecycle', recovery.lifecycle)):
            self.remote['scripts/' + name + '.py'] = Path(module.__file__).read_bytes()
        authfile = self.repo / recovery.AUTHORIZATION
        authfile.parent.mkdir(parents=True)
        authfile.write_bytes(self.remote[recovery.AUTHORIZATION])
        withdrawal = {**self.identity, 'authority_ref': self.comment['html_url'],
                      'authority_body_sha256': self.auth['authority_body_sha256'],
                      'history_path': recovery.WITHDRAWAL, 'history_sha256': recovery._sha(self.history_raw),
                      'previous_status': 'AWAITING_OWNER_ACCEPTANCE', 'resulting_status': 'WITHDRAWN_SUPERSEDED'}
        self.registry = {'selected_survivors': {}, 'canonical_current': {'current_id': 'fixture-current'},
                         'withdrawal_deletion_authorizations': {
            self.relative: {**self.identity, 'path': self.relative, 'authority_ref': self.comment['html_url'],
                            'lifecycle': 'WITHDRAWN_SUPERSEDED'}}}
        self.audit = {'authority_state': 'COMPLETE', 'registry_sha256': 'b' * 64, 'entries': [],
                      'protected_identities': {}, 'canonical': {
                          'main_sha': self.main, 'withdrawn_candidate_lifecycles': [withdrawal]}}
        for fixture_patch in (
            patch.object(recovery, 'ROOT', self.repo), patch.object(recovery, 'BASE', self.base),
            patch.object(recovery, 'IDENTITY', self.identity), patch.object(recovery, 'RELATIVE', self.relative),
            patch.object(recovery, 'PREVIOUS_DEVICE', self.previous_device),
            patch.object(recovery, 'EXPECTED_DEVICE', self.info.st_dev),
            patch.object(recovery, 'EXPECTED_INODE', self.info.st_ino),
            patch.object(recovery, 'OWNER_UID', os.getuid()),
            patch.object(recovery, 'REQUEST_SHA256', self.request_sha),
            patch.object(recovery, '_volume_identity', return_value=self.volume),
            patch.object(recovery.protection, '_api', side_effect=self._api),
            patch.object(recovery.gate, '_snapshot', side_effect=lambda **kw: (deepcopy(self.registry), deepcopy(self.audit))),
            patch.object(retention, '_inactive', return_value=True),
        ):
            fixture_patch.start(); self.addCleanup(fixture_patch.stop)
        self.evidence = self.catalog_file.parent / 'evidence' / recovery.TRANSACTION

    _manifest = fixtures.CandidateArchiveTests._manifest

    def _api(self, endpoint):
        prefix = 'repos/Yurielo/integra/contents/'
        if endpoint.startswith(prefix):
            path, ref = endpoint[len(prefix):].rsplit('?ref=', 1)
            self.assertEqual(ref, self.main)
            if path not in self.remote:
                raise ValueError('not on canonical main')
            return {'type': 'file', 'encoding': 'base64',
                    'content': base64.b64encode(self.remote[path]).decode()}
        if endpoint.endswith('/issues/comments/1'):
            return deepcopy(self.comment)
        if endpoint.endswith('/git/ref/heads/main'):
            return {'object': {'sha': self.main}}
        raise AssertionError('unexpected fixture transport read: ' + endpoint)

    def _catalog(self):
        return json.loads(self.catalog_file.read_bytes())

    def _change_record(self, key, value):
        catalog = self._catalog()
        catalog['artifacts'][str(self.package)][key] = value
        retention._persist(self.catalog_file, catalog)

    def _change_auth(self, key, value):
        self.auth[key] = value
        raw = recovery._bytes(self.auth)
        self.remote[recovery.AUTHORIZATION] = raw
        (self.repo / recovery.AUTHORIZATION).write_bytes(raw)

    def test_dry_run_preserves_all_catalog_and_payload_bytes(self):
        before = archive.verify_archive(self.package)
        result = recovery.recover()
        self.assertEqual(result['state'], 'READY')
        self.assertFalse(result['writes_performed'])
        self.assertEqual(self.catalog_file.read_bytes(), self.before_catalog)
        self.assertFalse(self.evidence.exists())
        self.assertEqual(archive.verify_archive(self.package), before)

    def test_exact_commit_changes_only_device_and_dedicated_journal_with_immutable_backup(self):
        receipt = archive.verify_archive(self.package)
        result = recovery.recover(apply=True)
        after = self._catalog()
        self.assertEqual(result['state'], 'COMPLETE')
        expected = json.loads(self.before_catalog)
        expected['artifacts'][str(self.package)]['device'] = self.info.st_dev
        self.assertEqual(recovery._without_journal(after), expected)
        self.assertEqual(after['artifacts'][str(self.base / 'another-package')], self.other)
        self.assertEqual((self.evidence / 'catalog-before.json').read_bytes(), self.before_catalog)
        self.assertEqual(archive.verify_archive(self.package), receipt)
        self.assertTrue(retention._ownership(self.package, after['artifacts'][str(self.package)], receipt))
        before = json.loads((self.evidence / 'BEFORE.json').read_bytes())
        completed = json.loads((self.evidence / 'AFTER.json').read_bytes())
        self.assertEqual(before['record_before'], self.original)
        self.assertEqual(completed['changed_record_fields'], ['device'])
        self.assertFalse(completed['archive_payload_changed'])
        saved = self.catalog_file.read_bytes()
        self.assertEqual(recovery.recover(apply=True)['state'], 'ALREADY_APPLIED')
        self.assertEqual(self.catalog_file.read_bytes(), saved)

    def test_missing_unmerged_or_changed_authorization_executable_dependency_is_rejected(self):
        for path, replacement in ((recovery.AUTHORIZATION, None), (recovery.SCRIPT, b'branch-only script'),
                                  ('scripts/candidate_retention.py', b'weakened ownership predicate')):
            original = self.remote[path]
            with self.subTest(path=path):
                if replacement is None:
                    del self.remote[path]
                else:
                    self.remote[path] = replacement
                with self.assertRaises(ValueError):
                    recovery.recover(apply=True)
                self.assertEqual(self.catalog_file.read_bytes(), self.before_catalog)
                self.remote[path] = original
        self.assertFalse(self.evidence.exists())

    def test_wrong_scope_identity_request_history_or_owner_permission_is_rejected(self):
        for field, value in (('scope', 'ALL_ARCHIVES'), ('identity', {**self.identity, 'bundle_digest': 'f' * 64}),
                             ('path', self.relative + '-another'), ('expected_inode', self.info.st_ino + 1),
                             ('owner_uid', os.getuid() + 1),
                             ('owner_decision_request', {'path': recovery.REQUEST, 'sha256': 'f' * 64}),
                             ('withdrawal_history', {'path': recovery.WITHDRAWAL, 'sha256': 'f' * 64})):
            original = deepcopy(self.auth[field])
            with self.subTest(field=field):
                self._change_auth(field, value)
                with self.assertRaises(ValueError):
                    recovery.recover(apply=True)
                self.assertEqual(self.catalog_file.read_bytes(), self.before_catalog)
                self._change_auth(field, original)
        self.comment['body'] += '\nchanged permission'
        with self.assertRaises(ValueError):
            recovery.recover(apply=True)
        self.assertFalse(self.evidence.exists())

    def test_withdrawal_hold_and_exact_grant_are_mandatory(self):
        for change in ('withdrawal', 'hold', 'grant', 'selector'):
            original_registry, original_audit = deepcopy(self.registry), deepcopy(self.audit)
            with self.subTest(change=change):
                if change == 'withdrawal':
                    self.audit['canonical']['withdrawn_candidate_lifecycles'] = []
                elif change == 'hold':
                    self.audit['protected_identities'][self.identity['candidate_id']] = {'reasons': ['CURRENT']}
                elif change == 'selector':
                    self.registry['selected_survivors'][self.identity['candidate_id']] = self.relative
                else:
                    self.registry['withdrawal_deletion_authorizations'] = {}
                with self.assertRaises(ValueError):
                    recovery.recover(apply=True)
                self.assertEqual(self.catalog_file.read_bytes(), self.before_catalog)
                self.registry, self.audit = original_registry, original_audit

    def test_publisher_attestation_inode_uid_metadata_and_active_writer_changes_are_rejected(self):
        for field, value in (('publisher_run_id', ''), ('publisher_start_token', ''),
                             ('publisher_completed', False), ('inode', self.info.st_ino + 1),
                             ('owner_uid', os.getuid() + 1), ('complete_sha256', 'f' * 64),
                             ('inventory_sha256', 'f' * 64), ('historical', True),
                             ('status', 'CURRENT')):
            with self.subTest(field=field):
                self._change_record(field, value)
                saved = self.catalog_file.read_bytes()
                with self.assertRaises(ValueError):
                    recovery.recover(apply=True)
                self.assertEqual(self.catalog_file.read_bytes(), saved)
                self._change_record(field, self.original[field])
        with patch.object(retention, '_inactive', return_value=False):
            with self.assertRaisesRegex(ValueError, 'inactivity'):
                recovery.recover(apply=True)
        with patch.object(retention, '_publisher_live', return_value=True):
            with self.assertRaisesRegex(ValueError, 'inactivity'):
                recovery.recover(apply=True)
        self.assertFalse(self.evidence.exists())

    def test_volume_change_and_canonical_main_race_are_rejected(self):
        with patch.object(recovery, '_volume_identity', return_value={**self.volume, 'uuid': 'f' * 36}):
            with self.assertRaisesRegex(ValueError, 'current volume'):
                recovery.recover(apply=True)
        original = self._api
        with patch.object(recovery.protection, '_api', side_effect=lambda endpoint:
                          {'object': {'sha': 'f' * 40}} if endpoint.endswith('/git/ref/heads/main') else original(endpoint)):
            with self.assertRaisesRegex(ValueError, 'main changed'):
                recovery.recover(apply=True)
        self.assertEqual(self.catalog_file.read_bytes(), self.before_catalog)

    def test_observed_directory_identity_changes_are_rejected(self):
        observed = recovery._filesystem(self.package)
        for key in ('inode', 'owner_uid', 'device'):
            with self.subTest(key=key), patch.object(
                    recovery, '_filesystem', return_value={**observed, key: observed[key] + 1}):
                with self.assertRaisesRegex(ValueError, 'current volume, inode or UID changed'):
                    recovery.recover(apply=True)
                self.assertEqual(self.catalog_file.read_bytes(), self.before_catalog)
        self.assertFalse(self.evidence.exists())

    def test_owner_comment_requires_exact_recovery_permission_not_withdrawal_alone(self):
        self.comment['body'] = self.body.replace(recovery.TOKEN, 'WITHDRAWAL_ONLY')
        self._change_auth('authority_body_sha256', recovery._sha(self.comment['body'].encode()))
        with self.assertRaisesRegex(ValueError, 'explicit owner authorization'):
            recovery.recover(apply=True)
        self.assertEqual(self.catalog_file.read_bytes(), self.before_catalog)

    def test_corrupt_archive_bytes_or_metadata_are_rejected_without_catalog_writes(self):
        for relative in ('Integra.app/Contents/MacOS/Integra', 'inventory.json', 'COMPLETE.json'):
            path = self.package / relative
            original = path.read_bytes()
            with self.subTest(path=relative):
                path.write_bytes(original + b'changed')
                with self.assertRaises(ValueError):
                    recovery.recover(apply=True)
                self.assertEqual(self.catalog_file.read_bytes(), self.before_catalog)
                path.write_bytes(original)
        self.assertFalse(self.evidence.exists())

    def test_interruption_before_or_after_each_atomic_catalog_checkpoint_resumes(self):
        persist = retention._persist
        # Each subcase owns a new tiny archive/catalog; no production state.
        for checkpoint in (1, 2, 3):
            for after_write in (False, True):
                with self.subTest(checkpoint=checkpoint, after_write=after_write):
                    if self.evidence.exists():
                        import shutil
                        shutil.rmtree(self.evidence)
                    self.catalog_file.write_bytes(self.before_catalog)
                    calls = 0
                    def interrupted(path, value):
                        nonlocal calls
                        calls += 1
                        if calls == checkpoint:
                            if after_write:
                                persist(path, value)
                            raise OSError('fixture atomic persistence interruption')
                        persist(path, value)
                    with patch.object(retention, '_persist', side_effect=interrupted):
                        with self.assertRaises(OSError):
                            recovery.recover(apply=True)
                    result = recovery.recover(apply=True)
                    self.assertIn(result['state'], ('COMPLETE', 'ALREADY_APPLIED'))
                    self.assertEqual(self._catalog()['artifacts'][str(self.package)]['device'], self.info.st_dev)
                    self.assertEqual((self.evidence / 'catalog-before.json').read_bytes(), self.before_catalog)
                    self.assertEqual(self._catalog()['artifacts'][str(self.base / 'another-package')], self.other)

    def test_changed_other_record_after_preparation_is_preserved_and_blocks_resume(self):
        persist = retention._persist
        def prepared_then_crash(path, value):
            persist(path, value)
            raise OSError('fixture stopped after prepared')
        with patch.object(retention, '_persist', side_effect=prepared_then_crash):
            with self.assertRaises(OSError):
                recovery.recover(apply=True)
        catalog = self._catalog()
        catalog['artifacts'][str(self.base / 'another-package')]['preserve'].append('new foreign work')
        persist(self.catalog_file, catalog)
        saved = self.catalog_file.read_bytes()
        with self.assertRaisesRegex(ValueError, 'outside its exact device update'):
            recovery.recover(apply=True)
        self.assertEqual(self.catalog_file.read_bytes(), saved)

    def test_receipt_publication_interruption_leaves_single_link_and_resumes(self):
        publish = archive._publish
        for receipt_name in ('catalog-before.json', 'BEFORE.json', 'AFTER.json'):
            with self.subTest(receipt_name=receipt_name):
                if self.evidence.exists():
                    import shutil
                    shutil.rmtree(self.evidence)
                self.catalog_file.write_bytes(self.before_catalog)
                def interrupted(source, destination):
                    publish(source, destination)
                    if destination.name == receipt_name:
                        raise OSError('fixture stopped immediately after no-replace rename')
                with patch.object(archive, '_publish', side_effect=interrupted):
                    with self.assertRaises(OSError):
                        recovery.recover(apply=True)
                self.assertEqual((self.evidence / receipt_name).stat().st_nlink, 1)
                self.assertEqual(recovery.recover(apply=True)['state'], 'COMPLETE')

    def test_immutable_before_backup_and_after_receipts_cannot_be_replaced(self):
        recovery.recover(apply=True)
        for name in ('BEFORE.json', 'AFTER.json', 'catalog-before.json'):
            path = self.evidence / name
            original = path.read_bytes()
            with self.subTest(name=name):
                path.write_bytes(original + b' ')
                saved = self.catalog_file.read_bytes()
                with self.assertRaises(ValueError):
                    recovery.recover(apply=True)
                self.assertEqual(self.catalog_file.read_bytes(), saved)
                path.write_bytes(original)

    def test_target_reconciliation_preserves_other_records_and_device_journal(self):
        recovery.recover(apply=True)
        before = self._catalog()
        self.audit['canonical']['withdrawn_candidate_lifecycles'].append({
            **{key: self.other[key] for key in archive.IDENTITY_KEYS},
            'previous_status': 'AWAITING_OWNER_ACCEPTANCE',
            'resulting_status': 'WITHDRAWN_SUPERSEDED', 'authority_ref': 'another validated fixture decision'})
        # The real broad reconciler would change this other pending record.
        disposable = deepcopy(before)
        retention.reconcile_catalog(disposable, self.registry, self.audit, self.base)
        self.assertEqual(disposable['artifacts'][str(self.base / 'another-package')]['status'], 'WITHDRAWN_SUPERSEDED')
        result = recovery.reconcile_target()
        self.assertEqual(result['state'], 'TARGET_WITHDRAWAL_RECONCILED')
        after = self._catalog()
        target = str(self.package)
        self.assertEqual(after['artifacts'][target]['status'], 'WITHDRAWN_SUPERSEDED')
        self.assertEqual(after['artifacts'][target], recovery.lifecycle.replay_withdrawal(
            before['artifacts'][target], self.audit['canonical']['withdrawn_candidate_lifecycles']))
        expected = deepcopy(before)
        expected['protection'] = after['protection']
        expected['artifacts'][target] = after['artifacts'][target]
        self.assertEqual(after, expected)
        self.assertEqual(after['artifacts'][str(self.base / 'another-package')], self.other)
        self.assertEqual(after[recovery.JOURNAL], before[recovery.JOURNAL])
        saved = self.catalog_file.read_bytes()
        self.assertEqual(recovery.reconcile_target()['state'], 'ALREADY_RECONCILED')
        self.assertEqual(self.catalog_file.read_bytes(), saved)

    def test_target_reconciliation_requires_complete_unchanged_device_receipts(self):
        with self.assertRaises((ValueError, FileNotFoundError)):
            recovery.reconcile_target()
        self.assertEqual(self.catalog_file.read_bytes(), self.before_catalog)
        recovery.recover(apply=True)
        for name in ('BEFORE.json', 'AFTER.json', 'catalog-before.json'):
            path = self.evidence / name
            original = path.read_bytes()
            with self.subTest(name=name):
                path.write_bytes(original + b' ')
                saved = self.catalog_file.read_bytes()
                with self.assertRaises(ValueError):
                    recovery.reconcile_target()
                self.assertEqual(self.catalog_file.read_bytes(), saved)
                path.write_bytes(original)

    def test_target_reconciliation_rejects_changed_target_activity_and_authority(self):
        recovery.recover(apply=True)
        current = self.catalog_file.read_bytes()
        for change in ('publisher', 'lease', 'deletion', 'withdrawal', 'protected'):
            original_audit = deepcopy(self.audit)
            with self.subTest(change=change):
                catalog = self._catalog()
                if change == 'publisher':
                    catalog['artifacts'][str(self.package)]['publisher_run_id'] = 'different publisher'
                elif change == 'lease':
                    catalog['leases']['fixture-active'] = {'owner_uid': os.getuid()}
                elif change == 'deletion':
                    catalog['deletions']['fixture-pending'] = {'phase': 'PREPARED'}
                elif change == 'withdrawal':
                    self.audit['canonical']['withdrawn_candidate_lifecycles'] = []
                else:
                    self.audit['protected_identities'][self.identity['candidate_id']] = {'reasons': ['CURRENT']}
                retention._persist(self.catalog_file, catalog)
                saved = self.catalog_file.read_bytes()
                with self.assertRaises(ValueError):
                    recovery.reconcile_target()
                self.assertEqual(self.catalog_file.read_bytes(), saved)
                self.audit = original_audit
                self.catalog_file.write_bytes(current)
        with patch.object(retention, '_inactive', return_value=False):
            with self.assertRaisesRegex(ValueError, 'inactivity'):
                recovery.reconcile_target()
        self.assertEqual(self.catalog_file.read_bytes(), current)

    def test_target_reconciliation_checks_established_helper_and_current_bytes(self):
        recovery.recover(apply=True)
        saved = self.catalog_file.read_bytes()
        reconcile = retention.reconcile_catalog
        def wrong_target(catalog, registry, audit, base):
            reconcile(catalog, registry, audit, base)
            catalog['artifacts'][str(self.package)]['unexpected'] = 'forbidden'
        with patch.object(retention, 'reconcile_catalog', side_effect=wrong_target):
            with self.assertRaisesRegex(ValueError, 'differs from the exact target withdrawal'):
                recovery.reconcile_target()
        path = self.package / 'Integra.app/Contents/MacOS/Integra'
        path.write_bytes(path.read_bytes() + b'changed after device repair')
        with self.assertRaises(ValueError):
            recovery.reconcile_target()
        self.assertEqual(self.catalog_file.read_bytes(), saved)

    def test_target_reconciliation_requires_verified_protected_survivors(self):
        recovery.recover(apply=True)
        saved = self.catalog_file.read_bytes()
        cid = self.other['candidate_id']
        self.registry['selected_survivors'][cid] = 'Build Archive/missing-protected-survivor'
        self.audit['protected_identities'][cid] = {'reasons': ['CURRENT']}
        with self.assertRaisesRegex(ValueError, 'protected survivor is not verified'):
            recovery.reconcile_target()
        self.assertEqual(self.catalog_file.read_bytes(), saved)

    def test_target_reconciliation_atomic_persist_interruption_is_idempotent(self):
        recovery.recover(apply=True)
        device_complete = self.catalog_file.read_bytes()
        persist = retention._persist
        for after_write in (False, True):
            with self.subTest(after_write=after_write):
                self.catalog_file.write_bytes(device_complete)
                def interrupted(path, value):
                    if after_write:
                        persist(path, value)
                    raise OSError('fixture reconciliation atomic interruption')
                with patch.object(retention, '_persist', side_effect=interrupted):
                    with self.assertRaises(OSError):
                        recovery.reconcile_target()
                result = recovery.reconcile_target()
                self.assertIn(result['state'], ('TARGET_WITHDRAWAL_RECONCILED', 'ALREADY_RECONCILED'))
                self.assertEqual(self._catalog()['artifacts'][str(self.package)]['status'], 'WITHDRAWN_SUPERSEDED')
                self.assertEqual(self._catalog()['artifacts'][str(self.base / 'another-package')], self.other)

    def test_target_protection_refresh_accepts_only_main_advance_and_preserves_receipts(self):
        recovery.recover(apply=True)
        recovery.reconcile_target()
        before = self._catalog()
        receipts = {name: (self.evidence / name).read_bytes()
                    for name in ('BEFORE.json', 'AFTER.json', 'catalog-before.json')}
        self.main = 'c' * 40
        self.audit['canonical']['main_sha'] = self.main
        result = recovery.reconcile_target()
        self.assertEqual(result['changed_catalog_fields'], ['protection'])
        after = self._catalog()
        self.assertEqual(after['artifacts'], before['artifacts'])
        self.assertEqual(after[recovery.JOURNAL], before[recovery.JOURNAL])
        expected = deepcopy(before)
        expected['protection'] = after['protection']
        self.assertEqual(after, expected)
        self.assertEqual(after['protection']['canonical_snapshot']['main_sha'], self.main)
        for name, raw in receipts.items():
            self.assertEqual((self.evidence / name).read_bytes(), raw)

    def test_target_protection_refresh_rejects_changed_auth_registry_or_withdrawal(self):
        recovery.recover(apply=True)
        self.main = 'c' * 40
        self.audit['canonical']['main_sha'] = self.main
        original_audit, original_auth = deepcopy(self.audit), deepcopy(self.auth)
        for change in ('authorization', 'registry', 'withdrawal'):
            with self.subTest(change=change):
                if change == 'authorization':
                    self._change_auth('publisher_attestation_sha256', 'f' * 64)
                elif change == 'registry':
                    self.audit['registry_sha256'] = 'e' * 64
                else:
                    self.audit['canonical']['withdrawn_candidate_lifecycles'][0]['reason'] = 'different withdrawal'
                saved = self.catalog_file.read_bytes()
                with self.assertRaisesRegex(ValueError, 'complete bound ownership transaction'):
                    recovery.reconcile_target()
                self.assertEqual(self.catalog_file.read_bytes(), saved)
                self.audit = deepcopy(original_audit)
                self.auth = deepcopy(original_auth)
                self._change_auth('publisher_attestation_sha256', self.auth['publisher_attestation_sha256'])

    def test_reconciliation_authority_shape_and_both_main_identities_are_strict(self):
        binding = {'main_sha': 'a' * 40, 'authorization_sha256': 'b' * 64,
                   'registry_sha256': 'c' * 64, 'withdrawal': {'exact': 'fixture'}}
        self.assertTrue(recovery._same_reconciliation_authority(binding, {**binding, 'main_sha': 'd' * 40}))
        for invalid in (None, {**binding, 'extra': True},
                        {key: value for key, value in binding.items() if key != 'withdrawal'},
                        {**binding, 'main_sha': 'branch-name'}, {**binding, 'main_sha': 1},
                        {**binding, 'main_sha': 'a' * 39}):
            with self.subTest(invalid=invalid):
                self.assertFalse(recovery._same_reconciliation_authority(invalid, binding))
                self.assertFalse(recovery._same_reconciliation_authority(binding, invalid))

    def test_device_recovery_remains_strict_after_main_advance(self):
        recovery.recover(apply=True)
        saved = self.catalog_file.read_bytes()
        self.main = 'c' * 40
        self.audit['canonical']['main_sha'] = self.main
        with self.assertRaisesRegex(ValueError, 'canonical authority changed'):
            recovery.recover(apply=True)
        self.assertEqual(self.catalog_file.read_bytes(), saved)

    def test_target_protection_refresh_still_rejects_main_race_within_operation(self):
        recovery.recover(apply=True)
        self.main = 'c' * 40
        self.audit['canonical']['main_sha'] = self.main
        authority = recovery._authority
        def changed_before_commit(*, with_snapshot=False):
            value = authority(with_snapshot=with_snapshot)
            if not with_snapshot:
                return value[0], {**value[1], 'main_sha': 'd' * 40}
            return value
        saved = self.catalog_file.read_bytes()
        with patch.object(recovery, '_authority', side_effect=changed_before_commit):
            with self.assertRaisesRegex(ValueError, 'changed before commit'):
                recovery.reconcile_target()
        self.assertEqual(self.catalog_file.read_bytes(), saved)


if __name__ == '__main__':
    unittest.main()
