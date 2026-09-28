#!/usr/bin/env python3
"""Authoritative lifecycle for disposable full-size Integra workspaces.

This module deliberately owns only directories it created and marked before a
build starts.  It is suitable for local candidate builds, release checks and
test harnesses; permanent Candidate archives are outside its authority.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid


MARKER = ".integra-owned-workspace.json"
SCHEMA = "1.0"
DEFAULT_EXPECTED_BYTES = 2_400 * 1024 * 1024
DEFAULT_RESERVE_BYTES = 2 * 1024 * 1024 * 1024
LOCK = ".integra-workspace-reservations.lock"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _atomic_json(path: Path, value: dict) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}")
    with temporary.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, sort_keys=True, separators=(",", ":"))
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _process_start_token(pid: int) -> str | None:
    if pid <= 0:
        return None
    result = subprocess.run(["/bin/ps", "-o", "lstart=", "-p", str(pid)], capture_output=True,
                            text=True, check=False, timeout=5)
    token = result.stdout.strip()
    return token or None


def _process_is_live(identity: dict | None) -> bool:
    if not isinstance(identity, dict):
        return False
    pid, token = identity.get("pid"), identity.get("start_token")
    return isinstance(pid, int) and isinstance(token, str) and _process_start_token(pid) == token


def _group_is_live(process_group: int | None) -> bool:
    if not isinstance(process_group, int) or process_group <= 0:
        return False
    try:
        os.killpg(process_group, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _base(value: str | Path | None) -> Path:
    path = Path(value or os.environ.get("INTEGRA_WORKSPACE_ROOT") or "/private/tmp").expanduser().resolve(strict=True)
    if path.is_symlink() or not path.is_dir():
        raise ValueError("owned workspace base must be an existing non-symlink directory")
    return path


def _marker_path(root: Path) -> Path:
    return root / MARKER


def _load(root: str | Path) -> tuple[Path, dict]:
    path = Path(root).expanduser().resolve(strict=True)
    if path.is_symlink() or not path.is_dir() or path.stat().st_uid != os.getuid():
        raise ValueError("workspace is not a safe current-user directory")
    marker = _marker_path(path)
    if marker.is_symlink() or not marker.is_file():
        raise ValueError("workspace lacks the required ownership marker")
    value = json.loads(marker.read_text(encoding="utf-8"))
    required = {"schema_version", "artifact_type", "root", "purpose", "created_at", "run_id",
                "expected_bytes", "reserve_bytes", "owner", "child", "state", "events"}
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError("workspace ownership marker schema differs from lifecycle contract")
    if value["schema_version"] != SCHEMA or value["artifact_type"] != "integra.disposable_workspace":
        raise ValueError("workspace ownership marker is not an Integra lifecycle marker")
    if value["root"] != str(path) or not isinstance(value["purpose"], str) or not value["purpose"]:
        raise ValueError("workspace ownership marker does not bind this directory")
    if not isinstance(value["expected_bytes"], int) or not isinstance(value["reserve_bytes"], int):
        raise ValueError("workspace reservation is invalid")
    if not isinstance(value["owner"], dict) or not isinstance(value["child"], dict) or not isinstance(value["events"], list):
        raise ValueError("workspace ownership marker is malformed")
    return path, value


@contextmanager
def _reservation_lock(base: Path):
    lock = base / LOCK
    descriptor = os.open(lock, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _live_reservations(base: Path) -> int:
    reserved = 0
    for child in base.iterdir():
        if child.is_symlink() or not child.is_dir() or not _marker_path(child).is_file():
            continue
        try:
            _, marker = _load(child)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if _process_is_live(marker["owner"]) or _process_is_live(marker["child"]) or _group_is_live(marker["child"].get("process_group")):
            reserved += marker["expected_bytes"]
    return reserved


def create_workspace(*, purpose: str, base: str | Path | None = None,
                     expected_bytes: int = DEFAULT_EXPECTED_BYTES,
                     reserve_bytes: int = DEFAULT_RESERVE_BYTES) -> tuple[Path, dict]:
    if not purpose.replace("-", "").replace("_", "").isalnum():
        raise ValueError("purpose must contain only letters, numbers, '-' or '_'")
    if expected_bytes < 0 or reserve_bytes < 0:
        raise ValueError("workspace byte reservations must be non-negative")
    root_base = _base(base)
    with _reservation_lock(root_base):
        live = _live_reservations(root_base)
        free = shutil.disk_usage(root_base).free
        required = expected_bytes + reserve_bytes + live
        if free < required:
            raise ValueError(
                f"insufficient disk for owned workspace: need {required} bytes "
                f"({expected_bytes} expected + {reserve_bytes} reserve + {live} live reservations), have {free}"
            )
        root = Path(tempfile.mkdtemp(prefix=f"integra-owned-{purpose}-", dir=root_base)).resolve(strict=True)
        os.chmod(root, 0o700)
        owner = {"pid": os.getpid(), "start_token": _process_start_token(os.getpid())}
        if owner["start_token"] is None:
            shutil.rmtree(root)
            raise ValueError("unable to establish owner process identity")
        marker = {
            "schema_version": SCHEMA,
            "artifact_type": "integra.disposable_workspace",
            "root": str(root),
            "purpose": purpose,
            "created_at": _now(),
            "run_id": uuid.uuid4().hex,
            "expected_bytes": expected_bytes,
            "reserve_bytes": reserve_bytes,
            "owner": owner,
            "child": {},
            "state": "CREATED",
            "events": [{"at": _now(), "event": "CREATED", "free_bytes": free, "reserved_bytes": live}],
        }
        _atomic_json(_marker_path(root), marker)
    return root, marker


def _record(root: Path, marker: dict, event: str, *, child: dict | None = None,
            state: str | None = None, **extra: object) -> dict:
    marker = {**marker}
    if child is not None:
        marker["child"] = child
    if state is not None:
        marker["state"] = state
    marker["events"] = [*marker["events"], {"at": _now(), "event": event, **extra}]
    _atomic_json(_marker_path(root), marker)
    return marker


def _terminate_group(process_group: int | None, *, grace_seconds: float = 5) -> None:
    if not _group_is_live(process_group):
        return
    try:
        os.killpg(process_group, signal.SIGTERM)
    except ProcessLookupError:
        return
    except PermissionError:
        # The caller must not widen its authority by signalling a group it
        # cannot prove it controls. The root process is handled separately.
        return
    deadline = time.monotonic() + grace_seconds
    while time.monotonic() < deadline:
        if not _group_is_live(process_group):
            return
        time.sleep(.05)
    try:
        os.killpg(process_group, signal.SIGKILL)
    except ProcessLookupError:
        return
    except PermissionError:
        return


def cleanup_workspace(root: str | Path, *, reason: str, allow_live_owner: bool = False) -> bool:
    # Cleanup is deliberately idempotent: an already-removed owned root is a
    # successful terminal state, while a present root must still prove ownership.
    requested = Path(root).expanduser()
    if not requested.exists():
        return False
    path, marker = _load(root)
    if not allow_live_owner and (_process_is_live(marker["owner"]) or _process_is_live(marker["child"]) or _group_is_live(marker["child"].get("process_group"))):
        raise ValueError("refusing to remove live owned workspace")
    _terminate_group(marker["child"].get("process_group"))
    marker = _record(path, marker, "CLEANUP", reason=reason)
    shutil.rmtree(path)
    return True


def reap_stale(*, base: str | Path | None = None) -> dict:
    root_base = _base(base)
    removed, skipped = [], []
    with _reservation_lock(root_base):
        for child in sorted(root_base.iterdir()):
            if child.is_symlink() or not child.is_dir() or not _marker_path(child).is_file():
                continue
            try:
                root, marker = _load(child)
                if _process_is_live(marker["owner"]) or _process_is_live(marker["child"]) or _group_is_live(marker["child"].get("process_group")):
                    skipped.append({"root": str(root), "reason": "LIVE_OWNER_OR_CHILD"})
                    continue
                cleanup_workspace(root, reason="STALE_REAP", allow_live_owner=False)
                removed.append(str(root))
            except (OSError, ValueError, json.JSONDecodeError) as error:
                skipped.append({"root": str(child), "reason": f"UNPROVEN_OWNERSHIP:{error}"})
    return {"removed": removed, "skipped": skipped}


def run_owned(args: argparse.Namespace) -> int:
    root, marker = create_workspace(purpose=args.purpose, base=args.base,
                                    expected_bytes=args.expected_bytes, reserve_bytes=args.reserve_bytes)
    child: subprocess.Popen | None = None
    interrupted = {"signal": None}

    def cancel(signum: int, _frame: object) -> None:
        interrupted["signal"] = signal.Signals(signum).name
        if child is not None:
            child.terminate()
            _terminate_group(child.pid, grace_seconds=1)
        raise KeyboardInterrupt

    previous = {item: signal.getsignal(item) for item in (signal.SIGINT, signal.SIGTERM)}
    signal.signal(signal.SIGINT, cancel)
    signal.signal(signal.SIGTERM, cancel)
    outcome = 1
    try:
        environment = os.environ | {"INTEGRA_OWNED_WORKSPACE": str(root), "TMPDIR": str(root / "tmp")}
        (root / "tmp").mkdir(mode=0o700)
        argv = args.argv[1:] if args.argv[:1] == ["--"] else args.argv
        child = subprocess.Popen(argv, cwd=root, env=environment, start_new_session=True)
        marker = _record(root, marker, "CHILD_STARTED", state="RUNNING", child={"pid": child.pid,
                         "start_token": _process_start_token(child.pid), "process_group": child.pid})
        try:
            result = child.wait(timeout=args.timeout_seconds)
        except subprocess.TimeoutExpired:
            child.terminate()
            _terminate_group(child.pid)
            marker = _record(root, marker, "TIMEOUT", state="TIMED_OUT", timeout_seconds=args.timeout_seconds)
            outcome = 124
        else:
            marker = _record(root, marker, "CHILD_EXITED", state="FINISHED", exit_code=result)
            outcome = result
    except KeyboardInterrupt:
        marker = _record(root, marker, "CANCELLED", state="CANCELLED", signal=interrupted["signal"])
        outcome = 128
    finally:
        for item, handler in previous.items():
            signal.signal(item, handler)
        if root.exists():
            try:
                cleanup_workspace(root, reason="RUN_FINISHED", allow_live_owner=True)
            except (OSError, ValueError) as error:
                print(f"INTEGRA_TEMP_LIFECYCLE: cleanup failed: {error}", file=sys.stderr)
                # Never report a completed command when its owned workspace
                # could not be removed. A marked root remains available for a
                # later conservative stale reaper.
                outcome = 1
    return outcome


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)
    create = commands.add_parser("create")
    create.add_argument("--purpose", required=True)
    create.add_argument("--base")
    create.add_argument("--expected-bytes", type=int, default=DEFAULT_EXPECTED_BYTES)
    create.add_argument("--reserve-bytes", type=int, default=DEFAULT_RESERVE_BYTES)
    create.set_defaults(handler=lambda a: print(create_workspace(purpose=a.purpose, base=a.base, expected_bytes=a.expected_bytes, reserve_bytes=a.reserve_bytes)[0]) or 0)
    inspect = commands.add_parser("inspect")
    inspect.add_argument("--root", required=True)
    inspect.set_defaults(handler=lambda a: print(json.dumps(_load(a.root)[1], sort_keys=True)) or 0)
    cleanup = commands.add_parser("cleanup")
    cleanup.add_argument("--root", required=True)
    cleanup.add_argument("--reason", default="EXPLICIT")
    cleanup.add_argument("--allow-live-owner", action="store_true")
    cleanup.set_defaults(handler=lambda a: int(not cleanup_workspace(a.root, reason=a.reason, allow_live_owner=a.allow_live_owner)))
    reap = commands.add_parser("reap-stale")
    reap.add_argument("--base")
    reap.set_defaults(handler=lambda a: print(json.dumps(reap_stale(base=a.base), sort_keys=True)) or 0)
    run = commands.add_parser("run")
    run.add_argument("--purpose", required=True)
    run.add_argument("--base")
    run.add_argument("--expected-bytes", type=int, default=DEFAULT_EXPECTED_BYTES)
    run.add_argument("--reserve-bytes", type=int, default=DEFAULT_RESERVE_BYTES)
    run.add_argument("--timeout-seconds", type=float, default=3600)
    run.add_argument("argv", nargs=argparse.REMAINDER)
    run.set_defaults(handler=run_owned)
    args = parser.parse_args()
    if args.operation == "run":
        if not args.argv or args.argv == ["--"]:
            parser.error("run requires a command after --")
        if args.timeout_seconds <= 0:
            parser.error("timeout must be positive")
    try:
        return args.handler(args)
    except (OSError, ValueError, json.JSONDecodeError, subprocess.SubprocessError) as error:
        print(f"INTEGRA_TEMP_LIFECYCLE: FAIL: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
