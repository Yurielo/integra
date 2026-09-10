"""Read-only discovery and fail-closed copy-on-write migration for Integra R7."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import stat
import uuid
from pathlib import Path
from typing import Any
from datetime import datetime, timezone

from .identity import derive_imported_id
from .operations import (
    JobStore,
    ResourceReservationStore,
    _sha256_regular_file,
    observe_process_start_token,
)
from .project_lease import LeaseStore
from .protocol import content_sha256


SUPPORTED_COMPONENTS = {"seminartext", "videotext"}
MIGRATION_STATUS = {"READY", "BLOCKED"}
REPORT_STATUS = {"SUCCEEDED"}
MIGRATION_ACTIONS = {"copy", "rollback", "recover"}
IN_PROGRESS_MARKER = ".integra-migration-in-progress.json"
INTEGRA_DIRECTORY = ".integra"
PROJECT_MANIFEST = "project.json"
MIGRATION_REPORT = "migration_report.json"


class MigrationError(RuntimeError):
    """Raised when migration truth is incomplete, unsafe, or contradictory."""


def discover_source_project(source_root: Path, source_component: str) -> dict[str, Any]:
    """Discover one supported source project without writing to it."""

    if source_component not in SUPPORTED_COMPONENTS:
        raise MigrationError("unsupported source component")
    root = _validated_directory(source_root, "source project")
    recognition = _recognize_project(root, source_component)
    files = _snapshot_files(root)
    if not files:
        raise MigrationError("source project is empty")
    content_set = sorted(
        ({"content_sha256": item["content_sha256"], "size_bytes": item["size_bytes"]}
         for item in files),
        key=lambda item: (item["content_sha256"], item["size_bytes"]),
    )
    source_revision_sha256 = content_sha256(content_set)
    project_id = derive_imported_id(
        "project",
        source_component,
        f"content-set:{source_revision_sha256}",
        source_revision_sha256,
    )
    mapped_files = []
    for item in files:
        mapped_files.append({
            **item,
            "artifact_id": derive_imported_id(
                "artifact",
                source_component,
                f"content:{item['content_sha256']}",
                item["content_sha256"],
            ),
        })
    layout_sha256 = content_sha256([
        {
            "source_relative_path": item["source_relative_path"],
            "size_bytes": item["size_bytes"],
            "content_sha256": item["content_sha256"],
        }
        for item in mapped_files
    ])
    discovery = {
        "schema_version": "1.0",
        "discovery_id": derive_imported_id(
            "operation", "integra.migration.discovery", project_id, layout_sha256
        ),
        "source_component": source_component,
        "source_format": recognition["source_format"],
        "source_schema_version": recognition["source_schema_version"],
        "source_root": str(root),
        "project_id": project_id,
        "source_revision_sha256": source_revision_sha256,
        "layout_sha256": layout_sha256,
        "status": "READY",
        "read_only": True,
        "source_compatibility": "SUPPORTED",
        "file_count": len(mapped_files),
        "total_bytes": sum(item["size_bytes"] for item in mapped_files),
        "files": mapped_files,
        "source_references": recognition["source_references"],
    }
    validate_discovery(discovery)
    return discovery


def validate_discovery(discovery: dict[str, Any]) -> None:
    required = {
        "schema_version", "discovery_id", "source_component", "source_format",
        "source_schema_version", "source_root", "project_id",
        "source_revision_sha256", "layout_sha256", "status", "read_only",
        "source_compatibility", "file_count", "total_bytes", "files",
        "source_references",
    }
    if not isinstance(discovery, dict) or set(discovery) != required:
        raise MigrationError("discovery fields differ from v1")
    if discovery["schema_version"] != "1.0" or discovery["status"] != "READY":
        raise MigrationError("discovery is not ready")
    if discovery["source_component"] not in SUPPORTED_COMPONENTS:
        raise MigrationError("discovery component is unsupported")
    if discovery["read_only"] is not True or discovery["source_compatibility"] != "SUPPORTED":
        raise MigrationError("discovery does not preserve source compatibility")
    _validate_urn(discovery["discovery_id"], "operation")
    _validate_urn(discovery["project_id"], "project")
    _validate_sha256(discovery["source_revision_sha256"], "source revision")
    _validate_sha256(discovery["layout_sha256"], "source layout")
    files = discovery["files"]
    if not isinstance(files, list) or not files:
        raise MigrationError("discovery file inventory is empty")
    paths: set[str] = set()
    for item in files:
        if not isinstance(item, dict) or set(item) != {
            "source_relative_path", "size_bytes", "content_sha256", "artifact_id"
        }:
            raise MigrationError("discovery file entry differs from v1")
        relative = _relative_parts(item["source_relative_path"])
        normalized = "/".join(relative)
        if normalized != item["source_relative_path"] or normalized in paths:
            raise MigrationError("discovery contains duplicate or non-canonical paths")
        paths.add(normalized)
        if not isinstance(item["size_bytes"], int) or item["size_bytes"] < 0:
            raise MigrationError("discovery file size is invalid")
        _validate_sha256(item["content_sha256"], "file content")
        _validate_urn(item["artifact_id"], "artifact")
        expected_artifact_id = derive_imported_id(
            "artifact",
            discovery["source_component"],
            f"content:{item['content_sha256']}",
            item["content_sha256"],
        )
        if item["artifact_id"] != expected_artifact_id:
            raise MigrationError("discovery artifact ID is not derived from immutable content")
    if discovery["file_count"] != len(files):
        raise MigrationError("discovery file count differs from inventory")
    if discovery["total_bytes"] != sum(item["size_bytes"] for item in files):
        raise MigrationError("discovery total bytes differ from inventory")
    content_set = sorted(
        ({"content_sha256": item["content_sha256"], "size_bytes": item["size_bytes"]}
         for item in files),
        key=lambda item: (item["content_sha256"], item["size_bytes"]),
    )
    if content_sha256(content_set) != discovery["source_revision_sha256"]:
        raise MigrationError("discovery source revision hash is invalid")
    layout = [
        {
            "source_relative_path": item["source_relative_path"],
            "size_bytes": item["size_bytes"],
            "content_sha256": item["content_sha256"],
        }
        for item in files
    ]
    if content_sha256(layout) != discovery["layout_sha256"]:
        raise MigrationError("discovery layout hash is invalid")
    expected_project_id = derive_imported_id(
        "project",
        discovery["source_component"],
        f"content-set:{discovery['source_revision_sha256']}",
        discovery["source_revision_sha256"],
    )
    if discovery["project_id"] != expected_project_id:
        raise MigrationError("discovery project ID is not derived from immutable content")
    if discovery["discovery_id"] != derive_imported_id(
        "operation",
        "integra.migration.discovery",
        expected_project_id,
        discovery["layout_sha256"],
    ):
        raise MigrationError("discovery ID is invalid")


def build_dry_run(discovery: dict[str, Any], target_root: Path) -> dict[str, Any]:
    """Build a deterministic migration plan and perform no writes."""

    validate_discovery(discovery)
    source = Path(discovery["source_root"])
    target = _absolute_without_resolving(target_root)
    parent = _validated_directory(target.parent, "target parent")
    target = parent / target.name
    if target == source or _is_within(target, source):
        raise MigrationError("target project cannot be the source or live inside it")
    collision = target.exists() or target.is_symlink()
    mappings = [
        {
            "artifact_id": item["artifact_id"],
            "source_relative_path": item["source_relative_path"],
            "destination_relative_path": f"source/{item['source_relative_path']}",
            "size_bytes": item["size_bytes"],
            "content_sha256": item["content_sha256"],
        }
        for item in discovery["files"]
    ]
    identity = {
        "project_id": discovery["project_id"],
        "source_revision_sha256": discovery["source_revision_sha256"],
        "layout_sha256": discovery["layout_sha256"],
        "mappings": mappings,
    }
    plan_sha256 = content_sha256(identity)
    plan = {
        "schema_version": "1.0",
        "plan_id": derive_imported_id(
            "operation", "integra.migration.plan", discovery["project_id"], plan_sha256
        ),
        "job_id": derive_imported_id(
            "job", "integra.migration", discovery["project_id"], plan_sha256
        ),
        "source_discovery_id": discovery["discovery_id"],
        "source_component": discovery["source_component"],
        "project_id": discovery["project_id"],
        "source_root": str(source),
        "target_root": str(target),
        "target_parent": str(parent),
        "target_locator_sha256": hashlib.sha256(str(target).encode()).hexdigest(),
        "source_revision_sha256": discovery["source_revision_sha256"],
        "source_layout_sha256": discovery["layout_sha256"],
        "plan_sha256": plan_sha256,
        "status": "BLOCKED" if collision else "READY",
        "block_reasons": ["TARGET_EXISTS_NO_OVERWRITE"] if collision else [],
        "mode": "COPY_ON_WRITE",
        "activation": "VALIDATE_BEFORE_ACTIVATION",
        "collision_policy": "FAIL_NO_OVERWRITE",
        "source_write_operations": 0,
        "mappings": mappings,
    }
    validate_plan(plan)
    return plan


def validate_plan(plan: dict[str, Any]) -> None:
    required = {
        "schema_version", "plan_id", "job_id", "source_discovery_id",
        "source_component", "project_id", "source_root", "target_root",
        "target_parent", "target_locator_sha256", "source_revision_sha256", "source_layout_sha256",
        "plan_sha256", "status", "block_reasons", "mode", "activation",
        "collision_policy", "source_write_operations", "mappings",
    }
    if not isinstance(plan, dict) or set(plan) != required:
        raise MigrationError("migration plan fields differ from v1")
    if plan["schema_version"] != "1.0" or plan["status"] not in MIGRATION_STATUS:
        raise MigrationError("migration plan status is invalid")
    _validate_urn(plan["plan_id"], "operation")
    _validate_urn(plan["job_id"], "job")
    _validate_urn(plan["source_discovery_id"], "operation")
    _validate_urn(plan["project_id"], "project")
    for field in (
        "source_revision_sha256", "source_layout_sha256", "plan_sha256",
        "target_locator_sha256",
    ):
        _validate_sha256(plan[field], field)
    target = _absolute_without_resolving(Path(plan["target_root"]))
    parent = Path(plan["target_parent"])
    if (
        str(target) != plan["target_root"]
        or target.parent != parent
        or hashlib.sha256(plan["target_root"].encode()).hexdigest()
        != plan["target_locator_sha256"]
    ):
        raise MigrationError("migration target locator is invalid")
    if plan["source_component"] not in SUPPORTED_COMPONENTS:
        raise MigrationError("migration plan component is unsupported")
    if (
        plan["mode"] != "COPY_ON_WRITE"
        or plan["activation"] != "VALIDATE_BEFORE_ACTIVATION"
        or plan["collision_policy"] != "FAIL_NO_OVERWRITE"
        or plan["source_write_operations"] != 0
    ):
        raise MigrationError("migration plan weakens copy-on-write safety")
    if plan["status"] == "READY" and plan["block_reasons"]:
        raise MigrationError("ready migration plan contains blockers")
    if plan["status"] == "BLOCKED" and plan["block_reasons"] != ["TARGET_EXISTS_NO_OVERWRITE"]:
        raise MigrationError("blocked migration plan reason is invalid")
    mappings = plan["mappings"]
    if not isinstance(mappings, list) or not mappings:
        raise MigrationError("migration plan mapping is empty")
    sources: set[str] = set()
    destinations: set[str] = set()
    for item in mappings:
        if not isinstance(item, dict) or set(item) != {
            "artifact_id", "source_relative_path", "destination_relative_path",
            "size_bytes", "content_sha256",
        }:
            raise MigrationError("migration mapping differs from v1")
        _validate_urn(item["artifact_id"], "artifact")
        source = "/".join(_relative_parts(item["source_relative_path"]))
        destination = "/".join(_relative_parts(item["destination_relative_path"]))
        if source in sources or destination in destinations or destination != f"source/{source}":
            raise MigrationError("migration mapping is duplicate or non-canonical")
        sources.add(source)
        destinations.add(destination)
        _validate_sha256(item["content_sha256"], "migration mapping content")
        if not isinstance(item["size_bytes"], int) or item["size_bytes"] < 0:
            raise MigrationError("migration mapping size is invalid")
    identity = {
        "project_id": plan["project_id"],
        "source_revision_sha256": plan["source_revision_sha256"],
        "layout_sha256": plan["source_layout_sha256"],
        "mappings": mappings,
    }
    if content_sha256(identity) != plan["plan_sha256"]:
        raise MigrationError("migration plan hash is invalid")
    if plan["plan_id"] != derive_imported_id(
        "operation", "integra.migration.plan", plan["project_id"], plan["plan_sha256"]
    ):
        raise MigrationError("migration plan ID is invalid")
    if plan["job_id"] != derive_imported_id(
        "job", "integra.migration", plan["project_id"], plan["plan_sha256"]
    ):
        raise MigrationError("migration job ID is invalid")
    if plan["source_discovery_id"] != derive_imported_id(
        "operation",
        "integra.migration.discovery",
        plan["project_id"],
        plan["source_layout_sha256"],
    ):
        raise MigrationError("migration source discovery ID is invalid")


def execute_copy_on_write(
    discovery: dict[str, Any],
    plan: dict[str, Any],
    *,
    job_store: JobStore | None = None,
    reservation_store: ResourceReservationStore | None = None,
    lease_store: LeaseStore | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    """Create a separate Integra-owned copy without rewriting the source."""

    validate_discovery(discovery)
    validate_plan(plan)
    _require_plan_matches_discovery(plan, discovery)
    if plan["status"] != "READY":
        raise MigrationError("blocked migration plan cannot execute")
    operation = _require_governed_operation(
        plan, job_store, reservation_store, lease_store, now, action="copy"
    )
    current = discover_source_project(Path(plan["source_root"]), plan["source_component"])
    _require_same_source_snapshot(discovery, current)
    target = Path(plan["target_root"])
    parent = _validated_directory(Path(plan["target_parent"]), "target parent")
    if target.parent != parent:
        raise MigrationError("target parent changed after dry run")
    parent_descriptor = _open_directory_fd(parent, "target parent")
    target_descriptor: int | None = None
    source_descriptor: int | None = None
    try:
        os.mkdir(target.name, mode=0o700, dir_fd=parent_descriptor)
        target_descriptor = _open_child_directory_fd(
            parent_descriptor, target.name, "migration target"
        )
        source_descriptor = _open_directory_fd(
            Path(plan["source_root"]), "migration source"
        )
    except FileExistsError as error:
        os.close(parent_descriptor)
        raise MigrationError(
            "target exists; copy-on-write migration will not overwrite it"
        ) from error
    except Exception:
        if target_descriptor is not None:
            os.close(target_descriptor)
            try:
                os.rmdir(target.name, dir_fd=parent_descriptor)
            except OSError:
                pass
        os.close(parent_descriptor)
        raise
    created_files: list[str] = []
    try:
        marker = {
            "schema_version": "1.0",
            "plan_id": plan["plan_id"],
            "plan_sha256": plan["plan_sha256"],
            "project_id": plan["project_id"],
            "target_locator_sha256": plan["target_locator_sha256"],
            "state": "IN_PROGRESS",
        }
        _write_json_exclusive_at(target_descriptor, (IN_PROGRESS_MARKER,), marker)
        created_files.append(IN_PROGRESS_MARKER)
        os.mkdir("source", mode=0o700, dir_fd=target_descriptor)
        for mapping in plan["mappings"]:
            source_parts = _relative_parts(mapping["source_relative_path"])
            destination_parts = _relative_parts(mapping["destination_relative_path"])
            _ensure_directories_at(target_descriptor, destination_parts[:-1])
            _copy_regular_file_exact_at(
                source_descriptor,
                source_parts,
                target_descriptor,
                destination_parts,
                expected_size=mapping["size_bytes"],
                expected_sha256=mapping["content_sha256"],
            )
            created_files.append(mapping["destination_relative_path"])
        os.mkdir(INTEGRA_DIRECTORY, mode=0o700, dir_fd=target_descriptor)
        project_manifest = _expected_project_manifest(plan)
        _write_json_exclusive_at(
            target_descriptor,
            (INTEGRA_DIRECTORY, PROJECT_MANIFEST),
            project_manifest,
        )
        created_files.append(f"{INTEGRA_DIRECTORY}/{PROJECT_MANIFEST}")
        report = _expected_report(plan, operation)
        validate_report(report)
        _write_json_exclusive_at(
            target_descriptor,
            (INTEGRA_DIRECTORY, MIGRATION_REPORT),
            report,
        )
        created_files.append(f"{INTEGRA_DIRECTORY}/{MIGRATION_REPORT}")
        os.unlink(IN_PROGRESS_MARKER, dir_fd=target_descriptor)
        created_files.remove(IN_PROGRESS_MARKER)
        integrity = validate_migration(discovery, plan, report)
        if integrity["status"] != "PASS":
            raise MigrationError("migration Integrity failed")
        return report
    except Exception:
        _cleanup_failed_target(target, plan, created_files)
        raise
    finally:
        if source_descriptor is not None:
            os.close(source_descriptor)
        if target_descriptor is not None:
            os.close(target_descriptor)
        os.close(parent_descriptor)


def validate_report(report: dict[str, Any]) -> None:
    required = {
        "schema_version", "report_id", "plan_id", "job_id", "project_id",
        "source_component", "source_root", "target_root", "target_locator_sha256", "status",
        "source_revision_sha256", "source_layout_sha256", "copied_file_count",
        "copied_bytes", "copied_files", "source_project_changed",
        "source_repository_changed", "activation_performed", "target_state",
        "rollback_supported",
        "operation_guarded", "reservation_id", "lease_id", "lease_generation",
    }
    if not isinstance(report, dict) or set(report) != required:
        raise MigrationError("migration report fields differ from v1")
    if report["schema_version"] != "1.0" or report["status"] not in REPORT_STATUS:
        raise MigrationError("migration report status is invalid")
    for field, namespace in (
        ("report_id", "artifact"), ("plan_id", "operation"),
        ("job_id", "job"), ("project_id", "project"),
    ):
        _validate_urn(report[field], namespace)
    if report["source_component"] not in SUPPORTED_COMPONENTS:
        raise MigrationError("migration report component is unsupported")
    for field in (
        "source_revision_sha256", "source_layout_sha256", "target_locator_sha256"
    ):
        _validate_sha256(report[field], field)
    if (
        report["source_project_changed"] is not False
        or report["source_repository_changed"] is not False
        or report["activation_performed"] is not False
        or report["target_state"] != "READY_NOT_ACTIVATED"
        or report["rollback_supported"] is not True
        or report["operation_guarded"] is not True
    ):
        raise MigrationError("migration report weakens source preservation")
    _validate_urn(report["reservation_id"], "reservation")
    _validate_urn(report["lease_id"], "lease")
    if not isinstance(report["lease_generation"], int) or report["lease_generation"] < 1:
        raise MigrationError("migration report lease generation is invalid")
    if not isinstance(report["copied_files"], list) or not report["copied_files"]:
        raise MigrationError("migration report copied-file inventory is empty")
    if report["copied_file_count"] != len(report["copied_files"]):
        raise MigrationError("migration report file count is invalid")
    for item in report["copied_files"]:
        if not isinstance(item, dict) or set(item) != {
            "artifact_id", "source_relative_path", "destination_relative_path",
            "size_bytes", "content_sha256",
        }:
            raise MigrationError("migration report copied-file entry differs from v1")
        _validate_urn(item["artifact_id"], "artifact")
        _relative_parts(item["source_relative_path"])
        _relative_parts(item["destination_relative_path"])
        _validate_sha256(item["content_sha256"], "migration report file")
        if not isinstance(item["size_bytes"], int) or item["size_bytes"] < 0:
            raise MigrationError("migration report file size is invalid")
    if report["copied_bytes"] != sum(item["size_bytes"] for item in report["copied_files"]):
        raise MigrationError("migration report byte count is invalid")
    report_identity = {
        "plan_id": report["plan_id"],
        "project_id": report["project_id"],
        "source_revision_sha256": report["source_revision_sha256"],
        "source_layout_sha256": report["source_layout_sha256"],
        "copied_files": report["copied_files"],
    }
    if report["report_id"] != derive_imported_id(
        "artifact",
        "integra.migration.report",
        report["plan_id"],
        content_sha256(report_identity),
    ):
        raise MigrationError("migration report ID is invalid")


def validate_migration(
    discovery: dict[str, Any], plan: dict[str, Any], report: dict[str, Any]
) -> dict[str, Any]:
    """Verify source preservation, complete target bytes, and activation lock."""

    validate_discovery(discovery)
    validate_plan(plan)
    validate_report(report)
    _require_plan_matches_discovery(plan, discovery)
    if any(report[key] != plan[key] for key in (
        "plan_id", "job_id", "project_id", "source_component", "source_root",
        "target_root", "source_revision_sha256", "source_layout_sha256",
        "target_locator_sha256",
    )):
        raise MigrationError("migration report differs from plan")
    if report["copied_files"] != plan["mappings"]:
        raise MigrationError("migration report mapping differs from plan")
    current = discover_source_project(Path(plan["source_root"]), plan["source_component"])
    _require_same_source_snapshot(discovery, current)
    target = _validated_directory(Path(plan["target_root"]), "migration target")
    expected = {
        item["destination_relative_path"]: item for item in plan["mappings"]
    }
    target_descriptor = _open_directory_fd(target, "migration target")
    try:
        try:
            os.stat(
                IN_PROGRESS_MARKER,
                dir_fd=target_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            pass
        else:
            raise MigrationError("migration target is still marked in progress")
        inventory, _ = _snapshot_tree_at(target_descriptor)
        inventory_by_path = {
            item["source_relative_path"]: item for item in inventory
        }
        for relative, item in expected.items():
            actual = inventory_by_path.get(relative)
            if actual is None:
                raise MigrationError(f"migrated file is missing: {relative}")
            if actual["size_bytes"] != item["size_bytes"]:
                raise MigrationError(f"migrated file size differs: {relative}")
            if actual["content_sha256"] != item["content_sha256"]:
                raise MigrationError(f"migrated file hash differs: {relative}")
        project_manifest = _read_json_regular_at(
            target_descriptor,
            (INTEGRA_DIRECTORY, PROJECT_MANIFEST),
            "Integra project manifest",
        )
        stored_report = _read_json_regular_at(
            target_descriptor,
            (INTEGRA_DIRECTORY, MIGRATION_REPORT),
            "migration report",
        )
    finally:
        os.close(target_descriptor)
    if stored_report != report:
        raise MigrationError("stored migration report differs from returned report")
    if project_manifest != _expected_project_manifest(plan):
        raise MigrationError("Integra project manifest differs from migration plan")
    expected_paths = set(expected) | {
        f"{INTEGRA_DIRECTORY}/{PROJECT_MANIFEST}",
        f"{INTEGRA_DIRECTORY}/{MIGRATION_REPORT}",
    }
    actual_paths = set(inventory_by_path)
    if actual_paths != expected_paths:
        raise MigrationError("migration target contains missing or unexpected files")
    return {
        "schema_version": "1.0",
        "status": "PASS",
        "project_id": plan["project_id"],
        "plan_id": plan["plan_id"],
        "source_unchanged": True,
        "target_complete": True,
        "hashes_match": True,
        "activation_performed": False,
        "source_compatibility": "PRESERVED_BY_BYTE_IDENTITY",
    }


def rollback_migration(
    discovery: dict[str, Any],
    plan: dict[str, Any],
    report: dict[str, Any],
    *,
    job_store: JobStore,
    reservation_store: ResourceReservationStore,
    lease_store: LeaseStore,
    now: str,
) -> dict[str, Any]:
    """Remove only the exact validated Integra-owned target; never touch source."""

    operation = _require_governed_operation(
        plan, job_store, reservation_store, lease_store, now, action="rollback"
    )
    integrity = validate_migration(discovery, plan, report)
    target = Path(plan["target_root"])
    expected_files = {
        item["destination_relative_path"] for item in plan["mappings"]
    } | {
        f"{INTEGRA_DIRECTORY}/{PROJECT_MANIFEST}",
        f"{INTEGRA_DIRECTORY}/{MIGRATION_REPORT}",
    }
    _remove_owned_target(target, expected_files)
    current = discover_source_project(Path(plan["source_root"]), plan["source_component"])
    _require_same_source_snapshot(discovery, current)
    return {
        "schema_version": "1.0",
        "rollback_id": operation["operation_id"],
        "plan_id": plan["plan_id"],
        "project_id": plan["project_id"],
        "status": "ROLLED_BACK",
        "target_removed": not target.exists() and not target.is_symlink(),
        "source_unchanged": integrity["source_unchanged"],
        "source_repository_changed": False,
    }


def recover_incomplete_migration(
    plan: dict[str, Any],
    *,
    job_store: JobStore,
    reservation_store: ResourceReservationStore,
    lease_store: LeaseStore,
    now: str,
) -> dict[str, Any]:
    """Clean an exact owned partial copy that still carries the plan marker."""

    validate_plan(plan)
    _require_governed_operation(
        plan, job_store, reservation_store, lease_store, now, action="recover"
    )
    target = _validated_directory(Path(plan["target_root"]), "partial migration target")
    target_descriptor = _open_directory_fd(target, "partial migration target")
    allowed = {IN_PROGRESS_MARKER}
    mapping_by_path = {
        item["destination_relative_path"]: item for item in plan["mappings"]
    }
    project_manifest_path = f"{INTEGRA_DIRECTORY}/{PROJECT_MANIFEST}"
    migration_report_path = f"{INTEGRA_DIRECTORY}/{MIGRATION_REPORT}"
    try:
        marker = _read_json_regular_at(
            target_descriptor, (IN_PROGRESS_MARKER,), "migration marker"
        )
        if marker != {
            "schema_version": "1.0",
            "plan_id": plan["plan_id"],
            "plan_sha256": plan["plan_sha256"],
            "project_id": plan["project_id"],
            "target_locator_sha256": plan["target_locator_sha256"],
            "state": "IN_PROGRESS",
        }:
            raise MigrationError("partial migration marker differs from plan")
        inventory, _ = _snapshot_tree_at(target_descriptor)
        for item in inventory:
            relative = item["source_relative_path"]
            if relative == IN_PROGRESS_MARKER:
                continue
            mapping = mapping_by_path.get(relative)
            if mapping is not None:
                if (
                    item["size_bytes"] != mapping["size_bytes"]
                    or item["content_sha256"] != mapping["content_sha256"]
                ):
                    raise MigrationError("partial migration contains altered bytes")
            elif relative == project_manifest_path:
                if _read_json_regular_at(
                    target_descriptor,
                    _relative_parts(relative),
                    "partial migration metadata",
                ) != _expected_project_manifest(plan):
                    raise MigrationError("partial migration contains altered metadata")
            elif relative == migration_report_path:
                partial_report = _read_json_regular_at(
                    target_descriptor,
                    _relative_parts(relative),
                    "partial migration report",
                )
                validate_report(partial_report)
                if any(partial_report[key] != plan[key] for key in (
                    "plan_id", "job_id", "project_id", "source_component",
                    "source_root", "target_root", "target_locator_sha256",
                    "source_revision_sha256", "source_layout_sha256",
                )) or partial_report["copied_files"] != plan["mappings"]:
                    raise MigrationError("partial migration contains altered metadata")
            else:
                raise MigrationError("partial migration contains an unexpected file")
            allowed.add(relative)
    finally:
        os.close(target_descriptor)
    planned_directories = _parent_directories(
        set(mapping_by_path)
        | {project_manifest_path, migration_report_path, IN_PROGRESS_MARKER}
    )
    _remove_owned_target(target, allowed, allowed_directories=planned_directories)
    return {
        "schema_version": "1.0",
        "plan_id": plan["plan_id"],
        "project_id": plan["project_id"],
        "status": "RECOVERED_PARTIAL",
        "target_removed": not target.exists() and not target.is_symlink(),
    }


def _recognize_project(root: Path, component: str) -> dict[str, Any]:
    root_descriptor = _open_directory_fd(root, "source project")
    try:
        if component == "seminartext":
            seminar_text = _read_regular_bytes_at(
                root_descriptor, ("seminar.yaml",), "SeminarText seminar.yaml"
            ).decode("utf-8")
            if not seminar_text.strip() or "title:" not in seminar_text:
                raise MigrationError("SeminarText seminar.yaml is not recognized")
            registry = _read_json_regular_at(
                root_descriptor,
                ("sources.json",),
                "SeminarText sources registry",
            )
            if (
                registry.get("schema_version") != 1
                or not isinstance(registry.get("videos"), list)
                or not isinstance(registry.get("documents"), list)
            ):
                raise MigrationError("SeminarText sources registry is unsupported")
            native_ids: set[str] = set()
            references = []
            for collection, kind in (
                ("videos", "MEDIA"),
                ("documents", "DOCUMENT"),
            ):
                for item in registry[collection]:
                    native_id = (
                        item.get("source_id") if isinstance(item, dict) else None
                    )
                    locator = item.get("file") if isinstance(item, dict) else None
                    if (
                        not isinstance(native_id, str)
                        or not native_id
                        or native_id in native_ids
                    ):
                        raise MigrationError("SeminarText source identity is invalid")
                    native_ids.add(native_id)
                    if not isinstance(locator, str) or not locator:
                        raise MigrationError("SeminarText source locator is invalid")
                    parts = _relative_parts(locator)
                    _verify_regular_file_at(
                        root_descriptor,
                        parts,
                        "SeminarText registered source",
                    )
                    references.append({
                        "native_id": native_id,
                        "kind": kind,
                        "locator_sha256": hashlib.sha256(locator.encode()).hexdigest(),
                        "scope": "IN_PROJECT",
                        "accessed": True,
                    })
            return {
                "source_format": "SEMINARTEXT_PROJECT",
                "source_schema_version": "1",
                "source_references": references,
            }
        manifest = _read_json_regular_at(
            root_descriptor,
            ("Support files", "manifest.json"),
            "VideoText manifest",
        )
        if (
            str(manifest.get("appName", "")).lower() != "videotext"
            or manifest.get("schemaVersion") != 7
            or not isinstance(manifest.get("sourceMediaPath"), str)
            or not manifest["sourceMediaPath"]
        ):
            raise MigrationError(
                "VideoText project schema v7 is unsupported or incomplete"
            )
        locator = manifest["sourceMediaPath"]
        locator_path = Path(locator)
        in_project = False
        if not locator_path.is_absolute():
            try:
                parts = _relative_parts(locator)
                _verify_regular_file_at(
                    root_descriptor, parts, "VideoText in-project media"
                )
            except MigrationError:
                pass
            else:
                in_project = True
        return {
            "source_format": "VIDEOTEXT_PROJECT",
            "source_schema_version": "7",
            "source_references": [{
                "native_id": "primary-media",
                "kind": "MEDIA",
                "locator_sha256": hashlib.sha256(locator.encode()).hexdigest(),
                "scope": "IN_PROJECT" if in_project else "EXTERNAL_REFERENCE",
                "accessed": in_project,
            }],
        }
    except UnicodeError as error:
        raise MigrationError("source project text encoding is invalid") from error
    finally:
        os.close(root_descriptor)


def _snapshot_files(root: Path) -> list[dict[str, Any]]:
    descriptor = _open_directory_fd(root, "project root")
    try:
        entries, _ = _snapshot_tree_at(descriptor)
        return [
            {
                "source_relative_path": item["source_relative_path"],
                "size_bytes": item["size_bytes"],
                "content_sha256": item["content_sha256"],
            }
            for item in entries
        ]
    finally:
        os.close(descriptor)


def _snapshot_tree_at(
    root_descriptor: int,
) -> tuple[list[dict[str, Any]], dict[str, tuple[int, int]]]:
    """Inventory a tree through stable directory handles without following links."""

    files: list[dict[str, Any]] = []
    directories: dict[str, tuple[int, int]] = {}

    def visit(directory_descriptor: int, prefix: tuple[str, ...]) -> None:
        try:
            names = sorted(os.listdir(directory_descriptor))
        except OSError as error:
            raise MigrationError("project directory cannot be inventoried") from error
        for name in names:
            try:
                metadata = os.stat(
                    name, dir_fd=directory_descriptor, follow_symlinks=False
                )
            except OSError as error:
                raise MigrationError("project entry changed during inventory") from error
            relative_parts = (*prefix, name)
            relative = "/".join(relative_parts)
            if stat.S_ISDIR(metadata.st_mode):
                child = _open_child_directory_fd(
                    directory_descriptor, name, "project directory"
                )
                try:
                    opened = os.fstat(child)
                    directories[relative] = (opened.st_dev, opened.st_ino)
                    visit(child, relative_parts)
                finally:
                    os.close(child)
            elif stat.S_ISREG(metadata.st_mode):
                file_descriptor = None
                try:
                    file_descriptor = os.open(
                        name,
                        os.O_RDONLY
                        | os.O_NOFOLLOW
                        | getattr(os, "O_CLOEXEC", 0),
                        dir_fd=directory_descriptor,
                    )
                    opened = os.fstat(file_descriptor)
                    if (
                        not stat.S_ISREG(opened.st_mode)
                        or (opened.st_dev, opened.st_ino)
                        != (metadata.st_dev, metadata.st_ino)
                    ):
                        raise MigrationError("project file changed during inventory")
                    digest, size = _hash_open_file(file_descriptor)
                    if os.fstat(file_descriptor).st_size != size:
                        raise MigrationError("project file changed during hashing")
                except OSError as error:
                    raise MigrationError("project file cannot be inventoried") from error
                finally:
                    if file_descriptor is not None:
                        os.close(file_descriptor)
                files.append({
                    "source_relative_path": relative,
                    "size_bytes": size,
                    "content_sha256": digest,
                    "device": opened.st_dev,
                    "inode": opened.st_ino,
                })
            else:
                raise MigrationError("project tree contains an unsafe entry")

    visit(root_descriptor, ())
    files.sort(key=lambda item: item["source_relative_path"])
    return files, directories


def _copy_regular_file_exact_at(
    source_root_descriptor: int,
    source_parts: tuple[str, ...],
    target_root_descriptor: int,
    destination_parts: tuple[str, ...],
    *,
    expected_size: int,
    expected_sha256: str,
) -> None:
    source_parent = _open_directory_chain_at(
        source_root_descriptor, source_parts[:-1], "migration source parent"
    )
    destination_parent = _open_directory_chain_at(
        target_root_descriptor,
        destination_parts[:-1],
        "migration destination parent",
    )
    source_descriptor: int | None = None
    destination_descriptor: int | None = None
    try:
        source_descriptor = os.open(
            source_parts[-1],
            os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0),
            dir_fd=source_parent,
        )
        source_metadata = os.fstat(source_descriptor)
        if not stat.S_ISREG(source_metadata.st_mode):
            raise MigrationError("migration source is not a regular file")
        destination_descriptor = os.open(
            destination_parts[-1],
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
            0o600,
            dir_fd=destination_parent,
        )
        digest = hashlib.sha256()
        size = 0
        while True:
            chunk = os.read(source_descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
            view = memoryview(chunk)
            while view:
                written = os.write(destination_descriptor, view)
                view = view[written:]
        os.fsync(destination_descriptor)
        if size != expected_size or digest.hexdigest() != expected_sha256:
            raise MigrationError("source changed after migration dry run")
        if os.fstat(source_descriptor).st_size != source_metadata.st_size:
            raise MigrationError("source size changed while copying")
        destination_metadata = os.fstat(destination_descriptor)
        if not stat.S_ISREG(destination_metadata.st_mode) or destination_metadata.st_size != size:
            raise MigrationError("migration destination changed while copying")
    except OSError as error:
        raise MigrationError("copy-on-write file operation failed") from error
    finally:
        if destination_descriptor is not None:
            os.close(destination_descriptor)
        if source_descriptor is not None:
            os.close(source_descriptor)
        os.close(destination_parent)
        os.close(source_parent)


def _require_plan_matches_discovery(plan: dict[str, Any], discovery: dict[str, Any]) -> None:
    expected = {
        "source_discovery_id": discovery["discovery_id"],
        "source_component": discovery["source_component"],
        "project_id": discovery["project_id"],
        "source_root": discovery["source_root"],
        "source_revision_sha256": discovery["source_revision_sha256"],
        "source_layout_sha256": discovery["layout_sha256"],
    }
    if any(plan[key] != value for key, value in expected.items()):
        raise MigrationError("migration plan differs from discovery")


def _expected_project_manifest(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "project_id": plan["project_id"],
        "state": "READY_NOT_ACTIVATED",
        "source_component": plan["source_component"],
        "source_revision_sha256": plan["source_revision_sha256"],
        "source_layout_sha256": plan["source_layout_sha256"],
        "migration_plan_id": plan["plan_id"],
        "source_authority": "PINNED_ORIGIN_READ_ONLY",
        "mappings": copy.deepcopy(plan["mappings"]),
    }


def _expected_report(plan: dict[str, Any], operation: dict[str, Any]) -> dict[str, Any]:
    report_identity = {
        "plan_id": plan["plan_id"],
        "project_id": plan["project_id"],
        "source_revision_sha256": plan["source_revision_sha256"],
        "source_layout_sha256": plan["source_layout_sha256"],
        "copied_files": plan["mappings"],
    }
    return {
        "schema_version": "1.0",
        "report_id": derive_imported_id(
            "artifact",
            "integra.migration.report",
            plan["plan_id"],
            content_sha256(report_identity),
        ),
        "plan_id": plan["plan_id"],
        "job_id": plan["job_id"],
        "project_id": plan["project_id"],
        "source_component": plan["source_component"],
        "source_root": plan["source_root"],
        "target_root": plan["target_root"],
        "target_locator_sha256": plan["target_locator_sha256"],
        "status": "SUCCEEDED",
        "source_revision_sha256": plan["source_revision_sha256"],
        "source_layout_sha256": plan["source_layout_sha256"],
        "copied_file_count": len(plan["mappings"]),
        "copied_bytes": sum(item["size_bytes"] for item in plan["mappings"]),
        "copied_files": copy.deepcopy(plan["mappings"]),
        "source_project_changed": False,
        "source_repository_changed": False,
        "activation_performed": False,
        "target_state": "READY_NOT_ACTIVATED",
        "rollback_supported": True,
        "operation_guarded": True,
        "reservation_id": operation["reservation_id"],
        "lease_id": operation["lease_id"],
        "lease_generation": operation["lease_generation"],
    }


def _require_governed_operation(
    plan: dict[str, Any],
    job_store: JobStore | None,
    reservation_store: ResourceReservationStore | None,
    lease_store: LeaseStore | None,
    now: str | None,
    *,
    action: str,
) -> dict[str, Any]:
    if (
        not isinstance(job_store, JobStore)
        or not isinstance(reservation_store, ResourceReservationStore)
        or not isinstance(lease_store, LeaseStore)
        or not isinstance(now, str)
    ):
        raise MigrationError("migration requires a governed Operations context")
    try:
        observed = datetime.fromisoformat(now.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as error:
        raise MigrationError("migration operation time is invalid") from error
    if observed.tzinfo is None:
        raise MigrationError("migration operation time must include a timezone")
    operation_identity = migration_operation_identity(plan, action)
    job = job_store.read(operation_identity["job_id"])
    if (
        job["state"] != "RUNNING"
        or job["operation_id"] != operation_identity["operation_id"]
        or job["job_class"] != "lightweight"
        or job["capability"] != {
            "id": operation_identity["capability_id"], "version": "1.0"
        }
        or not job["reservation_id"]
    ):
        raise MigrationError("migration requires its exact running Operations job")
    reservation = reservation_store.read(job["reservation_id"])
    if (
        reservation["state"] != "ACTIVE"
        or reservation["job_id"] != operation_identity["job_id"]
        or reservation["operation_id"] != operation_identity["operation_id"]
        or reservation["job_class"] != "lightweight"
        or reservation["workload"] != "CPU_LIGHT"
    ):
        raise MigrationError("migration requires its exact active resource reservation")
    lease = lease_store.read(plan["project_id"], plan["project_id"])
    writer = lease.get("writer", {}) if isinstance(lease, dict) else {}
    if (
        not isinstance(lease, dict)
        or lease.get("state") != "ACTIVE"
        or lease.get("operation_id") != operation_identity["operation_id"]
        or lease.get("project_id") != plan["project_id"]
        or lease.get("mutable_entity") != {
            "namespace": "project", "entity_id": plan["project_id"]
        }
        or lease.get("artifact_precondition") != {
            "revision_id": migration_lease_precondition(plan),
            "content_sha256": plan["source_layout_sha256"],
        }
        or writer.get("component_id") != "integra.migration"
        or writer.get("host_id") != reservation["host_id"]
        or writer.get("process_id") != reservation["process_id"]
        or writer.get("process_start_token") != reservation["process_start_token"]
        or writer.get("process_id") != os.getpid()
        or writer.get("process_start_token")
        != observe_process_start_token(os.getpid())
    ):
        raise MigrationError("migration requires its exact active Project Lease")
    expires = datetime.fromisoformat(lease["expires_at"].replace("Z", "+00:00"))
    if observed.astimezone(timezone.utc) >= expires.astimezone(timezone.utc):
        raise MigrationError("migration Project Lease is expired")
    return {
        "reservation_id": reservation["reservation_id"],
        "lease_id": lease["lease_id"],
        "lease_generation": lease["generation"],
        "operation_id": operation_identity["operation_id"],
        "job_id": operation_identity["job_id"],
    }


def migration_operation_identity(plan: dict[str, Any], action: str) -> dict[str, str]:
    """Derive the exact independent Operations v1 identity for one migration action."""

    if action not in MIGRATION_ACTIONS:
        raise MigrationError("migration action is unsupported")
    if action == "copy":
        operation_id = plan["plan_id"]
        job_id = plan["job_id"]
    else:
        operation_id = derive_imported_id(
            "operation", f"integra.migration.{action}", plan["plan_id"], plan["plan_sha256"]
        )
        job_id = derive_imported_id(
            "job", f"integra.migration.{action}", plan["plan_id"], plan["plan_sha256"]
        )
    return {
        "operation_id": operation_id,
        "job_id": job_id,
        "capability_id": f"integra.migration.{action}",
    }


def migration_lease_precondition(plan: dict[str, Any]) -> str:
    """Bind Operations authority to source truth and the exact target locator."""

    return content_sha256({
        "source_revision_sha256": plan["source_revision_sha256"],
        "source_layout_sha256": plan["source_layout_sha256"],
        "target_locator_sha256": plan["target_locator_sha256"],
    })


def _require_same_source_snapshot(expected: dict[str, Any], actual: dict[str, Any]) -> None:
    fields = (
        "source_component", "source_format", "source_schema_version", "project_id",
        "source_revision_sha256", "layout_sha256", "file_count", "total_bytes", "files",
        "source_references",
    )
    if any(expected[field] != actual[field] for field in fields):
        raise MigrationError("source project changed after discovery")


def _cleanup_failed_target(target: Path, plan: dict[str, Any], created_files: list[str]) -> None:
    if not target.exists() or target.is_symlink():
        return
    allowed = set(created_files)
    try:
        _remove_owned_target(target, allowed)
    except MigrationError:
        # Preserve unexpected state for explicit investigation; never broaden deletion.
        return


def _remove_owned_target(
    target: Path,
    expected_files: set[str],
    *,
    allowed_directories: set[str] | None = None,
) -> None:
    root = _validated_directory(target, "Integra-owned migration target")
    parent = _validated_directory(root.parent, "migration target parent")
    parent_descriptor = _open_directory_fd(parent, "migration target parent")
    try:
        root_descriptor = _open_child_directory_fd(
            parent_descriptor, root.name, "Integra-owned migration target"
        )
    except Exception:
        os.close(parent_descriptor)
        raise
    try:
        root_identity = os.fstat(root_descriptor)
        inventory, directory_identities = _snapshot_tree_at(root_descriptor)
        actual = {item["source_relative_path"] for item in inventory}
        if actual != expected_files:
            raise MigrationError(
                "rollback target contains missing or unexpected files"
            )
        expected_directories = _parent_directories(expected_files)
        actual_directories = set(directory_identities)
        directories_are_valid = (
            actual_directories == expected_directories
            if allowed_directories is None
            else expected_directories <= actual_directories <= allowed_directories
        )
        if not directories_are_valid:
            raise MigrationError(
                "rollback target contains missing or unexpected directories"
            )
        for item in inventory:
            parts = _relative_parts(item["source_relative_path"])
            file_parent = _open_directory_chain_at(
                root_descriptor, parts[:-1], "rollback file parent"
            )
            try:
                metadata = os.stat(
                    parts[-1], dir_fd=file_parent, follow_symlinks=False
                )
                if (
                    not stat.S_ISREG(metadata.st_mode)
                    or (metadata.st_dev, metadata.st_ino)
                    != (item["device"], item["inode"])
                ):
                    raise MigrationError("rollback target changed before deletion")
                os.unlink(parts[-1], dir_fd=file_parent)
            except OSError as error:
                raise MigrationError("rollback file deletion failed closed") from error
            finally:
                os.close(file_parent)
        for relative in sorted(
            actual_directories,
            key=lambda value: len(_relative_parts(value)),
            reverse=True,
        ):
            parts = _relative_parts(relative)
            directory_parent = _open_directory_chain_at(
                root_descriptor, parts[:-1], "rollback directory parent"
            )
            try:
                metadata = os.stat(
                    parts[-1],
                    dir_fd=directory_parent,
                    follow_symlinks=False,
                )
                if (
                    not stat.S_ISDIR(metadata.st_mode)
                    or (metadata.st_dev, metadata.st_ino)
                    != directory_identities[relative]
                ):
                    raise MigrationError("rollback directory changed before deletion")
                os.rmdir(parts[-1], dir_fd=directory_parent)
            except OSError as error:
                raise MigrationError("rollback directory deletion failed closed") from error
            finally:
                os.close(directory_parent)
        current_root = os.stat(root.name, dir_fd=parent_descriptor, follow_symlinks=False)
        if (
            not stat.S_ISDIR(current_root.st_mode)
            or (current_root.st_dev, current_root.st_ino)
            != (root_identity.st_dev, root_identity.st_ino)
        ):
            raise MigrationError("migration target changed before root deletion")
        os.rmdir(root.name, dir_fd=parent_descriptor)
    finally:
        os.close(root_descriptor)
        os.close(parent_descriptor)


def _parent_directories(relative_files: set[str]) -> set[str]:
    directories: set[str] = set()
    for relative in relative_files:
        parts = _relative_parts(relative)
        for depth in range(1, len(parts)):
            directories.add("/".join(parts[:depth]))
    return directories


def _directory_open_flags() -> int:
    return (
        os.O_RDONLY
        | os.O_DIRECTORY
        | os.O_NOFOLLOW
        | getattr(os, "O_CLOEXEC", 0)
    )


def _open_directory_fd(path: Path, label: str) -> int:
    """Open an absolute directory one no-follow component at a time."""

    candidate = _absolute_without_resolving(Path(path))
    try:
        initial = candidate.lstat()
    except OSError as error:
        raise MigrationError(f"{label} is unavailable") from error
    if candidate.is_symlink() or not stat.S_ISDIR(initial.st_mode):
        raise MigrationError(f"{label} is not a safe directory")
    if candidate == Path("/"):
        return os.open("/", _directory_open_flags())
    try:
        resolved_parent = candidate.parent.resolve(strict=True)
    except OSError as error:
        raise MigrationError(f"{label} parent is unavailable") from error
    descriptor = os.open("/", _directory_open_flags())
    try:
        for part in resolved_parent.parts[1:]:
            next_descriptor = _open_child_directory_fd(descriptor, part, label)
            os.close(descriptor)
            descriptor = next_descriptor
        opened = _open_child_directory_fd(descriptor, candidate.name, label)
        metadata = os.fstat(opened)
        if (metadata.st_dev, metadata.st_ino) != (initial.st_dev, initial.st_ino):
            os.close(opened)
            raise MigrationError(f"{label} changed while opening")
        os.close(descriptor)
        return opened
    except Exception:
        os.close(descriptor)
        raise


def _open_child_directory_fd(parent_descriptor: int, name: str, label: str) -> int:
    if not isinstance(name, str) or not name or "/" in name or name in {".", ".."}:
        raise MigrationError(f"{label} path component is invalid")
    try:
        descriptor = os.open(
            name,
            _directory_open_flags(),
            dir_fd=parent_descriptor,
        )
    except OSError as error:
        raise MigrationError(f"{label} is unavailable or unsafe") from error
    metadata = os.fstat(descriptor)
    if not stat.S_ISDIR(metadata.st_mode):
        os.close(descriptor)
        raise MigrationError(f"{label} is not a directory")
    return descriptor


def _open_directory_chain_at(
    root_descriptor: int,
    parts: tuple[str, ...],
    label: str,
) -> int:
    descriptor = os.dup(root_descriptor)
    try:
        for part in parts:
            next_descriptor = _open_child_directory_fd(descriptor, part, label)
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def _ensure_directories_at(
    root_descriptor: int,
    parts: tuple[str, ...],
) -> None:
    descriptor = os.dup(root_descriptor)
    try:
        for part in parts:
            try:
                os.mkdir(part, mode=0o700, dir_fd=descriptor)
            except FileExistsError:
                pass
            next_descriptor = _open_child_directory_fd(
                descriptor, part, "migration destination directory"
            )
            os.close(descriptor)
            descriptor = next_descriptor
    finally:
        os.close(descriptor)


def _hash_open_file(descriptor: int) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    while True:
        chunk = os.read(descriptor, 1024 * 1024)
        if not chunk:
            break
        digest.update(chunk)
        size += len(chunk)
    return digest.hexdigest(), size


def _verify_regular_file_at(
    root_descriptor: int,
    parts: tuple[str, ...],
    label: str,
) -> None:
    parent = _open_directory_chain_at(root_descriptor, parts[:-1], f"{label} parent")
    descriptor = None
    try:
        descriptor = os.open(
            parts[-1],
            os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0),
            dir_fd=parent,
        )
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise MigrationError(f"{label} is not a regular file")
    except OSError as error:
        raise MigrationError(f"{label} is missing or unsafe") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(parent)


def _read_regular_bytes_at(
    root_descriptor: int,
    parts: tuple[str, ...],
    label: str,
) -> bytes:
    parent = _open_directory_chain_at(root_descriptor, parts[:-1], f"{label} parent")
    descriptor = None
    try:
        descriptor = os.open(
            parts[-1],
            os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0),
            dir_fd=parent,
        )
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise MigrationError(f"{label} is not a regular file")
        chunks: list[bytes] = []
        size = 0
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
        if os.fstat(descriptor).st_size != size:
            raise MigrationError(f"{label} changed while reading")
        return b"".join(chunks)
    except OSError as error:
        raise MigrationError(f"{label} is missing or unsafe") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(parent)


def _read_json_regular_at(
    root_descriptor: int,
    parts: tuple[str, ...],
    label: str,
) -> dict[str, Any]:
    try:
        value = json.loads(_read_regular_bytes_at(root_descriptor, parts, label))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise MigrationError(f"{label} is invalid") from error
    if not isinstance(value, dict):
        raise MigrationError(f"{label} must be an object")
    return value


def _write_json_exclusive_at(
    root_descriptor: int,
    parts: tuple[str, ...],
    value: dict[str, Any],
) -> None:
    payload = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode() + b"\n"
    parent = _open_directory_chain_at(root_descriptor, parts[:-1], "JSON parent")
    descriptor = None
    try:
        descriptor = os.open(
            parts[-1],
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
            0o600,
            dir_fd=parent,
        )
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            view = view[written:]
        os.fsync(descriptor)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(parent)


def _read_json_regular(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise MigrationError(f"{label} is missing or unsafe")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise MigrationError(f"{label} is invalid") from error
    if not isinstance(value, dict):
        raise MigrationError(f"{label} must be an object")
    return value


def _validated_directory(path: Path, label: str) -> Path:
    candidate = Path(path)
    try:
        metadata = candidate.lstat()
    except OSError as error:
        raise MigrationError(f"{label} is unavailable") from error
    if candidate.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
        raise MigrationError(f"{label} is not a safe directory")
    return candidate.resolve()


def _absolute_without_resolving(path: Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    return Path(os.path.abspath(candidate))


def _is_within(candidate: Path, root: Path) -> bool:
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return True


def _relative_parts(value: str) -> tuple[str, ...]:
    if not isinstance(value, str) or not value or "\\" in value:
        raise MigrationError("project path is invalid")
    path = Path(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise MigrationError("project path escapes its root")
    return tuple(path.parts)


def _validate_sha256(value: Any, label: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise MigrationError(f"{label} must be a lowercase SHA-256")


def _validate_urn(value: Any, namespace: str) -> None:
    prefix = f"urn:integra:{namespace}:"
    if not isinstance(value, str) or not value.startswith(prefix):
        raise MigrationError(f"value must use Integra {namespace} namespace")
    suffix = value.removeprefix(prefix)
    try:
        identifier = uuid.UUID(suffix)
    except (ValueError, AttributeError) as error:
        raise MigrationError(f"value must use a canonical Integra {namespace} UUID") from error
    if str(identifier) != suffix:
        raise MigrationError(f"value must use a canonical Integra {namespace} UUID")
