"""Fail-closed operation gates over the single Candidate protection registry.

No operation here mutates an archive or CURRENT. Callers retain their existing
validation; this gate only adds authority and exact survivor requirements.
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import hashlib
import re

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


# This is a single historical transition, not a substitute for the ordinary
# outgoing-CURRENT archive requirement in require_promotion().  The accepted
# #214 decision records missing bytes; it never asserts recovery.
HISTORICAL_CURRENT = 'candidate-v1-d8bd6fc2649e061d50bfabae37c636d8caeb764965c941cf4fef88ae5fe301a8'
HISTORICAL_ROLLBACK = 'candidate-v1-af81b2867f893e8e529a2d4f64d6c1370dd1249b46eb999d427fb408229680fa'
HISTORICAL_SUCCESSOR = 'candidate-v1-82ba92224a7dcdc0f1738155ba2e3f73dbdfc529ce2a8ffc461be73fa1351f29'
HISTORICAL_PROPOSAL_HEAD = 'ff0760f1a206de3f047b8d163c2c573689a4a530'


def require_historical_gap_transition(proposal: dict, current: dict,
                                      candidate_archive: Path, authorization_ref: str) -> dict:
    """Admit only the exact #214 gap -> #213 Candidate after a fresh owner gate.

    This returns evidence for a prepare-only helper. It never changes CURRENT
    or grants archive deletion. A later CURRENT cannot reuse the exception.
    """
    registry, audit = _snapshot()
    canonical = audit['canonical']
    main = canonical['main_sha']
    remote_bytes, _ = protection._remote_file('state/candidate_protection_registry_v1.json', main)
    if remote_bytes != protection.REGISTRY.read_bytes():
        raise ValueError('canonical registry is not published unchanged on main')
    expected_gaps = {('CURRENT', HISTORICAL_CURRENT), ('ROLLBACK', HISTORICAL_ROLLBACK)}
    gaps = registry.get('historical_gaps')
    if (not isinstance(gaps, list) or len(gaps) != 2
            or {(g.get('role'), g.get('candidate_id')) for g in gaps if isinstance(g, dict)} != expected_gaps
            or any(g.get('observed_state') != 'MISSING_WITH_AVAILABLE_EVIDENCE' for g in gaps)
            or registry.get('canonical_current', {}).get('candidate_id') != HISTORICAL_CURRENT
            or registry.get('rollback', {}).get('candidate_id') != HISTORICAL_ROLLBACK
            or registry.get('recovery_selection') != {
                'state': 'NO_VERIFIED_ARCHIVE_ACCEPTED_HISTORICAL_GAP',
                'candidate_id': HISTORICAL_CURRENT,
                'decision_ref': registry.get('decision_authority_ref'), 'archive_path': None}
            or registry.get('selected_survivors', {}).get(HISTORICAL_CURRENT, 'absent') is not None
            or registry.get('selected_survivors', {}).get(HISTORICAL_ROLLBACK, 'absent') is not None):
        raise ValueError('exact accepted historical recovery gap is unavailable')
    if (current.get('current_id') != registry['canonical_current']['current_id']
            or proposal.get('candidate', {}).get('candidate_id') != HISTORICAL_SUCCESSOR
            or not any(p.get('pr') == 213 and p.get('head_sha') == HISTORICAL_PROPOSAL_HEAD
                       and p.get('candidate_id') == HISTORICAL_SUCCESSOR
                       for p in registry.get('proposed', []))
            or canonical.get('proposal_heads', {}).get('213') != HISTORICAL_PROPOSAL_HEAD):
        raise ValueError('transition CURRENT or proposed Candidate differs from exact scope')
    local_current = protection.ROOT / registry['canonical_current']['path']
    data = local_current.read_bytes()
    if (protection.sha(data) != registry['canonical_current']['sha256']
            or json.loads(data) != current):
        raise ValueError('transition CURRENT differs from exact canonical main binding')
    if (registry.get('unknown_historical') != 'RETAIN_FAIL_CLOSED'
            or registry.get('deletion_enabled') is not False
            or registry.get('deletion_authorizations') != {}
            or any(row['classification'] == 'ELIGIBLE' for row in audit['entries'])
            or set(audit['promotion_blockers']) != {
                'OUTGOING_CURRENT_EXACT_ARCHIVE_MISSING',
                'PROMOTION_OWNER_AUTHORIZATION_MISSING:213'}):
        raise ValueError('transition protection or promotion blockers differ')
    _selected_verified(registry, audit, proposal['candidate'], candidate_archive)
    match = re.fullmatch(r'https://github\.com/Yurielo/integra/issues/216#issuecomment-([0-9]+)',
                         authorization_ref)
    if not match:
        raise ValueError('exact Issue #216 Product Owner transition reference required')
    authority = protection._api(f'repos/{protection.REPOSITORY}/issues/comments/{match.group(1)}')
    token = ('PRODUCT_OWNER_AUTHORIZATION: ISSUE_216_HISTORICAL_GAP_TRANSITION '
             f'FROM={HISTORICAL_CURRENT} TO={HISTORICAL_SUCCESSOR} '
             f'PROPOSAL_PR_213_HEAD={HISTORICAL_PROPOSAL_HEAD} '
             f'REGISTRY_SHA256={audit["registry_sha256"]} '
             'CURRENT_RECOVERY=MISSING_WITH_AVAILABLE_EVIDENCE '
             'ROLLBACK_RECOVERY=MISSING_WITH_AVAILABLE_EVIDENCE '
             'UNKNOWN=RETAIN_FAIL_CLOSED DELETION=FORBIDDEN')
    if (authority.get('html_url') != authorization_ref
            or authority.get('user', {}).get('login', '').lower() != 'yurielo'
            or authority.get('body', '').strip() != token):
        raise ValueError('exact Product Owner transition authorization is absent or differs')
    if protection.sha(protection.REGISTRY.read_bytes()) != audit['registry_sha256']:
        raise ValueError('canonical registry changed after transition authorization check')
    return {'authorization_ref': authorization_ref, 'authorization_token_sha256': protection.sha(token.encode()),
            'registry_sha256': audit['registry_sha256'], 'canonical_main_sha': main,
            'outgoing_recovery': 'MISSING_WITH_AVAILABLE_EVIDENCE',
            'rollback_recovery': 'MISSING_WITH_AVAILABLE_EVIDENCE',
            'proposed_archive': str(candidate_archive.resolve())}


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
    accepted_gaps = protection._accepted_historical_gaps(registry, canonical, blockers)
    protected = protection._validate_registry(registry, current, proposals, blockers, accepted_gaps)
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
