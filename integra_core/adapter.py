"""Minimal non-mutating adapters for pinned local source components."""

from __future__ import annotations

import hashlib
import os
import signal
import subprocess
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .identity import derive_imported_id
from .protocol import (
    CompatibilityError,
    PROTOCOL_VERSION,
    ProtocolViolation,
    canonical_json,
    content_sha256,
    negotiate_protocol,
    validate_artifact_reference,
    validate_component_identity,
    validate_message,
)


class AdapterPreconditionError(RuntimeError):
    """Raised before execution when a source or request is not trustworthy."""


@dataclass(frozen=True)
class CapabilitySpec:
    id: str
    version: str
    input_schema_ids: tuple[str, ...]
    output_schema_ids: tuple[str, ...]
    supports_resume: bool
    command: tuple[str, ...]
    success_stdout_marker: str

    def declaration(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "version": self.version,
            "input_schema_ids": list(self.input_schema_ids),
            "output_schema_ids": list(self.output_schema_ids),
            "supports_resume": self.supports_resume,
        }


@dataclass(frozen=True)
class ProcessOutcome:
    state: str
    exit_code: int | None
    stdout: bytes
    stderr: bytes
    elapsed_ms: int


class LocalComponentAdapter:
    """Invoke a fixed capability in a verified checkout through R3 messages."""

    def __init__(
        self,
        *,
        identity: dict[str, Any],
        source_root: Path,
        output_root: Path,
        capabilities: tuple[CapabilitySpec, ...],
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        validate_component_identity(identity)
        if not capabilities or len({item.id for item in capabilities}) != len(capabilities):
            raise AdapterPreconditionError("capabilities must be non-empty and unique")
        self.identity = identity
        self.source_root = source_root.resolve()
        self.output_root = output_root.resolve()
        self.capabilities = {item.id: item for item in capabilities}
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def verify_source(self) -> dict[str, str]:
        if not self.source_root.is_dir():
            raise AdapterPreconditionError("source checkout does not exist")
        if self.output_root == self.source_root or self.source_root in self.output_root.parents:
            raise AdapterPreconditionError("adapter output must be outside the source checkout")
        head = self._git("rev-parse", "HEAD")
        tree = self._git("rev-parse", "HEAD^{tree}")
        status = self._git("status", "--porcelain", "--untracked-files=all")
        if head != self.identity["commit_sha"]:
            raise AdapterPreconditionError("source HEAD differs from pinned component identity")
        if tree != self.identity["tree_sha"]:
            raise AdapterPreconditionError("source tree differs from pinned component identity")
        if status:
            raise AdapterPreconditionError("source checkout is not clean")
        return {"commit_sha": head, "tree_sha": tree, "status": "CLEAN"}

    def handshake(self, request: dict[str, Any]) -> dict[str, Any]:
        validate_message(request)
        if request["type"] != "HANDSHAKE_REQUEST":
            raise ProtocolViolation("adapter handshake requires HANDSHAKE_REQUEST")
        selected = negotiate_protocol(
            request["payload"]["supported_protocol_versions"], [PROTOCOL_VERSION]
        )
        requested = set(request["payload"]["requested_capabilities"])
        missing = requested - set(self.capabilities)
        if missing:
            raise CompatibilityError(f"unsupported capabilities: {sorted(missing)}")
        response = self._message(
            "HANDSHAKE_RESPONSE",
            request["correlation_id"],
            "handshake",
            {
                "selected_protocol_version": selected,
                "worker": self.identity,
                "capabilities": [
                    self.capabilities[key].declaration()
                    for key in sorted(self.capabilities)
                    if not requested or key in requested
                ],
                "compatibility": {
                    "schema_policy": "EXACT_SCHEMA_VERSION",
                    "backward_compatible_protocol_versions": [],
                },
            },
        )
        validate_message(response)
        return response

    def invoke(
        self,
        request: dict[str, Any],
        *,
        cancel_requested: Callable[[], bool] | None = None,
    ) -> list[dict[str, Any]]:
        validate_message(request)
        if request["type"] != "JOB_REQUEST":
            raise ProtocolViolation("adapter invocation requires JOB_REQUEST")
        capability = self.capabilities.get(request["payload"]["capability"])
        if capability is None:
            raise CompatibilityError("requested capability is unsupported")

        source_before = self.verify_source()
        inputs = request["payload"]["inputs"]
        input_paths = self._validate_inputs(inputs)
        command = self._render_command(capability.command, input_paths)
        events = [self._progress(request, 0, 0.0, "validated")]
        outcome = self._run_process(
            command,
            timeout_ms=request["payload"]["timeout_ms"],
            cancel_requested=cancel_requested or (lambda: False),
        )
        source_after = self.verify_source()

        if outcome.state == "CANCELLED":
            events.append(
                self._message(
                    "CANCEL_ACK",
                    request["correlation_id"],
                    "cancelled",
                    {"job_id": request["payload"]["job_id"], "status": "CANCELLED"},
                )
            )
            return self._validated(events)
        if outcome.state == "TIMED_OUT":
            events.append(
                self._error(
                    request,
                    "WORKER_TIMEOUT_UNKNOWN_OUTCOME",
                    "The bounded worker exceeded its declared timeout.",
                    "UNKNOWN_OUTCOME",
                    outcome,
                )
            )
            return self._validated(events)
        if outcome.exit_code != 0:
            events.append(
                self._error(
                    request,
                    "WORKER_COMMAND_FAILED",
                    "The pinned worker capability returned a non-zero status.",
                    "NON_RETRYABLE",
                    outcome,
                )
            )
            return self._validated(events)
        if capability.success_stdout_marker.encode() not in outcome.stdout:
            events.append(
                self._error(
                    request,
                    "WORKER_SUCCESS_MARKER_MISSING",
                    "The worker output did not contain its pinned success marker.",
                    "NON_RETRYABLE",
                    outcome,
                )
            )
            return self._validated(events)

        events.append(self._progress(request, 1, 0.9, "capability_complete"))
        report = self._report(request, capability, outcome, source_before, source_after)
        report_bytes = canonical_json(report)
        report_hash = hashlib.sha256(report_bytes).hexdigest()
        relative_path = f"adapter_reports/{report_hash}.json"
        self._atomic_write(self.output_root / relative_path, report_bytes)
        artifact = {
            "artifact_id": derive_imported_id(
                "artifact", self.identity["component_id"], capability.id, report_hash
            ),
            "kind": "adapter_probe_report",
            "schema_id": "adapter_probe_report_v1",
            "schema_version": "1.0",
            "content_sha256": report_hash,
            "size_bytes": len(report_bytes),
            "storage_scope": "INTEGRA_STORE",
            "relative_path": relative_path,
            "origin": self.identity,
            "provenance": {
                "parent_artifact_ids": [item["artifact_id"] for item in inputs],
                "operation_id": request["payload"]["operation_id"],
            },
        }
        validate_artifact_reference(artifact)
        events.append(
            self._message(
                "RESULT",
                request["correlation_id"],
                "result",
                {
                    "job_id": request["payload"]["job_id"],
                    "operation_id": request["payload"]["operation_id"],
                    "status": "SUCCEEDED",
                    "outputs": [artifact],
                },
            )
        )
        return self._validated(events)

    def _report(
        self,
        request: dict[str, Any],
        capability: CapabilitySpec,
        outcome: ProcessOutcome,
        source_before: dict[str, str],
        source_after: dict[str, str],
    ) -> dict[str, Any]:
        inputs = request["payload"]["inputs"]
        return {
            "schema_version": "1.0",
            "component": self.identity,
            "capability": capability.declaration(),
            "job_id": request["payload"]["job_id"],
            "operation_id": request["payload"]["operation_id"],
            "input_artifact_ids": [item["artifact_id"] for item in inputs],
            "input_content_sha256": [item["content_sha256"] for item in inputs],
            "source_before": source_before,
            "source_after": source_after,
            "command": list(capability.command),
            "exit_code": outcome.exit_code,
            "stdout_sha256": hashlib.sha256(outcome.stdout).hexdigest(),
            "stderr_sha256": hashlib.sha256(outcome.stderr).hexdigest(),
            "stdout_size_bytes": len(outcome.stdout),
            "stderr_size_bytes": len(outcome.stderr),
            "elapsed_ms": outcome.elapsed_ms,
            "status": "PASS",
        }

    def _validate_inputs(self, inputs: list[dict[str, Any]]) -> list[Path]:
        paths: list[Path] = []
        for reference in inputs:
            validate_artifact_reference(reference)
            if reference["storage_scope"] != "SOURCE_READ_ONLY":
                raise AdapterPreconditionError("adapter spike accepts read-only inputs only")
            if reference["origin"] != self.identity:
                raise AdapterPreconditionError("input origin differs from pinned worker identity")
            path = (self.source_root / reference["relative_path"]).resolve()
            if self.source_root not in path.parents or not path.is_file():
                raise AdapterPreconditionError("input does not resolve to a source file")
            payload = path.read_bytes()
            if len(payload) != reference["size_bytes"]:
                raise AdapterPreconditionError("input size differs from artifact reference")
            if hashlib.sha256(payload).hexdigest() != reference["content_sha256"]:
                raise AdapterPreconditionError("input hash differs from artifact reference")
            paths.append(path)
        return paths

    def _render_command(self, template: tuple[str, ...], inputs: list[Path]) -> list[str]:
        rendered: list[str] = []
        for item in template:
            value = item
            for index, path in enumerate(inputs):
                value = value.replace(f"{{input{index}}}", str(path))
            value = value.replace("{output_root}", str(self.output_root))
            if "{input" in value or "{output_root}" in value:
                raise AdapterPreconditionError("capability command has an unresolved placeholder")
            rendered.append(value)
        if not rendered:
            raise AdapterPreconditionError("capability command is empty")
        return rendered

    def _run_process(
        self,
        command: list[str],
        *,
        timeout_ms: int,
        cancel_requested: Callable[[], bool],
    ) -> ProcessOutcome:
        self.output_root.mkdir(parents=True, exist_ok=True)
        temp_root = self.output_root / "tmp"
        temp_root.mkdir(parents=True, exist_ok=True)
        environment = os.environ.copy()
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        environment["TMPDIR"] = str(temp_root)
        started = time.monotonic()
        process = subprocess.Popen(
            command,
            cwd=self.source_root,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        deadline = started + timeout_ms / 1000
        while True:
            try:
                stdout, stderr = process.communicate(timeout=0.05)
                state = "COMPLETED"
                break
            except subprocess.TimeoutExpired:
                if cancel_requested():
                    stdout, stderr = self._terminate(process)
                    state = "CANCELLED"
                    break
                if time.monotonic() >= deadline:
                    stdout, stderr = self._terminate(process)
                    state = "TIMED_OUT"
                    break
        return ProcessOutcome(
            state, process.returncode, stdout, stderr,
            max(0, round((time.monotonic() - started) * 1000)),
        )

    @staticmethod
    def _terminate(process: subprocess.Popen[bytes]) -> tuple[bytes, bytes]:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            return process.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            return process.communicate()

    def _progress(
        self, request: dict[str, Any], sequence: int, fraction: float, stage: str
    ) -> dict[str, Any]:
        return self._message(
            "PROGRESS",
            request["correlation_id"],
            f"progress-{sequence}",
            {
                "job_id": request["payload"]["job_id"],
                "sequence": sequence,
                "fraction": fraction,
                "stage": stage,
            },
        )

    def _error(
        self,
        request: dict[str, Any],
        code: str,
        message: str,
        classification: str,
        outcome: ProcessOutcome,
    ) -> dict[str, Any]:
        return self._message(
            "ERROR",
            request["correlation_id"],
            code.lower(),
            {
                "job_id": request["payload"]["job_id"],
                "code": code,
                "message": message,
                "classification": classification,
                "safe_to_retry": False,
                "details": {
                    "exit_code": outcome.exit_code,
                    "stdout_sha256": hashlib.sha256(outcome.stdout).hexdigest(),
                    "stderr_sha256": hashlib.sha256(outcome.stderr).hexdigest(),
                    "elapsed_ms": outcome.elapsed_ms,
                },
            },
        )

    def _message(
        self,
        message_type: str,
        correlation_id: str,
        discriminator: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        fingerprint = content_sha256(
            {
                "component": self.identity["component_id"],
                "correlation_id": correlation_id,
                "discriminator": discriminator,
                "payload": payload,
            }
        )
        message_id = derive_imported_id(
            "message", self.identity["component_id"], discriminator, fingerprint
        )
        timestamp = self.clock().astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        return {
            "protocol_version": PROTOCOL_VERSION,
            "message_id": message_id,
            "correlation_id": correlation_id,
            "sent_at": timestamp,
            "type": message_type,
            "payload": payload,
        }

    @staticmethod
    def _validated(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        for event in events:
            validate_message(event)
        return events

    def _git(self, *arguments: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(self.source_root), *arguments],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if result.returncode != 0:
            raise AdapterPreconditionError("source path is not a readable Git checkout")
        return result.stdout.strip()

    @staticmethod
    def _atomic_write(path: Path, payload: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if path.read_bytes() != payload:
                raise AdapterPreconditionError("content-addressed output collision")
            return
        descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
