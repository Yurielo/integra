"""Pure canonical lifecycle replay and durable physical retirement evidence.

This module neither discovers authority nor changes acceptance. Its inputs must
come from the fresh canonical protection resolver, not the ownership catalog.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
from datetime import datetime, timezone

IDENTITY = ('candidate_id', 'bundle_digest', 'manifest_digest')
TERMINAL = {'COMPLETED', 'REJECTED', 'SUPERSEDED', 'UNUSED',
            'HISTORICAL_PROMOTED', 'WITHDRAWN_SUPERSEDED'}
PENDING = {'AWAITING_OWNER_ACCEPTANCE', 'AWAITING_BASELINE_ACCEPTANCE',
           'ACCEPTED_UNPROMOTED', 'AWAITING_CURRENT_PROMOTION'}
HOLDS = ('candidate-v1-721d', 'candidate-v1-073396',
         'candidate-v1-97be', 'candidate-v1-14b3')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()


def exact_identity(identity):
    return (isinstance(identity, dict)
            and isinstance(identity.get('candidate_id'), str)
            and re.fullmatch(r'candidate-v1-[0-9a-f]{64}', identity['candidate_id'])
            and all(isinstance(identity.get(key), str)
                    and re.fullmatch(r'[0-9a-f]{64}', identity[key])
                    for key in ('bundle_digest', 'manifest_digest')))


def evidence_matches(identity, evidence):
    return bool(exact_identity(identity) and isinstance(evidence, dict)
                and all(evidence.get(key) == identity[key] for key in IDENTITY)
                and evidence.get('immutable_history_complete') is True
                and exact_source(evidence.get('source'))
                and evidence.get('canonical_snapshot')
                and evidence.get('acceptance_refs')
                and evidence.get('promotion_refs')
                and evidence.get('proposal_refs'))


def exact_source(source):
    return bool(isinstance(source, dict) and all(
        isinstance(source.get(key), str) and re.fullmatch(r'[0-9a-f]{40}', source[key])
        for key in ('commit_sha', 'tree_sha')))


def collect_lifecycle_events(current, promotion_events, canonical_snapshot):
    """Replay only retained exact promotion events linked to accepted records.

    The caller fetches immutable event bytes at canonical main and verifies the
    retired Proposal binding. Generic events may be decorated with their
    verified Proposal's ``inputs.source`` by that transport layer.
    """
    events = {}
    records = current.get('records', [])
    for path, event in promotion_events.items():
        inputs = event.get('inputs', {})
        identity = inputs.get('candidate', inputs.get('incoming', {}))
        if not exact_identity(identity):
            raise ValueError('canonical lifecycle event exact identity is incomplete')
        matches = [record for record in records
                   if record.get('baseline_id') == event.get('result', {}).get('current_id')
                   and all(record.get('candidate', {}).get(k) == identity[k]
                           for k in ('candidate_id', 'bundle_digest'))]
        if len(matches) != 1:
            raise ValueError('canonical promotion does not bind one accepted CURRENT record')
        record = matches[0]
        acceptance = record.get('acceptance', {})
        authorization = inputs.get('authorization', inputs.get('authority_ref'))
        if not authorization:
            authorization = inputs.get('authority', {}).get('promotion', {}).get('authority_ref')
        if (acceptance.get('decision') not in {'USER_ACCEPTED', 'PILOT_ACCEPTED'}
                or not acceptance.get('authority_ref') or not authorization
                or not event.get('transaction_id') or not canonical_snapshot
                or not exact_source(inputs.get('source'))):
            raise ValueError('canonical lifecycle acceptance/promotion authority is incomplete')
        if event.get('artifact_type') == 'integra.open_proposal_promotion_transaction':
            if event.get('semantics', {}).get('post') != 'CURRENT_PROTECTED_PROPOSAL_CONSUMED':
                raise ValueError('canonical lifecycle promotion is not consumed')
        elif event.get('artifact_type') not in {
                'integra.exact_successor_transaction', 'integra.successor_transaction'}:
            raise ValueError('canonical lifecycle event type is unsupported')
        proposal = inputs.get('proposal_id')
        if not proposal:
            proposal = event.get('result', {}).get('accepted_proposal_path')
        if not proposal:
            raise ValueError('canonical lifecycle Proposal lineage is incomplete')
        evidence = {**{k: identity[k] for k in IDENTITY},
                    'source': deepcopy(inputs.get('source')),
                    'acceptance_refs': [acceptance['authority_ref']],
                    'promotion_refs': [path, authorization],
                    'proposal_refs': [proposal],
                    'transaction_id': event['transaction_id'],
                    'canonical_snapshot': deepcopy(canonical_snapshot),
                    'immutable_history_complete': True}
        cid = identity['candidate_id']
        if cid in events and events[cid] != evidence:
            raise ValueError('conflicting canonical lifecycle events')
        events[cid] = evidence
    return events


def replay(record, events, protected_roles):
    """Reconcile only a proven exact promoted identity, preserving human history."""
    result = deepcopy(record)
    evidence = (events or {}).get(record.get('candidate_id'))
    if not evidence_matches(record, evidence):
        return result
    roles = set(protected_roles or [])
    if 'CURRENT' in roles:
        state = 'CURRENT'
    elif roles & {'CONFIRMED_ROLLBACK', 'IMMEDIATE_ROLLBACK', 'ROLLBACK'}:
        state = 'CONFIRMED_ROLLBACK'
    elif roles & {'CONFIRMED_RECOVERY', 'SELECTED_RECOVERY', 'RECOVERY'}:
        state = 'CONFIRMED_RECOVERY'
    elif roles:
        state = 'PROMOTED_PROTECTED'
    else:
        state = 'HISTORICAL_PROMOTED'
    result['local_lifecycle_before_replay'] = record.get(
        'local_lifecycle_before_replay', record.get('status', 'UNKNOWN'))
    result['status'] = state
    result['lifecycle_evidence'] = deepcopy(evidence)
    result['lifecycle_authority'] = 'CANONICAL_EXACT_PROMOTION_REPLAY'
    return result


def terminal_eligibility(identity, record, roles, *, owned,
                         integrity_verified, context_valid, inactive,
                         standing_policy=None):
    """All standing predicates must pass; losing one role is never sufficient."""
    reasons = []
    if not exact_identity(identity) or any(record.get(k) != identity.get(k)
                                          for k in IDENTITY):
        reasons.append('EXACT_IDENTITY_UNPROVEN')
    cid = identity.get('candidate_id', '')
    if cid.startswith(HOLDS):
        reasons.append('EXPLICIT_TASK_HOLD')
    if owned is not True:
        reasons.append('OWNERSHIP_UNKNOWN_OR_UNCONFIRMED')
    if integrity_verified is not True or record.get('integrity_incident'):
        reasons.append('INTEGRITY_UNPROVEN_OR_INCIDENT')
    if context_valid is not True:
        reasons.append('FRESH_CANONICAL_PROTECTION_UNAVAILABLE')
    if inactive is not True:
        reasons.append('ACTIVE_OR_ACTIVITY_UNPROVEN')
    reasons.extend(sorted(set(roles or [])))
    if record.get('pin_ref'):
        reasons.append('EXPLICIT_GOVERNANCE_PROVENANCE')
    if record.get('unresolved_successor_transaction'):
        reasons.append('UNRESOLVED_SUCCESSOR_TRANSACTION')
    if record.get('historical_gap_obligation'):
        reasons.append('HISTORICAL_GAP_OBLIGATION')
    if record.get('required_rollback_or_recovery'):
        reasons.append('ROLLBACK_OR_RECOVERY_REQUIRED')
    if record.get('sole_required_representation'):
        reasons.append('SOLE_REQUIRED_REPRESENTATION')
    if record.get('status') in PENDING:
        reasons.append(record['status'])
    if record.get('status') not in TERMINAL:
        reasons.append('LIFECYCLE_NOT_TERMINAL')
    evidence = record.get('lifecycle_evidence')
    if not evidence_matches(identity, evidence):
        reasons.append('IMMUTABLE_HISTORY_INCOMPLETE')
    policy = standing_policy or {}
    if (policy.get('status') != 'PRODUCT_OWNER_AUTHORIZED_ACTIVE'
            or not policy.get('authority_ref')):
        reasons.append('STANDING_POLICY_UNAVAILABLE')
    return {'eligible': not reasons, 'reasons': sorted(set(reasons))}


def prepare_retirement(identity, record, manifest, verification, *,
                       transaction_id, canonical_snapshot, policy,
                       reason='TERMINAL_NO_CANONICAL_PROTECTION', timestamp=None):
    """Retain full immutable identity/evidence before any physical withdrawal."""
    if (not exact_identity(identity) or not evidence_matches(
            identity, record.get('lifecycle_evidence'))
            or any(record.get(k) != identity[k] for k in IDENTITY)
            or not transaction_id or not canonical_snapshot
            or policy.get('status') != 'PRODUCT_OWNER_AUTHORIZED_ACTIVE'
            or not policy.get('authority_ref')):
        raise ValueError('physical retirement receipt authority/identity is incomplete')
    source = manifest.get('identity', {}).get('source', manifest.get('source'))
    if (manifest.get('candidate_id') != identity['candidate_id']
            or manifest.get('bundle', {}).get('digest') != identity['bundle_digest']
            or not source):
        raise ValueError('physical retirement manifest identity differs')
    evidence = record['lifecycle_evidence']
    if evidence.get('source') is not None and any(
            source.get(k) != value for k, value in evidence['source'].items()):
        raise ValueError('retirement source differs from exact canonical lineage')
    return {'schema_version': '1.0',
            'artifact_type': 'integra.candidate_physical_retirement',
            **{k: identity[k] for k in IDENTITY},
            'source': deepcopy(source),
            'publisher_attestation': deepcopy(record),
            'complete_sha256': record.get('complete_sha256'),
            'inventory_sha256': record.get('inventory_sha256'),
            'retained_manifest': deepcopy(manifest),
            'lifecycle_before_retirement': record['status'],
            'proposal_refs': deepcopy(evidence['proposal_refs']),
            'acceptance_refs': deepcopy(evidence['acceptance_refs']),
            'promotion_refs': deepcopy(evidence['promotion_refs']),
            'lifecycle_evidence': deepcopy(evidence),
            'verification_evidence': deepcopy(verification),
            'reason': reason, 'policy_authority_ref': policy['authority_ref'],
            'transaction_id': transaction_id,
            'canonical_snapshot': deepcopy(canonical_snapshot),
            'timestamp': timestamp or datetime.now(timezone.utc).isoformat(),
            'state': 'PREPARED', 'execution_result': 'NOT_EXECUTED',
            'physical_available': True}


def update_retirement(receipt, *, source, trash, completed=False, error=None):
    """Physical truth dominates claims; a prepared receipt never implies deletion."""
    result = deepcopy(receipt)
    remains = Path(source).exists() or Path(trash).exists()
    if completed and remains:
        raise ValueError('cannot report retirement while physical payload exists')
    if completed:
        result.update(state='RETIRED_NOT_AVAILABLE', execution_result='PASS',
                      physical_available=False)
    elif error is not None or not Path(source).exists():
        result.update(state='PARTIAL', execution_result='INTERRUPTED',
                      physical_available=remains, error=str(error) if error else None)
    return result
