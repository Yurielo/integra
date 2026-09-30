#!/usr/bin/env python3
"""Owned Candidate retention. Plans are read-only; legacy adoption is gated."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import time
import uuid

try:
    from scripts import build_disk_admission as admission
except ModuleNotFoundError:
    import build_disk_admission as admission

ROOT = Path(__file__).resolve().parents[1]
MAX_COPIES = 8
MAX_BYTES = 20 * 1024**3
FREE_FLOOR = 15 * 1024**3
TERMINAL = {'COMPLETED', 'REJECTED', 'SUPERSEDED', 'UNUSED'}
PROTECTED = {'CURRENT', 'LATEST_ACCEPTED_BASELINE', 'CONFIRMED_ROLLBACK',
             'CONFIRMED_RECOVERY', 'AWAITING_OWNER_ACCEPTANCE', 'EXPLICIT_GOVERNANCE_PROVENANCE'}


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _safe(path):
    path = Path(path).expanduser().absolute()
    if '..' in path.parts or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('retention path must not traverse symlinks or parents')
    return path


def catalog_path(archive_root):
    _safe(archive_root)
    base = Path.home() / ('Library/Application Support/Integra/Retention' if sys.platform == 'darwin'
                          else '.local/state/integra/retention')
    return base / f'catalog-{os.getuid()}.json'


def managed_roots():
    base = Path.home() / 'Library/Application Support/Integra'
    return [base / name for name in ('Build Archive', 'Recovery Archive', 'Build Archive Recovery', 'Candidate Builds')]


def _empty():
    return {'schema_version': '1.0', 'artifact_type': 'integra.owned_archive_catalog',
            'owner_uid': os.getuid(), 'roots': [], 'artifacts': {}, 'leases': {},
            'protection': None, 'historical_adoptions': [], 'deletions': {}}


def _persist(path, value):
    """Durable checkpoints also survive exceptions and interrupted deletion."""
    from tempfile import mkstemp
    path = Path(path)
    descriptor, name = mkstemp(prefix=path.name + '.', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w') as handle:
            json.dump(value, handle, sort_keys=True)
            handle.flush(); os.fsync(handle.fileno())
        os.replace(name, path)
        descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        if Path(name).exists():
            Path(name).unlink()


@contextmanager
def locked(path):
    """Use the existing bounded file-lock primitive, with a separate catalog."""
    path = _safe(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.stat().st_uid != os.getuid():
        raise ValueError('catalog parent is foreign')
    # Do not monkeypatch a module/global lock selector across concurrent code.
    import fcntl
    fd = os.open(path.with_suffix('.lock'), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        if os.fstat(fd).st_uid != os.getuid():
            raise ValueError('catalog lock is foreign')
        end = time.monotonic() + 30
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= end:
                    raise ValueError('retention catalog lock timed out')
                time.sleep(.05)
        if path.exists() and (path.stat().st_uid != os.getuid() or path.is_symlink()):
            raise ValueError('catalog ownership is unproven')
        value = json.loads(path.read_text()) if path.exists() else _empty()
        if value.get('artifact_type') != 'integra.owned_archive_catalog' or value.get('owner_uid') != os.getuid():
            raise ValueError('catalog schema/ownership differs')
        for root in managed_roots():
            register_root(value, root)
        yield value
        _persist(path, value)
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN); os.close(fd)


def register_root(catalog, root):
    root = _safe(root)
    for other in catalog['roots']:
        a, b = root.resolve(), Path(other).resolve()
        if a != b and (a in b.parents or b in a.parents):
            raise ValueError('registered archive roots overlap')
    if str(root) not in catalog['roots']:
        catalog['roots'].append(str(root))


def _measure(path, seen):
    total = 0
    if not Path(path).exists():
        return 0
    s = Path(path).lstat()
    if (s.st_dev, s.st_ino) not in seen:
        seen.add((s.st_dev, s.st_ino)); total += s.st_blocks * 512
    for directory, dirs, files in os.walk(path, followlinks=False, onerror=lambda e: (_ for _ in ()).throw(e)):
        for name in dirs + files:
            p = Path(directory) / name
            s = p.lstat()
            if stat.S_ISLNK(s.st_mode) or not (stat.S_ISREG(s.st_mode) or stat.S_ISDIR(s.st_mode)):
                raise ValueError(f'unknown filesystem object in archive: {p}')
            if (s.st_dev, s.st_ino) not in seen:
                seen.add((s.st_dev, s.st_ino)); total += s.st_blocks * 512
    return total


def _packages(catalog):
    packages = []
    seen = set()
    for root in catalog['roots']:
        if not Path(root).exists():
            continue
        for directory, dirs, files in os.walk(_safe(root), followlinks=False):
            if 'Integra.app' in dirs:
                p = Path(directory); s = p.stat()
                if (s.st_dev, s.st_ino) not in seen:
                    seen.add((s.st_dev, s.st_ino)); packages.append(p)
                dirs.remove('Integra.app')
    return sorted(set(packages))


def _metadata(package):
    """Bound receipts and exact size/mode/file-set, without payload rehash."""
    try:
        inventory = json.loads((package / 'inventory.json').read_text())
        receipt = json.loads((package / 'COMPLETE.json').read_text())
        manifest = package / 'Integra.app/Contents/Resources/candidate-manifest.json'
        embedded = json.loads(manifest.read_text())
        identity = {'candidate_id': embedded['candidate_id'], 'bundle_digest': embedded['bundle']['digest'],
                    'manifest_digest': _sha(manifest)}
        if receipt.get('status') != 'COMPLETE' or receipt.get('inventory_sha256') != _sha(package / 'inventory.json') or any(receipt.get(k) != v for k, v in identity.items()):
            raise ValueError('receipt identity/inventory binding differs')
        expected = {e['path']: e for e in inventory}
        if len(expected) != len(inventory):
            raise ValueError('inventory has duplicate paths')
        actual = set()
        for directory, dirs, files in os.walk(package, followlinks=False, onerror=lambda e: (_ for _ in ()).throw(e)):
            for name in dirs + files:
                p = Path(directory) / name; rel = p.relative_to(package).as_posix()
                if rel in {'inventory.json', 'COMPLETE.json'}:
                    continue
                actual.add(rel); s = p.lstat(); e = expected.get(rel)
                typ = 'file' if stat.S_ISREG(s.st_mode) else 'directory' if stat.S_ISDIR(s.st_mode) else 'other'
                if s.st_uid != os.getuid() or not e or typ != e['type'] or stat.S_IMODE(s.st_mode) != e['mode'] or (typ == 'file' and (s.st_size != e['size'] or s.st_nlink != 1)):
                    raise ValueError(f'unrecorded/changed entry: {rel}')
        if actual != set(expected):
            raise ValueError('recorded archive entries are missing')
        return identity, receipt, None
    except (OSError, ValueError, KeyError, TypeError) as error:
        # A manifest may still identify a protected object, even with no receipt.
        try:
            m = json.loads((package / 'Integra.app/Contents/Resources/candidate-manifest.json').read_text())
            return {'candidate_id': m['candidate_id'], 'bundle_digest': m['bundle']['digest']}, None, str(error)
        except (OSError, ValueError, KeyError, TypeError):
            return {}, None, str(error)


def _ownership(package, record, receipt):
    if not record or not receipt:
        return False
    s = package.lstat()
    return (record.get('owner_uid') == s.st_uid == os.getuid()
            and record.get('device') == s.st_dev and record.get('inode') == s.st_ino
            and record.get('complete_sha256') == _sha(package / 'COMPLETE.json')
            and record.get('inventory_sha256') == receipt['inventory_sha256']
            and record.get('inventory_sha256') == _sha(package / 'inventory.json')
            and record.get('publisher_run_id')
            and all(record.get(k) == receipt.get(k) for k in ('candidate_id', 'bundle_digest', 'manifest_digest')))


def _context_valid(context):
    try:
        try:
            from scripts.retention_governance import validate_snapshot
        except ModuleNotFoundError:
            from retention_governance import validate_snapshot
        return bool(context and context.get('protected') and context.get('inputs')
                    and set(context['protected']) == set(context.get('selected_archives', {}))
                    and set(context['protected']) == set(context.get('verified_survivors', {}))
                    and all(_sha(p) == digest for p, digest in context['inputs'].items())
                    and validate_snapshot(context.get('authoritative_snapshot')))
    except (OSError, ValueError, ImportError, subprocess.SubprocessError):
        return False


def plan(catalog, *, free_bytes=None):
    seen = set(); before = sum(_measure(_safe(p), seen) for p in catalog['roots'])
    rows = []; context = catalog.get('protection'); valid = _context_valid(context); attributed = set()
    # Root/container metadata is attributed to UNKNOWN, once, not a package.
    for root in catalog['roots']:
        if Path(root).exists():
            s = Path(root).stat(); attributed.add((s.st_dev, s.st_ino))
    protected_ids = set((context or {}).get('protected', {}))
    complete_roots = all(str(_safe(p)) in catalog['roots'] for p in managed_roots())
    for package in _packages(catalog):
        identity, receipt, error = _metadata(package)
        record = catalog['artifacts'].get(str(package)); owned = _ownership(package, record, receipt)
        amount = _measure(package, attributed); status = (record or {}).get('status', 'LEGACY_UNCONFIRMED')
        cid = identity.get('candidate_id'); reasons = []
        selected = (context or {}).get('selected_archives', {}).get(cid)
        if cid in protected_ids and (not selected or selected == str(package) or (record or {}).get('pin_ref')):
            reasons += context['protected'][cid]
        if status == 'AWAITING_OWNER_ACCEPTANCE' and (not selected or selected == str(package)):
            reasons.append('AWAITING_OWNER_ACCEPTANCE')
        if (record or {}).get('pin_ref'):
            reasons.append('EXPLICIT_GOVERNANCE_PROVENANCE')
        if reasons:
            classification = 'PROTECTED'
        elif not valid or not complete_roots or error or not owned or status not in TERMINAL or _publisher_live(record) or not _inactive(package):
            classification = 'UNKNOWN'
        else:
            classification = 'DELETABLE'
        rows.append({'path': str(package), **identity, 'allocated_bytes': amount,
                     'classification': classification, 'protected_reasons': reasons,
                     'ownership': 'PUBLISHER_BOUND' if owned else 'LEGACY_OR_UNKNOWN_UNCONFIRMED',
                     'lifecycle': status, 'metadata_error': error, 'device': package.stat().st_dev,
                     'inode': package.stat().st_ino, 'historical': bool((record or {}).get('historical'))})
    survivors_valid = all(any(r.get('candidate_id') == cid and not r['metadata_error']
                                  and all(r.get(k) == context.get('verified_survivors', {}).get(cid, {}).get(k)
                                          for k in ('candidate_id', 'bundle_digest', 'manifest_digest'))
                                  and (not (context or {}).get('selected_archives', {}).get(cid)
                                       or r['path'] == context['selected_archives'][cid]) for r in rows)
                          for cid in protected_ids)
    valid = valid and complete_roots and survivors_valid
    if not valid:
        for r in rows:
            if r['classification'] == 'DELETABLE':
                r['classification'] = 'UNKNOWN'
    protected = sum(r['allocated_bytes'] for r in rows if r['classification'] == 'PROTECTED')
    deletable = sum(r['allocated_bytes'] for r in rows if r['classification'] == 'DELETABLE')
    unknown = before - protected - deletable
    if free_bytes is None:
        anchor = next((Path(p) for p in catalog['roots'] if Path(p).exists()), Path.home())
        free_bytes = shutil.disk_usage(anchor).free
    report = {'schema_version': '1.0', 'artifact_type': 'integra.retention_plan', 'dry_run': True,
              'BEFORE_BYTES': before, 'PROTECTED_BYTES': protected, 'DELETABLE_BYTES': deletable,
              'UNKNOWN_BYTES': unknown, 'EXPECTED_AFTER_BYTES': before - deletable,
              'EXPECTED_FREE_SPACE': free_bytes + deletable,
              'reclaim_estimate': 'ATTRIBUTED_BLOCKS; APFS_EXCLUSIVE_EXTENTS_NOT_PROVEN',
              'full_copies': len(rows), 'over_copy_cap': len(rows) > MAX_COPIES,
              'over_byte_cap': before > MAX_BYTES, 'protection_context_valid': valid,
              'catalog_sha256': _digest(catalog), 'entries': rows}
    report['plan_sha256'] = _digest(report)
    return report


def _recover_leases(catalog):
    """Reap only common-lifecycle stages; unresolved publications stay charged."""
    try:
        from scripts import temp_workspace_lifecycle as lifecycle
    except ModuleNotFoundError:
        import temp_workspace_lifecycle as lifecycle
    for token, lease in list(catalog['leases'].items()):
        if admission._live(lease):
            continue
        stage = lease.get('stage_root')
        destination = lease.get('destination')
        if destination and Path(destination).exists():
            # Only a destination inode journaled BEFORE no-replace publication
            # can be recovered as our publication. A collision is not ours.
            package = _safe(destination); s = package.stat()
            if (s.st_dev, s.st_ino) == tuple(lease.get('publication_inode', [])):
                try:
                    try:
                        from scripts.candidate_archive import verify_archive
                    except ModuleNotFoundError:
                        from candidate_archive import verify_archive
                    receipt = verify_archive(package, lease['identity'])
                    _record_publication(catalog, token, lease, receipt)
                    if stage and Path(stage).exists():
                        lifecycle.cleanup_workspace(stage, reason='PUBLISHED_STAGE_RECOVERY', allow_live_owner=False)
                except (OSError, ValueError, KeyError):
                    pass
                continue
            # A no-replace collision is foreign. Reap only our stage and
            # release its unused publication reservation below.
        if stage and Path(stage).exists():
            try:
                _, marker = lifecycle._load(stage)
                if marker['run_id'] != lease.get('stage_run_id'):
                    continue
                if not lifecycle.cleanup_workspace(stage, reason='RETENTION_STALE_STAGE', allow_live_owner=False):
                    continue
            except (OSError, ValueError, KeyError):
                continue
        if not stage:
            # No payload copy may start before bind_stage. Any unbound stage
            # contains only common ownership metadata; volume-ledger recovery
            # handles it, without holding an unused archive slot forever.
            for stale in admission.stale_workspaces(catalog['roots'][0]):
                try:
                    _, marker = lifecycle._load(stale)
                    owner = lease.get('stage_owner', lease)
                    if marker['owner']['pid'] == owner['pid'] and marker['owner']['start_token'] == owner['start_token']:
                        lifecycle.cleanup_workspace(stale, reason='UNBOUND_STAGE_RECOVERY', allow_live_owner=False)
                except (OSError, ValueError, KeyError):
                    continue
        del catalog['leases'][token]


def bind_stage(path, token, stage, marker):
    with locked(path) as catalog:
        lease = catalog['leases'][token]
        if not _lease_caller(lease):
            raise ValueError('stage reservation owner differs')
        lease.update(stage_root=str(stage), stage_run_id=marker['run_id'])


def bind_publication(path, token, payload):
    """Prepublication inode binding prevents adopting someone else's collision."""
    with locked(path) as catalog:
        lease = catalog['leases'][token]
        if not _lease_caller(lease) or str(_safe(payload).parent) != lease.get('stage_root'):
            raise ValueError('publication stage ownership differs')
        s = _safe(payload).stat()
        lease['publication_inode'] = [s.st_dev, s.st_ino]


def _record_publication(catalog, token, lease, receipt):
    package = _safe(receipt['archive_path']); s = package.stat()
    if (s.st_dev, s.st_ino) != tuple(lease.get('publication_inode', [])):
        raise ValueError('publication inode differs from prepublication journal')
    catalog['artifacts'][str(package)] = {
        **{k: receipt[k] for k in ('candidate_id', 'bundle_digest', 'manifest_digest', 'inventory_sha256')},
        'complete_sha256': _sha(package / 'COMPLETE.json'), 'owner_uid': os.getuid(),
        'device': s.st_dev, 'inode': s.st_ino, 'publisher_run_id': token,
        'publisher_pid': lease['pid'], 'publisher_start_token': lease['start_token'],
        'status': 'AWAITING_OWNER_ACCEPTANCE', 'historical': False}
    del catalog['leases'][token]


def _lease_caller(lease):
    return (lease.get('owner_uid') == os.getuid()
            and admission._start(lease['pid']) == lease['start_token']
            and (lease['pid'] == os.getpid() or lease.get('process_group') == os.getpgrp()))


def reserve_archive(root, allocated_bytes, *, destination=None, identity=None):
    """Reserve a publication slot before staging; never silently prune."""
    path = catalog_path(root)
    with locked(path) as catalog:
        register_root(catalog, root)
        _recover_leases(catalog)
        inherited = os.environ.get('INTEGRA_RETENTION_BUILD_LEASE')
        if inherited:
            lease = catalog['leases'].get(inherited)
            if not lease or not _lease_caller(lease) or lease.get('archive_root') != str(_safe(root)) or allocated_bytes > lease['expected_bytes']:
                raise ValueError('inherited build publication lease is unproven/insufficient')
            lease.update(destination=str(destination), identity=identity,
                         stage_owner={'pid': os.getpid(), 'start_token': admission._start(os.getpid())})
            return path, inherited
        # Charge existing unmanaged legacy bytes too. Unknown deletion ownership
        # must not make real archive occupancy disappear from caps.
        snapshot = plan(catalog)
        reserved = sum(r['expected_bytes'] for r in catalog['leases'].values())
        if snapshot['full_copies'] + sum(r.get('copies', 1) for r in catalog['leases'].values()) + 1 > MAX_COPIES or snapshot['BEFORE_BYTES'] + reserved + allocated_bytes > MAX_BYTES:
            raise ValueError('bounded archive cap exceeded; protected/legacy artifacts require a retention decision')
        token = uuid.uuid4().hex
        catalog['leases'][token] = {'pid': os.getpid(), 'start_token': admission._start(os.getpid()),
                                    'expected_bytes': allocated_bytes, 'owner_uid': os.getuid(),
                                    'destination': str(destination) if destination else None, 'identity': identity}
    return path, token


def reusable_archive(root, identity, planned):
    """Find an exact requested package, without importing legacy ownership."""
    try:
        from scripts.candidate_archive import verify_archive
    except ModuleNotFoundError:
        from candidate_archive import verify_archive
    with locked(catalog_path(root)) as catalog:
        register_root(catalog, root)
        for package in _packages(catalog):
            actual, _, error = _metadata(package)
            if error or actual != identity or json.loads((package / 'inventory.json').read_text()) != planned:
                continue
            try:
                return verify_archive(package, identity)
            except ValueError:
                continue
    return None


def finish_publication(path, token, receipt):
    package = _safe(receipt['archive_path']); s = package.stat()
    with locked(path) as catalog:
        lease = catalog['leases'][token]
        if not _lease_caller(lease) or str(package) != lease.get('destination') or any(receipt.get(k) != v for k, v in (lease.get('identity') or {}).items()):
            raise ValueError('publication owner/destination/identity differs from lease')
        actual, bound, error = _metadata(package)
        if error or bound != {k: v for k, v in receipt.items() if k != 'archive_path'} or actual != lease.get('identity'):
            raise ValueError('publication receipt differs from journaled fresh artifact')
        _record_publication(catalog, token, lease, receipt)


def cancel_publication(path, token):
    with locked(path) as catalog:
        r = catalog['leases'].get(token)
        if r and r.get('destination') and Path(r['destination']).exists() and tuple(r.get('publication_inode', [])) == (Path(r['destination']).stat().st_dev, Path(r['destination']).stat().st_ino):
            # Preserve a published but not yet ownership-attested package and
            # journal. It is never failure-cleaned as disposable staging.
            return
        if r and r['pid'] == os.getpid() and r['start_token'] == admission._start(os.getpid()):
            del catalog['leases'][token]


def build_preflight(root, expected_bytes, *, archive_copy=True):
    path = catalog_path(root)
    with locked(path) as catalog:
        register_root(catalog, root); _recover_leases(catalog); snapshot = plan(catalog)
        reserved = sum(r['expected_bytes'] for r in catalog['leases'].values())
        if snapshot['full_copies'] + sum(r.get('copies', 1) for r in catalog['leases'].values()) + int(archive_copy) > MAX_COPIES or snapshot['BEFORE_BYTES'] + reserved + (expected_bytes if archive_copy else 0) > MAX_BYTES:
            raise ValueError('build blocked by 8-copy / 20-GiB archive cap')
    # Existing atomic workspace admission remains authoritative at spawn.
    # Include copy peak and conservative live-workspace charging in preflight.
    with admission._ledger(root) as (anchor, records):
        live = sum(r['expected_bytes'] for r in records.values() if admission._live(r))
        budget = expected_bytes * (3 if archive_copy else 1)
        if shutil.disk_usage(anchor).free < FREE_FLOOR + budget + live:
            raise ValueError('full build blocked: 15-GiB reserve after planned peak/live reservations')
    return snapshot


def require_build_lease(root, *, output=None):
    token = os.environ.get('INTEGRA_RETENTION_BUILD_LEASE')
    with locked(catalog_path(root)) as catalog:
        lease = catalog['leases'].get(token)
        if not lease or not _lease_caller(lease) or lease.get('archive_root') != str(_safe(root)) or not lease.get('volume_reservation_id'):
            raise ValueError('full build requires atomic retention/disk admission; use build_macos_candidate.py')
        if output is not None:
            workspace = lease.get('workspace')
            if not workspace or _safe(workspace) not in _safe(output).parents:
                raise ValueError('full build output must be within its reserved owned workspace')
            try:
                from scripts.temp_workspace_lifecycle import _load
            except ModuleNotFoundError:
                from temp_workspace_lifecycle import _load
            _load(_safe(workspace))
            if (_safe(output) / 'Integra.app').exists():
                raise ValueError('full Candidate output must be fresh, never an existing archive or app')


@contextmanager
def reserved_build(root, expected_bytes, *, archive_copy):
    """Atomic slot + volume-peak lease immediately before the real builder."""
    path = catalog_path(root); token = None; volume = None; completed = False; workspace = None
    try:
        with locked(path) as catalog:
            register_root(catalog, root); _recover_leases(catalog); snapshot = plan(catalog)
            copies = int(archive_copy)
            if snapshot['full_copies'] + sum(r.get('copies', 1) for r in catalog['leases'].values()) + copies > MAX_COPIES or snapshot['BEFORE_BYTES'] + sum(r['expected_bytes'] for r in catalog['leases'].values()) + copies * expected_bytes > MAX_BYTES:
                raise ValueError('atomic build admission exceeds archive cap')
            # Keep the existing deliberately conservative charging of already
            # allocated workspace bytes. Extra headroom covers both common
            # workspace and archive-stage leases, rather than lowering reserve.
            budget = expected_bytes * (3 if archive_copy else 1)
            volume, _, _ = admission.reserve(root, budget, FREE_FLOOR + (3 * expected_bytes if archive_copy else 0))
            workspace = os.environ.get('INTEGRA_OWNED_WORKSPACE')
            admission.bind(root, volume, workspace=workspace, process_group=os.getpgrp())
            token = uuid.uuid4().hex
            catalog['leases'][token] = {'pid': os.getpid(), 'start_token': admission._start(os.getpid()),
                'owner_uid': os.getuid(), 'expected_bytes': expected_bytes if archive_copy else 0,
                'copies': copies, 'workspace': workspace, 'process_group': os.getpgrp(),
                'archive_root': str(_safe(root)), 'volume_reservation_id': volume}
        previous = os.environ.get('INTEGRA_RETENTION_BUILD_LEASE')
        os.environ['INTEGRA_RETENTION_BUILD_LEASE'] = token
        previous_root = os.environ.get('INTEGRA_RETENTION_ARCHIVE_ROOT')
        os.environ['INTEGRA_RETENTION_ARCHIVE_ROOT'] = str(_safe(root))
        try:
            yield
            completed = True
        finally:
            if previous is None:
                os.environ.pop('INTEGRA_RETENTION_BUILD_LEASE', None)
            else:
                os.environ['INTEGRA_RETENTION_BUILD_LEASE'] = previous
            if previous_root is None:
                os.environ.pop('INTEGRA_RETENTION_ARCHIVE_ROOT', None)
            else:
                os.environ['INTEGRA_RETENTION_ARCHIVE_ROOT'] = previous_root
    finally:
        # On interrupted/failing builders keep the peak and slot charged until
        # the common supervisor proves group termination and removes its root.
        release_safe = completed or not workspace or not Path(workspace).exists()
        if token and release_safe:
            cancel_publication(path, token)
        if volume and release_safe:
            admission.release(root, volume)


def sync_protection(catalog, current_path, proposals, rollback_archive, recovery_archive,
                    pins=None, *, recovery_authority=None, selected_archives=None):
    """Require fresh canonical CURRENT/open proposals and confirmed durable roles."""
    try:
        from scripts.candidate_archive import verify_archive
        from scripts.retention_governance import capture_protection
    except ModuleNotFoundError:
        from candidate_archive import verify_archive
        from retention_governance import capture_protection
    rollback = verify_archive(_safe(rollback_archive)); recovery = verify_archive(_safe(recovery_archive))
    context = capture_protection(_safe(current_path), proposals, rollback, recovery, recovery_authority, pins)
    selected = dict(selected_archives or {})
    selected[rollback['candidate_id']] = rollback['archive_path']
    selected[recovery['candidate_id']] = recovery['archive_path']
    verified = {}
    for cid, name in selected.items():
        if cid not in context['protected']:
            raise ValueError('selected survivor has no protected role')
        package = _safe(name)
        if not any(package == root or root in package.parents for root in map(_safe, catalog['roots'])):
            raise ValueError('protected survivor is outside the managed roots')
        receipt = verify_archive(package, {'candidate_id': cid})
        for identity in context['protected_identities'].get(cid, []):
            if any(receipt.get(k) != v for k, v in identity.items() if k in ('candidate_id', 'bundle_digest', 'manifest_digest')):
                raise ValueError('protected survivor conflicts with a required exact identity tuple')
        # CURRENT and every open proposal must retain the exact bundle tuple.
        snapshot = context['authoritative_snapshot']
        identities = [snapshot['current']['value']['records'][-1]['candidate']]
        identities += [v['proposal']['value']['candidate'] for v in snapshot['open_prs'].values() if v['proposal']]
        required = [v for v in identities if v['candidate_id'] == cid]
        if any(v['bundle_digest'] != receipt['bundle_digest'] for v in required):
            raise ValueError('protected survivor bundle differs from authoritative identity')
        verified[cid] = receipt
        context['inputs'][str(package / 'COMPLETE.json')] = _sha(package / 'COMPLETE.json')
        context['inputs'][str(package / 'inventory.json')] = _sha(package / 'inventory.json')
    context['selected_archives'] = selected
    context['verified_survivors'] = verified
    catalog['protection'] = context
    accepted = {r['candidate']['candidate_id'] for r in context['authoritative_snapshot']['current']['value']['records']}
    for name, record in catalog['artifacts'].items():
        cid = record['candidate_id']
        if cid in accepted and cid not in context['protected']:
            record['status'] = 'SUPERSEDED'; record['disposition_ref'] = str(current_path) + ':' + _sha(current_path)
        elif cid in selected and selected[cid] != name and not record.get('pin_ref'):
            chosen = verified[cid]
            if all(record[k] == chosen[k] for k in ('candidate_id', 'bundle_digest', 'manifest_digest', 'inventory_sha256')):
                record['status'] = 'SUPERSEDED'; record['disposition_ref'] = 'EXACT_VERIFIED_SELECTED_SURVIVOR:' + selected[cid]


def disposition(catalog, package, status, authority_ref):
    if status not in TERMINAL or not authority_ref:
        raise ValueError('terminal disposition needs status and explicit evidence/authority')
    record = catalog['artifacts'][str(_safe(package))]
    record['status'] = status; record['disposition_ref'] = authority_ref


def _inactive(package):
    executable = '/usr/sbin/lsof' if sys.platform == 'darwin' else shutil.which('lsof')
    if not executable:
        return False
    try:
        r = subprocess.run([executable, '+D', str(package)], capture_output=True, text=True, timeout=25)
        return r.returncode == 1 and not r.stdout.strip() and not r.stderr.strip()
    except (OSError, subprocess.TimeoutExpired):
        return False


def _publisher_live(record):
    if not record:
        return False
    pid, token = record.get('publisher_pid'), record.get('publisher_start_token')
    return bool(pid and token and admission._start(pid) == token)


def cleanup(path, expected_plan, *, historical_authority=None):
    try:
        from scripts import retention_cleanup
    except ModuleNotFoundError:
        import retention_cleanup
    # Historical ownership/migration is never authorized by a free-form string.
    return retention_cleanup.apply(sys.modules[__name__], path, expected_plan)


def recover_cleanup(path):
    try:
        from scripts import retention_cleanup
    except ModuleNotFoundError:
        import retention_cleanup
    with locked(path) as catalog:
        if not catalog['roots'] or _safe(path) != _safe(catalog_path(catalog['roots'][0])):
            raise ValueError('recovery requires shared authoritative device catalog')
        return retention_cleanup.recover(sys.modules[__name__], path, catalog)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', type=Path, required=True)
    commands = parser.add_subparsers(dest='command', required=True)
    init = commands.add_parser('init'); init.add_argument('--root', type=Path, action='append', required=True)
    commands.add_parser('plan')
    commands.add_parser('recover')
    mark = commands.add_parser('disposition'); mark.add_argument('--archive', type=Path, required=True)
    mark.add_argument('--status', choices=sorted(TERMINAL), required=True); mark.add_argument('--authority-ref', required=True)
    sync = commands.add_parser('post-promotion'); sync.add_argument('--current', type=Path, required=True)
    sync.add_argument('--proposal', type=Path, action='append', default=[])
    sync.add_argument('--recovery-authority', type=Path, required=True, help='JSON authority descriptor (path, sha256, optional accepted repository_path)')
    sync.add_argument('--selected-archives', type=Path, required=True, help='JSON protected Candidate ID to exact archive path map')
    sync.add_argument('--rollback-archive', type=Path, required=True); sync.add_argument('--recovery-archive', type=Path, required=True)
    apply = commands.add_parser('cleanup'); apply.add_argument('--plan', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'recover':
        result = recover_cleanup(args.catalog)
    elif args.command == 'cleanup':
        result = cleanup(args.catalog, json.loads(args.plan.read_text()))
    elif args.command == 'plan':
        # Read-only: never create a catalog or lock during migration inspection.
        result = plan(json.loads(_safe(args.catalog).read_text()))
    else:
        if args.command != 'init' and not args.catalog.exists():
            raise ValueError('mutation requires existing shared catalog')
        roots = args.root if args.command == 'init' else json.loads(args.catalog.read_text()).get('roots', [])
        if not roots or _safe(args.catalog) != _safe(catalog_path(roots[0])):
            raise ValueError('mutation requires shared authoritative catalog')
        with locked(args.catalog) as catalog:
            if args.command == 'init':
                for root in args.root:
                    register_root(catalog, root)
            elif args.command == 'disposition':
                disposition(catalog, args.archive, args.status, args.authority_ref)
            else:
                sync_protection(catalog, args.current, args.proposal, args.rollback_archive, args.recovery_archive,
                                recovery_authority=json.loads(args.recovery_authority.read_text()),
                                selected_archives=json.loads(args.selected_archives.read_text()))
            result = plan(catalog)
        if args.command == 'post-promotion':
            result['deleted_owned_terminal'] = cleanup(args.catalog, result)
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError) as error:
        print(f'INTEGRA_RETENTION: FAIL_CLOSED: {error}', file=sys.stderr)
        raise SystemExit(1)
