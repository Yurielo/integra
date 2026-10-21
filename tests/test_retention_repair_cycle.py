"""Real tiny archive rollover; only transport and host paths are isolated.

The initial accepted archives are fixture inputs, not newly admitted copies.
Every subsequent copy, promotion package, protection resolution, capacity
reservation and retirement uses the production implementation. No real
Candidate/catalog/CURRENT is consulted or mutated.
"""
from __future__ import annotations

import copy
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from integra_core.candidate_identity import canonical_bytes, candidate_id, tree_sha256
from scripts import candidate_archive as archive, candidate_protection_audit as p
from scripts import candidate_protection_gate as gate, candidate_retention as r
from scripts import build_disk_admission as disk, open_proposal_promotion_transaction as tx
from scripts import proposed_baseline_lite as baseline, candidate_lifecycle as lifecycle


class RealRetentionFixture:
    """Exact isolated canonical transport plus independently verified payloads."""
    def __init__(self, case):
        self.case = case
        self.temp = tempfile.TemporaryDirectory(prefix='.integra-retention-proof-', dir=Path.home())
        case.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.home = self.root / 'home'; self.home.mkdir()
        self.base = self.home / 'Library/Application Support/Integra'
        self.repo = self.root / 'canonical'; self.repo.mkdir()
        self.archive_root = self.base / 'Build Archive'; self.archive_root.mkdir(parents=True)
        self.catalog = self.root / 'retention/catalog.json'; self.catalog.parent.mkdir()
        self.current = {'schema_version': '2.0', 'artifact_type': 'integra.current_product_baseline',
                        'current_id': '', 'records': []}
        self.registry = {'schema_version': '1.0', 'artifact_type': 'integra.candidate_protection_registry',
            'status': 'PRODUCT_OWNER_AUTHORIZED_ACTIVE', 'activation_authority_ref': 'fixture-owner',
            'decision_authority_ref': 'fixture-owner', 'decision_token_sha256': 'fixture-token',
            'promotion_contract_integration_ref': p.INTEGRATION_REF,
            'managed_roots': sorted(p.ROOT_NAMES), 'limits': {
                'max_full_copies': 8, 'max_attributed_bytes': 21474836480,
                'minimum_free_after_reservations': 16106127360},
            'canonical_current': {}, 'latest_accepted_candidate_id': '', 'rollback': {},
            'recovery': None, 'recovery_selection': None, 'proposed': [],
            'accepted_unpromoted': [], 'explicit_governance_pins': {},
            'historical_gaps': [], 'successor_transactions': [],
            'selected_survivors': {}, 'deletion_enabled': False, 'deletion_authorizations': {},
            'withdrawn_candidate_lifecycles': [],
            'standing_retention_policy': {'status': 'PRODUCT_OWNER_AUTHORIZED_ACTIVE',
                                         'authority_ref': 'fixture-standing-owner', 'sha256': 'f' * 64,
                                         'rotation_strategy': 'OLDEST_PROVEN_ELIGIBLE_FIRST',
                                         'rotation_scope': 'ONE_FULL_COPY_PER_TRANSACTION',
                                         'all_protected': 'FAIL_CLOSED_NO_NINTH_ARCHIVE'},
            'lifecycle_events': []}
        self.events = {}; self.proposals = {}; self.accepted_unpromoted = {}
        self.withdrawals = []
        self.free = 64 * 1024**3; self.counter = 1
        self.main = '1' * 40
        self.remote = None
        self.promotion_observer = None
        (self.repo / 'governed.txt').write_text('unchanged tiny product fixture')
        (self.repo / 'state/history').mkdir(parents=True)
        (self.repo / 'state/history/bootstrap.json').write_text('{}')
        self.owner_catalog = r._empty()
        self.owner_catalog['roots'] = [str(self.base / name) for name in sorted(p.ROOT_NAMES)]
        self._install()

    def _install(self):
        def paths(target):
            target = Path(target).resolve()
            while not target.exists(): target = target.parent
            return target, self.root / 'volume.lock', self.root / 'volume.json'
        for item in (
            patch.object(Path, 'home', return_value=self.home),
            patch.object(archive, 'MANAGED_BASE', self.base),
            patch.object(r, 'catalog_path', return_value=self.catalog),
            patch.object(disk, '_paths', side_effect=paths),
            patch.object(shutil, 'disk_usage', side_effect=lambda _: SimpleNamespace(free=self.free)),
            patch.object(p, 'ROOT', self.repo),
            patch.object(p, 'REGISTRY', self.repo / tx.REGISTRY),
            patch.object(p, 'fetch_canonical', side_effect=self.capture),
        ):
            item.start(); self.case.addCleanup(item.stop)

    def capture(self, registry):
        """Fixture external transport, never substitute resolver/gate results."""
        current, events, main = self.current, self.events, self.main
        if self.remote is not None:
            main = subprocess.check_output(['git', '--git-dir', str(self.remote),
                                            'rev-parse', 'refs/heads/main'], text=True).strip()
            def remote_blob(name):
                return subprocess.check_output(['git', '--git-dir', str(self.remote),
                                                 'show', main + ':' + name])
            current = json.loads(remote_blob(tx.CURRENT))
            events = {}
            names = subprocess.check_output(['git', '--git-dir', str(self.remote), 'ls-tree', '-r',
                                              '--name-only', main, 'state/history'], text=True).splitlines()
            for name in names:
                if name.endswith('_promotion_transaction_v1.json'):
                    event = json.loads(remote_blob(name))
                    retired = tx._paths({'candidate': event['inputs']['candidate']})['retired']
                    if retired in names:
                        event['inputs']['source'] = json.loads(remote_blob(retired))['proposed_source']
                    events[name] = event
        current_raw = tx.encoded(current)
        consumed = {record['candidate']['candidate_id'] for record in current['records']}
        proposals = {number: value for number, value in self.proposals.items()
                     if value['candidate']['candidate_id'] not in consumed}
        canonical = {'main_sha': self.main,
            'current_sha256': p.sha(current_raw),
            'decision_authority_ref': 'fixture-owner', 'decision_token_sha256': 'fixture-token',
            'decision_token': 'PRODUCT_OWNER_AUTHORIZATION: FIXTURE EXPLICIT_GOVERNANCE_PINS={} DELETION_AUTHORIZATIONS={} DELETION_ENABLED=false',
            'historical_receipts': {}, 'successor_transactions': {},
            'proposal_heads': {str(n): row['head_sha'] for n, row in
                              ((row['pr'], row) for row in self.registry['proposed'])},
            'accepted_unpromoted': copy.deepcopy(self.accepted_unpromoted),
            'withdrawn_candidate_lifecycles': copy.deepcopy(self.withdrawals),
            'promotion_events': copy.deepcopy(events),
            'lifecycle_events': copy.deepcopy(events),
            'standing_retention_policy': copy.deepcopy(self.registry['standing_retention_policy'])}
        canonical['main_sha'] = main
        canonical['canonical_lifecycles'] = lifecycle.collect_lifecycle_events(
            current, events, {'main_sha': main, 'current_sha256': canonical['current_sha256']})
        canonical['standing_policy'] = copy.deepcopy(self.registry['standing_retention_policy'])
        canonical['current_json'] = copy.deepcopy(current)
        return copy.deepcopy(current), copy.deepcopy(proposals), canonical

    def app(self, label, *, source=None):
        app = self.root / 'sources' / label / 'Integra.app'
        manifest_path = app / archive.EMBEDDED
        manifest_path.parent.mkdir(parents=True)
        executable = app / 'Contents/MacOS/Integra'; executable.parent.mkdir()
        executable.write_bytes(('tiny representative payload ' + label).encode()); executable.chmod(0o755)
        identity = {'source': {'commit_sha': f'{self.counter:040x}', 'tree_sha': f'{self.counter+100:040x}'},
                    'execution': {'gui_python': {'path': '/fixture/python', 'sha256': 'a' * 64}}}
        self.counter += 1
        if source is not None: identity['source'] = {**source, 'dirty': False}
        manifest = {'schema_version': '1.0', 'candidate_id': candidate_id(identity),
            'identity_sha256': candidate_id(identity).removeprefix('candidate-v1-'), 'identity': identity,
            'bundle': {'digest_algorithm': 'sha256-tree-excluding-candidate-manifest',
                       'digest': tree_sha256(app, exclude={archive.EMBEDDED})},
            'build': {'timestamp': 'isolated-proof'}}
        manifest_path.write_bytes(canonical_bytes(manifest) + b'\n')
        return app

    def git(self, *args):
        return subprocess.check_output(['git', *args], cwd=self.repo, text=True,
                                       stderr=subprocess.PIPE).strip()

    def commit(self, message):
        self.git('add', '.')
        self.git('commit', '-qm', message)
        return {'commit_sha': self.git('rev-parse', 'HEAD'), 'tree_sha': self.git('rev-parse', 'HEAD^{tree}')}

    def init_git(self):
        self.git('init', '-q')
        self.git('config', 'user.name', 'Isolated Retention QA')
        self.git('config', 'user.email', 'retention-fixture@example.invalid')
        target = self.repo / 'integra_core/fixture.py'; target.parent.mkdir()
        target.write_text('version = 0\n')
        anchor = self.commit('initial isolated product')
        self.current['records'][-1]['main'] = anchor
        self.current['records'][-1]['governed_files'].append({'path': 'integra_core/fixture.py',
                                                           'sha256': p.sha(target.read_bytes())})
        self.publish_state()
        self.main = self.commit('isolated canonical authority')['commit_sha']
        self.remote = self.root / 'canonical-origin.git'
        subprocess.run(['git', 'init', '--bare', '-q', str(self.remote)], check=True)
        self.git('remote', 'add', 'origin', str(self.remote))
        self.git('push', '-q', 'origin', self.main + ':refs/heads/main')

    def prepare_proposal(self, label, number):
        self.owner_catalog = json.loads(self.catalog.read_bytes())
        target = self.repo / 'integra_core/fixture.py'
        before = p.sha(target.read_bytes()); target.write_text('version = ' + str(number) + '\n')
        source = self.commit('isolated product ' + label)
        receipt = archive.create_archive(self.app(label, source=source), self.archive_root)
        manifest = Path(receipt['archive_path']) / archive.MANIFEST_NAME
        evidence_dir = self.repo / ('docs/evidence/' + label); evidence_dir.mkdir(parents=True)
        shutil.copy2(manifest, evidence_dir / 'manifest.json')
        evidence = {'candidate_id': receipt['candidate_id'],
                    'manifest_identity_sha256': receipt['candidate_id'][13:],
                    'bundle_digest': receipt['bundle_digest'], 'product_source': source}
        (evidence_dir / 'evidence.json').write_bytes(tx.encoded(evidence))
        (evidence_dir / 'report.txt').write_text('Isolated representative rollover proof; not product acceptance.')
        overlay = self.commit('isolated evidence ' + label)
        active = self.current['records'][-1]
        proposal = {'schema_version': '1.0', 'artifact_type': 'integra.proposed_product_baseline',
            'proposal_id': 'proposal-' + label, 'status': 'PROPOSED_BASELINE_VALID',
            'base_current_id': self.current['current_id'], 'base_main': active['main'],
            'proposed_source': source, 'proposed_head': overlay,
            'intended_scope': {'wp': 'isolated-retention-proof', 'journey': 'mechanical rollover'},
            'candidate': {**{k: receipt[k] for k in p.IDENTITY}, 'identity_sha256': receipt['candidate_id'][13:]},
            'delta': [{'path': 'integra_core/fixture.py', 'before_sha256': before,
                       'after_sha256': p.sha(target.read_bytes())}], 'historical_test_successors': [],
            'gates': [{'name': 'isolated-bound-evidence', 'result': 'PASS',
                       'evidence_ref': str((evidence_dir / 'evidence.json').relative_to(self.repo))}],
            'evidence': {key: {'path': str((evidence_dir / name).relative_to(self.repo)),
                               'sha256': p.sha((evidence_dir / name).read_bytes())}
                         for key, name in (('candidate_manifest', 'manifest.json'),
                                           ('candidate_evidence', 'evidence.json'), ('report', 'report.txt'))},
            'owner_acceptance': None,
            'allowed_overlay_paths': [str(path.relative_to(self.repo)) for path in evidence_dir.iterdir()]}
        proposal_path = self.repo / tx.PROPOSAL; proposal_path.write_bytes(tx.encoded(proposal))
        self.commit('isolated proposed baseline declaration')
        proposal['owner_acceptance'] = {'decision': 'PILOT_ACCEPTED', 'authority_ref': 'fixture owner acceptance',
                                        'scope': 'isolated fixture only', 'promotion_authorized': False}
        proposal_path.write_bytes(tx.encoded(proposal))
        head = self.commit('isolated exact owner acceptance')['commit_sha']
        self.proposals[number] = proposal
        return proposal, receipt, head

    def promote(self, label, number):
        proposal, receipt, head = self.prepare_proposal(label, number)
        authority = 'PROMOTE_CURRENT ' + proposal['proposal_id'] + ' ' + receipt['candidate_id']
        remote = {'state': 'open', 'head': {'sha': head}, 'base': {'sha': self.main}}
        def api(endpoint):
            if endpoint.endswith('/check-runs'):
                return {'check_runs': [{'name': 'governance', 'conclusion': 'success'}]}
            if endpoint.endswith('/pulls/' + str(number)): return remote
            raise AssertionError('unexpected isolated transport endpoint: ' + endpoint)
        original_post = tx.validate_post
        def observed_post(*args, **kwargs):
            audit = original_post(*args, **kwargs)
            if self.promotion_observer is not None: self.promotion_observer()
            return audit
        with patch.object(p, '_api', side_effect=api), patch.object(tx, 'validate_post', side_effect=observed_post):
            merge = tx.apply(self.repo, pr=number, expected_head=head,
                             expected_base=self.main, authorization=authority)
        self.git('checkout', '--detach', '-q', merge)
        self.current = json.loads((self.repo / tx.CURRENT).read_bytes())
        self.registry = json.loads((self.repo / tx.REGISTRY).read_bytes())
        event = json.loads((self.repo / tx._paths(proposal)['event']).read_bytes())
        self.proposals.pop(number)
        self.events[tx._paths(proposal)['event']] = {**event, 'inputs': {
            **event['inputs'], 'source': copy.deepcopy(proposal['proposed_source'])}}
        self.main = merge
        self.refresh()
        return receipt, event

    def bootstrap_archive(self, label):
        """Prepare independently accepted pre-state; no admission bypass later."""
        app = self.app(label); identity = archive._identity(app)
        package = self.archive_root / identity['candidate_id'] / identity['bundle_digest']
        package.mkdir(parents=True)
        shutil.copytree(app, package / archive.APP)
        shutil.copy2(app / archive.EMBEDDED, package / archive.MANIFEST_NAME)
        inventory = archive._inventory(package)
        (package / archive.INVENTORY).write_bytes(canonical_bytes(inventory) + b'\n')
        receipt = archive._receipt(identity, inventory, archive._hash(package / archive.INVENTORY))
        (package / archive.COMPLETE).write_bytes(canonical_bytes(receipt) + b'\n')
        verified = archive.verify_archive(package)
        s = package.stat()
        self.owner_catalog['artifacts'][str(package)] = {
            **{k: verified[k] for k in ('candidate_id', 'bundle_digest', 'manifest_digest', 'inventory_sha256')},
            'complete_sha256': r._sha(package / archive.COMPLETE),
            'owner_uid': os.getuid(), 'device': s.st_dev, 'inode': s.st_ino,
            'publisher_run_id': 'isolated-bootstrap-' + label, 'publisher_pid': os.getpid(),
            'publisher_start_token': disk._start(os.getpid()), 'publisher_completed': True,
            'publication_sequence': len(self.owner_catalog['artifacts']) + 1,
            'status': 'AWAITING_OWNER_ACCEPTANCE', 'historical': False}
        return verified

    def record(self, receipt):
        cid = receipt['candidate_id']; suffix = cid.removeprefix('candidate-v1-')
        manifest = json.loads((Path(receipt['archive_path']) / archive.MANIFEST_NAME).read_text())
        record = {'baseline_id': 'current-v2-' + suffix, 'status': 'CURRENT', 'repository': p.REPOSITORY,
            'main': {'commit_sha': manifest['identity']['source']['commit_sha'],
                     'tree_sha': manifest['identity']['source']['tree_sha']},
            'candidate': {'candidate_id': cid, 'identity_sha256': suffix,
                          'bundle_digest': receipt['bundle_digest']},
            'acceptance': {'authority_ref': 'PROMOTE_CURRENT fixture ' + cid,
                           'scope': 'isolated rollover', 'decision': 'USER_ACCEPTED'},
            'promotion_policy': 'EXPLICIT_HUMAN_OWNER_AUTHORIZATION_REQUIRED',
            'promotion': {'issue_159_ref': 'fixture', 'pull_160_ref': 'fixture', 'accepted_report_head': self.main},
            'historical_predecessors': [{'path': 'state/history/bootstrap.json',
                                       'sha256': p.sha(b'{}')}],
            'governed_files': [{'path': 'governed.txt', 'sha256': p.sha((self.repo / 'governed.txt').read_bytes())}]}
        self.current['records'].append(record); self.current['current_id'] = record['baseline_id']
        event_path = 'state/history/bootstrap_' + suffix[:16] + '_promotion_transaction_v1.json'
        event = {'artifact_type': 'integra.open_proposal_promotion_transaction', 'schema_version': '1.0',
            'transaction_id': 'open-proposal-v1-' + suffix,
            'inputs': {'candidate': {k: receipt[k] for k in p.IDENTITY},
                       'proposal_id': 'proposal-' + suffix[:16],
                       'source': copy.deepcopy(manifest['identity']['source']),
                       'authorization': record['acceptance']['authority_ref']},
            'semantics': {'post': 'CURRENT_PROTECTED_PROPOSAL_CONSUMED'},
            'result': {'current_id': record['baseline_id']}}
        self.events[event_path] = event
        (self.repo / event_path).write_bytes(tx.encoded(event))
        return record

    def publish_state(self):
        last, previous = self.current['records'][-1], self.current['records'][-2]
        receipt = next(v for v in self.owner_catalog['artifacts'].values()
                       if v['candidate_id'] == last['candidate']['candidate_id'])
        prior = next(v for v in self.owner_catalog['artifacts'].values()
                     if v['candidate_id'] == previous['candidate']['candidate_id'])
        raw = tx.encoded(self.current); (self.repo / tx.CURRENT).write_bytes(raw)
        self.registry['canonical_current'] = {'path': tx.CURRENT, 'sha256': p.sha(raw),
            'current_id': self.current['current_id'], **{k: receipt[k] for k in p.IDENTITY}}
        self.registry['latest_accepted_candidate_id'] = receipt['candidate_id']
        self.registry['rollback'] = {**{k: prior[k] for k in p.IDENTITY}, 'confirmation_ref': 'fixture-owner'}
        if self.registry['recovery'] is None:
            self.registry['recovery'] = copy.deepcopy(self.registry['rollback'])
        ids = {receipt['candidate_id'], prior['candidate_id'], self.registry['recovery']['candidate_id']}
        ids |= {row['candidate_id'] for row in self.registry['proposed']}
        self.registry['selected_survivors'] = {cid: str(Path(name).relative_to(self.base))
            for name, value in self.owner_catalog['artifacts'].items() if (cid := value['candidate_id']) in ids}
        self.registry['lifecycle_events'] = [{'path': path, 'transaction_id': event['transaction_id']}
                                            for path, event in self.events.items()]
        (self.repo / tx.REGISTRY).write_bytes(tx.encoded(self.registry))
        self.catalog.write_bytes(tx.encoded(self.owner_catalog))

    def refresh(self):
        with r.locked(self.catalog) as catalog: r.refresh_protection(catalog)
        self.owner_catalog = json.loads(self.catalog.read_bytes())

    def audit(self):
        return gate._snapshot(for_deletion=True)[1]


class RealRolloverProof(unittest.TestCase):
    def test_actual_archive_and_resolver_no_governance_gate_stubs(self):
        f = RealRetentionFixture(self)
        for label in ('recovery', 'current'): f.record(f.bootstrap_archive(label))
        f.publish_state(); f.refresh()
        self.assertEqual(f.audit()['authority_state'], 'COMPLETE')
        incoming = archive.create_archive(f.app('incoming-A'), f.archive_root)
        self.assertEqual(archive.verify_archive(Path(incoming['archive_path'])), incoming)
        self.assertEqual(f.audit()['full_copies'], 3)

    def test_real_accepted_promotion_reconciles_roles(self):
        f = RealRetentionFixture(self)
        for label in ('recovery', 'old-rollback', 'current'): f.record(f.bootstrap_archive(label))
        f.publish_state(); f.refresh(); f.init_git()
        receipt, event = f.promote('A', 100)
        resolved = f.audit()
        self.assertEqual(resolved['authority_state'], 'COMPLETE')
        self.assertIn('CURRENT', resolved['protected_identities'][receipt['candidate_id']]['reasons'])
        self.assertEqual(f.current['current_id'], event['result']['current_id'])
        self.assertEqual(set(f.registry['selected_survivors']), set(resolved['protected_identities']))

    def test_primary_three_candidate_cycle_with_real_promotion_and_retirement(self):
        """A/B promote, C admits; no fixture Candidate-specific deletion grant."""
        f = RealRetentionFixture(self)
        receipts = [f.bootstrap_archive('initial-' + str(i)) for i in range(4)]
        for item in receipts: f.record(item)
        for i in range(4): f.bootstrap_archive('pending-' + str(i))
        f.publish_state(); f.refresh(); f.init_git()
        self.assertEqual(f.audit()['full_copies'], 8)
        logs = io.StringIO()
        with contextlib.redirect_stderr(logs):
            a, _ = f.promote('cycle-A', 101)
            self.assertEqual(f.current['records'][-1]['candidate']['candidate_id'], a['candidate_id'])
            before_b = f.audit()['full_copies']
            self.assertLessEqual(before_b, 8)
            b, _ = f.promote('cycle-B', 102)
            self.assertEqual(f.current['records'][-1]['candidate']['candidate_id'], b['candidate_id'])
            before_c = f.audit()['full_copies']
            admitted = r.build_preflight(f.archive_root, 2 * 1024**2)
            with r.reserved_build(f.archive_root, 2 * 1024**2, archive_copy=True):
                self.assertTrue(os.environ.get('INTEGRA_RETENTION_BUILD_LEASE'))
        final = f.audit()
        self.assertEqual(final['authority_state'], 'COMPLETE')
        self.assertEqual(set(f.registry['selected_survivors']), set(final['protected_identities']))
        self.assertLessEqual(final['full_copies'], 7)
        self.assertLessEqual(admitted['full_copies'], 7)
        self.assertTrue(all(Path(item['archive_path']).is_dir() for item in (a, b)))
        catalog = json.loads(f.catalog.read_bytes())
        self.assertTrue(catalog.get('retirements'))
        self.assertTrue(all(row['state'] == 'RETIRED_NOT_AVAILABLE'
                            for row in catalog['retirements'].values()))
        self.assertEqual(f.registry['deletion_authorizations'], {})
        self.assertIn('CLEANUP_COMPLETED', logs.getvalue())
        if os.environ.get('INTEGRA_RETENTION_CYCLE_REPORT'):
            Path(os.environ['INTEGRA_RETENTION_CYCLE_REPORT']).write_text(json.dumps({
                'proof': 'REAL_TINY_PAYLOAD_ARCHIVE_PROMOTION_RETIREMENT_A_B_C',
                'transport_boundary': 'isolated canonical GitHub snapshot fixture',
                'governance_gates_mocked': False, 'initial_copies': 8,
                'copies_before_B': before_b, 'copies_before_C': before_c,
                'final_copies': final['full_copies'], 'retirement_count': len(catalog['retirements']),
                'candidate_specific_deletion_grants': 0, 'real_archives_changed': False,
                'result': 'PASS'}, indent=2))


if __name__ == '__main__': unittest.main()
