"""Durable, resumable physical retirement of exact managed full copies."""
import base64
import json
import os
from pathlib import Path
import stat
import time
import uuid
from datetime import datetime, timezone

try:
    from scripts import candidate_protection_gate as canonical_gate
except ModuleNotFoundError:
    import candidate_protection_gate as canonical_gate

try:
    from scripts import candidate_lifecycle as lifecycle
except ModuleNotFoundError:
    import candidate_lifecycle as lifecycle

UNLINK_DEADLINE_SECONDS = 900


def _retirement_checkpoint(r, path, catalog, job, *, completed=False, error=None):
    receipt = job.get('retirement_receipt')
    if receipt is None:
        return  # Historical pre-repair journals retain their original evidence.
    receipt = lifecycle.update_retirement(receipt, source=job['source'],
                                         trash=job['trash'], completed=completed,
                                         error=error)
    if job.get('kind') == 'CAPACITY_ROTATION' and not Path(job['source']).exists():
        # A renamed or partly unlinked payload is not available at its
        # identity-bound archive path, even while recovery can still resume.
        receipt['physical_available'] = False
    job['retirement_receipt'] = receipt
    catalog.setdefault('retirements', {})[receipt['transaction_id']] = receipt
    r._persist(path, catalog)


def _prepare_receipt(r, catalog, job, manifest, verification):
    context = catalog.get('protection') or {}
    record = lifecycle.replay(job['record'], context.get('canonical_lifecycles', {}),
                              context.get('protected', {}).get(job['identity']['candidate_id'], []))
    # A separately verified withdrawal is terminal lifecycle evidence, not a
    # promotion.  Protection planning and the deletion gate already replay it;
    # the physical-retirement receipt must use that same canonical evidence.
    # Without this replay an otherwise authorized withdrawal reaches cleanup as
    # a stale pending record and fails after the costly immutable-byte check.
    record = lifecycle.replay_withdrawal(
        record, context.get('withdrawn_candidate_lifecycles', []))
    policy = context.get('standing_policy') or {}
    eligibility = lifecycle.terminal_eligibility(
        job['identity'], record, context.get('protected', {}).get(record['candidate_id'], []),
        owned=True, integrity_verified=True, context_valid=r._context_valid(context),
        inactive=not r._publisher_live(record) and r._inactive(Path(job['source'])),
        standing_policy=policy)
    if (eligibility['eligible']
            and lifecycle.evidence_matches(job['identity'],
                                           record.get('lifecycle_evidence'))):
        return lifecycle.prepare_retirement(
            job['identity'], record, manifest, verification,
            transaction_id=job['transaction_id'],
            canonical_snapshot=context['canonical_snapshot'], policy=policy)
    # Keep the existing exact Candidate-specific authorization path compatible;
    # it does not acquire standing policy merely because a receipt is created.
    if record.get('status') not in r.TERMINAL or not record.get('disposition_ref'):
        raise ValueError('retirement standing eligibility or exact disposition is unproven')
    return {'schema_version': '1.0',
            'artifact_type': 'integra.candidate_physical_retirement',
            **job['identity'], 'source': manifest.get('identity', {}).get('source', manifest.get('source')),
            'retained_manifest': manifest,
            'publisher_attestation': record,
            'complete_sha256': record['complete_sha256'],
            'inventory_sha256': record['inventory_sha256'],
            'lifecycle_before_retirement': record['status'],
            'proposal_refs': [], 'acceptance_refs': [], 'promotion_refs': [],
            'verification_evidence': verification,
            'reason': 'EXACT_CANDIDATE_SPECIFIC_DISPOSITION',
            'policy_authority_ref': record['disposition_ref'],
            'transaction_id': job['transaction_id'],
            'canonical_snapshot': job['canonical_deletion_lease'],
            'timestamp': time.time(), 'state': 'PREPARED',
            'execution_result': 'NOT_EXECUTED', 'physical_available': True}


def _entries(r, package, *, observed_inventory=None):
    expected = (observed_inventory if observed_inventory is not None else
                json.loads((package / 'inventory.json').read_text()))
    expected = [dict(item) for item in expected]
    if observed_inventory is None:
        for name in ('inventory.json', 'COMPLETE.json'):
            p = package / name; s = p.stat()
            expected.append({'path': name, 'type': 'file', 'mode': stat.S_IMODE(s.st_mode),
                             'size': s.st_size, 'sha256': r._sha(p)})
    for entry in expected:
        s = (package / entry['path']).lstat()
        entry['device'], entry['inode'] = s.st_dev, s.st_ino
        if entry['type'] == 'file':
            entry['mtime_ns'], entry['ctime_ns'] = s.st_mtime_ns, s.st_ctime_ns
    return expected


def _remaining(r, package, job, *, hash_bytes):
    """Missing entries after DELETING are expected; extra/replaced bytes are not."""
    expected = {e['path']: e for e in job['entries']}
    found = set()
    for directory, dirs, files in os.walk(package, followlinks=False,
                                          onerror=lambda e: (_ for _ in ()).throw(e)):
        for name in dirs + files:
            p = Path(directory) / name; relative = p.relative_to(package).as_posix()
            e = expected.get(relative); s = p.lstat()
            typ = 'file' if stat.S_ISREG(s.st_mode) else 'directory' if stat.S_ISDIR(s.st_mode) else 'other'
            if not e or (s.st_dev, s.st_ino) != (e['device'], e['inode']) or s.st_uid != os.getuid() or typ != e['type'] or stat.S_IMODE(s.st_mode) != e['mode']:
                raise ValueError('cleanup journal contains foreign/replaced/unrecorded entry')
            if typ == 'file' and (s.st_nlink != 1 or s.st_size != e['size'] or (hash_bytes and r._sha(p) != e['sha256'])):
                raise ValueError('cleanup journal remaining bytes changed')
            found.add(relative)
    if job['phase'] == 'PREPARED' and found != set(expected):
        raise ValueError('prepared package differs from verified complete inventory')
    return [expected[p] for p in found]


def _parent_fd(package, relative, expected, job):
    fd = os.open(package, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        root = os.fstat(fd)
        if (root.st_dev, root.st_ino) != (job['device'], job['inode']) or root.st_uid != os.getuid():
            raise ValueError('cleanup root directory identity changed')
        parts = Path(relative).parts
        for i, part in enumerate(parts[:-1]):
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd); fd = child
            e = expected['/'.join(parts[:i + 1])]; s = os.fstat(fd)
            if s.st_uid != os.getuid() or (s.st_dev, s.st_ino) != (e['device'], e['inode']):
                raise ValueError('cleanup directory identity changed')
        return fd, parts[-1]
    except BaseException:
        os.close(fd); raise


def _guard(r, catalog, job, package, *, transaction=False, full_rotation=False):
    rotation = job.get('kind') == 'CAPACITY_ROTATION'
    if rotation:
        if full_rotation and package == Path(job['source']):
            if canonical_gate.require_capacity_rotation(package) != job.get('canonical_deletion_lease'):
                raise ValueError('canonical rotation decision changed before withdrawal')
        else:
            canonical_gate.require_capacity_rotation_continuation(
                job.get('canonical_deletion_lease'), full=full_rotation)
    elif package == Path(job['source']):
        if canonical_gate.require_deletion(package) != job.get('canonical_deletion_lease'):
            raise ValueError('canonical deletion decision changed before withdrawal')
    else:
        canonical_gate.require_deletion_continuation(job.get('canonical_deletion_lease'))
    context = catalog.get('protection') or {}
    cid = job['identity']['candidate_id']
    selected = context.get('selected_archives', {}).get(cid)
    # Canonical authorization is captured at the atomic package withdrawal
    # boundary and refreshed before every resumed transaction. Individual
    # entries belong to that same committed immutable package operation.
    context_valid = (r._digest(context) == job.get('transaction_context_sha256')
                     if transaction or rotation
                     else r._context_valid(context))
    if not context_valid or (not rotation and
            ((cid in context.get('protected', {}) and (not selected or selected in (job['source'], job['trash'])))
             or job['record'].get('pin_ref'))):
        raise ValueError('cleanup protection authority changed or is unavailable')
    s = r._safe(package).lstat()
    if (s.st_dev, s.st_ino) != (job['device'], job['inode']) or s.st_uid != os.getuid() or not stat.S_ISDIR(s.st_mode) or r._publisher_live(job['record']) or not r._inactive(package):
        raise ValueError('cleanup owner/identity/activity changed')
    if rotation and getattr(s, 'st_birthtime', None) != job.get('birthtime'):
        raise ValueError('rotation target birthtime changed')


def _finish_container(catalog, job):
    """Idempotent exact empty-parent cleanup, including post-unlink recovery."""
    parent = Path(job['source']).parent
    if (parent.name != job['identity']['candidate_id']
            or str(parent.parent) not in catalog['roots'] or not parent.exists()):
        return
    if parent.is_symlink() or parent.lstat().st_uid != os.getuid():
        raise ValueError('Candidate container ownership changed')
    try:
        parent.rmdir()
    except OSError:
        pass  # Other bundles/evidence remain; never recurse on the parent.


def _complete_job(r, path, catalog, job, token):
    _finish_container(catalog, job)
    _retirement_checkpoint(r, path, catalog, job, completed=True)
    catalog['artifacts'].pop(job['source'], None)
    del catalog['deletions'][token]; r._persist(path, catalog)
    return job['source']


def _execute_payload(r, path, catalog, token):
    job = catalog['deletions'][token]
    source, trash = Path(job['source']), Path(job['trash'])
    if source.exists() and trash.exists():
        raise ValueError('cleanup source/trash collision; recovery requires review')
    package = source if source.exists() else trash
    if not package.exists():
        if job['phase'] != 'FINAL_UNLINK_READY':
            raise ValueError('cleanup package disappeared without final-unlink proof')
        if job.get('kind') == 'CAPACITY_ROTATION':
            canonical_gate.require_capacity_rotation_continuation(job.get('canonical_deletion_lease'))
        elif not r._context_valid(catalog.get('protection')):
            raise ValueError('cleanup recovery protection context is unavailable')
        if job.get('kind') != 'CAPACITY_ROTATION':
            canonical_gate.require_deletion_continuation(job.get('canonical_deletion_lease'))
        return _complete_job(r, path, catalog, job, token)
    _guard(r, catalog, job, package)
    entries = _remaining(r, package, job, hash_bytes=True)
    if job['phase'] == 'FINAL_UNLINK_READY':
        if package != trash or entries:
            raise ValueError('final-unlink checkpoint has remaining or moved bytes')
        _guard(r, catalog, job, trash, transaction=True,
               full_rotation=job.get('kind') == 'CAPACITY_ROTATION')
        os.rmdir(trash)
        return _complete_job(r, path, catalog, job, token)
    if package == source:
        try:
            from scripts.candidate_archive import _publish
        except ModuleNotFoundError:
            from candidate_archive import _publish
        _guard(r, catalog, job, source,
               full_rotation=job.get('kind') == 'CAPACITY_ROTATION')
        job['transaction_context_sha256'] = r._digest(catalog['protection'])
        r._persist(path, catalog)
        _publish(source, trash)
        fd = os.open(trash.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    job['transaction_context_sha256'] = r._digest(catalog['protection'])
    job['phase'] = 'DELETING'; r._persist(path, catalog)
    _retirement_checkpoint(r, path, catalog, job)
    expected = {e['path']: e for e in job['entries']}
    deadline = time.monotonic() + UNLINK_DEADLINE_SECONDS
    refresh = time.monotonic()
    for e in sorted(entries, key=lambda e: (e['type'] == 'directory', -len(Path(e['path']).parts))):
        if time.monotonic() > deadline:
            raise ValueError('bounded cleanup timed out; durable journal retained')
        if time.monotonic() >= refresh:
            _guard(r, catalog, job, trash, transaction=True); refresh = time.monotonic() + 5
        fd, name = _parent_fd(trash, e['path'], expected, job)
        try:
            s = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if (s.st_dev, s.st_ino) != (e['device'], e['inode']) or s.st_uid != os.getuid():
                raise ValueError('cleanup entry identity changed at unlink')
            typ = 'file' if stat.S_ISREG(s.st_mode) else 'directory' if stat.S_ISDIR(s.st_mode) else 'other'
            if typ != e['type'] or stat.S_IMODE(s.st_mode) != e['mode']:
                raise ValueError('cleanup entry shape changed at unlink')
            if typ == 'file' and (s.st_nlink != 1 or s.st_size != e['size'] or s.st_mtime_ns != e['mtime_ns'] or s.st_ctime_ns != e['ctime_ns']):
                raise ValueError('cleanup file changed after transaction verification')
            if e['type'] == 'directory':
                os.rmdir(name, dir_fd=fd)
            else:
                os.unlink(name, dir_fd=fd)
        finally:
            os.close(fd)
    # The expensive canonical and all-survivor byte proof runs once at the
    # completion boundary, outside the 900-second unlink-work deadline. A
    # failed proof leaves the durable journal PARTIAL and blocks admission.
    _guard(r, catalog, job, trash, transaction=True,
           full_rotation=job.get('kind') == 'CAPACITY_ROTATION')
    if _remaining(r, trash, job, hash_bytes=False):
        raise ValueError('cleanup final-unlink proof found remaining entries')
    job['phase'] = 'FINAL_UNLINK_READY'; r._persist(path, catalog)
    os.rmdir(trash)
    # Remove only the now-empty owned Candidate container. Otherwise repeated
    # promotion would still accumulate top-level candidate-v1-* directories.
    return _complete_job(r, path, catalog, job, token)


def _execute(r, path, catalog, token):
    try:
        return _execute_payload(r, path, catalog, token)
    except BaseException as error:
        job = catalog.get('deletions', {}).get(token)
        if job is not None:
            _retirement_checkpoint(r, path, catalog, job, error=error)
        raise


def recover(r, path, catalog):
    try:
        from scripts.candidate_archive import verify_archive
    except ModuleNotFoundError:
        from candidate_archive import verify_archive
    if catalog.get('deletions'):
        for job in catalog['deletions'].values():
            if job.get('kind') == 'CAPACITY_ROTATION':
                lease = job.get('canonical_deletion_lease')
                upgraded = canonical_gate.require_capacity_rotation_continuation(lease)
                if upgraded is not None and upgraded != lease:
                    # A pre-repair journal is fully reverified once, then
                    # gains cheap metadata anchors before resumable unlink.
                    job['canonical_deletion_lease'] = upgraded
                    receipt = job['retirement_receipt']
                    receipt['canonical_snapshot'] = upgraded
                    catalog.setdefault('retirements', {})[receipt['transaction_id']] = receipt
                    r._persist(path, catalog)
            else:
                canonical_gate.require_deletion_continuation(job.get('canonical_deletion_lease'))
        if not all(job.get('kind') == 'CAPACITY_ROTATION' for job in catalog['deletions'].values()) and not r._context_valid(catalog.get('protection')):
            raise ValueError('cleanup recovery protection context is unavailable')
        for receipt in catalog['protection']['verified_survivors'].values():
            if any(job.get('kind') == 'CAPACITY_ROTATION' and receipt['archive_path'] == job['source']
                   for job in catalog['deletions'].values()):
                continue
            verify_archive(Path(receipt['archive_path']), {k: receipt[k] for k in ('candidate_id', 'bundle_digest', 'manifest_digest')})
    return [_execute(r, path, catalog, token) for token in list(catalog.get('deletions', {}))]


def apply(r, path, expected_plan):
    try:
        from scripts.candidate_archive import verify_archive
    except ModuleNotFoundError:
        from candidate_archive import verify_archive
    deleted = []
    with r.locked(path) as catalog:
        if not catalog['roots'] or r._safe(path) != r._safe(r.catalog_path(catalog['roots'][0])):
            raise ValueError('cleanup requires the shared authoritative device catalog')
        if catalog.get('deletions'):
            raise ValueError('interrupted cleanup requires explicit recover before a new plan')
        snapshot = r.plan(catalog, free_bytes=expected_plan['EXPECTED_FREE_SPACE'] - expected_plan['DELETABLE_BYTES'])
        if snapshot['plan_sha256'] != expected_plan['plan_sha256'] or not snapshot['protection_context_valid']:
            raise ValueError('retention plan/protection changed; no deletion')
        for receipt in catalog['protection']['verified_survivors'].values():
            verify_archive(Path(receipt['archive_path']), {k: receipt[k] for k in ('candidate_id', 'bundle_digest', 'manifest_digest')})
        target = expected_plan.get('rotation_target')
        if not isinstance(target, dict):
            raise ValueError('cleanup requires one proven oldest eligible rotation target')
        targets = [e for e in snapshot['entries']
                   if e['classification'] == 'DELETABLE'
                   and all(e.get(key) == target.get(key) for key in
                           ('path', 'candidate_id', 'bundle_digest',
                            'manifest_digest', 'publication_sequence'))]
        if len(targets) != 1:
            raise ValueError('cleanup rotation target changed or is not eligible')
        verified_targets = {}
        for e in targets:
            canonical_gate.require_deletion(Path(e['path']))
            if e['historical'] and not e.get('standing_retirement_eligible'):
                raise ValueError('historical archive adoption/deletion requires separate Human Gate')
            package = r._safe(e['path'])
            if (package / '.git').exists() or not r._inactive(package):
                raise ValueError('active/worktree archive cannot be deleted')
            verified_targets[str(package)] = verify_archive(
                package, {k: e[k] for k in ('candidate_id', 'bundle_digest', 'manifest_digest')})
        for e in targets:
            package = r._safe(e['path']); token = uuid.uuid4().hex
            record = catalog['artifacts'][str(package)]
            if not r._ownership(package, record, json.loads((package / 'COMPLETE.json').read_text())):
                raise ValueError('publisher ownership changed')
            job = {'source': str(package), 'trash': str(package.parent / ('.retention-trash-' + token)),
                   'transaction_id': 'retirement-v1-' + token,
                   'phase': 'PREPARED', 'identity': {k: e[k] for k in ('candidate_id', 'bundle_digest', 'manifest_digest')},
                   'device': e['device'], 'inode': e['inode'], 'record': record,
                   'entries': _entries(r, package)}
            job['canonical_deletion_lease'] = canonical_gate.require_deletion(package)
            manifest = json.loads((package / 'Integra.app/Contents/Resources/candidate-manifest.json').read_text())
            verification = verified_targets[str(package)]
            job['retirement_receipt'] = _prepare_receipt(r, catalog, job, manifest, verification)
            captured = {e['path']: e for e in job['entries']}
            if captured['inventory.json']['sha256'] != record['inventory_sha256'] or captured['COMPLETE.json']['sha256'] != record['complete_sha256']:
                raise ValueError('cleanup journal metadata differs from publisher authority')
            _guard(r, catalog, job, package)
            catalog['deletions'][token] = job
            catalog.setdefault('retirements', {})[job['transaction_id']] = job['retirement_receipt']
            r._persist(path, catalog)
            deleted.append(_execute(r, path, catalog, token))
    return deleted


def apply_exact(r, path, identity):
    """Retire one owner-authorized withdrawn Candidate without rotation order.

    This is deliberately separate from oldest-first rotation: it accepts only
    an exact identity already admitted by the canonical deletion gate.
    """
    required = {'candidate_id', 'bundle_digest', 'manifest_digest'}
    if not isinstance(identity, dict) or set(identity) != required:
        raise ValueError('exact cleanup requires one complete Candidate identity')
    try:
        from scripts.candidate_archive import verify_archive
    except ModuleNotFoundError:
        from candidate_archive import verify_archive
    with r.locked(path) as catalog:
        if not catalog['roots'] or r._safe(path) != r._safe(r.catalog_path(catalog['roots'][0])):
            raise ValueError('cleanup requires the shared authoritative device catalog')
        if catalog.get('deletions'):
            raise ValueError('interrupted cleanup requires explicit recover before a new plan')
        candidates = []
        for package in r._packages(catalog):
            record = catalog['artifacts'].get(str(package))
            if record and all(record.get(key) == identity[key] for key in required):
                candidates.append(r._safe(package))
        if len(candidates) != 1:
            raise ValueError('exact cleanup Candidate is missing or ambiguous')
        package = candidates[0]
        lease = canonical_gate.require_deletion(package)
        verification = verify_archive(package, identity)
        record = catalog['artifacts'].get(str(package))
        if not r._ownership(package, record, json.loads((package / 'COMPLETE.json').read_text())):
            raise ValueError('publisher ownership changed')
        if record.get('status') != 'WITHDRAWN_SUPERSEDED' or not record.get('disposition_ref'):
            raise ValueError('exact cleanup requires replayed withdrawn lifecycle evidence')
        token = uuid.uuid4().hex
        job = {'source': str(package), 'trash': str(package.parent / ('.retention-trash-' + token)),
               'transaction_id': 'retirement-v1-' + token, 'phase': 'PREPARED',
               'identity': identity, 'device': package.stat().st_dev, 'inode': package.stat().st_ino,
               'record': record, 'entries': _entries(r, package),
               'canonical_deletion_lease': lease}
        manifest = json.loads((package / 'Integra.app/Contents/Resources/candidate-manifest.json').read_text())
        job['retirement_receipt'] = _prepare_receipt(r, catalog, job, manifest, verification)
        captured = {entry['path']: entry for entry in job['entries']}
        if (captured['inventory.json']['sha256'] != record['inventory_sha256']
                or captured['COMPLETE.json']['sha256'] != record['complete_sha256']):
            raise ValueError('cleanup journal metadata differs from publisher authority')
        _guard(r, catalog, job, package)
        catalog['deletions'][token] = job
        catalog.setdefault('retirements', {})[job['transaction_id']] = job['retirement_receipt']
        r._persist(path, catalog)
        return [_execute(r, path, catalog, token)]


def apply_capacity_rotation(r, path, expected_plan):
    """Retire one exact oldest copy using the existing durable cleanup journal.

    An unarchived legacy Candidate receives a fresh observed-now attestation;
    it is never represented as a historically completed publisher archive.
    """
    try:
        from scripts.candidate_archive import _identity, _inventory, verify_archive
    except ModuleNotFoundError:
        from candidate_archive import _identity, _inventory, verify_archive
    with r.locked(path) as catalog:
        if not catalog['roots'] or r._safe(path) != r._safe(r.catalog_path(catalog['roots'][0])):
            raise ValueError('rotation requires the shared authoritative device catalog')
        if catalog.get('deletions'):
            raise ValueError('interrupted rotation must recover before a new plan')
        snapshot = r.plan(catalog, free_bytes=expected_plan['EXPECTED_FREE_SPACE'] - expected_plan['DELETABLE_BYTES'],
                          _validated_context=True)
        target = snapshot.get('capacity_rotation_target')
        if (snapshot['plan_sha256'] != expected_plan.get('plan_sha256')
                or not snapshot['protection_context_valid'] or not isinstance(target, dict)
                or target != expected_plan.get('capacity_rotation_target')):
            raise ValueError('oldest-copy rotation plan or protection changed')
        package = r._safe(target['path'])
        lease = canonical_gate.require_capacity_rotation(package)
        if (lease['identity'] != {key: target[key] for key in ('candidate_id', 'bundle_digest', 'manifest_digest')}
                or lease['order'] != target['capacity_rotation_order']
                or (lease['device'], lease['inode']) != (target['device'], target['inode'])):
            raise ValueError('canonical oldest-copy lease differs from local plan')
        if catalog.get('rotation_order_v2') is None:
            catalog['rotation_order_v2'] = lease['initial_order']
            r._persist(path, catalog)
        elif catalog['rotation_order_v2'] != lease['initial_order']:
            raise ValueError('persisted initial order differs from canonical rotation lease')
        root_stat = package.lstat()
        if (root_stat.st_uid != os.getuid()
                or (root_stat.st_dev, root_stat.st_ino) != (target['device'], target['inode'])
                or getattr(root_stat, 'st_birthtime', None) != lease['birthtime']
                or (package / '.git').exists() or not r._inactive(package)):
            raise ValueError('rotation target ownership, birthtime, or inactivity changed')
        identity = _identity(package / 'Integra.app')
        if identity != lease['identity']:
            raise ValueError('rotation app bytes differ from exact manifest')
        inventory = _inventory(package)
        if not inventory:
            raise ValueError('rotation target inventory is empty')
        for item in inventory:
            stat_result = (package / item['path']).lstat()
            if stat_result.st_uid != os.getuid() or (item['type'] == 'file' and stat_result.st_nlink != 1):
                raise ValueError('rotation inventory contains foreign or linked bytes')
        provenance_files = {}
        provenance_total = 0
        for item in inventory:
            name = item['path']
            if (item['type'] != 'file' or name.startswith('Integra.app/')
                    or name in ('inventory.json', 'COMPLETE.json')):
                continue
            provenance_total += item['size']
            if provenance_total > 16 * 1024 * 1024:
                raise ValueError('rotation provenance exceeds bounded receipt capacity')
            data = (package / name).read_bytes()
            if len(data) != item['size'] or r._sha(package / name) != item['sha256']:
                raise ValueError('rotation provenance changed during capture')
            provenance_files[name] = base64.b64encode(data).decode('ascii')
        manifest_bytes = (package / 'Integra.app/Contents/Resources/candidate-manifest.json').read_bytes()
        manifest = json.loads(manifest_bytes)
        has_inventory = (package / 'inventory.json').exists()
        has_complete = (package / 'COMPLETE.json').exists()
        if has_inventory != has_complete:
            raise ValueError('rotation target has an incomplete archive receipt')
        original_inventory_bytes = (package / 'inventory.json').read_bytes() if has_inventory else None
        original_complete_bytes = (package / 'COMPLETE.json').read_bytes() if has_complete else None
        record = catalog['artifacts'].get(str(package))
        if has_complete:
            complete = json.loads(original_complete_bytes)
            publisher_bound = r._ownership(package, record, complete)
            if record is not None and not publisher_bound:
                raise ValueError('completed archive conflicts with publisher catalog ownership')
            verification = verify_archive(package, identity)
            archive_kind = ('PUBLISHER_BOUND_COMPLETE_ARCHIVE' if publisher_bound else
                            'LEGACY_COMPLETED_ARCHIVE_OBSERVED_NOW')
            entries = _entries(r, package)
            if record is None:
                record = {**identity, 'status': 'LEGACY_UNCONFIRMED', 'owner_uid': os.getuid()}
        else:
            if record is not None:
                raise ValueError('legacy unarchived Candidate conflicts with publisher catalog')
            verification = {'method': 'OBSERVED_NOW_FULL_APP_AND_PACKAGE_INVENTORY',
                            'app_bundle_digest': identity['bundle_digest'],
                            'manifest_digest': identity['manifest_digest'],
                            'inventory_sha256': r._digest(inventory),
                            'inventory_entries': len(inventory)}
            archive_kind = 'UNARCHIVED_CANDIDATE_BUILD'
            entries = _entries(r, package, observed_inventory=inventory)
            record = {**identity, 'status': 'LEGACY_UNCONFIRMED', 'owner_uid': os.getuid()}
        verification = {**verification, 'manifest_digest': identity['manifest_digest'],
                        'rotation_inventory_sha256': r._digest(inventory)}
        token = uuid.uuid4().hex
        receipt = {'schema_version': '2.0', 'artifact_type': 'integra.candidate_physical_retirement',
                   **identity, 'source': manifest['identity']['source'],
                   'retained_manifest': manifest,
                   'retained_manifest_base64': base64.b64encode(manifest_bytes).decode('ascii'),
                   'retained_inventory': inventory,
                   'retained_provenance_files_base64': provenance_files,
                   'retained_inventory_json_base64': (base64.b64encode(original_inventory_bytes).decode('ascii')
                                                      if original_inventory_bytes is not None else None),
                   'retained_complete_base64': (base64.b64encode(original_complete_bytes).decode('ascii')
                                                if original_complete_bytes is not None else None),
                   'publisher_attestation': catalog['artifacts'].get(str(package)),
                   'archive_kind': archive_kind,
                   'lifecycle_before_retirement': record['status'],
                   'proposal_refs': lease['proposal_refs'], 'verification_evidence': verification,
                   'reason': 'OWNER_POLICY_CAPACITY_ROTATION',
                   'policy_authority_ref': lease['policy_authority_ref'],
                   'policy_sha256': lease['policy_sha256'],
                   'physical_source_path': str(package),
                   'order_provenance': lease['order'],
                   'observed_at': datetime.now(timezone.utc).isoformat(),
                   'observed_owner_uid': root_stat.st_uid, 'observed_device': root_stat.st_dev,
                   'observed_inode': root_stat.st_ino,
                   'transaction_id': 'rotation-v2-' + token,
                   'canonical_snapshot': lease,
                   'state': 'PREPARED', 'execution_result': 'NOT_EXECUTED',
                   'physical_available': True}
        job = {'kind': 'CAPACITY_ROTATION', 'source': str(package),
               'trash': str(package.parent / ('.retention-trash-' + token)),
               'transaction_id': receipt['transaction_id'], 'phase': 'PREPARED',
               'identity': identity, 'device': root_stat.st_dev, 'inode': root_stat.st_ino,
               'birthtime': lease['birthtime'], 'record': record,
               'entries': entries, 'canonical_deletion_lease': lease,
               'retirement_receipt': receipt}
        job['transaction_context_sha256'] = r._digest(catalog['protection'])
        _guard(r, catalog, job, package)
        catalog['deletions'][token] = job
        catalog.setdefault('retirements', {})[receipt['transaction_id']] = receipt
        r._persist(path, catalog)
        return [_execute(r, path, catalog, token)]
