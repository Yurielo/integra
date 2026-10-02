#!/usr/bin/env python3
"""Retire only the six owner-authorized historical Integra.app payloads.

Package receipts, inventories, provenance and proof files are never removed.
The durable journal permits conservative resumption of a partially unlinked app.
This is deliberately separate from publisher-owned automatic retention cleanup.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time
import uuid

try:
    from scripts import candidate_archive, candidate_protection_audit as authority
    from scripts import candidate_protection_gate, retention_cleanup
    from scripts import candidate_retention
except ModuleNotFoundError:
    import candidate_archive
    import candidate_protection_audit as authority
    import candidate_protection_gate
    import retention_cleanup
    import candidate_retention

BASE = Path.home() / 'Library/Application Support/Integra'
CATALOG = authority.ROOT / 'state/issue214_exact_legacy_retirement_v1.json'
CATALOG_SHA = 'f146bfb1c3ed397275071528ee1aa0945dbde75a0b1669357051c3a6136e2c76'
DECISION_REF = 'https://github.com/Yurielo/integra/issues/214#issuecomment-5957484872'
DECISION_SHA = '358eeb2902767c5d4efd873e8654d5a4f0bfe7477f23c36f25230c4e5368b526'
COUNT = 6
MAX_BYTES = 13673029632
JOURNAL = BASE / 'issue214-exact-legacy-retirement-journal.json'
LOCK = BASE / 'issue214-exact-legacy-retirement.lock'
EVIDENCE = BASE / 'Historical Retirement Evidence' / ('issue214-' + CATALOG_SHA)
RELOCATION_JOURNAL = BASE / 'issue214-exact-legacy-relocation-journal.json'
IDENTITY = ('candidate_id', 'bundle_digest', 'manifest_digest')


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _catalog(registry: dict) -> list[dict]:
    expected = {'status': 'PRODUCT_OWNER_AUTHORIZED_EXACT_CATALOG',
                'decision_ref': DECISION_REF, 'decision_token_sha256': DECISION_SHA,
                'catalog_path': 'state/issue214_exact_legacy_retirement_v1.json',
                'catalog_sha256': CATALOG_SHA, 'count': COUNT,
                'max_attributed_bytes': MAX_BYTES, 'deletion_mode': 'EXACT_CATALOG_ONLY'}
    if (registry.get('exact_legacy_retirement') != expected
            or registry.get('explicit_governance_pins') != {}
            or registry.get('deletion_authorizations') != {}
            or registry.get('deletion_enabled') is not False
            or registry.get('unknown_historical') != 'RETAIN_FAIL_CLOSED'):
        raise ValueError('exact legacy retirement authority or fail-closed state differs')
    rows = json.loads(CATALOG.read_text())
    if (not isinstance(rows, list) or len(rows) != COUNT or _digest(rows) != CATALOG_SHA
            or sum(row['allocated_bytes'] for row in rows) != MAX_BYTES
            or len({row['path'] for row in rows}) != COUNT
            or rows != sorted(rows, key=lambda row: row['path'])):
        raise ValueError('six-object authorized catalog differs')
    for row in rows:
        if (set(row) != {'path', *IDENTITY, 'allocated_bytes'}
                or row['path'].startswith('/') or '..' in Path(row['path']).parts
                or not re.fullmatch(r'candidate-v1-[0-9a-f]{64}', row['candidate_id'])
                or any(not re.fullmatch(r'[0-9a-f]{64}', row[k]) for k in IDENTITY[1:])
                or type(row['allocated_bytes']) is not int or row['allocated_bytes'] <= 0):
            raise ValueError('authorized catalog row is invalid')
    return rows


def _owner_decision() -> None:
    comment = authority._api('repos/Yurielo/integra/issues/comments/5957484872')
    token = re.findall(r'^PRODUCT_OWNER_AUTHORIZATION:.*$', comment.get('body', ''), re.MULTILINE)
    expected = ('PRODUCT_OWNER_AUTHORIZATION: ISSUE_214_AUTHORIZE_EXACT_LEGACY_RETIREMENT '
                f'CATALOG_SHA256={CATALOG_SHA} COUNT={COUNT} MAX_ATTRIBUTED_BYTES={MAX_BYTES} '
                'DELETION_ENABLED=EXACT_CATALOG_ONLY EXPLICIT_GOVERNANCE_PINS={} '
                'UNKNOWN_OUTSIDE_CATALOG=RETAIN_FAIL_CLOSED CURRENT_CHANGE=FORBIDDEN PROMOTION=FORBIDDEN')
    if (comment.get('html_url') != DECISION_REF
            or comment.get('user', {}).get('login', '').lower() != 'yurielo'
            or token != [expected] or authority.sha(expected.encode()) != DECISION_SHA):
        raise ValueError('Product Owner exact legacy retirement decision is not verified')


def _snapshot() -> tuple[dict, dict, list[dict]]:
    registry, audit = candidate_protection_gate._snapshot(for_deletion=True)
    rows = _catalog(registry)
    _owner_decision()
    if audit['authority_state'] != 'COMPLETE':
        raise ValueError('canonical protection authority is incomplete')
    for row in rows:
        if row['candidate_id'] in audit['protected_identities']:
            raise ValueError('authorized historical identity has become protected')
    return registry, audit, rows


def _app(row: dict) -> Path:
    package = BASE / row['path']
    candidate_archive._path(package, durable=True)
    if not any(package == BASE / root or package.is_relative_to(BASE / root)
               for root in ('Build Archive', 'Recovery Archive', 'Build Archive Recovery')):
        raise ValueError('retirement path is outside historical archive roots')
    return package / 'Integra.app'


def _inactive(app: Path) -> None:
    result = subprocess.run(['lsof', '+D', str(app)], capture_output=True, text=True, timeout=90)
    if result.returncode not in (0, 1) or result.stdout.strip() or result.stderr.strip():
        raise ValueError('historical app is active or lsof could not prove inactivity')


def _measure(root: Path) -> int:
    seen = set(); total = 0
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in dirs + files:
            p = Path(directory) / name; s = p.lstat()
            if not (stat.S_ISREG(s.st_mode) or stat.S_ISDIR(s.st_mode)) or s.st_uid != os.getuid():
                raise ValueError('foreign or nonregular legacy app entry')
            if stat.S_ISREG(s.st_mode) and s.st_nlink != 1:
                raise ValueError('hardlinked legacy app entry')
            key = (s.st_dev, s.st_ino)
            if key not in seen:
                seen.add(key); total += s.st_blocks * 512
    s = root.lstat()
    if not stat.S_ISDIR(s.st_mode) or s.st_uid != os.getuid():
        raise ValueError('legacy app root owner/type differs')
    total += s.st_blocks * 512
    return total


def _verify_app(row: dict, audit: dict) -> Path:
    app = _app(row); package = app.parent
    matches = [item for item in audit['entries'] if item['path'] == row['path']]
    if len(matches) != 1 or matches[0]['classification'] != 'UNKNOWN':
        raise ValueError('authorized legacy package is absent or newly protected')
    if any(matches[0].get(k) != row[k] for k in (*IDENTITY, 'allocated_bytes')):
        raise ValueError('legacy package identity or allocation changed')
    if not app.is_dir() or app.is_symlink() or (package / '.git').exists():
        raise ValueError('legacy app is absent, linked, or a worktree')
    _inactive(app)
    identity = candidate_archive._identity(app)
    if any(identity[k] != row[k] for k in IDENTITY):
        raise ValueError('legacy app bytes differ from authorized Candidate identity')
    # A COMPLETE receipt binds all archival bytes; the two loose originals are
    # checked against their complete retained app twins during full preflight.
    if (package / 'COMPLETE.json').exists():
        candidate_archive.verify_archive(package, identity)
    if _measure(package) != row['allocated_bytes']:
        raise ValueError('legacy package physical allocation changed')
    return app


def _loose_twins(rows: list[dict]) -> None:
    for original, twin in (("Build Archive/pilot-2fe375-original", '2fe375'),
                           ("Build Archive/recovered-current-65bf72", '65bf72')):
        loose = next(row for row in rows if row['path'] == original)
        retained = next(row for row in rows if row['path'].startswith('Build Archive/retained/')
                        and twin in row['candidate_id'])
        if (candidate_archive._inventory(_app(loose)) !=
                candidate_archive._inventory(_app(retained))):
            raise ValueError('loose historical app differs from its COMPLETE twin')


def _entries(app: Path) -> list[dict]:
    entries = candidate_archive._inventory(app)
    for entry in entries:
        s = (app / entry['path']).lstat()
        if s.st_uid != os.getuid() or (entry['type'] == 'file' and s.st_nlink != 1):
            raise ValueError('foreign or hardlinked entry in retirement app')
        entry.update(device=s.st_dev, inode=s.st_ino)
        if entry['type'] == 'file':
            entry.update(mtime_ns=s.st_mtime_ns, ctime_ns=s.st_ctime_ns)
    return entries


def _write_journal(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.new')
    with temporary.open('x') as handle:
        json.dump(value, handle, sort_keys=True)
        handle.write('\n'); handle.flush(); os.fsync(handle.fileno())
    os.replace(temporary, path)
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _persist(value: dict) -> None:
    _write_journal(JOURNAL, value)


def _load(registry_sha: str) -> dict:
    if not JOURNAL.exists():
        return {'schema_version': '1.0', 'catalog_sha256': CATALOG_SHA,
                'registry_sha256': registry_sha, 'completed': [], 'active': None}
    value = json.loads(JOURNAL.read_text())
    if (value.get('schema_version') != '1.0' or value.get('catalog_sha256') != CATALOG_SHA
            or value.get('registry_sha256') != registry_sha
            or not isinstance(value.get('completed'), list)
            or len(set(value['completed'])) != len(value['completed'])
            or set(value) != {'schema_version', 'catalog_sha256', 'registry_sha256', 'completed', 'active'}):
        raise ValueError('retirement journal is stale or malformed')
    return value


def _delete_active(journal: dict, audit: dict, rows: list[dict],
                   *, registry_sha: str | None = None) -> None:
    job = journal['active']
    row = next((item for item in rows if item['path'] == job['path']), None)
    if row is None or job['identity'] != {k: row[k] for k in IDENTITY}:
        raise ValueError('active retirement target is outside exact catalog')
    app = _app(row)
    if not app.exists():
        if job['phase'] != 'DELETING' or not app.parent.is_dir():
            raise ValueError('retirement target disappeared without a durable transaction')
    else:
        s = app.lstat()
        if (not stat.S_ISDIR(s.st_mode) or (s.st_dev, s.st_ino) != (job['device'], job['inode'])
                or s.st_uid != os.getuid()):
            raise ValueError('retirement app root was replaced')
        _inactive(app)
        remaining = retention_cleanup._remaining(candidate_retention, app, job, hash_bytes=True)
        # Inventory hashing can take minutes for a full app. Refresh the one
        # canonical authority immediately before the first destructive syscall.
        if registry_sha is not None:
            _, refreshed, current_rows = _snapshot()
            if refreshed['registry_sha256'] != registry_sha or current_rows != rows:
                raise ValueError('canonical protection changed before legacy unlink')
        if job['phase'] == 'PREPARED':
            job['phase'] = 'DELETING'; _persist(journal)
        expected = {entry['path']: entry for entry in job['entries']}
        refresh_at = time.monotonic() + 30
        for entry in sorted(remaining, key=lambda item: (item['type'] == 'directory',
                                                        -len(Path(item['path']).parts))):
            if registry_sha is not None and time.monotonic() >= refresh_at:
                _, refreshed, current_rows = _snapshot()
                if refreshed['registry_sha256'] != registry_sha or current_rows != rows:
                    raise ValueError('canonical protection changed during legacy retirement')
                refresh_at = time.monotonic() + 30
            fd, name = retention_cleanup._parent_fd(app, entry['path'], expected, job)
            try:
                s = os.stat(name, dir_fd=fd, follow_symlinks=False)
                if ((s.st_dev, s.st_ino) != (entry['device'], entry['inode'])
                        or s.st_uid != os.getuid()
                        or stat.S_IMODE(s.st_mode) != entry['mode']):
                    raise ValueError('retirement entry changed before unlink')
                if entry['type'] == 'file':
                    if (not stat.S_ISREG(s.st_mode) or s.st_nlink != 1
                            or s.st_size != entry['size'] or s.st_mtime_ns != entry['mtime_ns']
                            or s.st_ctime_ns != entry['ctime_ns']):
                        raise ValueError('retirement file changed before unlink')
                    os.unlink(name, dir_fd=fd)
                elif stat.S_ISDIR(s.st_mode):
                    os.rmdir(name, dir_fd=fd)
                else:
                    raise ValueError('retirement directory changed type')
            finally:
                os.close(fd)
        os.rmdir(app)
    journal['completed'].append(row['path'])
    journal['active'] = None
    _persist(journal)


def execute(*, apply: bool = False) -> dict:
    """Dry-run is read-only; apply removes only authorized app children."""
    registry, audit, rows = _snapshot()
    registry_sha = audit['registry_sha256']
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    with LOCK.open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        journal = _load(registry_sha)
        if any(path not in {row['path'] for row in rows} for path in journal['completed']):
            raise ValueError('journal completion is outside exact catalog')
        if journal['active'] is None:
            for row in rows:
                if row['path'] in journal['completed']:
                    if _app(row).exists():
                        raise ValueError('completed legacy app reappeared')
                else:
                    _verify_app(row, audit)
            if not journal['completed']:
                _loose_twins(rows)
        if not apply:
            return {'status': 'DRY_RUN', 'catalog_sha256': CATALOG_SHA,
                    'completed': len(journal['completed']), 'remaining': COUNT - len(journal['completed']),
                    'max_attributed_bytes': MAX_BYTES, 'authority_state': audit['authority_state']}
        if not JOURNAL.exists():
            _persist(journal)
        for row in rows:
            if row['path'] in journal['completed']:
                continue
            registry, audit, current_rows = _snapshot()
            if audit['registry_sha256'] != registry_sha or current_rows != rows:
                raise ValueError('canonical retirement authority drifted')
            if journal['active'] is None:
                app = _verify_app(row, audit)
                s = app.lstat()
                journal['active'] = {'path': row['path'], 'identity': {k: row[k] for k in IDENTITY},
                                     'phase': 'PREPARED', 'device': s.st_dev, 'inode': s.st_ino,
                                     'entries': _entries(app)}
                _persist(journal)
            elif journal['active']['path'] != row['path']:
                raise ValueError('retirement journal order differs from exact catalog')
            _delete_active(journal, audit, rows, registry_sha=registry_sha)
        return {'status': 'COMPLETED', 'catalog_sha256': CATALOG_SHA,
                'completed': len(journal['completed']), 'max_attributed_bytes': MAX_BYTES}


def _metadata_digest(root: Path) -> str:
    """Bind every remaining file/mode; never mistake a new app for metadata."""
    candidate_archive._path(root, durable=True)
    if not root.is_dir() or root.is_symlink() or (root / 'Integra.app').exists():
        raise ValueError('retirement metadata root is missing, linked, or contains an app')
    s = root.lstat()
    if s.st_uid != os.getuid() or not stat.S_ISDIR(s.st_mode):
        raise ValueError('retirement metadata root has foreign ownership/type')
    _inactive(root)
    entries = candidate_archive._inventory(root)
    for item in entries:
        info = (root / item['path']).lstat()
        if info.st_uid != os.getuid() or (item['type'] == 'file' and info.st_nlink != 1):
            raise ValueError('retirement metadata contains a foreign/hardlinked entry')
    return _digest(entries)


def _load_relocation(registry_sha: str) -> dict:
    if not RELOCATION_JOURNAL.exists():
        return {'schema_version': '1.0', 'catalog_sha256': CATALOG_SHA,
                'registry_sha256': registry_sha, 'completed': [],
                'completed_digests': {}, 'active': None}
    value = json.loads(RELOCATION_JOURNAL.read_text())
    if (set(value) != {'schema_version', 'catalog_sha256', 'registry_sha256',
                       'completed', 'completed_digests', 'active'}
            or value['schema_version'] != '1.0' or value['catalog_sha256'] != CATALOG_SHA
            or value['registry_sha256'] != registry_sha
            or not isinstance(value['completed'], list)
            or len(set(value['completed'])) != len(value['completed'])
            or not isinstance(value['completed_digests'], dict)
            or set(value['completed_digests']) != set(value['completed'])):
        raise ValueError('metadata relocation journal is stale or malformed')
    return value


def _relocate_active(journal: dict, row: dict) -> None:
    job = journal['active']
    if not isinstance(job, dict) or job.get('path') != row['path']:
        raise ValueError('metadata relocation target differs from exact catalog')
    source = BASE / row['path']
    destination = EVIDENCE / row['path']
    candidate_archive._path(source, durable=True)
    candidate_archive._path(destination, durable=True)
    if source.exists() and destination.exists():
        raise ValueError('metadata source/destination collision')
    if source.exists():
        info = source.lstat()
        if ((info.st_dev, info.st_ino) != (job['device'], job['inode'])
                or _metadata_digest(source) != job['inventory_digest']):
            raise ValueError('metadata changed after relocation was prepared')
        destination.parent.mkdir(parents=True, exist_ok=True)
        candidate_archive._path(destination, durable=True)
        if destination.exists():
            raise ValueError('metadata destination appeared before atomic move')
        os.rename(source, destination)
        for parent in (source.parent, destination.parent):
            fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
    if not destination.exists() or source.exists():
        raise ValueError('metadata atomic relocation did not complete')
    info = destination.lstat()
    if ((info.st_dev, info.st_ino) != (job['device'], job['inode'])
            or _metadata_digest(destination) != job['inventory_digest']):
        raise ValueError('relocated metadata inode or bytes differ')
    journal['completed'].append(row['path'])
    journal['completed_digests'][row['path']] = job['inventory_digest']
    journal['active'] = None
    _write_journal(RELOCATION_JOURNAL, journal)


def finalize_paths() -> dict:
    """Atomically preserve metadata elsewhere so all six exact roots disappear."""
    registry, audit, rows = _snapshot()
    registry_sha = audit['registry_sha256']
    if audit['full_copies'] != 2 or audit['unknown_bytes'] != 0 or audit['eligible_bytes'] != 0:
        raise ValueError('exact legacy retirement payload state is not complete')
    with LOCK.open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        retirement = _load(registry_sha)
        if (retirement['active'] is not None
                or retirement['completed'] != [row['path'] for row in rows]):
            raise ValueError('six-app retirement journal is incomplete')
        journal = _load_relocation(registry_sha)
        if any(path not in {row['path'] for row in rows} for path in journal['completed']):
            raise ValueError('relocation completion is outside exact catalog')
        # Verify all six metadata roots before the first move. Completed roots
        # are validated at their exact evidence destinations on resumption.
        for row in rows:
            source, dest = BASE / row['path'], EVIDENCE / row['path']
            if row['path'] in journal['completed']:
                if source.exists() or not dest.exists() or _metadata_digest(dest) != journal.get('completed_digests', {}).get(row['path']):
                    raise ValueError('completed metadata relocation differs')
            elif journal['active'] is None or journal['active'].get('path') != row['path']:
                _metadata_digest(source)
        if not RELOCATION_JOURNAL.exists():
            _write_journal(RELOCATION_JOURNAL, journal)
        for row in rows:
            if row['path'] in journal['completed']:
                continue
            _, current, current_rows = _snapshot()
            if current['registry_sha256'] != registry_sha or current_rows != rows:
                raise ValueError('canonical protection changed before metadata relocation')
            if journal['active'] is None:
                source = BASE / row['path']; info = source.lstat()
                journal['active'] = {'path': row['path'], 'device': info.st_dev,
                                     'inode': info.st_ino,
                                     'inventory_digest': _metadata_digest(source)}
                _write_journal(RELOCATION_JOURNAL, journal)
            elif journal['active']['path'] != row['path']:
                raise ValueError('relocation journal order differs from catalog')
            _relocate_active(journal, row)
        return {'status': 'COMPLETE', 'catalog_sha256': CATALOG_SHA,
                'relocated': len(journal['completed']), 'evidence_root': str(EVIDENCE)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='execute exact owner-authorized retirement')
    parser.add_argument('--finalize-paths', action='store_true',
                        help='atomically preserve metadata and remove six exact source paths')
    args = parser.parse_args()
    if args.apply and args.finalize_paths:
        parser.error('choose one operation')
    print(json.dumps(finalize_paths() if args.finalize_paths else execute(apply=args.apply), sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
