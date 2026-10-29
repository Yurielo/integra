"""Validate the bounded standing policy, not Product Owner authority itself."""
from pathlib import Path
import json
import re

REQUIRED = {'canonical_terminal_lineage', 'governed_ownership', 'complete_immutable_history',
            'fresh_protection', 'fresh_integrity', 'inactive_writer', 'no_active_role',
            'no_pending_authority', 'no_unresolved_transaction', 'no_integrity_incident',
            'no_required_physical_representation'}
DENIED = {'acceptance', 'rejection', 'rollback_selection', 'recovery_selection',
          'withdrawal', 'UNKNOWN_ownership_adoption', 'K2_continuation'}


def validate(value):
    errors = []
    expected = {'schema_version': '1.0',
                'artifact_type': 'integra.candidate_lifecycle_retention_policy',
                'status': 'PRODUCT_OWNER_AUTHORIZED_ACTIVE',
                'policy_id': 'terminal-owned-archive-retirement-v1',
                'max_full_copies': 8, 'max_attributed_bytes': 21474836480,
                'minimum_free_after_reservations': 16106127360,
                'rotation_strategy': 'OLDEST_PROVEN_ELIGIBLE_FIRST',
                'rotation_scope': 'ONE_FULL_COPY_PER_TRANSACTION',
                'all_protected': 'FAIL_CLOSED_NO_NINTH_ARCHIVE',
                'absolute_hold_prefixes': ['721d', '073396', '97be', '14b3']}
    for key, expected_value in expected.items():
        if value.get(key) != expected_value or type(value.get(key)) is not type(expected_value):
            errors.append('retention policy differs: ' + key)
    for key, members in [('requires', REQUIRED), ('does_not_authorize', DENIED)]:
        values = value.get(key)
        if not isinstance(values, list) or not all(isinstance(v, str) for v in values) or set(values) != members or len(values) != len(members):
            errors.append('retention policy predicate enumeration differs: ' + key)
    if not isinstance(value.get('authority_ref'), str) or not value['authority_ref']:
        errors.append('retention policy authority reference missing')
    if not re.fullmatch('[0-9a-f]{64}', str(value.get('authority_payload_sha256', ''))):
        errors.append('retention policy authority payload digest missing')
    if set(value) != set(expected) | {'requires', 'does_not_authorize', 'authority_ref', 'authority_payload_sha256'}:
        errors.append('retention policy fields differ')
    return errors


def validate_file(root: Path):
    return (validate(json.loads((root / 'state/candidate_lifecycle_retention_policy_v1.json').read_bytes()))
            + validate_rotation(json.loads((root / 'state/candidate_archive_rotation_policy_v2.json').read_bytes())))


def validate_rotation(value):
    """Validate the Owner's capacity-rotation amendment separately from v1 history."""
    expected = {
        'schema_version': '2.0',
        'artifact_type': 'integra.candidate_archive_rotation_policy',
        'status': 'PRODUCT_OWNER_AUTHORIZED_ACTIVE',
        'supersedes': 'terminal-owned-archive-retirement-v1 for capacity rotation only',
        'max_full_copies': 8,
        'max_attributed_bytes': 21474836480,
        'minimum_free_after_reservations': 16106127360,
        'rotation_strategy': 'OLDEST_FULL_COPY_FIRST',
        'new_order_source': 'PUBLISHER_PUBLICATION_TIMESTAMP',
        'legacy_order_source': 'APFS_DIRECTORY_BIRTHTIME_OBSERVED_NOW',
        'pre_amendment_publisher_order_source': 'PUBLISHER_SEQUENCE_WITH_OBSERVED_NOW_COHORT_PLACEMENT',
        'initial_order_persistence': 'EXACT_EIGHT_COPY_ORDINAL_IN_OWNED_CATALOG',
        'tie_break': 'CANDIDATE_ID',
        'retire_exactly_one': True,
        'installed_app': 'PRESERVE_UNCHANGED',
        'physical_availability_after_retirement': 'RETIRED_NOT_AVAILABLE',
        'legacy_attestation': 'OBSERVED_NOW_NOT_HISTORICAL_PUBLICATION',
        'owner_decisions_required_for_routine_rotation': False,
    }
    errors = []
    if set(value) != set(expected) | {'authority_ref', 'authority_payload_sha256', 'order_clarification_ref'}:
        errors.append('rotation policy fields differ')
    for key, required in expected.items():
        if value.get(key) != required or type(value.get(key)) is not type(required):
            errors.append('rotation policy differs: ' + key)
    if not isinstance(value.get('authority_ref'), str) or not value['authority_ref']:
        errors.append('rotation policy authority reference missing')
    if not re.fullmatch('[0-9a-f]{64}', str(value.get('authority_payload_sha256', ''))):
        errors.append('rotation policy authority digest missing')
    if not isinstance(value.get('order_clarification_ref'), str) or not value['order_clarification_ref']:
        errors.append('rotation policy order clarification missing')
    return errors
