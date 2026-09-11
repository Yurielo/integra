"""Filesystem-backed, locally verified OneDrive publication."""

from __future__ import annotations

import json
import os
import re
import stat
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from .identity import derive_imported_id
from .project_lease import LeaseStore
from .protocol import canonical_json, content_sha256
from .publishing import (
    CHECKSUMS, COMPLETE, CURRENT, MANAGED_ROOT, MANIFEST, HEX, PublishingError,
    _atomic_file, _expected_directories, _fsync_dir, _lexists, _managed_path,
    _safe_relative, _safe_slug, _target_lock, sha256_bytes, validate_package,
)


CONFLICT = re.compile(r"(?:conflicted|conflict)[ _-]*(?:copy|version)", re.IGNORECASE)
ONEDRIVE_WRITER = "integra.onedrive_publisher"


def build_onedrive_package(
    obsidian_manifest: dict[str, Any], files: dict[str, bytes], *, created_at: str,
) -> tuple[dict[str, Any], dict[str, bytes]]:
    """Bind an accepted immutable Obsidian package without writing a sync root."""
    validate_package(obsidian_manifest, files)
    _utc(created_at)
    packaged = dict(sorted(files.items()))
    inventory = [
        {"path": name, "size_bytes": len(payload), "sha256": sha256_bytes(payload),
         "ownership_class": "MANAGED_GENERATED"}
        for name, payload in packaged.items()
    ]
    identity = {
        "project_id": obsidian_manifest["project_id"],
        "project_slug": _safe_slug(obsidian_manifest["project_slug"]),
        "created_at": created_at,
        "source_package_id": obsidian_manifest["package_id"],
        "source_version_sha256": obsidian_manifest["version_sha256"],
        "files": inventory,
    }
    version = content_sha256(identity)
    package_id = derive_imported_id(
        "artifact", "integra.onedrive", identity["project_id"], version,
    )
    manifest = {
        "schema_version": "1.0", "artifact_type": "integra.onedrive_package",
        "package_id": package_id, "version_sha256": version,
        "project_id": identity["project_id"], "project_slug": identity["project_slug"],
        "created_at": created_at,
        "source_package": {
            "package_id": identity["source_package_id"],
            "version_sha256": identity["source_version_sha256"],
        },
        "files": inventory, "semantic_authority": "DERIVED_SOURCE_TRUTH_PRESERVED",
        "source_artifacts_modified": False,
    }
    return manifest, packaged


def validate_onedrive_package(manifest: dict[str, Any], files: dict[str, bytes]) -> None:
    fields = {"schema_version", "artifact_type", "package_id", "version_sha256",
              "project_id", "project_slug", "created_at", "source_package", "files",
              "semantic_authority", "source_artifacts_modified"}
    if not isinstance(manifest, dict) or set(manifest) != fields:
        raise PublishingError("OneDrive package fields differ from v1")
    if manifest.get("schema_version") != "1.0" or manifest.get("artifact_type") != "integra.onedrive_package":
        raise PublishingError("OneDrive package identity is invalid")
    if manifest.get("semantic_authority") != "DERIVED_SOURCE_TRUTH_PRESERVED" or manifest.get("source_artifacts_modified") is not False:
        raise PublishingError("OneDrive package authority differs")
    if not isinstance(manifest.get("project_id"), str) or not manifest["project_id"]:
        raise PublishingError("OneDrive project identity is invalid")
    if manifest.get("project_slug") != _safe_slug(manifest.get("project_slug", "")):
        raise PublishingError("OneDrive project slug differs")
    _utc(manifest.get("created_at"))
    source = manifest.get("source_package")
    if (not isinstance(source, dict) or set(source) != {"package_id", "version_sha256"}
            or not isinstance(source.get("package_id"), str) or not source["package_id"]
            or not HEX.fullmatch(str(source.get("version_sha256", "")))):
        raise PublishingError("OneDrive source package binding is invalid")
    inventory = manifest.get("files")
    if not isinstance(inventory, list) or not inventory:
        raise PublishingError("OneDrive file inventory is invalid")
    expected: dict[str, dict[str, Any]] = {}
    for item in inventory:
        if (not isinstance(item, dict)
                or set(item) != {"path", "size_bytes", "sha256", "ownership_class"}
                or item.get("ownership_class") != "MANAGED_GENERATED"
                or not isinstance(item.get("size_bytes"), int) or isinstance(item["size_bytes"], bool)
                or item["size_bytes"] < 0 or not HEX.fullmatch(str(item.get("sha256", "")))):
            raise PublishingError("OneDrive file record is invalid")
        name = item.get("path"); _safe_relative(name)
        if name in expected or name in {MANIFEST, CHECKSUMS, COMPLETE, CURRENT}:
            raise PublishingError("OneDrive file path is reserved or duplicated")
        expected[name] = item
    if set(files) != set(expected):
        raise PublishingError("OneDrive file inventory differs")
    for name, payload in files.items():
        if not isinstance(payload, bytes):
            raise PublishingError("OneDrive payload must be bytes")
        if expected[name]["size_bytes"] != len(payload) or expected[name]["sha256"] != sha256_bytes(payload):
            raise PublishingError(f"OneDrive payload differs: {name}")
    identity = {
        "project_id": manifest["project_id"], "project_slug": manifest["project_slug"],
        "created_at": manifest["created_at"],
        "source_package_id": source["package_id"],
        "source_version_sha256": source["version_sha256"], "files": inventory,
    }
    if manifest.get("version_sha256") != content_sha256(identity):
        raise PublishingError("OneDrive package version identity differs")
    expected_id = derive_imported_id(
        "artifact", "integra.onedrive", manifest["project_id"], manifest["version_sha256"],
    )
    if manifest.get("package_id") != expected_id:
        raise PublishingError("OneDrive package derived identity differs")


def preview_onedrive_publication(sync_root: Path, workspace: Path,
                                 manifest: dict[str, Any], files: dict[str, bytes]) -> dict[str, Any]:
    validate_onedrive_package(manifest, files)
    workspace = _workspace(workspace, sync_root)
    target = _target(sync_root, manifest)
    available = _availability(sync_root)
    collisions = _preflight_target(sync_root, target, manifest, files) if available else []
    return _receipt("DRY_RUN_AVAILABLE" if available else "DRY_RUN_UNAVAILABLE",
                    manifest, target, workspace, collisions, False)


def publish_onedrive_package(
    sync_root: Path, workspace: Path, manifest: dict[str, Any], files: dict[str, bytes], *,
    lease: dict[str, Any], lease_store: LeaseStore,
    clock: Callable[[], datetime] | None = None,
    placeholder_detector: Callable[[Path], bool] | None = None,
    interrupt_after: str | None = None,
) -> dict[str, Any]:
    validate_onedrive_package(manifest, files)
    workspace = _workspace(workspace, sync_root)
    _validate_lease(manifest, lease, lease_store, clock)
    available = _availability(sync_root)
    stage = _prepare_stage(workspace, manifest, files)
    target = _target(sync_root, manifest)
    if not available:
        _write_queue(workspace, sync_root, stage, manifest)
        return _receipt("QUEUED_TARGET_UNAVAILABLE", manifest, target, workspace, [], False)
    collisions = _preflight_target(sync_root, target, manifest, files)
    if collisions:
        raise PublishingError("OneDrive target collision: " + ", ".join(collisions))
    target.mkdir(parents=True, exist_ok=True)
    lock = target / ".export.lock"  # Same identity/path as R10 when the Vault is in OneDrive.
    if _lexists(lock) and lock.is_symlink():
        raise PublishingError("publication lock path is a symlink")
    with _target_lock(lock):
        collisions = _preflight_target(sync_root, target, manifest, files)
        if collisions:
            raise PublishingError("OneDrive target collision: " + ", ".join(collisions))
        state = _publish_locked(target, stage, manifest, files,
                                placeholder_detector or _is_placeholder, interrupt_after)
        if state != "UNCHANGED":
            _remove_queue(workspace, sync_root, stage, manifest)
        return _receipt(state, manifest, target, workspace, [], state == "UNCHANGED")


def recover_onedrive_publication(
    sync_root: Path, workspace: Path, manifest: dict[str, Any], files: dict[str, bytes], *,
    lease: dict[str, Any], lease_store: LeaseStore,
    clock: Callable[[], datetime] | None = None,
    placeholder_detector: Callable[[Path], bool] | None = None,
) -> dict[str, Any]:
    validate_onedrive_package(manifest, files)
    workspace = _workspace(workspace, sync_root)
    _validate_lease(manifest, lease, lease_store, clock)
    available = _availability(sync_root)
    stage = _prepare_stage(workspace, manifest, files)
    if not available:
        _write_queue(workspace, sync_root, stage, manifest)
        return _receipt("QUEUED_TARGET_UNAVAILABLE", manifest, _target(sync_root, manifest), workspace, [], False)
    target = _target(sync_root, manifest)
    collisions = _preflight_target(sync_root, target, manifest, files, allow_partial=True)
    if collisions:
        raise PublishingError("OneDrive target collision: " + ", ".join(collisions))
    target.mkdir(parents=True, exist_ok=True)
    lock = target / ".export.lock"
    if _lexists(lock) and lock.is_symlink():
        raise PublishingError("publication lock path is a symlink")
    with _target_lock(lock):
        collisions = _preflight_target(sync_root, target, manifest, files, allow_partial=True)
        if collisions:
            raise PublishingError("OneDrive target collision: " + ", ".join(collisions))
        version = target / "versions" / manifest["version_sha256"]
        if _lexists(version) and not (version / COMPLETE).exists():
            _verify_partial(version, stage, manifest, files,
                            placeholder_detector or _is_placeholder)
        state = _publish_locked(target, stage, manifest, files,
                                placeholder_detector or _is_placeholder, None)
        _remove_queue(workspace, sync_root, stage, manifest)
        return _receipt(state, manifest, target, workspace, [], state == "UNCHANGED")


def _publish_locked(target: Path, stage: Path, manifest: dict[str, Any], files: dict[str, bytes],
                    placeholder: Callable[[Path], bool], interrupt_after: str | None) -> str:
    version = target / "versions" / manifest["version_sha256"]
    if _lexists(version) and (version / COMPLETE).exists():
        _verify_version(version, manifest, files, placeholder)
        if _current_exact(target, manifest):
            return "UNCHANGED"
        _atomic_file(target / CURRENT, _pointer(manifest))
        return "LOCALLY_PUBLISHED"
    if not _lexists(version):
        version.parent.mkdir(parents=True, exist_ok=True)
        version.mkdir(mode=0o700)
    _verify_partial(version, stage, manifest, files, placeholder)
    for name in sorted(files):
        destination = _managed_path(version, name)
        if not _lexists(destination):
            destination.parent.mkdir(parents=True, exist_ok=True)
            _atomic_file(destination, (_managed_path(stage, name)).read_bytes())
    if interrupt_after == "FILES":
        raise PublishingError("injected interruption after OneDrive files")
    for name in (MANIFEST, CHECKSUMS):
        destination = version / name
        if not _lexists(destination):
            _atomic_file(destination, (stage / name).read_bytes())
    _verify_payload(version, manifest, files, placeholder)
    if interrupt_after == "VERIFIED":
        raise PublishingError("injected interruption after OneDrive verification")
    _atomic_file(version / COMPLETE, _complete(manifest))
    _fsync_dir(version)
    if interrupt_after == "COMPLETE":
        raise PublishingError("injected interruption after OneDrive completion")
    _verify_version(version, manifest, files, placeholder)
    _atomic_file(target / CURRENT, _pointer(manifest))
    return "LOCALLY_PUBLISHED"


def _prepare_stage(workspace: Path, manifest: dict[str, Any], files: dict[str, bytes]) -> Path:
    stage = _workspace_path(
        workspace, "onedrive-staging", manifest["project_slug"],
        manifest["version_sha256"] + ".stage",
    )
    if _lexists(stage):
        if stage.is_symlink() or not stage.is_dir():
            raise PublishingError("OneDrive staging path is unsafe")
        _verify_version(stage, manifest, files, lambda _: False)
        return stage
    stage.mkdir(parents=True, mode=0o700)
    try:
        for name, payload in sorted(files.items()):
            destination = _managed_path(stage, name)
            destination.parent.mkdir(parents=True, exist_ok=True)
            _atomic_file(destination, payload)
        manifest_bytes = canonical_json(manifest) + b"\n"
        _atomic_file(stage / MANIFEST, manifest_bytes)
        _atomic_file(stage / CHECKSUMS, _checksums(manifest, manifest_bytes))
        _verify_payload(stage, manifest, files, lambda _: False)
        _atomic_file(stage / COMPLETE, _complete(manifest))
        _verify_version(stage, manifest, files, lambda _: False)
        return stage
    except Exception:
        # The outside-sync staging tree remains for fail-closed inspection.
        raise


def _preflight_target(sync_root: Path, target: Path, manifest: dict[str, Any],
                      files: dict[str, bytes], allow_partial: bool = False) -> list[str]:
    _ensure_sync_root(sync_root)
    collisions: list[str] = []
    cursor = sync_root
    for part in target.relative_to(sync_root).parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise PublishingError("OneDrive managed target contains a symlink")
    if not target.exists():
        return []
    allowed = {"versions", ".export.lock", CURRENT}
    collisions.extend(str(item.relative_to(sync_root)) for item in target.iterdir() if item.name not in allowed)
    for item in target.rglob("*"):
        if item.is_symlink():
            collisions.append(str(item.relative_to(sync_root)))
        if CONFLICT.search(item.name):
            collisions.append(str(item.relative_to(sync_root)))
    versions = target / "versions"
    if _lexists(versions) and not versions.is_dir():
        collisions.append(str(versions.relative_to(sync_root)))
    pointer = target / CURRENT
    if _lexists(pointer) and not _valid_current(target, pointer):
        collisions.append(str(pointer.relative_to(sync_root)))
    requested = versions / manifest["version_sha256"]
    if _lexists(requested):
        try:
            if requested.is_symlink() or not requested.is_dir():
                raise PublishingError("unsafe immutable version")
            if (requested / COMPLETE).exists():
                _verify_version(requested, manifest, files, _is_placeholder)
            elif not allow_partial:
                raise PublishingError("incomplete immutable version requires recovery")
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError, PublishingError):
            collisions.append(str(requested.relative_to(sync_root)))
    return sorted(set(collisions))


def _verify_partial(version: Path, stage: Path, manifest: dict[str, Any], files: dict[str, bytes],
                    placeholder: Callable[[Path], bool]) -> None:
    if version.is_symlink() or not version.is_dir():
        raise PublishingError("OneDrive partial version is unsafe")
    expected = set(files) | {MANIFEST, CHECKSUMS, COMPLETE}
    actual_files = {item.relative_to(version).as_posix() for item in version.rglob("*") if item.is_file()}
    actual_dirs = {item.relative_to(version).as_posix() for item in version.rglob("*") if item.is_dir()}
    if (any(item.is_symlink() for item in version.rglob("*")) or actual_files - expected
            or actual_dirs - _expected_directories(files)):
        raise PublishingError("OneDrive partial version contains unknown content")
    for name in actual_files:
        target_file = version / name
        if placeholder(target_file):
            raise PublishingError(f"OneDrive placeholder is not materialized: {name}")
        if target_file.read_bytes() != (stage / name).read_bytes():
            raise PublishingError(f"OneDrive partial version differs: {name}")


def _verify_payload(root: Path, manifest: dict[str, Any], files: dict[str, bytes],
                    placeholder: Callable[[Path], bool]) -> None:
    for name, payload in files.items():
        path = _managed_path(root, name)
        metadata = path.lstat()
        if (not stat.S_ISREG(metadata.st_mode) or placeholder(path)
                or metadata.st_size != len(payload) or sha256_bytes(path.read_bytes()) != sha256_bytes(payload)):
            raise PublishingError(f"OneDrive physical verification failed: {name}")
    manifest_bytes = canonical_json(manifest) + b"\n"
    for path, expected in ((root / MANIFEST, manifest_bytes),
                           (root / CHECKSUMS, _checksums(manifest, manifest_bytes))):
        metadata = path.lstat()
        if (not stat.S_ISREG(metadata.st_mode) or placeholder(path)
                or metadata.st_size != len(expected) or path.read_bytes() != expected):
            raise PublishingError(f"OneDrive physical verification failed: {path.name}")


def _verify_version(root: Path, manifest: dict[str, Any], files: dict[str, bytes],
                    placeholder: Callable[[Path], bool]) -> None:
    _verify_payload(root, manifest, files, placeholder)
    expected = set(files) | {MANIFEST, CHECKSUMS, COMPLETE}
    actual = {item.relative_to(root).as_posix() for item in root.rglob("*") if item.is_file()}
    directories = {item.relative_to(root).as_posix() for item in root.rglob("*") if item.is_dir()}
    if any(item.is_symlink() for item in root.rglob("*")) or actual != expected or directories != _expected_directories(files):
        raise PublishingError("OneDrive immutable version inventory differs")
    complete = root / COMPLETE
    if placeholder(complete) or complete.read_bytes() != _complete(manifest):
        raise PublishingError("OneDrive completion is ambiguous")


def _checksums(manifest: dict[str, Any], manifest_bytes: bytes) -> bytes:
    lines = [f"{item['sha256']}  {item['path']}" for item in manifest["files"]]
    lines.append(f"{sha256_bytes(manifest_bytes)}  {MANIFEST}")
    return ("\n".join(lines) + "\n").encode()


def _complete(manifest: dict[str, Any]) -> bytes:
    return canonical_json({
        "schema_version": "1.0", "package_id": manifest["package_id"],
        "version_sha256": manifest["version_sha256"],
        "manifest_sha256": sha256_bytes(canonical_json(manifest) + b"\n"),
        "state": "LOCALLY_COMPLETE", "cloud_verified": False,
    }) + b"\n"


def _pointer(manifest: dict[str, Any]) -> bytes:
    return canonical_json({
        "schema_version": "1.0", "package_id": manifest["package_id"],
        "version_sha256": manifest["version_sha256"],
        "relative_path": f"versions/{manifest['version_sha256']}",
        "cloud_verified": False,
    }) + b"\n"


def _current_exact(target: Path, manifest: dict[str, Any]) -> bool:
    pointer = target / CURRENT
    return pointer.is_file() and not pointer.is_symlink() and pointer.read_bytes() == _pointer(manifest)


def _valid_current(target: Path, pointer: Path) -> bool:
    try:
        value = json.loads(pointer.read_bytes())
        if pointer.is_symlink() or set(value) != {"schema_version", "package_id", "version_sha256", "relative_path", "cloud_verified"}:
            return False
        if value["schema_version"] != "1.0" or value["cloud_verified"] is not False or not HEX.fullmatch(value["version_sha256"]):
            return False
        relative = PurePosixPath(value["relative_path"])
        if relative.parts != ("versions", value["version_sha256"]):
            return False
        version = target.joinpath(*relative.parts)
        manifest = json.loads((version / MANIFEST).read_bytes())
        if (not version.is_dir() or version.is_symlink()
                or manifest.get("package_id") != value["package_id"]
                or manifest.get("version_sha256") != value["version_sha256"]):
            return False
        files = {
            item["path"]: _managed_path(version, item["path"]).read_bytes()
            for item in manifest["files"]
        }
        validate_onedrive_package(manifest, files)
        _verify_version(version, manifest, files, _is_placeholder)
        return True
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError, PublishingError):
        return False


def _write_queue(workspace: Path, sync_root: Path, stage: Path, manifest: dict[str, Any]) -> None:
    record = canonical_json({
        "schema_version": "1.0", "state": "QUEUED_TARGET_UNAVAILABLE",
        "package_id": manifest["package_id"], "version_sha256": manifest["version_sha256"],
        "manifest_sha256": sha256_bytes(canonical_json(manifest) + b"\n"),
        "sync_root": str(Path(sync_root).absolute()), "stage": str(stage),
        "cloud_verified": False,
    }) + b"\n"
    path = _queue_path(workspace, manifest)
    path.parent.mkdir(parents=True, exist_ok=True)
    if _lexists(path) and (path.is_symlink() or path.read_bytes() != record):
        raise PublishingError("OneDrive queue record differs")
    if not _lexists(path):
        _atomic_file(path, record)


def _remove_queue(workspace: Path, sync_root: Path, stage: Path, manifest: dict[str, Any]) -> None:
    path = _queue_path(workspace, manifest)
    if not _lexists(path):
        return
    expected = canonical_json({
        "schema_version": "1.0", "state": "QUEUED_TARGET_UNAVAILABLE",
        "package_id": manifest["package_id"], "version_sha256": manifest["version_sha256"],
        "manifest_sha256": sha256_bytes(canonical_json(manifest) + b"\n"),
        "sync_root": str(Path(sync_root).absolute()), "stage": str(stage),
        "cloud_verified": False,
    }) + b"\n"
    if path.is_symlink() or path.read_bytes() != expected:
        raise PublishingError("OneDrive queue record differs")
    path.unlink()
    _fsync_dir(path.parent)


def _queue_path(workspace: Path, manifest: dict[str, Any]) -> Path:
    return _workspace_path(workspace, "onedrive-queue", manifest["version_sha256"] + ".json")


def _workspace_path(workspace: Path, *parts: str) -> Path:
    cursor = workspace
    for part in parts:
        cursor = cursor / part
        if _lexists(cursor) and cursor.is_symlink():
            raise PublishingError("OneDrive workspace contains a symlink")
    return cursor


def _receipt(state: str, manifest: dict[str, Any], target: Path, workspace: Path,
             collisions: list[str], replay: bool) -> dict[str, Any]:
    return {"schema_version": "1.0", "state": state, "package_id": manifest["package_id"],
            "version_sha256": manifest["version_sha256"], "managed_root": str(target),
            "workspace": str(workspace), "collisions": collisions, "replay": replay,
            "local_files_verified": state in {"LOCALLY_PUBLISHED", "UNCHANGED"},
            "cloud_verified": False}


def _target(sync_root: Path, manifest: dict[str, Any]) -> Path:
    return Path(sync_root).absolute() / MANAGED_ROOT / _safe_slug(manifest["project_slug"])


def _availability(sync_root: Path) -> bool:
    root = Path(sync_root)
    if _lexists(root) and root.is_symlink():
        raise PublishingError("OneDrive sync root must not be a symlink")
    if not _lexists(root):
        return False
    if not root.is_dir():
        raise PublishingError("OneDrive sync root is not a directory")
    if _is_placeholder(root):
        return False
    return True


def _ensure_sync_root(sync_root: Path) -> None:
    if not _availability(sync_root):
        raise PublishingError("OneDrive sync root is unavailable")


def _workspace(workspace: Path, sync_root: Path) -> Path:
    candidate = Path(workspace)
    if _lexists(candidate) and candidate.is_symlink():
        raise PublishingError("OneDrive workspace must not be a symlink")
    if not candidate.is_dir():
        raise PublishingError("OneDrive workspace must be an existing directory")
    resolved = candidate.resolve(strict=True)
    sync = Path(sync_root).absolute()
    try:
        sync_resolved = sync.resolve(strict=False)
        if resolved == sync_resolved or resolved.is_relative_to(sync_resolved) or sync_resolved.is_relative_to(resolved):
            raise PublishingError("OneDrive staging workspace must be outside the sync root")
    except OSError as error:
        raise PublishingError("OneDrive target identity is unavailable") from error
    return resolved


def _is_placeholder(path: Path) -> bool:
    metadata = path.lstat()
    offline = getattr(stat, "UF_OFFLINE", 0)
    if offline and metadata.st_flags & offline:
        return True
    try:
        for name in os.listxattr(path, follow_symlinks=False):
            lowered = name.lower()
            if "placeholder" in lowered or "dataless" in lowered:
                return True
    except (AttributeError, OSError):
        pass
    return False


def _utc(value: Any) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as error:
        raise PublishingError("timestamp must be UTC") from error
    if not value.endswith("Z") or parsed.tzinfo != timezone.utc:
        raise PublishingError("timestamp must be UTC")
    return parsed


def _validate_lease(manifest: dict[str, Any], lease: dict[str, Any], store: LeaseStore,
                    clock: Callable[[], datetime] | None) -> None:
    try:
        current = store.read(manifest["project_id"], manifest["package_id"])
        now = (clock or (lambda: datetime.now(timezone.utc)))()
        heartbeat = _utc(lease["heartbeat_at"]); expires = _utc(lease["expires_at"])
    except (KeyError, TypeError, ValueError) as error:
        raise PublishingError("OneDrive publication lease is invalid") from error
    if (current != lease or lease.get("state") != "ACTIVE"
            or lease.get("project_id") != manifest["project_id"]
            or lease.get("mutable_entity") != {"namespace": "artifact", "entity_id": manifest["package_id"]}
            or lease.get("writer", {}).get("component_id") != ONEDRIVE_WRITER
            or lease.get("artifact_precondition") != {"revision_id": manifest["package_id"], "content_sha256": manifest["version_sha256"]}
            or not isinstance(now, datetime) or now.tzinfo is None or not (heartbeat <= now < expires)):
        raise PublishingError("OneDrive publication lease does not authorize this package")
