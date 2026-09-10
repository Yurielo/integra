"""Deterministic single-writer Project Lease storage and recovery policy."""

from __future__ import annotations

import enum
import fcntl
import hashlib
import json
import os
import tempfile
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class LeaseConflict(RuntimeError):
    """Raised when a lease operation would violate single-writer ownership."""


class RecoveryDecision(str, enum.Enum):
    NOT_STALE = "NOT_STALE"
    DENY_UNVERIFIED_PROCESS = "DENY_UNVERIFIED_PROCESS"
    DENY_PROCESS_ALIVE = "DENY_PROCESS_ALIVE"
    DENY_UNVERIFIED_ARTIFACT = "DENY_UNVERIFIED_ARTIFACT"
    DENY_ARTIFACT_CHANGED = "DENY_ARTIFACT_CHANGED"
    ALLOW_RECOVERY = "ALLOW_RECOVERY"


UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


@dataclass(frozen=True)
class RecoveryObservation:
    process_state: str
    artifact_state: str


def _instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("lease timestamps must include a timezone")
    return parsed.astimezone(timezone.utc)


def recovery_decision(
    lease: dict[str, Any], now: str, observation: RecoveryObservation
) -> RecoveryDecision:
    """Allow stale recovery only after both process and artifact facts are proven."""

    if lease.get("state") != "ACTIVE" or _instant(now) < _instant(lease["expires_at"]):
        return RecoveryDecision.NOT_STALE
    if observation.process_state == "ALIVE":
        return RecoveryDecision.DENY_PROCESS_ALIVE
    if observation.process_state != "NOT_RUNNING":
        return RecoveryDecision.DENY_UNVERIFIED_PROCESS
    if observation.artifact_state == "CHANGED":
        return RecoveryDecision.DENY_ARTIFACT_CHANGED
    if observation.artifact_state != "UNCHANGED":
        return RecoveryDecision.DENY_UNVERIFIED_ARTIFACT
    return RecoveryDecision.ALLOW_RECOVERY


class LeaseStore:
    """File-backed lease store confined to an explicit Integra-owned directory."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def entity_key(project_id: str, entity_id: str) -> str:
        project_uuid = project_id.removeprefix("urn:integra:project:")
        if project_uuid == project_id or not UUID_PATTERN.fullmatch(project_uuid):
            raise ValueError("project_id must use the Integra project namespace")
        entity_parts = entity_id.split(":")
        if (
            len(entity_parts) != 4
            or entity_parts[:2] != ["urn", "integra"]
            or not entity_parts[2]
            or not UUID_PATTERN.fullmatch(entity_parts[3])
        ):
            raise ValueError("entity_id must use an Integra namespace")
        return hashlib.sha256(f"{project_id}\x1f{entity_id}".encode()).hexdigest()

    def _paths(self, project_id: str, entity_id: str) -> tuple[Path, Path]:
        key = self.entity_key(project_id, entity_id)
        return self.root / f"{key}.json", self.root / f"{key}.guard"

    def read(self, project_id: str, entity_id: str) -> dict[str, Any] | None:
        record_path, guard_path = self._paths(project_id, entity_id)
        with guard_path.open("a+b") as guard:
            fcntl.flock(guard.fileno(), fcntl.LOCK_SH)
            return self._read_unlocked(record_path)

    def acquire(self, lease: dict[str, Any]) -> dict[str, Any]:
        project_id = lease["project_id"]
        entity_id = lease["mutable_entity"]["entity_id"]
        record_path, guard_path = self._paths(project_id, entity_id)
        with guard_path.open("a+b") as guard:
            fcntl.flock(guard.fileno(), fcntl.LOCK_EX)
            existing = self._read_unlocked(record_path)
            if existing and existing.get("state") != "RELEASED":
                raise LeaseConflict("mutable entity already has a non-released lease")
            candidate = dict(lease)
            candidate["state"] = "ACTIVE"
            candidate["generation"] = (existing or {}).get("generation", 0) + 1
            self._validate_shape(candidate)
            self._validate_temporal_order(candidate)
            self._write_unlocked(record_path, candidate)
            return candidate

    def heartbeat(
        self,
        project_id: str,
        entity_id: str,
        lease_id: str,
        writer: dict[str, str],
        generation: int,
        heartbeat_at: str,
        expires_at: str,
    ) -> dict[str, Any]:
        record_path, guard_path = self._paths(project_id, entity_id)
        with guard_path.open("a+b") as guard:
            fcntl.flock(guard.fileno(), fcntl.LOCK_EX)
            lease = self._require_active(record_path, lease_id, writer, generation)
            if _instant(heartbeat_at) < _instant(lease["heartbeat_at"]):
                raise LeaseConflict("heartbeat time cannot move backwards")
            if _instant(heartbeat_at) >= _instant(lease["expires_at"]):
                raise LeaseConflict("expired lease cannot be renewed")
            if _instant(expires_at) <= _instant(heartbeat_at):
                raise LeaseConflict("expiry must be after heartbeat")
            lease["heartbeat_at"] = heartbeat_at
            lease["expires_at"] = expires_at
            self._write_unlocked(record_path, lease)
            return lease

    def release(
        self,
        project_id: str,
        entity_id: str,
        lease_id: str,
        writer: dict[str, str],
        generation: int,
        released_at: str,
    ) -> dict[str, Any]:
        record_path, guard_path = self._paths(project_id, entity_id)
        with guard_path.open("a+b") as guard:
            fcntl.flock(guard.fileno(), fcntl.LOCK_EX)
            lease = self._require_active(record_path, lease_id, writer, generation)
            if _instant(released_at) < _instant(lease["acquired_at"]):
                raise LeaseConflict("release cannot predate acquisition")
            lease["state"] = "RELEASED"
            lease["released_at"] = released_at
            lease["release_reason"] = "WRITER_RELEASE"
            self._write_unlocked(record_path, lease)
            return lease

    def recover_stale(
        self,
        project_id: str,
        entity_id: str,
        now: str,
        observation: RecoveryObservation,
    ) -> tuple[RecoveryDecision, dict[str, Any]]:
        record_path, guard_path = self._paths(project_id, entity_id)
        with guard_path.open("a+b") as guard:
            fcntl.flock(guard.fileno(), fcntl.LOCK_EX)
            lease = self._read_unlocked(record_path)
            if lease is None:
                raise LeaseConflict("no lease exists for recovery")
            decision = recovery_decision(lease, now, observation)
            if decision is RecoveryDecision.ALLOW_RECOVERY:
                lease["state"] = "RELEASED"
                lease["released_at"] = now
                lease["release_reason"] = "VERIFIED_STALE_RECOVERY"
                self._write_unlocked(record_path, lease)
            return decision, lease

    @staticmethod
    def _read_unlocked(path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)

    @staticmethod
    def _write_unlocked(path: Path, value: dict[str, Any]) -> None:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            directory_descriptor = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_descriptor)
            finally:
                os.close(directory_descriptor)
        finally:
            if temporary.exists():
                temporary.unlink()

    @staticmethod
    def _validate_temporal_order(lease: dict[str, Any]) -> None:
        acquired = _instant(lease["acquired_at"])
        heartbeat = _instant(lease["heartbeat_at"])
        expires = _instant(lease["expires_at"])
        if heartbeat < acquired or expires <= heartbeat:
            raise LeaseConflict("lease timestamps are not monotonic")

    @staticmethod
    def _validate_shape(lease: dict[str, Any]) -> None:
        if lease.get("schema_version") != "1.0":
            raise LeaseConflict("unsupported lease schema version")
        for field, namespace in (("lease_id", "lease"), ("operation_id", "operation")):
            value = lease.get(field, "")
            suffix = value.removeprefix(f"urn:integra:{namespace}:")
            if suffix == value or not UUID_PATTERN.fullmatch(suffix):
                raise LeaseConflict(f"invalid {field}")
        mutable = lease.get("mutable_entity", {})
        entity_id = mutable.get("entity_id", "")
        expected_prefix = f"urn:integra:{mutable.get('namespace', '')}:"
        if not expected_prefix or not entity_id.startswith(expected_prefix):
            raise LeaseConflict("mutable entity namespace and ID do not match")
        writer = lease.get("writer", {})
        if set(writer) != {"component_id", "host_id", "process_id", "process_start_token"}:
            raise LeaseConflict("writer identity is incomplete")
        if not isinstance(writer.get("process_id"), int) or writer["process_id"] < 1:
            raise LeaseConflict("writer process ID must be a positive integer")
        if any(not str(writer.get(field, "")).strip() for field in ("component_id", "host_id", "process_start_token")):
            raise LeaseConflict("writer identity contains an empty field")
        digest = lease.get("artifact_precondition", {}).get("content_sha256", "")
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise LeaseConflict("artifact precondition must contain a lowercase SHA-256")
        readers = lease.get("readers")
        if not isinstance(readers, list) or len(readers) != len(set(readers)):
            raise LeaseConflict("lease readers must be a unique list")

    @staticmethod
    def _require_active(
        record_path: Path,
        lease_id: str,
        writer: dict[str, str],
        generation: int,
    ) -> dict[str, Any]:
        lease = LeaseStore._read_unlocked(record_path)
        if lease is None or lease.get("state") != "ACTIVE":
            raise LeaseConflict("active lease not found")
        if lease.get("lease_id") != lease_id:
            raise LeaseConflict("lease ID does not match")
        if lease.get("writer") != writer:
            raise LeaseConflict("writer identity does not match")
        if lease.get("generation") != generation:
            raise LeaseConflict("lease generation does not match")
        return lease
