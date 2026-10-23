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
    def setUp(self):
        fixtures.CandidateArchiveTests.setUp(self)
        self._install_canonical_fixture()

    def _install_canonical_fixture(self):
        """Isolate Issue #212 lifecycle mechanics from the real registry."""
        from scripts import candidate_protection_gate as gate
        for fixture_patch in (
            patch.object(archive, 'MANAGED_BASE', self.root),
            patch.object(gate, 'require_archive_publication', return_value=None),
            patch.object(gate, 'require_deletion', return_value='fixture-deletion-lease'),
            patch.object(gate, 'require_deletion_continuation', return_value=None),
            patch.object(r, '_context_valid', return_value=True),
            patch.object(r, 'refresh_protection', return_value=None),
        ):
            fixture_patch.start(); self.addCleanup(fixture_patch.stop)
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
            for sequence, item in enumerate((package, survivor), start=1):
                item_receipt = archive.verify_archive(item)
                info = item.stat()
                catalog['artifacts'][str(item)] = {
                    **{key: item_receipt[key] for key in ('candidate_id', 'bundle_digest', 'manifest_digest', 'inventory_sha256')},
                    'complete_sha256': r._sha(item / 'COMPLETE.json'),
                    'owner_uid': os.getuid(), 'device': info.st_dev, 'inode': info.st_ino,
                    'publisher_run_id': 'fixture', 'publisher_pid': os.getpid(),
                    'publisher_start_token': 'dead fixture publisher',
                    'publisher_completed': True, 'publication_sequence': sequence,
                    'status': 'AWAITING_OWNER_ACCEPTANCE',
                    'historical': False,
                }
            catalog['protection'] = {'protected': {cid: ['CURRENT', 'LATEST_ACCEPTED_BASELINE', 'CONFIRMED_ROLLBACK', 'CONFIRMED_RECOVERY']},
                'inputs': {str(survivor / 'COMPLETE.json'): r._sha(survivor / 'COMPLETE.json')},
                'authoritative_snapshot': {'fixture': True}, 'selected_archives': {cid: str(survivor)},
                'verified_survivors': {cid: receipt}}
            r.disposition(catalog, package, 'SUPERSEDED', 'fixture exact retirement authority')
            for v in catalog['artifacts'].values():
                v['publisher_start_token'] = 'dead fixture publisher'
        for fixture_patch in (patch.object(r, '_inactive', return_value=True),):
            fixture_patch.start(); self.addCleanup(fixture_patch.stop)

    def _plan(self):
        return r.plan(json.loads(self._catalog().read_text()), free_bytes=64 * 1024**3)

    def test_policy_limits_match_owner_machine_record(self):
        policy = json.loads((r.ROOT / 'state/candidate_retention_policy_v1.json').read_text())
        self.assertEqual((r.MAX_COPIES, r.MAX_BYTES, r.FREE_FLOOR),
                         (policy['max_full_copies'], policy['max_allocated_bytes'], policy['minimum_free_after_reservations']))
        self.assertEqual(set(policy['protected_classes']), r.PROTECTED)

    def test_context_accepts_all_protected_roles_and_selected_archive_subset(self):
        selected = self.root / 'selected'; selected.mkdir()
        complete = selected / 'COMPLETE.json'; complete.write_text('{"status":"COMPLETE"}\n')
        selected_id = 'candidate-selected'; missing_id = 'candidate-historical-gap'
        registry = {'selected_survivors': {selected_id: 'selected', missing_id: None}}
        audit = {'authority_state': 'COMPLETE', 'registry_sha256': 'fixture-registry',
                 'protected_identities': {selected_id: {}, missing_id: {}},
                 'canonical': {'canonical_lifecycles': {'fixture': 'event'},
                               'standing_policy': {'fixture': 'policy'}}}
        context = {
            'protected': {selected_id: ['CURRENT'], missing_id: ['EXPLICIT_GOVERNANCE_PROVENANCE']},
            'inputs': {str(complete): r._sha(complete)},
            'selected_archives': {selected_id: str(selected)},
            'verified_survivors': {selected_id: {'fixture': 'receipt'}},
            'registry_sha256': 'fixture-registry',
            'canonical_lifecycles': {'fixture': 'event'},
            'standing_policy': {'fixture': 'policy'},
        }
        self.assertTrue(r._context_matches(context, registry, audit, self.root))
        context['protected'].pop(missing_id)
        self.assertFalse(r._context_matches(context, registry, audit, self.root))

    def test_nested_legacy_root_is_collapsed_without_losing_catalog_records(self):
        validation = self.root / 'Validation'
        prior_run = validation / 'integra-212-native-example'
        catalog = r._empty()
        catalog['roots'] = [str(prior_run)]
        catalog['artifacts'][str(prior_run / 'candidate')] = {'preserve': True}

        r.register_root(catalog, validation)

        self.assertEqual(catalog['roots'], [str(validation)])
        self.assertEqual(catalog['artifacts'][str(prior_run / 'candidate')], {'preserve': True})
        r.register_root(catalog, prior_run)
        self.assertEqual(catalog['roots'], [str(validation)])

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
        with patch.object(r, '_context_valid', return_value=False):
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

    def test_rotation_deletes_only_the_oldest_proven_eligible_archive(self):
        oldest, survivor = self._ready()
        self.identity['source']['commit_sha'] = 'd' * 40; self._manifest()
        with patch.object(r, 'maintenance', return_value=[]):
            newer = self._package()
        with r.locked(self._catalog()) as catalog:
            r.disposition(catalog, newer, 'SUPERSEDED', 'fixture newer terminal authority')
        planned = self._plan()
        self.assertEqual(planned['rotation_strategy'], 'OLDEST_PROVEN_ELIGIBLE_FIRST')
        self.assertEqual(planned['rotation_target']['path'], str(oldest))
        self.assertLess(planned['rotation_target']['publication_sequence'],
                        next(row['publication_sequence'] for row in planned['entries']
                             if row['path'] == str(newer)))
        self.assertEqual(r.cleanup(self._catalog(), planned), [str(oldest)])
        self.assertFalse(oldest.exists()); self.assertTrue(newer.exists())
        self.assertEqual(archive.verify_archive(survivor)['status'], 'COMPLETE')

    def test_unproven_rotation_order_and_protected_oldest_fail_closed(self):
        oldest, survivor = self._ready()
        with r.locked(self._catalog()) as catalog:
            del catalog['artifacts'][str(oldest)]['publication_sequence']
        planned = self._plan()
        row = next(row for row in planned['entries'] if row['path'] == str(oldest))
        self.assertEqual(row['classification'], 'UNKNOWN')
        self.assertEqual(row['retention_order'], 'UNPROVEN')
        self.assertIsNone(planned['rotation_target'])
        self.assertTrue(oldest.exists()); self.assertTrue(survivor.exists())

    def test_exact_withdrawal_can_retire_without_publication_order(self):
        package, survivor = self._ready()
        with r.locked(self._catalog()) as catalog:
            record = catalog['artifacts'][str(package)]
            del record['publication_sequence']
            record['status'] = 'WITHDRAWN_SUPERSEDED'
            record['disposition_ref'] = 'fixture exact withdrawal authority'
        identity = {key: json.loads((package / 'COMPLETE.json').read_text())[key]
                    for key in ('candidate_id', 'bundle_digest', 'manifest_digest')}
        self.assertEqual(r.cleanup_exact(self._catalog(), identity), [str(package)])
        self.assertFalse(package.exists())
        self.assertEqual(archive.verify_archive(survivor)['status'], 'COMPLETE')

    def test_protected_oldest_is_not_selected_for_rotation(self):
        oldest, _ = self._ready()
        self.identity['source']['commit_sha'] = 'd' * 40; self._manifest()
        with patch.object(r, 'maintenance', return_value=[]):
            newer = self._package()
        with r.locked(self._catalog()) as catalog:
            old_id = catalog['artifacts'][str(oldest)]['candidate_id']
            catalog['protection']['protected'][old_id] = ['AWAITING_OWNER_ACCEPTANCE']
            r.disposition(catalog, newer, 'SUPERSEDED', 'fixture newer terminal authority')
        planned = self._plan()
        old_row = next(row for row in planned['entries'] if row['path'] == str(oldest))
        self.assertEqual(old_row['classification'], 'PROTECTED')
        self.assertEqual(planned['rotation_target']['path'], str(newer))

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
        with patch.object(r, '_context_valid', return_value=False):
            with self.assertRaisesRegex(ValueError, 'plan/protection changed'):
                r.cleanup(self._catalog(), planned)
        self.assertTrue(package.exists())
        with patch.object(executor.os, 'unlink', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                r.cleanup(self._catalog(), self._plan())
        job = next(iter(json.loads(self._catalog().read_text())['deletions'].values()))
        with patch.object(r, '_context_valid', return_value=False):
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
