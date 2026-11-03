"""Fail-closed operation gates over the single Candidate protection registry.

No operation here mutates an archive or CURRENT. Callers retain their existing
validation; this gate only adds authority and exact survivor requirements.
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import hashlib
import os
import stat
from datetime import datetime, timezone

try:
    from scripts import candidate_protection_audit as protection
except ModuleNotFoundError:
    import candidate_protection_audit as protection


def _snapshot(*, for_deletion: bool = False, purpose: str = 'INTEGRITY') -> tuple[dict, dict]:
    registry_bytes = protection.REGISTRY.read_bytes()
    registry_sha256 = protection.sha(registry_bytes)
    registry = json.loads(registry_bytes)
    if (registry.get('status') != 'PRODUCT_OWNER_AUTHORIZED_ACTIVE'
            or not registry.get('activation_authority_ref')
            or not registry.get('promotion_contract_integration_ref')
            or type(registry.get('deletion_enabled')) is not bool):
        raise ValueError('canonical protection authority is not activated and integrated')
    current, proposals, canonical = protection.fetch_canonical(registry)
    if purpose == 'CAPACITY' and not canonical.get('rotation_policy'):
        # Before canonical v2, admission continues under its original strict
        # policy. An invalid/present v2 policy never receives this fallback.
        purpose = 'INTEGRITY'
    base = Path.home() / 'Library/Application Support/Integra'
    packages = protection.scan_local(registry, base, purpose=purpose)
    rotation_receipts = protection.load_rotation_receipts(base, canonical.get('rotation_policy'), purpose=purpose)
    audit = protection.resolve(registry, current, proposals, packages,
                               free_bytes=shutil.disk_usage(base).free,
                               canonical=canonical, for_deletion=for_deletion,
                               rotation_receipts=rotation_receipts, purpose=purpose)
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
    registry, audit = _snapshot(purpose='CAPACITY')
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


def _observed_publisher_order_evidence(package: Path, record: dict | None,
                                       identity: dict) -> dict | None:
    """Match a completed publisher record to current verified bytes.

    A device number can change when APFS exposes the preserved directory from a
    different volume view.  This narrow exception preserves the original
    catalog record (including its publication timestamp, when present), never
    sets ``publisher_owned``, and requires the exact completed receipt and
    inventory to still bind the record to the physical archive.
    """
    try:
        from scripts import candidate_retention as retention
    except ModuleNotFoundError:
        import candidate_retention as retention
    if (not isinstance(record, dict) or record.get('historical') is not False
            or record.get('publisher_completed') is not True
            or type(record.get('publication_sequence')) is not int
            or record['publication_sequence'] <= 0
            or not isinstance(record.get('publisher_run_id'), str)
            or not record['publisher_run_id']
            or type(record.get('publisher_pid')) is not int
            or record['publisher_pid'] <= 0
            or not isinstance(record.get('publisher_start_token'), str)
            or not record['publisher_start_token']
            or any(record.get(key) != identity.get(key) for key in protection.IDENTITY)):
        return None
    if package.is_symlink():
        return None
    try:
        s = package.lstat()
        if (not stat.S_ISDIR(s.st_mode)
                or record.get('owner_uid') != s.st_uid or s.st_uid != os.getuid()
                or record.get('inode') != s.st_ino
                or type(record.get('device')) is not int
                or record['device'] == s.st_dev):
            return None
        receipt_bytes = (package / 'COMPLETE.json').read_bytes()
        inventory_bytes = (package / 'inventory.json').read_bytes()
        receipt = json.loads(receipt_bytes)
        if (receipt.get('status') != 'COMPLETE'
                or any(receipt.get(key) != identity.get(key) for key in protection.IDENTITY)
                or receipt.get('inventory_sha256') != protection.sha(inventory_bytes)
                or record.get('complete_sha256') != protection.sha(receipt_bytes)
                or record.get('inventory_sha256') != protection.sha(inventory_bytes)):
            return None
    except (OSError, ValueError, TypeError, KeyError):
        return None
    order = retention._rotation_order(package, record)
    if order is None:
        return None
    return {'kind': 'OBSERVED_CATALOG_PUBLISHER_RECORD_RECEIPT_MATCH_DEVICE_DRIFT',
            'physical_publisher_owned': False,
            'publication_sequence': record['publication_sequence'],
            'publication_recorded_at': record.get('publication_recorded_at'),
            'order_provenance': order,
            'observed_catalog_record_sha256': protection.digest(record),
            'recorded_device': record['device'], 'observed_device': s.st_dev,
            'recorded_inode': record['inode'], 'observed_inode': s.st_ino,
            'complete_sha256': record['complete_sha256'],
            'inventory_sha256': record['inventory_sha256']}


def require_capacity_rotation(path: Path, *, purpose: str = 'CAPACITY') -> dict:
    """Authorize exactly the oldest physical copy under canonical Owner policy.

    Legacy birthtime is an observed ordering input, never a publisher claim.
    This grants no semantic withdrawal or Proposal status change.
    """
    try:
        from scripts import candidate_retention as retention
        from scripts.candidate_archive import _identity
    except ModuleNotFoundError:
        import candidate_retention as retention
        from candidate_archive import _identity
    if purpose not in ('INTEGRITY', 'CAPACITY'):
        raise ValueError('unknown archive operation purpose')
    capacity = purpose == 'CAPACITY'
    registry, audit = (_snapshot(for_deletion=True, purpose=purpose) if capacity
                       else _snapshot(for_deletion=True))
    policy = audit['canonical'].get('rotation_policy') or {}
    if (policy.get('rotation_strategy') != 'OLDEST_FULL_COPY_FIRST'
            or policy.get('status') != 'PRODUCT_OWNER_AUTHORIZED_ACTIVE'):
        raise ValueError('canonical Owner capacity-rotation policy is unavailable')
    if audit['full_copies'] != policy['max_full_copies']:
        raise ValueError('capacity rotation requires exactly eight physical copies')
    base = Path.home() / 'Library/Application Support/Integra'
    target = path.resolve(strict=True)
    try:
        relative = target.relative_to(base).as_posix()
    except ValueError as error:
        raise ValueError('rotation target is outside managed authority') from error
    entries = audit['entries']
    if any(not all(row.get(key) for key in protection.IDENTITY) for row in entries):
        raise ValueError('rotation order contains an unidentified physical copy')
    ordered = []
    publisher_order_evidence = {}
    for row in entries:
        record = row.get('catalog_record') or {}
        sequence = record.get('publication_sequence')
        if sequence is not None and (type(sequence) is not int or sequence <= 0):
            raise ValueError('publisher sequence record is invalid')
        if sequence is not None and not row.get('publisher_owned'):
            evidence = (_observed_publisher_order_evidence(
                Path(row['absolute_path']), record,
                {key: row[key] for key in protection.IDENTITY})
                if row.get('identity_metadata_verified' if capacity else 'integrity_verified') is True and row.get('metadata_error') is None
                else None)
            if evidence is None:
                raise ValueError('publisher order is not bound to verified archive bytes')
            publisher_order_evidence[row['path']] = evidence
        order = retention._rotation_order(Path(row['absolute_path']), row.get('catalog_record'))
        if order is None:
            raise ValueError('rotation order is unproven for a physical copy')
        row['capacity_rotation_order'] = order
        ordered.append(row)
    catalog_path = retention.catalog_path(base / 'Build Archive')
    local_catalog = json.loads(catalog_path.read_bytes()) if catalog_path.exists() else {}
    if local_catalog and (local_catalog.get('artifact_type') != 'integra.owned_archive_catalog'
                          or local_catalog.get('owner_uid') != os.getuid()):
        raise ValueError('rotation order catalog ownership differs')
    if local_catalog.get('publication_timestamp_order_conflict'):
        raise ValueError('new publication clock order conflicts with publisher sequence')
    persisted_order = local_catalog.get('rotation_order_v2')
    prior_rotated = protection.load_rotation_receipts(base, policy, purpose=purpose)
    retired_paths = retention._retired_rotation_sources(local_catalog, policy['sha256'])
    if persisted_order:
        ordered = retention._ordered_rotation_rows(
            ordered, persisted_order, policy['sha256'], retired_paths, policy['max_full_copies'], purpose=purpose)
        initial_order = persisted_order
    else:
        initial_order = retention._initial_rotation_order(
            ordered, policy['sha256'], datetime.now(timezone.utc).isoformat(),
            policy['max_full_copies'])
        ordered = retention._ordered_rotation_rows(
            ordered, initial_order, policy['sha256'], {}, policy['max_full_copies'])
    protected_paths = {path for path in registry['selected_survivors'].values() if path is not None}
    first = next((row for row in ordered if row['path'] not in protected_paths), None)
    if first is None:
        raise ValueError('capacity rotation has no unprotected physical copy')
    if first['path'] != relative:
        raise ValueError('rotation target is not the oldest physical copy')
    row = first
    identity = _rotation_package_metadata(target)['identity'] if capacity else _identity(target / 'Integra.app')
    if any(identity[key] != row[key] for key in protection.IDENTITY):
        raise ValueError('oldest copy app bytes differ from manifest identity')
    expected_selected = registry['selected_survivors']
    # Retain the open Proposal reference without changing its review state.
    proposal_refs = sorted(f'PR #{number}' for number, proposal in protection.fetch_canonical(registry)[1].items()
                           if proposal.get('candidate', {}).get('candidate_id') == identity['candidate_id'])
    survivors = {}
    for cid, selected in expected_selected.items():
        if selected is None or selected == relative or cid in audit.get('rotated_unavailable', {}):
            continue
        receipt = base / selected / 'COMPLETE.json'
        survivors[cid] = {'path': selected, 'receipt_sha256': protection.sha(receipt.read_bytes())}
    physical_survivors = {}
    for other in entries:
        if other['path'] == relative:
            continue
        verifier = _rotation_package_metadata if capacity else _rotation_package_attestation
        physical_survivors[other['path']] = verifier(
            Path(other['absolute_path']), {key: other[key] for key in protection.IDENTITY})
    lease = {'kind': 'OWNER_POLICY_CAPACITY_ROTATION',
            'registry_sha256': audit['registry_sha256'],
            'canonical_sha256': protection.digest(audit['canonical']),
            'policy_sha256': policy['sha256'], 'policy_authority_ref': policy['authority_ref'],
            'path': relative, 'identity': identity, 'order': first['capacity_rotation_order'],
            'owner_uid': target.stat().st_uid, 'device': target.stat().st_dev,
            'inode': target.stat().st_ino, 'birthtime': getattr(target.stat(), 'st_birthtime', None),
            'selected_survivors': expected_selected, 'survivors': survivors,
            'physical_survivors': physical_survivors,
            'initial_order': initial_order,
            'prior_rotated': prior_rotated,
            'publisher_order_evidence': publisher_order_evidence,
            'proposal_refs': proposal_refs,
            'protected_identities': {cid: value['identity'] for cid, value in audit['protected_identities'].items()}}
    if capacity:
        lease['verification_purpose'] = 'CAPACITY'
    return lease


def require_capacity_rotation_continuation(lease: dict, *, full: bool = True) -> dict | None:
    """Check the lease cheaply during unlink; rehash before completion.

    The full check remains mandatory before an interrupted operation resumes
    and before a completed retirement is recorded. Fast checks never grant a
    new rotation: only require_capacity_rotation can create the lease.
    """
    if not isinstance(lease, dict) or lease.get('kind') != 'OWNER_POLICY_CAPACITY_ROTATION':
        raise ValueError('capacity-rotation lease is missing')
    raw = protection.REGISTRY.read_bytes()
    if protection.sha(raw) != lease.get('registry_sha256'):
        raise ValueError('rotation registry changed')
    registry = json.loads(raw)
    if registry.get('selected_survivors') != lease.get('selected_survivors'):
        raise ValueError('rotation survivor selection changed')
    base = Path.home() / 'Library/Application Support/Integra'
    try:
        from scripts import candidate_retention as retention
    except ModuleNotFoundError:
        import candidate_retention as retention
    catalog_path = retention.catalog_path(base / 'Build Archive')
    local_catalog = json.loads(catalog_path.read_bytes())
    if local_catalog.get('rotation_order_v2') != lease.get('initial_order'):
        raise ValueError('persisted initial rotation order changed')
    for relative, evidence in lease.get('publisher_order_evidence', {}).items():
        record = local_catalog.get('artifacts', {}).get(str(base / relative))
        if not isinstance(record, dict) or protection.digest(record) != evidence.get(
                'observed_catalog_record_sha256'):
            raise ValueError('pre-amendment publisher order record changed')
    for cid, expected in lease.get('survivors', {}).items():
        selected = registry['selected_survivors'].get(cid)
        if selected != expected['path']:
            raise ValueError('rotation survivor selection changed')
        receipt = base / selected / 'COMPLETE.json'
        if protection.sha(receipt.read_bytes()) != expected['receipt_sha256']:
            raise ValueError('rotation survivor receipt changed')
    physical_survivors = lease.get('physical_survivors')
    if not isinstance(physical_survivors, dict):
        raise ValueError('rotation physical-survivor attestations are missing')
    for relative, expected in physical_survivors.items():
        if (not isinstance(relative, str) or Path(relative).is_absolute()
                or '..' in Path(relative).parts
                or not any(relative == root or relative.startswith(root + '/')
                           for root in registry['managed_roots'])):
            raise ValueError('rotation physical-survivor path is outside managed authority')
        if not _fast_rotation_package_anchor(base / relative, expected):
            raise ValueError('rotation physical survivor changed: ' + relative)
    if not full:
        return
    current, proposals, canonical = protection.fetch_canonical(registry)
    policy = canonical.get('rotation_policy') or {}
    if (policy.get('sha256') != lease.get('policy_sha256')
            or policy.get('authority_ref') != lease.get('policy_authority_ref')
            or protection.digest(canonical) != lease.get('canonical_sha256')):
        raise ValueError('rotation canonical authority changed')
    blockers = []
    gaps = protection._accepted_historical_gaps(registry, canonical, blockers)
    protected = protection._validate_registry(registry, current, proposals, blockers, gaps, canonical)
    if (blockers or {cid: role['identity'] for cid, role in protected.items()}
            != lease.get('protected_identities')):
        raise ValueError('rotation protection graph changed')
    capacity = lease.get('verification_purpose') == 'CAPACITY'
    if protection.load_rotation_receipts(base, policy, purpose='CAPACITY' if capacity else 'INTEGRITY') != lease.get('prior_rotated'):
        raise ValueError('prior physical-retirement receipts changed')
    if not capacity:
        for cid, expected in lease.get('survivors', {}).items():
            protection.verify_archive(base / expected['path'], protected[cid]['identity'])
    upgraded = {}
    for relative, expected in physical_survivors.items():
        verifier = _rotation_package_metadata if capacity else _rotation_package_attestation
        fresh = verifier(base / relative, expected['identity'])
        if any(fresh.get(key) != value for key, value in expected.items()):
            raise ValueError('rotation physical survivor bytes changed: ' + relative)
        upgraded[relative] = fresh
    return {**lease, 'physical_survivors': upgraded}


def _fast_rotation_package_anchor(package: Path, expected: dict) -> bool:
    """Compare owner/inode and small immutable metadata between full proofs."""
    if not {'metadata_anchors', 'manifest_sha256', 'complete_sha256'} <= set(expected):
        # Journals from the earlier executor remain recoverable under its full
        # verifier; never weaken a legacy lease by omitting an anchor.
        return _rotation_package_attestation(package, expected['identity']) == expected
    if package.is_symlink():
        return False
    root = package.lstat()
    if (not stat.S_ISDIR(root.st_mode) or root.st_uid != os.getuid()
            or (root.st_dev, root.st_ino, getattr(root, 'st_birthtime', None)) !=
               (expected['device'], expected['inode'], expected['birthtime'])):
        return False
    manifest = package / 'Integra.app/Contents/Resources/candidate-manifest.json'
    if (_file_anchor(manifest) != expected['metadata_anchors'].get('manifest')
            or protection.sha(manifest.read_bytes()) != expected['manifest_sha256']):
        return False
    for name, key in (('COMPLETE.json', 'complete'),
                      ('inventory.json', 'inventory')):
        path = package / name
        anchor = _file_anchor(path) if path.exists() else None
        if anchor != expected['metadata_anchors'].get(key):
            return False
    complete = package / 'COMPLETE.json'
    if (protection.sha(complete.read_bytes()) if complete.exists() else None) != expected['complete_sha256']:
        return False
    return True


def _file_anchor(path: Path) -> dict:
    s = path.lstat()
    if not stat.S_ISREG(s.st_mode) or s.st_uid != os.getuid() or s.st_nlink != 1:
        raise ValueError('rotation metadata file owner or type changed')
    return {'device': s.st_dev, 'inode': s.st_ino, 'owner_uid': s.st_uid,
            'mode': stat.S_IMODE(s.st_mode), 'size': s.st_size,
            'mtime_ns': s.st_mtime_ns, 'ctime_ns': s.st_ctime_ns}


def _rotation_package_metadata(package: Path, identity: dict | None = None) -> dict:
    """Bind disposable package identity, not restoration eligibility.

    Original inventory/COMPLETE remain immutable provenance. Payload contents
    are deliberately not certified here; the executor snapshots the selected
    target separately before its guarded deletion transaction.
    """
    try:
        from scripts import candidate_archive as archive
    except ModuleNotFoundError:
        import candidate_archive as archive
    package = archive._path(package, durable=True)
    root = package.lstat()
    if not stat.S_ISDIR(root.st_mode) or root.st_uid != os.getuid():
        raise ValueError('rotation package root ownership differs')
    if (package / '.git').exists():
        raise ValueError('rotation package is a worktree')
    manifest = archive._path(package / 'Integra.app' / archive.EMBEDDED)
    manifest_anchor = _file_anchor(manifest)
    raw = manifest.read_bytes()
    value = json.loads(raw)
    archive.validate_manifest(value)
    actual = {'candidate_id': value['candidate_id'], 'bundle_digest': value['bundle']['digest'],
              'manifest_digest': protection.sha(raw)}
    if identity is not None and actual != identity:
        raise ValueError('rotation manifest identity differs')
    complete = package / 'COMPLETE.json'
    inventory = package / 'inventory.json'
    if complete.exists() != inventory.exists():
        raise ValueError('rotation package has partial archive metadata')
    complete_hash = inventory_hash = None
    anchors = {'manifest': manifest_anchor, 'complete': None, 'inventory': None}
    if complete.exists():
        for key, path in (('complete', complete), ('inventory', inventory)):
            archive._path(path)
            anchors[key] = _file_anchor(path)
        complete_raw, inventory_raw = complete.read_bytes(), inventory.read_bytes()
        receipt, entries = json.loads(complete_raw), json.loads(inventory_raw)
        complete_hash, inventory_hash = protection.sha(complete_raw), protection.sha(inventory_raw)
        if (receipt.get('status') != 'COMPLETE'
                or any(receipt.get(key) != actual[key] for key in protection.IDENTITY)
                or receipt.get('inventory_sha256') != inventory_hash
                or not isinstance(entries, list)
                or package.name != actual['bundle_digest']
                or package.parent.name != actual['candidate_id']):
            raise ValueError('rotation original receipt identity/inventory differs')
        retained = archive._path(package / archive.MANIFEST_NAME)
        _file_anchor(retained)
        if retained.read_bytes() != raw:
            raise ValueError('rotation retained manifest differs')
    return {'identity': actual, 'device': root.st_dev, 'inode': root.st_ino,
            'birthtime': getattr(root, 'st_birthtime', None),
            'inventory_sha256': inventory_hash,
            'archive_kind': 'COMPLETE' if complete.exists() else 'UNARCHIVED',
            'manifest_sha256': actual['manifest_digest'], 'complete_sha256': complete_hash,
            'metadata_anchors': anchors}


def _rotation_package_attestation(package: Path, identity: dict) -> dict:
    """Rehash every surviving physical copy, including legacy unarchived builds."""
    try:
        from scripts.candidate_archive import _identity, _inventory, verify_archive
    except ModuleNotFoundError:
        from candidate_archive import _identity, _inventory, verify_archive
    if package.is_symlink():
        raise ValueError('rotation survivor path is a symlink')
    root = package.lstat()
    if not stat.S_ISDIR(root.st_mode) or root.st_uid != os.getuid():
        raise ValueError('rotation survivor root ownership differs')
    if _identity(package / 'Integra.app') != identity:
        raise ValueError('rotation survivor app identity differs')
    inventory = _inventory(package)
    for item in inventory:
        entry = (package / item['path']).lstat()
        if entry.st_uid != os.getuid() or (item['type'] == 'file' and entry.st_nlink != 1):
            raise ValueError('rotation survivor contains foreign or linked bytes')
    has_inventory = (package / 'inventory.json').exists()
    has_complete = (package / 'COMPLETE.json').exists()
    if has_inventory != has_complete:
        raise ValueError('rotation survivor has partial archive metadata')
    if has_complete:
        verify_archive(package, identity)
    return {'identity': identity, 'device': root.st_dev, 'inode': root.st_ino,
            'birthtime': getattr(root, 'st_birthtime', None),
            'inventory_sha256': protection.digest(inventory),
            'archive_kind': 'COMPLETE' if has_complete else 'UNARCHIVED',
            'manifest_sha256': protection.sha(
                (package / 'Integra.app/Contents/Resources/candidate-manifest.json').read_bytes()),
            'complete_sha256': protection.sha((package / 'COMPLETE.json').read_bytes())
            if has_complete else None,
            'metadata_anchors': {
                'manifest': _file_anchor(
                    package / 'Integra.app/Contents/Resources/candidate-manifest.json'),
                'complete': _file_anchor(package / 'COMPLETE.json') if has_complete else None,
                'inventory': _file_anchor(package / 'inventory.json') if has_inventory else None}}
