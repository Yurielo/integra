"""Fail-closed Operations & Diagnostics primitives for Integra 1.0."""

from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import math
import os
import re
import signal
import stat
import subprocess
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .protocol import (
    content_sha256,
    resume_binding,
    validate_artifact_reference,
    validate_component_identity,
    validate_message,
)
from .project_lease import LeaseStore


JOB_STATES = {
    "QUEUED", "PREFLIGHT", "WAITING_RESOURCES", "RUNNING", "PAUSE_REQUESTED",
    "PAUSED", "RESUMING", "RECOVERY_REQUIRED", "CANCEL_REQUESTED",
    "CANCELLED", "SUCCEEDED", "FAILED", "UNKNOWN_OUTCOME",
}
TERMINAL_STATES = {"CANCELLED", "SUCCEEDED", "FAILED", "UNKNOWN_OUTCOME"}
JOB_CLASSES = {"lightweight", "heavy-model", "heavy-media"}
WORKLOADS = {"ASR", "LLM", "FFMPEG_HEAVY", "MEDIA_LIGHT", "CPU_LIGHT"}
MODEL_FAMILIES = {"WHISPER", "OLLAMA"}
RESUME_SCOPES = {"NONE", "WORKER", "PIPELINE_PREFIX"}
TRANSITIONS = {
    "QUEUED": {"PREFLIGHT", "CANCEL_REQUESTED", "FAILED"},
    "PREFLIGHT": {"WAITING_RESOURCES", "CANCEL_REQUESTED", "FAILED"},
    "WAITING_RESOURCES": {"RUNNING", "CANCEL_REQUESTED", "FAILED"},
    "RUNNING": {"PAUSE_REQUESTED", "CANCEL_REQUESTED", "SUCCEEDED", "FAILED", "UNKNOWN_OUTCOME", "RECOVERY_REQUIRED"},
    "PAUSE_REQUESTED": {"PAUSED", "CANCEL_REQUESTED", "FAILED", "UNKNOWN_OUTCOME"},
    "PAUSED": {"RESUMING", "CANCEL_REQUESTED", "FAILED"},
    "RESUMING": {"PREFLIGHT", "CANCEL_REQUESTED", "FAILED"},
    "RECOVERY_REQUIRED": {"RESUMING", "CANCEL_REQUESTED", "FAILED", "UNKNOWN_OUTCOME"},
    "CANCEL_REQUESTED": {"CANCELLED", "FAILED", "UNKNOWN_OUTCOME"},
}
SENSITIVE_KEYS = {
    "authorization", "cookie", "cookies", "credential", "credentials",
    "password", "personal_data", "private_content", "secret", "token",
}
SENSITIVE_KEY_PARTS = {
    "authorization", "cookie", "credential", "key", "password", "personal",
    "private", "secret", "token",
}
TOKEN_PATTERN = re.compile(
    r"(?i)(bearer\s+|token[=:]\s*|password[=:]\s*|cookie[=:]\s*)[^\s,;]+"
)
JWT_PATTERN = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")
SECRET_VALUE_PATTERN = re.compile(
    r"(?i)\b(?:sk-(?:proj-)?|gh[opusr]_|xox[baprs]-)[A-Za-z0-9_-]{8,}\b"
)
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
ABSOLUTE_PATH_PATTERN = re.compile(r"^(?:/|[A-Za-z]:[\\/])")
SAFE_LOG_TOKEN = re.compile(r"^[A-Za-z0-9_.:-]{1,256}$")
UUID_TEXT = r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"
PUBLIC_COMPONENT_ID = re.compile(
    r"^(?:integra|seminartext|videotext)\.[a-z0-9]+(?:[._-][a-z0-9]+)*$"
)
PUBLIC_LOG_STATES = JOB_STATES | {
    "ACTIVE", "ALLOW", "AVAILABLE", "BLOCKED", "CLEAR", "COMPLETE",
    "CONFLICT", "CRITICAL", "DENY", "ESTIMATED", "KNOWN", "NORMAL",
    "NOT_REQUIRED", "NOT_RUNNING", "OWNER_RELEASE", "PASS", "PID_REUSED",
    "READY", "RELEASED", "SAFE", "STALE", "SYNC", "UNAVAILABLE",
    "UNKNOWN", "UNSAFE", "VERIFIED_RECOVERY", "VERIFIED_STALE_RECOVERY",
    "WRITER_RELEASE",
}
PUBLIC_LOG_CODES = {
    "ACTIVE_RESERVATION_STATE_UNVERIFIED", "ALTERED_HASH",
    "DISK_ESTIMATE_MISMATCH", "DUPLICATE_IDENTITY",
    "FFMPEG_WHISPER_CONCURRENCY_DENIED", "HEAVY_MEDIA_ALREADY_ACTIVE",
    "HEAVY_MODEL_ALREADY_ACTIVE", "IDENTITY_MISMATCH",
    "IDENTITY_OR_PARTIAL_STATE", "INSUFFICIENT_CALCULATED_DISK",
    "LEASE_UNSAFE", "MISSING_OR_ESCAPED", "PARTIAL_SIZE",
    "PLAYLIST_ITEM_ALREADY_ACTIVE", "PROCESS_OR_MODEL_STATE_UNVERIFIED",
    "PUBLICATION_TARGET_UNAVAILABLE", "UNSAFE_ARTIFACT_TYPE",
    "UNSAFE_MEMORY_PRESSURE", "UNSAFE_OR_UNKNOWN_SWAP",
    "UNVERIFIED_DISK_ESTIMATE", "UNVERIFIED_RESOURCE_METRIC",
    "WHISPER_OLLAMA_CONCURRENCY_DENIED", "WORKSPACE_OR_DEVICE_UNAVAILABLE",
}
PUBLIC_LOG_CLASSIFICATIONS = {"OPERATIONAL", "PUBLIC", "REDACTED"}
PUBLIC_LOG_EVENTS = {
    "capability_preflight", "cancellation_acknowledged",
    "cancellation_requested", "checkpoint_created", "integrity_checked",
    "job_created", "job_finished", "job_transition", "model_loaded",
    "model_unloaded", "process_cleanup", "progress_updated",
    "reservation_acquired", "reservation_released", "worker_failed",
    "worker_started",
}


class OperationsError(RuntimeError):
    """Raised when operational truth is incomplete, unsafe, or contradictory."""


def _instant(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as error:
        raise OperationsError("timestamp must be ISO-8601 with timezone") from error
    if parsed.tzinfo is None:
        raise OperationsError("timestamp must include timezone")
    return parsed.astimezone(timezone.utc)


def _sha256(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise OperationsError(f"{label} must be a lowercase SHA-256")
    return value


def _git_sha(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 40
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise OperationsError(f"{label} must be a lowercase 40-character Git SHA")
    return value


def _urn(value: Any, namespace: str, label: str) -> str:
    if (
        not isinstance(value, str)
        or re.fullmatch(rf"urn:integra:{re.escape(namespace)}:{UUID_TEXT}", value)
        is None
    ):
        raise OperationsError(f"{label} must be a canonical Integra {namespace} URN")
    return value


def _atomic_json(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(document, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def validate_job(record: dict[str, Any]) -> None:
    required = {
        "schema_version", "job_id", "operation_id", "revision", "job_class",
        "capability", "state", "progress", "cancellation", "checkpoint",
        "preflight", "reservation_id", "resume_scope", "events", "terminal",
        "created_at", "updated_at",
    }
    if not isinstance(record, dict) or set(record) != required:
        raise OperationsError("job record fields differ from v1")
    if record["schema_version"] != "1.0":
        raise OperationsError("unsupported job schema version")
    for key, namespace in (("job_id", "job"), ("operation_id", "operation")):
        _urn(record[key], namespace, key)
    if isinstance(record["revision"], bool) or not isinstance(record["revision"], int) or record["revision"] < 1:
        raise OperationsError("job revision must be positive")
    if record["job_class"] not in JOB_CLASSES or record["state"] not in JOB_STATES:
        raise OperationsError("job class or state is invalid")
    if record["resume_scope"] not in RESUME_SCOPES:
        raise OperationsError("job resume scope is invalid")
    capability = record["capability"]
    if (
        not isinstance(capability, dict)
        or set(capability) != {"id", "version"}
        or not all(isinstance(capability[key], str) and capability[key] for key in capability)
    ):
        raise OperationsError("job capability identity is incomplete")
    progress = record["progress"]
    if not isinstance(progress, dict) or set(progress) != {
        "sequence", "fraction", "stage", "eta_status", "eta_seconds"
    }:
        raise OperationsError("job progress fields differ from v1")
    if (
        isinstance(progress["sequence"], bool)
        or not isinstance(progress["sequence"], int)
        or progress["sequence"] < 0
        or isinstance(progress["fraction"], bool)
        or not isinstance(progress["fraction"], (int, float))
        or not math.isfinite(progress["fraction"])
        or not 0 <= progress["fraction"] <= 1
        or not isinstance(progress["stage"], str)
        or not progress["stage"]
    ):
        raise OperationsError("job progress is invalid")
    if progress["eta_status"] == "UNKNOWN":
        if progress["eta_seconds"] is not None:
            raise OperationsError("unknown ETA cannot contain invented seconds")
    elif progress["eta_status"] == "ESTIMATED":
        if (
            isinstance(progress["eta_seconds"], bool)
            or not isinstance(progress["eta_seconds"], (int, float))
            or not math.isfinite(progress["eta_seconds"])
            or progress["eta_seconds"] < 0
        ):
            raise OperationsError("estimated ETA must contain non-negative seconds")
    else:
        raise OperationsError("ETA status is invalid")
    cancellation = record["cancellation"]
    if not isinstance(cancellation, dict) or set(cancellation) != {
        "requested_at", "acknowledged_at"
    }:
        raise OperationsError("cancellation fields differ from v1")
    for value in cancellation.values():
        if value is not None:
            _instant(value)
    checkpoint = record["checkpoint"]
    if checkpoint is not None:
        if not isinstance(checkpoint, dict) or set(checkpoint) != {
            "checkpoint_id", "created_at", "input_hashes", "worker_commit_sha",
            "capability_report_sha256", "config_sha256",
            "execution_identity_sha256", "protocol_binding_sha256",
            "binding_sha256",
        }:
            raise OperationsError("checkpoint fields differ from v1")
        _instant(checkpoint["created_at"])
        if not isinstance(checkpoint["checkpoint_id"], str) or not checkpoint["checkpoint_id"]:
            raise OperationsError("checkpoint ID is required")
        _git_sha(checkpoint["worker_commit_sha"], "checkpoint worker commit")
        for field in (
            "capability_report_sha256",
            "config_sha256",
            "execution_identity_sha256",
            "protocol_binding_sha256",
        ):
            _sha256(checkpoint[field], f"checkpoint {field}")
        if not isinstance(checkpoint["input_hashes"], list) or not checkpoint["input_hashes"]:
            raise OperationsError("checkpoint input hashes are required")
        for digest in checkpoint["input_hashes"]:
            _sha256(digest, "checkpoint input")
        protocol_digest = resume_binding(
            record["job_id"],
            f"{record['capability']['id']}@{record['capability']['version']}",
            checkpoint["worker_commit_sha"],
            checkpoint["input_hashes"],
        )
        if checkpoint["protocol_binding_sha256"] != protocol_digest:
            raise OperationsError("checkpoint protocol binding differs")
        execution_digest = content_sha256({
            "capability": record["capability"],
            "capability_report_sha256": checkpoint["capability_report_sha256"],
            "config_sha256": checkpoint["config_sha256"],
            "job_id": record["job_id"],
            "operation_id": record["operation_id"],
            "resume_scope": record["resume_scope"],
        })
        if checkpoint["execution_identity_sha256"] != execution_digest:
            raise OperationsError("checkpoint execution identity differs")
        expected = content_sha256({
            "checkpoint_id": checkpoint["checkpoint_id"],
            "input_hashes": checkpoint["input_hashes"],
            "worker_commit_sha": checkpoint["worker_commit_sha"],
            "capability_report_sha256": checkpoint["capability_report_sha256"],
            "config_sha256": checkpoint["config_sha256"],
            "execution_identity_sha256": execution_digest,
            "protocol_binding_sha256": protocol_digest,
        })
        if checkpoint["binding_sha256"] != expected:
            raise OperationsError("checkpoint binding differs")
    preflight = record["preflight"]
    if preflight is not None:
        if not isinstance(preflight, dict) or set(preflight) != {
            "report_sha256", "measured_at"
        }:
            raise OperationsError("job preflight fields differ from v1")
        _sha256(preflight["report_sha256"], "job preflight report")
        _instant(preflight["measured_at"])
    reservation_id = record["reservation_id"]
    if reservation_id is not None:
        _urn(reservation_id, "reservation", "job reservation identity")
    execution_states = {
        "WAITING_RESOURCES", "RUNNING", "PAUSE_REQUESTED", "PAUSED",
        "RESUMING", "RECOVERY_REQUIRED",
    }
    if record["state"] in execution_states and preflight is None:
        raise OperationsError("job execution state lacks measured preflight")
    if record["state"] in {
        "RUNNING", "PAUSE_REQUESTED", "PAUSED", "RESUMING",
        "RECOVERY_REQUIRED",
    } and reservation_id is None:
        raise OperationsError("job execution state lacks resource reservation")
    events = record["events"]
    if not isinstance(events, list) or not events:
        raise OperationsError("job event history is required")
    previous_at: datetime | None = None
    for index, event in enumerate(events):
        if (
            not isinstance(event, dict)
            or set(event) != {"sequence", "at", "from_state", "to_state", "evidence_sha256"}
            or event["sequence"] != index
            or (index and event["from_state"] != events[index - 1]["to_state"])
            or event["to_state"] not in JOB_STATES
        ):
            raise OperationsError("job event history is invalid")
        event_at = _instant(event["at"])
        if previous_at is not None and event_at < previous_at:
            raise OperationsError("job event timestamps move backwards")
        previous_at = event_at
        if event["from_state"] is not None and event["from_state"] not in JOB_STATES:
            raise OperationsError("job event state is invalid")
        if index == 0:
            if event["from_state"] is not None or event["to_state"] != "QUEUED":
                raise OperationsError("job event history must begin at QUEUED")
        elif event["to_state"] not in TRANSITIONS.get(event["from_state"], set()):
            raise OperationsError("job event contains an illegal transition")
        if event["evidence_sha256"] is not None:
            _sha256(event["evidence_sha256"], "job event evidence")
    if events[-1]["to_state"] != record["state"]:
        raise OperationsError("job state differs from event history")
    terminal = record["terminal"]
    if record["state"] in TERMINAL_STATES:
        if (
            not isinstance(terminal, dict)
            or set(terminal) != {"finished_at", "outcome", "error_code"}
            or terminal["outcome"] != record["state"]
        ):
            raise OperationsError("terminal outcome is missing or contradictory")
        _instant(terminal["finished_at"])
        if record["state"] in {"SUCCEEDED", "CANCELLED"}:
            if terminal["error_code"] is not None:
                raise OperationsError("successful or cancelled outcome cannot contain an error")
        elif not isinstance(terminal["error_code"], str) or not terminal["error_code"]:
            raise OperationsError("failed or unknown outcome requires an error code")
    elif terminal is not None:
        raise OperationsError("non-terminal job cannot have terminal outcome")
    created, updated = _instant(record["created_at"]), _instant(record["updated_at"])
    if updated < created:
        raise OperationsError("job timestamps move backwards")
    if record["state"] == "CANCELLED" and cancellation["acknowledged_at"] is None:
        raise OperationsError("cancelled job lacks cancellation acknowledgement")
    if cancellation["acknowledged_at"] is not None:
        if cancellation["requested_at"] is None or _instant(cancellation["acknowledged_at"]) < _instant(cancellation["requested_at"]):
            raise OperationsError("cancellation acknowledgement precedes its request")
    if record["state"] == "CANCEL_REQUESTED" and cancellation["requested_at"] is None:
        raise OperationsError("cancel-requested job lacks request evidence")
    event_instants = [_instant(event["at"]) for event in events]
    if event_instants[0] < created or event_instants[-1] > updated:
        raise OperationsError("job event timestamp is outside the record lifetime")
    if checkpoint is not None:
        checkpoint_at = _instant(checkpoint["created_at"])
        if checkpoint_at < created or checkpoint_at > updated:
            raise OperationsError("checkpoint timestamp is outside the record lifetime")
    if preflight is not None:
        preflight_at = _instant(preflight["measured_at"])
        if preflight_at < created or preflight_at > updated:
            raise OperationsError("preflight timestamp is outside the record lifetime")
    if terminal is not None:
        finished_at = _instant(terminal["finished_at"])
        if finished_at < created or finished_at > updated:
            raise OperationsError("terminal timestamp is outside the record lifetime")


class JobStore:
    """Atomic versioned job state with optimistic revision checks."""

    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, job_id: str) -> Path:
        _urn(job_id, "job", "job ID")
        return self.root / f"{hashlib.sha256(job_id.encode()).hexdigest()}.json"

    def create(
        self,
        *,
        job_id: str,
        operation_id: str,
        job_class: str,
        capability_id: str,
        capability_version: str,
        resume_scope: str,
        now: str,
    ) -> dict[str, Any]:
        path = self._path(job_id)
        record = {
            "schema_version": "1.0",
            "job_id": job_id,
            "operation_id": operation_id,
            "revision": 1,
            "job_class": job_class,
            "capability": {"id": capability_id, "version": capability_version},
            "resume_scope": resume_scope,
            "state": "QUEUED",
            "progress": {
                "sequence": 0,
                "fraction": 0.0,
                "stage": "queued",
                "eta_status": "UNKNOWN",
                "eta_seconds": None,
            },
            "cancellation": {"requested_at": None, "acknowledged_at": None},
            "checkpoint": None,
            "preflight": None,
            "reservation_id": None,
            "events": [{
                "sequence": 0,
                "at": now,
                "from_state": None,
                "to_state": "QUEUED",
                "evidence_sha256": None,
            }],
            "terminal": None,
            "created_at": now,
            "updated_at": now,
        }
        validate_job(record)
        with path.with_suffix(".guard").open("a+b") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            if path.exists():
                raise OperationsError("job already exists")
            _atomic_json(path, record)
        return record

    def read(self, job_id: str) -> dict[str, Any]:
        path = self._path(job_id)
        with path.with_suffix(".guard").open("a+b") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_SH)
            if not path.is_file():
                raise OperationsError("job does not exist")
            record = json.loads(path.read_text(encoding="utf-8"))
            validate_job(record)
            return record

    def mutate(
        self,
        job_id: str,
        expected_revision: int,
        now: str,
        mutation: Callable[[dict[str, Any]], None],
    ) -> dict[str, Any]:
        path = self._path(job_id)
        guard = path.with_suffix(".guard")
        with guard.open("a+b") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            if not path.is_file():
                raise OperationsError("job does not exist")
            record = json.loads(path.read_text(encoding="utf-8"))
            validate_job(record)
            if record["revision"] != expected_revision:
                raise OperationsError("job revision conflict")
            if record["state"] in TERMINAL_STATES:
                raise OperationsError("terminal job is immutable")
            if _instant(now) < _instant(record["updated_at"]):
                raise OperationsError("job mutation timestamp moves backwards")
            candidate = copy.deepcopy(record)
            mutation(candidate)
            candidate["revision"] += 1
            candidate["updated_at"] = now
            validate_job(candidate)
            _atomic_json(path, candidate)
            return candidate

    def transition(
        self,
        job_id: str,
        expected_revision: int,
        *,
        to_state: str,
        now: str,
        evidence_sha256: str | None = None,
    ) -> dict[str, Any]:
        if evidence_sha256 is not None:
            _sha256(evidence_sha256, "transition evidence")
        if to_state in TERMINAL_STATES:
            raise OperationsError("terminal states require the governed finish path")
        if to_state in {"WAITING_RESOURCES", "RUNNING"}:
            raise OperationsError(
                "preflight and running states require their governed paths"
            )
        if to_state == "RECOVERY_REQUIRED" and evidence_sha256 is None:
            raise OperationsError("lifecycle transition requires verified evidence")

        def apply(record: dict[str, Any]) -> None:
            previous = record["state"]
            if to_state not in TRANSITIONS.get(previous, set()):
                raise OperationsError(f"illegal job transition: {previous} -> {to_state}")
            record["state"] = to_state
            record["events"].append({
                "sequence": len(record["events"]),
                "at": now,
                "from_state": previous,
                "to_state": to_state,
                "evidence_sha256": evidence_sha256,
            })

        return self.mutate(job_id, expected_revision, now, apply)

    def complete_preflight(
        self,
        job_id: str,
        expected_revision: int,
        *,
        probe: dict[str, Any],
        expected: dict[str, Any],
        now: str,
    ) -> dict[str, Any]:
        """Measure exact capability facts and persist the only valid preflight."""

        report = probe_capability(**probe)
        validate_capability_preflight(report, expected)
        report_sha256 = content_sha256(report)

        def apply(record: dict[str, Any]) -> None:
            if record["state"] != "PREFLIGHT":
                raise OperationsError("measured preflight requires PREFLIGHT state")
            if report["capability"] != record["capability"]:
                raise OperationsError("measured capability differs from job")
            if (
                record["checkpoint"] is not None
                and record["checkpoint"]["capability_report_sha256"]
                != report_sha256
            ):
                raise OperationsError("resumed capability report differs from checkpoint")
            record["preflight"] = {
                "report_sha256": report_sha256,
                "measured_at": now,
            }
            previous = record["state"]
            record["state"] = "WAITING_RESOURCES"
            record["events"].append({
                "sequence": len(record["events"]),
                "at": now,
                "from_state": previous,
                "to_state": "WAITING_RESOURCES",
                "evidence_sha256": report_sha256,
            })

        return self.mutate(job_id, expected_revision, now, apply)

    def start_reserved(
        self,
        job_id: str,
        expected_revision: int,
        *,
        reservation_store: "ResourceReservationStore",
        reservation_id: str,
        now: str,
    ) -> dict[str, Any]:
        reservation = reservation_store.read(reservation_id)

        def apply(record: dict[str, Any]) -> None:
            if record["state"] != "WAITING_RESOURCES":
                raise OperationsError("resource start requires WAITING_RESOURCES")
            if record["preflight"] is None:
                raise OperationsError("resource start lacks measured preflight")
            if (
                reservation["state"] != "ACTIVE"
                or reservation["job_id"] != job_id
                or reservation["operation_id"] != record["operation_id"]
                or reservation["job_class"] != record["job_class"]
                or reservation["capability_report_sha256"]
                != record["preflight"]["report_sha256"]
            ):
                raise OperationsError("active reservation differs from job preflight")
            record["reservation_id"] = reservation_id
            record["state"] = "RUNNING"
            record["events"].append({
                "sequence": len(record["events"]),
                "at": now,
                "from_state": "WAITING_RESOURCES",
                "to_state": "RUNNING",
                "evidence_sha256": content_sha256(reservation),
            })

        return self.mutate(job_id, expected_revision, now, apply)

    def progress(
        self,
        job_id: str,
        expected_revision: int,
        *,
        sequence: int,
        fraction: float,
        stage: str,
        now: str,
        eta_seconds: float | None = None,
    ) -> dict[str, Any]:
        def apply(record: dict[str, Any]) -> None:
            previous = record["progress"]
            if record["state"] != "RUNNING":
                raise OperationsError("progress is not allowed in current state")
            if sequence <= previous["sequence"] or fraction < previous["fraction"]:
                raise OperationsError("progress must be monotonic")
            record["progress"] = {
                "sequence": sequence,
                "fraction": fraction,
                "stage": stage,
                "eta_status": "UNKNOWN" if eta_seconds is None else "ESTIMATED",
                "eta_seconds": eta_seconds,
            }

        return self.mutate(job_id, expected_revision, now, apply)

    def checkpoint(
        self,
        job_id: str,
        expected_revision: int,
        *,
        checkpoint_id: str,
        input_hashes: list[str],
        worker_commit_sha: str,
        capability_report_sha256: str,
        config_sha256: str,
        now: str,
    ) -> dict[str, Any]:
        def apply(record: dict[str, Any]) -> None:
            if record["state"] != "RUNNING":
                raise OperationsError("checkpoint requires a running job")
            if record["resume_scope"] == "NONE":
                raise OperationsError("job does not support checkpoint resume")
            if (
                record["preflight"] is None
                or record["preflight"]["report_sha256"]
                != capability_report_sha256
            ):
                raise OperationsError("checkpoint capability differs from measured preflight")
            facts = {
                "checkpoint_id": checkpoint_id,
                "input_hashes": input_hashes,
                "worker_commit_sha": worker_commit_sha,
                "capability_report_sha256": capability_report_sha256,
                "config_sha256": config_sha256,
            }
            facts["protocol_binding_sha256"] = resume_binding(
                record["job_id"],
                f"{record['capability']['id']}@{record['capability']['version']}",
                worker_commit_sha,
                input_hashes,
            )
            facts["execution_identity_sha256"] = content_sha256({
                "capability": record["capability"],
                "capability_report_sha256": capability_report_sha256,
                "config_sha256": config_sha256,
                "job_id": record["job_id"],
                "operation_id": record["operation_id"],
                "resume_scope": record["resume_scope"],
            })
            record["checkpoint"] = {
                **facts,
                "created_at": now,
                "binding_sha256": content_sha256(facts),
            }
            previous = record["state"]
            record["state"] = "PAUSE_REQUESTED"
            record["events"].append({
                "sequence": len(record["events"]), "at": now,
                "from_state": previous, "to_state": "PAUSE_REQUESTED",
                "evidence_sha256": record["checkpoint"]["binding_sha256"],
            })

        return self.mutate(job_id, expected_revision, now, apply)

    def resume(
        self,
        job_id: str,
        expected_revision: int,
        *,
        input_hashes: list[str],
        worker_commit_sha: str,
        capability_report_sha256: str,
        config_sha256: str,
        now: str,
    ) -> dict[str, Any]:
        def apply(record: dict[str, Any]) -> None:
            checkpoint = record["checkpoint"]
            if record["state"] != "RESUMING" or checkpoint is None:
                raise OperationsError("resume requires a checkpointed job")
            if (
                checkpoint["input_hashes"] != input_hashes
                or checkpoint["worker_commit_sha"] != worker_commit_sha
                or checkpoint["capability_report_sha256"] != capability_report_sha256
                or checkpoint["config_sha256"] != config_sha256
            ):
                raise OperationsError("resume identity differs from checkpoint")
            facts = {
                key: checkpoint[key]
                for key in (
                    "checkpoint_id", "input_hashes", "worker_commit_sha",
                    "capability_report_sha256", "config_sha256",
                    "execution_identity_sha256", "protocol_binding_sha256",
                )
            }
            if content_sha256(facts) != checkpoint["binding_sha256"]:
                raise OperationsError("resume checkpoint binding differs")
            previous = record["state"]
            record["state"] = "PREFLIGHT"
            record["events"].append({
                "sequence": len(record["events"]), "at": now,
                "from_state": previous, "to_state": "PREFLIGHT",
                "evidence_sha256": checkpoint["binding_sha256"],
            })

        return self.mutate(job_id, expected_revision, now, apply)

    def request_cancel(
        self, job_id: str, expected_revision: int, *, now: str
    ) -> dict[str, Any]:
        def apply(record: dict[str, Any]) -> None:
            previous = record["state"]
            if "CANCEL_REQUESTED" not in TRANSITIONS.get(previous, set()):
                raise OperationsError("cancel request is illegal in current state")
            record["state"] = "CANCEL_REQUESTED"
            record["cancellation"]["requested_at"] = now
            record["events"].append({
                "sequence": len(record["events"]), "at": now,
                "from_state": previous, "to_state": "CANCEL_REQUESTED",
                "evidence_sha256": None,
            })

        return self.mutate(job_id, expected_revision, now, apply)

    def acknowledge_cancel(
        self,
        job_id: str,
        expected_revision: int,
        *,
        now: str,
        cancel_ack: dict[str, Any],
        lease_store: LeaseStore | None = None,
        lease_project_id: str | None = None,
        lease_entity_id: str | None = None,
        reservation_store: "ResourceReservationStore" | None = None,
    ) -> dict[str, Any]:
        validate_message(cancel_ack)
        if (
            cancel_ack.get("type") != "CANCEL_ACK"
            or cancel_ack.get("payload") != {"job_id": job_id, "status": "CANCELLED"}
        ):
            raise OperationsError("cancellation acknowledgement differs from the job")
        snapshot = self.read(job_id)
        if snapshot["state"] in TERMINAL_STATES:
            raise OperationsError("terminal job is immutable")
        cleanup_sha256: str | None = None
        reservation_id = _terminal_reservation_id(
            snapshot, reservation_store, require_after_preflight=True
        )
        if reservation_id is not None:
            cleanup_sha256 = _load_durable_cleanup_evidence(
                lease_store=lease_store,
                lease_project_id=lease_project_id,
                lease_entity_id=lease_entity_id,
                reservation_store=reservation_store,
                reservation_id=reservation_id,
                job_id=job_id,
                operation_id=snapshot["operation_id"],
            )
        elif snapshot["events"][-1]["from_state"] not in {"QUEUED", "PREFLIGHT"}:
            raise OperationsError("cancellation cleanup authority is missing")

        def apply(record: dict[str, Any]) -> None:
            if record["state"] != "CANCEL_REQUESTED":
                raise OperationsError("cancel acknowledgement lacks a request")
            record["state"] = "CANCELLED"
            record["cancellation"]["acknowledged_at"] = now
            record["terminal"] = {
                "finished_at": now,
                "outcome": "CANCELLED",
                "error_code": None,
            }
            record["events"].append({
                "sequence": len(record["events"]), "at": now,
                "from_state": "CANCEL_REQUESTED", "to_state": "CANCELLED",
                "evidence_sha256": content_sha256({
                    "cancel_ack": cancel_ack,
                    "cleanup_sha256": cleanup_sha256,
                }),
            })

        return self.mutate(job_id, expected_revision, now, apply)

    def finish(
        self,
        job_id: str,
        expected_revision: int,
        *,
        outcome: str,
        now: str,
        error_code: str | None = None,
        failure_evidence_sha256: str | None = None,
        artifact_root: Path | None = None,
        artifact_expectations: list[dict[str, Any]] | None = None,
        lease_store: LeaseStore | None = None,
        lease_project_id: str | None = None,
        lease_entity_id: str | None = None,
        reservation_store: "ResourceReservationStore" | None = None,
    ) -> dict[str, Any]:
        if outcome not in {"SUCCEEDED", "FAILED", "UNKNOWN_OUTCOME"}:
            raise OperationsError("invalid terminal outcome")

        snapshot = self.read(job_id)
        if snapshot["state"] in TERMINAL_STATES:
            raise OperationsError("terminal job is immutable")
        cleanup_sha256: str | None = None
        reservation_id = _terminal_reservation_id(
            snapshot,
            reservation_store,
            require_after_preflight=(outcome != "UNKNOWN_OUTCOME"),
        )
        if reservation_id is not None and outcome != "UNKNOWN_OUTCOME":
            cleanup_sha256 = _load_durable_cleanup_evidence(
                lease_store=lease_store,
                lease_project_id=lease_project_id,
                lease_entity_id=lease_entity_id,
                reservation_store=reservation_store,
                reservation_id=reservation_id,
                job_id=job_id,
                operation_id=snapshot["operation_id"],
            )
        if outcome == "SUCCEEDED":
            if artifact_root is None or not artifact_expectations:
                raise OperationsError("successful completion requires promoted artifacts")
            if any(
                not isinstance(expected, dict)
                or expected.get("reference", {}).get("provenance", {}).get(
                    "operation_id"
                )
                != snapshot["operation_id"]
                for expected in artifact_expectations
            ):
                raise OperationsError("successful artifact operation differs from job")
            integrity_report = verify_artifacts(
                artifact_root, artifact_expectations
            )
            if cleanup_sha256 is None:
                raise OperationsError("successful completion lacks durable cleanup")
            if integrity_report != {
                "schema_version": "1.0", "status": "PASS", "findings": []
            }:
                raise OperationsError("artifact Integrity has not passed")
            completion_sha256 = content_sha256({
                "integrity_report": integrity_report,
                "cleanup_sha256": cleanup_sha256,
            })
        else:
            completion_sha256 = None
            _sha256(failure_evidence_sha256, "terminal failure evidence")
            if reservation_id is not None and outcome == "FAILED" and cleanup_sha256 is None:
                raise OperationsError("failed execution lacks durable cleanup")

        def apply(record: dict[str, Any]) -> None:
            previous = record["state"]
            if outcome not in TRANSITIONS.get(previous, set()):
                raise OperationsError("job cannot finish from current state")
            record["state"] = outcome
            record["terminal"] = {
                "finished_at": now,
                "outcome": outcome,
                "error_code": error_code,
            }
            if outcome == "SUCCEEDED":
                record["progress"] = {
                    "sequence": record["progress"]["sequence"] + 1,
                    "fraction": 1.0,
                    "stage": "complete",
                    "eta_status": "ESTIMATED",
                    "eta_seconds": 0,
                }
            record["events"].append({
                "sequence": len(record["events"]), "at": now,
                "from_state": previous, "to_state": outcome,
                "evidence_sha256": (
                    completion_sha256
                    if outcome == "SUCCEEDED"
                    else content_sha256({
                        "failure_evidence_sha256": failure_evidence_sha256,
                        "cleanup_sha256": cleanup_sha256,
                    })
                ),
            })

        return self.mutate(job_id, expected_revision, now, apply)


def _terminal_reservation_id(
    snapshot: dict[str, Any],
    reservation_store: "ResourceReservationStore" | None,
    *,
    require_after_preflight: bool,
) -> str | None:
    """Resolve durable resource ownership, including the reserve/start race."""

    linked_reservation_id = snapshot["reservation_id"]
    prior_state = snapshot["events"][-1].get("from_state")
    resource_may_exist = (
        snapshot["state"] not in {"QUEUED", "PREFLIGHT"}
        or prior_state not in {None, "QUEUED", "PREFLIGHT"}
    )
    if reservation_store is None:
        if linked_reservation_id is not None:
            return linked_reservation_id
        if not require_after_preflight or not resource_may_exist:
            return None
        raise OperationsError("resource reservation store is required after preflight")
    reservations = reservation_store.find_by_job(snapshot["job_id"])
    if linked_reservation_id is not None:
        linked = [
            record for record in reservations
            if record["reservation_id"] == linked_reservation_id
        ]
        other_active = [
            record for record in reservations
            if record["reservation_id"] != linked_reservation_id
            and record["state"] == "ACTIVE"
        ]
        if len(linked) != 1 or other_active:
            raise OperationsError("resource reservation ownership is not uniquely proven")
        reservation = linked[0]
    elif len(reservations) == 1:
        reservation = reservations[0]
    elif not require_after_preflight and not resource_may_exist and not reservations:
        return None
    else:
        raise OperationsError("resource reservation ownership is not uniquely proven")
    if reservation["operation_id"] != snapshot["operation_id"]:
        raise OperationsError("resource reservation operation differs from job")
    return reservation["reservation_id"]


def _load_durable_cleanup_evidence(
    *,
    lease_store: LeaseStore | None,
    lease_project_id: str | None,
    lease_entity_id: str | None,
    reservation_store: "ResourceReservationStore" | None,
    reservation_id: str,
    job_id: str,
    operation_id: str,
) -> str:
    if (
        lease_store is None
        or lease_project_id is None
        or lease_entity_id is None
        or reservation_store is None
    ):
        raise OperationsError("durable cleanup stores are required")
    lease = lease_store.read(lease_project_id, lease_entity_id)
    if lease is None:
        raise OperationsError("completion lease does not exist")
    try:
        LeaseStore._validate_shape(lease)
        LeaseStore._validate_temporal_order(lease)
    except Exception as error:
        raise OperationsError("completion lease is invalid") from error
    if (
        lease.get("state") != "RELEASED"
        or lease.get("release_reason") not in {
            "WRITER_RELEASE", "VERIFIED_STALE_RECOVERY"
        }
        or not lease.get("released_at")
    ):
        raise OperationsError("completion lease is not released")
    if _instant(lease["released_at"]) < _instant(lease["acquired_at"]):
        raise OperationsError("completion lease release predates acquisition")
    if lease.get("operation_id") != operation_id:
        raise OperationsError("completion lease operation differs")
    reservation = reservation_store.read(reservation_id)
    if reservation["job_id"] != job_id or reservation["state"] != "RELEASED":
        raise OperationsError("completion reservation is not released for job")
    if reservation["operation_id"] != operation_id:
        raise OperationsError("completion reservation operation differs")
    cleanup = reservation["process_cleanup"]
    if (
        not isinstance(cleanup, dict)
        or set(cleanup) != {
            "status", "pid", "orphaned", "process_group_reaped"
        }
        or cleanup["status"] != "PASS"
        or cleanup["orphaned"] is not False
        or cleanup["process_group_reaped"] is not True
        or cleanup["pid"] != reservation["process_id"]
    ):
        raise OperationsError("owned process cleanup is not proven")
    if observe_process_state(
        reservation["process_id"], reservation["process_start_token"]
    )["state"] != "NOT_RUNNING":
        raise OperationsError("owned process is still running")
    if observe_process_group_state(reservation["process_id"]) != "NOT_RUNNING":
        raise OperationsError("owned process group is still running")
    writer = lease.get("writer", {})
    if (
        writer.get("host_id") != reservation["host_id"]
        or writer.get("process_id") != reservation["process_id"]
        or writer.get("process_start_token") != reservation["process_start_token"]
    ):
        raise OperationsError("lease and reservation owners differ")
    return content_sha256({
        "lease": lease,
        "reservation": reservation,
        "process_cleanup": cleanup,
    })


def validate_capability_preflight(
    report: dict[str, Any], expected: dict[str, Any]
) -> None:
    fields = {
        "schema_version", "status", "capability", "worker", "component",
        "model", "runtime", "source", "target", "contract",
    }
    if not isinstance(report, dict) or set(report) != fields:
        raise OperationsError("capability preflight fields differ from v1")
    if report["schema_version"] != "1.0" or report["status"] != "READY":
        raise OperationsError("capability is not ready")
    if set(expected) != fields - {"schema_version", "status"}:
        raise OperationsError("expected capability identity is incomplete")
    if any(report[field] != expected[field] for field in expected):
        raise OperationsError("capability identity drift detected")
    validate_component_identity(report["component"])
    for field in ("worker", "model", "runtime", "source", "target", "contract"):
        value = report[field]
        if not isinstance(value, dict) or not value:
            raise OperationsError(f"capability {field} identity is incomplete")
    _sha256(report["worker"].get("identity_sha256"), "worker identity")
    _sha256(report["model"].get("identity_sha256"), "model identity")
    _sha256(report["source"].get("content_sha256"), "source identity")
    _sha256(report["contract"].get("schema_sha256"), "contract identity")
    if report["target"].get("state") != "AVAILABLE":
        raise OperationsError("capability target is not available")
    component = report["component"]
    if report["worker"].get("id") != component["component_id"]:
        raise OperationsError("worker identity contradicts component identity")
    runtime = report["runtime"]
    if (
        set(runtime) != {
            "id", "version", "executable_sha256", "probe_arguments_sha256"
        }
        or runtime.get("id") != component["runtime"]["kind"]
        or runtime.get("version") != component["runtime"]["version"]
    ):
        raise OperationsError("runtime identity contradicts component identity")
    _sha256(runtime.get("executable_sha256"), "runtime executable identity")
    _sha256(runtime.get("probe_arguments_sha256"), "runtime probe arguments")
    if {"id": runtime["id"], "version": runtime["version"]} != {
        "id": component["runtime"]["kind"],
        "version": component["runtime"]["version"],
    }:
        raise OperationsError("runtime identity contradicts component identity")
    if report["model"] not in component.get("models", []):
        raise OperationsError("model identity is absent from component capability")
    if report["contract"].get("id") not in component["contracts"]:
        raise OperationsError("contract identity is absent from component capability")


def probe_capability(
    *,
    capability: dict[str, str],
    component: dict[str, Any],
    worker_path: Path,
    model_id: str,
    model_path: Path,
    source_id: str,
    source_path: Path,
    target_id: str,
    target_path: Path,
    contract_id: str,
    contract_path: Path,
    runtime_executable_path: Path,
    runtime_version_args: list[str],
) -> dict[str, Any]:
    """Measure capability facts from local files and a pinned component identity."""

    validate_component_identity(component)
    if (
        not isinstance(capability, dict)
        or set(capability) != {"id", "version"}
        or not all(isinstance(value, str) and value for value in capability.values())
    ):
        raise OperationsError("capability identity is invalid")
    worker_digest = _sha256_regular_file(Path(worker_path), "worker")
    model_digest = _sha256_regular_file(Path(model_path), "model")
    source_digest = _sha256_regular_file(Path(source_path), "source")
    contract_digest = _sha256_regular_file(Path(contract_path), "contract")
    model = {"id": model_id, "identity_sha256": model_digest}
    if model not in component.get("models", []):
        raise OperationsError("measured model differs from component capability")
    if contract_id not in component["contracts"]:
        raise OperationsError("measured contract differs from component capability")
    runtime_executable = Path(runtime_executable_path)
    runtime_executable_sha256 = _sha256_regular_file(
        runtime_executable, "runtime executable"
    )
    if (
        not isinstance(runtime_version_args, list)
        or not runtime_version_args
        or not all(isinstance(item, str) and item for item in runtime_version_args)
    ):
        raise OperationsError("runtime probe arguments are invalid")
    expected_runtime = {
        "id": component["runtime"]["kind"],
        "version": component["runtime"]["version"],
        "executable_sha256": runtime_executable_sha256,
        "probe_arguments_sha256": content_sha256(runtime_version_args),
    }
    try:
        runtime_probe = subprocess.run(
            [str(runtime_executable), *runtime_version_args],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise OperationsError("runtime identity cannot be measured") from error
    if (
        runtime_probe.returncode != 0
        or runtime_probe.stdout.strip() != expected_runtime["version"]
    ):
        raise OperationsError("measured runtime differs from component capability")
    target = Path(target_path)
    target_available = (
        target.is_dir()
        and not target.is_symlink()
        and os.access(target, os.W_OK | os.X_OK)
    )
    report = {
        "schema_version": "1.0",
        "status": "READY" if target_available else "BLOCKED",
        "capability": dict(capability),
        "worker": {
            "id": component["component_id"],
            "identity_sha256": worker_digest,
        },
        "component": copy.deepcopy(component),
        "model": model,
        "runtime": expected_runtime,
        "source": {"id": source_id, "content_sha256": source_digest},
        "target": {
            "id": target_id,
            "state": "AVAILABLE" if target_available else "UNAVAILABLE",
        },
        "contract": {"id": contract_id, "schema_sha256": contract_digest},
    }
    return report


def _sha256_regular_file(path: Path, label: str) -> str:
    try:
        metadata = path.lstat()
    except OSError as error:
        raise OperationsError(f"{label} file is unavailable") from error
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        raise OperationsError(f"{label} file is not a regular file")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    if path.lstat() != metadata:
        raise OperationsError(f"{label} file changed during hashing")
    return digest.hexdigest()


@dataclass(frozen=True)
class ResourceDecision:
    status: str
    reasons: tuple[str, ...]


class ResourceScheduler:
    """Reference-Mac admission policy with calculated disk truth."""

    INCOMPATIBLE_MODELS = {frozenset(("WHISPER", "OLLAMA"))}

    @staticmethod
    def admit(
        request: dict[str, Any], snapshot: dict[str, Any], active: list[dict[str, Any]]
    ) -> ResourceDecision:
        request_fields = {
            "operation_id", "job_class", "workload", "model_family", "collection_id",
            "collection_kind", "requires_publication_target",
            "capability_report_sha256",
        }
        snapshot_fields = {
            "memory_pressure", "swap_used_bytes", "free_disk_bytes",
            "required_disk_bytes", "disk_estimate", "workspace_available", "device_available",
            "swap_state", "loaded_models", "loaded_models_state",
            "child_processes", "child_processes_state", "lease_state",
            "publication_target_state",
        }
        if set(request) != request_fields or set(snapshot) != snapshot_fields:
            raise OperationsError("resource request or snapshot fields differ from v1")
        _urn(request["operation_id"], "operation", "resource request operation")
        if (
            request["job_class"] not in JOB_CLASSES
            or request["workload"] not in WORKLOADS
            or (
                request["model_family"] is not None
                and request["model_family"] not in MODEL_FAMILIES
            )
            or request["collection_kind"] not in {"SINGLE", "PLAYLIST"}
            or (
                request["collection_id"] is not None
                and (
                    not isinstance(request["collection_id"], str)
                    or not request["collection_id"]
                )
            )
            or (
                request["collection_kind"] == "PLAYLIST"
                and request["collection_id"] is None
            )
            or (
                request["collection_kind"] == "SINGLE"
                and request["collection_id"] is not None
            )
            or not isinstance(request["requires_publication_target"], bool)
        ):
            raise OperationsError("resource request is invalid")
        _sha256(
            request["capability_report_sha256"],
            "resource request capability report",
        )
        if not isinstance(active, list):
            raise OperationsError("active reservation inventory must be a list")
        reasons: list[str] = []
        active_valid = all(
            isinstance(item, dict)
            and item.get("job_class") in JOB_CLASSES
            and item.get("workload") in WORKLOADS
            and (
                item.get("model_family") is None
                or item.get("model_family") in MODEL_FAMILIES
            )
            and (
                item.get("collection_id") is None
                or isinstance(item.get("collection_id"), str)
            )
            and item.get("collection_kind") in {"SINGLE", "PLAYLIST"}
            and (
                (item.get("collection_kind") == "PLAYLIST")
                == (item.get("collection_id") is not None)
            )
            for item in active
        )
        if not active_valid:
            reasons.append("ACTIVE_RESERVATION_STATE_UNVERIFIED")
        if snapshot["memory_pressure"] not in {"NORMAL", "WARN"}:
            reasons.append("UNSAFE_MEMORY_PRESSURE")
        if snapshot["swap_state"] != "SAFE":
            reasons.append("UNSAFE_OR_UNKNOWN_SWAP")
        metrics_valid = True
        for field in ("swap_used_bytes", "free_disk_bytes", "required_disk_bytes"):
            if isinstance(snapshot[field], bool) or not isinstance(snapshot[field], int) or snapshot[field] < 0:
                reasons.append("UNVERIFIED_RESOURCE_METRIC")
                metrics_valid = False
        try:
            if calculate_required_disk(snapshot["disk_estimate"]) != snapshot["required_disk_bytes"]:
                reasons.append("DISK_ESTIMATE_MISMATCH")
        except OperationsError:
            reasons.append("UNVERIFIED_DISK_ESTIMATE")
        if metrics_valid and snapshot["free_disk_bytes"] < snapshot["required_disk_bytes"]:
            reasons.append("INSUFFICIENT_CALCULATED_DISK")
        if snapshot["workspace_available"] is not True or snapshot["device_available"] is not True:
            reasons.append("WORKSPACE_OR_DEVICE_UNAVAILABLE")
        if snapshot["lease_state"] not in {"CLEAR", "OWNED_BY_JOB"}:
            reasons.append("LEASE_UNSAFE")
        if request["requires_publication_target"] and snapshot["publication_target_state"] != "AVAILABLE":
            reasons.append("PUBLICATION_TARGET_UNAVAILABLE")
        process_truth_invalid = (
            snapshot["loaded_models_state"] != "KNOWN"
            or snapshot["child_processes_state"] != "KNOWN"
            or not isinstance(snapshot["loaded_models"], list)
            or not isinstance(snapshot["child_processes"], list)
            or (
                isinstance(snapshot["loaded_models"], list)
                and not all(isinstance(item, str) and item for item in snapshot["loaded_models"])
            )
            or (
                isinstance(snapshot["child_processes"], list)
                and not all(
                    isinstance(item, int) and not isinstance(item, bool) and item > 0
                    for item in snapshot["child_processes"]
                )
            )
        )
        if process_truth_invalid:
            reasons.append("PROCESS_OR_MODEL_STATE_UNVERIFIED")
        safe_active = [item for item in active if isinstance(item, dict)]
        if request["job_class"] == "heavy-model" and any(
            item.get("job_class") == "heavy-model" for item in safe_active
        ):
            reasons.append("HEAVY_MODEL_ALREADY_ACTIVE")
        if request["job_class"] == "heavy-media" and any(
            item.get("job_class") == "heavy-media" for item in safe_active
        ):
            reasons.append("HEAVY_MEDIA_ALREADY_ACTIVE")
        loaded_models = (
            snapshot["loaded_models"]
            if isinstance(snapshot["loaded_models"], list)
            and all(isinstance(item, str) and item for item in snapshot["loaded_models"])
            else []
        )
        active_models = {
            item.get("model_family") for item in safe_active if item.get("model_family")
        } | set(loaded_models)
        if request["model_family"] and any(
            frozenset((request["model_family"], other)) in ResourceScheduler.INCOMPATIBLE_MODELS
            for other in active_models
        ):
            reasons.append("WHISPER_OLLAMA_CONCURRENCY_DENIED")
        active_workloads = {
            item.get("workload") for item in safe_active if item.get("workload")
        }
        if request["workload"] == "FFMPEG_HEAVY" and "WHISPER" in active_models:
            reasons.append("FFMPEG_WHISPER_CONCURRENCY_DENIED")
        if request["model_family"] == "WHISPER" and "FFMPEG_HEAVY" in active_workloads:
            reasons.append("FFMPEG_WHISPER_CONCURRENCY_DENIED")
        if request["collection_kind"] == "PLAYLIST" and any(
            item.get("collection_id") == request["collection_id"] for item in safe_active
        ):
            reasons.append("PLAYLIST_ITEM_ALREADY_ACTIVE")
        return ResourceDecision("DENY" if reasons else "ALLOW", tuple(sorted(set(reasons))))


def observe_process_start_token(process_id: int) -> str:
    try:
        result = subprocess.run(
            ["/bin/ps", "-o", "lstart=", "-p", str(process_id)],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise OperationsError("process identity cannot be observed") from error
    token = " ".join(result.stdout.split())
    if result.returncode != 0 or not token:
        raise OperationsError("process is not running")
    return token


def observe_process_state(process_id: int, expected_start_token: str) -> dict[str, str]:
    try:
        actual = observe_process_start_token(process_id)
    except OperationsError as error:
        if str(error) == "process is not running":
            return {
                "state": "NOT_RUNNING",
                "process_start_token": expected_start_token,
            }
        return {"state": "UNKNOWN", "process_start_token": expected_start_token}
    return {
        "state": "RUNNING" if actual == expected_start_token else "PID_REUSED",
        "process_start_token": actual,
    }


def observe_process_group_state(process_group_id: int) -> str:
    try:
        os.killpg(process_group_id, 0)
    except ProcessLookupError:
        return "NOT_RUNNING"
    except (OSError, PermissionError):
        return "UNKNOWN"
    return "RUNNING"


class ResourceReservationStore:
    """Atomic host-level reservations; deliberately separate from Project Lease."""

    def __init__(
        self,
        root: Path,
        host_id: str,
        *,
        snapshot_provider: Callable[..., dict[str, Any]] | None = None,
    ):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        if not host_id:
            raise OperationsError("host identity is required")
        self.host_id = host_id
        self.guard = self.root / ".resource-reservations.guard"
        self.snapshot_provider = snapshot_provider or capture_resource_snapshot

    def _records_unlocked(self) -> list[dict[str, Any]]:
        records = []
        for path in sorted(self.root.glob("*.json")):
            record = json.loads(path.read_text(encoding="utf-8"))
            validate_resource_reservation(record)
            if record["host_id"] != self.host_id:
                raise OperationsError("resource reservation identity is invalid")
            records.append(record)
        return records

    def read(self, reservation_id: str) -> dict[str, Any]:
        _urn(reservation_id, "reservation", "resource reservation ID")
        path = self.root / f"{hashlib.sha256(reservation_id.encode()).hexdigest()}.json"
        with self.guard.open("a+b") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_SH)
            if not path.is_file():
                raise OperationsError("resource reservation does not exist")
            record = json.loads(path.read_text(encoding="utf-8"))
            validate_resource_reservation(record)
            if record["host_id"] != self.host_id:
                raise OperationsError("resource reservation host differs")
            return record

    def find_by_job(self, job_id: str) -> list[dict[str, Any]]:
        _urn(job_id, "job", "resource reservation job ID")
        with self.guard.open("a+b") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_SH)
            return [
                record for record in self._records_unlocked()
                if record["job_id"] == job_id
            ]

    def admit_and_reserve(
        self,
        *,
        reservation_id: str,
        job_id: str,
        process_id: int,
        job_store: JobStore,
        request: dict[str, Any],
        workspace: Path,
        disk_estimate: dict[str, int],
        device_paths: list[Path],
        lease_store: LeaseStore,
        lease_identity: tuple[str, str],
        publication_target: Path | None,
        acquired_at: str,
    ) -> dict[str, Any]:
        _instant(acquired_at)
        process_start_token = observe_process_start_token(process_id)
        try:
            process_group_id = os.getpgid(process_id)
        except OSError as error:
            raise OperationsError("reservation process group cannot be observed") from error
        _urn(reservation_id, "reservation", "resource reservation ID")
        _urn(job_id, "job", "resource reservation job ID")
        _urn(request.get("operation_id"), "operation", "resource request operation")
        if (
            isinstance(process_id, bool)
            or not isinstance(process_id, int)
            or process_id < 1
            or not process_start_token
            or process_group_id != process_id
        ):
            raise OperationsError("reservation requires an isolated process group")
        job = job_store.read(job_id)
        if (
            job["state"] != "WAITING_RESOURCES"
            or job["operation_id"] != request["operation_id"]
            or job["job_class"] != request["job_class"]
            or job["preflight"] is None
            or job["preflight"]["report_sha256"]
            != request["capability_report_sha256"]
        ):
            raise OperationsError("resource request differs from waiting job")
        lease = lease_store.read(*lease_identity)
        writer = lease.get("writer", {}) if isinstance(lease, dict) else {}
        if (
            not isinstance(lease, dict)
            or lease.get("state") != "ACTIVE"
            or _instant(acquired_at) >= _instant(lease.get("expires_at", ""))
            or lease.get("operation_id") != request["operation_id"]
            or writer.get("host_id") != self.host_id
            or writer.get("process_id") != process_id
            or writer.get("process_start_token") != process_start_token
        ):
            raise OperationsError("active Project Lease differs from resource request")
        snapshot = self.snapshot_provider(
            workspace=workspace,
            disk_estimate=disk_estimate,
            owner_pid=process_id,
            device_paths=device_paths,
            lease_store=lease_store,
            lease_identity=lease_identity,
            operation_id=request["operation_id"],
            observed_at=acquired_at,
            publication_target=publication_target,
        )
        with self.guard.open("a+b") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            records = self._records_unlocked()
            if any(item["reservation_id"] == reservation_id for item in records):
                raise OperationsError("resource reservation already exists")
            active = [item for item in records if item["state"] == "ACTIVE"]
            if any(
                item["job_id"] == job_id
                or item["operation_id"] == request["operation_id"]
                for item in active
            ):
                raise OperationsError("job or operation already has an active reservation")
            decision = ResourceScheduler.admit(request, snapshot, active)
            if decision.status != "ALLOW":
                raise OperationsError(
                    "resource admission denied: " + ",".join(decision.reasons)
                )
            record = {
                "schema_version": "1.0",
                "reservation_id": reservation_id,
                "job_id": job_id,
                "operation_id": request["operation_id"],
                "host_id": self.host_id,
                "process_id": process_id,
                "process_start_token": process_start_token,
                "job_class": request["job_class"],
                "workload": request["workload"],
                "model_family": request["model_family"],
                "collection_id": request["collection_id"],
                "collection_kind": request["collection_kind"],
                "capability_report_sha256": request["capability_report_sha256"],
                "state": "ACTIVE",
                "acquired_at": acquired_at,
                "released_at": None,
                "release_reason": None,
                "recovery": None,
                "process_cleanup": None,
                "snapshot_sha256": content_sha256(snapshot),
            }
            validate_resource_reservation(record)
            _atomic_json(
                self.root / f"{hashlib.sha256(reservation_id.encode()).hexdigest()}.json",
                record,
            )
            return record

    def release(
        self,
        reservation_id: str,
        *,
        job_id: str,
        process_id: int,
        process_start_token: str,
        released_at: str,
    ) -> dict[str, Any]:
        _instant(released_at)
        _urn(reservation_id, "reservation", "resource reservation ID")
        _urn(job_id, "job", "resource reservation job ID")
        path = self.root / f"{hashlib.sha256(reservation_id.encode()).hexdigest()}.json"
        with self.guard.open("a+b") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            if not path.is_file():
                raise OperationsError("resource reservation does not exist")
            record = json.loads(path.read_text(encoding="utf-8"))
            validate_resource_reservation(record)
            owner = (record["job_id"], record["process_id"], record["process_start_token"])
            if record["state"] != "ACTIVE" or owner != (job_id, process_id, process_start_token):
                raise OperationsError("resource reservation owner differs")
            process_state = observe_process_state(process_id, process_start_token)
            group_state = observe_process_group_state(process_id)
            if process_state["state"] != "NOT_RUNNING" or group_state != "NOT_RUNNING":
                raise OperationsError("resource release requires verified process cleanup")
            record["state"] = "RELEASED"
            record["released_at"] = released_at
            record["release_reason"] = "OWNER_RELEASE"
            record["process_cleanup"] = {
                "status": "PASS",
                "pid": process_id,
                "orphaned": False,
                "process_group_reaped": True,
            }
            validate_resource_reservation(record)
            _atomic_json(path, record)
            return record

    def recover(
        self,
        reservation_id: str,
        *,
        job_store: JobStore,
        recovered_at: str,
    ) -> dict[str, Any]:
        _instant(recovered_at)
        _urn(reservation_id, "reservation", "resource reservation ID")
        path = self.root / f"{hashlib.sha256(reservation_id.encode()).hexdigest()}.json"
        with self.guard.open("a+b") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            if not path.is_file():
                raise OperationsError("resource reservation does not exist")
            record = json.loads(path.read_text(encoding="utf-8"))
            validate_resource_reservation(record)
            if record["state"] != "ACTIVE":
                raise OperationsError("resource reservation is not active")
            observation = observe_process_state(
                record["process_id"], record["process_start_token"]
            )
            if observation != {
                "state": "NOT_RUNNING",
                "process_start_token": record["process_start_token"],
            }:
                raise OperationsError("resource reservation recovery is not proven safe")
            if observe_process_group_state(record["process_id"]) != "NOT_RUNNING":
                raise OperationsError("resource reservation process group is still running")
            job = job_store.read(record["job_id"])
            if job["state"] not in TERMINAL_STATES | {"RECOVERY_REQUIRED"}:
                raise OperationsError("resource reservation job is not recoverable")
            record["state"] = "RELEASED"
            record["released_at"] = recovered_at
            record["release_reason"] = "VERIFIED_RECOVERY"
            record["recovery"] = {
                "process_state": observation["state"],
                "job_state": job["state"],
            }
            record["process_cleanup"] = {
                "status": "PASS",
                "pid": record["process_id"],
                "orphaned": False,
                "process_group_reaped": True,
            }
            validate_resource_reservation(record)
            _atomic_json(path, record)
            return record


def validate_resource_reservation(record: dict[str, Any]) -> None:
    required = {
        "schema_version", "reservation_id", "job_id", "operation_id", "host_id", "process_id",
        "process_start_token", "job_class", "workload", "model_family",
        "collection_id", "collection_kind", "capability_report_sha256", "state",
        "acquired_at", "released_at", "release_reason", "recovery",
        "process_cleanup", "snapshot_sha256",
    }
    if not isinstance(record, dict) or set(record) != required:
        raise OperationsError("resource reservation fields differ from v1")
    if record["schema_version"] != "1.0":
        raise OperationsError("unsupported resource reservation version")
    _urn(record["reservation_id"], "reservation", "resource reservation ID")
    _urn(record["job_id"], "job", "resource reservation job ID")
    _urn(record["operation_id"], "operation", "resource reservation operation ID")
    if not isinstance(record["host_id"], str) or not record["host_id"]:
        raise OperationsError("invalid reservation host ID")
    if isinstance(record["process_id"], bool) or not isinstance(record["process_id"], int) or record["process_id"] < 1:
        raise OperationsError("invalid reservation process ID")
    if not isinstance(record["process_start_token"], str) or not record["process_start_token"]:
        raise OperationsError("invalid reservation process start token")
    if record["job_class"] not in JOB_CLASSES:
        raise OperationsError("invalid reservation job class")
    if record["workload"] not in WORKLOADS:
        raise OperationsError("invalid reservation workload")
    if record["model_family"] is not None and record["model_family"] not in MODEL_FAMILIES:
        raise OperationsError("invalid reservation model family")
    for field in ("model_family", "collection_id"):
        if record[field] is not None and (not isinstance(record[field], str) or not record[field]):
            raise OperationsError(f"invalid reservation {field}")
    if record["collection_kind"] not in {"SINGLE", "PLAYLIST"}:
        raise OperationsError("invalid reservation collection kind")
    if (record["collection_kind"] == "PLAYLIST") != (record["collection_id"] is not None):
        raise OperationsError("reservation collection identity is contradictory")
    _instant(record["acquired_at"])
    _sha256(record["snapshot_sha256"], "reservation snapshot")
    _sha256(record["capability_report_sha256"], "reservation capability report")
    if record["state"] == "ACTIVE":
        if any(record[field] is not None for field in (
            "released_at", "release_reason", "recovery", "process_cleanup"
        )):
            raise OperationsError("active reservation contains release evidence")
    elif record["state"] == "RELEASED":
        if record["release_reason"] not in {"OWNER_RELEASE", "VERIFIED_RECOVERY"}:
            raise OperationsError("released reservation lacks a valid reason")
        if _instant(record["released_at"]) < _instant(record["acquired_at"]):
            raise OperationsError("reservation release precedes acquisition")
        if record["release_reason"] == "OWNER_RELEASE" and record["recovery"] is not None:
            raise OperationsError("owner release cannot contain recovery evidence")
        if record["release_reason"] == "VERIFIED_RECOVERY":
            recovery = record["recovery"]
            if (
                not isinstance(recovery, dict)
                or set(recovery) != {"process_state", "job_state"}
                or recovery["process_state"] != "NOT_RUNNING"
                or recovery["job_state"] not in TERMINAL_STATES | {"RECOVERY_REQUIRED"}
            ):
                raise OperationsError("recovery evidence is incomplete")
        cleanup = record["process_cleanup"]
        if (
            not isinstance(cleanup, dict)
            or set(cleanup) != {
                "status", "pid", "orphaned", "process_group_reaped"
            }
            or cleanup != {
                "status": "PASS",
                "pid": record["process_id"],
                "orphaned": False,
                "process_group_reaped": True,
            }
        ):
            raise OperationsError("released reservation lacks process cleanup proof")
    else:
        raise OperationsError("invalid resource reservation state")


def capture_resource_snapshot(
    *,
    workspace: Path,
    disk_estimate: dict[str, int],
    owner_pid: int,
    device_paths: list[Path],
    lease_store: Any | None = None,
    lease_identity: tuple[str, str] | None = None,
    operation_id: str | None = None,
    observed_at: str | None = None,
    publication_target: Path | None = None,
    command_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, Any]:
    """Capture host facts from the OS and accepted stores; unknown facts stay unsafe."""

    workspace = Path(workspace)
    try:
        free_disk = os.statvfs(workspace).f_bavail * os.statvfs(workspace).f_frsize
        available = workspace.is_dir()
    except OSError:
        free_disk, available = 0, False
    required_disk_bytes = calculate_required_disk(disk_estimate)
    memory_pressure = "UNKNOWN"
    swap_used_bytes = 0
    swap_state = "UNKNOWN"
    loaded_models: list[str] = []
    loaded_models_state = "UNKNOWN"
    child_processes: list[int] = []
    child_processes_state = "UNKNOWN"
    try:
        memory = command_runner(
            ["/usr/bin/memory_pressure", "-Q"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        match = re.search(r"memory free percentage:\s*(\d+)%", memory.stdout)
        if memory.returncode == 0 and match:
            free_percent = int(match.group(1))
            memory_pressure = (
                "NORMAL" if free_percent >= 20 else "WARN" if free_percent >= 10 else "CRITICAL"
            )
        swap = command_runner(
            ["/usr/sbin/sysctl", "-n", "vm.swapusage"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        swap_match = re.search(r"used\s*=\s*([0-9.]+)([KMG])", swap.stdout)
        total_match = re.search(r"system has\s+(\d+)", memory.stdout, re.IGNORECASE)
        if swap.returncode == 0 and swap_match and total_match:
            multipliers = {"K": 1024, "M": 1024 ** 2, "G": 1024 ** 3}
            swap_used_bytes = int(
                float(swap_match.group(1)) * multipliers[swap_match.group(2)]
            )
            total_memory = int(total_match.group(1))
            swap_state = (
                "SAFE"
                if memory_pressure in {"NORMAL", "WARN"}
                and swap_used_bytes <= total_memory
                else "UNSAFE"
            )
        processes = command_runner(
            ["/bin/ps", "-axo", "pid=,ppid=,command="],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if processes.returncode == 0:
            inventory: list[tuple[int, int, str]] = []
            for line in processes.stdout.splitlines():
                parts = line.strip().split(None, 2)
                if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit():
                    inventory.append((int(parts[0]), int(parts[1]), parts[2]))
            commands = [command.lower() for _, _, command in inventory]
            if any("ollama runner" in command for command in commands):
                loaded_models.append("OLLAMA")
            if any("whisper" in command for command in commands):
                loaded_models.append("WHISPER")
            loaded_models = sorted(set(loaded_models))
            loaded_models_state = "KNOWN"
            descendants = {owner_pid}
            changed = True
            while changed:
                changed = False
                for pid, parent, _ in inventory:
                    if parent in descendants and pid not in descendants:
                        descendants.add(pid)
                        changed = True
            child_processes = sorted(descendants - {owner_pid})
            child_processes_state = "KNOWN"
    except (OSError, subprocess.SubprocessError, ValueError):
        pass
    observation_time = (
        _instant(observed_at)
        if observed_at is not None
        else datetime.now(timezone.utc)
    )
    if lease_store is not None and lease_identity is not None and operation_id is not None:
        try:
            _urn(operation_id, "operation", "resource snapshot operation ID")
            lease = lease_store.read(*lease_identity)
            if lease is None or lease.get("state") == "RELEASED":
                lease_state = "CLEAR"
            elif (
                lease.get("state") == "ACTIVE"
                and observation_time < _instant(lease.get("expires_at", ""))
                and lease.get("operation_id") == operation_id
                and lease.get("writer", {}).get("process_id") == owner_pid
                and lease.get("writer", {}).get("process_start_token")
                == observe_process_start_token(owner_pid)
            ):
                lease_state = "OWNED_BY_JOB"
            else:
                lease_state = "CONFLICT"
        except Exception:
            lease_state = "UNKNOWN"
    else:
        lease_state = "UNKNOWN"
    if publication_target is None:
        publication_target_state = "NOT_REQUIRED"
    else:
        target = Path(publication_target)
        publication_target_state = (
            "AVAILABLE"
            if target.is_dir() and not target.is_symlink() and os.access(target, os.W_OK | os.X_OK)
            else "UNAVAILABLE"
        )
    device_available = bool(device_paths) and all(
        Path(path).exists() and not Path(path).is_symlink() for path in device_paths
    )
    return {
        "memory_pressure": memory_pressure,
        "swap_used_bytes": swap_used_bytes,
        "swap_state": swap_state,
        "free_disk_bytes": free_disk,
        "required_disk_bytes": required_disk_bytes,
        "disk_estimate": dict(disk_estimate),
        "workspace_available": available,
        "device_available": device_available,
        "loaded_models": loaded_models,
        "loaded_models_state": loaded_models_state,
        "child_processes": child_processes,
        "child_processes_state": child_processes_state,
        "lease_state": lease_state,
        "publication_target_state": publication_target_state,
    }


def calculate_required_disk(terms: dict[str, int]) -> int:
    expected = {
        "source", "extracted_audio", "cache", "intermediate_media",
        "final_output", "safety_margin",
    }
    if not isinstance(terms, dict) or set(terms) != expected:
        raise OperationsError("disk estimate terms differ from v1")
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in terms.values()):
        raise OperationsError("disk estimate terms must be non-negative integers")
    return sum(terms.values())


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: (
                "[REDACTED]"
                if key.lower() in SENSITIVE_KEYS
                or any(part in key.lower() for part in SENSITIVE_KEY_PARTS)
                else redact(child)
            )
            for key, child in value.items()
        }
    if isinstance(value, list):
        return [redact(child) for child in value]
    if isinstance(value, str):
        value = TOKEN_PATTERN.sub(lambda match: match.group(1) + "[REDACTED]", value)
        value = JWT_PATTERN.sub("[REDACTED]", value)
        value = SECRET_VALUE_PATTERN.sub("[REDACTED]", value)
        if EMAIL_PATTERN.fullmatch(value) or ABSOLUTE_PATH_PATTERN.match(value):
            return "[REDACTED]"
        return value
    return value


def structured_event(
    *,
    job_id: str,
    operation_id: str,
    sequence: int,
    level: str,
    event: str,
    occurred_at: str,
    details: dict[str, Any],
) -> dict[str, Any]:
    _instant(occurred_at)
    if (
        not isinstance(event, str)
        or event not in PUBLIC_LOG_EVENTS
    ):
        raise OperationsError("log event name is invalid")
    if not isinstance(details, dict):
        raise OperationsError("log details must be an object")
    if level not in {"DEBUG", "INFO", "WARN", "ERROR"}:
        raise OperationsError("log level is invalid")
    _urn(job_id, "job", "log job identity")
    _urn(operation_id, "operation", "log operation identity")
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
        raise OperationsError("log sequence is invalid")
    allowlisted = {
        "artifact_id", "capability_id", "classification", "code",
        "component_id", "content_sha256", "reason_code", "size_bytes",
        "state", "status",
    }
    safe_details: dict[str, Any] = {}
    for key, value in details.items():
        if key not in allowlisted:
            continue
        if key == "size_bytes":
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise OperationsError("log size is invalid")
            safe_details[key] = value
        elif key == "content_sha256":
            safe_details[key] = _sha256(value, "log content")
        elif key in {"state", "status"}:
            safe_details[key] = (
                value
                if isinstance(value, str) and value in PUBLIC_LOG_STATES
                else "[REDACTED]"
            )
        elif key in {"code", "reason_code"}:
            safe_details[key] = (
                value
                if isinstance(value, str) and value in PUBLIC_LOG_CODES
                else "[REDACTED]"
            )
        elif key == "classification":
            safe_details[key] = (
                value
                if isinstance(value, str) and value in PUBLIC_LOG_CLASSIFICATIONS
                else "[REDACTED]"
            )
        elif key == "artifact_id":
            safe_details[key] = (
                value
                if isinstance(value, str)
                and re.fullmatch(rf"urn:integra:artifact:{UUID_TEXT}", value)
                else "[REDACTED]"
            )
        elif key in {"capability_id", "component_id"}:
            safe_details[key] = (
                value
                if isinstance(value, str) and PUBLIC_COMPONENT_ID.fullmatch(value)
                else "[REDACTED]"
            )
        else:
            safe_details[key] = "[REDACTED]"
    return {
        "schema_version": "1.0",
        "job_id": job_id,
        "operation_id": operation_id,
        "sequence": sequence,
        "level": level,
        "event": event,
        "occurred_at": occurred_at,
        "details": safe_details,
    }


def verify_artifacts(
    root: Path, expectations: list[dict[str, Any]]
) -> dict[str, Any]:
    root = Path(root).resolve()
    findings: list[dict[str, str]] = []
    seen: set[str] = set()
    for expected in expectations:
        try:
            validate_artifact_reference(expected["reference"])
        except Exception:
            findings.append({"artifact_id": str(expected.get("artifact_id")), "code": "IDENTITY_MISMATCH"})
            continue
        reference = expected["reference"]
        artifact_id = reference["artifact_id"]
        if artifact_id in seen:
            findings.append({"artifact_id": artifact_id, "code": "DUPLICATE_IDENTITY"})
            continue
        seen.add(artifact_id)
        if (
            expected.get("artifact_id") != artifact_id
            or expected.get("status") != "COMPLETE"
            or reference.get("storage_scope") != "INTEGRA_STORE"
        ):
            findings.append({"artifact_id": artifact_id, "code": "IDENTITY_OR_PARTIAL_STATE"})
            continue
        parts = Path(reference["relative_path"]).parts
        if ".staging" in parts or any(part.startswith(".staging-") for part in parts):
            findings.append({"artifact_id": artifact_id, "code": "IDENTITY_OR_PARTIAL_STATE"})
            continue
        try:
            size, digest = _hash_confined_regular_file(root, parts)
        except FileNotFoundError:
            findings.append({"artifact_id": artifact_id, "code": "MISSING_OR_ESCAPED"})
            continue
        except OperationsError:
            findings.append({"artifact_id": artifact_id, "code": "UNSAFE_ARTIFACT_TYPE"})
            continue
        if size != reference["size_bytes"]:
            findings.append({"artifact_id": artifact_id, "code": "PARTIAL_SIZE"})
        elif digest != reference["content_sha256"]:
            findings.append({"artifact_id": artifact_id, "code": "ALTERED_HASH"})
    return {
        "schema_version": "1.0",
        "status": "PASS" if not findings else "FAIL",
        "findings": findings,
    }


def _hash_confined_regular_file(
    root: Path, parts: tuple[str, ...]
) -> tuple[int, str]:
    if not parts:
        raise OperationsError("artifact path is empty")
    descriptors: list[int] = []
    try:
        current = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
        descriptors.append(current)
        for part in parts[:-1]:
            current = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=current,
            )
            descriptors.append(current)
        file_descriptor = os.open(
            parts[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=current
        )
        descriptors.append(file_descriptor)
        metadata = os.fstat(file_descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise OperationsError("artifact is not a single-linked regular file")
        digest = hashlib.sha256()
        size = 0
        while True:
            chunk = os.read(file_descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
        if os.fstat(file_descriptor) != metadata:
            raise OperationsError("artifact metadata changed during verification")
        return size, digest.hexdigest()
    except OSError as error:
        if isinstance(error, FileNotFoundError):
            raise
        raise OperationsError("artifact path is unsafe") from error
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


class ModelResidencyStore:
    """Durable ownership for models loaded by a specific Integra job."""

    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.guard = self.root / ".model-residency.guard"

    def _path(self, model_id: str) -> Path:
        if not isinstance(model_id, str) or not SAFE_LOG_TOKEN.fullmatch(model_id):
            raise OperationsError("model residency identity is invalid")
        return self.root / f"{hashlib.sha256(model_id.encode()).hexdigest()}.json"

    def acquire(
        self,
        *,
        model_id: str,
        job_id: str,
        operation_id: str,
        load: Callable[[str], None],
        unload: Callable[[str], None],
        loaded_models: Callable[[], list[str]],
        acquired_at: str,
    ) -> dict[str, Any]:
        _instant(acquired_at)
        path = self._path(model_id)
        with self.guard.open("a+b") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            if path.exists():
                existing = json.loads(path.read_text(encoding="utf-8"))
                validate_model_residency(existing)
                if existing["state"] in {"LOADING", "ACTIVE", "RECOVERY_REQUIRED"}:
                    raise OperationsError("model already has active residency ownership")
            observed_before = loaded_models()
            if not isinstance(observed_before, list) or not all(
                isinstance(item, str) and item for item in observed_before
            ):
                raise OperationsError("model residency observation is invalid")
            if model_id in observed_before:
                raise OperationsError("pre-existing model cannot be acquired")
            record = {
                "schema_version": "1.0",
                "model_id": model_id,
                "job_id": job_id,
                "operation_id": operation_id,
                "state": "LOADING",
                "acquired_at": acquired_at,
                "released_at": None,
            }
            validate_model_residency(record)
            _atomic_json(path, record)

            def persist_recovery_required() -> None:
                record["state"] = "RECOVERY_REQUIRED"
                record["released_at"] = None
                validate_model_residency(record)
                _atomic_json(path, record)

            def rollback_after_load(cause: Exception) -> None:
                try:
                    unload(model_id)
                except Exception as cleanup_error:
                    persist_recovery_required()
                    raise OperationsError(
                        "model acquisition rollback failed; recovery is required"
                    ) from cleanup_error
                try:
                    remaining = loaded_models()
                except Exception as observation_error:
                    persist_recovery_required()
                    raise OperationsError(
                        "model state is unknown after rollback; recovery is required"
                    ) from observation_error
                if (
                    not isinstance(remaining, list)
                    or not all(isinstance(item, str) and item for item in remaining)
                    or model_id in remaining
                ):
                    persist_recovery_required()
                    raise OperationsError(
                        "model acquisition rollback left residency; recovery is required"
                    ) from cause
                record["state"] = "RELEASED"
                record["released_at"] = acquired_at
                validate_model_residency(record)
                _atomic_json(path, record)

            try:
                load(model_id)
            except Exception as load_error:
                rollback_after_load(load_error)
                raise
            try:
                observed_after = loaded_models()
                if (
                    not isinstance(observed_after, list)
                    or not all(isinstance(item, str) and item for item in observed_after)
                    or model_id not in observed_after
                ):
                    raise OperationsError("model acquisition ownership is not proven")
                record["state"] = "ACTIVE"
                validate_model_residency(record)
                _atomic_json(path, record)
            except Exception as error:
                rollback_after_load(error)
                raise
        return record

    def read(self, model_id: str) -> dict[str, Any]:
        path = self._path(model_id)
        with self.guard.open("a+b") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_SH)
            if not path.is_file():
                raise OperationsError("model residency does not exist")
            record = json.loads(path.read_text(encoding="utf-8"))
            validate_model_residency(record)
            return record

    def unload_owned(
        self,
        *,
        model_id: str,
        job_id: str,
        operation_id: str,
        unload: Callable[[str], None],
        loaded_models: Callable[[], list[str]],
        released_at: str,
    ) -> dict[str, Any]:
        _instant(released_at)
        path = self._path(model_id)
        with self.guard.open("a+b") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            if not path.is_file():
                raise OperationsError("model residency does not exist")
            record = json.loads(path.read_text(encoding="utf-8"))
            validate_model_residency(record)
            if (
                record["state"] not in {"LOADING", "ACTIVE", "RECOVERY_REQUIRED"}
                or record["job_id"] != job_id
                or record["operation_id"] != operation_id
            ):
                raise OperationsError("model residency owner differs")
            try:
                unload(model_id)
                remaining = loaded_models()
            except Exception as error:
                record["state"] = "RECOVERY_REQUIRED"
                record["released_at"] = None
                validate_model_residency(record)
                _atomic_json(path, record)
                raise OperationsError(
                    "model unload or absence observation failed; recovery is required"
                ) from error
            if (
                not isinstance(remaining, list)
                or not all(isinstance(item, str) and item for item in remaining)
                or model_id in remaining
            ):
                record["state"] = "RECOVERY_REQUIRED"
                record["released_at"] = None
                validate_model_residency(record)
                _atomic_json(path, record)
                return {
                    "status": "FAIL",
                    "model_id": model_id,
                    "remaining_models": remaining,
                }
            record["state"] = "RELEASED"
            record["released_at"] = released_at
            validate_model_residency(record)
            _atomic_json(path, record)
            return {
                "status": "PASS",
                "model_id": model_id,
                "remaining_models": remaining,
            }


def validate_model_residency(record: Any) -> None:
    if not isinstance(record, dict) or set(record) != {
        "schema_version", "model_id", "job_id", "operation_id", "state",
        "acquired_at", "released_at",
    }:
        raise OperationsError("model residency fields differ from v1")
    if record["schema_version"] != "1.0":
        raise OperationsError("unsupported model residency version")
    if not isinstance(record["model_id"], str) or not SAFE_LOG_TOKEN.fullmatch(record["model_id"]):
        raise OperationsError("model residency ID is invalid")
    for field, namespace in (("job_id", "job"), ("operation_id", "operation")):
        _urn(record[field], namespace, f"model residency {field}")
    acquired = _instant(record["acquired_at"])
    if record["state"] in {"LOADING", "ACTIVE", "RECOVERY_REQUIRED"}:
        if record["released_at"] is not None:
            raise OperationsError("unreleased model residency contains release evidence")
    elif record["state"] == "RELEASED":
        if _instant(record["released_at"]) < acquired:
            raise OperationsError("model residency release predates acquisition")
    else:
        raise OperationsError("model residency state is invalid")


class ProcessSupervisor:
    """Own child process shutdown and model unloading without orphan claims."""

    @staticmethod
    def shutdown(
        process: subprocess.Popen[bytes],
        *,
        expected_process_group_id: int,
        timeout_seconds: float = 2.0,
    ) -> dict[str, Any]:
        if expected_process_group_id != process.pid:
            raise OperationsError("supervised process-group identity differs")
        if process.poll() is None:
            try:
                if os.getpgid(process.pid) != expected_process_group_id:
                    raise OperationsError(
                        "child process does not own an isolated process group"
                    )
            except ProcessLookupError:
                pass
        try:
            os.killpg(expected_process_group_id, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(expected_process_group_id, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
        deadline = time.monotonic() + timeout_seconds
        process_group_reaped = False
        while time.monotonic() < deadline:
            try:
                os.killpg(expected_process_group_id, 0)
            except ProcessLookupError:
                process_group_reaped = True
                break
            try:
                os.killpg(expected_process_group_id, signal.SIGKILL)
            except ProcessLookupError:
                process_group_reaped = True
                break
            time.sleep(0.01)
        if process_group_reaped:
            process.communicate()
        return {
            "status": (
                "PASS"
                if process.poll() is not None and process_group_reaped
                else "FAIL"
            ),
            "pid": process.pid,
            "orphaned": not process_group_reaped,
            "process_group_reaped": process_group_reaped,
        }

    @staticmethod
    def unload_model(
        model_id: str,
        *,
        job_id: str,
        operation_id: str,
        residency_store: ModelResidencyStore,
        unload: Callable[[str], None],
        loaded_models: Callable[[], list[str]],
        released_at: str,
    ) -> dict[str, Any]:
        return residency_store.unload_owned(
            model_id=model_id,
            job_id=job_id,
            operation_id=operation_id,
            unload=unload,
            loaded_models=loaded_models,
            released_at=released_at,
        )
