#!/usr/bin/env python3
"""Ownership-bound lifecycle for disposable Integra build/test scratch roots.

This tool intentionally never discovers directories by an ``integra*`` glob.
It acts only on a root carrying the exact marker it created, and stale reaping
skips a live owner process.  Retained Candidate/evidence roots use a different
policy and are never removed by the automatic reaper.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import uuid

MARKER = ".integra-temp-artifact.json"
POLICIES = {"AUTO_CLEANUP", "RETAIN_EVIDENCE"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _process_token(pid: int) -> str | None:
    if pid <= 0:
        return None
    result = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], text=True,
                            capture_output=True, check=False)
    token = result.stdout.strip()
    return token or None


def _marker_path(root: Path) -> Path:
    return root / MARKER


def _load(root: Path) -> dict:
    root = root.resolve(strict=True)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("temporary root is unsafe")
    path = _marker_path(root)
    if path.is_symlink() or not path.is_file():
        raise ValueError("temporary root lacks an Integra ownership marker")
    value = json.loads(path.read_text(encoding="utf-8"))
    required = {"schema_version", "artifact_type", "root", "purpose", "created_at", "cleanup_policy", "owner"}
    if not isinstance(value, dict) or set(value) != required or value.get("schema_version") != "1.0" or value.get("artifact_type") != "integra.temporary_artifact_root":
        raise ValueError("temporary ownership marker is invalid")
    if value.get("root") != str(root) or value.get("cleanup_policy") not in POLICIES:
        raise ValueError("temporary ownership marker does not bind this root")
    owner = value.get("owner")
    if not isinstance(owner, dict) or set(owner) != {"pid", "process_start_token", "run_token"} or not isinstance(owner["pid"], int) or not isinstance(owner["run_token"], str):
        raise ValueError("temporary ownership marker owner is invalid")
    return value


def _owner_live(marker: dict) -> bool:
    owner = marker["owner"]
    token = _process_token(owner["pid"])
    return token is not None and token == owner["process_start_token"]


def _safe_delete(root: Path, marker: dict, *, allow_live: bool) -> None:
    if marker["cleanup_policy"] != "AUTO_CLEANUP":
        raise ValueError("retained evidence root is not eligible for automatic cleanup")
    if not allow_live and _owner_live(marker):
        raise ValueError("temporary root belongs to a live process")
    # ``root`` was resolved and marker-bound before deletion; never accept a
    # caller glob, parent path, or a symlink as a cleanup target.
    shutil.rmtree(root)


def create(args: argparse.Namespace) -> int:
    base = Path(args.base or os.environ.get("TMPDIR") or "/private/tmp").expanduser().resolve(strict=True)
    if base.is_symlink() or not base.is_dir():
        raise ValueError("temporary base is unsafe")
    if args.policy not in POLICIES:
        raise ValueError("invalid cleanup policy")
    if args.required_bytes:
        free = shutil.disk_usage(base).free
        required = args.required_bytes + args.reserve_bytes
        if free < required:
            raise ValueError(
                f"insufficient free space for owned build: need {required} bytes "
                f"({args.required_bytes} build + {args.reserve_bytes} reserve), have {free}"
            )
    pid = args.owner_pid if args.owner_pid is not None else os.getppid()
    token = _process_token(pid)
    if token is None:
        raise ValueError("temporary owner process is unavailable")
    root = Path(tempfile.mkdtemp(prefix=f"integra-scratch-{args.purpose}-", dir=base)).resolve(strict=True)
    value = {"schema_version": "1.0", "artifact_type": "integra.temporary_artifact_root",
             "root": str(root), "purpose": args.purpose, "created_at": _now(),
             "cleanup_policy": args.policy,
             "owner": {"pid": pid, "process_start_token": token, "run_token": uuid.uuid4().hex}}
    _marker_path(root).write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")
    print(root)
    return 0


def cleanup(args: argparse.Namespace) -> int:
    root = Path(args.root)
    marker = _load(root)
    _safe_delete(root.resolve(strict=True), marker, allow_live=args.allow_live_owner)
    return 0


def inspect(args: argparse.Namespace) -> int:
    marker = _load(Path(args.root))
    print(json.dumps(marker | {"owner_live": _owner_live(marker)}, sort_keys=True))
    return 0


def reap(args: argparse.Namespace) -> int:
    base = Path(args.base or os.environ.get("TMPDIR") or "/private/tmp").expanduser().resolve(strict=True)
    removed: list[str] = []
    skipped: list[str] = []
    for child in sorted(base.iterdir()):
        marker_path = child / MARKER
        if child.is_symlink() or not child.is_dir() or marker_path.is_symlink() or not marker_path.is_file():
            continue
        try:
            marker = _load(child)
            if marker["cleanup_policy"] != "AUTO_CLEANUP" or _owner_live(marker):
                skipped.append(str(child)); continue
            _safe_delete(child.resolve(strict=True), marker, allow_live=False)
            removed.append(str(child))
        except (OSError, ValueError, json.JSONDecodeError):
            # A nonconforming directory is never ours to remove.
            skipped.append(str(child))
    print(json.dumps({"removed": removed, "skipped": skipped}, sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage owned disposable Integra artifact roots")
    sub = parser.add_subparsers(dest="command", required=True)
    create_parser = sub.add_parser("create")
    create_parser.add_argument("--purpose", required=True)
    create_parser.add_argument("--policy", default="AUTO_CLEANUP", choices=sorted(POLICIES))
    create_parser.add_argument("--base")
    create_parser.add_argument("--owner-pid", type=int)
    create_parser.add_argument("--required-bytes", type=int, default=0)
    create_parser.add_argument("--reserve-bytes", type=int, default=0)
    create_parser.set_defaults(handler=create)
    cleanup_parser = sub.add_parser("cleanup")
    cleanup_parser.add_argument("--root", required=True)
    cleanup_parser.add_argument("--allow-live-owner", action="store_true")
    cleanup_parser.set_defaults(handler=cleanup)
    inspect_parser = sub.add_parser("inspect")
    inspect_parser.add_argument("--root", required=True)
    inspect_parser.set_defaults(handler=inspect)
    reap_parser = sub.add_parser("reap")
    reap_parser.add_argument("--base")
    reap_parser.set_defaults(handler=reap)
    args = parser.parse_args()
    try:
        return args.handler(args)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"INTEGRA_TEMP_ARTIFACT: FAIL: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
