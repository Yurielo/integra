"""Isolated capacity-rotation proofs; never touch the user's managed archive."""
import base64
import copy
import json
import os
from pathlib import Path
import shutil
import time
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

    def test_persisted_order_allows_only_observed_device_drift(self):
        binding = {'path': '/fixture/legacy', 'candidate_id': 'candidate-legacy',
                   'bundle_digest': 'b' * 64, 'manifest_digest': 'c' * 64,
                   'owner_uid': os.getuid(), 'device': 2, 'inode': 10,
                   'birthtime': 100.0,
                   'order_provenance': {'timestamp': 100.0,
                                        'source': 'APFS_DIRECTORY_BIRTHTIME_OBSERVED_NOW',
                                        'recorded_value': 100.0}}
        row = {'path': binding['path'], 'candidate_id': binding['candidate_id'],
               'capacity_rotation_order': binding['order_provenance'], 'binding': binding}
        baseline = {'schema_version': '2.0', 'policy_sha256': 'a' * 64,
                    'entries': [{**binding, 'device': 1, 'ordinal': 0}]}
        with patch.object(retention, '_rotation_binding', side_effect=lambda item: item['binding']):
            ordered = retention._ordered_rotation_rows([row], baseline, 'a' * 64, {}, 1)
            self.assertEqual(ordered, [row])
            changed_inode = {**binding, 'inode': 11}
            with self.assertRaisesRegex(ValueError, 'identity or birthtime changed'):
                retention._ordered_rotation_rows(
                    [{**row, 'binding': changed_inode}], baseline, 'a' * 64, {}, 1)


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

    def completed_device_drift_case(self, destination=None, *, timestamped=False):
        destination = destination or self.root / 'Build Archive'
        with patch.object(gate, 'require_archive_publication', return_value=None), \
                patch.object(retention, 'refresh_protection', return_value=None), \
                patch.object(retention, '_context_valid', return_value=True), \
                patch.object(archive, 'MANAGED_BASE', self.root):
            published = archive.create_archive(self.app, destination)
        package = Path(published['archive_path'])
        identity = {key: published[key] for key in archive.IDENTITY_KEYS}
        catalog_path = retention.catalog_path(destination)
        with retention.locked(catalog_path) as catalog:
            record = catalog['artifacts'][str(package)]
            record['device'] = package.stat().st_dev + 1
            if not timestamped:
                record.pop('publication_recorded_at')
            record['publication_sequence'] = 2
            catalog['protection'] = {
                'protected': {identity['candidate_id']: ['OPEN_PROPOSAL']},
                'inputs': {}, 'selected_archives': {}, 'verified_survivors': {},
                'rotation_policy': {'rotation_strategy': 'OLDEST_FULL_COPY_FIRST',
                                    'sha256': 'a' * 64}}
            saved = copy.deepcopy(record)
        return package, catalog_path, identity, saved

    def test_rotation_gate_accepts_only_metadata_bound_device_drift_order(self):
        base = self.root / 'Library/Application Support/Integra'
        package, _, identity, record = self.completed_device_drift_case(base / 'Build Archive')
        relative = package.relative_to(base).as_posix()
        policy = {'rotation_strategy': 'OLDEST_FULL_COPY_FIRST',
                  'status': 'PRODUCT_OWNER_AUTHORIZED_ACTIVE', 'max_full_copies': 1,
                  'sha256': 'a' * 64, 'authority_ref': 'direct Owner fixture'}
        registry = {'selected_survivors': {}, 'managed_roots': ['Build Archive']}
        row = {'path': relative, 'absolute_path': str(package), **identity,
               'catalog_record': record, 'publisher_owned': False,
               'integrity_verified': False, 'identity_metadata_verified': True,
               'metadata_error': None}
        audit = {'canonical': {'rotation_policy': policy}, 'full_copies': 1,
                 'entries': [row], 'registry_sha256': 'b' * 64,
                 'protected_identities': {}, 'rotated_unavailable': {}}
        with patch.object(gate.Path, 'home', return_value=self.root), \
                patch.object(gate, '_snapshot', return_value=(registry, audit)), \
                patch.object(protection, 'fetch_canonical', return_value=({}, {}, audit['canonical'])):
            lease = gate.require_capacity_rotation(package)
            self.assertFalse(row['publisher_owned'])
            self.assertEqual(lease['publisher_order_evidence'][relative]['recorded_device'],
                             record['device'])
            row['identity_metadata_verified'] = False
            with self.assertRaisesRegex(ValueError, 'not bound to verified archive bytes'):
                gate.require_capacity_rotation(package)
            row['identity_metadata_verified'] = True
            row['catalog_record'] = {**record, 'complete_sha256': '0' * 64}
            with self.assertRaisesRegex(ValueError, 'not bound to verified archive bytes'):
                gate.require_capacity_rotation(package)
            row['catalog_record'] = {**record, 'publication_sequence': '2'}
            with self.assertRaisesRegex(ValueError, 'publisher sequence record is invalid'):
                gate.require_capacity_rotation(package)

    def test_pre_amendment_order_matches_bytes_without_adopting_device(self):
        package, catalog_path, identity, record = self.completed_device_drift_case()
        self.assertFalse(retention._ownership(package, record,
                         json.loads((package / 'COMPLETE.json').read_bytes())))
        archive.verify_archive(package, identity)
        evidence = gate._observed_publisher_order_evidence(package, record, identity)
        self.assertEqual(evidence['kind'], 'OBSERVED_CATALOG_PUBLISHER_RECORD_RECEIPT_MATCH_DEVICE_DRIFT')
        self.assertIs(evidence['physical_publisher_owned'], False)
        self.assertEqual(evidence['publication_sequence'], 2)
        self.assertNotEqual(evidence['recorded_device'], evidence['observed_device'])
        self.assertEqual(json.loads(catalog_path.read_bytes())['artifacts'][str(package)], record)

    def test_pre_amendment_order_rejects_forged_or_mismatched_record(self):
        package, _, identity, record = self.completed_device_drift_case()
        for change in ({'publisher_run_id': ''}, {'publisher_completed': False},
                       {'publication_sequence': 0}, {'inode': record['inode'] + 1},
                       {'candidate_id': 'wrong-candidate'},
                       {'complete_sha256': '0' * 64}, {'inventory_sha256': '0' * 64},
                       {'device': package.stat().st_dev}):
            with self.subTest(change=change):
                self.assertIsNone(gate._observed_publisher_order_evidence(
                    package, {**record, **change}, identity))
        with (package / 'COMPLETE.json').open('ab') as handle:
            handle.write(b' ')
        self.assertIsNone(gate._observed_publisher_order_evidence(package, record, identity))

    def test_timestamped_order_matches_bytes_without_adopting_device(self):
        package, _, identity, record = self.completed_device_drift_case(timestamped=True)
        evidence = gate._observed_publisher_order_evidence(package, record, identity)
        self.assertEqual(evidence['order_provenance']['source'],
                         'PUBLISHER_PUBLICATION_TIMESTAMP')
        self.assertEqual(evidence['publication_recorded_at'],
                         record['publication_recorded_at'])

    def test_timestamped_device_drift_retirement_keeps_exact_order_evidence(self):
        package, catalog_path, identity, record = self.completed_device_drift_case(timestamped=True)
        with patch.object(retention, '_context_valid', return_value=True), \
                patch.object(retention, '_inactive', return_value=True), \
                patch.object(retention, 'MAX_COPIES', 1):
            plan = retention.plan(json.loads(catalog_path.read_bytes()), free_bytes=64 * 1024**3)
            target = plan['capacity_rotation_target']
            relative = package.relative_to(self.root).as_posix()
            evidence = gate._observed_publisher_order_evidence(package, record, identity)
            lease = {'kind': 'OWNER_POLICY_CAPACITY_ROTATION', 'path': relative,
                     'identity': identity, 'order': target['capacity_rotation_order'],
                     'device': target['device'], 'inode': target['inode'],
                     'birthtime': package.stat().st_birthtime,
                     'policy_authority_ref': 'direct Owner fixture', 'policy_sha256': 'a' * 64,
                     'initial_order': retention._initial_rotation_order(
                         plan['entries'], 'a' * 64, '2026-10-29T00:00:00+00:00', 1),
                     'publisher_order_evidence': {relative: evidence}, 'proposal_refs': []}
            with patch.object(gate, 'require_capacity_rotation', return_value=lease), \
                    patch.object(gate, 'require_capacity_rotation_continuation', return_value=None):
                self.assertEqual(retention.cleanup_capacity_rotation(catalog_path, plan), [str(package)])
        retired_catalog = self.root / 'Retention' / f'catalog-{os.getuid()}.json'
        retired_catalog.parent.mkdir(exist_ok=True)
        retired_catalog.write_bytes(catalog_path.read_bytes())
        policy = {'rotation_strategy': 'OLDEST_FULL_COPY_FIRST', 'sha256': 'a' * 64}
        self.assertEqual(protection.load_rotation_receipts(self.root, policy)[identity['candidate_id']]['path'],
                         relative)

    def test_future_oldest_conflicting_record_retires_with_honest_receipt(self):
        package, catalog_path, identity, record = self.completed_device_drift_case()
        with patch.object(retention, '_context_valid', return_value=True), \
                patch.object(retention, '_inactive', return_value=True), \
                patch.object(retention, 'MAX_COPIES', 1):
            plan = retention.plan(json.loads(catalog_path.read_bytes()), free_bytes=64 * 1024**3)
            target = plan['capacity_rotation_target']
            self.assertEqual(target['path'], str(package))
            self.assertEqual(target['capacity_rotation_order']['publisher_sequence'], 2)
            relative = package.relative_to(self.root).as_posix()
            evidence = gate._observed_publisher_order_evidence(package, record, identity)
            lease = {'kind': 'OWNER_POLICY_CAPACITY_ROTATION', 'path': relative,
                     'identity': identity, 'order': target['capacity_rotation_order'],
                     'device': target['device'], 'inode': target['inode'],
                     'birthtime': package.stat().st_birthtime,
                     'policy_authority_ref': 'direct Owner fixture', 'policy_sha256': 'a' * 64,
                     'initial_order': retention._initial_rotation_order(
                         plan['entries'], 'a' * 64, '2026-10-29T00:00:00+00:00', 1),
                     'publisher_order_evidence': {relative: evidence}, 'proposal_refs': []}
            with patch.object(gate, 'require_capacity_rotation', return_value=lease), \
                    patch.object(gate, 'require_capacity_rotation_continuation', return_value=None):
                self.assertEqual(retention.cleanup_capacity_rotation(catalog_path, plan), [str(package)])
        self.assertFalse(package.exists())
        updated = json.loads(catalog_path.read_bytes())
        self.assertNotIn(str(package), updated['artifacts'])
        receipt = next(iter(updated['retirements'].values()))
        self.assertEqual(receipt['archive_kind'],
                         'COMPLETED_ARCHIVE_WITH_CONFLICTING_PUBLISHER_RECORD')
        self.assertIs(receipt['physical_publisher_owned'], False)
        self.assertIsNone(receipt['publisher_attestation'])
        self.assertEqual(receipt['conflicting_catalog_record'], record)
        self.assertEqual(receipt['observed_catalog_order_evidence'], evidence)
        retired_catalog = self.root / 'Retention' / f'catalog-{os.getuid()}.json'
        retired_catalog.parent.mkdir(exist_ok=True)
        retired_catalog.write_bytes(catalog_path.read_bytes())
        policy = {'rotation_strategy': 'OLDEST_FULL_COPY_FIRST', 'sha256': 'a' * 64}
        self.assertEqual(protection.load_rotation_receipts(self.root, policy)[identity['candidate_id']]['path'],
                         relative)
        original = json.loads(retired_catalog.read_bytes())
        for field, value in (('recorded_device', record['device'] + 1),
                             ('publisher_run_id', ''), ('order_timestamp', 0)):
            forged = copy.deepcopy(original)
            changed = next(iter(forged['retirements'].values()))
            if field == 'recorded_device':
                changed['conflicting_catalog_record']['device'] = value
            elif field == 'publisher_run_id':
                changed['conflicting_catalog_record']['publisher_run_id'] = value
            else:
                changed['order_provenance']['timestamp'] = value
            retired_catalog.write_text(json.dumps(forged))
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError,
                                            'conflicting-record retirement evidence differs'):
                    protection.load_rotation_receipts(self.root, policy)

    def test_unarchived_oldest_is_attested_then_retired_with_history_preserved(self):
        legacy, catalog_path, plan, lease, identity = self.legacy_case()
        with patch.object(retention, '_context_valid', return_value=True), \
                patch.object(retention, '_inactive', return_value=True), \
                patch.object(retention, 'MAX_COPIES', 1):
            with patch.object(gate, 'require_capacity_rotation', return_value=lease) as grant, \
                    patch.object(gate, 'require_capacity_rotation_continuation', return_value=None) as continuation:
                result = retention_cleanup.apply_capacity_rotation(retention, catalog_path, plan)
            self.assertEqual(grant.call_count, 2)  # capture and immediately before rename
            self.assertEqual(sum(call.kwargs.get('full') is True
                                 for call in continuation.call_args_list), 1)
            self.assertGreater(sum(call.kwargs.get('full') is False
                                   for call in continuation.call_args_list), 0)
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
                        'selected_survivors': {}}
            registry_path.write_text(json.dumps(registry))
            proposal = {204: {'candidate': {'candidate_id': identity['candidate_id']}}}

            def synthetic_scan(*_args, **_kwargs):
                return [{'path': relative, 'absolute_path': str(legacy), **identity,
                         'catalog_record': None, 'publisher_owned': False}]

            def synthetic_resolve(*_args, rotation_receipts=None, **_kwargs):
                self.assertEqual(rotation_receipts, {})
                return {'authority_state': 'COMPLETE', 'blockers': [],
                        'canonical': canonical, 'full_copies': 1,
                        'entries': synthetic_scan(), 'rotated_unavailable': {},
                        'protected_identities': {}}

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
                    patch.object(protection, '_validate_registry', return_value={}), \
                    patch.object(retention, '_context_valid', side_effect=lambda *args, **kwargs: legacy.exists()), \
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

    def test_external_disappearance_after_partial_unlink_never_becomes_complete(self):
        legacy, catalog_path, plan, lease, _ = self.legacy_case()
        original_parent_fd = retention_cleanup._parent_fd
        calls = 0

        def interrupt(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 3:
                raise RuntimeError('injected partial unlink')
            return original_parent_fd(*args, **kwargs)

        with patch.object(retention, '_context_valid', return_value=True), \
                patch.object(retention, '_inactive', return_value=True), \
                patch.object(retention, 'MAX_COPIES', 1), \
                patch.object(gate, 'require_capacity_rotation', return_value=lease), \
                patch.object(gate, 'require_capacity_rotation_continuation', return_value=None):
            with patch.object(retention_cleanup, '_parent_fd', side_effect=interrupt):
                with self.assertRaisesRegex(RuntimeError, 'partial unlink'):
                    retention_cleanup.apply_capacity_rotation(retention, catalog_path, plan)
            journal = next(iter(json.loads(catalog_path.read_bytes())['deletions'].values()))
            self.assertEqual(journal['phase'], 'DELETING')
            shutil.rmtree(journal['trash'])  # Synthetic external loss only.
            with self.assertRaisesRegex(ValueError, 'without final-unlink proof'):
                retention.recover_cleanup(catalog_path)
        state = json.loads(catalog_path.read_bytes())
        self.assertEqual(next(iter(state['retirements'].values()))['state'], 'PARTIAL')
        self.assertTrue(state['deletions'])

    def test_crash_after_durable_final_empty_checkpoint_recovers(self):
        legacy, catalog_path, plan, lease, _ = self.legacy_case()
        original_rmdir = os.rmdir
        failed = False

        def interrupt_final_rmdir(path, *args, **kwargs):
            nonlocal failed
            if Path(path).name.startswith('.retention-trash-') and not failed:
                failed = True
                raise RuntimeError('injected after final checkpoint')
            return original_rmdir(path, *args, **kwargs)

        with patch.object(retention, '_context_valid', return_value=True), \
                patch.object(retention, '_inactive', return_value=True), \
                patch.object(retention, 'MAX_COPIES', 1), \
                patch.object(gate, 'require_capacity_rotation', return_value=lease), \
                patch.object(gate, 'require_capacity_rotation_continuation', return_value=None):
            with patch.object(retention_cleanup.os, 'rmdir', side_effect=interrupt_final_rmdir):
                with self.assertRaisesRegex(RuntimeError, 'after final checkpoint'):
                    retention_cleanup.apply_capacity_rotation(retention, catalog_path, plan)
            journal = next(iter(json.loads(catalog_path.read_bytes())['deletions'].values()))
            self.assertEqual(journal['phase'], 'FINAL_UNLINK_READY')
            self.assertEqual(retention.recover_cleanup(catalog_path), [str(legacy)])
        state = json.loads(catalog_path.read_bytes())
        self.assertEqual(next(iter(state['retirements'].values()))['state'], 'RETIRED_NOT_AVAILABLE')

    def test_slow_final_full_proof_does_not_consume_unlink_deadline(self):
        legacy, catalog_path, plan, lease, _ = self.legacy_case()
        full_calls = 0

        def slow_final(_lease, *, full=True):
            nonlocal full_calls
            if full:
                full_calls += 1
                time.sleep(0.35)

        with patch.object(retention, '_context_valid', return_value=True), \
                patch.object(retention, '_inactive', return_value=True), \
                patch.object(retention, 'MAX_COPIES', 1), \
                patch.object(retention_cleanup, 'UNLINK_DEADLINE_SECONDS', 0.2), \
                patch.object(gate, 'require_capacity_rotation', return_value=lease), \
                patch.object(gate, 'require_capacity_rotation_continuation', side_effect=slow_final):
            self.assertEqual(retention.cleanup_capacity_rotation(catalog_path, plan), [str(legacy)])
        self.assertEqual(full_calls, 1)
        self.assertEqual(next(iter(json.loads(catalog_path.read_bytes())['retirements'].values()))['state'],
                         'RETIRED_NOT_AVAILABLE')

    def test_canonical_change_at_rename_gate_keeps_original_bytes(self):
        legacy, catalog_path, plan, lease, identity = self.legacy_case()
        with patch.object(retention, '_context_valid', return_value=True), \
                patch.object(retention, '_inactive', return_value=True), \
                patch.object(retention, 'MAX_COPIES', 1), \
                patch.object(gate, 'require_capacity_rotation',
                             side_effect=[lease, ValueError('canonical changed before rename')]) as grant, \
                patch.object(gate, 'require_capacity_rotation_continuation', return_value=None):
            with self.assertRaisesRegex(ValueError, 'canonical changed before rename'):
                retention.cleanup_capacity_rotation(catalog_path, plan)
        self.assertEqual(grant.call_count, 2)
        self.assertTrue(legacy.exists())
        self.assertEqual(archive._identity(legacy / 'Integra.app'), identity)
        state = json.loads(catalog_path.read_bytes())
        self.assertEqual(next(iter(state['deletions'].values()))['phase'], 'PREPARED')
        self.assertEqual(next(iter(state['retirements'].values()))['state'], 'PARTIAL')

    def test_pre_repair_journal_gains_fast_anchors_after_one_full_recovery_proof(self):
        legacy, catalog_path, _, _, identity = self.legacy_case()
        old_lease = {'kind': 'OWNER_POLICY_CAPACITY_ROTATION',
                     'physical_survivors': {'Candidate Builds/other': {'identity': identity}}}
        upgraded = {'kind': old_lease['kind'],
                    'physical_survivors': {'Candidate Builds/other': {
                        'identity': identity, 'metadata_anchors': {'manifest': {},
                            'complete': None, 'inventory': None},
                        'manifest_sha256': identity['manifest_digest'],
                        'complete_sha256': None}}}
        receipt = {'transaction_id': 'rotation-v2-old', 'canonical_snapshot': old_lease}
        job = {'kind': 'CAPACITY_ROTATION', 'source': str(legacy),
               'canonical_deletion_lease': old_lease, 'retirement_receipt': receipt}
        catalog = {'deletions': {'old': job}, 'retirements': {'rotation-v2-old': receipt},
                   'protection': {'verified_survivors': {}}}

        def inspect_upgraded(_r, _path, current, token):
            self.assertEqual(token, 'old')
            self.assertEqual(current['deletions'][token]['canonical_deletion_lease'], upgraded)
            self.assertEqual(current['retirements']['rotation-v2-old']['canonical_snapshot'], upgraded)
            return str(legacy)

        with patch.object(gate, 'require_capacity_rotation_continuation', return_value=upgraded) as full, \
                patch.object(retention_cleanup, '_execute', side_effect=inspect_upgraded):
            self.assertEqual(retention_cleanup.recover(retention, catalog_path, catalog), [str(legacy)])
        self.assertEqual(full.call_count, 1)
        self.assertEqual(json.loads(catalog_path.read_bytes())['deletions']['old']
                         ['canonical_deletion_lease'], upgraded)

    def test_maintenance_to_rotation_uses_bounded_full_gates(self):
        legacy, catalog_path, _, lease, _ = self.legacy_case()
        registry = {'canonical_current': {'current_id': 'fixture-current', 'path': 'CURRENT.json'},
                    'selected_survivors': {}, 'rollback': {'candidate_id': 'fixture-rollback'},
                    'recovery': None, 'explicit_governance_pins': []}
        audit = {'canonical': {'rotation_policy': {'rotation_strategy': 'OLDEST_FULL_COPY_FIRST'}},
                 'rotated_unavailable': {}}
        with patch.object(gate, '_snapshot', return_value=(registry, audit)) as snapshot, \
                patch.object(retention, 'reconcile_catalog', return_value=None) as reconcile, \
                patch.object(retention, '_context_valid', side_effect=AssertionError(
                    'verified local plan must not refetch canonical authority')) as refetch, \
                patch.object(retention, '_inactive', return_value=True), \
                patch.object(retention, 'MAX_COPIES', 1), \
                patch.object(gate, 'require_capacity_rotation', return_value=lease) as grant, \
                patch.object(gate, 'require_capacity_rotation_continuation', return_value=None) as continuation:
            self.assertEqual(retention.maintenance(self.destination, reason='SYNTHETIC_ADMISSION',
                                                   need_slot=True), [str(legacy)])
        self.assertEqual(snapshot.call_count, 2)  # once before, once after retirement
        self.assertEqual(reconcile.call_count, 2)
        refetch.assert_not_called()
        self.assertEqual(grant.call_count, 2)  # lease capture and fresh rename gate
        self.assertEqual(sum(call.kwargs.get('full') is True
                             for call in continuation.call_args_list), 1)
        self.assertGreater(sum(call.kwargs.get('full') is False
                               for call in continuation.call_args_list), 0)
        self.assertFalse(legacy.exists())
        self.assertEqual(json.loads(catalog_path.read_bytes())['deletions'], {})

    def test_fast_anchor_skips_payload_hash_and_final_full_detects_change(self):
        legacy, _, _, _, identity = self.legacy_case()
        expected = gate._rotation_package_attestation(legacy, identity)
        with patch.object(gate, '_rotation_package_attestation',
                          side_effect=AssertionError('fast check must not rehash payload')):
            self.assertTrue(gate._fast_rotation_package_anchor(legacy, expected))
        (legacy / 'build.log').write_text('changed while transaction is open\n')
        self.assertTrue(gate._fast_rotation_package_anchor(legacy, expected))
        self.assertNotEqual(gate._rotation_package_attestation(legacy, identity), expected)

    def test_non_rotation_reconciliation_still_fully_verifies_archive(self):
        with patch.object(gate, 'require_archive_publication', return_value=None), \
                patch.object(retention, 'refresh_protection', return_value=None), \
                patch.object(retention, '_context_valid', return_value=True), \
                patch.object(archive, 'MANAGED_BASE', self.root):
            published = archive.create_archive(self.app, self.destination)
        package = Path(published['archive_path'])
        identity = {key: published[key] for key in archive.IDENTITY_KEYS}
        relative = package.relative_to(self.root).as_posix()
        (package / 'Integra.app/Contents/MacOS/Integra').write_bytes(b'corrupt payload')
        registry = {'selected_survivors': {identity['candidate_id']: relative},
                    'canonical_current': {'current_id': 'fixture-current'}}
        audit = {'authority_state': 'COMPLETE',
                 'protected_identities': {identity['candidate_id']: {
                     'identity': identity, 'reasons': ['CURRENT']}},
                 'entries': [{'path': relative, **identity, 'classification': 'PROTECTED',
                              'verified_protected_archive': True}], 'canonical': {}}
        catalog = {'roots': [str(self.destination)], 'artifacts': {}}
        with self.assertRaisesRegex(ValueError, 'bundle bytes differ'):
            retention.reconcile_catalog(catalog, registry, audit, self.root)

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
