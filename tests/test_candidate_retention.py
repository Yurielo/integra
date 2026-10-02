"""Tiny owned archive fixtures; never touch the historical managed archive."""
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_candidate_archive as fixtures
from scripts import candidate_retention as r, candidate_archive as archive, retention_cleanup as executor


class OwnedRetentionTests(unittest.TestCase):
    setUp = fixtures.CandidateArchiveTests.setUp
    _manifest = fixtures.CandidateArchiveTests._manifest
    _create = fixtures.CandidateArchiveTests._create
    _package = fixtures.CandidateArchiveTests._package
    _expected_path = fixtures.CandidateArchiveTests._expected_path

    def _catalog(self):
        return self.root / 'retention/catalog.json'

    def _ready(self):
        package = self._package()
        self.identity['source']['commit_sha'] = 'c' * 40; self._manifest()
        survivor = self._package()
        self._context(package, survivor)
        return package, survivor

    def _context(self, package, survivor):
        receipt = archive.verify_archive(survivor); cid = receipt['candidate_id']
        with r.locked(self._catalog()) as catalog:
            catalog['protection'] = {'protected': {cid: ['CURRENT', 'LATEST_ACCEPTED_BASELINE', 'CONFIRMED_ROLLBACK', 'CONFIRMED_RECOVERY']},
                'inputs': {str(survivor / 'COMPLETE.json'): r._sha(survivor / 'COMPLETE.json')},
                'authoritative_snapshot': {'fixture': True}, 'selected_archives': {cid: str(survivor)},
                'verified_survivors': {cid: receipt}}
            r.disposition(catalog, package, 'SUPERSEDED', 'fixture exact retirement authority')
            for v in catalog['artifacts'].values():
                v['publisher_start_token'] = 'dead fixture publisher'
        for fixture_patch in (patch('scripts.retention_governance.validate_snapshot', return_value=True),
                              patch.object(r, '_inactive', return_value=True)):
            fixture_patch.start(); self.addCleanup(fixture_patch.stop)

    def _plan(self):
        return r.plan(json.loads(self._catalog().read_text()), free_bytes=64 * 1024**3)

    def test_policy_limits_match_owner_machine_record(self):
        policy = json.loads((r.ROOT / 'state/candidate_retention_policy_v1.json').read_text())
        self.assertEqual((r.MAX_COPIES, r.MAX_BYTES, r.FREE_FLOOR),
                         (policy['max_full_copies'], policy['max_allocated_bytes'], policy['minimum_free_after_reservations']))
        self.assertEqual(set(policy['protected_classes']), r.PROTECTED)

    def test_publication_ownership_is_journal_bound(self):
        package = self._package(); catalog = json.loads(self._catalog().read_text())
        identity, receipt, error = r._metadata(package)
        self.assertIsNone(error); self.assertTrue(r._ownership(package, catalog['artifacts'][str(package)], receipt))
        copy = dict(catalog['artifacts'][str(package)]); copy['inode'] += 1
        self.assertFalse(r._ownership(package, copy, receipt))

    def test_unowned_legacy_counts_toward_cap_and_is_never_deletable(self):
        package, survivor = self._ready()
        with r.locked(self._catalog()) as catalog:
            del catalog['artifacts'][str(package)]
        p = self._plan()
        self.assertEqual(p['DELETABLE_BYTES'], 0); self.assertEqual(p['full_copies'], 2)
        self.assertGreater(p['UNKNOWN_BYTES'], 0)
        with patch.object(r, 'MAX_BYTES', self._plan()['BEFORE_BYTES']):
            with self.assertRaisesRegex(ValueError, 'cap exceeded'):
                r.reserve_archive(self.destination, 1)
        self.assertTrue(package.exists())

    def test_eight_copy_and_byte_caps_apply_independently(self):
        self._package()
        self.identity['source']['commit_sha'] = 'c' * 40; self._manifest(); self._package()
        # Pending objects cannot be evicted to admit another publication.
        for cap, value in [('MAX_COPIES', 2), ('MAX_BYTES', self._plan()['BEFORE_BYTES'])]:
            with self.subTest(cap=cap), patch.object(r, cap, value):
                with self.assertRaisesRegex(ValueError, 'cap exceeded'):
                    r.reserve_archive(self.destination, 1)

    def test_reservations_serialize_across_different_roots(self):
        self._package()
        with patch.object(r, 'MAX_COPIES', 2):
            path, token = r.reserve_archive(self.destination, 1024)
            try:
                with self.assertRaisesRegex(ValueError, 'cap exceeded'):
                    r.reserve_archive(self.root / 'other', 1024)
            finally:
                r.cancel_publication(path, token)

    def test_atomic_build_reserves_before_builder_and_releases_on_failure(self):
        with r.reserved_build(self.destination, 1, archive_copy=True):
            catalog = json.loads(self._catalog().read_text()); self.assertEqual(len(catalog['leases']), 1)
            r.require_build_lease(self.destination)
            with patch.object(r, 'MAX_COPIES', 1):
                with self.assertRaisesRegex(ValueError, 'atomic build admission'):
                    with r.reserved_build(self.root / 'other', 1, archive_copy=True):
                        self.fail('second builder spawned')
        self.assertEqual(json.loads(self._catalog().read_text())['leases'], {})
        with self.assertRaisesRegex(RuntimeError, 'injected builder failure'):
            with r.reserved_build(self.destination, 1, archive_copy=True):
                raise RuntimeError('injected builder failure')
        self.assertEqual(json.loads(self._catalog().read_text())['leases'], {})

    def test_fifteen_gib_floor_blocks_before_builder(self):
        with patch.object(r.shutil, 'disk_usage', return_value=SimpleNamespace(free=r.FREE_FLOOR)):
            with self.assertRaisesRegex(ValueError, '15-GiB reserve'):
                r.build_preflight(self.destination, 1, archive_copy=False)
            with self.assertRaisesRegex(ValueError, 'insufficient disk'):
                with r.reserved_build(self.destination, 1, archive_copy=False):
                    self.fail('builder invoked under disk floor')

    def test_missing_context_and_protected_or_active_objects_fail_closed(self):
        package, survivor = self._ready()
        with patch('scripts.retention_governance.validate_snapshot', return_value=False):
            self.assertEqual(self._plan()['DELETABLE_BYTES'], 0)
        with patch.object(r, '_inactive', return_value=False):
            self.assertEqual(self._plan()['DELETABLE_BYTES'], 0)
        with patch.object(r, '_publisher_live', return_value=True):
            self.assertEqual(self._plan()['DELETABLE_BYTES'], 0)
        p = self._plan(); self.assertGreater(p['PROTECTED_BYTES'], 0)
        self.assertNotIn(str(survivor), [v['path'] for v in p['entries'] if v['classification'] == 'DELETABLE'])

    def test_shape_drift_and_hardlinks_are_unknown(self):
        package, _ = self._ready(); extra = package / 'foreign'; extra.write_text('preserve')
        self.assertEqual(self._plan()['DELETABLE_BYTES'], 0); extra.unlink()
        exe = package / 'Integra.app/Contents/MacOS/Integra'; alias = self.root / 'foreign-link'
        os.link(exe, alias)
        self.assertEqual(self._plan()['DELETABLE_BYTES'], 0)

    def test_cleanup_rehash_rejects_same_size_payload_tampering(self):
        package, _ = self._ready(); plan = self._plan()
        p = package / 'Integra.app/Contents/MacOS/Integra'
        content = p.read_bytes(); p.write_bytes(b'X' * len(content))
        with self.assertRaisesRegex(ValueError, 'bundle bytes differ'):
            r.cleanup(self._catalog(), plan)
        self.assertTrue(package.exists())

    def test_cleanup_deletes_only_owned_terminal_and_protects_survivor(self):
        package, survivor = self._ready(); deleted = r.cleanup(self._catalog(), self._plan())
        self.assertEqual(deleted, [str(package)]); self.assertFalse(package.exists())
        self.assertEqual(archive.verify_archive(survivor)['status'], 'COMPLETE')
        self.assertEqual(json.loads(self._catalog().read_text())['deletions'], {})

    def test_historical_mass_delete_gate_cannot_be_bypassed_by_authority_string(self):
        package, _ = self._ready()
        with r.locked(self._catalog()) as catalog:
            catalog['artifacts'][str(package)]['historical'] = True
        with self.assertRaisesRegex(ValueError, 'Human Gate'):
            r.cleanup(self._catalog(), self._plan(), historical_authority='policy accepted')
        self.assertTrue(package.exists())

    def test_cleanup_crash_after_one_unlink_has_durable_bounded_recovery(self):
        package, survivor = self._ready(); original = os.unlink; calls = 0
        def interrupt(path, **kwargs):
            nonlocal calls
            if kwargs.get('dir_fd') is not None:
                calls += 1
                if calls == 2:
                    raise KeyboardInterrupt('simulated process death')
            return original(path, **kwargs)
        with patch.object(executor.os, 'unlink', side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt):
                r.cleanup(self._catalog(), self._plan())
        catalog = json.loads(self._catalog().read_text()); self.assertEqual(len(catalog['deletions']), 1)
        job = next(iter(catalog['deletions'].values()))
        self.assertEqual(job['phase'], 'DELETING'); self.assertFalse(package.exists())
        self.assertTrue(Path(job['trash']).exists())
        self.assertEqual(r.recover_cleanup(self._catalog()), [str(package)])
        self.assertTrue(survivor.exists()); self.assertEqual(json.loads(self._catalog().read_text())['deletions'], {})

    def test_crash_recovery_preserves_foreign_addition(self):
        package, _ = self._ready()
        with patch.object(executor.os, 'unlink', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                r.cleanup(self._catalog(), self._plan())
        job = next(iter(json.loads(self._catalog().read_text())['deletions'].values()))
        foreign = Path(job['trash']) / 'foreign'; foreign.write_text('never delete')
        with self.assertRaisesRegex(ValueError, 'foreign/replaced/unrecorded'):
            r.recover_cleanup(self._catalog())
        self.assertEqual(foreign.read_text(), 'never delete')

    def test_prepared_crash_after_rename_rehashes_before_resuming(self):
        package, _ = self._ready(); original = archive._publish
        def interrupted(source, destination):
            original(source, destination)
            raise KeyboardInterrupt('crash after atomic withdrawal')
        with patch.object(archive, '_publish', side_effect=interrupted):
            with self.assertRaises(KeyboardInterrupt):
                r.cleanup(self._catalog(), self._plan())
        job = next(iter(json.loads(self._catalog().read_text())['deletions'].values()))
        self.assertEqual(job['phase'], 'PREPARED')
        target = Path(job['trash']) / 'Integra.app/Contents/MacOS/Integra'
        target.write_bytes(b'X' * target.stat().st_size)
        with self.assertRaisesRegex(ValueError, 'remaining bytes changed'):
            r.recover_cleanup(self._catalog())
        self.assertTrue(target.exists())

    def test_protection_drift_before_withdrawal_and_resume_preserves_bytes(self):
        package, _ = self._ready(); planned = self._plan()
        with patch('scripts.retention_governance.validate_snapshot', return_value=False):
            with self.assertRaisesRegex(ValueError, 'plan/protection changed'):
                r.cleanup(self._catalog(), planned)
        self.assertTrue(package.exists())
        with patch.object(executor.os, 'unlink', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                r.cleanup(self._catalog(), self._plan())
        job = next(iter(json.loads(self._catalog().read_text())['deletions'].values()))
        with patch('scripts.retention_governance.validate_snapshot', return_value=False):
            with self.assertRaisesRegex(ValueError, 'context is unavailable'):
                r.recover_cleanup(self._catalog())
        self.assertTrue(Path(job['trash']).exists())

    def test_mutation_after_full_verification_cannot_become_journal_authority(self):
        package, _ = self._ready(); planned = self._plan(); original = executor._entries
        def changed(r0, path):
            p = path / 'Integra.app/Contents/MacOS/Integra'
            p.write_bytes(b'X' * p.stat().st_size)
            return original(r0, path)
        with patch.object(executor, '_entries', side_effect=changed):
            with self.assertRaisesRegex(ValueError, 'remaining bytes changed'):
                r.cleanup(self._catalog(), planned)
        self.assertTrue(package.exists())

    def test_inventory_mutation_cannot_become_publisher_or_journal_authority(self):
        package, _ = self._ready(); planned = self._plan(); original = executor._entries
        def changed(r0, path):
            inventory = path / 'inventory.json'; value = json.loads(inventory.read_text())
            value[0]['mode'] = 0o700; inventory.write_text(json.dumps(value))
            return original(r0, path)
        with patch.object(executor, '_entries', side_effect=changed):
            with self.assertRaisesRegex(ValueError, 'metadata differs from publisher'):
                r.cleanup(self._catalog(), planned)
        self.assertTrue(package.exists())

    def test_cross_root_exact_package_reuse_does_not_duplicate_or_adopt(self):
        receipt = self._create(); destination = self.root / 'another-root'
        with patch.object(archive, '_publish', side_effect=AssertionError('duplicate publication')):
            reused = archive.create_archive(self.app, destination)
        self.assertEqual(reused, receipt); self.assertFalse(destination.exists())
        self.assertEqual(len(json.loads(self._catalog().read_text())['artifacts']), 1)

    def test_finish_cannot_attest_legacy_or_wrong_destination(self):
        receipt = self._create(); package = Path(receipt['archive_path'])
        path, token = r.reserve_archive(self.destination, 1, destination=self.root / 'wrong', identity={k: receipt[k] for k in archive.IDENTITY_KEYS})
        try:
            with self.assertRaisesRegex(ValueError, 'destination/identity'):
                r.finish_publication(path, token, receipt)
        finally:
            r.cancel_publication(path, token)
        self.assertTrue(package.exists())

    def test_direct_builder_requires_admission_lease(self):
        with self.assertRaisesRegex(ValueError, 'atomic retention/disk admission'):
            r.require_build_lease(self.destination)

    def test_admitted_builder_cannot_target_archive_or_unowned_durable_output(self):
        with r.reserved_build(self.destination, 1, archive_copy=False):
            with self.assertRaisesRegex(ValueError, 'reserved owned workspace'):
                r.require_build_lease(self.destination, output=self.destination)

    def test_published_crash_recovery_requires_prepublication_inode(self):
        with patch.object(r, 'finish_publication', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self._create()
        package = self._expected_path(); self.assertTrue(package.exists())
        with patch.object(r.admission, '_live', return_value=False):
            with r.locked(self._catalog()) as catalog:
                r._recover_leases(catalog)
                self.assertEqual(catalog['leases'], {})
                self.assertIn(str(package), catalog['artifacts'])
                self.assertEqual(catalog['artifacts'][str(package)]['status'], 'AWAITING_OWNER_ACCEPTANCE')

    def test_publication_collision_releases_own_slot_without_adopting_collision(self):
        original = archive._publish
        def collide(stage, destination):
            destination.mkdir(); (destination / 'foreign').write_text('preserve')
            original(stage, destination)
        with patch.object(archive, '_publish', side_effect=collide):
            with self.assertRaises(ValueError):
                self._create()
        catalog = json.loads(self._catalog().read_text())
        self.assertEqual(catalog['leases'], {}); self.assertEqual(catalog['artifacts'], {})
        self.assertEqual((self._expected_path() / 'foreign').read_text(), 'preserve')


if __name__ == '__main__':
    unittest.main()
