"""Integra local JSONL worker protocol v1 reference validation."""

from __future__ import annotations

import enum
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any


SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+$")
URN_PATTERN = re.compile(
    r"^urn:integra:[a-z][a-z0-9_]{1,31}:"
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
PROTOCOL_VERSION = "1.0"
MESSAGE_TYPES = {
    "HANDSHAKE_REQUEST",
    "HANDSHAKE_RESPONSE",
    "JOB_REQUEST",
    "PROGRESS",
    "RESULT",
    "ERROR",
    "CANCEL_REQUEST",
    "CANCEL_ACK",
}


class ProtocolViolation(ValueError):
    """Raised when an envelope or artifact violates the accepted contract."""


class CompatibilityError(ProtocolViolation):
    """Raised when controller and worker have no exact supported version."""


class IdempotencyDecision(str, enum.Enum):
    NEW = "NEW"
    REPLAY = "REPLAY"


def _require_object_fields(
    value: Any,
    required: set[str],
    allowed: set[str],
    label: str,
) -> None:
    if not isinstance(value, dict):
        raise ProtocolViolation(f"{label} must be an object")
    missing = required - set(value)
    if missing:
        raise ProtocolViolation(f"{label} missing: {sorted(missing)}")
    unknown = set(value) - allowed
    if unknown:
        raise ProtocolViolation(f"{label} has unknown fields: {sorted(unknown)}")


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def content_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _require_urn(value: Any, field: str) -> None:
    if not isinstance(value, str) or not URN_PATTERN.fullmatch(value):
        raise ProtocolViolation(f"invalid {field}")


def _require_sha256(value: Any, field: str) -> None:
    if not isinstance(value, str) or not SHA256_PATTERN.fullmatch(value):
        raise ProtocolViolation(f"{field} must be lowercase SHA-256")


def _require_git_sha(value: Any, field: str) -> None:
    if not isinstance(value, str) or not GIT_SHA_PATTERN.fullmatch(value):
        raise ProtocolViolation(f"{field} must be a lowercase 40-character Git SHA")


def _require_timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ProtocolViolation(f"{field} must be a UTC RFC3339 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ProtocolViolation(f"invalid {field}") from error
    if parsed.tzinfo != timezone.utc:
        raise ProtocolViolation(f"{field} must use UTC")
    return parsed


def negotiate_protocol(controller_versions: list[str], worker_versions: list[str]) -> str:
    """Choose the highest exact common semantic version without guessing compatibility."""

    candidates = controller_versions + worker_versions
    if not candidates or any(
        not isinstance(value, str) or not VERSION_PATTERN.fullmatch(value)
        for value in candidates
    ):
        raise CompatibilityError("protocol versions must use numeric major.minor form")
    common = set(controller_versions).intersection(worker_versions)
    if not common:
        raise CompatibilityError("no exact common protocol version")

    def version_key(value: str) -> tuple[int, ...]:
        try:
            return tuple(int(part) for part in value.split("."))
        except ValueError as error:
            raise CompatibilityError(f"invalid protocol version: {value}") from error

    return max(common, key=version_key)


def validate_component_identity(identity: dict[str, Any]) -> None:
    required = {
        "component_id",
        "repository",
        "commit_sha",
        "tree_sha",
        "version",
        "contracts",
        "runtime",
    }
    _require_object_fields(
        identity,
        required,
        required | {"models"},
        "component identity",
    )
    for field in ("component_id", "repository", "version"):
        if not isinstance(identity[field], str) or not identity[field]:
            raise ProtocolViolation(f"component {field} must be non-empty")
    for field in ("commit_sha", "tree_sha"):
        _require_git_sha(identity[field], f"component {field}")
    contracts = identity["contracts"]
    if (
        not isinstance(contracts, list)
        or not contracts
        or not all(isinstance(item, str) and item for item in contracts)
        or len(contracts) != len(set(contracts))
    ):
        raise ProtocolViolation("component contracts must be a non-empty unique list")
    runtime = identity["runtime"]
    _require_object_fields(
        runtime,
        {"kind", "version"},
        {"kind", "version", "architecture"},
        "component runtime",
    )
    if not runtime.get("kind") or not runtime.get("version"):
        raise ProtocolViolation("component runtime identity is incomplete")
    models = identity.get("models", [])
    if not isinstance(models, list):
        raise ProtocolViolation("component models must be a list")
    for model in models:
        _require_object_fields(
            model,
            {"id", "identity_sha256"},
            {"id", "identity_sha256"},
            "model identity",
        )
        if not model.get("id"):
            raise ProtocolViolation("model ID must be non-empty")
        _require_sha256(model.get("identity_sha256"), "model identity")


def validate_artifact_reference(reference: dict[str, Any]) -> None:
    required = {
        "artifact_id",
        "kind",
        "schema_id",
        "schema_version",
        "content_sha256",
        "size_bytes",
        "storage_scope",
        "relative_path",
        "origin",
        "provenance",
    }
    _require_object_fields(
        reference,
        required,
        required | {"semantic_status"},
        "artifact reference",
    )
    _require_urn(reference["artifact_id"], "artifact_id")
    for field in ("kind", "schema_id", "schema_version"):
        if not isinstance(reference[field], str) or not reference[field]:
            raise ProtocolViolation(f"artifact {field} must be non-empty")
    if "semantic_status" in reference and reference["semantic_status"] not in {
        "NOT_APPLICABLE",
        "PROVISIONAL",
        "REVIEW_REQUIRED",
    }:
        raise ProtocolViolation("artifact semantic_status is invalid")
    if not VERSION_PATTERN.fullmatch(reference["schema_version"]):
        raise ProtocolViolation("artifact schema_version must use numeric major.minor form")
    _require_sha256(reference["content_sha256"], "artifact content hash")
    if (
        isinstance(reference["size_bytes"], bool)
        or not isinstance(reference["size_bytes"], int)
        or reference["size_bytes"] < 0
    ):
        raise ProtocolViolation("artifact size must be a non-negative integer")
    if reference["storage_scope"] not in {"INTEGRA_STORE", "SOURCE_READ_ONLY"}:
        raise ProtocolViolation("invalid artifact storage scope")
    path = reference["relative_path"]
    if not isinstance(path, str):
        raise ProtocolViolation("artifact path must be a string")
    parsed = PurePosixPath(path)
    if (
        not path
        or parsed.is_absolute()
        or ".." in parsed.parts
        or str(parsed) != path
    ):
        raise ProtocolViolation("artifact path must be a normalized relative path")
    origin = reference["origin"]
    validate_component_identity(origin)
    provenance = reference["provenance"]
    _require_object_fields(
        provenance,
        {"parent_artifact_ids", "operation_id"},
        {"parent_artifact_ids", "operation_id", "source_locator"},
        "artifact provenance",
    )
    parents = provenance.get("parent_artifact_ids")
    if (
        not isinstance(parents, list)
        or not all(isinstance(parent, str) for parent in parents)
        or len(parents) != len(set(parents))
    ):
        raise ProtocolViolation("provenance parents must be a unique list")
    for parent in parents:
        _require_urn(parent, "provenance parent ID")
    _require_urn(provenance["operation_id"], "provenance operation ID")


def resume_binding(
    job_id: str,
    capability: str,
    worker_commit_sha: str,
    input_hashes: list[str],
) -> str:
    """Bind an opaque resume token to immutable execution facts."""

    _require_urn(job_id, "job_id")
    if not isinstance(capability, str) or not capability:
        raise ProtocolViolation("resume capability is required")
    _require_git_sha(worker_commit_sha, "resume worker commit")
    if not isinstance(input_hashes, list) or not input_hashes:
        raise ProtocolViolation("resume inputs must contain lowercase SHA-256 hashes")
    for item in input_hashes:
        _require_sha256(item, "resume input hash")
    return content_sha256(
        {
            "capability": capability,
            "input_hashes": input_hashes,
            "job_id": job_id,
            "worker_commit_sha": worker_commit_sha,
        }
    )


def validate_resume_token(token: dict[str, Any]) -> None:
    required = {"token", "binding_sha256", "issued_at", "expires_at"}
    _require_object_fields(token, required, required, "resume token")
    if not isinstance(token["token"], str) or not token["token"]:
        raise ProtocolViolation("resume token must be opaque and non-empty")
    _require_sha256(token["binding_sha256"], "resume binding")
    issued_at = _require_timestamp(token["issued_at"], "resume issued_at")
    expires_at = _require_timestamp(token["expires_at"], "resume expires_at")
    if expires_at <= issued_at:
        raise ProtocolViolation("resume token must expire after it is issued")


def validate_resume_binding(
    token: dict[str, Any],
    job_id: str,
    capability: str,
    worker_commit_sha: str,
    input_hashes: list[str],
) -> None:
    validate_resume_token(token)
    expected = resume_binding(job_id, capability, worker_commit_sha, input_hashes)
    if token["binding_sha256"] != expected:
        raise ProtocolViolation("resume token is not bound to current immutable job facts")


def _validate_capabilities(capabilities: Any) -> None:
    if not isinstance(capabilities, list) or not capabilities:
        raise ProtocolViolation("worker must declare capabilities")
    ids: list[str] = []
    for capability in capabilities:
        required = {"id", "version", "input_schema_ids", "output_schema_ids", "supports_resume"}
        _require_object_fields(capability, required, required, "capability declaration")
        if (
            not isinstance(capability["id"], str)
            or not capability["id"]
            or not isinstance(capability["version"], str)
            or not capability["version"]
        ):
            raise ProtocolViolation("capability identity is incomplete")
        if not isinstance(capability["supports_resume"], bool):
            raise ProtocolViolation("supports_resume must be boolean")
        for field in ("input_schema_ids", "output_schema_ids"):
            values = capability[field]
            if (
                not isinstance(values, list)
                or not all(isinstance(item, str) and item for item in values)
                or len(values) != len(set(values))
            ):
                raise ProtocolViolation(f"{field} must be a unique list")
        ids.append(capability["id"])
    if len(ids) != len(set(ids)):
        raise ProtocolViolation("capability IDs must be unique")


def validate_message(message: dict[str, Any]) -> None:
    envelope_fields = {
        "protocol_version", "message_id", "correlation_id", "sent_at", "type", "payload"
    }
    _require_object_fields(message, envelope_fields, envelope_fields, "message")
    if message["protocol_version"] != PROTOCOL_VERSION:
        raise CompatibilityError("unsupported protocol envelope version")
    _require_urn(message["message_id"], "message_id")
    _require_urn(message["correlation_id"], "correlation_id")
    _require_timestamp(message["sent_at"], "sent_at")
    message_type = message["type"]
    if message_type not in MESSAGE_TYPES:
        raise ProtocolViolation("unknown message type")
    payload = message["payload"]
    if not isinstance(payload, dict):
        raise ProtocolViolation("payload must be an object")

    if message_type == "HANDSHAKE_REQUEST":
        fields = {"supported_protocol_versions", "requested_capabilities", "controller"}
        _require_object_fields(payload, fields, fields, "handshake request")
        versions = payload.get("supported_protocol_versions")
        if (
            not isinstance(versions, list)
            or not versions
            or not all(isinstance(value, str) for value in versions)
            or len(versions) != len(set(versions))
        ):
            raise ProtocolViolation("handshake request has no supported versions")
        if any(
            not isinstance(value, str) or not VERSION_PATTERN.fullmatch(value)
            for value in versions
        ):
            raise CompatibilityError("handshake contains an invalid protocol version")
        requested = payload.get("requested_capabilities")
        if (
            not isinstance(requested, list)
            or not all(isinstance(value, str) and value for value in requested)
            or len(requested) != len(set(requested))
        ):
            raise ProtocolViolation("requested capabilities must be a unique list")
        validate_component_identity(payload["controller"])
    elif message_type == "HANDSHAKE_RESPONSE":
        fields = {"selected_protocol_version", "worker", "capabilities", "compatibility"}
        _require_object_fields(payload, fields, fields, "handshake response")
        validate_component_identity(payload["worker"])
        if payload.get("selected_protocol_version") != PROTOCOL_VERSION:
            raise CompatibilityError("worker selected an unsupported protocol")
        _validate_capabilities(payload.get("capabilities"))
        compatibility = payload.get("compatibility")
        _require_object_fields(
            compatibility,
            {"schema_policy", "backward_compatible_protocol_versions"},
            {"schema_policy", "backward_compatible_protocol_versions"},
            "compatibility declaration",
        )
        if compatibility.get("schema_policy") != "EXACT_SCHEMA_VERSION":
            raise CompatibilityError("worker must fail closed on unknown schema versions")
        versions = compatibility.get("backward_compatible_protocol_versions")
        if (
            not isinstance(versions, list)
            or not all(isinstance(value, str) for value in versions)
            or len(versions) != len(set(versions))
        ):
            raise CompatibilityError("invalid backward compatibility declaration")
        if any(
            not isinstance(value, str) or not VERSION_PATTERN.fullmatch(value)
            for value in versions
        ):
            raise CompatibilityError("invalid backward compatible protocol version")
    elif message_type == "JOB_REQUEST":
        required = {"job_id", "operation_id", "idempotency_key", "capability", "timeout_ms", "inputs"}
        _require_object_fields(
            payload,
            required,
            required | {"resume_token", "mutable_entity", "write_lease"},
            "job request",
        )
        _require_urn(payload["job_id"], "job_id")
        _require_urn(payload["operation_id"], "operation_id")
        _require_sha256(payload["idempotency_key"], "idempotency key")
        if not isinstance(payload["capability"], str) or not payload["capability"]:
            raise ProtocolViolation("job capability must be non-empty")
        if (
            isinstance(payload["timeout_ms"], bool)
            or not isinstance(payload["timeout_ms"], int)
            or payload["timeout_ms"] < 1
        ):
            raise ProtocolViolation("job timeout must be positive")
        if not isinstance(payload["inputs"], list):
            raise ProtocolViolation("job inputs must be a list")
        for reference in payload["inputs"]:
            validate_artifact_reference(reference)
        if "resume_token" in payload:
            validate_resume_token(payload["resume_token"])
        if payload.get("mutable_entity") is not None:
            _require_urn(payload["mutable_entity"], "mutable_entity")
            lease = payload.get("write_lease")
            _require_object_fields(
                lease,
                {"lease_id", "generation", "artifact_precondition_sha256"},
                {"lease_id", "generation", "artifact_precondition_sha256"},
                "write lease",
            )
            _require_urn(lease.get("lease_id"), "lease_id")
            if (
                isinstance(lease.get("generation"), bool)
                or not isinstance(lease.get("generation"), int)
                or lease["generation"] < 1
            ):
                raise ProtocolViolation("write lease generation must be positive")
            _require_sha256(
                lease.get("artifact_precondition_sha256"),
                "write lease artifact precondition",
            )
    elif message_type == "PROGRESS":
        _require_object_fields(
            payload,
            {"job_id", "sequence", "fraction", "stage"},
            {"job_id", "sequence", "fraction", "stage", "eta_ms"},
            "progress",
        )
        _require_urn(payload.get("job_id"), "job_id")
        fraction = payload.get("fraction")
        if (
            isinstance(fraction, bool)
            or not isinstance(fraction, (int, float))
            or not 0 <= fraction <= 1
        ):
            raise ProtocolViolation("progress fraction must be between zero and one")
        if (
            isinstance(payload.get("sequence"), bool)
            or not isinstance(payload.get("sequence"), int)
            or payload["sequence"] < 0
        ):
            raise ProtocolViolation("progress sequence must be non-negative")
        if not isinstance(payload.get("stage"), str) or not payload["stage"]:
            raise ProtocolViolation("progress stage must be non-empty")
        if "eta_ms" in payload and (
            isinstance(payload["eta_ms"], bool)
            or not isinstance(payload["eta_ms"], int)
            or payload["eta_ms"] < 0
        ):
            raise ProtocolViolation("progress ETA must be non-negative")
    elif message_type == "RESULT":
        fields = {"job_id", "operation_id", "status", "outputs"}
        _require_object_fields(payload, fields, fields, "result")
        _require_urn(payload.get("job_id"), "job_id")
        _require_urn(payload.get("operation_id"), "operation_id")
        if payload.get("status") != "SUCCEEDED":
            raise ProtocolViolation("result must have SUCCEEDED status")
        outputs = payload.get("outputs")
        if not isinstance(outputs, list):
            raise ProtocolViolation("result outputs must be a list")
        for reference in outputs:
            validate_artifact_reference(reference)
    elif message_type == "ERROR":
        required = {"job_id", "code", "message", "classification", "safe_to_retry"}
        _require_object_fields(
            payload,
            required,
            required | {"retry_after_ms", "details"},
            "error",
        )
        _require_urn(payload.get("job_id"), "job_id")
        if not payload.get("code") or not payload.get("message"):
            raise ProtocolViolation("structured error requires code and message")
        classification = payload.get("classification")
        retryable = payload.get("safe_to_retry")
        if classification not in {
            "RETRYABLE", "NON_RETRYABLE", "INCOMPATIBLE", "CANCELLED", "UNKNOWN_OUTCOME"
        }:
            raise ProtocolViolation("invalid error classification")
        if not isinstance(retryable, bool):
            raise ProtocolViolation("error must declare safe_to_retry")
        if classification in {"NON_RETRYABLE", "INCOMPATIBLE", "CANCELLED", "UNKNOWN_OUTCOME"} and retryable:
            raise ProtocolViolation("unsafe error classification cannot permit retry")
        if retryable and (
            isinstance(payload.get("retry_after_ms"), bool)
            or not isinstance(payload.get("retry_after_ms"), int)
            or payload["retry_after_ms"] < 1
        ):
            raise ProtocolViolation("retryable error requires a positive retry delay")
    elif message_type == "CANCEL_REQUEST":
        _require_object_fields(payload, {"job_id"}, {"job_id", "reason"}, "cancel request")
        _require_urn(payload.get("job_id"), "job_id")
    elif message_type == "CANCEL_ACK":
        _require_object_fields(payload, {"job_id", "status"}, {"job_id", "status"}, "cancel ack")
        _require_urn(payload.get("job_id"), "job_id")
        if payload.get("status") not in {"CANCELLED", "ALREADY_TERMINAL", "NOT_FOUND"}:
            raise ProtocolViolation("invalid cancellation acknowledgement")


class IdempotencyLedger:
    """Fail closed if a key is reused for a different canonical request."""

    def __init__(self) -> None:
        self._fingerprints: dict[str, str] = {}

    def register(self, key: str, request_payload: dict[str, Any]) -> IdempotencyDecision:
        _require_sha256(key, "idempotency key")
        if not isinstance(request_payload, dict):
            raise ProtocolViolation("idempotency request must be an object")
        fingerprint = content_sha256(request_payload)
        existing = self._fingerprints.get(key)
        if existing is None:
            self._fingerprints[key] = fingerprint
            return IdempotencyDecision.NEW
        if existing == fingerprint:
            return IdempotencyDecision.REPLAY
        raise ProtocolViolation("idempotency key was reused for a different request")


class ProgressTracker:
    """Reject reordered, regressing, or post-terminal job events."""

    def __init__(self) -> None:
        self.sequence = -1
        self.fraction = 0.0
        self.terminal = False
        self.job_id: str | None = None
        self.correlation_id: str | None = None

    def apply(self, message: dict[str, Any]) -> None:
        validate_message(message)
        if self.terminal:
            raise ProtocolViolation("event received after terminal message")
        message_type = message["type"]
        if message_type in {"PROGRESS", "RESULT", "ERROR", "CANCEL_REQUEST", "CANCEL_ACK"}:
            job_id = message["payload"]["job_id"]
            if self.job_id is None:
                self.job_id = job_id
                self.correlation_id = message["correlation_id"]
            elif job_id != self.job_id or message["correlation_id"] != self.correlation_id:
                raise ProtocolViolation("event belongs to a different job or correlation")
        if message_type == "PROGRESS":
            payload = message["payload"]
            if payload["sequence"] <= self.sequence:
                raise ProtocolViolation("progress sequence did not increase")
            if payload["fraction"] < self.fraction:
                raise ProtocolViolation("progress fraction regressed")
            self.sequence = payload["sequence"]
            self.fraction = float(payload["fraction"])
        elif message_type in {"RESULT", "ERROR", "CANCEL_ACK"}:
            self.terminal = True
