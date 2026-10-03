#!/usr/bin/env python3
"""Read-only canonical Candidate protection resolver and recovery-gap report.

This module never performs cleanup, adoption, archive publication or promotion.
The proposed registry is not activation authority until a separate owner gate.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

try:
    from scripts import candidate_archive
except ModuleNotFoundError:
    import candidate_archive
verify_archive = candidate_archive.verify_archive

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / 'state/candidate_protection_registry_v1.json'
REPOSITORY = 'Yurielo/integra'
IDENTITY = ('candidate_id', 'bundle_digest', 'manifest_digest')
CID = re.compile(r'^candidate-v1-[0-9a-f]{64}$')
HASH = re.compile(r'^[0-9a-f]{64}$')
TERMINAL = {'COMPLETED', 'REJECTED', 'SUPERSEDED', 'UNUSED'}
ROOT_NAMES = {'Build Archive', 'Recovery Archive', 'Build Archive Recovery',
              'Candidate Builds', 'Validation'}
ACCEPTED_GAP_DECISION_SHA256 = 'c0fbc7699ae3caa6ea56a59987410977515881043f2ce2fd9b4f39382cc132f8'
INTEGRATION_REF = 'https://github.com/Yurielo/integra/pull/215'
HISTORICAL_RECEIPTS = {
    'CURRENT': 'docs/evidence/PROCESS_V1_ZOOM_FOLDER_CANDIDATE_ARCHIVE.json',
    'ROLLBACK': 'docs/evidence/PROCESS_V1_FOLDER_DISCOVERY_CANDIDATE_ARCHIVE.json'}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest(value: object) -> str:
    return sha(json.dumps(value, sort_keys=True, separators=(',', ':')).encode())


def verify_exact_recovery_source(app: Path, historical_receipt: dict,
                                 evidence: list[Path] | None = None) -> dict:
    """Read-only full-byte preflight against the *historical* archive receipt.

    A matching Candidate ID and tree digest alone omit bytes such as pyc files.
    The historical package inventory digest binds every retained file and mode.
    """
    app = candidate_archive._path(app)
    identity = candidate_archive._identity(app)
    candidate_archive._expect(identity, {k: historical_receipt[k] for k in IDENTITY})
    manifest = app / candidate_archive.EMBEDDED
    planned = [candidate_archive._entry(app, candidate_archive.APP)] + [
        {**item, 'path': candidate_archive.APP + '/' + item['path']}
        for item in candidate_archive._inventory(app)]
    planned.append(candidate_archive._entry(manifest, candidate_archive.MANIFEST_NAME))
    if evidence:
        planned.append({'path': 'evidence', 'type': 'directory', 'mode': 0o700})
    for index, path in enumerate(evidence or []):
        planned.append(candidate_archive._entry(candidate_archive._path(path),
                       f'evidence/{index:04d}-{Path(path).name}'))
    planned.sort(key=lambda item: item['path'])
    inventory_digest = sha(candidate_archive.canonical_bytes(planned) + b'\n')
    computed = candidate_archive._receipt(identity, planned, inventory_digest)
    if any(computed.get(k) != historical_receipt.get(k) for k in
           ('inventory_sha256', 'file_count', 'app_size_bytes', 'retained_size_bytes')):
        raise ValueError('source full-byte inventory differs from historical receipt')
    return {**computed, 'source_verification': 'EXACT_HISTORICAL_SOURCE_VERIFIED'}


def bootstrap_plan(registry: dict, audit: dict) -> dict:
    """Machine-readable migration plan; never claims recovered bytes or writes state."""
    gaps = [gap for gap in registry.get('historical_gaps', [])
            if gap.get('observed_state') == 'MISSING_WITH_AVAILABLE_EVIDENCE']
    limits = registry['limits']
    copies = audit.get('full_copies')
    archive_bytes = audit.get('archive_bytes')
    free_bytes = audit.get('free_bytes')
    capacity_known = all(isinstance(value, int) for value in (copies, archive_bytes, free_bytes))
    capacity_available = (capacity_known and copies < limits['max_full_copies']
                          and archive_bytes < limits['max_attributed_bytes']
                          and free_bytes > limits['minimum_free_after_reservations'])
    return {'artifact_type': 'integra.protection_bootstrap_plan',
            'status': 'ACCEPTED_HISTORICAL_GAP_NO_RECOVERY' if gaps and audit.get('decision_authority_verified') else
                      'BLOCKED_REQUIRES_PRODUCT_OWNER_RECOVERY_GAP_DECISION' if gaps else 'NO_HISTORICAL_GAP',
            'historical_gaps': gaps, 'unknown_bytes': audit.get('unknown_bytes'),
            'unknown_copies': sum(row.get('classification') == 'UNKNOWN' for row in audit.get('entries', [])),
            'archive_copies': copies, 'archive_bytes': archive_bytes,
            'remaining_copy_slots': max(0, limits['max_full_copies'] - copies) if capacity_known else None,
            'remaining_archive_bytes': max(0, limits['max_attributed_bytes'] - archive_bytes) if capacity_known else None,
            'free_bytes': free_bytes, 'capacity_available_for_preflight': capacity_available,
            'exact_source_verified': False, 'can_create_recovery_now': False,
            'current_unchanged': True, 'historical_receipts_unchanged': True,
            'deletion_enabled': False, 'promotion_authorized': False,
            'bootstrap_authorization_ref': registry.get('bootstrap_authorization_ref')}


def _api(endpoint: str) -> object:
    run = subprocess.run(['gh', 'api', endpoint], capture_output=True, text=True, timeout=30)
    if run.returncode:
        raise ValueError('canonical GitHub read failed: ' + endpoint)
    return json.loads(run.stdout)


def _optional_remote_file(path: str, ref: str) -> tuple[bytes, dict] | None:
    endpoint = f'repos/{REPOSITORY}/contents/{path}?ref={ref}'
    run = subprocess.run(['gh', 'api', endpoint], capture_output=True, text=True, timeout=30)
    if run.returncode:
        if 'HTTP 404' in run.stderr:
            return None
        raise ValueError('canonical GitHub read failed: ' + endpoint)
    value = json.loads(run.stdout)
    if not isinstance(value, dict) or value.get('type') != 'file' or value.get('encoding') != 'base64':
        raise ValueError('canonical proposal file response is invalid')
    data = base64.b64decode(''.join(value['content'].split()), validate=True)
    return data, json.loads(data)


def _remote_file(path: str, ref: str) -> tuple[bytes, dict]:
    value = _api(f'repos/{REPOSITORY}/contents/{path}?ref={ref}')
    if not isinstance(value, dict) or value.get('type') != 'file' or value.get('encoding') != 'base64':
        raise ValueError('canonical GitHub file response is invalid')
    data = base64.b64decode(value['content'], validate=False)
    return data, json.loads(data)


def fetch_canonical(registry: dict) -> tuple[dict, dict[int, dict], dict]:
    """Pin exact main and proposal heads, then detect drift before returning."""
    main = _api(f'repos/{REPOSITORY}/git/ref/heads/main')['object']['sha']
    current_bytes, current = _remote_file(registry['canonical_current']['path'], main)
    if sha(current_bytes) != registry['canonical_current']['sha256']:
        raise ValueError('canonical CURRENT bytes differ from registry binding')
    decision_ref = registry.get('decision_authority_ref', '')
    match = re.fullmatch(r'https://github\.com/Yurielo/integra/issues/214#issuecomment-([0-9]+)', decision_ref)
    if not match:
        raise ValueError('Product Owner decision reference is invalid')
    decision_authority = _api(f'repos/{REPOSITORY}/issues/comments/{match.group(1)}')
    decision_token_lines = re.findall(r'^PRODUCT_OWNER_AUTHORIZATION:.*$', decision_authority.get('body', ''), re.MULTILINE)
    if (registry.get('decision_authority_ref') != decision_authority.get('html_url')
            or decision_authority.get('user', {}).get('login', '').lower() != 'yurielo'
            or len(decision_token_lines) != 1
            or sha(decision_token_lines[0].encode()) != registry.get('decision_token_sha256')):
        raise ValueError('Product Owner Issue #214 decision binding differs')
    historical_receipts = {}
    for gap in registry.get('historical_gaps', []):
        data, receipt = _remote_file(gap['receipt_path'], main)
        historical_receipts[gap['candidate_id']] = {
            'record': receipt, 'sha256': sha(data), 'path': gap['receipt_path']}
    proposals = {}
    captured_heads = {}
    page = 1
    while True:
        pull_page = _api(f'repos/{REPOSITORY}/pulls?state=open&per_page=100&page={page}')
        if not isinstance(pull_page, list):
            raise ValueError('open PR enumeration failed')
        for pr in pull_page:
            number, head = pr['number'], pr['head']['sha']
            captured_heads[number] = head
            result = _optional_remote_file('state/proposed_baseline_lite_v1.json', head)
            if result is not None:
                proposals[number] = result[1]
        if len(pull_page) < 100:
            break
        page += 1
    for reference in registry['proposed']:
        if captured_heads.get(reference['pr']) != reference['head_sha']:
            raise ValueError(f'proposal PR #{reference["pr"]} is closed or has changed head')
    accepted_unpromoted = {}
    for reference in registry.get('accepted_unpromoted', []):
        required = {'pr', 'head_sha', *IDENTITY, 'authority_ref', 'authorization_sha256', 'status'}
        if set(reference) != required or reference['status'] != 'ACCEPTED_UNPROMOTED_PROTECTED':
            raise ValueError('accepted-unpromoted registry record is invalid')
        match = re.fullmatch(r'https://github\.com/Yurielo/integra/issues/214#issuecomment-([0-9]+)', reference['authority_ref'])
        if not match:
            raise ValueError('accepted-unpromoted authority reference is invalid')
        authority = _api(f'repos/{REPOSITORY}/issues/comments/{match.group(1)}')
        lines = re.findall(r'^PRODUCT_OWNER_AUTHORIZATION:.*$', authority.get('body', ''), re.MULTILINE)
        if (authority.get('html_url') != reference['authority_ref']
                or authority.get('user', {}).get('login', '').lower() != 'yurielo'
                or len(lines) != 1 or sha(lines[0].encode()) != reference['authorization_sha256']
                or f'CANDIDATE_ID={reference["candidate_id"]}' not in lines[0]
                or 'FROM=OPEN_PROPOSAL_PR_213 TO=ACCEPTED_UNPROMOTED_PROTECTED' not in lines[0]
                or 'MERGE_PR_213=AUTHORIZED' not in lines[0]
                or 'PROMOTION=FORBIDDEN' not in lines[0] or 'CURRENT_CHANGE=FORBIDDEN' not in lines[0]
                or 'DELETION_AUTHORIZATIONS={}' not in lines[0] or 'UNKNOWN=RETAIN_FAIL_CLOSED' not in lines[0]):
            raise ValueError('accepted-unpromoted Product Owner authorization differs')
        pr = _api(f'repos/{REPOSITORY}/pulls/{reference["pr"]}')
        if (pr.get('state') != 'closed' or not pr.get('merged_at')
                or pr.get('head', {}).get('sha') != reference['head_sha']):
            raise ValueError('accepted-unpromoted PR is not the exact merged PR head')
        proposal = _remote_file('state/proposed_baseline_lite_v1.json', reference['head_sha'])[1]
        if (proposal.get('artifact_type') != 'integra.proposed_product_baseline'
                or any(proposal.get('candidate', {}).get(k) != reference[k] for k in IDENTITY)
                or proposal.get('owner_acceptance', {}).get('decision') != 'PILOT_ACCEPTED'
                or proposal.get('owner_acceptance', {}).get('promotion_authorized') is not False):
            raise ValueError('accepted-unpromoted proposal binding differs')
        accepted_unpromoted[reference['pr']] = proposal
    closing_heads = {}
    page = 1
    while True:
        pull_page = _api(f'repos/{REPOSITORY}/pulls?state=open&per_page=100&page={page}')
        if not isinstance(pull_page, list):
            raise ValueError('open PR re-enumeration failed')
        closing_heads.update({pr['number']: pr['head']['sha'] for pr in pull_page})
        if len(pull_page) < 100:
            break
        page += 1
    if closing_heads != captured_heads:
        raise ValueError('open PR set or head changed during protection capture')
    if _api(f'repos/{REPOSITORY}/git/ref/heads/main')['object']['sha'] != main:
        raise ValueError('canonical main moved during protection capture')
    return current, proposals, {'main_sha': main, 'current_sha256': sha(current_bytes),
                                 'decision_authority_ref': decision_authority['html_url'],
                                 'decision_token_sha256': sha(decision_token_lines[0].encode()),
                                 'decision_token': decision_token_lines[0],
                                 'historical_receipts': historical_receipts,
                                 'proposal_heads': {str(n): captured_heads[n] for n in proposals},
                                 'accepted_unpromoted': accepted_unpromoted}


def _identity(value: dict) -> dict:
    result = {key: value.get(key) for key in IDENTITY if key in value}
    if (not isinstance(result.get('candidate_id'), str)
            or not CID.fullmatch(result['candidate_id'])
            or not isinstance(result.get('bundle_digest'), str)
            or not HASH.fullmatch(result['bundle_digest'])
            or ('manifest_digest' in result and
                (not isinstance(result['manifest_digest'], str) or not HASH.fullmatch(result['manifest_digest'])))):
        raise ValueError('invalid Candidate identity tuple')
    return result


def _add(protected: dict, identity: dict, reason: str, blockers: list[str]) -> None:
    identity = _identity(identity)
    cid = identity['candidate_id']
    previous = protected.get(cid)
    if previous and any(previous['identity'].get(k) != value for k, value in identity.items()
                        if k in previous['identity']):
        blockers.append('CONFLICTING_PROTECTED_IDENTITY:' + cid)
    if previous:
        previous['reasons'].append(reason)
        previous['identity'].update(identity)
    else:
        protected[cid] = {'identity': identity, 'reasons': [reason]}


def _accepted_historical_gaps(registry: dict, canonical: dict | None,
                              blockers: list[str]) -> set[str]:
    """Recognize only the exact Issue #214 owner decision, never inferred loss."""
    token = (canonical or {}).get('decision_token', '')
    current_id = registry.get('canonical_current', {}).get('candidate_id')
    rollback_id = registry.get('rollback', {}).get('candidate_id')
    expected = {'CURRENT': current_id, 'ROLLBACK': rollback_id}
    gaps = registry.get('historical_gaps')
    if gaps == []:
        if registry.get('decision_token_sha256') == ACCEPTED_GAP_DECISION_SHA256:
            blockers.append('HISTORICAL_GAP_DECISION_CONFLICT')
        return set()
    if (registry.get('decision_token_sha256') != ACCEPTED_GAP_DECISION_SHA256
            or (canonical or {}).get('decision_token_sha256') != ACCEPTED_GAP_DECISION_SHA256
            or not isinstance(gaps, list) or len(gaps) != 2
            or {g.get('role'): g.get('candidate_id') for g in gaps if isinstance(g, dict)} != expected
            or any(g.get('observed_state') != 'MISSING_WITH_AVAILABLE_EVIDENCE'
                   or set(g) != {'role', 'candidate_id', 'receipt_path', 'observed_state'}
                   or g.get('receipt_path') != HISTORICAL_RECEIPTS.get(g.get('role'))
                   for g in gaps if isinstance(g, dict))
            or any(f'{role}_RECOVERY_GAP={cid}:MISSING_WITH_AVAILABLE_EVIDENCE' not in token
                   for role, cid in expected.items())
            or 'UNKNOWN=RETAIN_FAIL_CLOSED' not in token
            or 'CANONICAL_PROTECTION_AUTHORITY=state/candidate_protection_registry_v1.json' not in token
            or registry.get('unknown_historical') != 'RETAIN_FAIL_CLOSED'):
        blockers.append('HISTORICAL_GAP_DECISION_CONFLICT')
        return set()
    return {current_id, rollback_id}


def _validate_registry(registry: dict, current: dict, proposals: dict[int, dict],
                       blockers: list[str], accepted_gaps: set[str] | None = None,
                       canonical: dict | None = None) -> dict:
    accepted_gaps = accepted_gaps or set()
    if registry.get('artifact_type') != 'integra.candidate_protection_registry' or registry.get('schema_version') != '1.0':
        raise ValueError('protection registry schema is invalid')
    if set(registry.get('managed_roots', [])) != ROOT_NAMES or len(registry['managed_roots']) != len(ROOT_NAMES):
        blockers.append('MANAGED_ROOT_ENUMERATION_INCOMPLETE')
    if type(registry.get('deletion_enabled')) is not bool:
        blockers.append('DELETION_STATE_INVALID')
    if registry.get('decision_token_sha256') == ACCEPTED_GAP_DECISION_SHA256:
        if registry.get('explicit_governance_pins') != {}:
            blockers.append('OWNER_AUTHORIZED_PINS_DIFFER')
        if registry.get('deletion_authorizations') != {}:
            blockers.append('OWNER_AUTHORIZED_DELETION_GRANTS_DIFFER')
        if registry.get('deletion_enabled') is not False:
            blockers.append('OWNER_AUTHORIZED_DELETION_DISABLED')
    if (registry.get('status') != 'PRODUCT_OWNER_AUTHORIZED_ACTIVE'
            or registry.get('activation_authority_ref') != registry.get('decision_authority_ref')):
        blockers.append('REGISTRY_NOT_OWNER_ACTIVATED')
    if registry.get('promotion_contract_integration_ref') != INTEGRATION_REF:
        blockers.append('PROMOTION_CONTRACT_INTEGRATION_MISSING')
    records = current['records']
    active = [item for item in records if item['baseline_id'] == current['current_id']]
    if len(active) != 1 or active[0] != records[-1] or len(records) < 2:
        blockers.append('CANONICAL_CURRENT_AMBIGUOUS')
        return {}
    latest = active[0]['candidate']
    registered = registry['canonical_current']
    if (registered['current_id'] != current['current_id']
            or any(registered[k] != latest[k] for k in ('candidate_id', 'bundle_digest'))):
        blockers.append('CURRENT_REGISTRY_CONFLICT')
    if registry['latest_accepted_candidate_id'] != latest['candidate_id']:
        blockers.append('LATEST_ACCEPTED_REGISTRY_CONFLICT')
    protected = {}
    _add(protected, {k: registered[k] for k in IDENTITY}, 'CURRENT', blockers)
    _add(protected, latest, 'LATEST_ACCEPTED_BASELINE', blockers)
    rollback = registry.get('rollback')
    previous = records[-2]['candidate']
    if not isinstance(rollback, dict) or any(rollback.get(k) != previous.get(k)
                                             for k in ('candidate_id', 'bundle_digest')):
        blockers.append('ROLLBACK_REGISTRY_CONFLICT')
    else:
        if (rollback['candidate_id'] in accepted_gaps
                and (rollback.get('confirmation_ref') is not None
                     or set(rollback) != {*IDENTITY, 'confirmation_ref'})):
            blockers.append('HISTORICAL_ROLLBACK_FALSE_RECOVERY_CLAIM')
        _add(protected, rollback,
             'ACCEPTED_HISTORICAL_ROLLBACK_GAP' if rollback['candidate_id'] in accepted_gaps
             else 'CONFIRMED_ROLLBACK', blockers)
        if not rollback.get('confirmation_ref') and rollback['candidate_id'] not in accepted_gaps:
            blockers.append('ROLLBACK_CONFIRMATION_MISSING')
    recovery = registry.get('recovery')
    if recovery is None:
        selection = registry.get('recovery_selection')
        if (registered['candidate_id'] not in accepted_gaps
                or not isinstance(selection, dict)
                or set(selection) != {'state', 'candidate_id', 'decision_ref', 'archive_path'}
                or selection.get('state') != 'NO_VERIFIED_ARCHIVE_ACCEPTED_HISTORICAL_GAP'
                or selection.get('candidate_id') != registered['candidate_id']
                or selection.get('decision_ref') != registry.get('decision_authority_ref')
                or selection.get('archive_path') is not None):
            blockers.append('RECOVERY_SELECTION_MISSING')
    else:
        if registry.get('recovery_selection') is not None:
            blockers.append('CONFLICTING_RECOVERY_SELECTION')
        _add(protected, recovery, 'CONFIRMED_RECOVERY', blockers)
        if not recovery.get('confirmation_ref'):
            blockers.append('RECOVERY_CONFIRMATION_MISSING')
    declared = {item['pr']: item for item in registry.get('proposed', [])}
    if len(declared) != len(registry.get('proposed', [])) or set(declared) != set(proposals):
        blockers.append('PROPOSAL_SET_CONFLICT')
    for number, proposal in proposals.items():
        reference = declared.get(number)
        if proposal.get('artifact_type') != 'integra.proposed_product_baseline':
            blockers.append('PROPOSAL_IDENTITY_CONFLICT:' + str(number))
            continue
        _add(protected, proposal['candidate'], 'OPEN_PROPOSAL', blockers)
        if not reference:
            blockers.append('UNREGISTERED_OPEN_PROPOSAL:' + str(number))
        elif any(reference.get(k) != proposal.get('candidate', {}).get(k) for k in IDENTITY):
            blockers.append('PROPOSAL_IDENTITY_CONFLICT:' + str(number))
    accepted = (canonical or {}).get('accepted_unpromoted', {})
    declared_accepted = {item['pr']: item for item in registry.get('accepted_unpromoted', [])}
    if len(declared_accepted) != len(registry.get('accepted_unpromoted', [])) or set(declared_accepted) != set(accepted):
        blockers.append('ACCEPTED_UNPROMOTED_SET_CONFLICT')
    for number, proposal in accepted.items():
        reference = declared_accepted.get(number)
        if not reference or any(reference.get(k) != proposal.get('candidate', {}).get(k) for k in IDENTITY):
            blockers.append('ACCEPTED_UNPROMOTED_IDENTITY_CONFLICT:' + str(number))
            continue
        _add(protected, proposal['candidate'], 'ACCEPTED_UNPROMOTED', blockers)
    pins = registry.get('explicit_governance_pins')
    if pins is None:
        blockers.append('EXPLICIT_PIN_ENUMERATION_MISSING')
    elif not isinstance(pins, dict):
        blockers.append('EXPLICIT_PIN_REGISTRY_INVALID')
    else:
        for cid, pin in pins.items():
            if not isinstance(pin, dict) or pin.get('candidate_id') != cid or not pin.get('authority_ref'):
                blockers.append('EXPLICIT_PIN_INVALID:' + str(cid))
            else:
                _add(protected, pin, 'EXPLICIT_GOVERNANCE_PROVENANCE', blockers)
    authorizations = registry.get('deletion_authorizations')
    if not isinstance(authorizations, dict):
        blockers.append('DELETION_AUTHORIZATION_ENUMERATION_MISSING')
    else:
        for path, authorization in authorizations.items():
            if (not isinstance(path, str) or not isinstance(authorization, dict)
                    or authorization.get('path') != path
                    or not authorization.get('authority_ref')):
                blockers.append('INVALID_DELETION_AUTHORIZATION:' + str(path))
    return protected


def resolve(registry: dict, current: dict, proposals: dict[int, dict], packages: list[dict],
            *, free_bytes: int, verifier=verify_archive, canonical: dict | None = None,
            for_deletion: bool = False) -> dict:
    """Classify only from exact authority and evidence; never mutate a package."""
    blockers: list[str] = []
    if canonical is None or canonical.get('current_sha256') != registry['canonical_current']['sha256']:
        blockers.append('CANONICAL_CURRENT_BYTES_UNVERIFIED')
    decision_verified = bool(canonical and canonical.get('decision_authority_ref') == registry.get('decision_authority_ref')
                             and canonical.get('decision_token_sha256') == registry.get('decision_token_sha256'))
    if not decision_verified:
        blockers.append('PRODUCT_OWNER_DECISION_UNVERIFIED')
    token = (canonical or {}).get('decision_token', '')
    for field, key in (('EXPLICIT_GOVERNANCE_PINS', 'explicit_governance_pins'),
                       ('DELETION_AUTHORIZATIONS', 'deletion_authorizations')):
        declared = re.search(r'(?:^| )' + field + r'=(\{\}|sha256:[0-9a-f]{64})(?: |$)', token)
        value = registry.get(key)
        if not declared or (declared.group(1) == '{}' and value != {}) or (
                declared.group(1).startswith('sha256:') and
                (not isinstance(value, dict) or digest(value) != declared.group(1)[7:])):
            blockers.append('OWNER_' + field + '_BINDING_MISSING_OR_CONFLICT')
    deletion_state = re.search(r'(?:^| )DELETION_ENABLED=(true|false)(?: |$)', token)
    # The accepted #214 token explicitly denies grants. It predates the
    # DELETION_ENABLED field; only its false state is valid under that token.
    if deletion_state is None:
        if registry.get('deletion_enabled') is not False:
            blockers.append('OWNER_DELETION_STATE_UNAUTHORIZED')
    elif (deletion_state.group(1) == 'true') != registry.get('deletion_enabled'):
        blockers.append('OWNER_DELETION_STATE_CONFLICT')
    accepted_gaps = _accepted_historical_gaps(registry, canonical, blockers)
    protected = _validate_registry(registry, current, proposals, blockers, accepted_gaps, canonical)
    historical = (canonical or {}).get('historical_receipts', {})
    for gap in registry.get('historical_gaps', []):
        cid = gap['candidate_id']
        receipt = historical.get(cid, {}).get('record')
        identity = protected.get(cid, {}).get('identity', {})
        if (not isinstance(receipt, dict) or historical[cid].get('path') != gap['receipt_path']
                or any(receipt.get(key) != identity.get(key) for key in IDENTITY)
                or not HASH.fullmatch(str(receipt.get('inventory_sha256', '')))):
            blockers.append('HISTORICAL_RECEIPT_CONFLICT:' + cid)
    selected = registry.get('selected_survivors', {})
    if not isinstance(selected, dict) or set(selected) != set(protected):
        blockers.append('SELECTED_SURVIVOR_SET_INCOMPLETE')
        selected = selected if isinstance(selected, dict) else {}
    rows = []
    known_paths = {item['path'] for item in packages}
    verified = set()
    verified_paths = set()
    for cid, role in protected.items():
        path = selected.get(cid)
        if path is None:
            # A null selector is an explicit statement that no verified
            # archive is claimed. The exact historical gap is protected by
            # identity; other open proposals are protected even when no
            # archive has been published. A specific promotion still requires
            # a byte-verified selected Candidate in its own operation gate.
            continue
        if not isinstance(path, str) or not path:
            blockers.append('INVALID_SELECTED_SURVIVOR:' + cid)
            continue
        if cid in accepted_gaps:
            blockers.append('HISTORICAL_GAP_FALSE_RECOVERY_CLAIM:' + cid)
            continue
        if path not in known_paths:
            blockers.append('MISSING_PROTECTED_ARCHIVE:' + cid)
            continue
        package = next(item for item in packages if item['path'] == path)
        if any(package.get(k) != v for k, v in role['identity'].items()):
            blockers.append('PROTECTED_ARCHIVE_IDENTITY_CONFLICT:' + cid)
            continue
        try:
            receipt = verifier(Path(package['absolute_path']), role['identity'])
            if any(receipt.get(k) != v for k, v in role['identity'].items()):
                raise ValueError('verified receipt identity differs')
            if cid in historical and receipt.get('inventory_sha256') != historical[cid]['record']['inventory_sha256']:
                raise ValueError('verified bytes differ from historical inventory')
        except (OSError, ValueError, KeyError, TypeError) as error:
            blockers.append('PROTECTED_ARCHIVE_INTEGRITY_FAIL:' + cid + ':' + str(error))
            continue
        verified.add(cid)
        verified_paths.add(path)
    for item in packages:
        cid = item.get('candidate_id')
        role = protected.get(cid)
        if role and all(item.get(k) == v for k, v in role['identity'].items()):
            classification = 'PROTECTED'
            reasons = role['reasons']
        else:
            classification = 'UNKNOWN'
            reasons = ['UNPROVEN_HISTORICAL_OR_FOREIGN']
            if role:
                blockers.append('PROTECTED_CANDIDATE_CONFLICTING_COPY:' + cid)
        rows.append({**item, 'classification': classification, 'reasons': reasons,
                     'verified_protected_archive': item['path'] in verified_paths})
    if len(known_paths) != len(packages):
        blockers.append('DUPLICATE_PACKAGE_PATH')
    if any(not isinstance(item.get('allocated_bytes'), int) or item['allocated_bytes'] < 0 for item in rows):
        blockers.append('UNKNOWN_ALLOCATION')
    total = sum(item.get('allocated_bytes', 0) for item in rows)
    limits = registry['limits']
    if not for_deletion and len(rows) > limits['max_full_copies']:
        blockers.append('ARCHIVE_COPY_CAP_EXCEEDED')
    if not for_deletion and total > limits['max_attributed_bytes']:
        blockers.append('ARCHIVE_BYTE_CAP_EXCEEDED')
    if not for_deletion and free_bytes < limits['minimum_free_after_reservations']:
        blockers.append('DISK_RESERVE_BELOW_FLOOR')
    for gap in registry.get('historical_gaps', []):
        if gap.get('observed_state') != 'MISSING_WITH_AVAILABLE_EVIDENCE':
            blockers.append('HISTORICAL_GAP_STATUS_CONFLICT:' + gap['candidate_id'])
    blockers = sorted(set(blockers))
    promotion_blockers = list(blockers)
    if registry['canonical_current']['candidate_id'] in accepted_gaps:
        promotion_blockers.append('OUTGOING_CURRENT_EXACT_ARCHIVE_MISSING')
    for number, proposal in proposals.items():
        if number == 213 and proposal['candidate']['candidate_id'] not in verified:
            promotion_blockers.append('PROPOSED_CANDIDATE_EXACT_ARCHIVE_MISSING:213')
        if number == 213 and (proposal.get('owner_acceptance') or {}).get('promotion_authorized') is not True:
            promotion_blockers.append('PROMOTION_OWNER_AUTHORIZATION_MISSING:213')
    # A future complete authority may classify exact owned terminal objects as
    # eligible. Incomplete authority never gets that result.
    if not blockers and registry.get('deletion_enabled') is True:
        authorized = registry['deletion_authorizations']
        for row in rows:
            grant = authorized.get(row['path'])
            if (row['classification'] == 'UNKNOWN' and row.get('publisher_owned') is True
                    and row.get('lifecycle') in TERMINAL and row.get('inactive') is True
                    and row.get('metadata_error') is None and isinstance(grant, dict)
                    and all(grant.get(k) == row.get(k) for k in ('path', *IDENTITY))
                    and grant.get('authority_ref')):
                row['classification'] = 'ELIGIBLE'
                row['reasons'] = ['EXACT_OWNER_AUTHORIZED_TERMINAL']
    result = {'artifact_type': 'integra.candidate_protection_audit',
            'registry_status': registry.get('status'),
            'decision_authority_verified': decision_verified,
            'authority_state': 'COMPLETE' if not blockers else 'BLOCKED_FAIL_CLOSED',
            'promotion_ready': not promotion_blockers,
            'promotion_blockers': sorted(set(promotion_blockers)),
            'blockers': blockers, 'canonical': canonical,
            'protected_identities': protected,
            'full_copies': len(rows), 'archive_bytes': total,
            'protected_bytes': sum(r['allocated_bytes'] for r in rows if r['classification'] == 'PROTECTED'),
            'verified_protected_bytes': sum(r['allocated_bytes'] for r in rows if r['verified_protected_archive']),
            'unknown_bytes': sum(r['allocated_bytes'] for r in rows if r['classification'] == 'UNKNOWN'),
            'eligible_bytes': sum(r['allocated_bytes'] for r in rows if r['classification'] == 'ELIGIBLE'),
            'free_bytes': free_bytes, 'entries': rows}
    result['bootstrap_plan'] = bootstrap_plan(registry, result)
    return result


def scan_local(registry: dict, base: Path) -> list[dict]:
    """Read-only inventory; publisher ownership requires an exact catalog bond."""
    base = Path(base).expanduser().resolve()
    if base.is_symlink() or not base.is_dir():
        raise ValueError('managed archive base is missing or linked')
    seen: set[tuple[int, int]] = set()
    rows = []
    catalog = {}
    try:
        from scripts import candidate_retention as retention
        catalog_path = retention.catalog_path(base / 'Build Archive')
        if catalog_path.is_symlink() or catalog_path.stat().st_uid != os.getuid():
            raise ValueError('publisher catalog owner is unproven')
        raw = catalog_path.read_bytes()
        catalog = json.loads(raw)
        if (catalog.get('artifact_type') != 'integra.owned_archive_catalog'
                or catalog.get('owner_uid') != os.getuid()
                or not isinstance(catalog.get('artifacts'), dict)
                or not set(map(str, (base / name for name in registry['managed_roots']))).issubset(set(catalog.get('roots', [])))):
            raise ValueError('publisher catalog is incomplete')
    except (OSError, ValueError, TypeError, KeyError, ImportError):
        catalog = {}
    for name in registry['managed_roots']:
        if name not in ROOT_NAMES:
            raise ValueError('unregistered managed archive root')
        root = base / name
        if not root.exists():
            continue
        if root.is_symlink():
            raise ValueError('managed archive root is linked')
        for app in sorted(root.rglob('Integra.app')):
            if not app.is_dir() or app.is_symlink():
                continue
            package = app.parent
            relative = package.relative_to(base).as_posix()
            manifest = app / 'Contents/Resources/candidate-manifest.json'
            identity = {}
            error = None
            try:
                value = json.loads(manifest.read_text())
                identity = {'candidate_id': value['candidate_id'],
                            'bundle_digest': value['bundle']['digest'],
                            'manifest_digest': sha(manifest.read_bytes())}
            except (OSError, ValueError, KeyError, TypeError) as problem:
                error = str(problem)
            amount = 0
            for directory, dirs, files in os.walk(package, followlinks=False):
                for item in (Path(directory), *(Path(directory) / n for n in dirs + files)):
                    s = item.lstat(); key = (s.st_dev, s.st_ino)
                    if key not in seen:
                        amount += s.st_blocks * 512; seen.add(key)
                    if stat.S_ISLNK(s.st_mode):
                        error = 'package contains a symlink'
            owned = False
            lifecycle = 'LEGACY_UNCONFIRMED'
            inactive = False
            record = catalog.get('artifacts', {}).get(str(package))
            if isinstance(record, dict) and not record.get('historical'):
                try:
                    verified_identity, receipt, metadata_error = retention._metadata(package)
                    owned = (metadata_error is None and verified_identity == identity
                             and retention._ownership(package, record, receipt)
                             and not retention._publisher_live(record))
                    if owned:
                        lifecycle = record.get('status', 'LEGACY_UNCONFIRMED')
                        inactive = retention._inactive(package)
                except (OSError, ValueError, KeyError, TypeError):
                    owned = False
            rows.append({'path': relative, 'absolute_path': str(package),
                         **identity, 'allocated_bytes': amount,
                         'metadata_error': error, 'publisher_owned': owned,
                         'lifecycle': lifecycle, 'inactive': inactive})
    return rows


def main() -> int:
    registry = json.loads(REGISTRY.read_text())
    try:
        current, proposals, canonical = fetch_canonical(registry)
        base = Path.home() / 'Library/Application Support/Integra'
        packages = scan_local(registry, base)
        import shutil
        free = shutil.disk_usage(base).free
        result = resolve(registry, current, proposals, packages,
                         free_bytes=free, canonical=canonical)
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as error:
        result = {'artifact_type': 'integra.candidate_protection_audit',
                  'authority_state': 'BLOCKED_FAIL_CLOSED', 'promotion_ready': False,
                  'blockers': ['AUDIT_INPUT_ERROR:' + str(error)]}
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get('authority_state') == 'COMPLETE' else 2


if __name__ == '__main__':
    sys.exit(main())
