"""Capacity integration uses real gates and tiny isolated filesystem packages.

Only external canonical facts, activity and disk availability are simulated.
No user archive, installed application or mutable user data is a test target.
"""
from __future__ import annotations

import base64
import copy
import json
import os
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from integra_core.candidate_identity import candidate_id, canonical_bytes, tree_sha256
from scripts import candidate_archive as archive
from scripts import candidate_protection_audit as protection
from scripts import candidate_protection_gate as gate
from scripts import candidate_retention as retention


@unittest.skipUnless(hasattr(Path.home().stat(), 'st_birthtime'),
                     'physical APFS creation-time integration requires macOS')
class CapacityDeletionSafetyTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='.integra-capacity-test-', dir=Path.home())
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.base = self.root / 'Library/Application Support/Integra'
        self.destination = self.base / 'Build Archive'
        self.destination.mkdir(parents=True)
        self.catalog_path = self.base / 'Retention' / f'catalog-{os.getuid()}.json'
        self.app = self.root / 'source/Integra.app'
        self.executable = self.app / 'Contents/MacOS/Integra'
        self.executable.parent.mkdir(parents=True)
        self.executable.write_bytes(b'isolated synthetic executable\n')
        self.executable.chmod(0o755)
        self.manifest = self.app / archive.EMBEDDED
        self.manifest.parent.mkdir(parents=True)
        self.next_source = 100
        self.patches = [
            patch.object(Path, 'home', return_value=self.root),
            patch.object(archive, 'MANAGED_BASE', self.base),
            patch.object(retention, '_inactive', return_value=True),
            patch.object(shutil, 'disk_usage', return_value=SimpleNamespace(
                total=128 * 1024**3, used=32 * 1024**3, free=96 * 1024**3)),
            patch.object(protection, 'ROOT', self.root),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

        # Bootstrap physical publisher fixtures outside managed roots. Their
        # exact metadata and physical custody are then recorded in the isolated
        # catalog, as input facts rather than a mocked admission result.
        self.packages = []
        self.identities = []
        self.original_receipts = []
        with retention.locked(self.catalog_path) as catalog:
            for number in range(8):
                self.write_manifest(number + 1)
                receipt = archive.create_archive(self.app, self.root / 'seed')
                source = Path(receipt['archive_path'])
                package = self.destination / source.parent.name / source.name
                package.parent.mkdir()
                source.rename(package)
                identity = {key: receipt[key] for key in protection.IDENTITY}
                info = package.stat()
                catalog['artifacts'][str(package)] = {
                    **identity, 'inventory_sha256': receipt['inventory_sha256'],
                    'complete_sha256': protection.sha((package / 'COMPLETE.json').read_bytes()),
                    'owner_uid': os.getuid(), 'device': info.st_dev, 'inode': info.st_ino,
                    'publisher_run_id': f'fixture-{number}', 'publisher_pid': os.getpid(),
                    'publisher_start_token': retention.admission._start(os.getpid()),
                    'publisher_completed': True, 'historical': False,
                    'status': 'AWAITING_OWNER_ACCEPTANCE', 'publication_sequence': number + 1,
                    'publication_recorded_at': f'2020-01-01T00:00:{number:02d}+00:00',
                }
                self.packages.append(package)
                self.identities.append(identity)
                self.original_receipts.append(receipt)
            catalog['publication_sequence_high_watermark'] = 8

        current_id = 'current-fixture'
        self.current = {'current_id': current_id, 'records': [
            {'baseline_id': 'previous-fixture', 'candidate': self.identities[6]},
            {'baseline_id': current_id, 'candidate': self.identities[7]},
        ]}
        current_path = self.root / 'state/current_product_baseline_v2.json'
        current_path.parent.mkdir()
        current_path.write_text(json.dumps(self.current))
        self.registry = {
            'schema_version': '1.0', 'artifact_type': 'integra.candidate_protection_registry',
            'status': 'PRODUCT_OWNER_AUTHORIZED_ACTIVE',
            'activation_authority_ref': 'fixture-owner', 'decision_authority_ref': 'fixture-owner',
            'decision_token_sha256': 'fixture-decision',
            'promotion_contract_integration_ref': protection.INTEGRATION_REF,
            'deletion_enabled': False, 'deletion_authorizations': {},
            'managed_roots': sorted(protection.ROOT_NAMES),
            'canonical_current': {**self.identities[7], 'current_id': current_id,
                                  'path': 'state/current_product_baseline_v2.json',
                                  'sha256': protection.sha(current_path.read_bytes())},
            'latest_accepted_candidate_id': self.identities[7]['candidate_id'],
            'rollback': {**self.identities[6], 'confirmation_ref': 'fixture-owner'},
            'recovery': {**self.identities[7], 'confirmation_ref': 'fixture-owner'},
            'recovery_selection': None, 'historical_gaps': [],
            'proposed': [], 'accepted_unpromoted': [], 'explicit_governance_pins': {},
            'selected_survivors': {
                self.identities[n]['candidate_id']: self.packages[n].relative_to(self.base).as_posix()
                for n in (6, 7)},
            'limits': {'max_full_copies': 8, 'max_attributed_bytes': 20 * 1024**3,
                       'minimum_free_after_reservations': 15 * 1024**3},
        }
        policy_bytes = (Path(__file__).resolve().parents[1] /
                        'state/candidate_archive_rotation_policy_v2.json').read_bytes()
        self.policy = {**json.loads(policy_bytes), 'sha256': protection.sha(policy_bytes)}
        self.canonical = {
            'current_sha256': self.registry['canonical_current']['sha256'],
            'decision_authority_ref': 'fixture-owner', 'decision_token_sha256': 'fixture-decision',
            'decision_token': ('PRODUCT_OWNER_AUTHORIZATION: FIXTURE '
                               'EXPLICIT_GOVERNANCE_PINS={} DELETION_AUTHORIZATIONS={} '
                               'DELETION_ENABLED=false'),
            'historical_receipts': {}, 'canonical_lifecycles': {},
            'rotation_policy': self.policy,
        }
        self.registry_path = self.root / 'state/candidate_protection_registry_v1.json'
        self.registry_path.write_text(json.dumps(self.registry))
        for item in (
            patch.object(protection, 'REGISTRY', self.registry_path),
            patch.object(protection, 'fetch_canonical', side_effect=lambda _registry: (
                copy.deepcopy(self.current), {}, copy.deepcopy(self.canonical))),
        ):
            item.start()
            self.addCleanup(item.stop)

    def write_manifest(self, number):
        identity = {'source': {'commit_sha': f'{number:040x}'},
                    'execution': {'gui_python': {'path': '/fixture/python', 'sha256': 'b' * 64}}}
        value = {'schema_version': '1.0', 'candidate_id': candidate_id(identity),
                 'identity_sha256': candidate_id(identity).removeprefix('candidate-v1-'),
                 'identity': identity,
                 'bundle': {'digest_algorithm': 'sha256-tree-excluding-candidate-manifest',
                            'digest': tree_sha256(self.app, exclude={archive.EMBEDDED})},
                 'build': {'timestamp': 'fixture'}}
        self.manifest.write_bytes(canonical_bytes(value) + b'\n')

    def add_cache(self, package):
        added = package / 'Integra.app/Contents/Resources/__pycache__/added.pyc'
        added.parent.mkdir(exist_ok=True)
        added.write_bytes(b'additional generated cache absent from historical inventory')
        return added

    def catalog(self):
        return json.loads(self.catalog_path.read_bytes())

    def publish_next(self):
        self.write_manifest(self.next_source)
        self.next_source += 1
        # Both standalone publication and the ordinary build preflight route
        # run production admission; no actual native compilation is needed.
        receipt = archive.create_archive(self.app, self.destination)
        self.assertEqual(archive.verify_archive(Path(receipt['archive_path']))['status'], 'COMPLETE')
        self.assertEqual(len(retention._packages(self.catalog())), 8)
        self.assertFalse(self.catalog()['deletions'])
        return receipt

    def test_added_cache_on_oldest_rotates_publishes_and_reloads_twice(self):
        old = self.packages[0]
        original_inventory = (old / 'inventory.json').read_bytes()
        original_complete = (old / 'COMPLETE.json').read_bytes()
        added = self.add_cache(old)
        with self.assertRaisesRegex(ValueError, 'inventory differs'):
            archive.verify_archive(old)
        self.publish_next()
        self.assertFalse(old.exists())
        retired = next(iter(self.catalog()['retirements'].values()))
        self.assertEqual(retired['state'], 'RETIRED_NOT_AVAILABLE')
        self.assertFalse(retired['physical_available'])
        self.assertEqual(retired['verification_evidence']['method'], 'DELETION_SNAPSHOT')
        self.assertEqual(base64.b64decode(retired['retained_inventory_json_base64']), original_inventory)
        self.assertEqual(base64.b64decode(retired['retained_complete_base64']), original_complete)
        self.assertIn(added.relative_to(old).as_posix(), {e['path'] for e in retired['retained_inventory']})
        self.assertIn(self.identities[0]['candidate_id'], protection.load_rotation_receipts(self.base, self.policy))
        self.publish_next()
        self.assertFalse(self.packages[1].exists())
        self.assertEqual(len(protection.load_rotation_receipts(self.base, self.policy)), 2)

    def test_changed_executable_can_be_retired_without_asserting_archive_integrity(self):
        oldest = self.packages[0]
        executable = oldest / 'Integra.app/Contents/MacOS/Integra'
        executable.write_bytes(b'changed noncache executable bytes')
        with self.assertRaises(ValueError):
            archive.verify_archive(oldest)
        observed_sha = protection.sha(executable.read_bytes())
        self.publish_next()
        self.assertFalse(oldest.exists())
        retired = next(iter(self.catalog()['retirements'].values()))
        observed = next(entry for entry in retired['retained_inventory']
                        if entry['path'] == 'Integra.app/Contents/MacOS/Integra')
        self.assertEqual(observed['sha256'], observed_sha)
        self.assertEqual(retired['verification_evidence']['method'], 'DELETION_SNAPSHOT')
        self.assertEqual(retired['verification_evidence']['archival_integrity'], 'NOT_ASSERTED')
        self.assertIn(self.identities[0]['candidate_id'],
                      protection.load_rotation_receipts(self.base, self.policy))

    def test_deletion_snapshot_loader_rejects_tampered_retained_evidence(self):
        self.add_cache(self.packages[0])
        self.publish_next()
        transaction, original = next(iter(self.catalog()['retirements'].items()))
        self.assertEqual(original['verification_evidence']['method'], 'DELETION_SNAPSHOT')
        for mutation in ('historical_inventory', 'observed_inventory', 'observed_hash'):
            with self.subTest(mutation=mutation):
                tampered = copy.deepcopy(original)
                if mutation == 'historical_inventory':
                    historical = base64.b64decode(tampered['retained_inventory_json_base64'])
                    # Even semantically identical JSON must keep its exact
                    # historical hash bound by COMPLETE.json.
                    tampered['retained_inventory_json_base64'] = base64.b64encode(
                        historical + b'\n').decode('ascii')
                elif mutation == 'observed_inventory':
                    entry = next(item for item in tampered['retained_inventory']
                                 if item['path'].endswith('/added.pyc'))
                    entry['sha256'] = '0' * 64
                else:
                    tampered['verification_evidence']['rotation_inventory_sha256'] = '0' * 64
                with retention.locked(self.catalog_path) as catalog:
                    catalog['retirements'][transaction] = tampered
                with self.assertRaises(ValueError):
                    protection.load_rotation_receipts(self.base, self.policy)
                with retention.locked(self.catalog_path) as catalog:
                    catalog['retirements'][transaction] = copy.deepcopy(original)
                self.assertIn(self.identities[0]['candidate_id'],
                              protection.load_rotation_receipts(self.base, self.policy))

    def test_unselected_survivor_cache_does_not_block_admission(self):
        added = self.add_cache(self.packages[3])
        before = added.read_bytes()
        self.publish_next()
        self.assertFalse(self.packages[0].exists())
        self.assertEqual(added.read_bytes(), before)
        with self.assertRaisesRegex(ValueError, 'inventory differs'):
            archive.verify_archive(self.packages[3])

    def test_selected_survivor_drift_is_not_false_verified_or_admission_blocker(self):
        self.add_cache(self.packages[6])
        self.publish_next()
        with self.assertRaisesRegex(ValueError, 'INTEGRITY_FAIL'):
            gate._snapshot()
        _, capacity = gate._snapshot(purpose='CAPACITY')
        self.assertEqual(capacity['authority_state'], 'COMPLETE')
        self.assertFalse(capacity['promotion_ready'])
        self.assertFalse(any(row['verified_protected_archive'] for row in capacity['entries']))

    def test_build_preflight_and_atomic_reservation_accept_historical_drift(self):
        self.add_cache(self.packages[6])
        snapshot = retention.build_preflight(self.destination, 1024 * 1024)
        self.assertEqual(snapshot['full_copies'], 7)
        self.assertFalse(self.packages[0].exists())
        with retention.reserved_build(self.destination, 1024 * 1024, archive_copy=True):
            self.assertTrue(self.catalog()['leases'])
        self.assertFalse(self.catalog()['leases'])

    def test_capacity_admission_preserves_default_strict_plan_when_bytes_match(self):
        retention.build_preflight(self.destination, 1024 * 1024)
        catalog = self.catalog()
        self.assertEqual(catalog['protection']['verification_purpose'], 'CAPACITY')
        strict = retention.plan(catalog)
        self.assertTrue(strict['protection_context_valid'])
        self.assertEqual(strict['full_copies'], 7)
        # The default still obtains fresh integrity evidence: persisted
        # capacity metadata cannot bless a newly changed selected survivor.
        self.add_cache(self.packages[6])
        self.assertFalse(retention.plan(self.catalog())['protection_context_valid'])
        self.assertTrue(retention.plan(self.catalog(), purpose='CAPACITY')['protection_context_valid'])

    def test_legacy_six_birthtimes_and_two_sequences_keep_approved_order(self):
        with retention.locked(self.catalog_path) as catalog:
            for package in self.packages[:6]:
                del catalog['artifacts'][str(package)]
            for package in self.packages[6:]:
                catalog['artifacts'][str(package)].pop('publication_recorded_at')
        expected = min(range(6), key=lambda n: (
            self.packages[n].stat().st_birthtime, self.identities[n]['candidate_id']))
        self.add_cache(self.packages[expected])
        self.publish_next()
        self.assertFalse(self.packages[expected].exists())
        order = self.catalog()['rotation_order_v2']['entries']
        self.assertEqual([entry['order_provenance']['source'] for entry in order[:6]],
                         ['APFS_DIRECTORY_BIRTHTIME_OBSERVED_NOW'] * 6)
        self.assertEqual([entry['order_provenance']['publisher_sequence'] for entry in order[6:]],
                         [7, 8])

    def test_active_oldest_is_not_replaced_by_a_younger_deletion(self):
        with patch.object(retention, '_inactive', side_effect=lambda package: Path(package) != self.packages[0]):
            with self.assertRaises(ValueError):
                self.publish_next()
        self.assertTrue(all(package.exists() for package in self.packages))
        self.assertFalse(self.catalog().get('retirements'))

    def test_wrong_manifest_identity_blocks_rotation(self):
        target = self.packages[0] / 'Integra.app' / archive.EMBEDDED
        target.write_bytes((self.packages[1] / 'Integra.app' / archive.EMBEDDED).read_bytes())
        with self.assertRaises(ValueError):
            self.publish_next()
        self.assertTrue(all(package.exists() for package in self.packages))

    def test_payload_links_cannot_escape_into_user_files(self):
        victim = self.root / 'user-file.txt'
        victim.write_bytes(b'untouched user fixture')
        target = self.packages[0] / 'Integra.app/Contents/Resources/link'
        for kind in ('symlink', 'hardlink'):
            with self.subTest(kind=kind):
                if kind == 'symlink':
                    target.symlink_to(victim)
                else:
                    os.link(victim, target)
                with self.assertRaises((ValueError, OSError)):
                    self.publish_next()
                self.assertEqual(victim.read_bytes(), b'untouched user fixture')
                self.assertTrue(all(package.exists() for package in self.packages))
                target.unlink()

    def test_corrupt_incoming_bundle_still_fails_before_rotation(self):
        self.write_manifest(100)
        self.executable.write_bytes(b'changed after manifest binding')
        with self.assertRaisesRegex(ValueError, 'candidate bundle bytes differ'):
            archive.create_archive(self.app, self.destination)
        self.assertTrue(all(package.exists() for package in self.packages))

    def test_installed_application_path_cannot_be_a_capacity_target(self):
        installed = self.root / 'Applications/Integra.app'
        installed.mkdir(parents=True)
        marker = installed / 'user-installed-bytes'
        marker.write_bytes(b'unchanged installation fixture')
        with self.assertRaisesRegex(ValueError, 'outside managed authority'):
            gate.require_capacity_rotation(installed.parent)
        self.assertEqual(marker.read_bytes(), b'unchanged installation fixture')
        self.assertTrue(all(package.exists() for package in self.packages))

    def test_rename_interruption_recovers_the_real_capacity_journal(self):
        self.add_cache(self.packages[0])
        original_publish = archive._publish

        def crash(source, destination):
            original_publish(source, destination)
            if Path(destination).name.startswith('.retention-trash-'):
                raise RuntimeError('injected interruption after rename')

        with patch.object(archive, '_publish', side_effect=crash):
            with self.assertRaisesRegex(RuntimeError, 'after rename'):
                retention.maintenance(self.destination, reason='FIXTURE', need_slot=True)
        self.assertFalse(self.packages[0].exists())
        self.assertEqual(len(self.catalog()['deletions']), 1)
        self.assertEqual(retention.recover_cleanup(self.catalog_path), [str(self.packages[0])])
        self.assertFalse(self.catalog()['deletions'])
        self.assertEqual(len(protection.load_rotation_receipts(self.base, self.policy)), 1)
        self.publish_next()

    def test_prepared_legacy_lease_recovers_with_its_original_strict_contract(self):
        original_gate = gate.require_capacity_rotation
        original_publish = archive._publish

        def strict_gate(package, **_kwargs):
            # Exercise the real old-format lease issuer. No admission or
            # continuation evidence is replaced by synthetic success.
            return original_gate(package, purpose='INTEGRITY')

        def crash(source, destination):
            if Path(destination).name.startswith('.retention-trash-'):
                raise RuntimeError('injected legacy interruption before rename')
            original_publish(source, destination)

        with patch.object(gate, 'require_capacity_rotation', side_effect=strict_gate), \
                patch.object(archive, '_publish', side_effect=crash):
            with self.assertRaisesRegex(RuntimeError, 'legacy interruption before rename'):
                retention.maintenance(self.destination, reason='FIXTURE', need_slot=True)
        job = next(iter(self.catalog()['deletions'].values()))
        self.assertEqual(job['kind'], 'CAPACITY_ROTATION')
        self.assertEqual(job['phase'], 'PREPARED')
        self.assertNotIn('verification_purpose', job['canonical_deletion_lease'])
        self.assertNotEqual(job['retirement_receipt']['verification_evidence'].get('method'),
                            'DELETION_SNAPSHOT')
        self.assertTrue(self.packages[0].exists())
        # A resumed old lease must still reject survivor payload drift; it
        # must not be silently upgraded to metadata-only capacity evidence.
        added = self.add_cache(self.packages[6])
        with self.assertRaises(ValueError):
            retention.recover_cleanup(self.catalog_path)
        self.assertTrue(self.packages[0].exists())
        added.unlink()
        added.parent.rmdir()
        self.assertEqual(retention.recover_cleanup(self.catalog_path), [str(self.packages[0])])
        self.assertFalse(self.catalog()['deletions'])
        self.assertEqual(len(protection.load_rotation_receipts(self.base, self.policy)), 1)

    def test_new_entry_after_preparation_blocks_recovery_without_expanding_scope(self):
        original_publish = archive._publish

        def crash(source, destination):
            if Path(destination).name.startswith('.retention-trash-'):
                raise RuntimeError('injected interruption before rename')
            original_publish(source, destination)

        with patch.object(archive, '_publish', side_effect=crash):
            with self.assertRaisesRegex(RuntimeError, 'before rename'):
                retention.maintenance(self.destination, reason='FIXTURE', need_slot=True)
        added = self.add_cache(self.packages[0])
        with self.assertRaisesRegex(ValueError, 'foreign/replaced/unrecorded'):
            retention.recover_cleanup(self.catalog_path)
        self.assertTrue(added.exists())
        self.assertEqual(len(self.catalog()['deletions']), 1)
        self.assertTrue(all(package.exists() for package in self.packages))

    def test_mid_unlink_interruption_resumes_without_historical_integrity_gate(self):
        self.add_cache(self.packages[0])
        original_unlink = os.unlink
        interrupted = False

        def crash(name, *args, **kwargs):
            nonlocal interrupted
            original_unlink(name, *args, **kwargs)
            if kwargs.get('dir_fd') is not None and not interrupted:
                interrupted = True
                raise RuntimeError('injected interruption after first unlink')

        with patch.object(os, 'unlink', side_effect=crash):
            with self.assertRaisesRegex(RuntimeError, 'first unlink'):
                retention.maintenance(self.destination, reason='FIXTURE', need_slot=True)
        receipt = next(iter(self.catalog()['retirements'].values()))
        self.assertEqual(receipt['state'], 'PARTIAL')
        self.assertFalse(receipt['physical_available'])
        self.assertEqual(retention.recover_cleanup(self.catalog_path), [str(self.packages[0])])
        self.assertEqual(len(protection.load_rotation_receipts(self.base, self.policy)), 1)
        self.publish_next()

    def test_final_empty_checkpoint_recovers_without_duplicate_rotation(self):
        self.add_cache(self.packages[0])
        original_rmdir = os.rmdir

        def crash(path, *args, **kwargs):
            original_rmdir(path, *args, **kwargs)
            if kwargs.get('dir_fd') is None and Path(path).name.startswith('.retention-trash-'):
                raise RuntimeError('injected interruption after final empty unlink')

        with patch.object(os, 'rmdir', side_effect=crash):
            with self.assertRaisesRegex(RuntimeError, 'final empty unlink'):
                retention.maintenance(self.destination, reason='FIXTURE', need_slot=True)
        job = next(iter(self.catalog()['deletions'].values()))
        self.assertEqual(job['phase'], 'FINAL_UNLINK_READY')
        self.assertFalse(Path(job['trash']).exists())
        self.assertEqual(retention.recover_cleanup(self.catalog_path), [str(self.packages[0])])
        self.assertEqual(retention.recover_cleanup(self.catalog_path), [])
        self.assertEqual(len(protection.load_rotation_receipts(self.base, self.policy)), 1)
        self.publish_next()


if __name__ == '__main__':
    unittest.main()
