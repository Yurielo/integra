"""Fresh canonical retention protection; no archive or governance writes.

An absent canonical pin registry yields provisional protection, never deletion
authority. Local recovery confirmations are SHA-bound structured owner evidence.
"""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import re
import subprocess

REPOSITORY = 'Yurielo/integra'
PROPOSAL = 'state/proposed_baseline_lite_v1.json'
CURRENT = 'state/current_product_baseline_v2.json'
POLICY = 'state/candidate_retention_policy_v1.json'


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _get(endpoint, *, absent=False):
    result = subprocess.run(['gh', 'api', endpoint], capture_output=True,
                            text=True, timeout=30)
    if result.returncode:
        if absent and re.search(r'\(HTTP 404\)', result.stderr):
            return None
        raise ValueError('canonical GitHub read failed: ' + endpoint)
    return json.loads(result.stdout)


def _content(path, ref, *, absent=False):
    value = _get(f'repos/{REPOSITORY}/contents/{path}?ref={ref}', absent=absent)
    if value is None:
        return None
    if value.get('encoding') != 'base64' or value.get('type') != 'file':
        raise ValueError('canonical input is not a base64 regular file')
    data = base64.b64decode(value['content'])
    return {'blob_sha': value['sha'], 'sha256': _sha(data), 'value': json.loads(data)}


def _open_heads():
    heads = {}
    for page in range(1, 11):
        values = _get(f'repos/{REPOSITORY}/pulls?state=open&per_page=100&page={page}')
        if not isinstance(values, list):
            raise ValueError('open PR inventory is invalid')
        for item in values:
            if item['state'] != 'open' or item['number'] in heads:
                raise ValueError('open PR inventory changed during pagination')
            heads[item['number']] = item['head']['sha']
        if len(values) < 100:
            return heads
    raise ValueError('open PR inventory exceeds bounded exhaustive read')


def fetch_snapshot():
    main = _get(f'repos/{REPOSITORY}/git/ref/heads/main')['object']['sha']
    current = _content(CURRENT, main)
    heads = _open_heads()
    proposals = {}
    for number, head in sorted(heads.items()):
        if _get(f'repos/{REPOSITORY}/commits/{head}').get('sha') != head:
            raise ValueError('open PR exact head is not readable in canonical repository')
        proposals[str(number)] = {'head_sha': head,
                                  'proposal': _content(PROPOSAL, head, absent=True)}
    policy = _content(POLICY, main, absent=True)
    pin_requirements = None
    if policy is not None:
        value = policy['value']
        if (value.get('artifact_type') == 'integra.candidate_retention_policy'
                and value.get('schema_version') == '1.0'
                and value.get('status') == 'PRODUCT_OWNER_AUTHORIZED' and value.get('authority_ref')):
            pin_requirements = value.get('explicit_governance_pins')
            if pin_requirements is not None and (not isinstance(pin_requirements, dict)
                    or any(not isinstance(k, str) or not isinstance(v, str) or not v
                           for k, v in pin_requirements.items())):
                raise ValueError('canonical governance pin registry is invalid')
    if (_get(f'repos/{REPOSITORY}/git/ref/heads/main')['object']['sha'] != main
            or _open_heads() != heads):
        raise ValueError('canonical protection changed during capture')
    return {'repository': REPOSITORY, 'main_sha': main, 'current': current,
            'open_prs': proposals, 'policy': policy,
            'pin_requirements': pin_requirements}


def validate_snapshot(snapshot):
    """Refetch all canonical inputs; any incomplete/error/drift fails closed."""
    try:
        if not snapshot or snapshot.get('pin_requirements') is None:
            return False
        expected = {k: v for k, v in snapshot.items() if k != 'authority_comments'}
        if fetch_snapshot() != expected:
            return False
        return all(_sha(json.dumps(_get(endpoint), sort_keys=True).encode()) == digest
                   for endpoint, digest in snapshot.get('authority_comments', {}).items())
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired):
        return False


def _recovery_authority(authority, receipt, snapshot):
    inputs = {}
    if isinstance(authority, dict):
        path = Path(authority['path']).expanduser().absolute()
        if any(p.is_symlink() for p in (path, *path.parents)):
            raise ValueError('recovery authority traverses a symlink')
        data = path.read_bytes()
        if _sha(data) != authority['sha256']:
            raise ValueError('recovery authority SHA differs')
        value = json.loads(data)
        if authority.get('repository_path'):
            canonical = _content(authority['repository_path'], snapshot['main_sha'])
            if (canonical['sha256'] != _sha(data)
                    or value.get('result') != 'EXACT_RECORDED_BUNDLE_AND_MANIFEST_RECOVERED'
                    or value.get('recovered_candidate') != receipt['candidate_id']
                    or value.get('recovered_bundle_digest') != receipt['bundle_digest']
                    or value.get('manifest_sha256') != receipt['manifest_digest']):
                raise ValueError('accepted recovery evidence does not bind exact retained identity')
            inputs[str(path)] = _sha(data)
            return (f"https://github.com/{REPOSITORY}/blob/{snapshot['main_sha']}/"
                    + authority['repository_path']), inputs
        if (value.get('decision') != 'CONFIRMED_RECOVERY' or not value.get('authority_ref')
                or any(value.get(k) != receipt[k] for k in ('candidate_id', 'bundle_digest'))):
            raise ValueError('recovery confirmation does not bind exact retained identity')
        inputs[str(path)] = _sha(data)
        # A self-authored JSON and its SHA do not establish owner authority.
        ref, verified_inputs = _recovery_authority(value['authority_ref'], receipt, snapshot)
        return ref, {**inputs, **verified_inputs}
    match = re.fullmatch(r'https://github\.com/Yurielo/integra/issues/\d+#issuecomment-(\d+)',
                         authority or '')
    if not match:
        raise ValueError('explicit recovery confirmation is required')
    value = _get(f'repos/{REPOSITORY}/issues/comments/{match.group(1)}')
    body = value.get('body', '')
    if body.strip().startswith('```json') and body.strip().endswith('```'):
        body = body.strip()[7:-3].strip()
    try:
        decision = json.loads(body)
    except (ValueError, TypeError):
        raise ValueError('recovery owner comment needs an explicit structured confirmation')
    if (value.get('user', {}).get('login', '').lower() != 'yurielo'
            or not isinstance(decision, dict) or decision.get('decision') != 'CONFIRMED_RECOVERY'
            or any(decision.get(k) != receipt[k] for k in ('candidate_id', 'bundle_digest'))):
        raise ValueError('owner comment does not confirm exact recovery identity')
    endpoint = f'repos/{REPOSITORY}/issues/comments/{match.group(1)}'
    snapshot.setdefault('authority_comments', {})[endpoint] = _sha(
        json.dumps(value, sort_keys=True).encode())
    return authority, inputs


def capture_protection(current_path, proposals, rollback_receipt, recovery_receipt,
                       recovery_authority, pins=None):
    """Bind local inputs to exhaustive canonical truth and exact durable roles.

    Caller must supply freshly verified receipts. Result contains selected
    archive paths; duplicate paths are not silently selected or rewritten.
    """
    snapshot = fetch_snapshot()
    path = Path(current_path).expanduser().absolute()
    data = path.read_bytes()
    if _sha(data) != snapshot['current']['sha256']:
        raise ValueError('local CURRENT is not exact canonical main bytes')
    current = snapshot['current']['value']; records = current['records']
    active = [r for r in records if r['baseline_id'] == current['current_id']]
    if (len(active) != 1 or active[0] != records[-1] or len(records) < 2
            or any(r['acceptance']['decision'] != 'USER_ACCEPTED' for r in records)):
        raise ValueError('canonical accepted baseline order is ambiguous')
    if any(rollback_receipt[k] != records[-2]['candidate'][k]
           for k in ('candidate_id', 'bundle_digest')):
        raise ValueError('rollback is not exact immediate outgoing accepted identity')
    for receipt in (rollback_receipt, recovery_receipt):
        if receipt.get('status') != 'COMPLETE' or receipt.get('verification') != 'ARCHIVAL_BYTE_INTEGRITY':
            raise ValueError('selected durable role lacks verified COMPLETE receipt')
    ref, authority_inputs = _recovery_authority(recovery_authority, recovery_receipt, snapshot)
    inputs = {str(path): _sha(data), **authority_inputs}
    canonical = [entry['proposal'] for entry in snapshot['open_prs'].values()
                 if entry['proposal'] is not None]
    for proposed in proposals:
        p = Path(proposed).expanduser().absolute(); digest = _sha(p.read_bytes())
        if digest not in {entry['sha256'] for entry in canonical}:
            raise ValueError('local proposal is not an exact open PR head input')
        inputs[str(p)] = digest
    # Protection includes every canonical open-PR proposal regardless of local
    # omission; supplied files are additional bindings, never the authority set.
    protected = {}; identities = {}
    def bind_identity(value):
        identity = {k: value[k] for k in ('candidate_id', 'bundle_digest', 'manifest_digest')
                    if k in value}
        entries = identities.setdefault(value['candidate_id'], [])
        if identity not in entries:
            entries.append(identity)
    def protect(cid, reason):
        protected.setdefault(cid, []).append(reason)
    protect(active[0]['candidate']['candidate_id'], 'CURRENT')
    protect(records[-1]['candidate']['candidate_id'], 'LATEST_ACCEPTED_BASELINE')
    protect(rollback_receipt['candidate_id'], 'CONFIRMED_ROLLBACK')
    protect(recovery_receipt['candidate_id'], 'CONFIRMED_RECOVERY')
    for value in (active[0]['candidate'], records[-1]['candidate'], rollback_receipt, recovery_receipt):
        bind_identity(value)
    for entry in canonical:
        value = entry['value']
        if value.get('artifact_type') != 'integra.proposed_product_baseline':
            raise ValueError('open PR proposal has invalid governed type')
        protect(value['candidate']['candidate_id'], 'AWAITING_OWNER_ACCEPTANCE')
        bind_identity(value['candidate'])
    required = snapshot['pin_requirements']; pins = pins or {}
    if required is not None and pins != required:
        raise ValueError('caller governance pins differ from complete canonical registry')
    for cid in (required or {}):
        protect(cid, 'EXPLICIT_GOVERNANCE_PROVENANCE')
    return {'protected': protected, 'protected_identities': identities,
            'inputs': inputs, 'authoritative_snapshot': snapshot,
            'selected_receipts': {'CONFIRMED_ROLLBACK': rollback_receipt,
                                  'CONFIRMED_RECOVERY': recovery_receipt},
            'authority_refs': {'CONFIRMED_RECOVERY': ref},
            'complete': required is not None,
            'unresolved': [] if required is not None else ['CANONICAL_PIN_REGISTRY_UNAVAILABLE']}
