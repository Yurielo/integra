"""Verified cancellation of Integra-owned run processes, outside the UI."""
from __future__ import annotations

import json
import fcntl
import ctypes
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid


def cancellation_path(record_path: Path) -> Path:
    return record_path.with_suffix(".cancel")


def ownership_path(record_path: Path) -> Path:
    return record_path.parent / ".workers" / record_path.name


def requires_shutdown(record_path: Path, record: dict) -> bool:
    if record.get("state") in {"QUEUED", "RUNNING"}:
        return True
    owner_path = ownership_path(record_path)
    if owner_path.is_symlink() or not owner_path.is_file():
        return False
    owner = json.loads(owner_path.read_bytes())
    snapshot = process_snapshot()
    identities = [owner.get("process", {})] + owner.get("observed_processes", [])
    return any(same_birth(item, snapshot.get(item.get("pid"))) for item in identities)


class _BSDInfo(ctypes.Structure):
    # Darwin sys/proc_info.h struct proc_bsdinfo / PROC_PIDTBSDINFO (3).
    _fields_ = [("identity", ctypes.c_uint32 * 12), ("comm", ctypes.c_char * 16),
                ("name", ctypes.c_char * 32), ("details", ctypes.c_uint32 * 6),
                ("start_seconds", ctypes.c_uint64), ("start_microseconds", ctypes.c_uint64)]


def _birth_identity(pid: int) -> str | None:
    if sys.platform == "darwin":
        info = _BSDInfo()
        library = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
        function = library.proc_pidinfo
        function.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_int]
        function.restype = ctypes.c_int
        if function(pid, 3, 0, ctypes.byref(info), ctypes.sizeof(info)) != ctypes.sizeof(info):
            return None
        if info.identity[3] != pid:
            return None
        return f"{info.start_seconds}:{info.start_microseconds}"
    if sys.platform.startswith("linux"):
        try:
            # starttime is field 22; comm may contain spaces or parentheses.
            fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
            return fields[19]
        except (OSError, IndexError):
            return None
    raise ValueError("Shutdown process identity is unsupported on this platform")


def process_snapshot() -> dict:
    result = subprocess.run(["/bin/ps", "-ww", "-axo", "pid=,ppid=,pgid=,lstart=,stat=,command="],
                            capture_output=True, text=True, check=True, timeout=5,
                            env={**os.environ, "LC_ALL": "C"})
    records = {}
    for line in result.stdout.splitlines():
        values = line.strip().split(None, 9)
        if len(values) != 10:
            continue
        try:
            pid, parent, group = map(int, values[:3])
        except ValueError:
            continue
        if values[8].startswith("Z"):
            continue
        birth = _birth_identity(pid)
        if birth is None:
            continue
        records[pid] = {"pid": pid, "parent": parent, "group": group,
                        "started": " ".join(values[3:8]), "command": values[9],
                        "birth": birth, "stopped": values[8].startswith("T")}
    return records


def same_process(left: dict, right: dict | None) -> bool:
    return right is not None and all(left.get(key) == right.get(key)
                                     for key in ("pid", "birth", "group", "started", "command"))


def same_birth(left: dict, right: dict | None) -> bool:
    # A captured child can exec or create a new session without becoming an
    # unrelated process. Kernel birth identity survives both; PID reuse does not.
    return (right is not None and left.get("birth") is not None
            and left.get("pid") == right.get("pid") and left["birth"] == right.get("birth"))


def register_worker(record_path: Path, pid: int, nonce: str) -> None:
    process = process_snapshot().get(pid)
    if process is None or process["group"] != pid or f"--integra-run-owner {nonce}" not in process["command"]:
        raise ValueError("Cannot verify newly launched Integra worker identity")
    target = ownership_path(record_path)
    target.parent.mkdir(exist_ok=True)
    temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps({"schema_version": "1.0", "nonce": nonce, "process": process}))
    os.replace(temporary, target)


def _descendants(snapshot: dict, owned: dict) -> None:
    while True:
        added = {pid: item for pid, item in snapshot.items()
                 if pid not in owned and item["parent"] in owned
                 and same_birth(owned[item["parent"]], snapshot.get(item["parent"]))}
        if not added:
            return
        owned.update(added)


def _signal_owned(identity: dict, sig: int) -> None:
    # Never signal a PID whose recorded process has exited or been replaced.
    if identity.get("birth") is not None and identity["birth"] == _birth_identity(identity["pid"]):
        try:
            os.kill(identity["pid"], sig)
        except ProcessLookupError:
            pass


def cancel_run(project_dir: Path, run_id: str, *, timeout: float = 8) -> dict:
    from .application_runtime import run_path
    path = run_path(project_dir, run_id)
    lock_path = path.with_suffix(".shutdown.lock")
    if lock_path.is_symlink():
        raise ValueError("Shutdown lock is unsafe")
    with lock_path.open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError("Shutdown already in progress for this run") from error
        return _cancel_run(project_dir, run_id, timeout=timeout)


def _cancel_run(project_dir: Path, run_id: str, *, timeout: float) -> dict:
    from .application_runtime import read_run, run_path
    from .user_media import atomic_json, now

    path = run_path(project_dir, run_id)
    record = read_run(project_dir, run_id)
    if not requires_shutdown(path, record):
        return record
    owner_path = ownership_path(path)
    if owner_path.is_symlink() or not owner_path.is_file():
        raise ValueError("Shutdown blocked: active run has no verified worker identity")
    owner = json.loads(owner_path.read_bytes())
    identity = owner.get("process", {})
    nonce = owner.get("nonce")
    if (not isinstance(nonce, str) or not nonce or identity.get("pid") != identity.get("group")
            or f"--integra-run-owner {nonce}" not in identity.get("command", "")):
        raise ValueError("Shutdown blocked: invalid worker ownership record")
    snapshot = process_snapshot()
    current = snapshot.get(identity["pid"])
    if current is not None and not same_process(identity, current):
        raise ValueError("Shutdown blocked: worker PID identity changed; no process was signalled")
    if current is None and not owner.get("observed_processes"):
        latest = read_run(project_dir, run_id)
        if latest["state"] not in {"QUEUED", "RUNNING"}:
            return latest
        raise ValueError("Shutdown blocked: worker exited without verified cleanup evidence")
    # Separate immutable request avoids progress writers erasing cancellation.
    marker = cancellation_path(path)
    if marker.is_symlink():
        raise ValueError("Shutdown cancellation marker is unsafe")
    owned = {identity["pid"]: identity}
    for item in owner.get("observed_processes", []):
        owned[item["pid"]] = item
    _descendants(snapshot, owned)
    owner["observed_processes"] = list(owned.values())
    atomic_json(owner_path, owner)
    started = time.monotonic()
    stopped_by_us = {}
    try:
        # Freeze before termination. Executing a SIGTERM handler can create a
        # new-session child and exit before the next ancestry snapshot. SIGSTOP
        # cannot be intercepted; repeatedly capture until the tree is stable.
        while True:
            snapshot = process_snapshot()
            _descendants(snapshot, owned)
            owner["observed_processes"] = list(owned.values())
            atomic_json(owner_path, owner)
            living = [item for pid, item in owned.items() if same_birth(item, snapshot.get(pid))]
            if not owner.get("tree_frozen") and any(not same_birth(item, snapshot.get(pid)) for pid, item in owned.items()
                   if pid not in stopped_by_us):
                raise ValueError("Shutdown blocked: process exited before its descendants could be verified")
            if all(snapshot[item["pid"]]["stopped"] for item in living):
                owner["tree_frozen"] = True
                atomic_json(owner_path, owner)
                break
            if time.monotonic() - started >= timeout:
                raise ValueError("Shutdown blocked: owned processing did not stop; cancellation is not confirmed")
            for item in living:
                if not snapshot[item["pid"]]["stopped"]:
                    _signal_owned(item, signal.SIGSTOP)
                    stopped_by_us[item["pid"]] = item
            time.sleep(.01)
        # Stop descendants before the leader. No termination handler is run,
        # so the frozen, fully captured tree cannot fork outside ownership.
        # Publish the cooperative request only after capture: otherwise ASR's
        # polling callback can exit during the ownership snapshot itself.
        marker.touch(exist_ok=True)
        for item in reversed(living):
            _signal_owned(item, signal.SIGKILL)
        while True:
            snapshot = process_snapshot()
            if not any(same_birth(item, snapshot.get(pid)) for pid, item in owned.items()):
                break
            if time.monotonic() - started >= timeout:
                raise ValueError("Shutdown blocked: owned processing did not stop; cancellation is not confirmed")
            time.sleep(.01)
    finally:
        # A failed identity lookup or signal must not leave an owned worker
        # suspended forever. Never resume a reused PID or a pre-stopped process.
        for item in stopped_by_us.values():
            _signal_owned(item, signal.SIGCONT)
    # Only after workers stopped may the bridge write final run/job states.
    latest = read_run(project_dir, run_id)
    if latest["state"] != "COMPLETED":
        latest.update(state="CANCELLED", cancelled_at=now(), current_stage=None)
        atomic_json(path, latest)
    jobs_path = project_dir / "jobs.json"
    if jobs_path.is_file() and not jobs_path.is_symlink():
        jobs = json.loads(jobs_path.read_bytes())
        for job in jobs.get("jobs", []):
            if job.get("run_id") == run_id and job.get("state") in {"QUEUED", "RUNNING"}:
                job.update(state="CANCELLED", message="Cancelled with source-first run", updated_at=now())
        atomic_json(jobs_path, jobs)
    return latest
