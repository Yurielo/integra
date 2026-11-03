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
from datetime import datetime, timezone
try:
    from scripts.lifecycle_diagnostics import emit
except ModuleNotFoundError:
    from lifecycle_diagnostics import emit

try:
    from scripts import build_disk_admission as admission
except ModuleNotFoundError:
    import build_disk_admission as admission

ROOT = Path(__file__).resolve().parents[1]
MAX_COPIES = 8
MAX_BYTES = 20 * 1024**3
FREE_FLOOR = 15 * 1024**3
# A validated exact withdrawal is a terminal lifecycle transition.  It is
# deliberately distinct from ordinary supersession and requires its own
# canonical evidence and exact deletion grant in the cleanup path.
TERMINAL = {'COMPLETED', 'REJECTED', 'SUPERSEDED', 'UNUSED',
            'WITHDRAWN_SUPERSEDED'}
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
    return [base / name for name in ('Build Archive', 'Recovery Archive', 'Build Archive Recovery',
                                    'Candidate Builds', 'Validation')]


def _empty():
    return {'schema_version': '1.0', 'artifact_type': 'integra.owned_archive_catalog',
            'owner_uid': os.getuid(), 'roots': [], 'artifacts': {}, 'leases': {},
            'protection': None, 'historical_adoptions': [], 'deletions': {},
            'publication_sequence_high_watermark': 0}


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
    # Older catalogs could retain a Validation run directory as a root before
    # the canonical Validation parent was registered.  The parent covers the
    # identical bytes, so keep the broader root and preserve all artifact
    # records rather than treating that recoverable catalog shape as unsafe.
    for other in list(catalog['roots']):
        a, b = root.resolve(), Path(other).resolve()
        if a == b:
            return
        if a in b.parents:
            catalog['roots'].remove(other)
        elif b in a.parents:
            return
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
            manifest = package / 'Integra.app/Contents/Resources/candidate-manifest.json'
            m = json.loads(manifest.read_text())
            return {'candidate_id': m['candidate_id'], 'bundle_digest': m['bundle']['digest'],
                    'manifest_digest': _sha(manifest)}, None, str(error)
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


def _context_matches(context, registry, audit, base):
    """Compare catalog context with a complete canonical protection snapshot."""
    selected = registry['selected_survivors']
    rotated = audit.get('rotated_unavailable', {})
    expected = {cid: str(base / relative) for cid, relative in selected.items()
                if relative and cid not in rotated}
    protected = audit.get('protected_identities', {})
    canonical = audit.get('canonical') or {}
    expected_events = audit.get('canonical_lifecycles', canonical.get('canonical_lifecycles'))
    expected_policy = audit.get('standing_policy', canonical.get('standing_policy'))
    expected_rotation = audit.get('rotation_policy', canonical.get('rotation_policy'))
    purpose = audit.get('verification_purpose', 'INTEGRITY')
    stored_purpose = (context or {}).get('verification_purpose', 'INTEGRITY')
    survivors_key = 'metadata_survivors' if stored_purpose == 'CAPACITY' else 'verified_survivors'
    # A fresh strict audit can validate a metadata-only mirror without a
    # manual sync operation. This is new byte evidence from the strict audit,
    # never an upgrade of the stored metadata claim itself.
    strict_recheck = (purpose == 'INTEGRITY' and stored_purpose == 'CAPACITY'
                      and all(any(row['path'] == selected[cid]
                                  and row.get('verified_protected_archive') is True
                                  and all(row.get(key) == context.get('metadata_survivors', {}).get(cid, {}).get(key)
                                          for key in ('candidate_id', 'bundle_digest', 'manifest_digest'))
                                  for row in audit['entries']) for cid in expected))
    return bool(context and context.get('protected') and isinstance(context.get('inputs'), dict)
                # Protection includes every canonical role.  Only the subset
                # with a selected local archive is independently re-verified.
                and set(context['protected']) == set(protected)
                and set(context.get('selected_archives', {})) == set(expected)
                and (stored_purpose == purpose or strict_recheck)
                and set(context.get(survivors_key, {})) == set(expected)
                and all(_sha(p) == digest for p, digest in context['inputs'].items())
                and context.get('selected_archives') == expected
                and context.get('rotated_unavailable', {}) == rotated
                and (audit.get('registry_sha256') is None
                     or context.get('registry_sha256') == audit['registry_sha256'])
                and (expected_events is None or context.get('canonical_lifecycles') == expected_events)
                and (expected_policy is None or context.get('standing_policy') == expected_policy)
                and (expected_rotation is None or context.get('rotation_policy') == expected_rotation)
                and audit['authority_state'] == 'COMPLETE')


def _context_valid(context, *, purpose='INTEGRITY'):
    try:
        try:
            from scripts.candidate_protection_gate import _snapshot
        except ModuleNotFoundError:
            from candidate_protection_gate import _snapshot
        registry, audit = (_snapshot(for_deletion=True, purpose=purpose) if purpose == 'CAPACITY'
                           else _snapshot(for_deletion=True))
        base = Path.home() / 'Library/Application Support/Integra'
        return _context_matches(context, registry, audit, base)
    except (OSError, ValueError, KeyError, TypeError, ImportError, subprocess.SubprocessError):
        return False


def _rotation_order(package, record):
    """Return observed order and its provenance; never infer legacy publication."""
    published = (record or {}).get('publication_recorded_at')
    if published is not None:
        try:
            parsed = datetime.fromisoformat(published.replace('Z', '+00:00'))
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                raise ValueError('publication time has no timezone')
            moment = parsed.timestamp()
        except (ValueError, TypeError, AttributeError):
            return None
        if moment <= 0:
            return None
        return {'timestamp': moment, 'source': 'PUBLISHER_PUBLICATION_TIMESTAMP',
                'recorded_value': published}
    sequence = (record or {}).get('publication_sequence')
    if type(sequence) is int and sequence > 0:
        observed = getattr(Path(package).stat(), 'st_birthtime', None)
        if not isinstance(observed, (float, int)) or observed <= 0:
            return None
        return {'timestamp': observed,
                'source': 'PUBLISHER_SEQUENCE_WITH_OBSERVED_NOW_COHORT_PLACEMENT',
                'recorded_value': observed, 'publisher_sequence': sequence}
    # Historical packages predate publication timestamps. The Owner explicitly
    # authorized APFS birthtime as an observed-now ordering input. It is not
    # represented as a historical publisher fact.
    stat_result = Path(package).stat()
    birthtime = getattr(stat_result, 'st_birthtime', None)
    if not isinstance(birthtime, (float, int)) or birthtime <= 0:
        return None
    return {'timestamp': birthtime, 'source': 'APFS_DIRECTORY_BIRTHTIME_OBSERVED_NOW',
            'recorded_value': birthtime}


def _rotation_binding(row):
    package = Path(row.get('absolute_path', row['path']))
    s = package.lstat()
    order = row.get('capacity_rotation_order') or _rotation_order(package, row.get('catalog_record'))
    if (not order or not all(row.get(key) for key in
                             ('candidate_id', 'bundle_digest', 'manifest_digest'))
            or not stat.S_ISDIR(s.st_mode) or s.st_uid != os.getuid()):
        raise ValueError('rotation physical identity or order is unproven')
    return {'path': str(package),
            **{key: row[key] for key in ('candidate_id', 'bundle_digest', 'manifest_digest')},
            'owner_uid': s.st_uid, 'device': s.st_dev, 'inode': s.st_ino,
            'birthtime': getattr(s, 'st_birthtime', None), 'order_provenance': order}


def _initial_rotation_order(rows, policy_sha256, observed_at, expected_copies=8):
    """Capture the exact first eight-copy ordinal, without inventing dates."""
    bindings = sorted((_rotation_binding(row) for row in rows), key=lambda item: (
        item['order_provenance']['timestamp'], item['candidate_id']))
    if len(bindings) != expected_copies or any(
            a['order_provenance']['timestamp'] == b['order_provenance']['timestamp']
            and a['candidate_id'] == b['candidate_id']
            for a, b in zip(bindings, bindings[1:])):
        raise ValueError('initial eight-copy order is missing or tied')
    sequences = [item['order_provenance']['publisher_sequence'] for item in bindings
                 if item['order_provenance']['source'] ==
                 'PUBLISHER_SEQUENCE_WITH_OBSERVED_NOW_COHORT_PLACEMENT']
    if sequences != sorted(set(sequences)):
        raise ValueError('publisher sequence conflicts with observed cohort placement')
    return {'schema_version': '2.0', 'policy_sha256': policy_sha256,
            'observed_at': observed_at,
            'entries': [{**item, 'ordinal': index} for index, item in enumerate(bindings)]}


def _retired_rotation_sources(catalog, policy_sha256):
    result = {}
    for receipt in catalog.get('retirements', {}).values():
        if receipt.get('reason') != 'OWNER_POLICY_CAPACITY_ROTATION':
            continue
        if (receipt.get('state') != 'RETIRED_NOT_AVAILABLE'
                or receipt.get('physical_available') is not False
                or receipt.get('policy_sha256') != policy_sha256):
            continue
        path = receipt.get('physical_source_path')
        if isinstance(path, str) and path:
            result.setdefault(path, []).append(receipt)
    return result


def _ordered_rotation_rows(rows, baseline, policy_sha256, retired_paths, expected_copies=8,
                           *, purpose='INTEGRITY'):
    """Use immutable initial order, then actual timestamps for later copies."""
    if not baseline:
        return sorted(rows, key=lambda row: (
            row['capacity_rotation_order']['timestamp'], row['candidate_id']))
    if (baseline.get('schema_version') != '2.0'
            or baseline.get('policy_sha256') != policy_sha256
            or not isinstance(baseline.get('entries'), list)
            or len(baseline['entries']) != expected_copies
            or [e.get('ordinal') for e in baseline['entries']] != list(range(expected_copies))):
        raise ValueError('persisted initial rotation order is invalid')
    known = {entry['path']: entry for entry in baseline['entries']}
    if len(known) != expected_copies:
        raise ValueError('persisted initial rotation paths are duplicated')
    live = {_rotation_binding(row)['path']: row for row in rows}
    if len(live) != len(rows):
        raise ValueError('rotation physical paths are duplicated')
    new_incarnations = set()
    for path, saved in known.items():
        if path in retired_paths and not any(
                all(receipt.get(key) == saved[key] for key in
                    ('candidate_id', 'bundle_digest', 'manifest_digest'))
                and (receipt.get('observed_device'), receipt.get('observed_inode'),
                     receipt.get('canonical_snapshot', {}).get('birthtime'),
                     receipt.get('order_provenance')) ==
                    (saved['device'], saved['inode'], saved['birthtime'],
                     saved['order_provenance'])
                for receipt in retired_paths[path]):
            raise ValueError('retirement receipt does not bind original initial incarnation')
        if path in live:
            current = _rotation_binding(live[path])
            if path in retired_paths:
                # The old physical incarnation was retired. A fresh publisher
                # may reuse the exact identity-bound path, but only with a
                # new inode and a verified completed archive.
                record = live[path].get('catalog_record') or {}
                if ((current['device'], current['inode'], current['birthtime']) ==
                        (saved['device'], saved['inode'], saved['birthtime'])
                        or current['order_provenance']['source'] != 'PUBLISHER_PUBLICATION_TIMESTAMP'
                        or record.get('publisher_completed') is not True
                        or not _ownership(Path(path), record,
                                          json.loads((Path(path) / 'COMPLETE.json').read_bytes()))):
                    raise ValueError('retired initial path lacks a verified new publisher incarnation')
                try:
                    from scripts.candidate_archive import verify_archive
                except ModuleNotFoundError:
                    from candidate_archive import verify_archive
                if purpose == 'INTEGRITY':
                    verify_archive(Path(path), {key: current[key] for key in
                                                ('candidate_id', 'bundle_digest', 'manifest_digest')})
                new_incarnations.add(path)
            else:
                expected = {key: value for key, value in saved.items() if key != 'ordinal'}
                # APFS can expose the same preserved directory through a new
                # device number after a volume transition.  The Owner-approved
                # rotation policy treats that as observed device drift only:
                # retain the original catalog value, but permit the current
                # incarnation when every identity, path, UID, inode, birthtime
                # and ordering field remains exact.  Any other change remains
                # fail-closed.
                observed_device_drift = {**expected, 'device': current['device']}
                if current != expected and current != observed_device_drift:
                    raise ValueError('persisted initial rotation identity or birthtime changed')
        elif path not in retired_paths:
            raise ValueError('initial rotation copy disappeared without completed receipt')
    for path, row in live.items():
        if (path not in known or path in new_incarnations) and \
                row['capacity_rotation_order']['source'] != 'PUBLISHER_PUBLICATION_TIMESTAMP':
            raise ValueError('new physical copy has no publication timestamp')
    new_rows = [row for row in rows if str(Path(row.get('absolute_path', row['path']))) not in known
                or str(Path(row.get('absolute_path', row['path']))) in new_incarnations]
    by_sequence = sorted(new_rows, key=lambda row: (row.get('catalog_record') or {}).get('publication_sequence', -1))
    if (any(type((row.get('catalog_record') or {}).get('publication_sequence')) is not int
            for row in by_sequence)
            or any(a['capacity_rotation_order']['timestamp'] >= b['capacity_rotation_order']['timestamp']
                   for a, b in zip(by_sequence, by_sequence[1:]))):
        raise ValueError('new publication timestamp conflicts with monotonic sequence')
    return sorted(rows, key=lambda row: (
        (0, known[str(Path(row.get('absolute_path', row['path'])))]['ordinal'])
        if str(Path(row.get('absolute_path', row['path']))) in known
        and str(Path(row.get('absolute_path', row['path']))) not in new_incarnations else
        (1, row['capacity_rotation_order']['timestamp'], row['candidate_id'])))


def plan(catalog, *, free_bytes=None, _validated_context=False, purpose='INTEGRITY'):
    try:
        from scripts.candidate_protection_gate import require_deletion
    except ModuleNotFoundError:
        from candidate_protection_gate import require_deletion
    try:
        from scripts import candidate_lifecycle as lifecycle
    except ModuleNotFoundError:
        import candidate_lifecycle as lifecycle
    seen = set(); before = sum(_measure(_safe(p), seen) for p in catalog['roots'])
    rows = []; context = catalog.get('protection')
    # This private fast path is used only under the shared lock after a fresh
    # canonical audit, or immediately before the mandatory full rotation gate.
    # A plan never grants deletion on its own.
    if purpose not in ('INTEGRITY', 'CAPACITY'):
        raise ValueError('unknown archive operation purpose')
    # Pre-v2 catalogs and explicit terminal maintenance keep their strict
    # contract. Only canonical v2 capacity context uses metadata evidence.
    if purpose == 'CAPACITY' and (context or {}).get('rotation_policy', {}).get('rotation_strategy') != 'OLDEST_FULL_COPY_FIRST':
        purpose = 'INTEGRITY'
    capacity = purpose == 'CAPACITY'
    valid = True if _validated_context else (_context_valid(context, purpose=purpose) if capacity else _context_valid(context))
    attributed = set()
    rotation_policy = (context or {}).get('rotation_policy') or {}
    rotation_active = rotation_policy.get('rotation_strategy') == 'OLDEST_FULL_COPY_FIRST'
    # Root/container metadata is attributed to UNKNOWN, once, not a package.
    for root in catalog['roots']:
        if Path(root).exists():
            s = Path(root).stat(); attributed.add((s.st_dev, s.st_ino))
    protected_ids = set((context or {}).get('protected', {}))
    complete_roots = all(str(_safe(p)) in catalog['roots'] for p in managed_roots())
    for package in _packages(catalog):
        if capacity:
            try:
                from scripts.candidate_protection_gate import _rotation_package_metadata
            except ModuleNotFoundError:
                from candidate_protection_gate import _rotation_package_metadata
            try:
                metadata = _rotation_package_metadata(package)
                identity = metadata['identity']
                receipt = (json.loads((package / 'COMPLETE.json').read_bytes())
                           if metadata['complete_sha256'] is not None else None)
                error = None
            except (OSError, ValueError, KeyError, TypeError) as problem:
                identity, receipt, error = {}, None, str(problem)
        else:
            identity, receipt, error = _metadata(package)
        local_record = catalog['artifacts'].get(str(package))
        record = lifecycle.replay(local_record or {},
                                  (context or {}).get('canonical_lifecycles', {}),
                                  (context or {}).get('protected', {}).get(identity.get('candidate_id'), []))
        owned = _ownership(package, local_record, receipt)
        amount = _measure(package, attributed); status = record.get('status', 'LEGACY_UNCONFIRMED')
        cid = identity.get('candidate_id'); reasons = []
        # Filesystem timestamps and source-commit dates do not prove archive
        # age. Only the monotonic sequence written by the shared publisher
        # catalog can order full copies for automatic retirement.
        sequence = record.get('publication_sequence')
        order_proven = type(sequence) is int and sequence > 0
        selected = (context or {}).get('selected_archives', {}).get(cid)
        if cid in protected_ids and (not selected or selected == str(package) or (record or {}).get('pin_ref')):
            reasons += context['protected'][cid]
        if status == 'AWAITING_OWNER_ACCEPTANCE' and (not selected or selected == str(package)):
            reasons.append('AWAITING_OWNER_ACCEPTANCE')
        if (record or {}).get('pin_ref'):
            reasons.append('EXPLICIT_GOVERNANCE_PROVENANCE')
        standing = lifecycle.terminal_eligibility(
            identity, record, (context or {}).get('protected', {}).get(cid, []),
            owned=owned, integrity_verified=not capacity and not error,
            context_valid=valid and complete_roots,
            inactive=not _publisher_live(record) and _inactive(package),
            standing_policy=(context or {}).get('standing_policy'))
        if reasons:
            classification = 'PROTECTED'
        elif capacity or not valid or not complete_roots or error or not owned or not order_proven or (status not in TERMINAL and not standing['eligible']) or _publisher_live(record) or not _inactive(package) or cid and cid.startswith(lifecycle.HOLDS):
            classification = 'UNKNOWN'
        else:
            classification = 'DELETABLE'
            # The publisher catalog proves ownership, but only the canonical
            # registry may authorize deletion. Any unavailable authority is
            # retained without changing the existing catalog validator.
            try:
                require_deletion(package)
            except (OSError, ValueError, KeyError, TypeError):
                classification = 'UNKNOWN'
        rows.append({'path': str(package), **identity, 'allocated_bytes': amount,
                     'classification': classification, 'protected_reasons': reasons,
                     'ownership': 'PUBLISHER_BOUND' if owned else 'LEGACY_OR_UNKNOWN_UNCONFIRMED',
                     'lifecycle': status,
                     'local_lifecycle': (local_record or {}).get('status', 'LEGACY_UNCONFIRMED'),
                     'standing_retirement_eligible': standing['eligible'],
                     'standing_retirement_reasons': standing['reasons'],
                     'publication_sequence': sequence if order_proven else None,
                     'retention_order': 'PUBLISHER_PUBLICATION_SEQUENCE' if order_proven else 'UNPROVEN',
                     'metadata_error': error, 'device': package.stat().st_dev,
                     'inode': package.stat().st_ino, 'historical': bool((record or {}).get('historical'))})
        if rotation_active:
            rows[-1]['capacity_rotation_order'] = _rotation_order(package, local_record)
    survivors_key = ('metadata_survivors' if (context or {}).get('verification_purpose') == 'CAPACITY'
                     else 'verified_survivors')
    survivors_valid = all(any(r.get('candidate_id') == cid and not r['metadata_error']
                                  and all(r.get(k) == context.get(survivors_key, {}).get(cid, {}).get(k)
                                          for k in ('candidate_id', 'bundle_digest', 'manifest_digest'))
                                  and (not (context or {}).get('selected_archives', {}).get(cid)
                                       or r['path'] == context['selected_archives'][cid]) for r in rows)
                          for cid in (context or {}).get('selected_archives', {}))
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
    # Retire exactly one archive per transaction. This makes archive rotation
    # deterministic and interruption-safe, and never turns a capacity check
    # into a bulk deletion operation.
    eligible = sorted((row for row in rows if row['classification'] == 'DELETABLE'),
                      key=lambda row: (row['publication_sequence'], row['candidate_id'],
                                       row['bundle_digest'], row['path']))
    target = eligible[0] if eligible else None
    # An incomplete order must not silently choose among legacy full copies.
    rotation_rows = []
    if (rotation_active and not catalog.get('publication_timestamp_order_conflict')
            and all(row.get('capacity_rotation_order') for row in rows)):
        retired_paths = _retired_rotation_sources(catalog, rotation_policy.get('sha256'))
        try:
            rotation_rows = _ordered_rotation_rows(
                [{**row, 'catalog_record': catalog.get('artifacts', {}).get(row['path'])}
                 for row in rows],
                catalog.get('rotation_order_v2'), rotation_policy.get('sha256'),
                retired_paths, MAX_COPIES, purpose=purpose)
        except (ValueError, KeyError, TypeError, OSError):
            rotation_rows = []
    ambiguous_oldest = (len(rotation_rows) > 1 and
                        (rotation_rows[0]['capacity_rotation_order']['timestamp'], rotation_rows[0]['candidate_id']) ==
                        (rotation_rows[1]['capacity_rotation_order']['timestamp'], rotation_rows[1]['candidate_id']))
    # The Owner-approved capacity policy permits automatic rotation, but never
    # overrides a physical archive selected as a canonical survivor (CURRENT,
    # rollback, or another required protected baseline).  Other pending
    # lifecycle states remain eligible under the approved capacity policy.
    selected_paths = set((context or {}).get('selected_archives', {}).values())
    capacity_target = (next((row for row in rotation_rows if row['path'] not in selected_paths), None)
                       if valid and rotation_rows and len(rows) >= MAX_COPIES
                       and not ambiguous_oldest else None)
    report = {'schema_version': '1.0', 'artifact_type': 'integra.retention_plan', 'dry_run': True,
              'BEFORE_BYTES': before, 'PROTECTED_BYTES': protected, 'DELETABLE_BYTES': deletable,
              'UNKNOWN_BYTES': unknown, 'EXPECTED_AFTER_BYTES': before - deletable,
              'EXPECTED_FREE_SPACE': free_bytes + deletable,
              'reclaim_estimate': 'ATTRIBUTED_BLOCKS; APFS_EXCLUSIVE_EXTENTS_NOT_PROVEN',
              'full_copies': len(rows), 'over_copy_cap': len(rows) > MAX_COPIES,
              'over_byte_cap': before > MAX_BYTES, 'protection_context_valid': valid,
              'catalog_sha256': _digest(catalog), 'entries': rows,
              'rotation_strategy': 'OLDEST_PROVEN_ELIGIBLE_FIRST',
              'rotation_target': ({key: target[key] for key in (
                  'path', 'candidate_id', 'bundle_digest', 'manifest_digest',
                  'publication_sequence')} if target else None)}
    if capacity:
        report['verification_purpose'] = 'CAPACITY'
    report['capacity_rotation_strategy'] = 'OLDEST_FULL_COPY_FIRST' if rotation_active else None
    report['capacity_rotation_target'] = ({key: capacity_target[key] for key in (
        'path', 'candidate_id', 'bundle_digest', 'manifest_digest',
        'capacity_rotation_order', 'device', 'inode')} if capacity_target else None)
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
    # Assigned under the shared catalog lock. Preserve the ordering floor even
    # after retirement removes the last numbered live archive. Legacy catalogs
    # recover that floor from durable publisher attestations, without assigning
    # an invented order to unnumbered legacy artifacts.
    watermark = catalog.get('publication_sequence_high_watermark', 0)
    if type(watermark) is not int or watermark < 0:
        raise ValueError('publication sequence high watermark is invalid')
    sequences = [watermark]
    records = list(catalog['artifacts'].values())
    records.extend(retired.get('publisher_attestation') or
                   retired.get('conflicting_catalog_record') or {}
                   for retired in catalog.get('retirements', {}).values())
    for record in records:
        sequence = record.get('publication_sequence')
        if type(sequence) is int and sequence > 0:
            sequences.append(sequence)
    sequence = max(sequences) + 1
    published_at = datetime.now(timezone.utc).isoformat()
    prior_timestamp = catalog.get('publication_timestamp_high_watermark')
    baseline_timestamp = (catalog.get('rotation_order_v2') or {}).get('observed_at')
    if ((prior_timestamp is not None and published_at <= prior_timestamp)
            or (baseline_timestamp is not None and published_at <= baseline_timestamp)):
        catalog['publication_timestamp_order_conflict'] = True
    else:
        catalog['publication_timestamp_high_watermark'] = published_at
    catalog['artifacts'][str(package)] = {
        **{k: receipt[k] for k in ('candidate_id', 'bundle_digest', 'manifest_digest', 'inventory_sha256')},
        'complete_sha256': _sha(package / 'COMPLETE.json'), 'owner_uid': os.getuid(),
        'device': s.st_dev, 'inode': s.st_ino, 'publisher_run_id': token,
        'publisher_pid': lease['pid'], 'publisher_start_token': lease['start_token'],
        'publisher_completed': True, 'publication_sequence': sequence,
        'publication_recorded_at': published_at,
        'status': 'AWAITING_OWNER_ACCEPTANCE', 'historical': False}
    catalog['publication_sequence_high_watermark'] = sequence
    del catalog['leases'][token]


def _lease_caller(lease):
    return (lease.get('owner_uid') == os.getuid()
            and admission._start(lease['pid']) == lease['start_token']
            and (lease['pid'] == os.getpid() or lease.get('process_group') == os.getpgrp()))


def reserve_archive(root, allocated_bytes, *, destination=None, identity=None):
    """Reserve a publication slot before staging; never silently prune."""
    try:
        from scripts.candidate_protection_gate import require_archive_publication
    except ModuleNotFoundError:
        from candidate_protection_gate import require_archive_publication
    if not os.environ.get('INTEGRA_RETENTION_BUILD_LEASE'):
        maintenance(root, reason='BEFORE_ARCHIVE_COPY', need_slot=True)
    require_archive_publication(_safe(root), allocated_bytes)
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
        snapshot = plan(catalog, purpose='CAPACITY')
        reserved = sum(r['expected_bytes'] for r in catalog['leases'].values())
        if snapshot['full_copies'] + sum(r.get('copies', 1) for r in catalog['leases'].values()) + 1 > MAX_COPIES or snapshot['BEFORE_BYTES'] + reserved + allocated_bytes > MAX_BYTES:
            emit('ARCHIVE_HEADROOM_REJECTED', copies=snapshot['full_copies'],
                 allocated_bytes=snapshot['BEFORE_BYTES'], requested_bytes=allocated_bytes)
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
    emit('CANDIDATE_CREATED', path=str(package), candidate_id=receipt['candidate_id'],
         protected_reason='AWAITING_OWNER_ACCEPTANCE')


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
    maintenance(root, reason='BEFORE_BUILD', need_slot=archive_copy)
    path = catalog_path(root)
    with locked(path) as catalog:
        register_root(catalog, root); _recover_leases(catalog); snapshot = plan(catalog, purpose='CAPACITY')
        if not snapshot['protection_context_valid']:
            raise ValueError('build admission blocked: fresh canonical protection unavailable')
        reserved = sum(r['expected_bytes'] for r in catalog['leases'].values())
        if snapshot['full_copies'] + sum(r.get('copies', 1) for r in catalog['leases'].values()) + int(archive_copy) > MAX_COPIES or snapshot['BEFORE_BYTES'] + reserved + (expected_bytes if archive_copy else 0) > MAX_BYTES:
            emit('BUILD_HEADROOM_REJECTED', copies=snapshot['full_copies'],
                 allocated_bytes=snapshot['BEFORE_BYTES'], requested_bytes=expected_bytes,
                 reason='8_COPY_OR_20_GIB_CAP')
            raise ValueError('build blocked by 8-copy / 20-GiB archive cap')
    # Existing atomic workspace admission remains authoritative at spawn.
    # Include copy peak and conservative live-workspace charging in preflight.
    with admission._ledger(root) as (anchor, records):
        live = sum(r['expected_bytes'] for r in records.values() if admission._live(r))
        budget = expected_bytes * (3 if archive_copy else 1)
        if shutil.disk_usage(anchor).free < FREE_FLOOR + budget + live:
            emit('DISK_HEADROOM_REJECTED', free_bytes=shutil.disk_usage(anchor).free,
                 required_bytes=FREE_FLOOR + budget + live, reserve_bytes=FREE_FLOOR)
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
            register_root(catalog, root); _recover_leases(catalog); snapshot = plan(catalog, purpose='CAPACITY')
            if not snapshot['protection_context_valid']:
                raise ValueError('atomic build admission blocked: fresh canonical protection unavailable')
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
    """Mirror only byte-verified canonical registry survivors into the owner catalog.

    The catalog records publisher ownership and transaction state; it cannot
    select protected identities or grant deletion independently of the registry.
    """
    try:
        from scripts.candidate_archive import verify_archive
        from scripts.candidate_protection_gate import _snapshot
        from scripts import candidate_protection_audit as protection
    except ModuleNotFoundError:
        from candidate_archive import verify_archive
        from candidate_protection_gate import _snapshot
        import candidate_protection_audit as protection
    registry, audit = _snapshot(for_deletion=True)
    base = Path.home() / 'Library/Application Support/Integra'
    if _safe(current_path) != _safe(protection.ROOT / registry['canonical_current']['path']):
        raise ValueError('catalog CURRENT differs from canonical registry')
    if pins is not None and pins != registry['explicit_governance_pins']:
        raise ValueError('catalog pins differ from canonical registry')
    selected = {cid: str(base / relative)
                for cid, relative in registry['selected_survivors'].items()
                if relative and cid not in audit.get('rotated_unavailable', {})}
    if (selected_archives is not None and selected_archives != selected
            or rollback_archive is not None and
               str(_safe(rollback_archive)) != selected.get(registry['rollback']['candidate_id'])
            or recovery_archive is not None and
               (registry['recovery'] is None or
                str(_safe(recovery_archive)) != selected.get(registry['recovery']['candidate_id']))):
        raise ValueError('catalog survivor selection differs from canonical registry')
    reconcile_catalog(catalog, registry, audit, base, current_path=current_path)


def reconcile_catalog(catalog, registry, audit, base, *, current_path=None,
                      _verified_snapshot=False):
    """Mirror a verified complete canonical snapshot, under the caller's lock.

    This is deterministic bookkeeping only. It does not select roles, create
    acceptance, or withdraw pending authority. No payload is changed.
    """
    try:
        from scripts.candidate_archive import verify_archive
        from scripts import candidate_lifecycle as lifecycle
    except ModuleNotFoundError:
        from candidate_archive import verify_archive
        import candidate_lifecycle as lifecycle
    if audit.get('authority_state') != 'COMPLETE':
        raise ValueError('catalog reconciliation needs complete canonical authority')
    base = _safe(base)
    protected = audit['protected_identities']
    if set(registry['selected_survivors']) != set(protected):
        raise ValueError('catalog reconciliation survivor domain differs')
    selected = {cid: str(base / relative)
                for cid, relative in registry['selected_survivors'].items()
                if relative and cid not in audit.get('rotated_unavailable', {})}
    canonical = audit.get('canonical', {})
    events = audit.get('canonical_lifecycles', canonical.get('canonical_lifecycles', {}))
    policy = audit.get('standing_policy', canonical.get('standing_policy', {}))
    rotation_policy = audit.get('rotation_policy', canonical.get('rotation_policy'))
    capacity = audit.get('verification_purpose') == 'CAPACITY'
    context = {'protected': {cid: role['reasons'] for cid, role in protected.items()},
               'inputs': {}, 'selected_archives': selected,
               'verified_survivors': {}, 'registry_sha256': audit.get('registry_sha256'),
               'canonical_snapshot': canonical,
               'canonical_lifecycles': events, 'standing_policy': policy,
               'rotated_unavailable': audit.get('rotated_unavailable', {})}
    if capacity:
        context.update(verification_purpose='CAPACITY', metadata_survivors={})
    if rotation_policy is not None:
        context['rotation_policy'] = rotation_policy
    verified = {}
    for cid, name in selected.items():
        package = _safe(name)
        if not any(package == root or root in package.parents for root in map(_safe, catalog['roots'])):
            raise ValueError('protected survivor is outside the managed roots')
        rows = [row for row in audit['entries'] if row['path'] == str(package.relative_to(base))]
        if (len(rows) != 1 or rows[0]['classification'] != 'PROTECTED'
                or not rows[0].get('identity_metadata_verified' if capacity else 'verified_protected_archive')):
            raise ValueError('canonical protected survivor is not verified')
        if capacity:
            context['metadata_survivors'][cid] = {
                **{key: rows[0][key] for key in lifecycle.IDENTITY},
                'archive_path': str(package), 'verification': 'IDENTITY_METADATA_ONLY'}
        elif _verified_snapshot:
            # Only refresh_protection passes the fresh audit obtained under
            # this lock. Other reconciliation callers keep full verification.
            receipt = json.loads((package / 'COMPLETE.json').read_bytes())
            if (receipt.get('status') != 'COMPLETE'
                    or any(receipt.get(key) != rows[0][key] for key in lifecycle.IDENTITY)):
                raise ValueError('canonical survivor receipt changed after audit')
            receipt = {**receipt, 'archive_path': str(package)}
        else:
            receipt = verify_archive(package, {key: rows[0][key]
                                               for key in lifecycle.IDENTITY})
        if not capacity:
            verified[cid] = receipt
        context['inputs'][str(package / 'COMPLETE.json')] = _sha(package / 'COMPLETE.json')
        context['inputs'][str(package / 'inventory.json')] = _sha(package / 'inventory.json')
    context['verified_survivors'] = verified
    if current_path is not None:
        context['current_path'] = str(_safe(current_path))
    else:
        context['current_id'] = registry['canonical_current']['current_id']
    catalog['protection'] = context
    for name, record in list(catalog['artifacts'].items()):
        reconciled = lifecycle.replay(
            record, events, context['protected'].get(record.get('candidate_id'), []))
        # Pending Candidate withdrawal is a separately validated canonical
        # terminal event, not a promotion.  Mirror it only after the complete
        # protection resolver has accepted its exact Product Owner evidence.
        catalog['artifacts'][name] = lifecycle.replay_withdrawal(
            reconciled, canonical.get('withdrawn_candidate_lifecycles', []))


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
    if record.get('publisher_completed'):
        return False  # COMPLETE bytes published; no remaining writer lease.
    pid, token = record.get('publisher_pid'), record.get('publisher_start_token')
    return bool(pid and token and admission._start(pid) == token)


def cleanup(path, expected_plan, *, historical_authority=None):
    try:
        from scripts import retention_cleanup
    except ModuleNotFoundError:
        import retention_cleanup
    # Historical ownership/migration is never authorized by a free-form string.
    return retention_cleanup.apply(sys.modules[__name__], path, expected_plan)


def cleanup_exact(path, identity):
    """Execute one independently authorized withdrawal retirement.

    Exact withdrawal is not rotation and never receives inferred publication
    order. The executor rechecks the canonical deletion gate before mutation.
    """
    try:
        from scripts import retention_cleanup
    except ModuleNotFoundError:
        import retention_cleanup
    return retention_cleanup.apply_exact(sys.modules[__name__], path, identity)


def cleanup_capacity_rotation(path, expected_plan):
    """Use the existing durable cleanup executor for one canonical oldest copy."""
    try:
        from scripts import retention_cleanup
    except ModuleNotFoundError:
        import retention_cleanup
    return retention_cleanup.apply_capacity_rotation(sys.modules[__name__], path, expected_plan)


def recover_cleanup(path):
    try:
        from scripts import retention_cleanup
    except ModuleNotFoundError:
        import retention_cleanup
    with locked(path) as catalog:
        if not catalog['roots'] or _safe(path) != _safe(catalog_path(catalog['roots'][0])):
            raise ValueError('recovery requires shared authoritative device catalog')
        return retention_cleanup.recover(sys.modules[__name__], path, catalog)


def refresh_protection(catalog, *, _reuse_verified_audit=False, purpose='INTEGRITY'):
    """Refresh the catalog mirror from the registry; no heuristic selection."""
    try:
        from scripts.candidate_protection_gate import _snapshot
        from scripts import candidate_protection_audit as protection
    except ModuleNotFoundError:
        from candidate_protection_gate import _snapshot
        import candidate_protection_audit as protection
    registry, audit = (_snapshot(for_deletion=True, purpose=purpose) if purpose == 'CAPACITY'
                       else _snapshot(for_deletion=True))
    base = Path.home() / 'Library/Application Support/Integra'
    selected = {cid: str(base / relative) for cid, relative in registry['selected_survivors'].items()
                if relative and cid not in audit.get('rotated_unavailable', {})}
    if (purpose == 'CAPACITY' or _reuse_verified_audit and
            (audit.get('canonical') or {}).get('rotation_policy', {}).get('rotation_strategy')
            == 'OLDEST_FULL_COPY_FIRST'):
        reconcile_catalog(catalog, registry, audit, base,
                          current_path=protection.ROOT / registry['canonical_current']['path'],
                          _verified_snapshot=True)
    else:
        sync_protection(catalog, protection.ROOT / registry['canonical_current']['path'], [],
                        selected.get(registry['rollback']['candidate_id']),
                        selected.get(registry['recovery']['candidate_id']) if registry['recovery'] else None,
                        pins=registry['explicit_governance_pins'], selected_archives=selected)
    emit('PROTECTION_RECONCILED', current_id=registry['canonical_current']['current_id'],
         selected_survivors=selected)
    return audit


def maintenance(root, *, reason, need_slot=False):
    """Reevaluate owned terminal objects before admission; never adopt legacy.

    Failure preserves the journal/artifacts and is observable. Admission still
    enforces both hard caps, so unavailable protection cannot produce growth.
    """
    path = catalog_path(root)
    if not path.exists():
        emit('CLEANUP_SKIPPED', reason='NO_OWNERSHIP_CATALOG', trigger=reason)
        return []
    emit('CLEANUP_ATTEMPTED', trigger=reason, catalog=str(path))
    try:
        with locked(path) as catalog:
            register_root(catalog, root)
            has_journal = bool(catalog.get('deletions'))
        if has_journal:
            recover_cleanup(path)
        with locked(path) as catalog:
            refresh_protection(catalog, _reuse_verified_audit=need_slot, purpose='CAPACITY')
            snapshot = plan(catalog, _validated_context=True, purpose='CAPACITY')
        for row in snapshot['entries']:
            if row['classification'] != 'DELETABLE':
                emit('CANDIDATE_RETAINED', path=row['path'],
                     reasons=row['protected_reasons'] or ['UNKNOWN_OR_ACTIVE'],
                     trigger=reason)
        if not snapshot['protection_context_valid']:
            emit('CLEANUP_SKIPPED', reason='PROTECTION_AUTHORITY_UNAVAILABLE', trigger=reason)
            return []
        if (need_slot and snapshot.get('capacity_rotation_strategy') == 'OLDEST_FULL_COPY_FIRST'
                and snapshot['full_copies'] >= MAX_COPIES):
            if snapshot.get('capacity_rotation_target') is None:
                emit('CLEANUP_SKIPPED', reason='CAPACITY_ROTATION_ORDER_UNPROVEN', trigger=reason)
                return []
            deleted = cleanup_capacity_rotation(path, snapshot)
            with locked(path) as catalog:
                refresh_protection(catalog, _reuse_verified_audit=True, purpose='CAPACITY')
            emit('CAPACITY_ROTATION_COMPLETED', paths=deleted, trigger=reason,
                 order_provenance=snapshot['capacity_rotation_target']['capacity_rotation_order'])
            return deleted
        if snapshot.get('capacity_rotation_strategy') == 'OLDEST_FULL_COPY_FIRST':
            emit('CLEANUP_SKIPPED', reason='CAPACITY_SLOT_NOT_NEEDED', trigger=reason)
            return []
        if not snapshot['DELETABLE_BYTES']:
            emit('CLEANUP_SKIPPED', reason='NO_ELIGIBLE_TERMINAL_COPIES', trigger=reason)
            return []
        if snapshot['rotation_target'] is None:
            emit('CLEANUP_SKIPPED', reason='NO_PROVEN_OLDEST_ELIGIBLE_COPY', trigger=reason)
            return []
        before_free = shutil.disk_usage(root if Path(root).exists() else Path(root).parent).free
        deleted = cleanup(path, snapshot)
        after_free = shutil.disk_usage(root if Path(root).exists() else Path(root).parent).free
        emit('CLEANUP_COMPLETED', paths=deleted, trigger=reason,
             attributed_bytes=next(row['allocated_bytes'] for row in snapshot['entries']
                                   if row['path'] == snapshot['rotation_target']['path']),
             observed_free_space_delta=after_free - before_free,
             physical_reclaim='NOT_EXCLUSIVE_APFS_PROOF')
        return deleted
    except (OSError, ValueError, KeyError) as error:
        emit('CLEANUP_FAILED', trigger=reason, reason=str(error), fail_closed=True)
        return []


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
