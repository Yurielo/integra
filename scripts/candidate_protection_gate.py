"""Fail-closed operation gates over the single Candidate protection registry.

No operation here mutates an archive or CURRENT. Callers retain their existing
validation; this gate only adds authority and exact survivor requirements.
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import hashlib

try:
    from scripts import candidate_protection_audit as protection
except ModuleNotFoundError:
    import candidate_protection_audit as protection


def _snapshot(*, for_deletion: bool = False) -> tuple[dict, dict]:
    registry_bytes = protection.REGISTRY.read_bytes()
    registry_sha256 = protection.sha(registry_bytes)
    registry = json.loads(registry_bytes)
    if (registry.get('status') != 'PRODUCT_OWNER_AUTHORIZED_ACTIVE'
            or not registry.get('activation_authority_ref')
            or not registry.get('promotion_contract_integration_ref')
            or type(registry.get('deletion_enabled')) is not bool):
        raise ValueError('canonical protection authority is not activated and integrated')
    current, proposals, canonical = protection.fetch_canonical(registry)
    base = Path.home() / 'Library/Application Support/Integra'
    packages = protection.scan_local(registry, base)
    audit = protection.resolve(registry, current, proposals, packages,
                               free_bytes=shutil.disk_usage(base).free,
                               canonical=canonical, for_deletion=for_deletion)
    if audit['authority_state'] != 'COMPLETE':
        raise ValueError('canonical protection authority is incomplete: ' + ','.join(audit['blockers']))
    if protection.sha(protection.REGISTRY.read_bytes()) != registry_sha256:
        raise ValueError('canonical protection registry changed during capture')
    audit['registry_sha256'] = registry_sha256
    return registry, audit


def _selected_verified(registry: dict, audit: dict, identity: dict, archive: Path) -> None:
    cid = identity['candidate_id']
    selected = registry['selected_survivors'].get(cid)
    if not selected:
        raise ValueError('protected Candidate has no selected archive: ' + cid)
    base = Path.home() / 'Library/Application Support/Integra'
    expected = base / selected
    if archive.resolve() != expected.resolve():
        raise ValueError('operation archive differs from canonical selected survivor: ' + cid)
    rows = [item for item in audit['entries'] if item['path'] == selected]
    if (len(rows) != 1 or not rows[0]['verified_protected_archive']
            or rows[0]['classification'] != 'PROTECTED'
            or any(rows[0].get(key) != identity[key] for key in protection.IDENTITY)):
        raise ValueError('canonical selected survivor is not byte verified: ' + cid)


def require_promotion(proposal: dict, current: dict, candidate_archive: Path,
                      outgoing_archive: Path | None, *, transaction: dict | None = None,
                      expected_head: str | None = None) -> None:
    """Require complete authority as an additional gate before record writes."""
    if transaction is not None:
        if outgoing_archive is not None or not expected_head:
            raise ValueError('exact missing-outgoing transaction needs external head and no false archive')
        try:
            from scripts.successor_transaction import require_exact_promotion
        except ModuleNotFoundError:
            from successor_transaction import require_exact_promotion
        require_exact_promotion(protection.ROOT, transaction, proposal, current,
                                candidate_archive, expected_head)
        return
    if outgoing_archive is None:
        raise ValueError('outgoing CURRENT archive is required; no general exception')
    registry, audit = _snapshot()
    if not audit['promotion_ready']:
        raise ValueError('canonical protection does not authorize promotion')
    if current.get('current_id') != registry['canonical_current']['current_id']:
        raise ValueError('promotion CURRENT differs from canonical authority')
    local_current = protection.ROOT / registry['canonical_current']['path']
    data = local_current.read_bytes()
    if (protection.sha(data) != registry['canonical_current']['sha256']
            or json.loads(data) != current):
        raise ValueError('promotion CURRENT bytes differ from exact canonical main binding')
    _selected_verified(registry, audit, proposal['candidate'], candidate_archive)
    _selected_verified(registry, audit, registry['canonical_current'], outgoing_archive)


def require_archive_publication(archive_root: Path, estimated_bytes: int) -> None:
    """Admit a new managed full copy only against fresh canonical protection."""
    registry, audit = _snapshot()
    if type(estimated_bytes) is not int or estimated_bytes < 0:
        raise ValueError('archive estimate is invalid')
    base = Path.home() / 'Library/Application Support/Integra'
    root = archive_root.resolve()
    if not any(root == base / name or root.is_relative_to(base / name)
               for name in registry['managed_roots']):
        raise ValueError('archive publication root is outside managed authority')
    limits = registry['limits']
    if (audit['full_copies'] + 1 > limits['max_full_copies']
            or audit['archive_bytes'] + estimated_bytes > limits['max_attributed_bytes']
            or audit['free_bytes'] - estimated_bytes < limits['minimum_free_after_reservations']):
        raise ValueError('canonical archive copy, byte, or disk reserve cap blocks publication')


def require_deletion(path: Path) -> None:
    """No deletion without an exact grant and a fresh eligible classification."""
    registry, audit = _snapshot(for_deletion=True)
    base = Path.home() / 'Library/Application Support/Integra'
    path = path.resolve()
    try:
        relative = path.relative_to(base).as_posix()
    except ValueError as error:
        raise ValueError('deletion target is outside managed authority') from error
    rows = [item for item in audit['entries'] if item['path'] == relative]
    grant = {**registry.get('deletion_authorizations', {}),
             **registry.get('withdrawal_deletion_authorizations', {})}.get(relative)
    # A standing retirement has canonical promotion lineage.  An exact
    # owner-authorized withdrawal is terminal through different immutable
    # evidence and must use its separately validated exact grant below.
    if (len(rows) == 1 and rows[0].get('standing_retirement_eligible') is True
            and rows[0].get('reasons') == ['STANDING_TERMINAL_RETIREMENT']
            and rows[0].get('candidate_id') in
            audit.get('canonical', {}).get('canonical_lifecycles', {})):
        policy = audit['canonical'].get('standing_policy')
        if not policy:
            raise ValueError('standing terminal retirement policy unavailable')
        grant = {'kind': 'STANDING_TERMINAL_RETIREMENT', 'path': relative,
                 **{k: rows[0][k] for k in protection.IDENTITY},
                 'authority_ref': policy['authority_ref'], 'policy_sha256': policy['sha256'],
                 'lifecycle_evidence': audit['canonical']['canonical_lifecycles'][rows[0]['candidate_id']]}
    elif registry.get('deletion_enabled') is not True:
        raise ValueError('canonical protection disables deletion')
    if (len(rows) != 1 or rows[0]['classification'] != 'ELIGIBLE'
            or not isinstance(grant, dict)
            or not grant.get('authority_ref')
            or any(grant.get(key) != rows[0].get(key)
                   for key in ('path', *protection.IDENTITY))):
        raise ValueError('canonical protection forbids deletion')
    survivors = {}
    for cid, selected in registry['selected_survivors'].items():
        if selected is not None:
            receipt = base / selected / 'COMPLETE.json'
            survivors[cid] = {'path': selected,
                              'receipt_sha256': protection.sha(receipt.read_bytes())}
    if protection.sha(protection.REGISTRY.read_bytes()) != audit.get('registry_sha256'):
        raise ValueError('canonical protection registry changed before deletion lease')
    return {'registry_sha256': audit['registry_sha256'],
            'canonical_sha256': protection.digest(audit['canonical']),
            'path': relative, 'identity': {key: rows[0][key] for key in protection.IDENTITY},
            'grant': grant, 'survivors': survivors}


def require_deletion_continuation(lease: dict) -> None:
    """Revalidate canonical bytes after an owned package is moved to trash.

    The original path no longer exists at this point, so a fresh eligibility
    scan would misclassify the in-progress transaction. The immutable decision
    and grant are instead bound to the journal and every canonical input is
    refreshed before unlink or interrupted recovery.
    """
    if not isinstance(lease, dict):
        raise ValueError('canonical deletion lease is missing')
    data = protection.REGISTRY.read_bytes()
    if hashlib.sha256(data).hexdigest() != lease.get('registry_sha256'):
        raise ValueError('canonical deletion registry changed')
    registry = json.loads(data)
    standing = (lease.get('grant') or {}).get('kind') == 'STANDING_TERMINAL_RETIREMENT'
    if (registry.get('status') != 'PRODUCT_OWNER_AUTHORIZED_ACTIVE'
            or not registry.get('activation_authority_ref')
            or not registry.get('promotion_contract_integration_ref')
            or (not standing and (registry.get('deletion_enabled') is not True
                or {**registry.get('deletion_authorizations', {}),
                    **registry.get('withdrawal_deletion_authorizations', {})}.get(lease.get('path')) != lease.get('grant')))):
        raise ValueError('canonical deletion authority is unavailable')
    current, proposals, canonical = protection.fetch_canonical(registry)
    if standing:
        policy = canonical.get('standing_policy') or {}
        identity = lease.get('identity') or {}
        grant = lease['grant']
        if (policy.get('status') != 'PRODUCT_OWNER_AUTHORIZED_ACTIVE'
                or policy.get('sha256') != grant.get('policy_sha256')
                or policy.get('authority_ref') != grant.get('authority_ref')
                or grant.get('lifecycle_evidence') != canonical.get('canonical_lifecycles', {}).get(identity.get('candidate_id'))
                or any(grant.get(k) != identity.get(k) for k in protection.IDENTITY)):
            raise ValueError('standing terminal retirement authority/identity changed')
    if protection.digest(canonical) != lease.get('canonical_sha256'):
        raise ValueError('canonical deletion inputs changed')
    blockers = []
    accepted_gaps = protection._accepted_historical_gaps(registry, canonical, blockers)
    protected = protection._validate_registry(registry, current, proposals, blockers, accepted_gaps, canonical)
    identity = lease.get('identity') or {}
    if blockers or identity.get('candidate_id') in protected:
        raise ValueError('canonical protection blocks resumed deletion')
    base = Path.home() / 'Library/Application Support/Integra'
    selected = registry['selected_survivors']
    if set(selected) != set(protected):
        raise ValueError('protected survivor set changed')
    expected_survivors = lease.get('survivors')
    if not isinstance(expected_survivors, dict) or set(expected_survivors) != {
            cid for cid, relative in selected.items() if relative is not None}:
        raise ValueError('protected survivor lease is incomplete')
    for cid, relative in selected.items():
        if relative is None:
            proposal_ids = {proposal['candidate']['candidate_id']
                            for proposal in proposals.values()}
            if cid not in accepted_gaps and cid not in proposal_ids:
                raise ValueError('required protected survivor is missing: ' + cid)
            continue
        if cid in accepted_gaps or not isinstance(relative, str) or not relative:
            raise ValueError('protected survivor claim conflicts with accepted gap: ' + cid)
        receipt = base / relative / 'COMPLETE.json'
        if (expected_survivors[cid].get('path') != relative
                or protection.sha(receipt.read_bytes()) != expected_survivors[cid].get('receipt_sha256')):
            raise ValueError('protected survivor disappeared or changed: ' + cid)
        if standing:
            protection.verify_archive(base / relative, protected[cid]['identity'])
