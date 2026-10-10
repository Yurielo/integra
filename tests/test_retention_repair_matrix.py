"""Issue #228's 36-point fail-closed matrix, using isolated actual payloads."""
from __future__ import annotations

import contextlib
import copy
import io
import json
import multiprocessing
import os
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch

from scripts import candidate_lifecycle as lc, candidate_retention as r
from scripts import candidate_archive as archive, candidate_protection_audit as p
from scripts import retention_cleanup as cleanup
from scripts import open_proposal_promotion_transaction as tx
from test_retention_repair_cycle import RealRetentionFixture


IDENTITY = {'candidate_id': 'candidate-v1-' + 'a' * 64,
            'bundle_digest': 'b' * 64, 'manifest_digest': 'c' * 64}
POLICY = {'status': 'PRODUCT_OWNER_AUTHORIZED_ACTIVE', 'authority_ref': 'isolated-owner-policy'}
EVIDENCE = {**IDENTITY, 'immutable_history_complete': True,
            'source': {'commit_sha': 'd' * 40, 'tree_sha': 'e' * 40},
            'canonical_snapshot': {'main_sha': 'd' * 40},
            'acceptance_refs': ['isolated-acceptance'], 'promotion_refs': ['isolated-promotion'],
            'proposal_refs': ['isolated-proposal']}


def lock_probe(path, archive_root, operation, entered, finished):
    entered.set()
    if operation == 'build': r.build_preflight(archive_root, 1024)
    elif operation == 'cleanup': r.maintenance(archive_root, reason='ISOLATED_LOCK_PROOF')
    elif operation == 'recovery': r.recover_cleanup(path)
    else: raise AssertionError('unknown isolated lock operation')
    finished.set()


class RetentionRepairMatrix(unittest.TestCase):
    def setUp(self):
        self.log = io.StringIO()
        redirect = contextlib.redirect_stderr(self.log); redirect.__enter__()
        self.addCleanup(redirect.__exit__, None, None, None)

    def fixture(self, count=2):
        f = RealRetentionFixture(self)
        for index in range(count): f.record(f.bootstrap_archive('initial-' + str(index)))
        f.publish_state(); f.refresh()
        return f

    def record(self):
        return {**IDENTITY, 'status': 'HISTORICAL_PROMOTED',
                'lifecycle_evidence': copy.deepcopy(EVIDENCE)}

    def eligible(self, *, record=None, identity=None, roles=(), **overrides):
        args = {'owned': True, 'integrity_verified': True, 'context_valid': True,
                'inactive': True, 'standing_policy': POLICY}; args.update(overrides)
        return lc.terminal_eligibility(identity or IDENTITY, record or self.record(), roles, **args)

    def plan(self, f):
        return r.plan(json.loads(f.catalog.read_bytes()), free_bytes=f.free)

    def snapshot(self, f):
        return f.capture(f.registry)[2]

    def resolve(self, f):
        return p.resolve(f.registry, f.current, f.proposals, p.scan_local(f.registry, f.base),
                         free_bytes=f.free, canonical=self.snapshot(f), for_deletion=True)

    def test_01_current_is_protected(self):
        f = self.fixture(); audit = f.audit()
        self.assertIn('CURRENT', audit['protected_identities'][f.registry['canonical_current']['candidate_id']]['reasons'])
        self.assertFalse(self.eligible(roles=['CURRENT'])['eligible'])

    def test_02_immediate_rollback_is_protected(self):
        f = self.fixture()
        self.assertIn('CONFIRMED_ROLLBACK', f.audit()['protected_identities'][f.registry['rollback']['candidate_id']]['reasons'])
        self.assertFalse(self.eligible(roles=['CONFIRMED_ROLLBACK'])['eligible'])

    def test_03_selected_recovery_is_protected(self):
        f = self.fixture()
        self.assertIn('CONFIRMED_RECOVERY', f.audit()['protected_identities'][f.registry['recovery']['candidate_id']]['reasons'])
        self.assertFalse(self.eligible(roles=['CONFIRMED_RECOVERY'])['eligible'])

    def test_04_pending_acceptance_is_protected(self):
        f = self.fixture(); receipt = f.bootstrap_archive('pending')
        f.catalog.write_bytes(tx.encoded(f.owner_catalog))
        rows = self.plan(f)['entries']
        row = next(row for row in rows if row.get('candidate_id') == receipt['candidate_id'])
        self.assertNotEqual(row['classification'], 'DELETABLE')
        record = self.record(); record['status'] = 'AWAITING_OWNER_ACCEPTANCE'
        self.assertFalse(self.eligible(record=record)['eligible'])

    def test_05_accepted_unpromoted_is_protected(self):
        f = self.fixture(); receipt = f.bootstrap_archive('accepted-unpromoted')
        candidate = {k: receipt[k] for k in p.IDENTITY}
        f.accepted_unpromoted[75] = {'artifact_type': 'integra.proposed_product_baseline',
                                     'candidate': candidate}
        f.registry['accepted_unpromoted'].append({'pr': 75, **candidate})
        f.publish_state()
        # publish_state selects normal CURRENT/rollback obligations; retain the
        # independently declared accepted-unpromoted obligation explicitly.
        f.registry['selected_survivors'][receipt['candidate_id']] = str(
            Path(receipt['archive_path']).relative_to(f.base))
        (f.repo / tx.REGISTRY).write_bytes(tx.encoded(f.registry)); f.refresh()
        self.assertIn('ACCEPTED_UNPROMOTED',
                      f.audit()['protected_identities'][receipt['candidate_id']]['reasons'])
        self.assertFalse(self.eligible(roles=['ACCEPTED_UNPROMOTED'])['eligible'])
        record = self.record(); record['status'] = 'ACCEPTED_UNPROMOTED'
        self.assertFalse(self.eligible(record=record)['eligible'])

    def test_06_awaiting_promotion_is_protected(self):
        f = self.fixture(); receipt = f.bootstrap_archive('awaiting-promotion')
        candidate = {k: receipt[k] for k in p.IDENTITY}
        f.proposals[76] = {'artifact_type': 'integra.proposed_product_baseline',
                          'candidate': candidate,
                          'owner_acceptance': {'decision': 'PILOT_ACCEPTED'}}
        f.registry['proposed'].append({'pr': 76, 'head_sha': 'e' * 40, **candidate})
        f.owner_catalog['artifacts'][receipt['archive_path']]['status'] = 'AWAITING_CURRENT_PROMOTION'
        f.publish_state(); f.refresh()
        row = next(row for row in self.plan(f)['entries']
                   if row.get('candidate_id') == receipt['candidate_id'])
        self.assertNotEqual(row['classification'], 'DELETABLE')
        self.assertIn('OPEN_PROPOSAL',
                      f.audit()['protected_identities'][receipt['candidate_id']]['reasons'])
        record = self.record(); record['status'] = 'AWAITING_CURRENT_PROMOTION'
        self.assertFalse(self.eligible(record=record)['eligible'])

    def test_07_active_proposal_is_protected(self):
        f = self.fixture(); receipt = f.bootstrap_archive('active-proposal')
        proposal = {'artifact_type': 'integra.proposed_product_baseline',
                    'candidate': {k: receipt[k] for k in p.IDENTITY}}
        f.proposals[77] = proposal
        f.registry['proposed'].append({'pr': 77, 'head_sha': 'e' * 40, **proposal['candidate']})
        f.publish_state(); f.refresh()
        self.assertIn('OPEN_PROPOSAL', f.audit()['protected_identities'][receipt['candidate_id']]['reasons'])
        self.assertFalse(self.eligible(roles=['OPEN_PROPOSAL'])['eligible'])

    def test_08_historical_promoted_identity_remains_historical(self):
        local = {**IDENTITY, 'status': 'AWAITING_OWNER_ACCEPTANCE'}
        replay = lc.replay(local, {IDENTITY['candidate_id']: EVIDENCE}, [])
        self.assertEqual(replay['status'], 'HISTORICAL_PROMOTED')
        self.assertEqual(replay['lifecycle_evidence']['acceptance_refs'], EVIDENCE['acceptance_refs'])

    def test_08a_validated_withdrawal_is_mirrored_to_catalog_not_inferred(self):
        f = self.fixture()
        receipt = f.bootstrap_archive('withdrawn-pending')
        f.catalog.write_bytes(tx.encoded(f.owner_catalog))
        withdrawal = {
            **{key: receipt[key] for key in p.IDENTITY},
            'previous_status': 'AWAITING_OWNER_ACCEPTANCE',
            'resulting_status': 'WITHDRAWN_SUPERSEDED',
            'reason': 'ISOLATED_EXACT_SUPERSESSION',
            'authority_ref': 'https://github.com/Yurielo/integra/issues/1#issuecomment-2',
            'authority_body_sha256': 'a' * 64,
            'history_path': 'state/history/isolated-withdrawal.json',
            'history_sha256': 'b' * 64,
        }
        # The fixture transport supplies an already-validated canonical event;
        # reconciliation must not create one from an unprotected pending row.
        f.withdrawals = [withdrawal]
        f.registry['withdrawn_candidate_lifecycles'] = [withdrawal]
        relative = str(Path(receipt['archive_path']).relative_to(f.base))
        f.registry['withdrawal_deletion_authorizations'] = {
            relative: {**{key: receipt[key] for key in p.IDENTITY},
                       'path': relative, 'authority_ref': withdrawal['authority_ref'],
                       'lifecycle': withdrawal['resulting_status'],
                       'reason': withdrawal['reason'], 'scope': 'ISOLATED_EXACT_WITHDRAWAL'}
        }
        f.publish_state()
        with r.locked(f.catalog) as catalog:
            r.refresh_protection(catalog)
        record = json.loads(f.catalog.read_bytes())['artifacts'][receipt['archive_path']]
        self.assertEqual(record['status'], 'WITHDRAWN_SUPERSEDED')
        self.assertEqual(record['disposition_ref'], withdrawal['authority_ref'])
        self.assertEqual(record['withdrawal_lifecycle_evidence'], withdrawal)
        # The canonical resolver must expose the exact withdrawn identity as
        # eligible.  Physical deletion still has a separate exact-grant gate.
        audit_row = next(row for row in f.audit()['entries']
                         if row.get('candidate_id') == receipt['candidate_id'])
        self.assertEqual(audit_row['classification'], 'ELIGIBLE')

    def test_09_every_standing_condition_is_required(self):
        self.assertTrue(self.eligible()['eligible'])
        for flag in ('owned', 'integrity_verified', 'context_valid', 'inactive'):
            with self.subTest(flag=flag): self.assertFalse(self.eligible(**{flag: False})['eligible'])
        for flag in ('integrity_incident', 'unresolved_successor_transaction', 'historical_gap_obligation',
                     'required_rollback_or_recovery', 'sole_required_representation', 'pin_ref'):
            record = self.record(); record[flag] = True
            with self.subTest(flag=flag): self.assertFalse(self.eligible(record=record)['eligible'])
        record = self.record(); record['lifecycle_evidence'] = {}
        self.assertFalse(self.eligible(record=record)['eligible'])
        self.assertFalse(self.eligible(standing_policy={})['eligible'])

    def test_10_unknown_ownership_is_fail_closed(self):
        self.assertIn('OWNERSHIP_UNKNOWN_OR_UNCONFIRMED', self.eligible(owned=False)['reasons'])

    def test_11_integrity_incident_is_fail_closed(self):
        record = self.record(); record['integrity_incident'] = 'unresolved cache mutation'
        self.assertIn('INTEGRITY_UNPROVEN_OR_INCIDENT', self.eligible(record=record)['reasons'])

    def test_12_ambiguous_lifecycle_is_fail_closed(self):
        record = self.record(); record['status'] = 'UNKNOWN'
        self.assertIn('LIFECYCLE_NOT_TERMINAL', self.eligible(record=record)['reasons'])

    def test_13_exact_promoted_pending_replays_mechanically(self):
        f = self.fixture()
        records = json.loads(f.catalog.read_bytes())['artifacts']
        for record in records.values(): self.assertNotEqual(record['status'], 'AWAITING_OWNER_ACCEPTANCE')
        self.assertTrue(all(record['lifecycle_authority'] == 'CANONICAL_EXACT_PROMOTION_REPLAY'
                            for record in records.values()))

    def test_14_obsolete_survivor_reconciles_from_domain(self):
        f = self.fixture(); obsolete = f.bootstrap_archive('obsolete')
        f.registry['selected_survivors'][obsolete['candidate_id']] = 'Build Archive/obsolete'
        selected = p.reconcile_survivors(f.registry, f.current, f.proposals, self.snapshot(f))
        self.assertNotIn(obsolete['candidate_id'], selected)
        self.assertEqual(set(selected), set(p.protected_domain(f.registry, f.current, f.proposals, self.snapshot(f))))

    def test_15_missing_survivor_fails(self):
        f = self.fixture(); cid = f.registry['canonical_current']['candidate_id']
        f.registry['selected_survivors'].pop(cid)
        self.assertIn('MISSING_SURVIVOR:' + cid, self.resolve(f)['blockers'])

    def test_16_extra_survivor_is_distinguished(self):
        f = self.fixture(); extra = 'candidate-v1-' + '0' * 64
        f.registry['selected_survivors'][extra] = 'Build Archive/extra'
        self.assertIn('EXTRA_SURVIVOR:' + extra, self.resolve(f)['blockers'])

    def test_17_conflicting_survivor_fails(self):
        f = self.fixture(); current = f.registry['canonical_current']['candidate_id']
        f.registry['selected_survivors'][current] = f.registry['selected_survivors'][f.registry['rollback']['candidate_id']]
        self.assertTrue(any(x.startswith('CONFLICTING_SURVIVOR:') for x in self.resolve(f)['blockers']))

    def test_18_unavailable_survivor_fails(self):
        f = self.fixture(); cid = f.registry['canonical_current']['candidate_id']
        f.registry['selected_survivors'][cid] = 'Build Archive/unavailable'
        self.assertIn('UNAVAILABLE_SURVIVOR:' + cid, self.resolve(f)['blockers'])

    def test_19_eight_copies_eligible_history_frees_capacity(self):
        f = self.fixture(4)
        for i in range(4): f.bootstrap_archive('pending-' + str(i))
        f.catalog.write_bytes(tx.encoded(f.owner_catalog)); f.refresh()
        self.assertEqual(f.audit()['full_copies'], 8)
        admitted = r.build_preflight(f.archive_root, 1024)
        self.assertLess(admitted['full_copies'], 8)
        self.assertTrue(json.loads(f.catalog.read_bytes()).get('retirements'))

    def test_20_eight_copies_no_eligible_archive_rejects(self):
        f = self.fixture()
        for i in range(6): f.bootstrap_archive('pending-' + str(i))
        f.catalog.write_bytes(tx.encoded(f.owner_catalog)); f.refresh()
        with self.assertRaisesRegex(ValueError, '8-copy|cap'):
            r.build_preflight(f.archive_root, 1024)
        self.assertEqual(f.audit()['full_copies'], 8)

    def test_21_twenty_gib_exact_threshold_enforced(self):
        f = self.fixture(); self.assertEqual(r.MAX_BYTES, 21474836480)
        with self.assertRaisesRegex(ValueError, 'cap'):
            r.build_preflight(f.archive_root, 21474836480)

    def test_22_exact_free_floor_and_peak_enforced(self):
        f = self.fixture(); self.assertEqual(r.FREE_FLOOR, 16106127360)
        f.free = 16106127360 + 3 * 1024 - 1
        with self.assertRaisesRegex(ValueError, 'reserve|disk|space'):
            r.build_preflight(f.archive_root, 1024)

    def test_23_standalone_copy_maintains_before_cap_gate(self):
        f = self.fixture(4)
        for i in range(4): f.bootstrap_archive('pending-' + str(i))
        f.catalog.write_bytes(tx.encoded(f.owner_catalog)); f.refresh()
        receipt = archive.create_archive(f.app('standalone'), f.archive_root)
        self.assertEqual(archive.verify_archive(Path(receipt['archive_path'])), receipt)
        self.assertLessEqual(f.audit()['full_copies'], 8)
        self.assertTrue(json.loads(f.catalog.read_bytes()).get('retirements'))

    def race_lock(self, operation):
        f = self.fixture()
        # A real process contends for exactly the same existing catalog lock.
        ctx = multiprocessing.get_context('fork')
        entered, finished = ctx.Event(), ctx.Event()
        with r.locked(f.catalog):
            worker = ctx.Process(target=lock_probe, args=(f.catalog, f.archive_root, operation, entered, finished)); worker.start()
            self.assertTrue(entered.wait(5)); self.assertFalse(finished.wait(.1))
        # Real protection/lsof preflight may exceed five seconds after release;
        # this completion budget does not change the held-lock exclusion proof.
        worker.join(60)
        self.assertEqual(worker.exitcode, 0); self.assertTrue(finished.is_set())

    def test_24_build_cleanup_common_lock_blocks_race(self): self.race_lock('build')
    def test_25_promotion_cleanup_common_lock_blocks_race(self):
        f = self.fixture(); f.init_git()
        ctx = multiprocessing.get_context('fork')
        entered, finished = ctx.Event(), ctx.Event()
        workers = []
        def during_real_post_validation():
            worker = ctx.Process(target=lock_probe,
                args=(f.catalog, f.archive_root, 'cleanup', entered, finished))
            workers.append(worker); worker.start()
            self.assertTrue(entered.wait(5))
            self.assertFalse(finished.wait(.15), 'cleanup must stay blocked through actual post-validation')
        f.promotion_observer = during_real_post_validation
        receipt, _ = f.promote('promotion-lock', 125)
        self.assertEqual(len(workers), 1)
        workers[0].join(20)
        self.assertEqual(workers[0].exitcode, 0); self.assertTrue(finished.is_set())
        self.assertEqual(archive.verify_archive(Path(receipt['archive_path'])), receipt)
    def test_26_recovery_cleanup_common_lock_blocks_race(self): self.race_lock('recovery')

    def interrupted(self):
        f = self.fixture(3)
        original = cleanup.os.unlink
        def interrupt(name, *args, **kwargs):
            if kwargs.get('dir_fd') is not None: raise KeyboardInterrupt('isolated unlink interruption')
            return original(name, *args, **kwargs)
        with patch.object(cleanup.os, 'unlink', side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt): r.maintenance(f.archive_root, reason='ISOLATED_CRASH')
        return f

    def test_27_interrupted_cleanup_preserves_journal(self):
        f = self.interrupted(); catalog = json.loads(f.catalog.read_bytes())
        self.assertTrue(catalog['deletions']); self.assertTrue(catalog['retirements'])

    def receipt(self):
        return lc.prepare_retirement(IDENTITY, self.record(),
            {'candidate_id': IDENTITY['candidate_id'], 'bundle': {'digest': IDENTITY['bundle_digest']},
             'identity': {'source': {'commit_sha': 'd' * 40, 'tree_sha': 'e' * 40}}},
            {'verification': 'isolated verified archive'}, transaction_id='isolated-retirement',
            canonical_snapshot={'main_sha': 'd' * 40}, policy=POLICY)

    def test_28_prepared_receipt_never_means_deleted(self):
        f = self.fixture(); receipt = self.receipt()
        changed = lc.update_retirement(receipt, source=f.archive_root, trash=f.root / 'missing')
        self.assertEqual(changed['state'], 'PREPARED'); self.assertTrue(changed['physical_available'])
        with self.assertRaises(ValueError):
            lc.update_retirement(receipt, source=f.archive_root, trash=f.root / 'missing', completed=True)

    def test_29_partial_retirement_is_recoverable(self):
        f = self.interrupted()
        retired = r.recover_cleanup(f.catalog)
        self.assertTrue(retired)
        catalog = json.loads(f.catalog.read_bytes())
        self.assertEqual(catalog['deletions'], {})
        self.assertTrue(all(row['state'] == 'RETIRED_NOT_AVAILABLE' for row in catalog['retirements'].values()))

    def test_30_completed_retirement_not_available(self):
        f = self.fixture(3); retired = r.maintenance(f.archive_root, reason='ISOLATED_TERMINAL')
        self.assertTrue(retired); self.assertTrue(all(not Path(path).exists() for path in retired))
        rows = json.loads(f.catalog.read_bytes())['retirements']
        self.assertTrue(all(row['state'] == 'RETIRED_NOT_AVAILABLE' and not row['physical_available'] for row in rows.values()))

    def test_31_authorization_cannot_replay_for_another_candidate(self):
        proposal = {'proposal_id': 'one-proposal', 'candidate': IDENTITY}
        accepted = tx._authority('PROMOTE_CURRENT one-proposal ' + IDENTITY['candidate_id'], proposal)
        other = copy.deepcopy(proposal); other['candidate']['candidate_id'] = 'candidate-v1-' + '0' * 64
        with self.assertRaises(ValueError): tx._authority(accepted, other)

    def test_32_candidate_substitution_fails(self):
        other = dict(IDENTITY, candidate_id='candidate-v1-' + '0' * 64)
        self.assertFalse(self.eligible(identity=other)['eligible'])

    def test_33_bundle_substitution_fails(self):
        self.assertFalse(self.eligible(identity=dict(IDENTITY, bundle_digest='0' * 64))['eligible'])

    def test_34_manifest_substitution_fails(self):
        self.assertFalse(self.eligible(identity=dict(IDENTITY, manifest_digest='0' * 64))['eligible'])

    def test_35_protected_archive_cannot_be_test_execution_location(self):
        from scripts import archive_execution_guard
        f = self.fixture()
        package = Path(next(iter(json.loads(f.catalog.read_bytes())['artifacts'])))
        with self.assertRaisesRegex(ValueError, 'PROTECTED_ARCHIVE_EXECUTION_REJECTED'):
            archive_execution_guard.require_execution_path(package / archive.APP)

    def test_36_external_archive_loss_detected(self):
        f = self.fixture(); cid = f.registry['canonical_current']['candidate_id']
        package = f.base / f.registry['selected_survivors'][cid]
        shutil.rmtree(package)  # Simulated external loss of isolated fixture ONLY.
        with self.assertRaises(ValueError): archive.verify_archive(package)
        self.assertIn('UNAVAILABLE_SURVIVOR:' + cid, self.resolve(f)['blockers'])

    def test_missing_canonical_protection_blocks_both_build_admissions(self):
        f = self.fixture()
        cid = f.registry['canonical_current']['candidate_id']
        f.registry['selected_survivors'].pop(cid)
        (f.repo / tx.REGISTRY).write_bytes(tx.encoded(f.registry))
        with self.assertRaisesRegex(ValueError, 'protection'):
            r.build_preflight(f.archive_root, 1024)
        with self.assertRaisesRegex(ValueError, 'protection'):
            with r.reserved_build(f.archive_root, 1024, archive_copy=True):
                self.fail('unsafe build reservation must not be entered')
        self.assertEqual(json.loads(f.catalog.read_bytes())['leases'], {})


if __name__ == '__main__': unittest.main()
