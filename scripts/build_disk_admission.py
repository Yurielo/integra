"""Atomic disk admission shared by build workspaces and archive copies.

Reservations are keyed by user and filesystem device, rather than a caller's
chosen workspace directory. Already allocated bytes remain part of free-space
accounting, so retaining the full reservation is deliberately conservative.
"""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import uuid
import time
import sys


def _start(pid):
    return subprocess.run(['/bin/ps', '-o', 'lstart=', '-p', str(pid)],
                          capture_output=True, text=True, timeout=5).stdout.strip()


def _live(record):
    if _start(record['pid']) == record['start_token']:
        return True
    group = record.get('process_group')
    if group:
        try:
            os.killpg(group, 0)
            return True
        except ProcessLookupError:
            pass
        except PermissionError:
            return True
    # A killed owner before child registration may have left an unregistered
    # writer. The workspace reaper must resolve that marker before admission.
    return bool(record.get('workspace') and Path(record['workspace']).exists())


def _paths(target):
    target = Path(target).resolve()
    while not target.exists():
        target = target.parent
    # Do not use tempfile.gettempdir(): TMPDIR inside an owned child points
    # into that child's workspace and would split the global ledger again.
    ledger_base = Path('/private/tmp' if sys.platform == 'darwin' else '/tmp')
    stem = ledger_base / f'.integra-disk-{os.getuid()}-{target.stat().st_dev}'
    return target, stem.with_suffix('.lock'), stem.with_suffix('.json')


@contextmanager
def _ledger(target):
    target, lock, path = _paths(target)
    descriptor = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        if os.fstat(descriptor).st_uid != os.getuid():
            raise ValueError('disk admission lock belongs to another user')
        deadline = time.monotonic() + 30
        while True:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise ValueError('disk admission lock timed out')
                time.sleep(.05)
        records = {}
        if path.exists() or path.is_symlink():
            if path.is_symlink() or path.stat().st_uid != os.getuid():
                raise ValueError('disk admission ledger ownership is unproven')
            records = json.loads(path.read_text())
            if not isinstance(records, dict):
                raise ValueError('disk admission ledger is invalid')
        yield target, records
        fd, name = tempfile.mkstemp(prefix=path.name + '.', dir=path.parent)
        try:
            with os.fdopen(fd, 'w') as handle:
                json.dump(records, handle, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(name, path)
        finally:
            if Path(name).exists():
                Path(name).unlink()
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def reserve(target, expected_bytes, reserve_bytes, *, reservation_id=None):
    if type(expected_bytes) is not int or type(reserve_bytes) is not int or min(expected_bytes, reserve_bytes) < 0:
        raise ValueError('disk admission sizes must be non-negative integers')
    identity = reservation_id or uuid.uuid4().hex
    with _ledger(target) as (anchor, records):
        retained = {key: item for key, item in records.items() if _live(item)}
        live_bytes = sum(item['expected_bytes'] for item in retained.values())
        free = shutil.disk_usage(anchor).free
        required = expected_bytes + reserve_bytes + live_bytes
        if free < required:
            raise ValueError(f'insufficient disk space: need {required} bytes ({expected_bytes} expected + '
                             f'{reserve_bytes} reserve + {live_bytes} live reservations), have {free}')
        if identity in retained:
            raise ValueError('disk reservation identity already exists')
        token = _start(os.getpid())
        if not token:
            raise ValueError('disk reservation owner identity is unavailable')
        records.clear()
        records.update(retained)
        records[identity] = {'pid': os.getpid(), 'start_token': token,
                             'expected_bytes': expected_bytes, 'workspace': None,
                             'process_group': None}
    return identity, free, live_bytes


def bind(target, reservation_id, *, workspace=None, process_group=None):
    with _ledger(target) as (_, records):
        record = records[reservation_id]
        if record['pid'] != os.getpid() or record['start_token'] != _start(os.getpid()):
            raise ValueError('disk reservation owner differs')
        if workspace is not None:
            record['workspace'] = str(Path(workspace).resolve())
        if process_group is not None:
            record['process_group'] = process_group


def release(target, reservation_id):
    with _ledger(target) as (_, records):
        records.pop(reservation_id, None)


def stale_workspaces(target):
    """Snapshot dead owners on this volume; caller must prove marker ownership.

    Release the ledger lock before cleanup, which itself releases a lease.
    A changed staging ancestor must not hide an interrupted archive copy.
    """
    with _ledger(target) as (_, records):
        return [record['workspace'] for record in records.values()
                if record.get('workspace') and _start(record['pid']) != record['start_token']]
