"""Exact successor authority and production validators; no user archives.

The immutable Git inputs are read from this checkout. Publication fixtures are
isolated clones, remote transport is synthetic, and tiny real archives are
created only in owned test directories. No product build or live merge occurs.
"""
from __future__ import annotations

import copy
import contextlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from integra_core.candidate_identity import candidate_id, canonical_bytes, tree_sha256
from scripts import candidate_archive as archive
from scripts import candidate_protection_audit as protection
from scripts import candidate_protection_gate as gate
from scripts import candidate_retention as retention
from scripts import successor_transaction as transaction
from scripts import promote_proposed_baseline_lite as promotion


ROOT = Path(__file__).resolve().parents[1]


class ExactSuccessorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.event = transaction.make_event(ROOT)
        cls.files = transaction.package(ROOT, cls.event['inputs'])

    def changed(self, *path, value):
        event = copy.deepcopy(self.event)
        cursor = event
        for name in path[:-1]:
            cursor = cursor[name]
        cursor[path[-1]] = value
        return event

    def rejects(self, *path, value):
        with self.assertRaises(ValueError):
            transaction.validate_event(ROOT, self.changed(*path, value=value))

    def test_02_exact_known_gap_with_complete_authority_validates(self):
        self.assertEqual(transaction.validate_event(ROOT, self.event), self.files)
        self.assertEqual(self.event['outgoing_archive_availability'], 'MISSING_WITH_AVAILABLE_EVIDENCE')

    def test_03_unknown_outgoing_archive_gap_fails(self):
        self.rejects('inputs', 'outgoing', 'candidate_id', value='candidate-v1-' + '0' * 64)

    def test_06_wrong_candidate_id_fails(self):
        self.rejects('inputs', 'incoming', 'candidate_id', value='candidate-v1-' + '0' * 64)

    def test_07_wrong_bundle_fails(self):
        self.rejects('inputs', 'incoming', 'bundle_digest', value='0' * 64)

    def test_08_wrong_manifest_fails(self):
        self.rejects('inputs', 'incoming', 'manifest_digest', value='0' * 64)

    def test_09_wrong_baseline_id_fails(self):
        self.rejects('inputs', 'outgoing', 'current_id', value='current-v2-' + '0' * 64)

    def test_10_wrong_current_hash_fails(self):
        self.rejects('inputs', 'outgoing', 'current_sha256', value='0' * 64)

    def test_11_empty_authority_and_wrong_payload_hash_fail(self):
        for role in ('acceptance', 'promotion', 'archive_exception'):
            for field in ('authority_ref', 'payload_sha256', 'original_payload_sha256'):
                for value in ('', ' ', None, '*'):
                    with self.subTest(role=role, field=field, value=value):
                        self.rejects('inputs', 'authority', role, field, value=value)

    def test_12_empty_or_unbound_transaction_id_fails(self):
        for value in ('', ' ', None, 'successor-v1-' + '0' * 64):
            with self.subTest(value=value):
                self.rejects('transaction_id', value=value)

    def test_13_empty_or_corrupt_historical_evidence_fails(self):
        for value in ([], {}, None, [{'path': '*', 'sha256': '0' * 64}]):
            with self.subTest(value=value):
                self.rejects('inputs', 'historical_evidence', value=value)

    def test_14_wrong_proposal_id_fails(self):
        self.rejects('inputs', 'proposal_id', value='proposal-unrelated')

    def test_15_proposal_hash_base_source_evidence_must_be_exact(self):
        for name in ('proposal_sha256', 'accepted_head', 'canonical_base'):
            with self.subTest(name=name):
                self.rejects('inputs', name, value='0' * len(self.event['inputs'][name]))
        for name in ('base_main', 'source', 'evidence_head', 'evidence'):
            with self.subTest(name=name):
                self.rejects('inputs', name, value={})

    def test_16_different_incoming_cannot_reuse_authority(self):
        event = self.changed('inputs', 'incoming', 'candidate_id', value='candidate-v1-' + '1' * 64)
        event['transaction_id'] = 'successor-v1-' + protection.digest(event['inputs'])
        with self.assertRaises(ValueError):
            transaction.validate_event(ROOT, event)

    def test_17_different_successor_cannot_reuse_authority(self):
        self.rejects('result', 'current_id', value='current-v2-' + '0' * 64)
        self.rejects('inputs', 'intended_successor', value='current-v2-' + '0' * 64)

    def test_18_exact_applied_retry_is_idempotent(self):
        self.assertEqual(transaction.canonical_state(self.event, self.files[transaction.CURRENT],
                                                    transaction.encoded(self.event)), 'ALREADY_APPLIED')
        old = transaction.git_bytes(ROOT, transaction.MAIN, transaction.CURRENT)
        self.assertEqual(transaction.canonical_state(self.event, old, None), 'NOT_APPLIED')
        for current, event in ((old, transaction.encoded(self.event)),
                               (self.files[transaction.CURRENT], None),
                               (self.files[transaction.CURRENT], b'{}')):
            with self.subTest(current=protection.sha(current), event=event):
                with self.assertRaises(ValueError):
                    transaction.canonical_state(self.event, current, event)

    def remote(self, *, main=None, head=None, base=None, consumed=False, changed_file=None):
        main = main or transaction.MAIN
        def api(endpoint):
            if endpoint.endswith('/git/ref/heads/main'):
                return {'object': {'sha': main}}
            if endpoint.endswith('/pulls/211'):
                return {'state': 'open', 'head': {'sha': head or transaction.ACCEPTED_HEAD},
                        'base': {'sha': base or transaction.MAIN}}
            raise AssertionError('unexpected network endpoint: ' + endpoint)
        def optional(path, ref):
            if consumed:
                raw = transaction.encoded(self.event) if path == transaction.EVENT else self.files.get(path)
                if path == changed_file:
                    raw = b'{}'
            else:
                raw = {transaction.CURRENT: self.files[transaction.OLD_CURRENT],
                       transaction.REGISTRY: self.files[transaction.OLD_REGISTRY]}.get(path)
            return None if raw is None else (raw, json.loads(raw) if path.endswith('.json') else {})
        return (patch.object(protection, '_api', side_effect=api),
                patch.object(protection, '_optional_remote_file', side_effect=optional),
                patch.object(protection, '_remote_file', side_effect=lambda path, ref: optional(path, ref)))

    def preflight_remote(self, **kwargs):
        patches = self.remote(**kwargs)
        with patches[0], patches[1], patches[2]:
            return transaction.preflight(ROOT, self.event, transaction.ACCEPTED_HEAD, require_tree=False)

    def test_19_stale_external_pr_head_fails(self):
        with self.assertRaisesRegex(ValueError, 'head/base/state'):
            self.preflight_remote(head='0' * 40)

    def test_20_stale_main_or_base_fails(self):
        for key in ('main', 'base'):
            with self.subTest(key=key):
                with self.assertRaisesRegex(ValueError, 'base'):
                    self.preflight_remote(**{key: '0' * 40})

    def test_26_every_package_result_hash_is_bound(self):
        for path in self.event['result']['files']:
            with self.subTest(path=path):
                self.rejects('result', 'files', path, value='0' * 64)
        self.rejects('outgoing_rollback_eligible', value=True)
        self.rejects('outgoing_restorable', value=True)
        self.rejects('single_use', value=False)

    def test_27_unrelated_records_history_and_receipts_remain_exact(self):
        old = json.loads(self.files[transaction.OLD_CURRENT])
        new = json.loads(self.files[transaction.CURRENT])
        self.assertEqual(new['records'][:-1], old['records'])
        self.assertEqual(len(new['records']), len(old['records']) + 1)
        original = json.loads(self.files[transaction.OLD_REGISTRY])
        successor = json.loads(self.files[transaction.REGISTRY])
        for key in ('historical_gaps', 'accepted_unpromoted', 'recovery', 'recovery_selection',
                    'explicit_governance_pins', 'deletion_authorizations', 'deletion_enabled', 'limits'):
            self.assertEqual(successor[key], original[key], key)
        self.assertEqual(successor['proposed'], [r for r in original['proposed'] if r['pr'] != 211])
        self.assertEqual(self.files[transaction.OLD_CURRENT], transaction.git_bytes(ROOT, transaction.MAIN, transaction.CURRENT))
        self.assertEqual(self.files[transaction.OLD_REGISTRY], transaction.git_bytes(ROOT, transaction.MAIN, transaction.REGISTRY))
        self.assertEqual(self.files[transaction.RETIRED], transaction.git_bytes(ROOT, transaction.ACCEPTED_HEAD, transaction.PROPOSAL))
        for item in self.event['inputs']['historical_evidence']:
            self.assertEqual(protection.sha(transaction.git_bytes(ROOT, transaction.MAIN, item['path'])), item['sha256'])

    def test_28_staged_local_event_does_not_consume_remote_authority(self):
        self.assertEqual(transaction.canonical_state(self.event, self.files[transaction.OLD_CURRENT], None), 'NOT_APPLIED')
        self.assertIsNone(self.files[transaction.PROPOSAL])

    def test_29_remote_verification_required_after_ambiguous_result(self):
        with tempfile.TemporaryDirectory(prefix='.integra-applied-loss-', dir=Path.home()) as isolated:
            with patch.object(transaction.Path, 'home', return_value=Path(isolated).resolve()):
                with self.assertRaises((ValueError, OSError)):
                    self.preflight_remote(consumed=True, main='f' * 40)
        self.assertEqual(transaction.canonical_state(self.event, self.files[transaction.CURRENT],
                                                    transaction.encoded(self.event)), 'ALREADY_APPLIED')
        for path in self.files:
            with self.subTest(path=path):
                with self.assertRaises(ValueError):
                    self.preflight_remote(consumed=True, main='f' * 40, changed_file=path)

    def test_30_ordinary_successor_does_not_inherit_gap_authority(self):
        event = self.changed('inputs', 'outgoing', 'candidate_id', value=transaction.INCOMING['candidate_id'])
        event['inputs']['incoming']['candidate_id'] = 'candidate-v1-' + '2' * 64
        event['transaction_id'] = 'successor-v1-' + protection.digest(event['inputs'])
        with self.assertRaises(ValueError):
            transaction.validate_event(ROOT, event)

    def test_real_successor_tree_and_committed_pr_package(self):
        with tempfile.TemporaryDirectory(prefix='.integra-successor-git-', dir=Path.home()) as temporary:
            root = Path(temporary).resolve() / 'repo'
            subprocess.run(['git', 'clone', '--shared', '--no-checkout', str(ROOT), str(root)],
                           check=True, capture_output=True)
            subprocess.run(['git', 'checkout', '--detach', transaction.ACCEPTED_HEAD], cwd=root,
                           check=True, capture_output=True)
            original = (root / transaction.CURRENT).read_bytes()
            for item in self.event['inputs']['authority'].values():
                path = item['authority_ref']
                (root / path).write_bytes((ROOT / path).read_bytes())
            for path, raw in self.files.items():
                target = root / path
                if raw is None:
                    target.unlink()
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(raw)
            event_path = root / transaction.EVENT
            event_path.write_bytes(transaction.encoded(self.event))
            # Real CURRENT/material validators evaluate the proposed tree.
            transaction.validate_tree(root)
            self.assertEqual(transaction.canonical_state(self.event, original, None), 'NOT_APPLIED')
            subprocess.run(['git', 'add', '-A'], cwd=root, check=True, capture_output=True)
            subprocess.run(['git', '-c', 'user.name=Successor QA', '-c',
                            'user.email=qa@example.invalid', 'commit', '-m', 'isolated successor fixture'],
                           cwd=root, check=True, capture_output=True)
            head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
            blob = subprocess.check_output(['git', 'hash-object', '-w', '--stdin'], cwd=root,
                                          input=self.files[transaction.RETIRED]).decode().strip()
            subprocess.run(['git', 'update-index', '--add', '--cacheinfo',
                '100644,' + blob + ',' + transaction.PROPOSAL], cwd=root, check=True, capture_output=True)
            tree = subprocess.check_output(['git', 'write-tree'], cwd=root, text=True).strip()
            bad_head = subprocess.check_output(['git', '-c', 'user.name=QA', '-c',
                'user.email=qa@example.invalid', 'commit-tree', tree, '-p', head,
                '-m', 'invalid active proposal fixture'], cwd=root, text=True).strip()
            subprocess.run(['git', 'read-tree', 'HEAD'], cwd=root, check=True, capture_output=True)
            with self.assertRaisesRegex(ValueError, 'did not retire active Proposal'):
                transaction.preflight(root, self.event, bad_head)
            patches = self.remote(consumed=True, main='f' * 40)
            with patches[0], patches[1], patches[2], patch.object(transaction.Path, 'home', return_value=root.parent):
                with self.assertRaises((ValueError, OSError)):
                    transaction.preflight(root, self.event, head)
            patches = self.remote(consumed=True, main='f' * 40)
            output = io.StringIO()
            with patches[0], patches[1], patches[2], patch.object(promotion, 'ROOT', root), \
                    patch.object(transaction.Path, 'home', return_value=root.parent), \
                    contextlib.redirect_stdout(output):
                self.assertEqual(promotion.main(['--verify-successor', '--expected-head', head]), 1)
            self.assertIn('PROMOTION: FAIL', output.getvalue())
            catalog_path = root.parent / 'owned-retention/catalog.json'
            patches = self.remote(consumed=True, main='f' * 40)
            run = subprocess.run
            with patches[0], patches[1], patches[2], \
                    patch.object(retention, 'catalog_path', return_value=catalog_path), \
                    patch.object(retention, 'managed_roots', return_value=[]), \
                    patch.object(transaction.Path, 'home', return_value=root.parent), \
                    patch.object(transaction.subprocess, 'run', wraps=run) as calls:
                with self.assertRaises((ValueError, OSError)):
                    transaction.merge(root, head)
            self.assertTrue(catalog_path.with_suffix('.lock').is_file())
            self.assertFalse(any(call.args[0][:3] == ['gh', 'pr', 'merge']
                                 for call in calls.call_args_list))
            self.assertFalse(any(call.args[0][:2] == ['git', 'push']
                                 for call in calls.call_args_list))
            successor_snapshot = root / 'state/history/later-successor-current.json'
            successor_snapshot.write_bytes(self.files[transaction.CURRENT])
            later = json.loads(self.files[transaction.CURRENT])
            later_record = copy.deepcopy(later['records'][-1])
            later_record['baseline_id'] = 'current-v2-' + '3' * 64
            later_record['historical_predecessors'] = [{'path': str(successor_snapshot.relative_to(root)),
                'sha256': protection.sha(self.files[transaction.CURRENT])}]
            later['records'].append(later_record)
            later['current_id'] = later_record['baseline_id']
            (root / transaction.CURRENT).write_bytes(transaction.encoded(later))
            transaction.validate_recorded_successor(root)
            successor_snapshot.write_bytes(b'{}')
            with self.assertRaisesRegex(ValueError, 'immutable predecessor'):
                transaction.validate_recorded_successor(root)
            (root / transaction.CURRENT).write_bytes(self.files[transaction.CURRENT])
            (root / transaction.OLD_CURRENT).write_bytes(b'{}')
            with self.assertRaisesRegex(ValueError, 'package differs'):
                transaction.validate_tree(root)

    def merged_fixture(self):
        temporary = tempfile.TemporaryDirectory(prefix='.integra-merged-lineage-', dir=Path.home())
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name).resolve() / 'repo'
        subprocess.run(['git', 'clone', '--shared', '--no-checkout', str(ROOT), str(root)],
                       check=True, capture_output=True)
        subprocess.run(['git', 'checkout', '--detach', '533be2514f74258cc5d32fb905f1b687d1700dae'],
                       cwd=root, check=True, capture_output=True)
        return root

    def test_merged_second_parent_acceptance_lineage_is_exact_and_read_only(self):
        root = self.merged_fixture()
        proposal = json.loads((root / transaction.RETIRED).read_bytes())
        preserved = {path: (root / path).read_bytes() for path in
            (transaction.CURRENT, transaction.REGISTRY, transaction.EVENT,
             transaction.OLD_CURRENT, transaction.OLD_REGISTRY, transaction.RETIRED)}
        preserved.update({item['authority_ref']: (root / item['authority_ref']).read_bytes()
                          for item in self.event['inputs']['authority'].values()})
        parents = subprocess.check_output(['git', 'rev-list', '--parents', '-n', '1', 'HEAD'],
                                          cwd=root, text=True).split()
        self.assertEqual(len(parents), 3)
        subprocess.run(['git', 'merge-base', '--is-ancestor', transaction.ACCEPTED_HEAD, parents[2]],
                       cwd=root, check=True, capture_output=True)
        prior = transaction.baseline.verify_promotion_material(proposal, root, root / transaction.PROPOSAL)
        self.assertIn('promotion pilot acceptance declaration history is unavailable', prior)
        self.assertEqual(transaction.baseline.verify_promotion_material(
            proposal, root, root / transaction.PROPOSAL, acceptance_ref=transaction.ACCEPTED_HEAD), [])
        transaction.validate_tree(root)
        transaction.validate_recorded_successor(root)
        self.assertEqual({path: (root / path).read_bytes() for path in preserved}, preserved)
        self.assertEqual(subprocess.check_output(['git', 'status', '--porcelain'],
                                                cwd=root, text=True).strip(), '')

    def test_consumed_successor_allows_only_later_deletion_authority_fields(self):
        root = self.merged_fixture()
        registry_path = root / transaction.REGISTRY
        registry = json.loads(registry_path.read_bytes())
        registry.update(
            deletion_authorizations={'Build Archive/exact': {
                'path': 'Build Archive/exact', 'authority_ref': 'fixture-owner'}},
            deletion_decision_authority_ref='issue-comment:fixture-delete',
            deletion_decision_token_sha256='1' * 64,
            deletion_enabled=True)
        registry_path.write_bytes(transaction.encoded(registry))
        transaction.validate_recorded_successor(root)
        registry['latest_accepted_candidate_id'] = 'candidate-v1-' + '0' * 64
        registry_path.write_bytes(transaction.encoded(registry))
        with self.assertRaisesRegex(ValueError, 'outside deletion authority'):
            transaction.validate_recorded_successor(root)

    def test_merged_acceptance_anchor_wrong_missing_and_unreachable_fail(self):
        root = self.merged_fixture()
        proposal = json.loads((root / transaction.RETIRED).read_bytes())
        tree = subprocess.check_output(['git', 'rev-parse', transaction.ACCEPTED_HEAD + '^{tree}'],
                                       cwd=root, text=True).strip()
        unreachable = subprocess.check_output(['git', '-c', 'user.name=QA', '-c',
            'user.email=qa@example.invalid', 'commit-tree', tree, '-m', 'unreachable accepted bytes'],
            cwd=root, text=True).strip()
        for ref in ('', ' ', 'HEAD', '0' * 40, transaction.MAIN,
                    self.event['inputs']['evidence_head']['commit_sha'], unreachable):
            with self.subTest(ref=ref):
                errors = transaction.baseline.verify_promotion_material(
                    proposal, root, root / transaction.PROPOSAL, acceptance_ref=ref)
                self.assertIn('promotion proposal record path or acceptance anchor is invalid', errors)
        changed = copy.deepcopy(proposal)
        changed['owner_acceptance']['authority_ref'] = 'different owner instruction'
        errors = transaction.baseline.verify_promotion_material(
            changed, root, root / transaction.PROPOSAL, acceptance_ref=transaction.ACCEPTED_HEAD)
        self.assertIn('promotion proposal record path or acceptance anchor is invalid', errors)
        errors = transaction.baseline.verify_promotion_material(
            proposal, root, root / transaction.RETIRED, acceptance_ref=transaction.ACCEPTED_HEAD)
        self.assertIn('promotion proposal record path or acceptance anchor is invalid', errors)
        self.assertEqual(subprocess.check_output(['git', 'status', '--porcelain'],
                                                cwd=root, text=True).strip(), '')


class RealArchiveAndHistoryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='.integra-successor-test-', dir=Path.home())
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.receipts = []
        self.enterContext(patch.object(archive.shutil, 'disk_usage',
                                       return_value=SimpleNamespace(free=64 * 1024**3)))

    def tiny_archive(self, name):
        app = self.root / name / 'Integra.app'
        manifest_path = app / archive.EMBEDDED
        manifest_path.parent.mkdir(parents=True)
        executable = app / 'Contents/MacOS/Integra'
        executable.parent.mkdir()
        executable.write_bytes(b'isolated fixture ' + name.encode())
        executable.chmod(0o755)
        identity = {'source': {'commit_sha': ('a' if name == 'current' else 'b') * 40}}
        manifest = {'schema_version': '1.0', 'candidate_id': candidate_id(identity),
                    'identity_sha256': candidate_id(identity).removeprefix('candidate-v1-'),
                    'identity': identity,
                    'bundle': {'digest_algorithm': 'sha256-tree-excluding-candidate-manifest',
                               'digest': tree_sha256(app, exclude={archive.EMBEDDED})},
                    'build': {'timestamp': 'synthetic-successor-test'}}
        manifest_path.write_bytes(canonical_bytes(manifest) + b'\n')
        receipt = archive.create_archive(app, self.root / 'Library/Application Support/Integra/Build Archive')
        self.receipts.append(receipt)
        return Path(receipt['archive_path']), {key: receipt[key] for key in protection.IDENTITY}

    def test_01_normal_archives_real_verification_and_operation_gate(self):
        proposed_path, incoming = self.tiny_archive('current')
        outgoing_path, outgoing = self.tiny_archive('accepted')
        for path, expected in ((proposed_path, incoming), (outgoing_path, outgoing)):
            self.assertEqual(archive.verify_archive(path, expected)['status'], 'COMPLETE')
        base = self.root / 'Library/Application Support/Integra'
        current = {'current_id': 'fixture-current', 'records': [
            {'baseline_id': 'fixture-previous', 'candidate': incoming},
            {'baseline_id': 'fixture-current', 'candidate': outgoing}]}
        current_path = self.root / transaction.CURRENT
        current_path.parent.mkdir(parents=True)
        current_path.write_bytes(transaction.encoded(current))
        registry = json.loads(transaction.git_bytes(ROOT, transaction.MAIN, transaction.REGISTRY))
        token = ('PRODUCT_OWNER_AUTHORIZATION: FIXTURE EXPLICIT_GOVERNANCE_PINS={} '
                 'DELETION_AUTHORIZATIONS={} DELETION_ENABLED=false')
        registry.update(canonical_current={'path': transaction.CURRENT, 'current_id': current['current_id'],
            'sha256': protection.sha(current_path.read_bytes()), **outgoing},
            latest_accepted_candidate_id=outgoing['candidate_id'],
            rollback={**incoming, 'confirmation_ref': 'fixture-rollback'},
            recovery={**outgoing, 'confirmation_ref': 'fixture-recovery'}, recovery_selection=None,
            proposed=[], accepted_unpromoted=[], historical_gaps=[], successor_transactions=[],
            decision_authority_ref='fixture-owner', activation_authority_ref='fixture-owner',
            decision_token_sha256=protection.sha(token.encode()),
            selected_survivors={incoming['candidate_id']: str(proposed_path.relative_to(base)),
                                outgoing['candidate_id']: str(outgoing_path.relative_to(base))})
        canonical = {'current_sha256': registry['canonical_current']['sha256'],
                     'decision_authority_ref': 'fixture-owner',
                     'decision_token_sha256': registry['decision_token_sha256'],
                     'decision_token': token, 'historical_receipts': {}, 'accepted_unpromoted': {}}
        registry_path = self.root / transaction.REGISTRY
        registry_path.write_bytes(transaction.encoded(registry))
        # Only external authority transport and host locations are replaced.
        # Snapshot, scanning, resolver, selected-survivor gate and byte verifier run.
        with patch.object(gate.Path, 'home', return_value=self.root), \
                patch.object(protection, 'ROOT', self.root), \
                patch.object(protection, 'REGISTRY', registry_path), \
                patch.object(protection, 'fetch_canonical', return_value=(current, {}, canonical)):
            gate.require_promotion({'candidate': incoming}, current, proposed_path, outgoing_path)
            with self.assertRaisesRegex(ValueError, 'outgoing CURRENT archive'):
                gate.require_promotion({'candidate': incoming}, current, proposed_path, None)

    def test_04_missing_incoming_real_archive_fails(self):
        with self.assertRaises((OSError, ValueError)):
            archive.verify_archive(self.root / 'missing', transaction.INCOMING)

    def test_05_corrupted_incoming_real_archive_fails(self):
        path, identity = self.tiny_archive('current')
        (path / archive.APP / 'Contents/MacOS/Integra').write_bytes(b'corrupt')
        with self.assertRaises(ValueError):
            archive.verify_archive(path, identity)

    def test_archive_id_bundle_manifest_are_each_independently_checked(self):
        path, identity = self.tiny_archive('current')
        for key in protection.IDENTITY:
            with self.subTest(key=key):
                bad = dict(identity)
                bad[key] = 'candidate-v1-' + '0' * 64 if key == 'candidate_id' else '0' * 64
                with self.assertRaises(ValueError):
                    archive.verify_archive(path, bad)

    def history_fixture(self):
        bound = transaction.inputs(ROOT)
        files = transaction.package(ROOT, bound)
        current, registry = json.loads(files[transaction.CURRENT]), json.loads(files[transaction.REGISTRY])
        incoming_path, incoming = self.tiny_archive('current')
        accepted_path, accepted = self.tiny_archive('accepted')
        # Synthetic identities let the actual archive verifier run without
        # reading multi-GiB accepted applications. The historical anchors stay exact.
        current['current_id'] = 'current-v2-' + incoming['candidate_id'][13:]
        current['records'][-1]['baseline_id'] = current['current_id']
        current['records'][-1]['candidate'].update(incoming)
        registry['canonical_current'].update(incoming, current_id=current['current_id'],
                                              sha256=protection.sha(transaction.encoded(current)))
        registry['latest_accepted_candidate_id'] = incoming['candidate_id']
        registry['selected_survivors'].pop(transaction.INCOMING['candidate_id'])
        registry['selected_survivors'][incoming['candidate_id']] = str(incoming_path.relative_to(self.root))
        old_accepted = registry['accepted_unpromoted'][0]['candidate_id']
        registry['accepted_unpromoted'][0].update(accepted)
        registry['selected_survivors'].pop(old_accepted)
        registry['selected_survivors'][accepted['candidate_id']] = str(accepted_path.relative_to(self.root))
        proposals = {row['pr']: {'artifact_type': 'integra.proposed_product_baseline',
                                'candidate': {key: row[key] for key in protection.IDENTITY}}
                     for row in registry['proposed']}
        token = ('PRODUCT_OWNER_AUTHORIZATION: ISSUE_214_ACCEPT_PROTECTION_DECISIONS ' +
                 ' '.join(gap['role'] + '_RECOVERY_GAP=' + gap['candidate_id'] +
                          ':MISSING_WITH_AVAILABLE_EVIDENCE' for gap in registry['historical_gaps']) +
                 ' EXPLICIT_GOVERNANCE_PINS={} UNKNOWN=RETAIN_FAIL_CLOSED DELETION_AUTHORIZATIONS={} '
                 'CANONICAL_PROTECTION_AUTHORITY=state/candidate_protection_registry_v1.json')
        canonical = {'current_sha256': registry['canonical_current']['sha256'],
                     'decision_authority_ref': registry['decision_authority_ref'],
                     'decision_token_sha256': registry['decision_token_sha256'],
                     'decision_token': token,
                     'successor_transactions': {transaction.make_event(ROOT)['transaction_id']:
                                                transaction.make_event(ROOT)},
                     'historical_receipts': {gap['candidate_id']: {'path': gap['receipt_path'],
                         'record': json.loads(transaction.git_bytes(ROOT, transaction.MAIN, gap['receipt_path']))}
                         for gap in registry['historical_gaps']},
                     'accepted_unpromoted': {213: {'candidate': accepted}}}
        packages = [{'path': str(path.relative_to(self.root)), 'absolute_path': str(path), **identity,
                     'allocated_bytes': 4096, 'publisher_owned': True, 'lifecycle': 'COMPLETED',
                     'inactive': True, 'metadata_error': None}
                    for path, identity in ((incoming_path, incoming), (accepted_path, accepted))]
        return current, registry, proposals, canonical, packages

    def resolved(self):
        current, registry, proposals, canonical, packages = self.history_fixture()
        result = protection.resolve(registry, current, proposals, packages,
                                    free_bytes=64 * 1024**3, canonical=canonical)
        return result, registry

    def test_21_gap_does_not_follow_current_role(self):
        result, registry = self.resolved()
        self.assertEqual(result['authority_state'], 'COMPLETE', result['blockers'])
        self.assertNotIn(registry['canonical_current']['candidate_id'], result['historical_availability'])
        self.assertIn(transaction.OUTGOING['candidate_id'], result['historical_availability'])

    def test_22_older_gap_remains_protected_after_predecessor_moves(self):
        result, registry = self.resolved()
        older = next(g['candidate_id'] for g in registry['historical_gaps'] if g['role'] == 'ROLLBACK')
        self.assertNotEqual(older, registry['rollback']['candidate_id'])
        self.assertIn('ACCEPTED_HISTORICAL_GAP', result['protected_identities'][older]['reasons'])
        self.assertEqual(result['authority_state'], 'COMPLETE', result['blockers'])

    def test_23_missing_outgoing_is_not_restorable_or_rollback_eligible(self):
        result, _ = self.resolved()
        outgoing = result['historical_availability'][transaction.OUTGOING['candidate_id']]
        self.assertFalse(outgoing['rollback_eligible'])
        self.assertFalse(outgoing['restorable_from_retained_archive'])

    def test_24_incoming_current_has_strict_byte_protection(self):
        result, registry = self.resolved()
        incoming = registry['canonical_current']['candidate_id']
        row = next(row for row in result['entries'] if row['candidate_id'] == incoming)
        self.assertTrue(row['verified_protected_archive'])
        self.assertEqual(row['classification'], 'PROTECTED')
        self.assertNotIn(incoming, result['historical_availability'])

    def test_25_post_promotion_actual_resolver_and_archives_pass(self):
        result, _ = self.resolved()
        self.assertEqual(result['authority_state'], 'COMPLETE', result['blockers'])
        self.assertTrue(result['promotion_ready'], result['promotion_blockers'])
        self.assertEqual(result['eligible_bytes'], 0)

    def test_missing_or_changed_transaction_pointer_blocks_resolver(self):
        current, registry, proposals, canonical, packages = self.history_fixture()
        for events in ({}, {'unrelated': {}}):
            with self.subTest(events=events):
                canonical['successor_transactions'] = events
                result = protection.resolve(registry, current, proposals, packages,
                                            free_bytes=64 * 1024**3, canonical=canonical)
                self.assertIn('CONSUMED_SUCCESSOR_TRANSACTION_MISSING_OR_CONFLICT', result['blockers'])
        canonical['successor_transactions'] = {transaction.make_event(ROOT)['transaction_id']: transaction.make_event(ROOT)}
        registry['successor_transactions'][0]['transaction_id'] = 'successor-v1-' + '0' * 64
        result = protection.resolve(registry, current, proposals, packages,
                                    free_bytes=64 * 1024**3, canonical=canonical)
        self.assertIn('CONSUMED_SUCCESSOR_TRANSACTION_MISSING_OR_CONFLICT', result['blockers'])
        registry['successor_transactions'] = []
        current['records'][-1]['baseline_id'] = transaction.NEW_ID
        current['current_id'] = transaction.NEW_ID
        registry['canonical_current']['current_id'] = transaction.NEW_ID
        result = protection.resolve(registry, current, proposals, packages,
                                    free_bytes=64 * 1024**3, canonical=canonical)
        self.assertIn('CONSUMED_SUCCESSOR_TRANSACTION_MISSING_OR_CONFLICT', result['blockers'])

    def test_non_force_merge_ref_transition_rejects_concurrent_main(self):
        repository = self.root / 'git-writer'
        remote = self.root / 'remote.git'
        subprocess.run(['git', 'init', '--bare', str(remote)], check=True, capture_output=True)
        subprocess.run(['git', 'init', str(repository)], check=True, capture_output=True)
        def git(*args):
            return subprocess.check_output(['git', '-c', 'user.name=QA', '-c',
                'user.email=qa@example.invalid', *args], cwd=repository, text=True).strip()
        (repository / 'fixture').write_text('base')
        git('add', 'fixture'); git('commit', '-m', 'base')
        base = git('rev-parse', 'HEAD')
        git('remote', 'add', 'origin', str(remote))
        git('push', 'origin', base + ':refs/heads/main')
        (repository / 'fixture').write_text('reviewed proposal')
        git('add', 'fixture'); git('commit', '-m', 'proposal')
        proposal = git('rev-parse', 'HEAD')
        merge = git('commit-tree', git('rev-parse', proposal + '^{tree}'),
                    '-p', base, '-p', proposal, '-m', 'reviewed merge')
        advanced = git('commit-tree', git('rev-parse', base + '^{tree}'), '-p', base, '-m', 'concurrent main')
        git('push', 'origin', advanced + ':refs/heads/main')
        refused = subprocess.run(['git', 'push', 'origin', merge + ':refs/heads/main'],
                                 cwd=repository, capture_output=True, text=True)
        self.assertNotEqual(refused.returncode, 0)
        self.assertEqual(git('ls-remote', 'origin', 'refs/heads/main').split()[0], advanced)

    def test_managed_retention_uses_exclusive_catalog_lock(self):
        catalog = self.root / 'retention/catalog.json'
        with patch.object(retention, 'managed_roots', return_value=[]):
            with retention.locked(catalog):
                probe = subprocess.run(['python3', '-c',
                    'import fcntl,sys;f=open(sys.argv[1],"r+");'
                    '\ntry: fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)'
                    '\nexcept BlockingIOError: sys.exit(0)'
                    '\nsys.exit(1)', str(catalog.with_suffix('.lock'))], capture_output=True)
                self.assertEqual(probe.returncode, 0, probe.stderr)
        self.assertEqual(json.loads(catalog.read_bytes())['artifact_type'], 'integra.owned_archive_catalog')


if __name__ == '__main__':
    unittest.main()
