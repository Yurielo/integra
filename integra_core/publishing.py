"""Deterministic, one-way publication of managed Obsidian views."""

from __future__ import annotations

import contextlib
import copy
import fcntl
import hashlib
import json
import os
import re
import shutil
import stat
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterator

from .identity import derive_imported_id
from .project_lease import LeaseStore
from .protocol import canonical_json, content_sha256


class PublishingError(RuntimeError):
    """Raised before user-owned or unverified bytes could be replaced."""


MANAGED_ROOT = "Integra"
MANIFEST = "publish_manifest.json"
CHECKSUMS = "checksums.sha256"
COMPLETE = "COMPLETE.json"
CURRENT = "CURRENT.json"
SOURCE_MANIFEST_TYPE = "seminartext.managed_generated_export"
HEX = re.compile(r"^[0-9a-f]{64}$")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _record_hash(value: dict[str, Any], field: str = "record_sha256") -> str:
    unsigned = copy.deepcopy(value)
    unsigned[field] = ""
    return content_sha256(unsigned)


def _safe_relative(value: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value:
        raise PublishingError("managed path is invalid")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise PublishingError(f"managed path is unsafe: {value}")
    return path


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip("-.")
    if not slug or slug in {".", ".."}:
        raise PublishingError("project slug is unsafe")
    return slug[:96]


def validate_source_export(files: dict[str, bytes], manifest: dict[str, Any]) -> None:
    """Validate the accepted R6 SeminarText managed-export shape and bytes."""
    required = {"artifact_type", "canonical_evidence_artifact_id", "canonical_evidence_sha256",
                "canonical_knowledge_artifact_id", "canonical_knowledge_sha256", "coverage", "files",
                "kind", "ownership_classes", "resolver_states", "schema_version"}
    if not isinstance(manifest, dict) or set(manifest) != required or manifest.get("artifact_type") != SOURCE_MANIFEST_TYPE:
        raise PublishingError("source export manifest identity is invalid")
    if manifest.get("kind") != "obsidian_derived_view" or manifest.get("schema_version") != 1:
        raise PublishingError("source export manifest version is invalid")
    if manifest.get("ownership_classes") != ["MANAGED_GENERATED", "USER_OWNED"]:
        raise PublishingError("source export ownership classes are invalid")
    expected = manifest.get("files")
    if not isinstance(expected, dict) or set(expected) != set(files):
        raise PublishingError("source export file inventory differs")
    for name, payload in files.items():
        _safe_relative(name)
        if not isinstance(payload, bytes):
            raise PublishingError("source export payload must be bytes")
        if expected[name] != sha256_bytes(payload):
            raise PublishingError(f"source export hash differs: {name}")
    for field in ("canonical_evidence_sha256", "canonical_knowledge_sha256"):
        if not HEX.fullmatch(str(manifest.get(field, ""))):
            raise PublishingError(f"source export {field} is invalid")
    for field in ("canonical_evidence_artifact_id", "canonical_knowledge_artifact_id"):
        if not isinstance(manifest.get(field), str) or not manifest[field]:
            raise PublishingError(f"source export {field} is invalid")
    if not isinstance(manifest["coverage"], dict) or not isinstance(manifest["resolver_states"], dict):
        raise PublishingError("source export coverage or resolver states are invalid")


def _validate_bound_record(value: dict[str, Any], id_field: str, label: str) -> None:
    if not isinstance(value, dict) or not isinstance(value.get(id_field), str):
        raise PublishingError(f"{label} binding is invalid")
    if value.get("record_sha256") != _record_hash(value):
        raise PublishingError(f"{label} record hash differs")


def build_obsidian_package(
    *, project_id: str, project_slug: str, source_files: dict[str, bytes],
    source_manifest: dict[str, Any], knowledge_view: dict[str, Any],
    navigation: dict[str, Any], created_at: str,
) -> tuple[dict[str, Any], dict[str, bytes]]:
    """Build immutable package bytes; no filesystem write occurs here."""
    validate_source_export(source_files, source_manifest)
    try:
        instant = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as error:
        raise PublishingError("created_at must be a UTC timestamp") from error
    if not created_at.endswith("Z") or instant.tzinfo != timezone.utc:
        raise PublishingError("created_at must be a UTC timestamp")
    _validate_bound_record(knowledge_view, "view_id", "knowledge")
    _validate_bound_record(navigation, "navigation_id", "navigation")
    if navigation.get("project_id") != project_id:
        raise PublishingError("navigation project differs")
    knowledge_binding = navigation.get("sources", {}).get("knowledge", {})
    if knowledge_binding != {
        "record_id": knowledge_view["view_id"],
        "record_sha256": knowledge_view["record_sha256"],
    }:
        raise PublishingError("navigation does not bind the knowledge view")
    source_binding = knowledge_view.get("source_binding", {})
    if (
        source_manifest.get("canonical_evidence_artifact_id") != source_binding.get("canonical_evidence_id")
        or source_manifest.get("canonical_evidence_sha256") != source_binding.get("canonical_evidence_sha256")
        or source_manifest.get("canonical_knowledge_artifact_id") != source_binding.get("canonical_knowledge_id")
        or source_manifest.get("canonical_knowledge_sha256") != source_binding.get("canonical_knowledge_sha256")
    ):
        raise PublishingError("source export differs from R9A canonical binding")

    files = dict(sorted(source_files.items()))
    navigation_metadata = canonical_json({
        "schema_version": "1.0",
        "navigation_id": navigation["navigation_id"],
        "navigation_sha256": navigation["record_sha256"],
        "targets": [
            {
                "target_id": item["target_id"], "target_sha256": item["target_sha256"],
                "available": item["available"], "actions": item["actions"],
                "locators": item["locators"], "unavailable_reason": item["unavailable_reason"],
            }
            for item in navigation["targets"]
        ],
    }) + b"\n"
    files["_meta/integra_navigation.json"] = navigation_metadata
    inventory = [
        {"path": name, "size_bytes": len(payload), "sha256": sha256_bytes(payload),
         "ownership_class": "MANAGED_GENERATED"}
        for name, payload in sorted(files.items())
    ]
    identity = {
        "project_id": project_id, "project_slug": _safe_slug(project_slug), "created_at": created_at,
        "source_manifest_sha256": content_sha256(source_manifest),
        "knowledge_view_id": knowledge_view["view_id"],
        "knowledge_view_sha256": knowledge_view["record_sha256"],
        "navigation_id": navigation["navigation_id"],
        "navigation_sha256": navigation["record_sha256"], "files": inventory,
    }
    version_sha = content_sha256(identity)
    package_id = derive_imported_id("artifact", "integra.obsidian", project_id, version_sha)
    manifest = {
        "schema_version": "1.0", "artifact_type": "integra.obsidian_package",
        "package_id": package_id, "version_sha256": version_sha,
        "project_id": project_id, "project_slug": identity["project_slug"],
        "created_at": created_at, "source_manifest_sha256": identity["source_manifest_sha256"],
        "knowledge": {"view_id": knowledge_view["view_id"], "record_sha256": knowledge_view["record_sha256"]},
        "navigation": {"navigation_id": navigation["navigation_id"], "record_sha256": navigation["record_sha256"]},
        "files": inventory, "semantic_authority": "DERIVED_SOURCE_TRUTH_PRESERVED",
        "source_artifacts_modified": False,
    }
    return manifest, files


def preview_obsidian_export(vault: Path, manifest: dict[str, Any], files: dict[str, bytes]) -> dict[str, Any]:
    vault = Path(vault).resolve(strict=True)
    root, version = _targets(vault, manifest)
    collisions = _preflight(vault, root, version, manifest, files)
    return _receipt("DRY_RUN", manifest, root, collisions, False)


def publish_obsidian_export(
    vault: Path, manifest: dict[str, Any], files: dict[str, bytes], *,
    lease: dict[str, Any], lease_store: LeaseStore, operation_at: str,
    interrupt_after: str | None = None,
) -> dict[str, Any]:
    vault = Path(vault).resolve(strict=True)
    root, version = _targets(vault, manifest)
    _ensure_vault(vault)
    _validate_lease(manifest, lease, lease_store, operation_at)
    initial_collisions = _preflight(vault, root, version, manifest, files)
    if initial_collisions:
        raise PublishingError("user-owned collision: " + ", ".join(initial_collisions))
    lock_parent = vault / ".integra-locks"
    lock_parent.mkdir(mode=0o700, exist_ok=True)
    _reject_symlink(lock_parent, vault)
    lock_path = lock_parent / f"{hashlib.sha256(str(root).encode()).hexdigest()}.lock"
    with _target_lock(lock_path):
        collisions = _preflight(vault, root, version, manifest, files)
        if collisions:
            raise PublishingError("user-owned collision: " + ", ".join(collisions))
        if version.exists():
            _verify_version(version, manifest, files)
            return _receipt("UNCHANGED", manifest, root, [], True)
        root.mkdir(parents=True, exist_ok=True)
        staging_root = root / ".staging"
        staging_root.mkdir(exist_ok=True)
        staging = staging_root / (manifest["version_sha256"] + ".partial")
        if staging.exists():
            _recover_staging(staging, manifest, files)
        staging.mkdir(mode=0o700)
        try:
            for name, payload in sorted(files.items()):
                destination = _managed_path(staging, name)
                destination.parent.mkdir(parents=True, exist_ok=True)
                _atomic_file(destination, payload)
            if interrupt_after == "FILES":
                raise PublishingError("injected interruption after files")
            manifest_bytes = canonical_json(manifest) + b"\n"
            _atomic_file(staging / MANIFEST, manifest_bytes)
            _atomic_file(staging / CHECKSUMS, _checksum_bytes(manifest, manifest_bytes))
            _verify_staged(staging, manifest, files)
            if interrupt_after == "VERIFIED":
                raise PublishingError("injected interruption after verification")
            complete = canonical_json({
                "schema_version": "1.0", "package_id": manifest["package_id"],
                "version_sha256": manifest["version_sha256"],
                "manifest_sha256": sha256_bytes(manifest_bytes), "state": "COMPLETE",
            }) + b"\n"
            _atomic_file(staging / COMPLETE, complete)
            _fsync_dir(staging)
            version.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staging, version)
            _fsync_dir(version.parent)
            pointer = canonical_json({
                "schema_version": "1.0", "package_id": manifest["package_id"],
                "version_sha256": manifest["version_sha256"],
                "relative_path": f"versions/{manifest['version_sha256']}",
            }) + b"\n"
            _atomic_file(root / CURRENT, pointer)
            _verify_version(version, manifest, files)
            return _receipt("EXPORTED", manifest, root, [], False)
        except Exception:
            # An incomplete staging tree is deliberately retained for verified recovery.
            raise


def recover_obsidian_export(
    vault: Path, manifest: dict[str, Any], files: dict[str, bytes], *,
    lease: dict[str, Any], lease_store: LeaseStore, operation_at: str,
) -> dict[str, Any]:
    vault = Path(vault).resolve(strict=True)
    root, version = _targets(vault, manifest)
    _ensure_vault(vault)
    _validate_lease(manifest, lease, lease_store, operation_at)
    lock_path = vault / ".integra-locks" / f"{hashlib.sha256(str(root).encode()).hexdigest()}.lock"
    lock_path.parent.mkdir(mode=0o700, exist_ok=True)
    with _target_lock(lock_path):
        staging = root / ".staging" / (manifest["version_sha256"] + ".partial")
        if version.exists():
            _verify_version(version, manifest, files)
            return _receipt("UNCHANGED", manifest, root, [], True)
        if not staging.exists():
            raise PublishingError("recoverable staging package is missing")
        _recover_staging(staging, manifest, files)
    return publish_obsidian_export(
        vault, manifest, files, lease=lease, lease_store=lease_store,
        operation_at=operation_at,
    )


def _receipt(state: str, manifest: dict[str, Any], root: Path, collisions: list[str], replay: bool) -> dict[str, Any]:
    return {"schema_version": "1.0", "state": state, "package_id": manifest["package_id"],
            "version_sha256": manifest["version_sha256"], "managed_root": str(root),
            "collisions": collisions, "replay": replay, "cloud_verified": False}


def _targets(vault: Path, manifest: dict[str, Any]) -> tuple[Path, Path]:
    vault = Path(vault).resolve(strict=False)
    slug = _safe_slug(manifest["project_slug"])
    version_sha = manifest.get("version_sha256")
    if not HEX.fullmatch(str(version_sha or "")):
        raise PublishingError("package version hash is invalid")
    root = vault / MANAGED_ROOT / slug
    return root, root / "versions" / version_sha


def _ensure_vault(vault: Path) -> None:
    if not vault.is_dir() or vault.is_symlink():
        raise PublishingError("vault must be an existing non-symlink directory")


def _preflight(vault: Path, root: Path, version: Path, manifest: dict[str, Any], files: dict[str, bytes]) -> list[str]:
    _ensure_vault(vault)
    validate_package(manifest, files)
    cursor = vault
    for part in root.relative_to(vault).parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise PublishingError("managed destination contains a symlink")
    collisions: list[str] = []
    if root.exists():
        allowed = {"versions", ".staging", CURRENT}
        collisions.extend(
            str(item.relative_to(vault)) for item in root.iterdir() if item.name not in allowed
        )
        pointer = root / CURRENT
        for managed_directory in (root / "versions", root / ".staging"):
            if managed_directory.is_symlink() or (managed_directory.exists() and not managed_directory.is_dir()):
                raise PublishingError("managed destination contains an unsafe directory")
        if pointer.exists():
            try:
                value = json.loads(pointer.read_bytes())
                relative = PurePosixPath(value["relative_path"])
                if (
                    pointer.is_symlink() or not pointer.is_file()
                    or value.get("schema_version") != "1.0"
                    or relative.parts[:1] != ("versions",)
                    or len(relative.parts) != 2
                    or not HEX.fullmatch(relative.parts[1])
                ):
                    raise ValueError
                current_version = root.joinpath(*relative.parts)
                if not current_version.is_dir() or not (current_version / COMPLETE).is_file():
                    raise ValueError
            except (OSError, ValueError, KeyError, json.JSONDecodeError):
                collisions.append(str(pointer.relative_to(vault)))
    if version.exists():
        if version.is_symlink() or not version.is_dir():
            return [str(version.relative_to(vault))]
        try:
            _verify_version(version, manifest, files)
        except PublishingError:
            collisions.append(str(version.relative_to(vault)))
    return sorted(set(collisions))


def validate_package(manifest: dict[str, Any], files: dict[str, bytes]) -> None:
    if manifest.get("artifact_type") != "integra.obsidian_package" or manifest.get("schema_version") != "1.0":
        raise PublishingError("package manifest identity is invalid")
    expected = {item["path"]: item for item in manifest.get("files", [])}
    if len(expected) != len(manifest.get("files", [])) or set(expected) != set(files):
        raise PublishingError("package file inventory differs")
    for name, payload in files.items():
        _safe_relative(name)
        item = expected[name]
        if item != {"path": name, "size_bytes": len(payload), "sha256": sha256_bytes(payload),
                    "ownership_class": "MANAGED_GENERATED"}:
            raise PublishingError(f"package file binding differs: {name}")
    identity = {"project_id": manifest["project_id"], "project_slug": manifest["project_slug"],
                "created_at": manifest["created_at"],
                "source_manifest_sha256": manifest["source_manifest_sha256"],
                "knowledge_view_id": manifest["knowledge"]["view_id"],
                "knowledge_view_sha256": manifest["knowledge"]["record_sha256"],
                "navigation_id": manifest["navigation"]["navigation_id"],
                "navigation_sha256": manifest["navigation"]["record_sha256"],
                "files": manifest["files"]}
    if manifest["version_sha256"] != content_sha256(identity):
        raise PublishingError("package version identity differs")


def _managed_path(root: Path, relative: str) -> Path:
    parts = _safe_relative(relative).parts
    cursor = root
    for part in parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise PublishingError(f"managed path is a symlink: {relative}")
    return cursor


def _reject_symlink(path: Path, root: Path) -> None:
    if path.is_symlink() or root.resolve() not in path.resolve(strict=False).parents:
        raise PublishingError("managed lock path is unsafe")


@contextlib.contextmanager
def _target_lock(path: Path) -> Iterator[None]:
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise PublishingError("publication target is locked") from error
        yield
    finally:
        os.close(descriptor)


def _atomic_file(path: Path, payload: bytes) -> None:
    temporary = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        try:
            with os.fdopen(descriptor, "wb", closefd=False) as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
    finally:
        os.close(descriptor)
    os.replace(temporary, path)
    _fsync_dir(path.parent)


def _fsync_dir(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _verify_staged(root: Path, manifest: dict[str, Any], files: dict[str, bytes]) -> None:
    for name, expected in files.items():
        path = _managed_path(root, name)
        metadata = path.lstat()
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size != len(expected) or sha256_bytes(path.read_bytes()) != sha256_bytes(expected):
            raise PublishingError(f"staged package verification failed: {name}")
    manifest_bytes = canonical_json(manifest) + b"\n"
    if (root / MANIFEST).read_bytes() != manifest_bytes:
        raise PublishingError("staged manifest differs")
    checksum_path = root / CHECKSUMS
    if not checksum_path.is_file() or checksum_path.is_symlink() or checksum_path.read_bytes() != _checksum_bytes(manifest, manifest_bytes):
        raise PublishingError("staged checksums differ")


def _verify_version(root: Path, manifest: dict[str, Any], files: dict[str, bytes]) -> None:
    _verify_staged(root, manifest, files)
    expected_paths = set(files) | {MANIFEST, CHECKSUMS, COMPLETE}
    actual_paths = {
        item.relative_to(root).as_posix() for item in root.rglob("*") if item.is_file()
    }
    if any(item.is_symlink() for item in root.rglob("*")) or actual_paths != expected_paths:
        raise PublishingError("immutable version inventory differs")
    complete_path = root / COMPLETE
    if not complete_path.is_file() or complete_path.is_symlink():
        raise PublishingError("complete marker is missing")
    complete = json.loads(complete_path.read_bytes())
    if complete != {"schema_version": "1.0", "package_id": manifest["package_id"],
                    "version_sha256": manifest["version_sha256"],
                    "manifest_sha256": sha256_bytes(canonical_json(manifest) + b"\n"), "state": "COMPLETE"}:
        raise PublishingError("complete marker differs")


def _recover_staging(staging: Path, manifest: dict[str, Any], files: dict[str, bytes]) -> None:
    if staging.is_symlink() or not staging.is_dir():
        raise PublishingError("staging path is unsafe")
    # Recovery is fail-closed: only exact expected bytes may be removed/rebuilt.
    expected = set(files) | {MANIFEST, CHECKSUMS, COMPLETE}
    actual = {item.relative_to(staging).as_posix() for item in staging.rglob("*") if item.is_file()}
    if any(item.is_symlink() for item in staging.rglob("*")) or actual - expected:
        raise PublishingError("staging contains unowned or unsafe content")
    for relative in actual & set(files):
        if (staging / relative).read_bytes() != files[relative]:
            raise PublishingError("staging content differs from requested package")
    shutil.rmtree(staging)


def _checksum_bytes(manifest: dict[str, Any], manifest_bytes: bytes) -> bytes:
    lines = [f"{item['sha256']}  {item['path']}" for item in manifest["files"]]
    lines.append(f"{sha256_bytes(manifest_bytes)}  {MANIFEST}")
    return ("\n".join(lines) + "\n").encode()


def _validate_lease(
    manifest: dict[str, Any], lease: dict[str, Any], store: LeaseStore, operation_at: str,
) -> None:
    try:
        current = store.read(manifest["project_id"], manifest["package_id"])
        instant = datetime.fromisoformat(operation_at.replace("Z", "+00:00"))
        heartbeat = datetime.fromisoformat(lease["heartbeat_at"].replace("Z", "+00:00"))
        expires = datetime.fromisoformat(lease["expires_at"].replace("Z", "+00:00"))
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        raise PublishingError("publication lease is invalid") from error
    if (
        current != lease or lease.get("state") != "ACTIVE"
        or lease.get("project_id") != manifest["project_id"]
        or lease.get("mutable_entity") != {"namespace": "artifact", "entity_id": manifest["package_id"]}
        or lease.get("writer", {}).get("component_id") != "integra.obsidian_exporter"
        or lease.get("artifact_precondition") != {
            "revision_id": manifest["package_id"], "content_sha256": manifest["version_sha256"]
        }
        or not operation_at.endswith("Z") or instant.tzinfo != timezone.utc
        or not (heartbeat <= instant < expires)
    ):
        raise PublishingError("publication lease does not authorize this package")
