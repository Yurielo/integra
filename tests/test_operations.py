from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from integra_core.identity import derive_imported_id
from integra_core.protocol import content_sha256
from integra_core.operations import (
    JobStore,
    ModelResidencyStore,
    OperationsError,
    ProcessSupervisor,
    ResourceReservationStore,
    ResourceScheduler,
    calculate_required_disk,
    capture_resource_snapshot,
    probe_capability,
    redact,
    structured_event,
    validate_capability_preflight,
    validate_job,
    validate_resource_reservation,
    verify_artifacts,
    observe_process_start_token,
)
from integra_core.operations_fixtures import run_operations_fixtures
from integra_core.project_lease import LeaseStore


NOW = "2026-09-11T00:00:00Z"
LATER = "2026-09-11T00:01:00Z"
AFTER = "2026-09-11T00:02:00Z"
CAPABILITY_REPORT_SHA256 = "7" * 64
CONFIG_SHA256 = "8" * 64
JOB_ID = derive_imported_id("job", "integra", "operations-test", "a" * 64)
OPERATION_ID = derive_imported_id(
    "operation", "integra", "operations-test", "b" * 64
)
ROOT = Path(__file__).resolve().parents[1]


class OperationsTests(unittest.TestCase):
    @staticmethod
    def lease_candidate(process_id: int, process_start_token: str) -> dict:
        return {
            "schema_version": "1.0",
            "lease_id": derive_imported_id(
                "lease", "integra", "operations-test", "d" * 64
            ),
            "project_id": derive_imported_id(
                "project", "integra", "operations-test", "e" * 64
            ),
            "mutable_entity": {
                "namespace": "artifact",
                "entity_id": derive_imported_id(
                    "artifact", "integra", "operations-test", "f" * 64
                ),
            },
            "writer": {
                "component_id": "integra.operations",
                "host_id": "host-1",
                "process_id": process_id,
                "process_start_token": process_start_token,
            },
            "operation_id": OPERATION_ID,
            "acquired_at": NOW,
            "heartbeat_at": NOW,
            "expires_at": LATER,
            "released_at": None,
            "release_reason": None,
            "artifact_precondition": {
                "revision_id": "revision-1",
                "content_sha256": "1" * 64,
            },
            "readers": [],
            "generation": 0,
        }

    def capability_probe(self, root: Path) -> tuple[dict, dict]:
        capability_root = root / "capability"
        capability_root.mkdir(parents=True, exist_ok=True)
        payloads = {
            "worker": b"worker",
            "model": b"model",
            "source": b"source",
            "contract": b"contract",
        }
        for name, payload in payloads.items():
            (capability_root / name).write_bytes(payload)
        component = self.component()
        component["models"] = [{
            "id": "model",
            "identity_sha256": hashlib.sha256(payloads["model"]).hexdigest(),
        }]
        probe = {
            "capability": {"id": "integra.core_alpha", "version": "1.0"},
            "component": component,
            "worker_path": capability_root / "worker",
            "model_id": "model",
            "model_path": capability_root / "model",
            "source_id": "source",
            "source_path": capability_root / "source",
            "target_id": "target",
            "target_path": root,
            "contract_id": "contract-v1",
            "contract_path": capability_root / "contract",
            "runtime_executable_path": Path("/usr/bin/printf"),
            "runtime_version_args": ["1"],
        }
        report = probe_capability(**probe)
        expected = {
            key: copy.deepcopy(value)
            for key, value in report.items()
            if key not in {"schema_version", "status"}
        }
        return probe, expected

    def start_governed_job(
        self,
        root: Path,
        *,
        resume_scope: str = "PIPELINE_PREFIX",
        start: bool = True,
    ) -> dict:
        store, job = self.create_job(root / "jobs", resume_scope=resume_scope)
        job = store.transition(
            JOB_ID, job["revision"], to_state="PREFLIGHT", now=NOW
        )
        probe, expected = self.capability_probe(root)
        job = store.complete_preflight(
            JOB_ID,
            job["revision"],
            probe=probe,
            expected=expected,
            now=NOW,
        )
        process = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        token = observe_process_start_token(process.pid)
        lease_store = LeaseStore(root / "leases")
        lease = lease_store.acquire(self.lease_candidate(process.pid, token))
        reservation_store = ResourceReservationStore(
            root / "reservations",
            "host-1",
            snapshot_provider=lambda **kwargs: self.safe_snapshot(
                lease_state="OWNED_BY_JOB"
            ),
        )
        reservation_id = derive_imported_id(
            "reservation", "integra", "operations-test", "c" * 64
        )
        reservation = reservation_store.admit_and_reserve(
            reservation_id=reservation_id,
            job_id=JOB_ID,
            process_id=process.pid,
            job_store=store,
            request=self.request(
                job_class="heavy-media",
                workload="FFMPEG_HEAVY",
                model_family=None,
                collection_id=None,
                collection_kind="SINGLE",
                capability_report_sha256=job["preflight"]["report_sha256"]
            ),
            workspace=root,
            disk_estimate={
                "source": 1, "extracted_audio": 1, "cache": 1,
                "intermediate_media": 1, "final_output": 1,
                "safety_margin": 1,
            },
            device_paths=[root],
            lease_store=lease_store,
            lease_identity=(
                lease["project_id"], lease["mutable_entity"]["entity_id"]
            ),
            publication_target=None,
            acquired_at=NOW,
        )
        if start:
            job = store.start_reserved(
                JOB_ID,
                job["revision"],
                reservation_store=reservation_store,
                reservation_id=reservation_id,
                now=NOW,
            )
        return {
            "store": store,
            "job": job,
            "probe": probe,
            "expected": expected,
            "process": process,
            "lease_store": lease_store,
            "lease": lease,
            "reservation_store": reservation_store,
            "reservation": reservation,
        }

    @staticmethod
    def clean_execution(context: dict) -> None:
        cleanup = ProcessSupervisor.shutdown(
            context["process"],
            expected_process_group_id=context["process"].pid,
            timeout_seconds=0.1,
        )
        if cleanup["status"] != "PASS":
            raise AssertionError("process cleanup failed")
        reservation = context["reservation"]
        context["reservation_store"].release(
            reservation["reservation_id"],
            job_id=reservation["job_id"],
            process_id=reservation["process_id"],
            process_start_token=reservation["process_start_token"],
            released_at=LATER,
        )
        lease = context["lease"]
        context["lease_store"].release(
            lease["project_id"],
            lease["mutable_entity"]["entity_id"],
            lease["lease_id"],
            lease["writer"],
            lease["generation"],
            LATER,
        )

    @staticmethod
    def durable_cleanup_arguments(context: dict) -> dict:
        lease = context["lease"]
        return {
            "lease_store": context["lease_store"],
            "lease_project_id": lease["project_id"],
            "lease_entity_id": lease["mutable_entity"]["entity_id"],
            "reservation_store": context["reservation_store"],
        }

    def test_governed_fixture_inventory_is_exact_and_deterministic(self) -> None:
        fixture_root = ROOT / "tests/fixtures/operations_v1"
        expected = {
            "success", "interruption", "resume", "unsafe_resource",
            "capability_drift", "integrity_failure", "process_cleanup",
        }
        paths = sorted(fixture_root.glob("*.json"))
        self.assertEqual({path.stem for path in paths}, expected)
        for path in paths:
            document = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(document["scenario"], path.stem)
            canonical = json.dumps(
                document, ensure_ascii=False, indent=2, sort_keys=True
            ) + "\n"
            self.assertEqual(path.read_text(encoding="utf-8"), canonical)
        self.assertEqual(
            run_operations_fixtures(ROOT),
            {scenario: "PASS" for scenario in expected},
        )

    def create_job(self, root: Path, *, resume_scope: str = "PIPELINE_PREFIX"):
        store = JobStore(root)
        record = store.create(
            job_id=JOB_ID,
            operation_id=OPERATION_ID,
            job_class="heavy-media",
            capability_id="integra.core_alpha",
            capability_version="1.0",
            resume_scope=resume_scope,
            now=NOW,
        )
        return store, record

    def test_job_lifecycle_checkpoint_resume_and_terminal_immutability(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            context = self.start_governed_job(Path(temporary))
            store, job = context["store"], context["job"]
            job = store.progress(
                JOB_ID,
                job["revision"],
                sequence=1,
                fraction=0.5,
                stage="render",
                now=NOW,
            )
            self.assertEqual(job["progress"]["eta_status"], "UNKNOWN")
            preflight_sha256 = job["preflight"]["report_sha256"]
            job = store.checkpoint(
                JOB_ID,
                job["revision"],
                checkpoint_id="checkpoint-1",
                input_hashes=["1" * 64],
                worker_commit_sha="2" * 40,
                capability_report_sha256=preflight_sha256,
                config_sha256=CONFIG_SHA256,
                now=NOW,
            )
            job = store.transition(
                JOB_ID, job["revision"], to_state="PAUSED", now=NOW
            )
            job = store.transition(
                JOB_ID, job["revision"], to_state="RESUMING", now=LATER
            )
            with self.assertRaisesRegex(OperationsError, "resume identity differs"):
                store.resume(
                    JOB_ID,
                    job["revision"],
                    input_hashes=["3" * 64],
                    worker_commit_sha="2" * 40,
                    capability_report_sha256=preflight_sha256,
                    config_sha256=CONFIG_SHA256,
                    now=LATER,
                )
            job = store.resume(
                JOB_ID,
                job["revision"],
                input_hashes=["1" * 64],
                worker_commit_sha="2" * 40,
                capability_report_sha256=preflight_sha256,
                config_sha256=CONFIG_SHA256,
                now=LATER,
            )
            job = store.complete_preflight(
                JOB_ID,
                job["revision"],
                probe=context["probe"],
                expected=context["expected"],
                now=LATER,
            )
            job = store.start_reserved(
                JOB_ID,
                job["revision"],
                reservation_store=context["reservation_store"],
                reservation_id=context["reservation"]["reservation_id"],
                now=LATER,
            )
            payload = b"complete-output"
            artifact_path = Path(temporary) / "artifacts/value.bin"
            artifact_path.parent.mkdir(parents=True)
            artifact_path.write_bytes(payload)
            reference = self.artifact_reference(payload)
            with self.assertRaisesRegex(
                OperationsError, "durable cleanup stores are required"
            ):
                store.finish(
                    JOB_ID,
                    job["revision"],
                    outcome="SUCCEEDED",
                    now=LATER,
                    artifact_root=Path(temporary),
                    artifact_expectations=[{
                        "artifact_id": reference["artifact_id"],
                        "status": "COMPLETE",
                        "reference": reference,
                    }],
                )
            self.clean_execution(context)
            wrong_reference = copy.deepcopy(reference)
            wrong_reference["provenance"]["operation_id"] = derive_imported_id(
                "operation", "integra", "wrong-operation", "4" * 64
            )
            with self.assertRaisesRegex(OperationsError, "operation differs"):
                store.finish(
                    JOB_ID,
                    job["revision"],
                    outcome="SUCCEEDED",
                    now=LATER,
                    artifact_root=Path(temporary),
                    artifact_expectations=[{
                        "artifact_id": wrong_reference["artifact_id"],
                        "status": "COMPLETE",
                        "reference": wrong_reference,
                    }],
                    **self.durable_cleanup_arguments(context),
                )
            job = store.finish(
                JOB_ID,
                job["revision"],
                outcome="SUCCEEDED",
                now=LATER,
                artifact_root=Path(temporary),
                artifact_expectations=[{
                    "artifact_id": reference["artifact_id"],
                    "status": "COMPLETE",
                    "reference": reference,
                }],
                **self.durable_cleanup_arguments(context),
            )
            validate_job(store.read(JOB_ID))
            self.assertEqual(job["progress"]["fraction"], 1.0)
            with self.assertRaisesRegex(OperationsError, "terminal job is immutable"):
                store.finish(
                    JOB_ID,
                    job["revision"],
                    outcome="FAILED",
                    now=LATER,
                    error_code="ALREADY_COMPLETE",
                    failure_evidence_sha256="9" * 64,
                )

    def test_cancel_requires_acknowledgement_and_becomes_terminal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            context = self.start_governed_job(
                Path(temporary), resume_scope="NONE"
            )
            store, job = context["store"], context["job"]
            job = store.request_cancel(JOB_ID, job["revision"], now=NOW)
            self.assertIsNone(job["cancellation"]["acknowledged_at"])
            cancel_ack = {
                "protocol_version": "1.0",
                "message_id": derive_imported_id(
                    "message", "integra", "cancel-ack", "a" * 64
                ),
                "correlation_id": derive_imported_id(
                    "session", "integra", "cancel-ack", "b" * 64
                ),
                "sent_at": LATER,
                "type": "CANCEL_ACK",
                "payload": {"job_id": JOB_ID, "status": "CANCELLED"},
            }
            with self.assertRaisesRegex(
                OperationsError, "durable cleanup stores are required"
            ):
                store.acknowledge_cancel(
                    JOB_ID,
                    job["revision"],
                    now=LATER,
                    cancel_ack=cancel_ack,
                )
            self.clean_execution(context)
            job = store.acknowledge_cancel(
                JOB_ID,
                job["revision"],
                now=LATER,
                cancel_ack=cancel_ack,
                **self.durable_cleanup_arguments(context),
            )
            self.assertEqual(job["state"], "CANCELLED")
            self.assertEqual(job["terminal"]["outcome"], "CANCELLED")

    def test_terminal_paths_detect_reservation_before_start_link(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            context = self.start_governed_job(Path(temporary), start=False)
            store, job = context["store"], context["job"]
            self.assertEqual(job["state"], "WAITING_RESOURCES")
            self.assertIsNone(job["reservation_id"])
            with self.assertRaisesRegex(
                OperationsError, "resource reservation store is required"
            ):
                store.finish(
                    JOB_ID,
                    job["revision"],
                    outcome="FAILED",
                    now=LATER,
                    error_code="ADMISSION_ABORTED",
                    failure_evidence_sha256="9" * 64,
                )
            with self.assertRaisesRegex(OperationsError, "lease is not released"):
                store.finish(
                    JOB_ID,
                    job["revision"],
                    outcome="FAILED",
                    now=LATER,
                    error_code="ADMISSION_ABORTED",
                    failure_evidence_sha256="9" * 64,
                    **self.durable_cleanup_arguments(context),
                )
            job = store.request_cancel(JOB_ID, job["revision"], now=LATER)
            cancel_ack = {
                "protocol_version": "1.0",
                "message_id": derive_imported_id(
                    "message", "integra", "reservation-race", "5" * 64
                ),
                "correlation_id": derive_imported_id(
                    "session", "integra", "reservation-race", "6" * 64
                ),
                "sent_at": LATER,
                "type": "CANCEL_ACK",
                "payload": {"job_id": JOB_ID, "status": "CANCELLED"},
            }
            with self.assertRaisesRegex(
                OperationsError, "resource reservation store is required"
            ):
                store.acknowledge_cancel(
                    JOB_ID, job["revision"], now=LATER, cancel_ack=cancel_ack
                )
            self.clean_execution(context)
            cancelled = store.acknowledge_cancel(
                JOB_ID,
                job["revision"],
                now=LATER,
                cancel_ack=cancel_ack,
                **self.durable_cleanup_arguments(context),
            )
            self.assertEqual(cancelled["state"], "CANCELLED")

    def test_duplicate_reservation_and_expired_lease_are_denied(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            context = self.start_governed_job(root, start=False)
            second_id = derive_imported_id(
                "reservation", "integra", "duplicate-reservation", "8" * 64
            )
            arguments = {
                "reservation_id": second_id,
                "job_id": JOB_ID,
                "process_id": context["process"].pid,
                "job_store": context["store"],
                "request": self.request(
                    job_class="heavy-media",
                    workload="FFMPEG_HEAVY",
                    model_family=None,
                    collection_id=None,
                    collection_kind="SINGLE",
                    capability_report_sha256=context["job"]["preflight"][
                        "report_sha256"
                    ],
                ),
                "workspace": root,
                "disk_estimate": {
                    "source": 1,
                    "extracted_audio": 1,
                    "cache": 1,
                    "intermediate_media": 1,
                    "final_output": 1,
                    "safety_margin": 1,
                },
                "device_paths": [root],
                "lease_store": context["lease_store"],
                "lease_identity": (
                    context["lease"]["project_id"],
                    context["lease"]["mutable_entity"]["entity_id"],
                ),
                "publication_target": None,
            }
            with self.assertRaisesRegex(
                OperationsError, "already has an active reservation"
            ):
                context["reservation_store"].admit_and_reserve(
                    **arguments, acquired_at=NOW
                )
            with self.assertRaisesRegex(
                OperationsError, "Project Lease differs"
            ):
                context["reservation_store"].admit_and_reserve(
                    **arguments, acquired_at=AFTER
                )
            self.clean_execution(context)

    def test_interruption_recovery_cannot_bypass_resume_revalidation(self) -> None:
        fixture = json.loads(
            (ROOT / "tests/fixtures/operations_v1/interruption.json").read_text(
                encoding="utf-8"
            )
        )
        with tempfile.TemporaryDirectory() as temporary:
            context = self.start_governed_job(Path(temporary))
            store, job = context["store"], context["job"]
            preflight_sha256 = job["preflight"]["report_sha256"]
            job = store.checkpoint(
                JOB_ID,
                job["revision"],
                checkpoint_id="checkpoint",
                input_hashes=["1" * 64],
                worker_commit_sha="2" * 40,
                capability_report_sha256=preflight_sha256,
                config_sha256=CONFIG_SHA256,
                now=NOW,
            )
            job = store.transition(
                JOB_ID, job["revision"], to_state="PAUSED", now=NOW
            )
            job = store.transition(
                JOB_ID, job["revision"], to_state="RESUMING", now=NOW
            )
            job = store.resume(
                JOB_ID,
                job["revision"],
                input_hashes=["1" * 64],
                worker_commit_sha="2" * 40,
                capability_report_sha256=preflight_sha256,
                config_sha256=CONFIG_SHA256,
                now=NOW,
            )
            job = store.complete_preflight(
                JOB_ID,
                job["revision"],
                probe=context["probe"],
                expected=context["expected"],
                now=NOW,
            )
            job = store.start_reserved(
                JOB_ID,
                job["revision"],
                reservation_store=context["reservation_store"],
                reservation_id=context["reservation"]["reservation_id"],
                now=NOW,
            )
            job = store.transition(
                JOB_ID,
                job["revision"],
                to_state=fixture["expected_state"],
                now=LATER,
                evidence_sha256="9" * 64,
            )
            with self.assertRaisesRegex(OperationsError, "illegal job transition"):
                store.transition(
                    JOB_ID, job["revision"], to_state="PREFLIGHT", now=LATER
                )
            self.clean_execution(context)

    def test_illegal_transition_revision_conflict_and_fabricated_eta_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store, job = self.create_job(Path(temporary))
            with self.assertRaisesRegex(OperationsError, "governed finish path"):
                store.transition(
                    JOB_ID, job["revision"], to_state="SUCCEEDED", now=NOW
                )
            with self.assertRaisesRegex(OperationsError, "revision conflict"):
                store.transition(JOB_ID, 99, to_state="PREFLIGHT", now=NOW)
            job = store.transition(
                JOB_ID, job["revision"], to_state="PREFLIGHT", now=NOW
            )
            with self.assertRaisesRegex(OperationsError, "governed paths"):
                store.transition(
                    JOB_ID,
                    job["revision"],
                    to_state="WAITING_RESOURCES",
                    now=NOW,
                    evidence_sha256="9" * 64,
                )
            job["progress"]["eta_seconds"] = 5
            with self.assertRaisesRegex(OperationsError, "unknown ETA"):
                validate_job(job)
            job["progress"]["eta_status"] = "ESTIMATED"
            job["progress"]["eta_seconds"] = float("nan")
            with self.assertRaisesRegex(OperationsError, "non-negative"):
                validate_job(job)
            job["progress"]["eta_status"] = "UNKNOWN"
            job["progress"]["eta_seconds"] = None
            job["events"][0]["to_state"] = "RUNNING"
            with self.assertRaisesRegex(OperationsError, "begin at QUEUED"):
                validate_job(job)
        with tempfile.TemporaryDirectory() as temporary:
            context = self.start_governed_job(
                Path(temporary), resume_scope="NONE"
            )
            store, job = context["store"], context["job"]
            with self.assertRaisesRegex(OperationsError, "does not support"):
                store.checkpoint(
                    JOB_ID,
                    job["revision"],
                    checkpoint_id="checkpoint",
                    input_hashes=["1" * 64],
                    worker_commit_sha="2" * 40,
                    capability_report_sha256=job["preflight"]["report_sha256"],
                    config_sha256=CONFIG_SHA256,
                    now=NOW,
                )
            self.clean_execution(context)

    @staticmethod
    def component():
        return {
            "component_id": "worker",
            "repository": "Yurielo/worker",
            "commit_sha": "1" * 40,
            "tree_sha": "2" * 40,
            "version": "1.0",
            "contracts": ["contract-v1"],
            "models": [{"id": "model", "identity_sha256": "3" * 64}],
            "runtime": {"kind": "local", "version": "1"},
        }

    def test_capability_preflight_is_exact_and_drift_blocks(self) -> None:
        component = self.component()
        expected = {
            "capability": {"id": "capability", "version": "1.0"},
            "worker": {
                "id": "worker",
                "identity_sha256": "4" * 64,
            },
            "component": component,
            "model": {"id": "model", "identity_sha256": "3" * 64},
            "runtime": {
                "id": "local",
                "version": "1",
                "executable_sha256": hashlib.sha256(
                    Path("/usr/bin/printf").read_bytes()
                ).hexdigest(),
                "probe_arguments_sha256": content_sha256(["1"]),
            },
            "source": {"id": "source", "content_sha256": "5" * 64},
            "target": {"id": "local-store", "state": "AVAILABLE"},
            "contract": {"id": "contract-v1", "schema_sha256": "6" * 64},
        }
        report = {"schema_version": "1.0", "status": "READY", **expected}
        validate_capability_preflight(report, expected)
        changed = {**expected, "model": {"id": "other", "identity_sha256": "3" * 64}}
        with self.assertRaisesRegex(OperationsError, "identity drift"):
            validate_capability_preflight(report, changed)
        unavailable = copy.deepcopy(report)
        unavailable["target"]["state"] = "UNAVAILABLE"
        expected_unavailable = {
            key: copy.deepcopy(value)
            for key, value in unavailable.items()
            if key not in {"schema_version", "status"}
        }
        with self.assertRaisesRegex(OperationsError, "target is not available"):
            validate_capability_preflight(unavailable, expected_unavailable)
        contradiction = copy.deepcopy(report)
        contradiction["component"]["models"] = []
        contradictory_expected = {
            key: copy.deepcopy(value)
            for key, value in contradiction.items()
            if key not in {"schema_version", "status"}
        }
        with self.assertRaisesRegex(OperationsError, "absent from component"):
            validate_capability_preflight(contradiction, contradictory_expected)

    def test_capability_probe_measures_files_and_rejects_model_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            files = {
                "worker": b"worker",
                "model": b"model",
                "source": b"source",
                "contract": b"contract",
            }
            for name, payload in files.items():
                (root / name).write_bytes(payload)
            component = self.component()
            component["models"] = [{
                "id": "model",
                "identity_sha256": hashlib.sha256(files["model"]).hexdigest(),
            }]
            report = probe_capability(
                capability={"id": "capability", "version": "1.0"},
                component=component,
                worker_path=root / "worker",
                model_id="model",
                model_path=root / "model",
                source_id="source",
                source_path=root / "source",
                target_id="target",
                target_path=root,
                contract_id="contract-v1",
                contract_path=root / "contract",
                runtime_executable_path=Path("/usr/bin/printf"),
                runtime_version_args=["1"],
            )
            expected = {
                key: copy.deepcopy(value)
                for key, value in report.items()
                if key not in {"schema_version", "status"}
            }
            validate_capability_preflight(report, expected)
            alternate_probe = {
                **{
                    key: value
                    for key, value in report.items()
                    if key not in {"schema_version", "status"}
                }
            }
            alternate_runtime = probe_capability(
                capability={"id": "capability", "version": "1.0"},
                component=component,
                worker_path=root / "worker",
                model_id="model",
                model_path=root / "model",
                source_id="source",
                source_path=root / "source",
                target_id="target",
                target_path=root,
                contract_id="contract-v1",
                contract_path=root / "contract",
                runtime_executable_path=Path("/bin/echo"),
                runtime_version_args=["1"],
            )
            self.assertNotEqual(
                alternate_runtime["runtime"]["executable_sha256"],
                alternate_probe["runtime"]["executable_sha256"],
            )
            with self.assertRaisesRegex(OperationsError, "identity drift"):
                validate_capability_preflight(alternate_runtime, expected)
            (root / "model").write_bytes(b"changed")
            with self.assertRaisesRegex(OperationsError, "measured model differs"):
                probe_capability(
                    capability={"id": "capability", "version": "1.0"},
                    component=component,
                    worker_path=root / "worker",
                    model_id="model",
                    model_path=root / "model",
                    source_id="source",
                    source_path=root / "source",
                    target_id="target",
                    target_path=root,
                    contract_id="contract-v1",
                    contract_path=root / "contract",
                    runtime_executable_path=Path("/usr/bin/printf"),
                    runtime_version_args=["1"],
                )

    @staticmethod
    def safe_snapshot(*, lease_state: str = "CLEAR"):
        return {
            "memory_pressure": "NORMAL",
            "swap_used_bytes": 0,
            "swap_state": "SAFE",
            "free_disk_bytes": 10_000,
            "required_disk_bytes": 5_000,
            "disk_estimate": {
                "source": 1_000,
                "extracted_audio": 500,
                "cache": 500,
                "intermediate_media": 1_000,
                "final_output": 1_000,
                "safety_margin": 1_000,
            },
            "workspace_available": True,
            "device_available": True,
            "loaded_models": [],
            "loaded_models_state": "KNOWN",
            "child_processes": [],
            "child_processes_state": "KNOWN",
            "lease_state": lease_state,
            "publication_target_state": "NOT_REQUIRED",
        }

    @staticmethod
    def request(**overrides):
        value = {
            "operation_id": OPERATION_ID,
            "job_class": "heavy-model",
            "workload": "ASR",
            "model_family": "WHISPER",
            "collection_id": "playlist-1",
            "collection_kind": "PLAYLIST",
            "requires_publication_target": False,
            "capability_report_sha256": CAPABILITY_REPORT_SHA256,
        }
        value.update(overrides)
        return value

    def test_resource_policy_blocks_unsafe_and_conflicting_heavy_work(self) -> None:
        safe = self.safe_snapshot()
        self.assertEqual(ResourceScheduler.admit(self.request(), safe, []).status, "ALLOW")
        unsafe = dict(safe)
        unsafe["free_disk_bytes"] = 4_999
        self.assertIn(
            "INSUFFICIENT_CALCULATED_DISK",
            ResourceScheduler.admit(self.request(), unsafe, []).reasons,
        )
        active = [{
            "job_class": "heavy-model",
            "model_family": "OLLAMA",
            "workload": "LLM",
            "collection_kind": "PLAYLIST",
            "collection_id": "playlist-1",
        }]
        reasons = ResourceScheduler.admit(self.request(), safe, active).reasons
        self.assertIn("HEAVY_MODEL_ALREADY_ACTIVE", reasons)
        self.assertIn("WHISPER_OLLAMA_CONCURRENCY_DENIED", reasons)
        self.assertIn("PLAYLIST_ITEM_ALREADY_ACTIVE", reasons)
        unknown = dict(safe)
        unknown["loaded_models_state"] = "UNKNOWN"
        self.assertIn(
            "PROCESS_OR_MODEL_STATE_UNVERIFIED",
            ResourceScheduler.admit(self.request(), unknown, []).reasons,
        )
        invalid_metric = dict(safe)
        invalid_metric["free_disk_bytes"] = "unknown"
        self.assertIn(
            "UNVERIFIED_RESOURCE_METRIC",
            ResourceScheduler.admit(self.request(), invalid_metric, []).reasons,
        )
        invalid_models = dict(safe)
        invalid_models["loaded_models"] = [{"not": "hashable"}]
        self.assertIn(
            "PROCESS_OR_MODEL_STATE_UNVERIFIED",
            ResourceScheduler.admit(self.request(), invalid_models, []).reasons,
        )
        self.assertIn(
            "ACTIVE_RESERVATION_STATE_UNVERIFIED",
            ResourceScheduler.admit(self.request(), safe, [{}]).reasons,
        )
        with self.assertRaisesRegex(OperationsError, "request is invalid"):
            ResourceScheduler.admit(
                self.request(requires_publication_target="yes"), safe, []
            )
        with self.assertRaisesRegex(OperationsError, "request is invalid"):
            ResourceScheduler.admit(
                self.request(workload="ffmpeg", model_family=None), safe, []
            )
        symmetric = [{
            "job_class": "heavy-media",
            "workload": "FFMPEG_HEAVY",
            "model_family": None,
            "collection_kind": "SINGLE",
            "collection_id": None,
        }]
        self.assertIn(
            "FFMPEG_WHISPER_CONCURRENCY_DENIED",
            ResourceScheduler.admit(
                self.request(collection_kind="SINGLE", collection_id=None),
                safe,
                symmetric,
            ).reasons,
        )

    def test_atomic_resource_reservation_and_verified_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            context = self.start_governed_job(root)
            store = context["reservation_store"]
            job_store, job = context["store"], context["job"]
            reservation = context["reservation"]
            job = job_store.transition(
                JOB_ID,
                job["revision"],
                to_state="RECOVERY_REQUIRED",
                now=LATER,
                evidence_sha256="9" * 64,
            )
            self.assertEqual(reservation["state"], "ACTIVE")
            second = subprocess.Popen(
                [sys.executable, "-c", "import time; time.sleep(30)"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
            with self.assertRaisesRegex(OperationsError, "job does not exist"):
                store.admit_and_reserve(
                    reservation_id=derive_imported_id(
                        "reservation", "integra", "second", "d" * 64
                    ),
                    job_id=derive_imported_id("job", "integra", "second", "c" * 64),
                    process_id=second.pid,
                    job_store=job_store,
                    request=self.request(collection_id="playlist-2"),
                    workspace=root,
                    disk_estimate={
                        "source": 1, "extracted_audio": 1, "cache": 1,
                        "intermediate_media": 1, "final_output": 1,
                        "safety_margin": 1,
                    },
                    device_paths=[root],
                    lease_store=context["lease_store"],
                    lease_identity=(
                        context["lease"]["project_id"],
                        context["lease"]["mutable_entity"]["entity_id"],
                    ),
                    publication_target=None,
                    acquired_at=NOW,
                )
            with self.assertRaisesRegex(OperationsError, "not proven safe"):
                store.recover(
                    reservation["reservation_id"],
                    job_store=job_store,
                    recovered_at=LATER,
                )
            ProcessSupervisor.shutdown(
                context["process"],
                expected_process_group_id=context["process"].pid,
                timeout_seconds=0.1,
            )
            ProcessSupervisor.shutdown(
                second,
                expected_process_group_id=second.pid,
                timeout_seconds=0.1,
            )
            recovered = store.recover(
                reservation["reservation_id"],
                job_store=job_store,
                recovered_at=LATER,
            )
            self.assertEqual(recovered["state"], "RELEASED")
            self.assertEqual(recovered["release_reason"], "VERIFIED_RECOVERY")
            validate_resource_reservation(recovered)
            lease = context["lease"]
            context["lease_store"].release(
                lease["project_id"],
                lease["mutable_entity"]["entity_id"],
                lease["lease_id"],
                lease["writer"],
                lease["generation"],
                LATER,
            )

    def test_resource_snapshot_marks_unknown_process_and_model_truth(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            snapshot = capture_resource_snapshot(
                workspace=Path(temporary),
                disk_estimate={
                    "source": 1,
                    "extracted_audio": 0,
                    "cache": 0,
                    "intermediate_media": 0,
                    "final_output": 0,
                    "safety_margin": 0,
                },
                owner_pid=os.getpid(),
                device_paths=[Path(temporary)],
                command_runner=lambda args, **kwargs: subprocess.CompletedProcess(
                    args, 1, "", ""
                ),
            )
            self.assertEqual(snapshot["loaded_models_state"], "UNKNOWN")
            self.assertEqual(snapshot["lease_state"], "UNKNOWN")
            self.assertEqual(ResourceScheduler.admit(self.request(), snapshot, []).status, "DENY")

    def test_resource_snapshot_binds_project_lease_operation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            process = subprocess.Popen(
                [sys.executable, "-c", "import time; time.sleep(30)"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
            token = observe_process_start_token(process.pid)
            lease_store = LeaseStore(root / "leases")
            lease = lease_store.acquire(self.lease_candidate(process.pid, token))
            wrong_operation = derive_imported_id(
                "operation", "integra", "wrong-lease-operation", "7" * 64
            )
            snapshot = capture_resource_snapshot(
                workspace=root,
                disk_estimate={
                    "source": 1,
                    "extracted_audio": 0,
                    "cache": 0,
                    "intermediate_media": 0,
                    "final_output": 0,
                    "safety_margin": 0,
                },
                owner_pid=process.pid,
                device_paths=[root],
                lease_store=lease_store,
                lease_identity=(
                    lease["project_id"], lease["mutable_entity"]["entity_id"]
                ),
                operation_id=wrong_operation,
                observed_at=NOW,
                command_runner=lambda args, **kwargs: subprocess.CompletedProcess(
                    args, 1, "", ""
                ),
            )
            self.assertEqual(snapshot["lease_state"], "CONFLICT")
            ProcessSupervisor.shutdown(
                process,
                expected_process_group_id=process.pid,
                timeout_seconds=0.1,
            )
            lease_store.release(
                lease["project_id"],
                lease["mutable_entity"]["entity_id"],
                lease["lease_id"],
                lease["writer"],
                lease["generation"],
                LATER,
            )

    def test_structured_logs_recursively_redact_secrets_and_private_content(self) -> None:
        details = {
            "Authorization": "Bearer super-secret",
            "nested": [{"cookie": "session=secret"}, "token=abc123"],
            "private_content": "transcript",
            "status": "READY",
            "code": {"access_token": "nested-secret"},
            "reason_code": "eyJabcdefghijk.abcdefghijk.abcdefghijk",
            "classification": "sk-proj-SUPERSECRET123",
            "component_id": "/Users/alice/private/client.mov",
            "capability_id": "alice@example.com",
        }
        event = structured_event(
            job_id=JOB_ID,
            operation_id=OPERATION_ID,
            sequence=0,
            level="ERROR",
            event="worker_failed",
            occurred_at=NOW,
            details=details,
        )
        serialized = str(event)
        for secret in (
            "super-secret", "session=secret", "abc123", "transcript",
            "nested-secret", "eyJabcdefghijk",
            "SUPERSECRET123", "/Users/alice", "alice@example.com",
        ):
            self.assertNotIn(secret, serialized)
        self.assertEqual(event["details"]["status"], "READY")
        for private_token in (
            "HIV_positive", "Alice", "client_secret_value",
            "ALICE", "HIV_POSITIVE", "CLIENT_SMITH", "SECRET_123",
        ):
            private_event = structured_event(
                job_id=JOB_ID,
                operation_id=OPERATION_ID,
                sequence=1,
                level="WARN",
                event="worker_failed",
                occurred_at=NOW,
                details={"status": private_token},
            )
            self.assertEqual(private_event["details"]["status"], "[REDACTED]")
        self.assertNotIn("nested", event["details"])
        self.assertNotIn("Authorization", event["details"])
        self.assertEqual(event["details"]["code"], "[REDACTED]")
        self.assertEqual(redact({"ToKeN": "value"})["ToKeN"], "[REDACTED]")

    def test_disk_estimate_is_explicit_and_exact(self) -> None:
        terms = {
            "source": 10,
            "extracted_audio": 20,
            "cache": 30,
            "intermediate_media": 40,
            "final_output": 50,
            "safety_margin": 60,
        }
        self.assertEqual(calculate_required_disk(terms), 210)
        terms["safety_margin"] = -1
        with self.assertRaisesRegex(OperationsError, "non-negative"):
            calculate_required_disk(terms)

    @staticmethod
    def artifact_reference(payload: bytes):
        return {
            "artifact_id": derive_imported_id("artifact", "integra", "test", hashlib.sha256(payload).hexdigest()),
            "kind": "diagnostic_fixture",
            "schema_id": "fixture_v1",
            "schema_version": "1.0",
            "content_sha256": hashlib.sha256(payload).hexdigest(),
            "size_bytes": len(payload),
            "storage_scope": "INTEGRA_STORE",
            "relative_path": "artifacts/value.bin",
            "origin": OperationsTests.component(),
            "provenance": {
                "parent_artifact_ids": [],
                "operation_id": OPERATION_ID,
            },
            "semantic_status": "NOT_APPLICABLE",
        }

    def test_integrity_detects_missing_partial_altered_and_identity_mismatch(self) -> None:
        payload = b"complete"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "artifacts/value.bin"
            path.parent.mkdir()
            path.write_bytes(payload)
            reference = self.artifact_reference(payload)
            expected = [{"artifact_id": reference["artifact_id"], "status": "COMPLETE", "reference": reference}]
            self.assertEqual(verify_artifacts(root, expected)["status"], "PASS")
            source_reference = copy.deepcopy(reference)
            source_reference["storage_scope"] = "SOURCE_READ_ONLY"
            source_expected = [{
                "artifact_id": source_reference["artifact_id"],
                "status": "COMPLETE",
                "reference": source_reference,
            }]
            self.assertEqual(
                verify_artifacts(root, source_expected)["findings"][0]["code"],
                "IDENTITY_OR_PARTIAL_STATE",
            )
            path.write_bytes(b"changed!")
            self.assertEqual(verify_artifacts(root, expected)["findings"][0]["code"], "ALTERED_HASH")
            path.unlink()
            self.assertEqual(verify_artifacts(root, expected)["findings"][0]["code"], "MISSING_OR_ESCAPED")
            path.write_bytes(payload)
            expected[0]["status"] = "PARTIAL"
            self.assertEqual(verify_artifacts(root, expected)["findings"][0]["code"], "IDENTITY_OR_PARTIAL_STATE")
            expected[0]["status"] = "COMPLETE"
            staging = root / ".staging/artifacts/value.bin"
            staging.parent.mkdir(parents=True)
            staging.write_bytes(payload)
            expected[0]["reference"] = {
                **reference,
                "relative_path": ".staging/artifacts/value.bin",
            }
            self.assertEqual(
                verify_artifacts(root, expected)["findings"][0]["code"],
                "IDENTITY_OR_PARTIAL_STATE",
            )

    def test_process_shutdown_reaps_and_model_unload_is_owner_scoped(self) -> None:
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
        self.assertEqual(report["status"], "PASS")
        self.assertFalse(report["orphaned"])
        loaded = ["user-model"]
        with tempfile.TemporaryDirectory() as temporary:
            residencies = ModelResidencyStore(Path(temporary))
            with self.assertRaisesRegex(OperationsError, "pre-existing model"):
                residencies.acquire(
                    model_id="user-model",
                    job_id=JOB_ID,
                    operation_id=OPERATION_ID,
                    load=loaded.append,
                    unload=loaded.remove,
                    loaded_models=lambda: list(loaded),
                    acquired_at=NOW,
                )
            residencies.acquire(
                model_id="owned",
                job_id=JOB_ID,
                operation_id=OPERATION_ID,
                load=loaded.append,
                unload=loaded.remove,
                loaded_models=lambda: list(loaded),
                acquired_at=NOW,
            )
            with self.assertRaisesRegex(OperationsError, "does not exist"):
                ProcessSupervisor.unload_model(
                    "user-model",
                    job_id=JOB_ID,
                    operation_id=OPERATION_ID,
                    residency_store=residencies,
                    unload=loaded.remove,
                    loaded_models=lambda: loaded,
                    released_at=LATER,
                )
            result = ProcessSupervisor.unload_model(
                "owned",
                job_id=JOB_ID,
                operation_id=OPERATION_ID,
                residency_store=residencies,
                unload=loaded.remove,
                loaded_models=lambda: loaded,
                released_at=LATER,
            )
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(residencies.read("owned")["state"], "RELEASED")

    def test_model_acquire_rolls_back_when_post_load_observation_fails(self) -> None:
        loaded: list[str] = []
        observations = 0

        def loaded_models() -> list[str]:
            nonlocal observations
            observations += 1
            if observations == 2:
                raise RuntimeError("observer failed after load")
            return list(loaded)

        with tempfile.TemporaryDirectory() as temporary:
            store = ModelResidencyStore(Path(temporary))
            with self.assertRaisesRegex(RuntimeError, "observer failed"):
                store.acquire(
                    model_id="rollback-model",
                    job_id=JOB_ID,
                    operation_id=OPERATION_ID,
                    load=loaded.append,
                    unload=loaded.remove,
                    loaded_models=loaded_models,
                    acquired_at=NOW,
                )
            self.assertEqual(loaded, [])
            self.assertEqual(store.read("rollback-model")["state"], "RELEASED")

    def test_model_acquire_rolls_back_when_loader_raises_after_loading(self) -> None:
        loaded: list[str] = []

        def partial_load(model_id: str) -> None:
            loaded.append(model_id)
            raise RuntimeError("loader failed after side effect")

        with tempfile.TemporaryDirectory() as temporary:
            store = ModelResidencyStore(Path(temporary))
            with self.assertRaisesRegex(RuntimeError, "loader failed"):
                store.acquire(
                    model_id="partial-model",
                    job_id=JOB_ID,
                    operation_id=OPERATION_ID,
                    load=partial_load,
                    unload=loaded.remove,
                    loaded_models=lambda: list(loaded),
                    acquired_at=NOW,
                )
            self.assertEqual(loaded, [])
            self.assertEqual(store.read("partial-model")["state"], "RELEASED")

    def test_model_observer_outage_retains_durable_recovery_ownership(self) -> None:
        loaded: list[str] = []
        observations = 0

        def loaded_models() -> list[str]:
            nonlocal observations
            observations += 1
            if observations > 1:
                raise RuntimeError("observer unavailable")
            return list(loaded)

        def partial_load(model_id: str) -> None:
            loaded.append(model_id)
            raise RuntimeError("loader response lost")

        with tempfile.TemporaryDirectory() as temporary:
            store = ModelResidencyStore(Path(temporary))
            with self.assertRaisesRegex(OperationsError, "recovery is required"):
                store.acquire(
                    model_id="observer-outage-model",
                    job_id=JOB_ID,
                    operation_id=OPERATION_ID,
                    load=partial_load,
                    unload=loaded.remove,
                    loaded_models=loaded_models,
                    acquired_at=NOW,
                )
            self.assertEqual(loaded, [])
            self.assertEqual(
                store.read("observer-outage-model")["state"],
                "RECOVERY_REQUIRED",
            )

    def test_model_recovery_requires_unload_and_absence_proof(self) -> None:
        loaded: list[str] = []

        def partial_load(model_id: str) -> None:
            loaded.append(model_id)
            raise RuntimeError("loader response lost")

        def failed_unload(model_id: str) -> None:
            raise RuntimeError(f"cannot unload {model_id}")

        with tempfile.TemporaryDirectory() as temporary:
            store = ModelResidencyStore(Path(temporary))
            with self.assertRaisesRegex(OperationsError, "recovery is required"):
                store.acquire(
                    model_id="stuck-model",
                    job_id=JOB_ID,
                    operation_id=OPERATION_ID,
                    load=partial_load,
                    unload=failed_unload,
                    loaded_models=lambda: list(loaded),
                    acquired_at=NOW,
                )
            self.assertEqual(store.read("stuck-model")["state"], "RECOVERY_REQUIRED")
            self.assertEqual(loaded, ["stuck-model"])
            result = ProcessSupervisor.unload_model(
                "stuck-model",
                job_id=JOB_ID,
                operation_id=OPERATION_ID,
                residency_store=store,
                unload=loaded.remove,
                loaded_models=lambda: list(loaded),
                released_at=LATER,
            )
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(loaded, [])
            self.assertEqual(store.read("stuck-model")["state"], "RELEASED")

    def test_private_top_level_log_event_is_rejected(self) -> None:
        with self.assertRaisesRegex(OperationsError, "event name"):
            structured_event(
                job_id=JOB_ID,
                operation_id=OPERATION_ID,
                sequence=0,
                level="INFO",
                event="ALICE",
                occurred_at=NOW,
                details={"status": "PASS"},
            )


if __name__ == "__main__":
    unittest.main()
