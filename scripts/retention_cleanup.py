"""Durable, resumable cleanup of publisher-bound terminal packages only."""
import json
import os
from pathlib import Path
import stat
import time
import uuid


def _entries(r, package):
    expected = json.loads((package / 'inventory.json').read_text())
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


def _guard(r, catalog, job, package, *, transaction=False):
    context = catalog.get('protection') or {}
    cid = job['identity']['candidate_id']
    selected = context.get('selected_archives', {}).get(cid)
    # Canonical authorization is captured at the atomic package withdrawal
    # boundary and refreshed before every resumed transaction. Individual
    # entries belong to that same committed immutable package operation.
    context_valid = (r._digest(context) == job.get('transaction_context_sha256')
                     if transaction else r._context_valid(context))
    if not context_valid or (cid in context.get('protected', {}) and (not selected or selected in (job['source'], job['trash']))) or job['record'].get('pin_ref'):
        raise ValueError('cleanup protection authority changed or is unavailable')
    s = r._safe(package).lstat()
    if (s.st_dev, s.st_ino) != (job['device'], job['inode']) or s.st_uid != os.getuid() or not stat.S_ISDIR(s.st_mode) or r._publisher_live(job['record']) or not r._inactive(package):
        raise ValueError('cleanup owner/identity/activity changed')


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


def _execute(r, path, catalog, token):
    job = catalog['deletions'][token]
    source, trash = Path(job['source']), Path(job['trash'])
    if source.exists() and trash.exists():
        raise ValueError('cleanup source/trash collision; recovery requires review')
    package = source if source.exists() else trash
    if not package.exists():
        if job['phase'] != 'DELETING':
            raise ValueError('prepared cleanup package disappeared')
        if not r._context_valid(catalog.get('protection')):
            raise ValueError('cleanup recovery protection context is unavailable')
        _finish_container(catalog, job)
        catalog['artifacts'].pop(job['source'], None)
        del catalog['deletions'][token]; r._persist(path, catalog)
        return job['source']
    _guard(r, catalog, job, package)
    entries = _remaining(r, package, job, hash_bytes=True)
    if package == source:
        try:
            from scripts.candidate_archive import _publish
        except ModuleNotFoundError:
            from candidate_archive import _publish
        _guard(r, catalog, job, source)
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
    expected = {e['path']: e for e in job['entries']}
    deadline = time.monotonic() + 900
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
    _guard(r, catalog, job, trash, transaction=True)
    os.rmdir(trash)
    # Remove only the now-empty owned Candidate container. Otherwise repeated
    # promotion would still accumulate top-level candidate-v1-* directories.
    _finish_container(catalog, job)
    catalog['artifacts'].pop(job['source'], None)
    del catalog['deletions'][token]; r._persist(path, catalog)
    return job['source']


def recover(r, path, catalog):
    try:
        from scripts.candidate_archive import verify_archive
    except ModuleNotFoundError:
        from candidate_archive import verify_archive
    if catalog.get('deletions'):
        if not r._context_valid(catalog.get('protection')):
            raise ValueError('cleanup recovery protection context is unavailable')
        for receipt in catalog['protection']['verified_survivors'].values():
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
        targets = [e for e in snapshot['entries'] if e['classification'] == 'DELETABLE']
        for e in targets:
            if e['historical']:
                raise ValueError('historical archive adoption/deletion requires separate Human Gate')
            package = r._safe(e['path'])
            if (package / '.git').exists() or not r._inactive(package):
                raise ValueError('active/worktree archive cannot be deleted')
            verify_archive(package, {k: e[k] for k in ('candidate_id', 'bundle_digest', 'manifest_digest')})
        for e in targets:
            package = r._safe(e['path']); token = uuid.uuid4().hex
            record = catalog['artifacts'][str(package)]
            if not r._ownership(package, record, json.loads((package / 'COMPLETE.json').read_text())):
                raise ValueError('publisher ownership changed')
            job = {'source': str(package), 'trash': str(package.parent / ('.retention-trash-' + token)),
                   'phase': 'PREPARED', 'identity': {k: e[k] for k in ('candidate_id', 'bundle_digest', 'manifest_digest')},
                   'device': e['device'], 'inode': e['inode'], 'record': record,
                   'entries': _entries(r, package)}
            captured = {e['path']: e for e in job['entries']}
            if captured['inventory.json']['sha256'] != record['inventory_sha256'] or captured['COMPLETE.json']['sha256'] != record['complete_sha256']:
                raise ValueError('cleanup journal metadata differs from publisher authority')
            _guard(r, catalog, job, package)
            catalog['deletions'][token] = job; r._persist(path, catalog)
            deleted.append(_execute(r, path, catalog, token))
    return deleted
