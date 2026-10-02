"""Issue212 controlled lifecycle: isolated stores, synthetic authority and bytes.

No CLI bypass: only test-local GitHub/activity adapters. Archive verification,
publication, catalog ownership, reservation, cleanup and reconciliation are real.
"""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import test_candidate_archive as fixtures
from scripts import candidate_retention as r, candidate_archive as archive
from scripts import retention_governance as g, retention_cleanup as executor
from scripts import temp_workspace_lifecycle as lifecycle


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        fixtures.CandidateArchiveTests.setUp(self)
        from test_candidate_retention import OwnedRetentionTests
        OwnedRetentionTests._install_canonical_fixture(self)
    _manifest = fixtures.CandidateArchiveTests._manifest
    _create = fixtures.CandidateArchiveTests._create
    _package = fixtures.CandidateArchiveTests._package
    _expected_path = fixtures.CandidateArchiveTests._expected_path

    def ready(self):
        from test_candidate_retention import OwnedRetentionTests
        return OwnedRetentionTests._ready(self)

    def _context(self, package, survivor):
        from test_candidate_retention import OwnedRetentionTests
        return OwnedRetentionTests._context(self, package, survivor)

    def _catalog(self):
        return self.root / 'retention/catalog.json'

    def plan(self):
        return r.plan(json.loads(self._catalog().read_text()))

    def test_prebuild_maintenance_frees_only_terminal_then_admits_at_cap(self):
        package, survivor = self.ready()
        with patch.object(r, 'MAX_COPIES', 2):
            r.build_preflight(self.destination, 1)
        self.assertFalse(package.exists()); self.assertFalse(package.parent.exists())
        self.assertTrue(survivor.exists())
        self.assertEqual(r.maintenance(self.destination, reason='RETRY'), [])

    def test_missing_authority_preserves_terminal_and_blocks_new_build(self):
        package, survivor = self.ready()
        with patch.object(r, '_context_valid', return_value=False), patch.object(r, 'MAX_COPIES', 2):
            with self.assertRaisesRegex(ValueError, 'archive cap'):
                r.build_preflight(self.destination, 1)
        self.assertTrue(package.exists()); self.assertTrue(survivor.exists())

    def test_nonempty_candidate_container_is_kept(self):
        package, survivor = self.ready()
        evidence = package.parent / 'foreign-evidence'; evidence.write_text('preserve')
        r.maintenance(self.destination, reason='TEST')
        self.assertFalse(package.exists()); self.assertEqual(evidence.read_text(), 'preserve')
        self.assertTrue(survivor.exists())

    def test_recovery_after_last_unlink_also_finishes_empty_container(self):
        package, survivor = self.ready()
        with patch.object(executor, '_finish_container', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                r.cleanup(self._catalog(), self.plan())
        self.assertTrue(package.parent.exists()); self.assertFalse(package.exists())
        self.assertEqual(r.recover_cleanup(self._catalog()), [str(package)])
        self.assertFalse(package.parent.exists()); self.assertTrue(survivor.exists())
        self.assertEqual(r.recover_cleanup(self._catalog()), [])

    def test_diagnostics_include_reason_and_do_not_claim_exclusive_reclaim(self):
        self.ready(); stream = io.StringIO()
        with contextlib.redirect_stderr(stream):
            r.maintenance(self.destination, reason='OBSERVABILITY')
        events = [json.loads(line) for line in stream.getvalue().splitlines()]
        self.assertIn('CANDIDATE_RETAINED', [e['event'] for e in events])
        complete = next(e for e in events if e['event'] == 'CLEANUP_COMPLETED')
        self.assertEqual(complete['physical_reclaim'], 'NOT_EXCLUSIVE_APFS_PROOF')
        self.assertGreater(complete['attributed_bytes'], 0)

    @unittest.skipUnless(sys.platform == 'darwin', 'actual lsof exclusion requires macOS')
    def test_real_open_candidate_cannot_be_reclaimed(self):
        package, survivor = self.ready()
        # Override the helper's test adapter with the actual native probe.
        original = r._inactive
        # Retrieve implementation from a fresh module name without altering it.
        import importlib.util
        spec = importlib.util.spec_from_file_location('issue212_activity_probe', r.__file__)
        probe = importlib.util.module_from_spec(spec); spec.loader.exec_module(probe)
        with (package / 'Integra.app/Contents/MacOS/Integra').open('rb') as handle, \
                patch.object(r, '_inactive', probe._inactive):
            self.assertFalse(r._inactive(package))
            self.assertEqual(r.maintenance(self.destination, reason='ACTIVE_CHECK'), [])
            self.assertTrue(handle.read(1))
        self.assertTrue(package.exists()); self.assertTrue(survivor.exists())

    def test_controlled_twelve_build_and_fixture_promotion_cycles(self):
        model = self.app / 'Contents/Resources/model.bin'
        model.write_bytes(b'immutable synthetic model\0' * 161320)  # ~4 MiB, nonsparse
        self.identity['source']['commit_sha'] = '0' * 40; self._manifest(); recovery = self._create()
        self.identity['source']['commit_sha'] = '1' * 40; self._manifest(); initial = self._create()
        self.identity['source']['commit_sha'] = '2' * 40; self._manifest(); pinned = self._create()
        self.identity['source']['commit_sha'] = '3' * 40; self._manifest(); pending = self._create()
        def record(receipt):
            return {'baseline_id': receipt['candidate_id'], 'candidate': {
                k: receipt[k] for k in ('candidate_id', 'bundle_digest', 'manifest_digest')},
                'acceptance': {'decision': 'USER_ACCEPTED'}}
        current = {'current_id': initial['candidate_id'], 'records': [record(recovery), record(initial)]}
        current_path = self.root / 'fixture-current.json'
        current_path.write_text(json.dumps(current))
        pins = {pinned['candidate_id']: 'ISOLATED_FIXTURE_PROVENANCE_PIN'}
        owner_ref = 'https://github.com/Yurielo/integra/issues/212#issuecomment-1'
        owner_comment = {'user': {'login': 'Yurielo'}, 'body': json.dumps({
            'decision': 'CONFIRMED_RECOVERY', 'candidate_id': recovery['candidate_id'],
            'bundle_digest': recovery['bundle_digest']})}
        def snapshot():
            data = current_path.read_bytes()
            return {'repository': g.REPOSITORY, 'main_sha': g._sha(data)[:40],
                    'current': {'sha256': g._sha(data), 'value': json.loads(data)},
                    'open_prs': {'212': {'head_sha': 'fixture-only', 'proposal': {'value': {
                        'artifact_type': 'integra.proposed_product_baseline',
                        'candidate': record(pending)['candidate']}}}},
                    'policy': {'fixture_only': True}, 'pin_requirements': pins}
        selected = {p['candidate_id']: p['archive_path'] for p in (recovery, initial, pinned, pending)}
        events = io.StringIO(); measurements = []
        temp = tempfile.TemporaryDirectory(prefix='integra-212-e2e-', dir='/private/tmp' if sys.platform == 'darwin' else '/tmp')
        self.addCleanup(temp.cleanup); tmp_base = Path(temp.name).resolve()
        with patch.object(g, 'fetch_snapshot', side_effect=snapshot), \
                patch.object(g, '_get', return_value=owner_comment), \
                patch.object(r, 'refresh_protection', return_value=None), \
                patch.object(r, '_inactive', return_value=True), contextlib.redirect_stderr(events):
            with r.locked(self._catalog()) as catalog:
                catalog['protection'] = {
                    'protected': {cid: ['FIXTURE_PROTECTED'] for cid in selected},
                    'inputs': {str(Path(path) / 'COMPLETE.json'): r._sha(Path(path) / 'COMPLETE.json')
                               for path in selected.values()},
                    'selected_archives': selected,
                    'verified_survivors': {item['candidate_id']: item for item in (recovery, initial, pinned, pending)},
                }
            baseline = self.plan()
            saved_model = model.read_bytes()
            for iteration in range(12):
                r.build_preflight(self.destination, 8 * 1024**2)
                workspace, _ = lifecycle.create_workspace(purpose='issue212-cycle', base=tmp_base,
                                                           expected_bytes=8 * 1024**2, reserve_bytes=r.FREE_FLOOR)
                try:
                    with patch.dict(os.environ, INTEGRA_OWNED_WORKSPACE=str(workspace)):
                        with r.reserved_build(self.destination, 8 * 1024**2, archive_copy=True):
                            output = workspace / 'candidate'; r.require_build_lease(self.destination, output=output)
                            app = output / 'Integra.app'
                            archive.shutil.copytree(self.app, app)
                            # A controlled fresh fixture build: distinct manifest identity;
                            # no native binary/signing/product-acceptance claim.
                            from integra_core.candidate_identity import canonical_bytes, candidate_id
                            value = json.loads((app / archive.EMBEDDED).read_text())
                            value['identity']['source']['commit_sha'] = f'{iteration+4:040x}'
                            value['candidate_id'] = candidate_id(value['identity'])
                            value['identity_sha256'] = value['candidate_id'].removeprefix('candidate-v1-')
                            (app / archive.EMBEDDED).write_bytes(canonical_bytes(value)+b'\n')
                            receipt = archive.create_archive(app, self.destination)
                            during = self.plan()
                finally:
                    lifecycle.cleanup_workspace(workspace, reason='CONTROLLED_CYCLE_COMPLETE', allow_live_owner=True)
                # Technical promotion of fixture authority only; real CURRENT never read/written.
                current['records'].append(record(receipt)); current['current_id'] = receipt['candidate_id']
                current_path.write_text(json.dumps(current))
                # The synthetic authority explicitly retires only the previous
                # fixture candidate.  Real cleanup receives this terminal
                # disposition from the canonical registry; it is never inferred
                # from age or the copy cap.
                with r.locked(self._catalog()) as catalog:
                    for name, artifact in catalog['artifacts'].items():
                        if (artifact['candidate_id'] not in selected
                                and artifact['candidate_id'] != receipt['candidate_id']
                                and artifact['status'] == 'AWAITING_OWNER_ACCEPTANCE'):
                            r.disposition(catalog, Path(name), 'SUPERSEDED',
                                          'fixture-canonical-promotion-authority')
                r.maintenance(self.destination, reason='CANONICAL_FIXTURE_PROMOTION_COMPLETED')
                after = self.plan()
                self.assertTrue(after['protection_context_valid'])
                self.assertLessEqual(during['full_copies'], 8); self.assertLessEqual(after['BEFORE_BYTES'], r.MAX_BYTES)
                self.assertLessEqual(len(list(self.destination.glob('candidate-v1-*'))), 5)
                self.assertEqual(list(tmp_base.glob('integra-owned-*')), [])
                self.assertEqual(self._catalog().parent.is_relative_to(self.root), True)
                for survivor in (recovery, pinned, pending):
                    self.assertEqual(archive.verify_archive(Path(survivor['archive_path'])), survivor)
                model_bytes = (Path(receipt['archive_path']) / 'Integra.app/Contents/Resources/model.bin').read_bytes()
                self.assertEqual(model_bytes, saved_model)
                measurements.append({'iteration': iteration+1, 'archive_count_during': during['full_copies'],
                    'archive_count_after': after['full_copies'], 'archive_allocated_after': after['BEFORE_BYTES'],
                    'tmp_owned_count_after': 0})
            self.assertEqual(after['full_copies'], 5)
            self.assertEqual(r.maintenance(self.destination, reason='IDEMPOTENT_RETRY'), [])
        result = {'issue': 212, 'validation': 'CONTROLLED_SYNTHETIC_FILESYSTEM_LIFECYCLE',
                  'production_product_acceptance': False, 'real_user_artifacts_modified': False,
                  'adapter_boundaries': ['isolated catalog/root/volume-ledger paths', 'synthetic canonical GitHub',
                                         'inactive fixture archive probe', 'synthetic app payload',
                                         'simulated 64-GiB free-space probe'],
                  'policy': {'copies': r.MAX_COPIES, 'bytes': r.MAX_BYTES, 'reserve': r.FREE_FLOOR},
                  'before_bytes': baseline['BEFORE_BYTES'], 'after_bytes': after['BEFORE_BYTES'],
                  'measurements': measurements, 'retained': after['entries'],
                  'events': [json.loads(line) for line in events.getvalue().splitlines()], 'result': 'PASS'}
        if os.environ.get('INTEGRA_212_E2E_REPORT'):
            Path(os.environ['INTEGRA_212_E2E_REPORT']).write_text(json.dumps(result, indent=2))


if __name__ == '__main__':
    unittest.main()
