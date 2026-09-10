"""Executable deterministic acceptance fixtures for Operations & Diagnostics v1."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from .identity import derive_imported_id
from .operations import (
    JobStore,
    OperationsError,
    ProcessSupervisor,
    ResourceReservationStore,
    ResourceScheduler,
    observe_process_start_token,
    probe_capability,
    validate_capability_preflight,
    verify_artifacts,
)
from .project_lease import LeaseStore


NOW = "2026-09-11T00:00:00Z"
LATER = "2026-09-11T00:01:00Z"


def run_operations_fixtures(root: Path) -> dict[str, str]:
    fixture_root = Path(root) / "tests/fixtures/operations_v1"
    fixtures = {
        path.stem: json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(fixture_root.glob("*.json"))
    }
    expected = {
        "success", "interruption", "resume", "unsafe_resource",
        "capability_drift", "integrity_failure", "process_cleanup",
    }
    if set(fixtures) != expected:
        raise OperationsError("operations fixture inventory differs")
    results = {
        "success": _success(fixtures["success"]),
        "interruption": _interruption(fixtures["interruption"]),
        "resume": _resume(fixtures["resume"]),
        "unsafe_resource": _unsafe_resource(fixtures["unsafe_resource"]),
        "capability_drift": _capability_drift(fixtures["capability_drift"]),
        "integrity_failure": _integrity_failure(fixtures["integrity_failure"]),
        "process_cleanup": _process_cleanup(fixtures["process_cleanup"]),
    }
    return results


def _success(fixture: dict[str, Any]) -> str:
    if fixture.get("expected_terminal") != "SUCCEEDED" or fixture.get(
        "required_checks"
    ) != [
        "measured_capability_preflight", "store_captured_resource_snapshot",
        "durable_reservation", "output_promotion", "integrity",
        "durable_lease_release", "durable_resource_release",
        "process_cleanup",
    ]:
        raise OperationsError("success fixture differs from v1")
    with tempfile.TemporaryDirectory() as temporary:
        context = _start_context(Path(temporary))
        root = context["root"]
        payload = b"operations-success"
        path = root / "output.bin"
        path.write_bytes(payload)
        reference = _reference(payload, "output.bin")
        expectations = [{
            "artifact_id": reference["artifact_id"],
            "status": "COMPLETE",
            "reference": reference,
        }]
        _cleanup_context(context)
        job = context["store"].finish(
            context["job_id"],
            context["job"]["revision"],
            outcome="SUCCEEDED",
            now=LATER,
            artifact_root=root,
            artifact_expectations=expectations,
            **_cleanup_arguments(context),
        )
    return "PASS" if job["state"] == "SUCCEEDED" else "FAIL"


def _interruption(fixture: dict[str, Any]) -> str:
    if fixture != {
        "automatic_success_forbidden": True,
        "event": "controller_restart",
        "expected_state": "RECOVERY_REQUIRED",
        "previous_state": "RUNNING",
        "scenario": "interruption",
    }:
        raise OperationsError("interruption fixture differs from v1")
    with tempfile.TemporaryDirectory() as temporary:
        context = _start_context(Path(temporary))
        job = context["store"].transition(
            context["job_id"],
            context["job"]["revision"],
            to_state="RECOVERY_REQUIRED",
            now=LATER,
            evidence_sha256="9" * 64,
        )
        if job["state"] != "RECOVERY_REQUIRED" or job["terminal"] is not None:
            return "FAIL"
        ProcessSupervisor.shutdown(
            context["process"],
            expected_process_group_id=context["process"].pid,
            timeout_seconds=0.1,
        )
        context["reservation_store"].recover(
            context["reservation"]["reservation_id"],
            job_store=context["store"],
            recovered_at=LATER,
        )
        _release_lease(context)
        job = context["store"].finish(
            context["job_id"],
            job["revision"],
            outcome="UNKNOWN_OUTCOME",
            now=LATER,
            error_code="CONTROLLER_RESTART",
            failure_evidence_sha256="8" * 64,
        )
    return "PASS" if job["state"] == "UNKNOWN_OUTCOME" else "FAIL"


def _resume(fixture: dict[str, Any]) -> str:
    if fixture.get("resume_scope") != "PIPELINE_PREFIX" or fixture.get(
        "required_revalidation"
    ) != [
        "job_id", "operation_id", "capability", "input_hashes",
        "worker_commit_sha", "capability_report_sha256", "config_sha256",
        "checkpoint_binding", "preflight", "resource_state",
    ]:
        raise OperationsError("resume fixture differs from v1")
    with tempfile.TemporaryDirectory() as temporary:
        context = _start_context(Path(temporary))
        store, job = context["store"], context["job"]
        preflight_sha256 = job["preflight"]["report_sha256"]
        job = store.checkpoint(
            context["job_id"],
            job["revision"],
            checkpoint_id="fixture-checkpoint",
            input_hashes=["3" * 64],
            worker_commit_sha="2" * 40,
            capability_report_sha256=preflight_sha256,
            config_sha256="4" * 64,
            now=NOW,
        )
        job = store.transition(
            context["job_id"], job["revision"], to_state="PAUSED", now=NOW
        )
        job = store.transition(
            context["job_id"], job["revision"], to_state="RESUMING", now=NOW
        )
        try:
            store.resume(
                context["job_id"],
                job["revision"],
                input_hashes=["0" * 64],
                worker_commit_sha="2" * 40,
                capability_report_sha256=preflight_sha256,
                config_sha256="4" * 64,
                now=NOW,
            )
        except OperationsError:
            pass
        else:
            return "FAIL"
        job = store.resume(
            context["job_id"],
            job["revision"],
            input_hashes=["3" * 64],
            worker_commit_sha="2" * 40,
            capability_report_sha256=preflight_sha256,
            config_sha256="4" * 64,
            now=NOW,
        )
        job = store.complete_preflight(
            context["job_id"],
            job["revision"],
            probe=context["probe"],
            expected=context["expected"],
            now=NOW,
        )
        job = store.start_reserved(
            context["job_id"],
            job["revision"],
            reservation_store=context["reservation_store"],
            reservation_id=context["reservation"]["reservation_id"],
            now=NOW,
        )
        context["job"] = job
        payload = b"operations-resume"
        (context["root"] / "resume.bin").write_bytes(payload)
        reference = _reference(payload, "resume.bin")
        _cleanup_context(context)
        job = store.finish(
            context["job_id"],
            job["revision"],
            outcome="SUCCEEDED",
            now=LATER,
            artifact_root=context["root"],
            artifact_expectations=[{
                "artifact_id": reference["artifact_id"],
                "status": "COMPLETE",
                "reference": reference,
            }],
            **_cleanup_arguments(context),
        )
    return "PASS" if job["state"] == "SUCCEEDED" else "FAIL"


def _unsafe_resource(fixture: dict[str, Any]) -> str:
    snapshot = {
        "memory_pressure": fixture["snapshot"]["memory_pressure"],
        "swap_used_bytes": 0,
        "swap_state": fixture["snapshot"]["swap_state"],
        "free_disk_bytes": 100,
        "required_disk_bytes": 6,
        "disk_estimate": {
            "source": 1, "extracted_audio": 1, "cache": 1,
            "intermediate_media": 1, "final_output": 1, "safety_margin": 1,
        },
        "workspace_available": fixture["snapshot"]["workspace_available"],
        "device_available": True,
        "loaded_models": [],
        "loaded_models_state": "KNOWN",
        "child_processes": [],
        "child_processes_state": "KNOWN",
        "lease_state": "CLEAR",
        "publication_target_state": "NOT_REQUIRED",
    }
    request = {
        "operation_id": derive_imported_id(
            "operation", "integra", "unsafe-resource", "8" * 64
        ),
        "job_class": fixture["request_class"],
        "workload": "ASR",
        "model_family": "WHISPER",
        "collection_id": None,
        "collection_kind": "SINGLE",
        "requires_publication_target": False,
        "capability_report_sha256": "7" * 64,
    }
    decision = ResourceScheduler.admit(request, snapshot, [])
    return "PASS" if decision.status == fixture["expected_admission"] else "FAIL"


def _capability_drift(fixture: dict[str, Any]) -> str:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        probe, expected = _capability_probe(root)
        report = probe_capability(**probe)
        validate_capability_preflight(report, expected)
        Path(probe["model_path"]).write_bytes(b"changed-model")
        try:
            probe_capability(**probe)
        except OperationsError:
            return "PASS" if fixture["expected_preflight"] == "BLOCKED" else "FAIL"
    return "FAIL"


def _integrity_failure(fixture: dict[str, Any]) -> str:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        payload = b"original"
        (root / "output.bin").write_bytes(b"altered!")
        reference = _reference(payload, "output.bin")
        report = verify_artifacts(root, [{
            "artifact_id": reference["artifact_id"],
            "status": "COMPLETE",
            "reference": reference,
        }])
    codes = [item["code"] for item in report["findings"]]
    return "PASS" if report["status"] == fixture["expected_integrity"] and fixture["finding"] in codes else "FAIL"


def _process_cleanup(fixture: dict[str, Any]) -> str:
    process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    report = ProcessSupervisor.shutdown(
        process,
        expected_process_group_id=process.pid,
        timeout_seconds=0.1,
    )
    return "PASS" if report["orphaned"] == fixture["expected_orphaned"] and report["status"] == "PASS" else "FAIL"


def _capability_probe(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    capability_root = root / "capability"
    capability_root.mkdir(parents=True, exist_ok=True)
    payloads = {
        "worker": b"worker", "model": b"model",
        "source": b"source", "contract": b"contract",
    }
    for name, payload in payloads.items():
        (capability_root / name).write_bytes(payload)
    component = {
        "component_id": "fixture-worker", "repository": "Yurielo/integra",
        "commit_sha": "1" * 40, "tree_sha": "2" * 40, "version": "1.0",
        "contracts": ["operations-v1"],
        "models": [{
            "id": "fixture-model",
            "identity_sha256": hashlib.sha256(payloads["model"]).hexdigest(),
        }],
        "runtime": {"kind": "local", "version": "1"},
    }
    probe = {
        "capability": {"id": "fixture-capability", "version": "1.0"},
        "component": component,
        "worker_path": capability_root / "worker",
        "model_id": "fixture-model",
        "model_path": capability_root / "model",
        "source_id": "fixture-source",
        "source_path": capability_root / "source",
        "target_id": "fixture-target",
        "target_path": root,
        "contract_id": "operations-v1",
        "contract_path": capability_root / "contract",
        "runtime_executable_path": Path("/usr/bin/printf"),
        "runtime_version_args": ["1"],
    }
    report = probe_capability(**probe)
    expected = {
        key: json.loads(json.dumps(value))
        for key, value in report.items()
        if key not in {"schema_version", "status"}
    }
    return probe, expected


def _safe_snapshot() -> dict[str, Any]:
    return {
        "memory_pressure": "NORMAL", "swap_used_bytes": 0,
        "swap_state": "SAFE", "free_disk_bytes": 100,
        "required_disk_bytes": 6,
        "disk_estimate": {
            "source": 1, "extracted_audio": 1, "cache": 1,
            "intermediate_media": 1, "final_output": 1, "safety_margin": 1,
        },
        "workspace_available": True, "device_available": True,
        "loaded_models": [], "loaded_models_state": "KNOWN",
        "child_processes": [], "child_processes_state": "KNOWN",
        "lease_state": "OWNED_BY_JOB",
        "publication_target_state": "NOT_REQUIRED",
    }


def _start_context(root: Path) -> dict[str, Any]:
    job_id = derive_imported_id("job", "integra", "fixture", "1" * 64)
    operation_id = derive_imported_id(
        "operation", "integra", "fixture", "2" * 64
    )
    store = JobStore(root / "jobs")
    job = store.create(
        job_id=job_id,
        operation_id=operation_id,
        job_class="heavy-media",
        capability_id="fixture-capability",
        capability_version="1.0",
        resume_scope="PIPELINE_PREFIX",
        now=NOW,
    )
    job = store.transition(job_id, job["revision"], to_state="PREFLIGHT", now=NOW)
    probe, expected = _capability_probe(root)
    job = store.complete_preflight(
        job_id, job["revision"], probe=probe, expected=expected, now=NOW
    )
    process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    token = observe_process_start_token(process.pid)
    project_id = derive_imported_id("project", "integra", "fixture", "3" * 64)
    entity_id = derive_imported_id("artifact", "integra", "fixture", "4" * 64)
    lease_store = LeaseStore(root / "leases")
    lease = lease_store.acquire({
        "schema_version": "1.0",
        "lease_id": derive_imported_id("lease", "integra", "fixture", "5" * 64),
        "project_id": project_id,
        "mutable_entity": {"namespace": "artifact", "entity_id": entity_id},
        "writer": {
            "component_id": "integra.operations", "host_id": "fixture-host",
            "process_id": process.pid, "process_start_token": token,
        },
        "operation_id": operation_id,
        "acquired_at": NOW, "heartbeat_at": NOW, "expires_at": LATER,
        "released_at": None, "release_reason": None,
        "artifact_precondition": {
            "revision_id": "fixture-revision", "content_sha256": "6" * 64,
        },
        "readers": [], "generation": 0,
    })
    reservation_store = ResourceReservationStore(
        root / "reservations",
        "fixture-host",
        snapshot_provider=lambda **kwargs: _safe_snapshot(),
    )
    reservation = reservation_store.admit_and_reserve(
        reservation_id=derive_imported_id(
            "reservation", "integra", "fixture", "7" * 64
        ),
        job_id=job_id,
        process_id=process.pid,
        job_store=store,
        request={
            "operation_id": operation_id,
            "job_class": "heavy-media", "workload": "FFMPEG_HEAVY",
            "model_family": None, "collection_id": None,
            "collection_kind": "SINGLE", "requires_publication_target": False,
            "capability_report_sha256": job["preflight"]["report_sha256"],
        },
        workspace=root,
        disk_estimate={
            "source": 1, "extracted_audio": 1, "cache": 1,
            "intermediate_media": 1, "final_output": 1, "safety_margin": 1,
        },
        device_paths=[root],
        lease_store=lease_store,
        lease_identity=(project_id, entity_id),
        publication_target=None,
        acquired_at=NOW,
    )
    job = store.start_reserved(
        job_id,
        job["revision"],
        reservation_store=reservation_store,
        reservation_id=reservation["reservation_id"],
        now=NOW,
    )
    return {
        "root": root, "job_id": job_id, "operation_id": operation_id,
        "store": store, "job": job, "probe": probe, "expected": expected,
        "process": process, "lease_store": lease_store, "lease": lease,
        "reservation_store": reservation_store, "reservation": reservation,
    }


def _cleanup_context(context: dict[str, Any]) -> None:
    report = ProcessSupervisor.shutdown(
        context["process"],
        expected_process_group_id=context["process"].pid,
        timeout_seconds=0.1,
    )
    if report["status"] != "PASS":
        raise OperationsError("fixture process cleanup failed")
    reservation = context["reservation"]
    context["reservation_store"].release(
        reservation["reservation_id"],
        job_id=reservation["job_id"],
        process_id=reservation["process_id"],
        process_start_token=reservation["process_start_token"],
        released_at=LATER,
    )
    _release_lease(context)


def _release_lease(context: dict[str, Any]) -> None:
    lease = context["lease"]
    context["lease_store"].release(
        lease["project_id"], lease["mutable_entity"]["entity_id"],
        lease["lease_id"], lease["writer"], lease["generation"], LATER,
    )


def _cleanup_arguments(context: dict[str, Any]) -> dict[str, Any]:
    lease = context["lease"]
    return {
        "lease_store": context["lease_store"],
        "lease_project_id": lease["project_id"],
        "lease_entity_id": lease["mutable_entity"]["entity_id"],
        "reservation_store": context["reservation_store"],
    }


def _reference(payload: bytes, relative_path: str) -> dict[str, Any]:
    digest = hashlib.sha256(payload).hexdigest()
    operation_id = derive_imported_id(
        "operation", "integra", "fixture", "2" * 64
    )
    return {
        "artifact_id": derive_imported_id(
            "artifact", "integra", "fixture", digest
        ),
        "kind": "operations_fixture",
        "schema_id": "fixture_v1",
        "schema_version": "1.0",
        "content_sha256": digest,
        "size_bytes": len(payload),
        "storage_scope": "INTEGRA_STORE",
        "relative_path": relative_path,
        "origin": {
            "component_id": "integra.operations",
            "repository": "Yurielo/integra",
            "commit_sha": "1" * 40,
            "tree_sha": "2" * 40,
            "version": "1.0",
            "contracts": ["operations-v1"],
            "models": [],
            "runtime": {"kind": "python", "version": "3"},
        },
        "provenance": {
            "parent_artifact_ids": [],
            "operation_id": operation_id,
        },
        "semantic_status": "NOT_APPLICABLE",
    }
