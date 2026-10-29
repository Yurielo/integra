"""Isolated capacity-rotation proofs; never touch the user's managed archive."""
import base64
import json
import os
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch

from scripts import candidate_archive as archive
from scripts import candidate_protection_gate as gate
from scripts import candidate_protection_audit as protection
from scripts import candidate_retention as retention
from scripts import retention_cleanup
import test_candidate_archive as fixtures


class RotationOrderTests(unittest.TestCase):
    def test_publication_time_precedes_legacy_birthtime_and_has_explicit_provenance(self):
        with patch.object(retention.Path, 'stat') as stat_result:
            stat_result.return_value.st_birthtime = 100.0
            legacy = retention._rotation_order('/fixture/legacy', {})
        modern = retention._rotation_order('/fixture/modern', {
            'publication_recorded_at': '1970-01-01T00:03:20+00:00'})
        self.assertEqual(legacy['source'], 'APFS_DIRECTORY_BIRTHTIME_OBSERVED_NOW')
        self.assertEqual(legacy['timestamp'], 100.0)
        self.assertEqual(modern['source'], 'PUBLISHER_PUBLICATION_TIMESTAMP')
        self.assertEqual(modern['timestamp'], 200.0)
        self.assertIsNone(retention._rotation_order('/fixture/modern', {
            'publication_recorded_at': 'invalid'}))

    def test_unmerged_policy_cannot_authorize_real_rotation(self):
        with patch.object(gate, '_snapshot', return_value=({}, {'canonical': {}})):
            with self.assertRaisesRegex(ValueError, 'canonical Owner capacity-rotation policy'):
                gate.require_capacity_rotation(Path('/fixture/oldest'))

    def test_equal_observed_time_uses_approved_candidate_id_tie_break(self):
        def binding(row):
            return {'path': '/fixture/' + row['candidate_id'], 'candidate_id': row['candidate_id'],
                    'bundle_digest': 'b' * 64, 'manifest_digest': 'c' * 64,
                    'owner_uid': os.getuid(), 'device': 1, 'inode': row['inode'],
                    'birthtime': 100.0,
                    'order_provenance': {'timestamp': 100.0,
                                         'source': 'APFS_DIRECTORY_BIRTHTIME_OBSERVED_NOW',
                                         'recorded_value': 100.0}}
        with patch.object(retention, '_rotation_binding', side_effect=binding):
            baseline = retention._initial_rotation_order(
                [{'candidate_id': 'candidate-b', 'inode': 2},
                 {'candidate_id': 'candidate-a', 'inode': 1}],
                'a' * 64, '2026-10-29T00:00:00+00:00', 2)
        self.assertEqual([item['candidate_id'] for item in baseline['entries']],
                         ['candidate-a', 'candidate-b'])

    def test_backwards_publication_clock_fails_closed_against_sequence(self):
        def row(name, timestamp, sequence=None):
            binding = {'path': '/fixture/' + name, 'candidate_id': name,
                       'bundle_digest': 'b' * 64, 'manifest_digest': 'c' * 64,
                       'owner_uid': os.getuid(), 'device': 1, 'inode': len(name),
                       'birthtime': timestamp,
                       'order_provenance': {'timestamp': timestamp,
                                            'source': ('PUBLISHER_PUBLICATION_TIMESTAMP' if sequence else
                                                       'APFS_DIRECTORY_BIRTHTIME_OBSERVED_NOW'),
                                            'recorded_value': timestamp}}
            return {'path': binding['path'], 'candidate_id': name,
                    'binding': binding, 'capacity_rotation_order': binding['order_provenance'],
                    'catalog_record': {'publication_sequence': sequence} if sequence else {}}
        original = [row('old-a', 100), row('old-b', 200)]
        newer = [row('new-c', 400, 4), row('new-d', 300, 5)]
        baseline = {'schema_version': '2.0', 'policy_sha256': 'a' * 64,
                    'entries': [{**item['binding'], 'ordinal': index}
                                for index, item in enumerate(original)]}
        with patch.object(retention, '_rotation_binding', side_effect=lambda item: item['binding']):
            with self.assertRaisesRegex(ValueError, 'timestamp conflicts'):
                retention._ordered_rotation_rows(original + newer, baseline,
                                                 'a' * 64, {}, 2)


@unittest.skipUnless(hasattr(Path.home().stat(), 'st_birthtime'), 'APFS birthtime integration needs macOS')
class LegacyRotationTests(unittest.TestCase):
    # Reuse the tiny exact Candidate fixture without inheriting its test cases.
    _manifest = fixtures.CandidateArchiveTests._manifest

    def setUp(self):
        fixtures.CandidateArchiveTests.setUp(self)

    def legacy_case(self):
        legacy = self.destination / 'legacy-build'
        legacy.mkdir(parents=True)
        shutil.copytree(self.app, legacy / 'Integra.app')
        (legacy / 'build.log').write_text('historical fixture\n')
        identity = archive._identity(legacy / 'Integra.app')
        catalog_path = retention.catalog_path(self.destination)
        with retention.locked(catalog_path) as catalog:
            retention.register_root(catalog, self.destination)
            catalog['protection'] = {'protected': {identity['candidate_id']: ['OPEN_PROPOSAL']},
                                     'inputs': {}, 'selected_archives': {}, 'verified_survivors': {},
                                     'rotation_policy': {'rotation_strategy': 'OLDEST_FULL_COPY_FIRST',
                                                         'sha256': 'a' * 64}}
        with patch.object(retention, '_context_valid', return_value=True), patch.object(retention, 'MAX_COPIES', 1):
            plan = retention.plan(json.loads(catalog_path.read_bytes()), free_bytes=64 * 1024**3)
        target = plan['capacity_rotation_target']
        self.assertEqual(target['path'], str(legacy))
        self.assertEqual(target['capacity_rotation_order']['source'],
                         'APFS_DIRECTORY_BIRTHTIME_OBSERVED_NOW')
        lease = {'kind': 'OWNER_POLICY_CAPACITY_ROTATION', 'identity': identity,
                 'order': target['capacity_rotation_order'],
                 'device': target['device'], 'inode': target['inode'],
                 'birthtime': legacy.stat().st_birthtime,
                 'policy_authority_ref': 'direct Owner fixture', 'policy_sha256': 'a' * 64,
                 'initial_order': retention._initial_rotation_order(
                     plan['entries'], 'a' * 64, '2026-10-29T00:00:00+00:00', 1),
                 'proposal_refs': ['PR #204']}
        return legacy, catalog_path, plan, lease, identity

    def test_unarchived_oldest_is_attested_then_retired_with_history_preserved(self):
        legacy, catalog_path, plan, lease, identity = self.legacy_case()
        with patch.object(retention, '_context_valid', return_value=True), \
                patch.object(retention, '_inactive', return_value=True), \
                patch.object(retention, 'MAX_COPIES', 1):
            with patch.object(gate, 'require_capacity_rotation', return_value=lease), \
                    patch.object(gate, 'require_capacity_rotation_continuation', return_value=None):
                result = retention_cleanup.apply_capacity_rotation(retention, catalog_path, plan)
        self.assertEqual(result, [str(legacy)])
        self.assertFalse(legacy.exists())
        self.assertEqual(archive._identity(self.app), identity)
        after = json.loads(catalog_path.read_bytes())
        self.assertEqual(after['deletions'], {})
        receipt = next(iter(after['retirements'].values()))
        self.assertEqual(receipt['archive_kind'], 'UNARCHIVED_CANDIDATE_BUILD')
        self.assertIsNone(receipt['publisher_attestation'])
        self.assertEqual(receipt['proposal_refs'], ['PR #204'])
        self.assertEqual(receipt['state'], 'RETIRED_NOT_AVAILABLE')
        self.assertIs(receipt['physical_available'], False)
        self.assertEqual(receipt['order_provenance']['source'],
                         'APFS_DIRECTORY_BIRTHTIME_OBSERVED_NOW')
        self.assertTrue(receipt['retained_inventory'])
        self.assertEqual(base64.b64decode(receipt['retained_provenance_files_base64']['build.log']),
                         b'historical fixture\n')

    def test_unregistered_complete_archive_retains_exact_original_receipt_bytes(self):
        legacy, catalog_path, _, _, identity = self.legacy_case()
        bound = self.destination / identity['candidate_id'] / identity['bundle_digest']
        bound.parent.mkdir()
        legacy.rename(bound)
        legacy = bound
        (legacy / archive.MANIFEST_NAME).write_bytes(self.manifest.read_bytes())
        original_inventory = archive._inventory(legacy)
        inventory_bytes = json.dumps(original_inventory, sort_keys=True).encode()
        (legacy / 'inventory.json').write_bytes(inventory_bytes)
        complete = archive._receipt(identity, original_inventory,
                                    protection.sha(inventory_bytes))
        complete_bytes = json.dumps(complete, sort_keys=True).encode()
        (legacy / 'COMPLETE.json').write_bytes(complete_bytes)
        self.assertEqual(archive.verify_archive(legacy, identity)['status'], 'COMPLETE')
        with patch.object(retention, '_context_valid', return_value=True), \
                patch.object(retention, 'MAX_COPIES', 1):
            plan = retention.plan(json.loads(catalog_path.read_bytes()), free_bytes=64 * 1024**3)
        target = plan['capacity_rotation_target']
        lease = {'kind': 'OWNER_POLICY_CAPACITY_ROTATION', 'identity': identity,
                 'order': target['capacity_rotation_order'],
                 'device': target['device'], 'inode': target['inode'],
                 'birthtime': legacy.stat().st_birthtime,
                 'policy_authority_ref': 'direct Owner fixture', 'policy_sha256': 'a' * 64,
                 'initial_order': retention._initial_rotation_order(
                     plan['entries'], 'a' * 64, '2026-10-29T00:00:00+00:00', 1),
                 'proposal_refs': ['PR #204']}
        with patch.object(retention, '_context_valid', return_value=True), \
                patch.object(retention, '_inactive', return_value=True), \
                patch.object(retention, 'MAX_COPIES', 1), \
                patch.object(gate, 'require_capacity_rotation', return_value=lease), \
                patch.object(gate, 'require_capacity_rotation_continuation', return_value=None):
            retention.cleanup_capacity_rotation(catalog_path, plan)
        retired = next(iter(json.loads(catalog_path.read_bytes())['retirements'].values()))
        self.assertEqual(retired['archive_kind'], 'LEGACY_COMPLETED_ARCHIVE_OBSERVED_NOW')
        self.assertIsNone(retired['publisher_attestation'])
        self.assertEqual(base64.b64decode(retired['retained_inventory_json_base64']), inventory_bytes)
        self.assertEqual(base64.b64decode(retired['retained_complete_base64']), complete_bytes)
        self.assertEqual(retired['proposal_refs'], ['PR #204'])

    def test_corrupt_unselected_complete_survivor_fails_full_attestation(self):
        identity = archive._identity(self.app)
        package = self.destination / identity['candidate_id'] / identity['bundle_digest']
        package.parent.mkdir(parents=True)
        shutil.copytree(self.app, package / 'Integra.app')
        (package / archive.MANIFEST_NAME).write_bytes(self.manifest.read_bytes())
        inventory = archive._inventory(package)
        inventory_bytes = json.dumps(inventory, sort_keys=True).encode()
        (package / 'inventory.json').write_bytes(inventory_bytes)
        complete = archive._receipt(identity, inventory, protection.sha(inventory_bytes))
        (package / 'COMPLETE.json').write_bytes(json.dumps(complete, sort_keys=True).encode())
        self.assertEqual(gate._rotation_package_attestation(package, identity)['archive_kind'], 'COMPLETE')
        (package / 'Integra.app/Contents/MacOS/Integra').write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, 'candidate bundle bytes differ'):
            gate._rotation_package_attestation(package, identity)

    def test_live_canonical_gate_and_rename_recovery_accept_exact_active_journal(self):
        base = self.root / 'Library/Application Support/Integra'
        self.destination = base / 'Candidate Builds'
        catalog_path = base / 'Retention' / f'catalog-{os.getuid()}.json'
        registry_path = self.root / 'rotation-registry.json'
        with patch.object(retention, 'catalog_path', return_value=catalog_path):
            legacy, _, plan, _, identity = self.legacy_case()
            relative = legacy.relative_to(base).as_posix()
            policy = {'status': 'PRODUCT_OWNER_AUTHORIZED_ACTIVE',
                      'rotation_strategy': 'OLDEST_FULL_COPY_FIRST',
                      'max_full_copies': 1, 'sha256': 'a' * 64,
                      'authority_ref': 'direct Owner fixture'}
            canonical = {'rotation_policy': policy}
            registry = {'status': 'PRODUCT_OWNER_AUTHORIZED_ACTIVE',
                        'activation_authority_ref': 'fixture',
                        'promotion_contract_integration_ref': 'fixture',
                        'deletion_enabled': True,
                        'managed_roots': ['Candidate Builds'],
                        'selected_survivors': {identity['candidate_id']: relative}}
            registry_path.write_text(json.dumps(registry))
            proposal = {204: {'candidate': {'candidate_id': identity['candidate_id']}}}

            def synthetic_scan(*_args):
                return [{'path': relative, 'absolute_path': str(legacy), **identity,
                         'catalog_record': None, 'publisher_owned': False}]

            def synthetic_resolve(*_args, rotation_receipts=None, **_kwargs):
                self.assertEqual(rotation_receipts, {})
                return {'authority_state': 'COMPLETE', 'blockers': [],
                        'canonical': canonical, 'full_copies': 1,
                        'entries': synthetic_scan(), 'rotated_unavailable': {},
                        'protected_identities': {
                            identity['candidate_id']: {'identity': identity}}}

            original_publish = archive._publish

            def interrupted_publish(source, destination):
                original_publish(source, destination)
                raise RuntimeError('injected crash after source rename')

            with patch.object(Path, 'home', return_value=self.root), \
                    patch.object(protection, 'REGISTRY', registry_path), \
                    patch.object(protection, 'fetch_canonical', return_value=({}, proposal, canonical)), \
                    patch.object(protection, 'scan_local', side_effect=synthetic_scan), \
                    patch.object(protection, 'resolve', side_effect=synthetic_resolve), \
                    patch.object(protection, '_accepted_historical_gaps', return_value=set()), \
                    patch.object(protection, '_validate_registry', return_value={
                        identity['candidate_id']: {'identity': identity}}), \
                    patch.object(retention, '_context_valid', side_effect=lambda _: legacy.exists()), \
                    patch.object(retention, '_inactive', return_value=True), \
                    patch.object(retention, 'MAX_COPIES', 1):
                # Neither capacity gate is mocked: the second pre-rename call
                # sees an active PREPARED receipt and the continuation sees a
                # moved package with a PARTIAL receipt.
                with patch.object(archive, '_publish', side_effect=interrupted_publish):
                    with self.assertRaisesRegex(RuntimeError, 'after source rename'):
                        retention.cleanup_capacity_rotation(catalog_path, plan)
                self.assertFalse(legacy.exists())
                self.assertEqual(retention.recover_cleanup(catalog_path), [str(legacy)])
            receipt = next(iter(json.loads(catalog_path.read_bytes())['retirements'].values()))
            self.assertEqual(receipt['state'], 'RETIRED_NOT_AVAILABLE')

    def test_exact_rebuild_at_retired_identity_path_is_new_publisher_incarnation(self):
        identity = archive._identity(self.app)
        package = self.destination / identity['candidate_id'] / identity['bundle_digest']
        package.parent.mkdir(parents=True)
        shutil.copytree(self.app, package / 'Integra.app')
        catalog_path = retention.catalog_path(self.destination)
        with retention.locked(catalog_path) as catalog:
            retention.register_root(catalog, self.destination)
            catalog['protection'] = {'protected': {identity['candidate_id']: ['OPEN_PROPOSAL']},
                                     'inputs': {}, 'selected_archives': {}, 'verified_survivors': {},
                                     'rotation_policy': {'rotation_strategy': 'OLDEST_FULL_COPY_FIRST',
                                                         'sha256': 'a' * 64}}
        with patch.object(retention, '_context_valid', return_value=True), \
                patch.object(retention, 'MAX_COPIES', 1):
            before = retention.plan(json.loads(catalog_path.read_bytes()), free_bytes=64 * 1024**3)
        target = before['capacity_rotation_target']
        lease = {'kind': 'OWNER_POLICY_CAPACITY_ROTATION', 'identity': identity,
                 'order': target['capacity_rotation_order'],
                 'device': target['device'], 'inode': target['inode'],
                 'birthtime': package.stat().st_birthtime,
                 'policy_authority_ref': 'direct Owner fixture', 'policy_sha256': 'a' * 64,
                 'initial_order': retention._initial_rotation_order(
                     before['entries'], 'a' * 64, '2026-10-29T00:00:00+00:00', 1),
                 'proposal_refs': ['PR #204']}
        with patch.object(retention, '_context_valid', return_value=True), \
                patch.object(retention, '_inactive', return_value=True), \
                patch.object(retention, 'MAX_COPIES', 1), \
                patch.object(gate, 'require_capacity_rotation', return_value=lease), \
                patch.object(gate, 'require_capacity_rotation_continuation', return_value=None):
            retention.cleanup_capacity_rotation(catalog_path, before)
        self.assertFalse(package.exists())
        with patch.object(gate, 'require_archive_publication', return_value=None), \
                patch.object(retention, 'refresh_protection', return_value=None), \
                patch.object(retention, '_context_valid', return_value=True), \
                patch.object(archive, 'MANAGED_BASE', self.root), \
                patch.object(retention, 'MAX_COPIES', 1):
            archive.create_archive(self.app, self.destination)
        with patch.object(retention, '_context_valid', return_value=True), \
                patch.object(retention, 'MAX_COPIES', 1):
            rebuilt = retention.plan(json.loads(catalog_path.read_bytes()), free_bytes=64 * 1024**3)
        self.assertEqual(rebuilt['full_copies'], 1)
        self.assertEqual(rebuilt['capacity_rotation_target']['path'], str(package))
        self.assertEqual(rebuilt['capacity_rotation_target']['capacity_rotation_order']['source'],
                         'PUBLISHER_PUBLICATION_TIMESTAMP')
        self.assertEqual(len(json.loads(catalog_path.read_bytes())['retirements']), 1)

    def test_interrupted_rename_recovers_without_false_completion(self):
        legacy, catalog_path, plan, lease, _ = self.legacy_case()
        original_publish = archive._publish

        def interrupted_publish(source, destination):
            original_publish(source, destination)
            raise RuntimeError('injected interruption after rename')

        with patch.object(retention, '_context_valid', side_effect=lambda _: legacy.exists()), \
                patch.object(retention, '_inactive', return_value=True), \
                patch.object(retention, 'MAX_COPIES', 1), \
                patch.object(gate, 'require_capacity_rotation', return_value=lease), \
                patch.object(gate, 'require_capacity_rotation_continuation', return_value=None):
            with patch.object(archive, '_publish', side_effect=interrupted_publish):
                with self.assertRaisesRegex(RuntimeError, 'injected interruption'):
                    retention_cleanup.apply_capacity_rotation(retention, catalog_path, plan)
            partial = json.loads(catalog_path.read_bytes())
            self.assertEqual(len(partial['deletions']), 1)
            receipt = next(iter(partial['retirements'].values()))
            self.assertEqual(receipt['state'], 'PARTIAL')
            self.assertFalse(receipt['physical_available'])
            self.assertFalse(legacy.exists())
            self.assertEqual(retention.recover_cleanup(catalog_path), [str(legacy)])
        completed = json.loads(catalog_path.read_bytes())
        self.assertEqual(completed['deletions'], {})
        self.assertEqual(next(iter(completed['retirements'].values()))['state'], 'RETIRED_NOT_AVAILABLE')

    def test_mid_unlink_failure_recovers_without_claiming_available_bytes(self):
        legacy, catalog_path, plan, lease, _ = self.legacy_case()
        original_parent_fd = retention_cleanup._parent_fd
        calls = 0

        def interrupt_after_two_entries(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 3:
                raise RuntimeError('injected mid-unlink interruption')
            return original_parent_fd(*args, **kwargs)

        with patch.object(retention, '_context_valid', side_effect=lambda _: legacy.exists()), \
                patch.object(retention, '_inactive', return_value=True), \
                patch.object(retention, 'MAX_COPIES', 1), \
                patch.object(gate, 'require_capacity_rotation', return_value=lease), \
                patch.object(gate, 'require_capacity_rotation_continuation', return_value=None):
            with patch.object(retention_cleanup, '_parent_fd', side_effect=interrupt_after_two_entries):
                with self.assertRaisesRegex(RuntimeError, 'mid-unlink'):
                    retention_cleanup.apply_capacity_rotation(retention, catalog_path, plan)
            partial = json.loads(catalog_path.read_bytes())
            self.assertEqual(next(iter(partial['retirements'].values()))['state'], 'PARTIAL')
            self.assertFalse(legacy.exists())
            self.assertEqual(retention.recover_cleanup(catalog_path), [str(legacy)])
        completed = json.loads(catalog_path.read_bytes())
        self.assertEqual(completed['deletions'], {})
        receipt = next(iter(completed['retirements'].values()))
        self.assertEqual(receipt['state'], 'RETIRED_NOT_AVAILABLE')
        self.assertIs(receipt['physical_available'], False)

    def test_eight_to_seven_to_eight_admits_new_archived_candidate(self):
        identities = []
        for number in range(8):
            self.identity['source']['commit_sha'] = f'{number:040x}'
            self._manifest()
            package = self.destination / f'legacy-{number}'
            package.mkdir(parents=True)
            shutil.copytree(self.app, package / 'Integra.app')
            identities.append(archive._identity(package / 'Integra.app'))
        catalog_path = retention.catalog_path(self.destination)
        with retention.locked(catalog_path) as catalog:
            retention.register_root(catalog, self.destination)
            catalog['protection'] = {'protected': {item['candidate_id']: ['OPEN_PROPOSAL'] for item in identities},
                                     'inputs': {}, 'selected_archives': {}, 'verified_survivors': {},
                                     'rotation_policy': {'rotation_strategy': 'OLDEST_FULL_COPY_FIRST',
                                                         'sha256': 'a' * 64}}
            for number, sequence in ((6, 2), (7, 3)):
                catalog['artifacts'][str(self.destination / f'legacy-{number}')] = {
                    **identities[number], 'status': 'AWAITING_OWNER_ACCEPTANCE',
                    'publication_sequence': sequence}
        with patch.object(retention, '_context_valid', return_value=True), \
                patch.object(retention, '_inactive', return_value=True):
            before = retention.plan(json.loads(catalog_path.read_bytes()), free_bytes=64 * 1024**3)
            self.assertEqual(before['full_copies'], 8)
            target = before['capacity_rotation_target']
            oldest = min(before['entries'], key=lambda row: (
                row['capacity_rotation_order']['timestamp'], row['candidate_id'], row['path']))
            self.assertEqual(target['path'], oldest['path'])
            initial = retention._initial_rotation_order(
                before['entries'], 'a' * 64, '2026-10-29T00:00:00+00:00')
            self.assertEqual([entry['order_provenance']['source'] for entry in initial['entries'][:6]],
                             ['APFS_DIRECTORY_BIRTHTIME_OBSERVED_NOW'] * 6)
            self.assertEqual([entry['order_provenance']['publisher_sequence']
                              for entry in initial['entries'][6:]], [2, 3])
            changed_birthtime = json.loads(json.dumps(initial))
            changed_birthtime['entries'][1]['birthtime'] += 1
            with self.assertRaisesRegex(ValueError, 'identity or birthtime changed'):
                retention._ordered_rotation_rows(before['entries'], changed_birthtime,
                                                 'a' * 64, set())
            changed_path = json.loads(json.dumps(initial))
            changed_path['entries'][1]['path'] += '-moved'
            with self.assertRaisesRegex(ValueError, 'disappeared without completed receipt'):
                retention._ordered_rotation_rows(before['entries'], changed_path,
                                                 'a' * 64, set())
            lease = {'kind': 'OWNER_POLICY_CAPACITY_ROTATION',
                     'identity': {key: target[key] for key in archive.IDENTITY_KEYS},
                     'order': target['capacity_rotation_order'],
                     'device': target['device'], 'inode': target['inode'],
                     'birthtime': Path(target['path']).stat().st_birthtime,
                     'policy_authority_ref': 'direct Owner fixture', 'policy_sha256': 'a' * 64,
                     'initial_order': initial,
                     'proposal_refs': []}
            with patch.object(gate, 'require_capacity_rotation', return_value=lease), \
                    patch.object(gate, 'require_capacity_rotation_continuation', return_value=None):
                self.assertEqual(retention.cleanup_capacity_rotation(catalog_path, before), [target['path']])
            after = retention.plan(json.loads(catalog_path.read_bytes()), free_bytes=64 * 1024**3)
            self.assertEqual(after['full_copies'], 7)
            self.assertEqual(json.loads(catalog_path.read_bytes())['rotation_order_v2'], initial)
            self.identity['source']['commit_sha'] = 'f' * 40
            self._manifest()
            with patch.object(gate, 'require_archive_publication', return_value=None), \
                    patch.object(retention, 'refresh_protection', return_value=None), \
                    patch.object(archive, 'MANAGED_BASE', self.root):
                receipt = archive.create_archive(self.app, self.destination)
            final = retention.plan(json.loads(catalog_path.read_bytes()), free_bytes=64 * 1024**3)
            self.assertEqual(final['full_copies'], 8)
            self.assertTrue(json.loads(catalog_path.read_bytes())['artifacts'][receipt['archive_path']]['publication_recorded_at'])
            self.assertEqual(archive.verify_archive(Path(receipt['archive_path']))['status'], 'COMPLETE')
            target2 = final['capacity_rotation_target']
            lease2 = {'kind': 'OWNER_POLICY_CAPACITY_ROTATION',
                      'identity': {key: target2[key] for key in archive.IDENTITY_KEYS},
                      'order': target2['capacity_rotation_order'],
                      'device': target2['device'], 'inode': target2['inode'],
                      'birthtime': Path(target2['path']).stat().st_birthtime,
                      'policy_authority_ref': 'direct Owner fixture', 'policy_sha256': 'a' * 64,
                      'initial_order': json.loads(catalog_path.read_bytes())['rotation_order_v2'],
                      'proposal_refs': []}
            with patch.object(gate, 'require_capacity_rotation', return_value=lease2), \
                    patch.object(gate, 'require_capacity_rotation_continuation', return_value=None):
                retention.cleanup_capacity_rotation(catalog_path, final)
            self.identity['source']['commit_sha'] = 'e' * 40
            self._manifest()
            with patch.object(gate, 'require_archive_publication', return_value=None), \
                    patch.object(retention, 'refresh_protection', return_value=None), \
                    patch.object(archive, 'MANAGED_BASE', self.root):
                archive.create_archive(self.app, self.destination)
            repeated = retention.plan(json.loads(catalog_path.read_bytes()), free_bytes=64 * 1024**3)
            self.assertEqual(repeated['full_copies'], 8)
            self.assertEqual(len(json.loads(catalog_path.read_bytes())['retirements']), 2)

    def test_completed_receipt_reports_missing_bytes_and_rejects_forgery(self):
        identity = archive._identity(self.app)
        manifest_bytes = self.manifest.read_bytes()
        inventory = archive._inventory(self.app)
        relative = 'Candidate Builds/old-copy'
        receipt = {'reason': 'OWNER_POLICY_CAPACITY_ROTATION',
                   'state': 'RETIRED_NOT_AVAILABLE', 'physical_available': False,
                   'execution_result': 'PASS', 'transaction_id': 'rotation-v2-fixture',
                   'policy_sha256': 'a' * 64, **identity,
                   'archive_kind': 'UNARCHIVED_CANDIDATE_BUILD',
                   'retained_inventory_json_base64': None,
                   'retained_complete_base64': None,
                   'publisher_attestation': None,
                   'canonical_snapshot': {'path': relative},
                   'physical_source_path': str(self.root / relative),
                   'retained_manifest': json.loads(manifest_bytes),
                   'retained_manifest_base64': base64.b64encode(manifest_bytes).decode('ascii'),
                   'retained_inventory': inventory,
                   'retained_provenance_files_base64': {
                       item['path']: base64.b64encode((self.app / item['path']).read_bytes()).decode('ascii')
                       for item in inventory if item['type'] == 'file'},
                   'verification_evidence': {
                       'manifest_digest': identity['manifest_digest'],
                       'rotation_inventory_sha256': protection.digest(inventory)}}
        metadata = self.root / 'Retention'; metadata.mkdir()
        catalog = metadata / f'catalog-{os.getuid()}.json'
        value = {'artifact_type': 'integra.owned_archive_catalog', 'owner_uid': os.getuid(),
                 'deletions': {}, 'retirements': {'rotation-v2-fixture': receipt}}
        catalog.write_text(json.dumps(value))
        policy = {'rotation_strategy': 'OLDEST_FULL_COPY_FIRST', 'sha256': 'a' * 64}
        self.assertEqual(protection.load_rotation_receipts(self.root, policy)[identity['candidate_id']]['path'],
                         relative)
        receipt['physical_source_path'] = str(self.root / 'other')
        catalog.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'inconsistent'):
            protection.load_rotation_receipts(self.root, policy)
        receipt['physical_source_path'] = str(self.root / relative)
        value['retirements']['rotation-v2-fixture']['observed_at'] = '2026-10-01T00:00:00+00:00'
        repeated_receipt = json.loads(json.dumps(receipt))
        repeated_receipt['transaction_id'] = 'rotation-v2-fixture-second'
        repeated_receipt['observed_at'] = '2026-10-02T00:00:00+00:00'
        value['retirements']['rotation-v2-fixture-second'] = repeated_receipt
        catalog.write_text(json.dumps(value))
        selected = protection.load_rotation_receipts(self.root, policy)[identity['candidate_id']]
        self.assertEqual(selected['transaction_id'], 'rotation-v2-fixture-second')
        (self.root / relative).mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, 'conflicts'):
            protection.load_rotation_receipts(self.root, policy)
        (self.root / relative).rmdir()
        value['retirements']['rotation-v2-fixture']['retained_manifest_base64'] = 'e30='
        catalog.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'inconsistent'):
            protection.load_rotation_receipts(self.root, policy)


if __name__ == '__main__':
    unittest.main()
