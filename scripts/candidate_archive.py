#!/usr/bin/env python3
"""Retain local Candidate bytes, not runtime readiness or release authority.

Packages are keyed by candidate ID AND bundle digest. Verification is offline:
validate_manifest + tree_sha256, not validate_bundle's live external-runtime
checks. No archive is overwritten or pruned, including incomplete attempts.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from integra_core.candidate_identity import (  # noqa: E402
    MANIFEST_NAME, canonical_bytes, tree_sha256, validate_manifest,
)

APP = "Integra.app"
EMBEDDED = "Contents/Resources/" + MANIFEST_NAME
INVENTORY = "inventory.json"
COMPLETE = "COMPLETE.json"
RESERVE_BYTES = 256 * 1024 * 1024
IDENTITY_KEYS = {"candidate_id", "bundle_digest", "manifest_digest"}


def path_is_within(path: Path, root: Path) -> bool:
    """Compare existing ancestors by filesystem identity, missing tails lexically.

    resolve() alone does not canonicalize case aliases on macOS. A root that
    does not yet exist is represented by its nearest existing ancestor plus
    the remaining path components; unrelated future siblings stay distinct.
    """
    path = Path(path).expanduser().resolve()
    root = Path(root).expanduser().resolve()
    anchor = root
    missing: tuple[str, ...] = ()
    while True:
        try:
            anchor.stat()
            break
        except FileNotFoundError:
            missing = (anchor.name, *missing)
            anchor = anchor.parent
    for ancestor in (path, *path.parents):
        try:
            if ancestor.samefile(anchor):
                return path.relative_to(ancestor).parts[:len(missing)] == missing
        except (FileNotFoundError, NotADirectoryError):
            continue
    return False


def _path(path: Path, *, durable: bool = False) -> Path:
    path = Path(path).expanduser()
    if ".." in path.parts:
        raise ValueError("parent traversal is not allowed")
    path = path.absolute()
    for part in (*reversed(path.parents), path):
        if part.is_symlink():
            raise ValueError(f"symlink path is not allowed: {part}")
    if durable:
        temporary = {"/tmp", "/private/tmp", "/var/tmp", "/private/var/tmp", "/dev/shm", "/run",
                     "/var/folders", "/private/var/folders", "/var/run", "/private/var/run",
                     tempfile.gettempdir()}
        temporary.update(os.environ[key] for key in ("TMPDIR", "TMP", "TEMP", "XDG_RUNTIME_DIR")
                         if os.environ.get(key))
        if any(path_is_within(path, Path(item)) for item in temporary):
            raise ValueError("archive destination must not be under a temporary root")
    return path


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _entry(path: Path, relative: str) -> dict:
    info = path.lstat()
    mode = stat.S_IMODE(info.st_mode)
    if stat.S_ISDIR(info.st_mode):
        return {"path": relative, "type": "directory", "mode": mode}
    if not stat.S_ISREG(info.st_mode):
        raise ValueError(f"only regular files and directories may be retained: {path}")
    return {"path": relative, "type": "file", "mode": mode,
            "size": info.st_size, "sha256": _hash(path)}


def _inventory(root: Path, *, exclude: set[str] | None = None) -> list[dict]:
    def fail(error: OSError) -> None:
        raise error

    if not stat.S_ISDIR(root.lstat().st_mode):
        raise ValueError("archive/app root must be a directory")
    entries = []
    for directory, dirs, files in os.walk(root, followlinks=False, onerror=fail):
        for name in sorted(dirs + files):
            path = Path(directory) / name
            relative = path.relative_to(root).as_posix()
            # Check the type even for metadata excluded from its own inventory.
            item = _entry(path, relative)
            if relative not in (exclude or set()):
                entries.append(item)
    return sorted(entries, key=lambda item: item["path"])


def _identity(app: Path) -> dict:
    manifest = app / EMBEDDED
    value = json.loads(manifest.read_text(encoding="utf-8"))
    validate_manifest(value)
    if tree_sha256(app, exclude={EMBEDDED}) != value["bundle"]["digest"]:
        raise ValueError("candidate bundle bytes differ from manifest")
    return {"candidate_id": value["candidate_id"], "bundle_digest": value["bundle"]["digest"],
            "manifest_digest": _hash(manifest)}


def _expect(actual: dict, expected: dict | None) -> None:
    if expected is None:
        return
    if not isinstance(expected, dict) or not set(expected) <= IDENTITY_KEYS:
        raise ValueError("unsupported expected archive identity fields")
    for key, value in expected.items():
        if not isinstance(value, str) or actual[key] != value:
            raise ValueError(f"archive {key} differs from expected identity")


def _receipt(identity: dict, inventory: list[dict], inventory_digest: str) -> dict:
    files = [item for item in inventory if item["type"] == "file"]
    return {"schema_version": "1.0", "artifact_type": "integra.candidate_archive",
            "status": "COMPLETE", "verification": "ARCHIVAL_BYTE_INTEGRITY",
            "runtime_validation": "NOT_PERFORMED", **identity,
            "inventory_sha256": inventory_digest, "file_count": len(files),
            "app_size_bytes": sum(item["size"] for item in files if item["path"].startswith(APP + "/")),
            "retained_size_bytes": sum(item["size"] for item in files)}


def _verify(archive: Path, expected: dict | None, *, check_key: bool = True) -> dict:
    inventory = _inventory(archive, exclude={INVENTORY, COMPLETE})
    for item in inventory + [{"path": INVENTORY, "type": "file"}, {"path": COMPLETE, "type": "file"}]:
        if item["type"] == "file" and (archive / item["path"]).lstat().st_nlink != 1:
            raise ValueError("retained files must not be hardlinked")
    # Metadata without the actual application can never be retention evidence.
    identity = _identity(archive / APP)
    _expect(identity, expected)
    if check_key and (archive.name != identity["bundle_digest"] or archive.parent.name != identity["candidate_id"]):
        raise ValueError("archive directory does not bind candidate and bundle identities")
    retained = archive / MANIFEST_NAME
    validate_manifest(json.loads(retained.read_text(encoding="utf-8")))
    if _hash(retained) != identity["manifest_digest"]:
        raise ValueError("retained and embedded candidate manifests differ")
    if json.loads((archive / INVENTORY).read_text(encoding="utf-8")) != inventory:
        raise ValueError("archive checksum/permission inventory differs from disk")
    receipt = _receipt(identity, inventory, _hash(archive / INVENTORY))
    if json.loads((archive / COMPLETE).read_text(encoding="utf-8")) != receipt:
        raise ValueError("archive COMPLETE receipt differs from verified disk bytes")
    return {**receipt, "archive_path": str(archive)}


def verify_archive(archive: Path, expected: dict | None = None) -> dict:
    """Rehash a durable package offline; return a fresh receipt or ValueError."""
    try:
        return _verify(_path(archive, durable=True), expected)
    except (OSError, TypeError, KeyError, UnicodeError) as error:
        raise ValueError(f"archive verification failed: {error}") from error


def _write_json(path: Path, value: object) -> None:
    with path.open("xb") as handle:
        handle.write(canonical_bytes(value) + b"\n")
        handle.flush()
        os.fsync(handle.fileno())


def _sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _publish(stage: Path, destination: Path) -> None:
    """Atomic no-replace rename, including a concurrently created empty target."""
    library = ctypes.CDLL(None, use_errno=True)
    if sys.platform == "darwin":
        rename = library.renamex_np
        rename.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        result = rename(os.fsencode(stage), os.fsencode(destination), 0x00000004)  # RENAME_EXCL
    elif sys.platform.startswith("linux") and hasattr(library, "renameat2"):
        rename = library.renameat2
        rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        result = rename(-100, os.fsencode(stage), -100, os.fsencode(destination), 1)  # RENAME_NOREPLACE
    else:
        raise ValueError("atomic no-replace archive publication is unsupported on this platform")
    if result:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), str(destination))


def create_archive(app: Path, archive_root: Path, *, manifest: Path | None = None,
                   evidence: list[Path] | None = None, reserve_bytes: int = RESERVE_BYTES) -> dict:
    """Copy and verify a fresh immutable package; preserve partial attempts."""
    stage = None
    try:
        app = _path(app)
        root = _path(archive_root, durable=True)
        if path_is_within(root, app) or path_is_within(app, root):
            raise ValueError("archive and source app must not overlap")
        if type(reserve_bytes) is not int or reserve_bytes < RESERVE_BYTES:
            raise ValueError(f"disk reserve must be at least {RESERVE_BYTES} bytes")
        source_entries = [_entry(app, APP)] + [
            {**item, "path": APP + "/" + item["path"]} for item in _inventory(app)]
        identity = _identity(app)
        retained_manifest = _path(manifest) if manifest is not None else app / EMBEDDED
        retained_entry = _entry(retained_manifest, MANIFEST_NAME)
        if retained_entry["type"] != "file" or retained_entry["sha256"] != identity["manifest_digest"]:
            raise ValueError("external retained manifest must exactly match embedded manifest")
        evidence_sources = [_path(path) for path in (evidence or [])]
        evidence_entries = [_entry(path, f"evidence/{index:04d}-{path.name}")
                            for index, path in enumerate(evidence_sources)]
        if any(item["type"] != "file" for item in evidence_entries):
            raise ValueError("retained evidence must be a regular file")
        planned = source_entries + [retained_entry] + evidence_entries
        if evidence_entries:
            planned.append({"path": "evidence", "type": "directory", "mode": 0o700})
        planned.sort(key=lambda item: item["path"])
        destination = root / identity["candidate_id"] / identity["bundle_digest"]
        _path(destination, durable=True)
        if destination.exists():
            receipt = verify_archive(destination, identity)
            if _inventory(destination, exclude={INVENTORY, COMPLETE}) != planned:
                raise ValueError("existing archive differs from requested retained files/permissions")
            return receipt
        ancestor = root
        while not ancestor.exists():
            ancestor = ancestor.parent
        block = max(4096, os.statvfs(ancestor).f_frsize)
        required = sum(((item.get("size", 0) + block - 1) // block + 1) * block for item in planned)
        required += 1024 * 1024 + reserve_bytes
        if shutil.disk_usage(ancestor).free < required:
            raise ValueError(f"insufficient disk space: need {required} free bytes including reserve")
        destination.parent.mkdir(parents=True, exist_ok=True)
        _path(destination.parent, durable=True)
        parent = destination.parent
        while parent != ancestor:
            _sync_directory(parent.parent)
            parent = parent.parent
        stage = Path(tempfile.mkdtemp(prefix=".incomplete-", dir=destination.parent))
        shutil.copytree(app, stage / APP, symlinks=True, copy_function=shutil.copy2)
        shutil.copy2(retained_manifest, stage / MANIFEST_NAME, follow_symlinks=False)
        if evidence_entries:
            (stage / "evidence").mkdir(mode=0o700)
        for source, item in zip(evidence_sources, evidence_entries):
            shutil.copy2(source, stage / item["path"], follow_symlinks=False)
        if _inventory(stage) != planned:
            raise ValueError("copied archive differs from source checksum/permission inventory")
        if _identity(app) != identity or _identity(stage / APP) != identity:
            raise ValueError("source or copied candidate changed during retention")
        current_source = [_entry(app, APP)] + [
            {**item, "path": APP + "/" + item["path"]} for item in _inventory(app)]
        if current_source != source_entries:
            raise ValueError("source files/permissions changed during retention")
        for item in planned:
            if item["type"] == "file":
                with (stage / item["path"]).open("rb") as handle:
                    os.fsync(handle.fileno())
        _write_json(stage / INVENTORY, planned)
        for directory in sorted((item for item in planned if item["type"] == "directory"),
                                key=lambda item: item["path"].count("/"), reverse=True):
            _sync_directory(stage / directory["path"])
        receipt = _receipt(identity, planned, _hash(stage / INVENTORY))
        _write_json(stage / COMPLETE, receipt)
        _sync_directory(stage)
        _verify(stage, identity, check_key=False)
        _publish(stage, destination)
        _sync_directory(destination.parent)
        _sync_directory(root)
        return verify_archive(destination, identity)
    except (OSError, ValueError, TypeError, KeyError, shutil.Error) as error:
        # Keep failed copies for inspection, but never leave a completion claim.
        if stage is not None and stage.exists():
            (stage / COMPLETE).unlink(missing_ok=True)
        raise ValueError(f"candidate archive creation failed: {error}") from error


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create")
    create.add_argument("--app", type=Path, required=True)
    create.add_argument("--archive-root", type=Path, required=True)
    create.add_argument("--manifest", type=Path)
    create.add_argument("--evidence", type=Path, action="append", default=[])
    create.add_argument("--reserve-bytes", type=int, default=RESERVE_BYTES)
    verify = commands.add_parser("verify")
    verify.add_argument("archive", type=Path)
    for key in sorted(IDENTITY_KEYS):
        verify.add_argument("--" + key.replace("_", "-"))
    args = parser.parse_args()
    try:
        if args.command == "create":
            receipt = create_archive(args.app, args.archive_root, manifest=args.manifest,
                                     evidence=args.evidence, reserve_bytes=args.reserve_bytes)
        else:
            expected = {key: getattr(args, key) for key in IDENTITY_KEYS if getattr(args, key) is not None}
            receipt = verify_archive(args.archive, expected)
    except ValueError as error:
        parser.exit(1, f"{error}\n")
    print(json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()
