"""Fail-closed helpers for the R6 pinned real-media certification."""

from __future__ import annotations

import hashlib
import copy
import json
import os
import select
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .core_alpha import StageOutput, reject_symlink_components, stage_output_contract
from .identity import derive_imported_id
from .protocol import (
    PROTOCOL_VERSION,
    ProgressTracker,
    canonical_json,
    content_sha256,
    validate_artifact_reference,
    validate_message,
)


STAGES = ("source", "transcript", "topics", "review", "knowledge", "media_clip")
SEMANTIC_STATUS = {
    "source": "NOT_APPLICABLE", "transcript": "REVIEW_REQUIRED",
    "topics": "REVIEW_REQUIRED", "review": "REVIEW_REQUIRED",
    "knowledge": "PROVISIONAL", "media_clip": "NOT_APPLICABLE",
}
PIPELINE_SEMANTIC_STATUS = {**SEMANTIC_STATUS, "transcript": "REVIEW_REQUIRED"}
TOP_LEVEL_FIELDS = {
    "schema_version", "status", "issue", "execution_mode", "executed_at",
    "semantic_authority", "source_repositories_changed", "protected_data_accessed",
    "human_decisions_applied", "reference_host", "source", "component_identities",
    "implementation", "models", "stage_sequence", "stages", "alignment",
    "provenance", "control_plane", "determinism", "acceptance", "limitations",
}
ACCEPTANCE = {
    "real_local_video_decoded": True, "pinned_components_executed": True,
    "source_grounded_provenance": True,
    "videotext_review_checkpoint": "SOURCE_TRANSCRIPT",
    "seminartext_topics_generated": True, "canonical_evidence_valid": True,
    "exception_review_package_generated": True,
    "provisional_knowledge_generated": True,
    "videotext_media_clip_rendered": True,
    "semantic_authority": "PROVISIONAL_ONLY", "human_decisions_applied": 0,
    "source_repositories_changed": False, "protected_data_accessed": False,
    "gold_accessed": False,
}


class RealMediaError(RuntimeError):
    """Raised when real-media evidence would overclaim or lose provenance."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def is_git_sha(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 40 and all(char in "0123456789abcdef" for char in value)


def determinism_run_record(document: dict[str, Any]) -> dict[str, Any]:
    stages = document.get("stages", {})
    control = document.get("control_plane", {})
    record = {
        "executed_at": document.get("executed_at"),
        "controller_commit_sha": control.get("controller_commit_sha"),
        "controller_tree_sha": control.get("controller_tree_sha"),
        "manifest_sha256": control.get("manifest_sha256"),
        "stage_hashes": {
            stage: stages.get(stage, {}).get("sha256") for stage in STAGES
        },
    }
    return {"run_id": content_sha256(record), **record}


def certify_deterministic_runs(
    first: dict[str, Any], second: dict[str, Any]
) -> dict[str, Any]:
    """Combine two independently emitted run records after exact comparison."""

    for label, document in (("first", first), ("second", second)):
        errors = validate_actual_evidence(document)
        if errors:
            raise RealMediaError(f"{label} evidence is invalid: {'; '.join(errors)}")
        if document["determinism"] != {
            "independent_runs_compared": 1,
            "all_stage_hashes_identical": None,
            "runs": [determinism_run_record(document)],
        }:
            raise RealMediaError(f"{label} evidence is not a single-run record")
    stable_fields = {
        "schema_version", "status", "issue", "execution_mode",
        "semantic_authority", "source_repositories_changed",
        "protected_data_accessed", "human_decisions_applied", "reference_host",
        "source", "component_identities", "implementation", "models",
        "stage_sequence", "stages", "alignment", "provenance", "acceptance",
        "limitations",
    }
    if any(first[field] != second[field] for field in stable_fields):
        raise RealMediaError("independent run evidence differs")
    first_control = dict(first["control_plane"])
    second_control = dict(second["control_plane"])
    first_control.pop("lease_heartbeats_during_workers")
    second_control.pop("lease_heartbeats_during_workers")
    if first_control != second_control:
        raise RealMediaError("independent run control-plane evidence differs")
    runs = [determinism_run_record(first), determinism_run_record(second)]
    if runs[0]["run_id"] == runs[1]["run_id"]:
        raise RealMediaError("independent run identities must differ")
    certified = copy.deepcopy(first)
    certified["determinism"] = {
        "independent_runs_compared": 2,
        "all_stage_hashes_identical": True,
        "runs": runs,
    }
    errors = validate_actual_evidence(certified)
    if errors:
        raise RealMediaError("certified evidence is invalid: " + "; ".join(errors))
    return certified


def aggregate_whisper_words(document: dict[str, Any]) -> tuple[list[dict], list[dict]]:
    """Aggregate whisper.cpp pieces without inventing zero-duration intervals."""

    transcription = document.get("transcription")
    if not isinstance(transcription, list) or not transcription:
        raise RealMediaError("whisper document has no transcription")
    words: list[dict] = []
    omitted: list[dict] = []
    for segment_index, segment in enumerate(transcription):
        if not isinstance(segment, dict):
            raise RealMediaError("whisper transcription segment is invalid")
        current: dict[str, Any] | None = None
        for token in segment.get("tokens", []):
            if not isinstance(token, dict):
                continue
            piece = token.get("text", "")
            if not isinstance(piece, str) or not piece or piece.startswith("[_"):
                continue
            offsets = token.get("offsets", {})
            try:
                start = float(offsets["from"]) / 1000.0
                end = float(offsets["to"]) / 1000.0
                score = float(token.get("p", 0.0))
            except (KeyError, TypeError, ValueError) as error:
                raise RealMediaError("whisper token timing is invalid") from error
            if piece[:1].isspace() or current is None:
                if current is not None:
                    _finish_word(current, words, omitted)
                current = {"word": piece.strip(), "start": start, "end": end, "scores": [score], "segment_index": segment_index}
            else:
                current["word"] += piece
                current["end"] = max(current["end"], end)
                current["scores"].append(score)
        if current is not None:
            _finish_word(current, words, omitted)
    if not words:
        raise RealMediaError("whisper transcription has no alignable word intervals")
    return words, omitted


def _finish_word(current: dict[str, Any], words: list[dict], omitted: list[dict]) -> None:
    value = str(current["word"]).strip()
    if not value:
        return
    record = {"word": value, "start": round(float(current["start"]), 3), "end": round(float(current["end"]), 3), "score": round(sum(current["scores"]) / len(current["scores"]), 6)}
    if record["end"] <= record["start"]:
        omitted.append({**record, "reason": "WHISPER_ZERO_DURATION_TOKEN", "segment_index": current["segment_index"]})
    else:
        words.append(record)


class JsonlProcessStageWorker:
    """Execute every real stage in an R3 stdio JSONL subprocess.

    The child performs the source-component operation only after receiving and
    validating the handshake and job. Its RESULT names an existing, confined,
    hash-verified file which the control plane then promotes atomically.
    """

    def __init__(
        self,
        *,
        worker_script: Path,
        config_path: Path,
        artifact_store: Path,
        controller: dict[str, Any],
        config_sha256: str,
        timeout_seconds: int = 900,
        heartbeat_interval_seconds: int = 60,
    ) -> None:
        self.worker_script = worker_script.resolve()
        self.config_path = config_path.resolve()
        self.artifact_store = artifact_store.resolve()
        self.controller = controller
        self.config_sha256 = config_sha256
        self.timeout_seconds = timeout_seconds
        self.heartbeat_interval_seconds = heartbeat_interval_seconds
        self.calls: list[str] = []
        self.messages: list[dict[str, Any]] = []
        self.lease_heartbeats = 0
        self._lease_heartbeat: Any = None

    def set_lease_heartbeat(self, callback: Any) -> None:
        self._lease_heartbeat = callback

    @staticmethod
    def _kill_and_reap(process: subprocess.Popen[bytes]) -> None:
        """Stop the isolated worker process group and always collect the child."""

        if getattr(process, "stdin", None) is not None and process.stdin.closed:
            process.stdin = None
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.communicate()

    def _refresh_active_lease(self, process: subprocess.Popen[bytes], stage: str) -> None:
        if self._lease_heartbeat is None:
            self._kill_and_reap(process)
            raise RealMediaError(
                f"{stage}: lease heartbeat is unavailable during a running worker"
            )
        try:
            self._lease_heartbeat()
        except Exception:
            self._kill_and_reap(process)
            raise
        self.lease_heartbeats += 1

    def _read_handshake_frame(
        self, process: subprocess.Popen[bytes], stage: str
    ) -> bytes:
        """Read one bounded JSONL frame without allowing a partial line to hang."""

        assert process.stdout is not None
        deadline = time.monotonic() + min(30, self.timeout_seconds)
        frame = bytearray()
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self._kill_and_reap(process)
                raise RealMediaError(
                    f"{stage}: R3 worker did not complete its handshake"
                )
            wait = min(self.heartbeat_interval_seconds, remaining)
            readable, _, _ = select.select([process.stdout], [], [], wait)
            if not readable:
                if time.monotonic() >= deadline:
                    self._kill_and_reap(process)
                    raise RealMediaError(
                        f"{stage}: R3 worker did not complete its handshake"
                    )
                self._refresh_active_lease(process, stage)
                continue
            chunk = os.read(process.stdout.fileno(), 65536)
            if not chunk:
                self._kill_and_reap(process)
                raise RealMediaError(
                    f"{stage}: R3 worker ended before completing its handshake"
                )
            frame.extend(chunk)
            if len(frame) > 1024 * 1024:
                self._kill_and_reap(process)
                raise RealMediaError(f"{stage}: R3 handshake frame is oversized")
            if b"\n" in frame:
                line, remainder = bytes(frame).split(b"\n", 1)
                if remainder:
                    self._kill_and_reap(process)
                    raise RealMediaError(
                        f"{stage}: R3 worker emitted data before job dispatch"
                    )
                return line

    def run(
        self,
        stage: str,
        capability: str,
        component: dict[str, Any],
        inputs: tuple[dict[str, Any], ...],
    ) -> StageOutput:
        if sha256_file(self.config_path) != self.config_sha256:
            raise RealMediaError(f"{stage}: worker configuration changed before execution")
        correlation = derive_imported_id(
            "session", "integra", "r6-real", content_sha256({"stage": stage})
        )
        operation = derive_imported_id(
            "operation",
            component["component_id"],
            capability,
            content_sha256([item["content_sha256"] for item in inputs]),
        )
        job_id = derive_imported_id(
            "job",
            component["component_id"],
            capability,
            content_sha256({"operation_id": operation}),
        )
        handshake = self._message(
            "HANDSHAKE_REQUEST",
            correlation,
            "handshake-request",
            {
                "supported_protocol_versions": [PROTOCOL_VERSION],
                "requested_capabilities": [capability],
                "controller": self.controller,
            },
        )
        job = self._message(
            "JOB_REQUEST",
            correlation,
            "job-request",
            {
                "job_id": job_id,
                "operation_id": operation,
                "idempotency_key": content_sha256(
                    {
                        "capability": capability,
                        "inputs": [item["content_sha256"] for item in inputs],
                    }
                ),
                "capability": capability,
                "timeout_ms": self.timeout_seconds * 1000,
                "inputs": list(inputs),
            },
        )
        for outgoing in (handshake, job):
            validate_message(outgoing)
        environment = os.environ.copy()
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        process = subprocess.Popen(
            [
                sys.executable,
                str(self.worker_script),
                "--stage",
                stage,
                "--config",
                str(self.config_path),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
            env=environment,
        )
        assert process.stdin is not None and process.stdout is not None
        process.stdin.write(canonical_json(handshake) + b"\n")
        process.stdin.flush()
        self.messages.append(handshake)
        try:
            response_line = self._read_handshake_frame(process, stage)
            response = json.loads(response_line)
            validate_message(response)
            if (
                response["correlation_id"] != correlation
                or response["type"] != "HANDSHAKE_RESPONSE"
            ):
                raise RealMediaError(
                    f"{stage}: R3 handshake correlation or type differs"
                )
            self.messages.append(response)
            process.stdin.write(canonical_json(job) + b"\n")
            process.stdin.flush()
            process.stdin.close()
            process.stdin = None
            self.messages.append(job)
        except Exception as error:
            self._kill_and_reap(process)
            if isinstance(error, (UnicodeDecodeError, json.JSONDecodeError)):
                raise RealMediaError(
                    f"{stage}: R3 worker emitted an invalid handshake"
                ) from error
            raise
        deadline = time.monotonic() + self.timeout_seconds
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self._kill_and_reap(process)
                raise RealMediaError(
                    f"{stage}: R3 worker exceeded its enforced timeout; outcome is unknown and was not retried"
                )
            try:
                stdout, stderr = process.communicate(
                    timeout=min(self.heartbeat_interval_seconds, remaining)
                )
                break
            except subprocess.TimeoutExpired:
                self._refresh_active_lease(process, stage)
        if process.returncode != 0:
            raise RealMediaError(
                f"{stage}: R3 worker failed ({process.returncode}): "
                + stderr.decode("utf-8", errors="replace")
            )
        lines = stdout.splitlines()
        if len(lines) != 2:
            raise RealMediaError(f"{stage}: R3 worker emitted {len(lines) + 1} messages instead of 3")
        try:
            progress, result = [json.loads(line) for line in lines]
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RealMediaError(f"{stage}: R3 worker emitted invalid JSONL") from error
        for message in (progress, result):
            validate_message(message)
            if message["correlation_id"] != correlation:
                raise RealMediaError(f"{stage}: R3 worker correlation changed")
            self.messages.append(message)
        if [response["type"], progress["type"], result["type"]] != ["HANDSHAKE_RESPONSE", "PROGRESS", "RESULT"]:
            raise RealMediaError(f"{stage}: R3 worker lifecycle is incomplete")
        expected_worker = dict(component)
        if response["payload"]["worker"] != expected_worker:
            raise RealMediaError(f"{stage}: R3 worker identity differs from the pin")
        expected_kind, expected_schema = stage_output_contract(stage, "PINNED_REAL_MEDIA")
        expected_capability = {
            "id": capability,
            "version": "1.0",
            "input_schema_ids": [item["schema_id"] for item in inputs],
            "output_schema_ids": [expected_schema],
            "supports_resume": False,
        }
        if response["payload"]["capabilities"] != [expected_capability]:
            raise RealMediaError(f"{stage}: R3 capability declaration differs")
        tracker = ProgressTracker()
        tracker.apply(progress)
        tracker.apply(result)
        if progress["payload"] != {
            "job_id": job_id,
            "sequence": 0,
            "fraction": 1.0,
            "stage": stage,
        }:
            raise RealMediaError(f"{stage}: R3 progress differs")
        result_payload = result["payload"]
        if (
            result_payload["job_id"] != job_id
            or result_payload["operation_id"] != operation
            or len(result_payload["outputs"]) != 1
        ):
            raise RealMediaError(f"{stage}: R3 result identity differs")
        reference = result_payload["outputs"][0]
        validate_artifact_reference(reference)
        if (
            reference["origin"] != component
            or reference["kind"] != expected_kind
            or reference["schema_id"] != expected_schema
            or reference["provenance"]["parent_artifact_ids"]
            != [item["artifact_id"] for item in inputs]
            or reference["provenance"]["operation_id"] != operation
        ):
            raise RealMediaError(f"{stage}: R3 output contract or provenance differs")
        output_path = (self.artifact_store / reference["relative_path"]).absolute()
        job_key = job_id.rsplit(":", 1)[-1]
        if not reference["relative_path"].startswith(f".staging/{job_key}/"):
            raise RealMediaError(f"{stage}: R3 output is outside its job staging directory")
        reject_symlink_components(output_path, label="R3 worker output")
        try:
            output_path.resolve().relative_to(self.artifact_store)
        except ValueError as error:
            raise RealMediaError(f"{stage}: R3 output escaped the artifact store") from error
        if not output_path.is_file() or output_path.stat().st_nlink != 1:
            raise RealMediaError(f"{stage}: R3 result output does not exist")
        output = output_path.read_bytes()
        if len(output) != reference["size_bytes"] or hashlib.sha256(output).hexdigest() != reference["content_sha256"]:
            raise RealMediaError(f"{stage}: R3 result output content differs")
        output_path.unlink()
        try:
            output_path.parent.rmdir()
        except OSError:
            pass
        self.calls.append(stage)
        if sha256_file(self.config_path) != self.config_sha256:
            raise RealMediaError(f"{stage}: worker configuration changed during execution")
        return StageOutput(
            payload=output,
            kind=reference["kind"],
            schema_id=reference["schema_id"],
            schema_version=reference["schema_version"],
            source_locator=reference["provenance"].get("source_locator"),
            semantic_status=reference["semantic_status"],
        )

    @staticmethod
    def _message(
        kind: str,
        correlation: str,
        discriminator: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "protocol_version": PROTOCOL_VERSION,
            "message_id": derive_imported_id(
                "message", "integra", f"{discriminator}:{correlation}", content_sha256(payload)
            ),
            "correlation_id": correlation,
            "sent_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "type": kind,
            "payload": payload,
        }


def validate_actual_evidence(document: dict[str, Any]) -> list[str]:
    """Validate every field of an R6 evidence record without third-party deps."""

    errors: list[str] = []
    if not isinstance(document, dict) or set(document) != TOP_LEVEL_FIELDS:
        errors.append("top-level fields must exactly match the R6 real-media contract")
    scalars = {
        "schema_version": "1.0", "status": "PASS", "issue": 8,
        "execution_mode": "PINNED_REAL_MEDIA", "semantic_authority": "PROVISIONAL_ONLY",
        "source_repositories_changed": False, "protected_data_accessed": False,
        "human_decisions_applied": 0,
    }
    for field, expected in scalars.items():
        if document.get(field) != expected:
            errors.append(f"{field} must be {expected!r}")
    try:
        timestamp = datetime.fromisoformat(str(document.get("executed_at", "")).replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            raise ValueError
    except ValueError:
        errors.append("executed_at must be an ISO-8601 timezone-aware timestamp")

    _exact_string_object(document.get("reference_host"), {"os", "architecture", "python", "swift", "ffmpeg", "whisper_cpp", "ollama"}, "reference_host", errors)
    source = document.get("source")
    if not isinstance(source, dict) or set(source) != {"kind", "privacy", "sha256", "size_bytes", "duration_seconds", "language"}:
        errors.append("source fields are invalid")
    else:
        if source.get("kind") != "GENERATED_LOCAL_VIDEO" or source.get("privacy") != "NON_PRIVATE_SYNTHETIC_SPEECH" or source.get("language") != "ru":
            errors.append("source certification identity is invalid")
        if not is_sha256(source.get("sha256")) or not _positive_int(source.get("size_bytes")) or not _positive_number(source.get("duration_seconds")):
            errors.append("source hash/size/duration is invalid")

    components = document.get("component_identities")
    if not isinstance(components, dict) or set(components) != {"seminartext", "videotext"}:
        errors.append("component_identities must contain SeminarText and VideoText")
    else:
        for name, value in components.items():
            if not isinstance(value, dict) or set(value) != {"repository", "commit_sha", "tree_sha", "version"}:
                errors.append(f"{name} component identity fields are invalid")
            elif not is_git_sha(value.get("commit_sha")) or not is_git_sha(value.get("tree_sha")) or not all(isinstance(value.get(key), str) and value[key] for key in ("repository", "version")):
                errors.append(f"{name} component identity is invalid")

    implementation = document.get("implementation")
    if not isinstance(implementation, list) or len(implementation) < 5:
        errors.append("implementation inventory must contain at least five files")
    else:
        paths: list[str] = []
        for record in implementation:
            if not isinstance(record, dict) or set(record) != {"path", "sha256"} or not isinstance(record.get("path"), str) or not record["path"] or not is_sha256(record.get("sha256")):
                errors.append("implementation record is invalid")
                continue
            paths.append(record["path"])
        if len(paths) != len(set(paths)):
            errors.append("implementation paths must be unique")

    models = document.get("models")
    if not isinstance(models, dict) or set(models) != {"whisper", "topics"}:
        errors.append("model inventory is invalid")
    else:
        whisper, topics = models.get("whisper"), models.get("topics")
        if not isinstance(whisper, dict) or set(whisper) != {"name", "sha256"} or not whisper.get("name") or not is_sha256(whisper.get("sha256")):
            errors.append("Whisper model identity is invalid")
        if not isinstance(topics, dict) or set(topics) != {"name", "provider", "digest", "weights_sha256"} or not topics.get("name") or topics.get("provider") != "ollama" or not is_sha256(topics.get("digest")) or not is_sha256(topics.get("weights_sha256")):
            errors.append("Topic model content identity is invalid")

    if document.get("stage_sequence") != list(STAGES):
        errors.append("stage_sequence must define the exact real-media path")
    stages = document.get("stages")
    if not isinstance(stages, dict) or set(stages) != set(STAGES):
        errors.append("stages must contain the exact real-media path")
    else:
        for name in STAGES:
            stage = stages[name]
            if not isinstance(stage, dict) or set(stage) != {"status", "semantic_status", "sha256", "size_bytes"}:
                errors.append(f"{name} stage fields are invalid")
            elif stage.get("status") != "PASS" or stage.get("semantic_status") != SEMANTIC_STATUS[name] or not is_sha256(stage.get("sha256")) or not _positive_int(stage.get("size_bytes")):
                errors.append(f"{name} stage is invalid")

    alignment = document.get("alignment")
    if not isinstance(alignment, dict) or set(alignment) != {"aligned_word_intervals", "unaligned_word_sequences", "omitted_zero_duration_tokens", "fabricated_intervals"}:
        errors.append("alignment fields are invalid")
    else:
        unaligned = alignment.get("unaligned_word_sequences")
        if not _positive_int(alignment.get("aligned_word_intervals")) or not isinstance(unaligned, list) or any(not isinstance(item, int) or item < 0 for item in unaligned) or len(unaligned) != len(set(unaligned)) or alignment.get("omitted_zero_duration_tokens") != len(unaligned) or alignment.get("fabricated_intervals") != 0:
            errors.append("alignment evidence is invalid")

    _validate_provenance(document.get("provenance"), errors)
    control = document.get("control_plane")
    control_keys = {
        "pipeline", "controller_commit_sha", "controller_tree_sha",
        "manifest_sha256", "project_lease_enforced",
        "lease_heartbeats_during_workers",
        "media_clip_functional_probe",
        "prefix_cancellation_checkpoint_verified",
        "prefix_resume_revalidation_verified", "r3_contract_boundary",
        "validated_jsonl_messages", "worker_processes",
        "worker_resume_support", "stage_timeout_enforced",
    }
    if not isinstance(control, dict) or set(control) != control_keys:
        errors.append("control_plane fields are invalid")
    elif (
        control.get("pipeline") != "INTEGRA_CORE_ALPHA_V1"
        or not is_git_sha(control.get("controller_commit_sha"))
        or not is_git_sha(control.get("controller_tree_sha"))
        or not is_sha256(control.get("manifest_sha256"))
        or control.get("validated_jsonl_messages") != 25
        or control.get("worker_processes") != 5
        or control.get("worker_resume_support") is not False
        or not _positive_int(control.get("lease_heartbeats_during_workers"))
        or any(
            control.get(key) is not True
            for key in (
                "project_lease_enforced",
                "prefix_cancellation_checkpoint_verified",
                "prefix_resume_revalidation_verified",
                "r3_contract_boundary",
                "stage_timeout_enforced",
                "media_clip_functional_probe",
            )
        )
    ):
        errors.append("control_plane evidence is invalid")

    determinism = document.get("determinism")
    if not isinstance(determinism, dict) or set(determinism) != {"independent_runs_compared", "all_stage_hashes_identical", "runs"}:
        errors.append("determinism fields are invalid")
    else:
        count, identical = determinism.get("independent_runs_compared"), determinism.get("all_stage_hashes_identical")
        runs = determinism.get("runs")
        if (
            not _positive_int(count)
            or not isinstance(runs, list)
            or len(runs) != count
            or (count == 1 and identical is not None)
            or (count >= 2 and identical is not True)
        ):
            errors.append("determinism evidence is invalid")
        else:
            run_ids: set[str] = set()
            for index, run in enumerate(runs):
                expected_fields = {
                    "run_id", "executed_at", "controller_commit_sha",
                    "controller_tree_sha", "manifest_sha256", "stage_hashes",
                }
                if not isinstance(run, dict) or set(run) != expected_fields:
                    errors.append(f"determinism run {index} fields are invalid")
                    continue
                expected_record = determinism_run_record(
                    {
                        "executed_at": run["executed_at"],
                        "control_plane": {
                            "controller_commit_sha": run["controller_commit_sha"],
                            "controller_tree_sha": run["controller_tree_sha"],
                            "manifest_sha256": run["manifest_sha256"],
                        },
                        "stages": {
                            stage: {"sha256": run.get("stage_hashes", {}).get(stage)}
                            for stage in STAGES
                        },
                    }
                )
                if run != expected_record or run["run_id"] in run_ids:
                    errors.append(f"determinism run {index} identity is invalid")
                run_ids.add(run["run_id"])
                if (
                    run["manifest_sha256"] != control.get("manifest_sha256")
                    or run["controller_commit_sha"]
                    != control.get("controller_commit_sha")
                    or run["controller_tree_sha"] != control.get("controller_tree_sha")
                    or run["stage_hashes"]
                    != {stage: stages[stage]["sha256"] for stage in STAGES}
                ):
                    errors.append(f"determinism run {index} hashes differ")
    if document.get("acceptance") != ACCEPTANCE:
        errors.append("acceptance evidence differs from the fail-closed contract")
    limitations = document.get("limitations")
    if not isinstance(limitations, list) or len(limitations) < 3 or len(limitations) != len(set(limitations)) or not all(isinstance(item, str) and item for item in limitations):
        errors.append("limitations must contain at least three unique statements")
    return errors


def _validate_provenance(value: Any, errors: list[str]) -> None:
    expected = {"project_id", "source_id", "transcript_revision_id", "word_interval", "topic_interval", "clip_interval", "artifact_lineage"}
    if not isinstance(value, dict) or set(value) != expected:
        errors.append("provenance fields are invalid")
        return
    if not all(isinstance(value.get(key), str) and value[key] for key in ("project_id", "source_id", "transcript_revision_id")):
        errors.append("provenance identities are invalid")
    word = value.get("word_interval")
    if not isinstance(word, dict) or set(word) != {"start_id", "end_id", "start_seconds", "end_seconds"} or not isinstance(word.get("start_id"), str) or not isinstance(word.get("end_id"), str) or not _valid_interval(word):
        errors.append("word provenance interval is invalid")
    for name in ("topic_interval", "clip_interval"):
        interval = value.get(name)
        if not isinstance(interval, dict) or set(interval) != {"start_seconds", "end_seconds"} or not _valid_interval(interval):
            errors.append(f"{name} is invalid")
    lineage = value.get("artifact_lineage")
    if not isinstance(lineage, dict) or set(lineage) != set(STAGES):
        errors.append("artifact_lineage is invalid")
    else:
        for name, record in lineage.items():
            if not isinstance(record, dict) or set(record) != {"artifact_id", "parent_artifact_ids", "operation_id"} or not isinstance(record.get("artifact_id"), str) or not record["artifact_id"] or not isinstance(record.get("operation_id"), str) or not record["operation_id"] or not isinstance(record.get("parent_artifact_ids"), list) or not all(isinstance(item, str) and item for item in record["parent_artifact_ids"]):
                errors.append(f"{name} artifact lineage is invalid")


def _valid_interval(value: dict[str, Any]) -> bool:
    start, end = value.get("start_seconds"), value.get("end_seconds")
    return isinstance(start, (int, float)) and not isinstance(start, bool) and start >= 0 and _positive_number(end) and end > start


def _positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _positive_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def _exact_string_object(value: Any, fields: set[str], label: str, errors: list[str]) -> None:
    if not isinstance(value, dict) or set(value) != fields or not all(isinstance(item, str) and item for item in value.values()):
        errors.append(f"{label} fields are invalid")


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RealMediaError(f"JSON document must be an object: {path}")
    return value
