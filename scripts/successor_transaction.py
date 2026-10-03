"""Exact Excel #7 successor transaction; no general archive waiver.

Preparation is a proposed Git tree. Only publication on main consumes the
authorization. Product identities and historical receipts are never rewritten.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess

try:
    from scripts import candidate_protection_audit as protection
    from scripts import proposed_baseline_lite as baseline
    from scripts import candidate_archive, candidate_retention
except ModuleNotFoundError:
    import candidate_protection_audit as protection
    import proposed_baseline_lite as baseline
    import candidate_archive
    import candidate_retention

CURRENT = 'state/current_product_baseline_v2.json'
REGISTRY = 'state/candidate_protection_registry_v1.json'
PROPOSAL = 'state/proposed_baseline_lite_v1.json'
EVENT = 'state/history/excel7_successor_transaction_v1.json'
OLD_CURRENT = 'state/history/excel7_outgoing_current_v2.json'
OLD_REGISTRY = 'state/history/excel7_outgoing_protection_registry_v1.json'
RETIRED = 'state/history/excel7_accepted_proposal_lite_v1.json'
ACCEPTED_HEAD = '893eb462c2e7ee13e62ddec23d231fd822b144ed'
MAIN = '5be70ddaa0b641f0b4dfb36b95c81641166ef2eb'
PROPOSAL_ID = 'proposal-process-v1-youtube-playlist'
OUTGOING = {
    'candidate_id': 'candidate-v1-d8bd6fc2649e061d50bfabae37c636d8caeb764965c941cf4fef88ae5fe301a8',
    'bundle_digest': 'fedc5481c20a8829f92fd6f6579e53197b1495bd960c238efe9fdd14c2cb5582',
    'manifest_digest': '48cd6a5fb04677bc8b79d2a8e6212749c51bc931719fbb8923b1cdb8f7e71c56'}
INCOMING = {
    'candidate_id': 'candidate-v1-5f6384c8d68c96cc84432e3c72039ef1cdb0642f6399c6d5df60387774a7ed1e',
    'bundle_digest': '639d66bbbd8d7af55d091f43156d823000496191c771bef28d7fffc6fe88a302',
    'manifest_digest': 'e50edf361bad7226caf3101584ec3dc73119a0254c464ecb424f1ec0a23daacf'}
OLD_ID = 'current-v2-' + OUTGOING['candidate_id'][13:]
NEW_ID = 'current-v2-' + INCOMING['candidate_id'][13:]
OLD_HASH = '47f4023fc7905166c5134f224519d83520f95b06ac68ccd357c02d86035f900e'
PROPOSAL_HASH = 'daf33b1f2ea99c7709a66d1d129bc53edd428b10900b46092b10d7de1bc59e84'
ARCHIVE = 'Build Archive/' + INCOMING['candidate_id'] + '/' + INCOMING['bundle_digest']
AUTHORITY = {
    'acceptance': ('28fe9d832e2b4496f65f92c5b468907bfa04ac21169694e563f99859e508a14f',
                   '11bcd27d98b7b193bb7d879582c465198e99b29e9b02cb1e12c83c7730bca60f'),
    'promotion': ('c8c8b4228b9537b18d32e3afdf9c5f9c95168e50c74854191940dd9fbc9133c7',
                  '899260c472f2b3f2ef3d80270cc6fb3fab5d42c07976b2f0958c3715684eb710'),
    'archive_exception': ('398cf7283ff0a142527715fdda932c459670bc5b92e1575617b2fa2c4209ac5b',
                          'b1d7c75df6a3299a338b7df8097261d234df542a7911752d49d074363438302e')}
BOARD = 'docs/PROCESS_V1_EXCEL_SCOPE_RECONCILIATION.md'
DOD = 'docs/PROCESS_V1_DEFINITION_OF_DONE.md'
ALLOWED_REPAIR = {
    'scripts/candidate_protection_audit.py', 'scripts/candidate_protection_gate.py',
    'scripts/promote_proposed_baseline_lite.py', 'scripts/successor_transaction.py',
    'scripts/validate_governance.py', 'scripts/candidate_retention.py',
    'scripts/proposed_baseline_lite.py',
    'tests/test_successor_transaction.py', 'tests/test_candidate_protection_audit.py',
    'tests/test_candidate_protection_gate.py', 'tests/test_promotion_archive_gate.py',
    'docs/CANDIDATE_RETENTION.md', 'docs/ISSUE_214_PROTECTION_RECOVERY_CONTRACT.md',
    'docs/PROPOSED_BASELINE_LITE_IMPLEMENTATION.md', 'docs/EXCEL7_SUCCESSOR_TRANSACTION.md'}


def encoded(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()


def git_bytes(root: Path, ref: str, path: str) -> bytes:
    run = subprocess.run(['git', 'show', ref + ':' + path], cwd=root,
                         capture_output=True, check=True)
    return run.stdout


def inputs(root: Path) -> dict:
    """Construct only from immutable accepted anchors and exact owner payloads."""
    current = git_bytes(root, MAIN, CURRENT)
    registry = git_bytes(root, MAIN, REGISTRY)
    proposal = git_bytes(root, ACCEPTED_HEAD, PROPOSAL)
    parsed = json.loads(proposal)
    if protection.sha(current) != OLD_HASH or protection.sha(proposal) != PROPOSAL_HASH:
        raise ValueError('accepted CURRENT/Proposal bytes changed')
    authority = {}
    for role, (normalized, original) in AUTHORITY.items():
        path = 'docs/evidence/EXCEL7_AUTHORITY_' + role.upper() + '.txt'
        raw = (root / path).read_bytes()
        if protection.sha(raw) != normalized:
            raise ValueError('authority payload differs: ' + role)
        # Text copies retain the exact original text, with a final LF added.
        if protection.sha(raw.rstrip(b'\n')) != original:
            raise ValueError('original owner instruction hash differs: ' + role)
        authority[role] = {'authority_ref': path, 'payload_sha256': normalized,
                           'original_payload_sha256': original}
    receipts = []
    for gap in json.loads(registry)['historical_gaps']:
        path = gap['receipt_path']
        receipts.append({'path': path, 'sha256': protection.sha(git_bytes(root, MAIN, path))})
    return {'outgoing': {'current_id': OLD_ID, **OUTGOING, 'current_sha256': OLD_HASH},
            'incoming': INCOMING.copy(), 'proposal_id': PROPOSAL_ID,
            'proposal_sha256': PROPOSAL_HASH, 'accepted_head': ACCEPTED_HEAD,
            'canonical_base': MAIN, 'base_main': parsed['base_main'],
            'source': parsed['proposed_source'], 'evidence_head': parsed['proposed_head'],
            'evidence': parsed['evidence'], 'authority': authority,
            'historical_evidence': receipts, 'archive_path': ARCHIVE,
            'archive_inventory_sha256': '98522a8283a26589ccac94eeaa747261f163573fd695ce56d50726803647c443',
            'pre_registry_sha256': protection.sha(registry),
            'intended_successor': NEW_ID}


def package(root: Path, bound: dict) -> dict[str, bytes | None]:
    """Deterministic append-only successor, independent of its future commit SHA."""
    if bound != inputs(root):
        raise ValueError('transaction inputs differ from exact accepted authority')
    original = git_bytes(root, MAIN, CURRENT)
    pre_registry = git_bytes(root, MAIN, REGISTRY)
    retired = git_bytes(root, ACCEPTED_HEAD, PROPOSAL)
    old, registry, proposal = map(json.loads, (original, pre_registry, retired))
    successor = baseline.next_current(old, proposal, proposal['owner_acceptance']['authority_ref'],
                                      previous_current_path=OLD_CURRENT, root=root)
    successor['records'][-1]['historical_predecessors'][0]['sha256'] = protection.sha(original)
    result = encoded(successor)
    registry['rollback'] = {**OUTGOING, 'confirmation_ref': None}
    registry['canonical_current'] = {'path': CURRENT, 'sha256': protection.sha(result),
                                     'current_id': NEW_ID, **INCOMING}
    registry['latest_accepted_candidate_id'] = INCOMING['candidate_id']
    removed = [r for r in registry['proposed'] if r['pr'] == 211]
    if len(removed) != 1:
        raise ValueError('exact stale #211 registry record is unavailable')
    registry['proposed'] = [r for r in registry['proposed'] if r['pr'] != 211]
    registry['selected_survivors'].pop(removed[0]['candidate_id'])
    registry['selected_survivors'][INCOMING['candidate_id']] = ARCHIVE
    txid = 'successor-v1-' + protection.digest(bound)
    registry['successor_transactions'] = [{'path': EVENT, 'transaction_id': txid}]
    board = git_bytes(root, ACCEPTED_HEAD, BOARD).decode()
    old_row = '| 7 | YouTube playlist | MUST | PROCESS | MUST | YouTube playlist | NOT_DONE | Retained with owner-fixed ordered discovery, selection, and independent item failure. |'
    new_row = '| 7 | YouTube playlist | MUST | PROCESS | MUST | YouTube playlist | DONE | Accepted Candidate `' + INCOMING['candidate_id'] + '`; native real-playlist A/C selection, explicit confirmation, ordered sources and exact provenance. |'
    if board.count(old_row) != 1 or board.count('40 DONE + 0 IN_PROGRESS + 4 NOT_DONE + 1 BLOCKED') != 1:
        raise ValueError('Board prestate differs')
    board = board.replace(old_row, new_row).replace('40 DONE + 0 IN_PROGRESS + 4 NOT_DONE + 1 BLOCKED',
                                                  '41 DONE + 0 IN_PROGRESS + 3 NOT_DONE + 1 BLOCKED')
    dod = git_bytes(root, ACCEPTED_HEAD, DOD).decode()
    old_dod = next(line for line in dod.splitlines() if line.startswith('| YouTube playlist |'))
    new_dod = '| YouTube playlist | DONE | S08 and S10 partial; exact owner-accepted Candidate `' + INCOMING['candidate_id'] + '` | Retain real ordered preview, A/C selection and explicit confirmation | Candidate-bound native proof `PROCESS_V1_YOUTUBE_PLAYLIST_E2E.json`; only selected sources enter Process in playlist order. |'
    return {CURRENT: result, REGISTRY: encoded(registry), OLD_CURRENT: original,
            OLD_REGISTRY: pre_registry, RETIRED: retired, PROPOSAL: None,
            BOARD: board.encode(), DOD: dod.replace(old_dod, new_dod).encode()}


def make_event(root: Path) -> dict:
    bound = inputs(root)
    files = package(root, bound)
    return {'artifact_type': 'integra.exact_successor_transaction', 'schema_version': '1.0',
            'transaction_id': 'successor-v1-' + protection.digest(bound), 'inputs': bound,
            'single_use': True, 'consumption': 'CONSUMED_ONLY_WHEN_THIS_TREE_IS_CANONICAL_MAIN',
            'result': {'current_id': NEW_ID, 'files': {
                path: None if data is None else protection.sha(data) for path, data in files.items()}},
            'pin_reconciliation': {
                'before': next(r for r in json.loads(files[OLD_REGISTRY])['proposed'] if r['pr'] == 211),
                'accepted_content_head': ACCEPTED_HEAD, 'candidate': INCOMING,
                'reason': 'accepted #7 Candidate changed after native UI repair and Candidate recovery; final promotion retires the open proposal'},
            'outgoing_archive_availability': 'MISSING_WITH_AVAILABLE_EVIDENCE',
            'outgoing_rollback_eligible': False, 'outgoing_restorable': False}


def validate_event(root: Path, event: dict) -> dict[str, bytes | None]:
    if event != make_event(root):
        raise ValueError('exact successor transaction identity/authority/result differs')
    return package(root, event['inputs'])


def validate_tree(root: Path) -> None:
    event = json.loads((root / EVENT).read_bytes())
    files = validate_event(root, event)
    for path, raw in files.items():
        target = root / path
        if raw is None:
            if target.exists() or target.is_symlink():
                raise ValueError('active Proposal is not retired')
        elif target.is_symlink() or target.read_bytes() != raw:
            raise ValueError('successor package differs: ' + path)
    errors = baseline.validate_current(json.loads(files[CURRENT]), root)
    errors += baseline.verify_promotion_material(json.loads(files[RETIRED]), root, root / PROPOSAL,
                                               acceptance_ref=ACCEPTED_HEAD)
    # Retirement preserves the original declaration path. The material validator
    # must inspect that original path, not require the historical copy to have
    # been created in the Proposal declaration commit.
    if errors:
        raise ValueError('; '.join(errors))


def validate_recorded_successor(root: Path) -> None:
    """Validate this applied event without making it a permanent CURRENT lock.

    Later ordinary promotions must retain its exact CURRENT through the existing
    immutable predecessor chain. They gain no missing-archive permission.
    """
    event = json.loads((root / EVENT).read_bytes())
    files = validate_event(root, event)
    registry = json.loads((root / REGISTRY).read_bytes())
    pointer = {'path': EVENT, 'transaction_id': event['transaction_id']}
    if registry.get('successor_transactions', []).count(pointer) != 1:
        raise ValueError('consumed transaction pointer is missing or differs')
    current = json.loads((root / CURRENT).read_bytes())
    if current['current_id'] == NEW_ID:
        validate_tree(root)
        return
    accepted = json.loads(files[CURRENT])
    if current['records'][:len(accepted['records'])] != accepted['records']:
        raise ValueError('later CURRENT rewrote consumed successor history')
    refs = [ref for r in current['records'][len(accepted['records']):]
            for ref in r.get('historical_predecessors', [])
            if ref.get('sha256') == event['result']['files'][CURRENT]]
    if not refs or any((root / ref['path']).read_bytes() != files[CURRENT] for ref in refs):
        raise ValueError('consumed successor lacks immutable predecessor bytes')
    for path in (OLD_CURRENT, OLD_REGISTRY, RETIRED):
        if (root / path).read_bytes() != files[path]:
            raise ValueError('consumed transaction history changed: ' + path)


def canonical_state(event: dict, current_raw: bytes, event_raw: bytes | None) -> str:
    """A local staged event never proves consumption; callers fetch remote main."""
    if protection.sha(current_raw) == OLD_HASH and event_raw is None:
        return 'NOT_APPLIED'
    if (protection.sha(current_raw) == event['result']['files'][CURRENT]
            and event_raw == encoded(event)):
        return 'ALREADY_APPLIED'
    raise ValueError('authorization already consumed by a different result or CURRENT drift')


def preflight(root: Path, event: dict, expected_head: str, *, require_tree: bool = True) -> str:
    files = validate_event(root, event)
    if require_tree:
        validate_tree(root)
        paths = set(subprocess.check_output(['git', 'diff', '--name-only', ACCEPTED_HEAD, expected_head],
                                           cwd=root, text=True).splitlines())
        allowed = ALLOWED_REPAIR | set(files) | {EVENT} | {
            row['authority_ref'] for row in event['inputs']['authority'].values()}
        if paths - allowed:
            raise ValueError('non-governance delta above accepted content: ' + ','.join(sorted(paths - allowed)))
        for path, raw in {**files, EVENT: encoded(event)}.items():
            if raw is None:
                run = subprocess.run(['git', 'ls-tree', expected_head, '--', ':(literal)' + path],
                                     cwd=root, capture_output=True, check=True)
                if run.stdout:
                    raise ValueError('final PR tree did not retire active Proposal: ' + path)
            elif git_bytes(root, expected_head, path) != raw:
                raise ValueError('final PR tree differs from verified package: ' + path)
    main = protection._api('repos/' + protection.REPOSITORY + '/git/ref/heads/main')['object']['sha']
    remote_current = protection._remote_file(CURRENT, main)[0]
    remote_event = protection._optional_remote_file(EVENT, main)
    state = canonical_state(event, remote_current, remote_event[0] if remote_event else None)
    if state == 'ALREADY_APPLIED':
        for path, raw in files.items():
            remote = protection._optional_remote_file(path, main)
            if (None if remote is None else remote[0]) != raw:
                raise ValueError('canonical consumed package differs: ' + path)
        base = Path.home() / 'Library/Application Support/Integra'
        receipt = candidate_archive.verify_archive(base / ARCHIVE, INCOMING)
        if receipt['inventory_sha256'] != event['inputs']['archive_inventory_sha256']:
            raise ValueError('consumed incoming archive inventory differs')
        return state
    if main != MAIN:
        raise ValueError('canonical main/base changed before promotion')
    if protection._remote_file(REGISTRY, main)[0] != files[OLD_REGISTRY]:
        raise ValueError('canonical protection prestate bytes changed')
    pr = protection._api('repos/' + protection.REPOSITORY + '/pulls/211')
    if pr.get('state') != 'open' or pr['head']['sha'] != expected_head or pr['base']['sha'] != MAIN:
        raise ValueError('PR #211 head/base/state differs from external preflight')
    registry = json.loads(files[OLD_REGISTRY])
    # The exact prior pin is reconciled by the owner-bound event. It is not an
    # arbitrary alternative registry and cannot authorize deletion.
    for row in registry['proposed']:
        if row['pr'] == 211:
            row.update(head_sha=expected_head, **INCOMING)
    prior = event['pin_reconciliation']['before']['candidate_id']
    registry['selected_survivors'].pop(prior)
    registry['selected_survivors'][INCOMING['candidate_id']] = ARCHIVE
    current, proposals, canonical = protection.fetch_canonical(registry)
    if canonical['main_sha'] != MAIN or current != json.loads(files[OLD_CURRENT]):
        raise ValueError('canonical prestate differs')
    if 211 not in proposals:
        # A verified successor HEAD retires the active file. Resolve the exact
        # accepted proposal at its immutable acceptance commit instead.
        raw, proposal = protection._remote_file(PROPOSAL, ACCEPTED_HEAD)
        if protection.sha(raw) != PROPOSAL_HASH:
            raise ValueError('accepted Proposal changed')
        proposals[211] = proposal
    elif protection.sha(encoded(proposals[211])) != protection.sha(encoded(json.loads(files[RETIRED]))):
        raise ValueError('PR Proposal differs from accepted content')
    base = Path.home() / 'Library/Application Support/Integra'
    packages = protection.scan_local(registry, base)
    import shutil
    audit = protection.resolve(registry, current, proposals, packages,
                               free_bytes=shutil.disk_usage(base).free, canonical=canonical)
    if audit['authority_state'] != 'COMPLETE' or audit['promotion_blockers'] != ['OUTGOING_CURRENT_EXACT_ARCHIVE_MISSING']:
        raise ValueError('unexpected pre-promotion protection blockers: ' + str(audit['promotion_blockers']))
    try:
        from scripts.candidate_protection_gate import _selected_verified
    except ModuleNotFoundError:
        from candidate_protection_gate import _selected_verified
    _selected_verified(registry, audit, INCOMING, base / ARCHIVE)
    receipt = candidate_archive.verify_archive(base / ARCHIVE, INCOMING)
    if receipt['inventory_sha256'] != event['inputs']['archive_inventory_sha256']:
        raise ValueError('incoming retained inventory changed')
    return 'NOT_APPLIED'


def require_exact_promotion(root: Path, event: dict, proposal: dict, current: dict,
                            archive: Path, expected_head: str) -> None:
    """Bound preparation path; no arbitrary alternate registry/exception flag."""
    files = validate_event(root, event)
    if (current != json.loads(files[OLD_CURRENT]) or proposal != json.loads(files[RETIRED])
            or archive.resolve() != (Path.home() / 'Library/Application Support/Integra' / ARCHIVE).resolve()):
        raise ValueError('operation inputs differ from exact authorized transaction')
    errors = (baseline.validate_current(current, root, proposal)
              + baseline.validate_proposal(proposal, current, root)
              + baseline.verify_promotion_material(proposal, root, root / PROPOSAL))
    if errors:
        raise ValueError('; '.join(errors))
    preflight(root, event, expected_head, require_tree=False)


def merge(root: Path, expected_head: str) -> str:
    """Hold the existing managed-retention lock through remote application.

    Unknown merge outcomes are never retried without reading canonical main.
    Post-check failure does not unconsume an applied authorization.
    """
    event = json.loads((root / EVENT).read_bytes())
    archive_root = Path.home() / 'Library/Application Support/Integra/Build Archive'
    with candidate_retention.locked(candidate_retention.catalog_path(archive_root)):
        state = preflight(root, event, expected_head)
        if state == 'ALREADY_APPLIED':
            return state
        pr = protection._api('repos/' + protection.REPOSITORY + '/pulls/211')
        if pr.get('mergeable') is not True or pr.get('mergeable_state') != 'clean':
            raise ValueError('final PR is not clean/mergeable')
        checks = protection._api('repos/' + protection.REPOSITORY + '/commits/' + expected_head + '/check-runs')
        gates = [c for c in checks['check_runs'] if c.get('name') == 'governance']
        if not gates or any(c.get('status') != 'completed' or c.get('conclusion') != 'success' for c in gates):
            raise ValueError('final GitHub Quality Gate is not successful')
        # Rehash after network checks, immediately before the guarded merge.
        final_receipt = candidate_archive.verify_archive(archive_root.parent / ARCHIVE, INCOMING)
        if final_receipt['inventory_sha256'] != event['inputs']['archive_inventory_sha256']:
            raise ValueError('incoming inventory changed immediately before application')
        # GitHub's PR merge endpoint pins head but provides no expected-base CAS.
        # A two-parent merge commit followed by a normal, non-force push applies
        # the established merge-commit method and atomically rejects a concurrent
        # divergent main. It never overwrites a moved branch or changes rulesets.
        fresh_pr = protection._api('repos/' + protection.REPOSITORY + '/pulls/211')
        fresh_main = protection._api('repos/' + protection.REPOSITORY + '/git/ref/heads/main')['object']['sha']
        if fresh_main != MAIN or fresh_pr['head']['sha'] != expected_head or fresh_pr['base']['sha'] != MAIN:
            raise ValueError('main or PR head changed immediately before merge')
        tree = subprocess.check_output(['git', 'rev-parse', expected_head + '^{tree}'], cwd=root, text=True).strip()
        merge_sha = subprocess.check_output(['git', 'commit-tree', tree, '-p', MAIN, '-p', expected_head,
             '-m', 'Merge pull request #211 from Yurielo/codex/excel-07-youtube-playlist-final-proposal\n\nApply exact owner-authorized YouTube playlist successor'],
             cwd=root, text=True).strip()
        command_error = ''
        try:
            run = subprocess.run(['git', 'push', 'origin', merge_sha + ':refs/heads/main'],
                                 cwd=root, capture_output=True, text=True, timeout=60)
            command_error = run.stderr.strip()
        except (OSError, subprocess.TimeoutExpired, KeyboardInterrupt) as error:
            command_error = str(error)
        # Always determine canonical outcome, even when gh returned an error.
        state = preflight(root, event, expected_head)
        if state != 'ALREADY_APPLIED':
            raise ValueError('merge not canonically applied; remote verified; ' + command_error)
        merged_pr = protection._api('repos/' + protection.REPOSITORY + '/pulls/211')
        if not merged_pr.get('merged_at') or merged_pr['head']['sha'] != expected_head:
            raise ValueError('canonical successor applied but PR merge correspondence is unconfirmed')
        return state
