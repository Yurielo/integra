"""Executable deterministic acceptance fixtures for Integra R7 migration."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .identity import derive_imported_id
from .operations import (
    JobStore,
    ProcessSupervisor,
    ResourceReservationStore,
    observe_process_start_token,
    probe_capability,
)
from .project_lease import LeaseStore
from .protocol import content_sha256

from .migration import (
    IN_PROGRESS_MARKER,
    MigrationError,
    build_dry_run,
    discover_source_project,
    execute_copy_on_write,
    migration_lease_precondition,
    migration_operation_identity,
    recover_incomplete_migration,
    rollback_migration,
    validate_migration,
)


EXPECTED_RESULTS = {
    "seminartext_copy_rollback",
    "videotext_copy_rollback",
    "stable_ids_after_move",
    "target_collision_fail_closed",
    "partial_copy_recovery",
}
NOW = "2026-09-11T00:00:00Z"
LATER = "2026-09-11T00:01:00Z"
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MIGRATION_WORKER_ARGUMENTS = (
    "-m",
    "integra_core.migration_fixtures",
    "--migration-worker",
)


def run_migration_fixtures(repository_root: Path) -> dict[str, str]:
    root = Path(repository_root)
    fixtures = root / "tests" / "fixtures" / "migration_v1"
    results = {
        "seminartext_copy_rollback": _copy_and_rollback(
            fixtures / "seminartext_project", "seminartext"
        ),
        "videotext_copy_rollback": _copy_and_rollback(
            fixtures / "videotext_project", "videotext"
        ),
        "stable_ids_after_move": _stable_ids_after_move(fixtures),
        "target_collision_fail_closed": _target_collision(fixtures),
        "partial_copy_recovery": _partial_recovery(fixtures),
    }
    if set(results) != EXPECTED_RESULTS:
        raise MigrationError("R7 fixture result inventory differs")
    return results


def _copy_and_rollback(source: Path, component: str) -> str:
    before = discover_source_project(source, component)
    with tempfile.TemporaryDirectory() as temporary:
        target = Path(temporary) / f"{component}.integra-project"
        plan = build_dry_run(before, target)
        if target.exists() or plan["status"] != "READY" or plan["source_write_operations"] != 0:
            return "FAIL"
        control = Path(temporary) / "control"
        report = run_governed_migration_action(
            control, action="copy", discovery=before, plan=plan
        )
        integrity = validate_migration(before, plan, report)
        rollback = run_governed_migration_action(
            control, action="rollback", discovery=before, plan=plan, report=report
        )
        after = discover_source_project(source, component)
        if (
            integrity["status"] != "PASS"
            or rollback["status"] != "ROLLED_BACK"
            or target.exists()
            or before != after
        ):
            return "FAIL"
    return "PASS"


def _stable_ids_after_move(fixtures: Path) -> str:
    source = fixtures / "seminartext_project"
    first = discover_source_project(source, "seminartext")
    with tempfile.TemporaryDirectory() as temporary:
        moved = Path(temporary) / "renamed-project"
        shutil.copytree(source, moved)
        second = discover_source_project(moved, "seminartext")
    identity_fields = (
        "project_id", "source_revision_sha256", "layout_sha256", "files"
    )
    return "PASS" if all(first[field] == second[field] for field in identity_fields) else "FAIL"


def _target_collision(fixtures: Path) -> str:
    source = fixtures / "videotext_project"
    discovery = discover_source_project(source, "videotext")
    with tempfile.TemporaryDirectory() as temporary:
        target = Path(temporary) / "occupied"
        target.mkdir()
        sentinel = target / "sentinel.txt"
        sentinel.write_text("owned", encoding="utf-8")
        plan = build_dry_run(discovery, target)
        if plan["status"] != "BLOCKED":
            return "FAIL"
        try:
            execute_copy_on_write(discovery, plan)
        except MigrationError:
            pass
        else:
            return "FAIL"
        if sentinel.read_text(encoding="utf-8") != "owned":
            return "FAIL"
    return "PASS"


def _partial_recovery(fixtures: Path) -> str:
    source = fixtures / "seminartext_project"
    discovery = discover_source_project(source, "seminartext")
    with tempfile.TemporaryDirectory() as temporary:
        target = Path(temporary) / "partial"
        plan = build_dry_run(discovery, target)
        target.mkdir()
        marker = {
            "schema_version": "1.0",
            "plan_id": plan["plan_id"],
            "plan_sha256": plan["plan_sha256"],
            "project_id": plan["project_id"],
            "target_locator_sha256": plan["target_locator_sha256"],
            "state": "IN_PROGRESS",
        }
        (target / IN_PROGRESS_MARKER).write_text(
            json.dumps(marker, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        mapping = plan["mappings"][0]
        destination = target / mapping["destination_relative_path"]
        destination.parent.mkdir(parents=True)
        shutil.copyfile(source / mapping["source_relative_path"], destination)
        recovered = run_governed_migration_action(
            Path(temporary) / "control", action="recover", plan=plan
        )
        if recovered["status"] != "RECOVERED_PARTIAL" or target.exists():
            return "FAIL"
    return "PASS"


def run_governed_migration_action(
    root: Path,
    *,
    action: str,
    plan: dict,
    discovery: dict | None = None,
    report: dict | None = None,
    authorization_plan: dict | None = None,
    execution_now: str = NOW,
) -> dict:
    """Execute one migration action inside its actually reserved worker process."""

    control_root = Path(root)
    control_root.mkdir(parents=True, exist_ok=True)
    process = subprocess.Popen(
        [sys.executable, *MIGRATION_WORKER_ARGUMENTS],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    authority = authorization_plan if authorization_plan is not None else plan
    completion: dict = {}
    try:
        with governed_migration_operation(
            control_root,
            authority,
            action=action,
            process=process,
            completion=completion,
        ) as operation:
            request = {
                "schema_version": "1.0",
                "action": action,
                "control_root": str(control_root.resolve()),
                "discovery": discovery,
                "plan": plan,
                "report": report,
                "now": execution_now,
            }
            payload = json.dumps(request, ensure_ascii=False, sort_keys=True).encode() + b"\n"
            try:
                stdout, stderr = process.communicate(payload, timeout=20)
            except subprocess.TimeoutExpired:
                ProcessSupervisor.shutdown(
                    process, expected_process_group_id=process.pid, timeout_seconds=0.1
                )
                raise
            if process.returncode != 0:
                raise MigrationError(
                    "isolated migration worker failed: "
                    + stderr.decode("utf-8", errors="replace").strip()
                )
            try:
                response = json.loads(stdout)
            except (UnicodeError, json.JSONDecodeError) as error:
                raise MigrationError(
                    "isolated migration worker returned invalid evidence"
                ) from error
            if not isinstance(response, dict) or set(response) != {
                "ok", "result", "error"
            }:
                raise MigrationError(
                    "isolated migration worker response differs from v1"
                )
            if response["ok"] is not True:
                raise MigrationError(str(response["error"]))
            if not isinstance(response["result"], dict):
                raise MigrationError("isolated migration worker result is invalid")

            receipt = {
                "schema_version": "1.0",
                "action": action,
                "plan_sha256": authority["plan_sha256"],
                "result": response["result"],
            }
            receipt_payload = (
                json.dumps(
                    receipt,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
                + b"\n"
            )
            receipt_relative_path = (
                Path("receipts")
                / f"{action}-{authority['plan_sha256']}.json"
            )
            receipt_path = control_root / receipt_relative_path
            receipt_path.parent.mkdir(parents=True, exist_ok=True)
            receipt_path.write_bytes(receipt_payload)
            reference = _migration_receipt_reference(
                receipt_payload,
                receipt_relative_path.as_posix(),
                authority,
                action,
                operation["component"],
            )
            completion.update({
                "outcome": "SUCCEEDED",
                "artifact_root": control_root,
                "artifact_expectations": [{
                    "artifact_id": reference["artifact_id"],
                    "status": "COMPLETE",
                    "reference": reference,
                }],
            })
            result = response["result"]
        terminal = JobStore(control_root / "jobs").read(
            migration_operation_identity(authority, action)["job_id"]
        )
        if terminal["state"] != "SUCCEEDED":
            raise MigrationError("migration Operations job did not finish successfully")
        return result
    except subprocess.TimeoutExpired as error:
        ProcessSupervisor.shutdown(
            process, expected_process_group_id=process.pid, timeout_seconds=0.1
        )
        raise MigrationError("isolated migration worker timed out") from error
    finally:
        if process.poll() is None:
            ProcessSupervisor.shutdown(
                process, expected_process_group_id=process.pid, timeout_seconds=0.1
            )


@contextmanager
def governed_migration_operation(
    root: Path,
    plan: dict,
    *,
    action: str,
    process: subprocess.Popen,
    completion: dict,
) -> Iterator[dict]:
    """Create a real isolated Operations v1 context for migration fixtures."""

    root.mkdir(parents=True, exist_ok=True)
    identity = migration_operation_identity(plan, action)
    reservation = None
    lease = None
    reservation_store = None
    lease_store = None
    job_store = None
    process_id = process.pid
    failure: Exception | None = None
    try:
        process_token = observe_process_start_token(process_id)
        job_store = JobStore(root / "jobs")
        job = job_store.create(
            job_id=identity["job_id"],
            operation_id=identity["operation_id"],
            job_class="lightweight",
            capability_id=identity["capability_id"],
            capability_version="1.0",
            resume_scope="PIPELINE_PREFIX",
            now=NOW,
        )
        job = job_store.transition(
            identity["job_id"], job["revision"], to_state="PREFLIGHT", now=NOW
        )
        capability_root = root / f"capability-{action}"
        capability_root.mkdir()
        payloads = {
            "source": plan["source_layout_sha256"].encode(),
            "contract": json.dumps(
                _migration_execution_contract(plan),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8"),
        }
        for name, payload in payloads.items():
            (capability_root / name).write_bytes(payload)
        component = _migration_component_identity()
        probe = {
            "capability": {"id": identity["capability_id"], "version": "1.0"},
            "component": component,
            "worker_path": Path(__file__).resolve(),
            "model_id": "copy-on-write-v1",
            "model_path": Path(__file__).with_name("migration.py").resolve(),
            "source_id": "migration-source-layout",
            "source_path": capability_root / "source",
            "target_id": f"migration-target:{plan['target_locator_sha256']}",
            "target_path": Path(plan["target_parent"]),
            "contract_id": "migration_plan_v1",
            "contract_path": capability_root / "contract",
            "runtime_executable_path": Path(sys.executable).resolve(),
            "runtime_version_args": [
                "-c",
                "import platform; print(platform.python_version())",
            ],
        }
        measured = probe_capability(**probe)
        expected = {
            key: copy.deepcopy(value)
            for key, value in measured.items()
            if key not in {"schema_version", "status"}
        }
        job = job_store.complete_preflight(
            identity["job_id"], job["revision"], probe=probe, expected=expected, now=NOW
        )
        lease_store = LeaseStore(root / "leases")
        writer = {
            "component_id": "integra.migration",
            "host_id": "migration-fixture-host",
            "process_id": process_id,
            "process_start_token": process_token,
        }
        lease = lease_store.acquire({
            "schema_version": "1.0",
            "lease_id": derive_imported_id(
                "lease", "integra.migration", identity["operation_id"], plan["plan_sha256"]
            ),
            "project_id": plan["project_id"],
            "mutable_entity": {"namespace": "project", "entity_id": plan["project_id"]},
            "writer": writer,
            "operation_id": identity["operation_id"],
            "acquired_at": NOW,
            "heartbeat_at": NOW,
            "expires_at": "2026-09-11T00:10:00Z",
            "released_at": None,
            "release_reason": None,
            "artifact_precondition": {
                "revision_id": migration_lease_precondition(plan),
                "content_sha256": plan["source_layout_sha256"],
            },
            "readers": [],
            "generation": 0,
        })
        disk_estimate = {
            "source": 1,
            "extracted_audio": 0,
            "cache": 1,
            "intermediate_media": 1,
            "final_output": 1,
            "safety_margin": 1,
        }
        safe_snapshot = {
            "memory_pressure": "NORMAL",
            "swap_used_bytes": 0,
            "free_disk_bytes": 1024 * 1024,
            "required_disk_bytes": 5,
            "disk_estimate": disk_estimate,
            "workspace_available": True,
            "device_available": True,
            "swap_state": "SAFE",
            "loaded_models": [],
            "loaded_models_state": "KNOWN",
            "child_processes": [],
            "child_processes_state": "KNOWN",
            "lease_state": "OWNED_BY_JOB",
            "publication_target_state": "NOT_REQUIRED",
        }
        reservation_store = ResourceReservationStore(
            root / "reservations",
            "migration-fixture-host",
            snapshot_provider=lambda **_: copy.deepcopy(safe_snapshot),
        )
        reservation = reservation_store.admit_and_reserve(
            reservation_id=derive_imported_id(
                "reservation", "integra.migration", identity["job_id"], plan["plan_sha256"]
            ),
            job_id=identity["job_id"],
            process_id=process_id,
            job_store=job_store,
            request={
                "operation_id": identity["operation_id"],
                "job_class": "lightweight",
                "workload": "CPU_LIGHT",
                "model_family": None,
                "collection_id": None,
                "collection_kind": "SINGLE",
                "requires_publication_target": False,
                "capability_report_sha256": job["preflight"]["report_sha256"],
            },
            workspace=root,
            disk_estimate=disk_estimate,
            device_paths=[root],
            lease_store=lease_store,
            lease_identity=(plan["project_id"], plan["project_id"]),
            publication_target=None,
            acquired_at=NOW,
        )
        job_store.start_reserved(
            identity["job_id"],
            job["revision"],
            reservation_store=reservation_store,
            reservation_id=reservation["reservation_id"],
            now=NOW,
        )
        yield {
            "job_store": job_store,
            "reservation_store": reservation_store,
            "lease_store": lease_store,
            "now": NOW,
            "component": component,
        }
    except Exception as error:
        failure = error
        completion.clear()
        completion.update({
            "outcome": "FAILED",
            "error_code": type(error).__name__.upper(),
            "failure_evidence_sha256": content_sha256({
                "action": action,
                "error": str(error),
            }),
        })
        raise
    finally:
        if process.poll() is None:
            ProcessSupervisor.shutdown(
                process,
                expected_process_group_id=process.pid,
                timeout_seconds=0.1,
            )
        if reservation is not None and reservation_store is not None:
            reservation_store.release(
                reservation["reservation_id"],
                job_id=reservation["job_id"],
                process_id=reservation["process_id"],
                process_start_token=reservation["process_start_token"],
                released_at=LATER,
            )
        if lease is not None and lease_store is not None:
            lease_store.release(
                lease["project_id"],
                lease["mutable_entity"]["entity_id"],
                lease["lease_id"],
                lease["writer"],
                lease["generation"],
                LATER,
            )
        if job_store is not None:
            current = job_store.read(identity["job_id"])
            if current["terminal"] is None:
                cleanup = {
                    "lease_store": lease_store,
                    "lease_project_id": plan["project_id"],
                    "lease_entity_id": plan["project_id"],
                    "reservation_store": reservation_store,
                }
                if completion.get("outcome") == "SUCCEEDED" and failure is None:
                    job_store.finish(
                        identity["job_id"],
                        current["revision"],
                        outcome="SUCCEEDED",
                        now=LATER,
                        artifact_root=completion["artifact_root"],
                        artifact_expectations=completion["artifact_expectations"],
                        **cleanup,
                    )
                else:
                    failure_sha256 = completion.get(
                        "failure_evidence_sha256",
                        content_sha256({
                            "action": action,
                            "error": "migration operation ended without completion evidence",
                        }),
                    )
                    job_store.finish(
                        identity["job_id"],
                        current["revision"],
                        outcome="FAILED",
                        now=LATER,
                        error_code=completion.get(
                            "error_code", "MISSING_COMPLETION_EVIDENCE"
                        ),
                        failure_evidence_sha256=failure_sha256,
                        **cleanup,
                    )


def _migration_component_identity() -> dict:
    """Bind preflight to the checked-out code and actual Python worker runtime."""

    def git_revision(revision: str) -> str:
        result = subprocess.run(
            ["git", "rev-parse", revision],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()

    model_path = Path(__file__).with_name("migration.py").resolve()
    model_sha256 = hashlib.sha256(model_path.read_bytes()).hexdigest()
    return {
        "component_id": "integra.migration",
        "repository": "Yurielo/integra",
        "commit_sha": git_revision("HEAD"),
        "tree_sha": git_revision("HEAD^{tree}"),
        "version": "R7",
        "contracts": ["migration_plan_v1"],
        "models": [{
            "id": "copy-on-write-v1",
            "identity_sha256": model_sha256,
        }],
        "runtime": {
            "kind": "python",
            "version": platform.python_version(),
        },
    }


def _migration_execution_contract(plan: dict) -> dict:
    """Bind capability evidence to the exact executable worker invocation."""

    executable = Path(sys.executable).resolve()
    worker = Path(__file__).resolve()
    implementation = Path(__file__).with_name("migration.py").resolve()
    return {
        "schema_version": "1.0",
        "plan_sha256": plan["plan_sha256"],
        "runtime_executable_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
        "worker_arguments": list(MIGRATION_WORKER_ARGUMENTS),
        "worker_sha256": hashlib.sha256(worker.read_bytes()).hexdigest(),
        "implementation_sha256": hashlib.sha256(
            implementation.read_bytes()
        ).hexdigest(),
    }


def _migration_receipt_reference(
    payload: bytes,
    relative_path: str,
    plan: dict,
    action: str,
    component: dict,
) -> dict:
    digest = hashlib.sha256(payload).hexdigest()
    identity = migration_operation_identity(plan, action)
    return {
        "artifact_id": derive_imported_id(
            "artifact", "integra.migration", f"{action}-receipt", digest
        ),
        "kind": "migration_action_receipt",
        "schema_id": "migration_action_receipt_v1",
        "schema_version": "1.0",
        "content_sha256": digest,
        "size_bytes": len(payload),
        "storage_scope": "INTEGRA_STORE",
        "relative_path": relative_path,
        "origin": copy.deepcopy(component),
        "provenance": {
            "parent_artifact_ids": [],
            "operation_id": identity["operation_id"],
        },
        "semantic_status": "NOT_APPLICABLE",
    }


def _migration_worker_main() -> int:
    try:
        request = json.loads(sys.stdin.buffer.read())
        if not isinstance(request, dict) or set(request) != {
            "schema_version", "action", "control_root", "discovery", "plan",
            "report", "now",
        } or request["schema_version"] != "1.0":
            raise MigrationError("isolated migration worker request differs from v1")
        root = Path(request["control_root"])
        operation = {
            "job_store": JobStore(root / "jobs"),
            "reservation_store": ResourceReservationStore(
                root / "reservations", "migration-fixture-host"
            ),
            "lease_store": LeaseStore(root / "leases"),
            "now": request["now"],
        }
        action = request["action"]
        if action == "copy":
            result = execute_copy_on_write(
                request["discovery"], request["plan"], **operation
            )
        elif action == "rollback":
            result = rollback_migration(
                request["discovery"], request["plan"], request["report"], **operation
            )
        elif action == "recover":
            result = recover_incomplete_migration(request["plan"], **operation)
        else:
            raise MigrationError("isolated migration worker action is unsupported")
        response = {"ok": True, "result": result, "error": None}
    except Exception as error:
        response = {"ok": False, "result": None, "error": str(error)}
    sys.stdout.write(json.dumps(response, ensure_ascii=False, sort_keys=True))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    if sys.argv[1:] != ["--migration-worker"]:
        raise SystemExit("unsupported migration fixture invocation")
    raise SystemExit(_migration_worker_main())
