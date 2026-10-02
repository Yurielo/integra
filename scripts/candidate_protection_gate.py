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
    registry = json.loads(protection.REGISTRY.read_text())
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
                      outgoing_archive: Path) -> None:
    """Require complete authority as an additional gate before record writes."""
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
    if registry.get('deletion_enabled') is not True:
        raise ValueError('canonical protection disables deletion')
    base = Path.home() / 'Library/Application Support/Integra'
    path = path.resolve()
    try:
        relative = path.relative_to(base).as_posix()
    except ValueError as error:
        raise ValueError('deletion target is outside managed authority') from error
    rows = [item for item in audit['entries'] if item['path'] == relative]
    grant = registry['deletion_authorizations'].get(relative)
    if (len(rows) != 1 or rows[0]['classification'] != 'ELIGIBLE'
            or not isinstance(grant, dict)
            or not grant.get('authority_ref')
            or any(grant.get(key) != rows[0].get(key)
                   for key in ('path', *protection.IDENTITY))):
        raise ValueError('canonical protection forbids deletion')
    return {'registry_sha256': hashlib.sha256(protection.REGISTRY.read_bytes()).hexdigest(),
            'canonical_sha256': protection.digest(audit['canonical']),
            'path': relative, 'identity': {key: rows[0][key] for key in protection.IDENTITY},
            'grant': grant}


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
    if (registry.get('status') != 'PRODUCT_OWNER_AUTHORIZED_ACTIVE'
            or not registry.get('activation_authority_ref')
            or not registry.get('promotion_contract_integration_ref')
            or registry.get('deletion_enabled') is not True
            or registry.get('deletion_authorizations', {}).get(lease.get('path')) != lease.get('grant')):
        raise ValueError('canonical deletion authority is unavailable')
    current, proposals, canonical = protection.fetch_canonical(registry)
    if protection.digest(canonical) != lease.get('canonical_sha256'):
        raise ValueError('canonical deletion inputs changed')
    blockers = []
    protected = protection._validate_registry(registry, current, proposals, blockers)
    identity = lease.get('identity') or {}
    if blockers or identity.get('candidate_id') in protected:
        raise ValueError('canonical protection blocks resumed deletion')
    base = Path.home() / 'Library/Application Support/Integra'
    for cid, relative in registry['selected_survivors'].items():
        if not relative:
            raise ValueError('protected survivor is missing: ' + cid)
        if cid not in protected or not (base / relative / 'COMPLETE.json').is_file():
            raise ValueError('protected survivor disappeared: ' + cid)
