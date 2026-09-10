"""Deterministic R6 control plane for the bounded Core Alpha vertical slice."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import platform
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol

from .identity import derive_imported_id
from .project_lease import LeaseConflict, LeaseStore
from .protocol import canonical_json, validate_artifact_reference, validate_component_identity


STAGE_ORDER = ("transcript", "topics", "review", "knowledge", "media_clip")
STAGE_COMPONENTS = {
    "transcript": "videotext",
    "topics": "seminartext",
    "review": "seminartext",
    "knowledge": "seminartext",
    "media_clip": "videotext",
}
STAGE_CAPABILITIES = {
    "transcript": "videotext.asr",
    "topics": "seminartext.topics",
    "review": "seminartext.topic_review",
    "knowledge": "seminartext.canonical_knowledge",
    "media_clip": "videotext.media_clip",
}
STAGE_OUTPUTS = {
    "transcript": ("machine_transcript", "videotext_transcript_replay_v1"),
    "topics": ("topic_drafts", "seminartext_topic_replay_v1"),
    "review": ("exception_review_result", "exception_review_replay_v1"),
    "knowledge": ("canonical_knowledge_candidate", "canonical_knowledge_replay_v1"),
    "media_clip": ("media_clip", "videotext_media_clip_replay_v1"),
}
STAGE_PARENTS = {
    "transcript": ("source",),
    "topics": ("transcript",),
    "review": ("transcript", "topics"),
    "knowledge": ("transcript", "topics", "review"),
    "media_clip": ("source", "topics", "review"),
}
EXPECTED_SELECTIONS = {
    "asr": ("videotext",),
    "topics": ("seminartext",),
    "review_mechanics": ("seminartext", "videotext"),
    "quality_validation": ("seminartext", "videotext"),
}
EXPECTED_R5_SELECTIONS_SHA256 = (
    "38ec6db0172c6bd61d8515b71c32be0554e311684364758cf87c598723dc20c3"
)
EXPECTED_PINNED_COMPONENTS = {
    "seminartext": {
        "component_id": "seminartext",
        "repository": "Yurielo/seminartext",
        "commit_sha": "a94936cd77cde13561c97c804ece1ac1134e01a6",
        "tree_sha": "5f5951da1d5dcf957ef982510fde3537f601ea15",
        "version": "4.0.0",
        "contracts": [
            "canonical_evidence_v1",
            "canonical_knowledge_v1",
            "topic_review_workflow_v2",
        ],
        "runtime": {"kind": "pinned_component", "version": "4.0.0"},
    },
    "videotext": {
        "component_id": "videotext",
        "repository": "Yurielo/videotext",
        "commit_sha": "2e098d1705b6815628bee1e023f4742718eabf02",
        "tree_sha": "f5ec484df90e4db655d31b4174434c37f4d1491c",
        "version": "0.6.4",
        "contracts": [
            "project_schema_v7",
            "project_store_v7",
            "build_identity_0_6_4",
        ],
        "runtime": {"kind": "pinned_component", "version": "0.6.4"},
    },
}
MANIFEST_FIELDS = {
    "schema_version",
    "pipeline",
    "execution_mode",
    "project_id",
    "source_sha256",
    "status",
    "next_stage",
    "stage_order",
    "completed_stages",
    "artifacts",
    "component_identities",
    "r5_selections",
    "semantic_authority",
    "project_lease_enforced",
    "external_actions_performed",
    "source_repositories_changed",
    "protected_data_accessed",
}
VIDEO_SUFFIXES = {".m4v", ".mkv", ".mov", ".mp4", ".webm"}
SEMANTIC_STAGES = {"topics", "review", "knowledge"}


class CoreAlphaError(RuntimeError):
    """Raised when an R6 run cannot preserve its fail-closed contract."""


@dataclass(frozen=True)
class StageOutput:
    payload: bytes
    kind: str
    schema_id: str
    schema_version: str = "1.0"
    source_locator: dict[str, Any] | None = None
    semantic_status: str = "NOT_APPLICABLE"


class StageWorker(Protocol):
    def run(
        self,
        stage: str,
        capability: str,
        component: dict[str, Any],
        inputs: tuple[dict[str, Any], ...],
    ) -> StageOutput: ...


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_core_alpha_manifest(manifest: dict[str, Any]) -> None:
    """Validate the dependency-free semantic constraints of the R6 manifest."""

    if not isinstance(manifest, dict) or set(manifest) != MANIFEST_FIELDS:
        raise CoreAlphaError("Core Alpha manifest fields differ from v1")
    expected_scalars = {
        "schema_version": "1.0",
        "pipeline": "INTEGRA_CORE_ALPHA_V1",
        "execution_mode": "CONTRACT_REPLAY",
        "semantic_authority": "PROVISIONAL_ONLY",
        "project_lease_enforced": True,
        "external_actions_performed": False,
        "source_repositories_changed": False,
        "protected_data_accessed": False,
    }
    for field, expected in expected_scalars.items():
        if manifest.get(field) != expected:
            raise CoreAlphaError(f"Core Alpha manifest has invalid {field}")
    source_hash = manifest.get("source_sha256", "")
    if len(source_hash) != 64 or any(char not in "0123456789abcdef" for char in source_hash):
        raise CoreAlphaError("Core Alpha manifest has invalid source hash")
    if not str(manifest.get("project_id", "")).startswith("urn:integra:project:"):
        raise CoreAlphaError("Core Alpha manifest has invalid project ID")
    expected_project_id = derive_imported_id(
        "project", "integra", "core-alpha", source_hash
    )
    if manifest["project_id"] != expected_project_id:
        raise CoreAlphaError("Core Alpha project ID differs from source hash")
    if manifest.get("stage_order") != list(STAGE_ORDER):
        raise CoreAlphaError("Core Alpha manifest has invalid stage order")
    if manifest.get("status") not in {"IN_PROGRESS", "CANCELLED", "SUCCEEDED"}:
        raise CoreAlphaError("Core Alpha manifest has invalid status")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict) or "source" not in artifacts:
        raise CoreAlphaError("Core Alpha manifest has incomplete artifacts")
    known = ("source", *STAGE_ORDER)
    completed = [name for name in known if name in artifacts]
    if set(artifacts) != set(completed) or completed != list(known[: len(completed)]):
        raise CoreAlphaError("Core Alpha artifacts must be a contiguous known prefix")
    if manifest.get("completed_stages") != completed:
        raise CoreAlphaError("Core Alpha completed stages differ from artifacts")
    expected_next = known[len(completed)] if len(completed) < len(known) else None
    if manifest.get("next_stage") != expected_next:
        raise CoreAlphaError("Core Alpha next stage differs from completed artifacts")
    if manifest["status"] == "SUCCEEDED" and expected_next is not None:
        raise CoreAlphaError("successful Core Alpha manifest is incomplete")
    if manifest["status"] != "SUCCEEDED" and expected_next is None:
        raise CoreAlphaError("complete Core Alpha manifest must be successful")
    components = manifest.get("component_identities")
    if not isinstance(components, dict) or set(components) != {
        "integra_control_plane",
        "seminartext",
        "videotext",
    }:
        raise CoreAlphaError("Core Alpha component inventory is invalid")
    for component_id, identity in components.items():
        validate_component_identity(identity)
        if identity["component_id"] != component_id:
            raise CoreAlphaError("Core Alpha component key differs from identity")
    for component_id, expected_identity in EXPECTED_PINNED_COMPONENTS.items():
        if components[component_id] != expected_identity:
            raise CoreAlphaError(f"Core Alpha pinned component differs: {component_id}")
    selections = manifest.get("r5_selections")
    if not isinstance(selections, dict) or set(selections) != set(EXPECTED_SELECTIONS):
        raise CoreAlphaError("Core Alpha R5 selections are invalid")
    for capability, expected_primary in EXPECTED_SELECTIONS.items():
        selection = selections[capability]
        expected_selection_fields = {
            "basis",
            "challenger",
            "decision_authority",
            "fallback",
            "mode",
            "primary",
            "semantic_superiority_claimed",
        }
        if (
            not isinstance(selection, dict)
            or set(selection) != expected_selection_fields
            or tuple(selection.get("primary", [])) != expected_primary
            or selection.get("decision_authority")
            != "ISSUE_7_TECHNICAL_INTEGRATION_SELECTION"
            or selection.get("semantic_superiority_claimed") is not False
            or not isinstance(selection.get("basis"), list)
            or not selection["basis"]
            or not all(
                isinstance(selection.get(field), list)
                for field in ("challenger", "fallback", "primary")
            )
            or selection.get("mode")
            not in {"SINGLE_PRIMARY", "COMPOSED_PRIMARY"}
        ):
            raise CoreAlphaError(f"Core Alpha R5 selection is invalid: {capability}")
    if sha256_bytes(canonical_json(selections)) != EXPECTED_R5_SELECTIONS_SHA256:
        raise CoreAlphaError("Core Alpha R5 selections differ from accepted evidence")
    for stage, reference in artifacts.items():
        validate_artifact_reference(reference)
        expected_kind, expected_schema = (
            ("local_video", "local_video_v1")
            if stage == "source"
            else STAGE_OUTPUTS[stage]
        )
        if (reference["kind"], reference["schema_id"]) != (
            expected_kind,
            expected_schema,
        ):
            raise CoreAlphaError(f"Core Alpha artifact contract differs: {stage}")
        if reference["schema_version"] != "1.0":
            raise CoreAlphaError(f"Core Alpha artifact schema version differs: {stage}")
        if reference["size_bytes"] < 1:
            raise CoreAlphaError(f"Core Alpha artifact must be non-empty: {stage}")
        expected_status = (
            {"PROVISIONAL", "REVIEW_REQUIRED"}
            if stage in SEMANTIC_STAGES
            else {"NOT_APPLICABLE"}
        )
        if reference.get("semantic_status") not in expected_status:
            raise CoreAlphaError(f"Core Alpha semantic status differs: {stage}")
        expected_origin = (
            "integra_control_plane" if stage == "source" else STAGE_COMPONENTS[stage]
        )
        if reference["origin"]["component_id"] != expected_origin:
            raise CoreAlphaError(f"Core Alpha artifact origin changed: {stage}")
        if reference["origin"] != components[expected_origin]:
            raise CoreAlphaError(f"Core Alpha component provenance differs: {stage}")
        expected_parents = (
            []
            if stage == "source"
            else [artifacts[parent]["artifact_id"] for parent in STAGE_PARENTS[stage]]
        )
        if reference["provenance"]["parent_artifact_ids"] != expected_parents:
            raise CoreAlphaError(f"Core Alpha artifact lineage changed: {stage}")
        expected_operation = (
            derive_imported_id(
                "operation", "integra", "source-ingest", manifest["source_sha256"]
            )
            if stage == "source"
            else derive_imported_id(
                "operation",
                expected_origin,
                STAGE_CAPABILITIES[stage],
                sha256_bytes(
                    canonical_json(
                        [artifacts[parent]["content_sha256"] for parent in STAGE_PARENTS[stage]]
                    )
                ),
            )
        )
        if reference["provenance"]["operation_id"] != expected_operation:
            raise CoreAlphaError(f"Core Alpha operation provenance differs: {stage}")
        expected_id = derive_imported_id(
            "artifact", expected_origin, stage, reference["content_sha256"]
        )
        if reference["artifact_id"] != expected_id:
            raise CoreAlphaError(f"Core Alpha artifact identity differs: {stage}")
        if stage == "source":
            if reference["content_sha256"] != manifest["source_sha256"]:
                raise CoreAlphaError("Core Alpha source artifact hash differs")
            expected_locator = {
                "type": "content_sha256",
                "value": manifest["source_sha256"],
            }
            if reference["provenance"].get("source_locator") != expected_locator:
                raise CoreAlphaError("Core Alpha source locator differs")
        elif stage == "review":
            if "source_locator" in reference["provenance"]:
                raise CoreAlphaError("review: source locator is not part of the R6 contract")
        else:
            _validate_time_interval_locator(
                stage, reference["provenance"].get("source_locator")
            )
        project_key = manifest["project_id"].rsplit(":", 1)[-1]
        expected_suffix = "source" if stage == "source" else (
            "bin" if stage == "media_clip" else "json"
        )
        expected_path = (
            f"projects/{project_key}/artifacts/"
            f"{reference['content_sha256']}.{expected_suffix}"
        )
        if reference["storage_scope"] != "INTEGRA_STORE" or reference["relative_path"] != expected_path:
            raise CoreAlphaError(f"Core Alpha artifact storage path differs: {stage}")


def load_component_identities(root: Path) -> dict[str, dict[str, Any]]:
    manifest = json.loads(
        (root / "state/component_baselines_v1.json").read_text(encoding="utf-8")
    )
    identities: dict[str, dict[str, Any]] = {}
    for component in manifest["components"]:
        identity = {
            "component_id": component["id"],
            "repository": component["repository"],
            "commit_sha": component["commit_sha"],
            "tree_sha": component["tree_sha"],
            "version": component["version"],
            "contracts": [item["id"] for item in component["supported_contracts"]],
            "runtime": {"kind": "pinned_component", "version": component["version"]},
        }
        validate_component_identity(identity)
        identities[component["id"]] = identity
    if identities != EXPECTED_PINNED_COMPONENTS:
        raise CoreAlphaError("R1 component identities differ from the R6 pinned baseline")
    return identities


def validate_r5_selections(root: Path) -> dict[str, Any]:
    benchmark = json.loads(
        (root / "state/capability_benchmark_v1.json").read_text(encoding="utf-8")
    )
    if benchmark.get("status") != "PASS":
        raise CoreAlphaError("R5 capability benchmark is not accepted")
    selections = {item["id"]: item["selection"] for item in benchmark["capabilities"]}
    for capability, expected in EXPECTED_SELECTIONS.items():
        actual = tuple(selections.get(capability, {}).get("primary", []))
        if actual != expected:
            raise CoreAlphaError(
                f"R5 selection drift for {capability}: expected {expected}, got {actual}"
            )
    selected = {key: selections[key] for key in sorted(EXPECTED_SELECTIONS)}
    if sha256_bytes(canonical_json(selected)) != EXPECTED_R5_SELECTIONS_SHA256:
        raise CoreAlphaError("R5 selection evidence differs from the R6 pinned baseline")
    return selected


class ReplayStageWorker:
    """Dependency-free deterministic worker for contract and recovery replay.

    It does not claim model inference. Its fixture must say ``CONTRACT_REPLAY``
    and all semantic payloads remain provisional.
    """

    def __init__(self, fixture: dict[str, Any]) -> None:
        if not isinstance(fixture, dict):
            raise CoreAlphaError("replay fixture must be an object")
        if fixture.get("schema_version") != "1.0":
            raise CoreAlphaError("replay fixture schema version must be 1.0")
        if fixture.get("execution_mode") != "CONTRACT_REPLAY":
            raise CoreAlphaError("replay worker requires explicit CONTRACT_REPLAY mode")
        if fixture.get("protected_data") is not False or fixture.get("gold_labels") is not False:
            raise CoreAlphaError("replay fixture must deny protected data and Gold")
        stages = fixture.get("stages")
        if not isinstance(stages, dict) or set(stages) != set(STAGE_ORDER):
            raise CoreAlphaError("replay fixture must define every Core Alpha stage exactly")
        for stage, record in stages.items():
            if not isinstance(record, dict):
                raise CoreAlphaError(f"{stage}: replay stage must be an object")
            required = {"component_id", "capability", "kind", "schema_id", "encoding", "semantic_status", "payload"}
            if not required.issubset(record) or not all(record.get(field) for field in ("component_id", "capability", "kind", "schema_id", "encoding")):
                raise CoreAlphaError(f"{stage}: replay stage fields are incomplete")
            expected_kind, expected_schema = STAGE_OUTPUTS[stage]
            if (record.get("kind"), record.get("schema_id")) != (expected_kind, expected_schema):
                raise CoreAlphaError(f"{stage}: replay output contract differs from R6")
        self.fixture = fixture
        self.calls: list[str] = []

    @classmethod
    def from_path(cls, path: Path) -> "ReplayStageWorker":
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise CoreAlphaError(f"cannot load replay fixture: {error}") from error
        if not isinstance(payload, dict):
            raise CoreAlphaError("replay fixture must be an object")
        return cls(payload)

    def run(
        self,
        stage: str,
        capability: str,
        component: dict[str, Any],
        inputs: tuple[dict[str, Any], ...],
    ) -> StageOutput:
        self.calls.append(stage)
        record = self.fixture["stages"][stage]
        if record.get("component_id") != component["component_id"]:
            raise CoreAlphaError(f"{stage}: fixture component differs from R5 selection")
        if record.get("capability") != capability:
            raise CoreAlphaError(f"{stage}: fixture capability differs from R6 contract")
        semantic_status = record.get("semantic_status", "NOT_APPLICABLE")
        if semantic_status not in {"NOT_APPLICABLE", "PROVISIONAL", "REVIEW_REQUIRED"}:
            raise CoreAlphaError(f"{stage}: replay cannot assert semantic acceptance")
        encoding = record.get("encoding")
        if encoding == "json":
            value = {
                "input_artifact_ids": [item["artifact_id"] for item in inputs],
                "input_content_sha256": [item["content_sha256"] for item in inputs],
                "result": record.get("payload"),
                "schema_version": "1.0",
                "semantic_status": semantic_status,
                "stage": stage,
            }
            payload = canonical_json(value)
        elif encoding == "base64":
            try:
                payload = base64.b64decode(record.get("payload", ""), validate=True)
            except (binascii.Error, ValueError, TypeError) as error:
                raise CoreAlphaError(f"{stage}: invalid base64 payload") from error
        else:
            raise CoreAlphaError(f"{stage}: unsupported replay encoding")
        if not payload:
            raise CoreAlphaError(f"{stage}: empty worker output")
        return StageOutput(
            payload=payload,
            kind=record["kind"],
            schema_id=record["schema_id"],
            source_locator=record.get("source_locator"),
            semantic_status=semantic_status,
        )


def _validate_time_interval_locator(stage: str, locator: Any) -> None:
    if not isinstance(locator, dict) or set(locator) != {
        "type",
        "start_seconds",
        "end_seconds",
    }:
        raise CoreAlphaError(f"{stage}: source locator must be an exact time interval")
    start = locator.get("start_seconds")
    end = locator.get("end_seconds")
    if (
        locator.get("type") != "time_interval"
        or isinstance(start, bool)
        or isinstance(end, bool)
        or not isinstance(start, (int, float))
        or not isinstance(end, (int, float))
        or start < 0
        or end <= start
    ):
        raise CoreAlphaError(f"{stage}: source time interval is invalid")


class CoreAlphaPipeline:
    def __init__(
        self,
        *,
        repository_root: Path,
        store_root: Path,
        controller_identity: dict[str, Any],
        worker: StageWorker,
        lease_store: LeaseStore | None = None,
        writer_identity: dict[str, Any] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        validate_component_identity(controller_identity)
        self.repository_root = repository_root.resolve()
        raw_store = store_root.expanduser().absolute()
        if raw_store.is_symlink():
            raise CoreAlphaError("Core Alpha store must not be a symlink")
        self.raw_store_root = raw_store
        self.store_root = raw_store.resolve()
        if self.store_root == self.repository_root or self.repository_root in self.store_root.parents:
            raise CoreAlphaError("Core Alpha store must be outside the repository")
        self.controller = controller_identity
        self.components = load_component_identities(self.repository_root)
        self.manifest_components = {
            "integra_control_plane": self.controller,
            **self.components,
        }
        self.selections = validate_r5_selections(self.repository_root)
        self.worker = worker
        self._require_confined_store_path(self.store_root / ".leases")
        self.lease_store = lease_store or LeaseStore(self.store_root / ".leases")
        lease_root = self.lease_store.root.absolute()
        if lease_root.is_symlink() or lease_root.resolve() != (self.store_root / ".leases").resolve():
            raise CoreAlphaError("Core Alpha lease store must be inside the store")
        self.writer_identity = writer_identity or {
            "component_id": "integra_control_plane",
            "host_id": platform.node() or "local-mac",
            "process_id": os.getpid(),
            "process_start_token": f"pid-{os.getpid()}",
        }
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def run(
        self,
        source: Path,
        *,
        cancel_requested: Callable[[str], bool] | None = None,
        resume_checkpoint: Path | None = None,
    ) -> dict[str, Any]:
        source_input = source.expanduser().absolute()
        if source_input.is_symlink():
            raise CoreAlphaError("source must be a regular local file, not a symlink")
        source = source_input.resolve()
        if not source.is_file():
            raise CoreAlphaError("source must be a regular local file, not a symlink")
        if source.suffix.lower() not in VIDEO_SUFFIXES:
            raise CoreAlphaError("source must use a supported local-video extension")
        source_size = source.stat().st_size
        if source_size == 0:
            raise CoreAlphaError("source video must not be empty")
        source_hash = sha256_file(source)
        project_id = derive_imported_id("project", "integra", "core-alpha", source_hash)
        project_key = project_id.rsplit(":", 1)[-1]
        project_root = self.store_root / "projects" / project_key
        self._require_confined_store_path(project_root)
        artifacts: dict[str, dict[str, Any]] = {}

        lease = self._acquire_project_lease(project_id, source_hash)
        try:
            return self._run_with_lease(
                source,
                source_hash,
                project_id,
                project_key,
                project_root,
                artifacts,
                cancel_requested,
                resume_checkpoint,
            )
        finally:
            now = self._timestamp(self.clock())
            self.lease_store.release(
                project_id,
                project_id,
                lease["lease_id"],
                self.writer_identity,
                lease["generation"],
                now,
            )

    def _run_with_lease(
        self,
        source: Path,
        source_hash: str,
        project_id: str,
        project_key: str,
        project_root: Path,
        artifacts: dict[str, dict[str, Any]],
        cancel_requested: Callable[[str], bool] | None,
        resume_checkpoint: Path | None,
    ) -> dict[str, Any]:

        if resume_checkpoint is not None:
            resume_checkpoint = self._require_confined_store_path(
                resume_checkpoint.expanduser().absolute()
            )
            checkpoint = self._load_checkpoint(resume_checkpoint, source_hash)
            if checkpoint["project_id"] != project_id:
                raise CoreAlphaError("resume checkpoint belongs to a different project")
            artifacts = checkpoint["artifacts"]
            self._verify_retained_artifacts(artifacts, project_id)

        if "source" not in artifacts:
            source_operation = derive_imported_id(
                "operation", "integra", "source-ingest", source_hash
            )
            relative = f"projects/{project_key}/artifacts/{source_hash}.source"
            copied_size = self._copy_immutable(
                source, self.store_root / relative, source_hash
            )
            artifacts["source"] = self._artifact_reference_from_digest(
                stage="source",
                kind="local_video",
                schema_id="local_video_v1",
                digest=source_hash,
                size_bytes=copied_size,
                relative_path=relative,
                origin=self.controller,
                parents=(),
                operation_id=source_operation,
                source_locator={"type": "content_sha256", "value": source_hash},
            )

        for stage in STAGE_ORDER:
            if stage in artifacts:
                continue
            if cancel_requested and cancel_requested(stage):
                return self._write_checkpoint(
                    project_root, project_id, source_hash, artifacts, stage, "CANCELLED"
                )
            parents = tuple(artifacts[name] for name in STAGE_PARENTS[stage])
            component = self.components[STAGE_COMPONENTS[stage]]
            output = self.worker.run(stage, STAGE_CAPABILITIES[stage], component, parents)
            self._validate_stage_output(stage, output, parents)
            operation_id = derive_imported_id(
                "operation",
                component["component_id"],
                STAGE_CAPABILITIES[stage],
                sha256_bytes(
                    canonical_json(
                        [item["content_sha256"] for item in parents]
                    )
                ),
            )
            payload_hash = sha256_bytes(output.payload)
            suffix = "bin" if stage == "media_clip" else "json"
            relative = f"projects/{project_key}/artifacts/{payload_hash}.{suffix}"
            self._write_immutable(self.store_root / relative, output.payload)
            artifacts[stage] = self._artifact_reference(
                stage=stage,
                kind=output.kind,
                schema_id=output.schema_id,
                schema_version=output.schema_version,
                payload=output.payload,
                relative_path=relative,
                origin=component,
                parents=parents,
                operation_id=operation_id,
                source_locator=output.source_locator,
                semantic_status=output.semantic_status,
            )
            next_stage = self._next_stage(stage)
            if next_stage is not None:
                self._write_checkpoint(
                    project_root,
                    project_id,
                    source_hash,
                    artifacts,
                    next_stage,
                    "IN_PROGRESS",
                )

        manifest = self._manifest(project_id, source_hash, artifacts, "SUCCEEDED", None)
        self._write_mutable(project_root / "core_alpha_manifest.json", canonical_json(manifest))
        self._write_mutable(project_root / "checkpoint.json", canonical_json(manifest))
        return manifest

    def _acquire_project_lease(self, project_id: str, source_hash: str) -> dict[str, Any]:
        instant = self.clock()
        if instant.tzinfo is None:
            raise CoreAlphaError("Core Alpha clock must be timezone-aware")
        acquired_at = self._timestamp(instant)
        expires_at = self._timestamp(instant + timedelta(minutes=5))
        lease_id = derive_imported_id("lease", "integra", "core-alpha", source_hash)
        operation_id = derive_imported_id("operation", "integra", "core-alpha", source_hash)
        try:
            return self.lease_store.acquire(
                {
                    "schema_version": "1.0",
                    "lease_id": lease_id,
                    "project_id": project_id,
                    "mutable_entity": {"namespace": "project", "entity_id": project_id},
                    "writer": self.writer_identity,
                    "operation_id": operation_id,
                    "acquired_at": acquired_at,
                    "heartbeat_at": acquired_at,
                    "expires_at": expires_at,
                    "artifact_precondition": {
                        "revision_id": source_hash,
                        "content_sha256": source_hash,
                    },
                    "readers": [],
                }
            )
        except LeaseConflict as error:
            raise CoreAlphaError(f"project lease conflict: {error}") from error

    @staticmethod
    def _timestamp(value: datetime) -> str:
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    def _manifest(
        self,
        project_id: str,
        source_hash: str,
        artifacts: dict[str, dict[str, Any]],
        status: str,
        next_stage: str | None,
    ) -> dict[str, Any]:
        manifest = {
            "schema_version": "1.0",
            "pipeline": "INTEGRA_CORE_ALPHA_V1",
            "execution_mode": "CONTRACT_REPLAY",
            "project_id": project_id,
            "source_sha256": source_hash,
            "status": status,
            "next_stage": next_stage,
            "stage_order": list(STAGE_ORDER),
            "completed_stages": [name for name in ("source", *STAGE_ORDER) if name in artifacts],
            "artifacts": artifacts,
            "component_identities": self.manifest_components,
            "r5_selections": self.selections,
            "semantic_authority": "PROVISIONAL_ONLY",
            "project_lease_enforced": True,
            "external_actions_performed": False,
            "source_repositories_changed": False,
            "protected_data_accessed": False,
        }
        validate_core_alpha_manifest(manifest)
        return manifest

    def _write_checkpoint(
        self,
        project_root: Path,
        project_id: str,
        source_hash: str,
        artifacts: dict[str, dict[str, Any]],
        next_stage: str | None,
        status: str,
    ) -> dict[str, Any]:
        checkpoint = self._manifest(project_id, source_hash, artifacts, status, next_stage)
        self._write_mutable(project_root / "checkpoint.json", canonical_json(checkpoint))
        return checkpoint

    def _load_checkpoint(self, path: Path, source_hash: str) -> dict[str, Any]:
        try:
            checkpoint = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise CoreAlphaError(f"cannot load resume checkpoint: {error}") from error
        validate_core_alpha_manifest(checkpoint)
        if checkpoint.get("pipeline") != "INTEGRA_CORE_ALPHA_V1":
            raise CoreAlphaError("resume checkpoint has the wrong pipeline identity")
        if checkpoint.get("source_sha256") != source_hash:
            raise CoreAlphaError("source hash differs from resume checkpoint")
        if checkpoint.get("component_identities") != self.manifest_components:
            raise CoreAlphaError("component identity drift blocks resume")
        if checkpoint.get("r5_selections") != self.selections:
            raise CoreAlphaError("R5 selection drift blocks resume")
        if checkpoint.get("semantic_authority") != "PROVISIONAL_ONLY":
            raise CoreAlphaError("resume checkpoint has invalid semantic authority")
        artifacts = checkpoint.get("artifacts")
        if not isinstance(artifacts, dict) or "source" not in artifacts:
            raise CoreAlphaError("resume checkpoint has incomplete artifacts")
        return checkpoint

    def _verify_retained_artifacts(
        self, artifacts: dict[str, dict[str, Any]], project_id: str
    ) -> None:
        known = ("source", *STAGE_ORDER)
        completed = [name for name in known if name in artifacts]
        if completed != list(known[: len(completed)]):
            raise CoreAlphaError("resume artifacts are not a contiguous stage prefix")
        for name in completed:
            reference = artifacts[name]
            validate_artifact_reference(reference)
            expected_origin = self.controller if name == "source" else self.components[STAGE_COMPONENTS[name]]
            if reference["origin"] != expected_origin:
                raise CoreAlphaError(f"retained artifact origin changed: {name}")
            expected_parents = [] if name == "source" else [
                artifacts[parent]["artifact_id"] for parent in STAGE_PARENTS[name]
            ]
            if reference["provenance"]["parent_artifact_ids"] != expected_parents:
                raise CoreAlphaError(f"retained artifact lineage changed: {name}")
            expected_id = derive_imported_id(
                "artifact", reference["origin"]["component_id"], name, reference["content_sha256"]
            )
            if reference["artifact_id"] != expected_id:
                raise CoreAlphaError(f"retained artifact identity changed: {name}")
            project_key = project_id.rsplit(":", 1)[-1]
            expected_prefix = f"projects/{project_key}/artifacts/{reference['content_sha256']}."
            if not reference["relative_path"].startswith(expected_prefix):
                raise CoreAlphaError(f"retained artifact path changed: {name}")
            path = self._require_confined_store_path(
                self.store_root / reference["relative_path"]
            )
            if not path.is_file():
                raise CoreAlphaError(f"retained artifact is missing: {name}")
            if path.stat().st_size != reference["size_bytes"]:
                raise CoreAlphaError(f"retained artifact size changed: {name}")
            if sha256_file(path) != reference["content_sha256"]:
                raise CoreAlphaError(f"retained artifact hash changed: {name}")

    @staticmethod
    def _validate_stage_output(
        stage: str,
        output: StageOutput,
        parents: tuple[dict[str, Any], ...],
    ) -> None:
        if not isinstance(output, StageOutput):
            raise CoreAlphaError(f"{stage}: worker output must use StageOutput")
        expected_kind, expected_schema = STAGE_OUTPUTS[stage]
        if (output.kind, output.schema_id) != (expected_kind, expected_schema):
            raise CoreAlphaError(f"{stage}: worker output contract differs from R6")
        if output.schema_version != "1.0":
            raise CoreAlphaError(f"{stage}: worker schema version must be 1.0")
        if not isinstance(output.payload, bytes) or not output.payload:
            raise CoreAlphaError(f"{stage}: worker payload must be non-empty bytes")
        allowed_statuses = (
            {"PROVISIONAL", "REVIEW_REQUIRED"}
            if stage in SEMANTIC_STAGES
            else {"NOT_APPLICABLE"}
        )
        if output.semantic_status not in allowed_statuses:
            raise CoreAlphaError(f"{stage}: semantic status violates provisional authority")
        if stage == "review":
            if output.source_locator is not None:
                raise CoreAlphaError("review: source locator is not part of the R6 contract")
        else:
            _validate_time_interval_locator(stage, output.source_locator)
        if stage == "media_clip":
            return
        try:
            document = json.loads(output.payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise CoreAlphaError(f"{stage}: worker payload must be valid JSON") from error
        expected_fields = {
            "input_artifact_ids",
            "input_content_sha256",
            "result",
            "schema_version",
            "semantic_status",
            "stage",
        }
        if not isinstance(document, dict) or set(document) != expected_fields:
            raise CoreAlphaError(f"{stage}: replay payload fields differ from R6")
        if document["stage"] != stage or document["schema_version"] != "1.0":
            raise CoreAlphaError(f"{stage}: replay payload identity differs from R6")
        if document["semantic_status"] != output.semantic_status:
            raise CoreAlphaError(f"{stage}: payload semantic status differs from output")
        if document["input_artifact_ids"] != [item["artifact_id"] for item in parents]:
            raise CoreAlphaError(f"{stage}: replay payload input identity differs")
        if document["input_content_sha256"] != [item["content_sha256"] for item in parents]:
            raise CoreAlphaError(f"{stage}: replay payload input hashes differ")
        result = document["result"]
        if not isinstance(result, dict):
            raise CoreAlphaError(f"{stage}: replay result must be an object")
        expected_result_fields = {
            "transcript": {"assurance", "language", "text"},
            "topics": {"topics"},
            "review": {"exceptions", "human_decision_required", "technical_status"},
            "knowledge": {"lifecycle", "title"},
        }[stage]
        if set(result) != expected_result_fields:
            raise CoreAlphaError(f"{stage}: replay result fields differ from R6")
        if stage in SEMANTIC_STAGES:
            CoreAlphaPipeline._reject_semantic_promotion(stage, result)
        if stage == "transcript":
            if (
                result.get("assurance") != "CONTRACT_REPLAY"
                or not isinstance(result.get("language"), str)
                or not result["language"]
                or not isinstance(result.get("text"), str)
                or not result["text"]
            ):
                raise CoreAlphaError("transcript: replay assurance/result is invalid")
        if stage == "topics":
            topics = result.get("topics")
            if not isinstance(topics, list) or not topics:
                raise CoreAlphaError("topics: replay result must contain Topic drafts")
            if any(
                not isinstance(topic, dict)
                or topic.get("status") not in {"PROVISIONAL", "REVIEW_REQUIRED"}
                for topic in topics
            ):
                raise CoreAlphaError("topics: replay result asserts semantic acceptance")
        if stage == "review":
            if (
                not isinstance(result.get("exceptions"), list)
                or not isinstance(result.get("human_decision_required"), bool)
                or result.get("technical_status") not in {"PASS", "REVIEW_REQUIRED"}
            ):
                raise CoreAlphaError("review: replay result is invalid")
        if stage == "knowledge":
            if result.get("lifecycle") != output.semantic_status:
                raise CoreAlphaError("knowledge: lifecycle contradicts provisional authority")
            if not isinstance(result.get("title"), str) or not result["title"]:
                raise CoreAlphaError("knowledge: replay title must be non-empty")

    @staticmethod
    def _reject_semantic_promotion(stage: str, value: Any) -> None:
        decision_fields = {
            "decision",
            "disposition",
            "lifecycle",
            "semantic_status",
            "status",
        }
        forbidden_values = {
            "ACCEPTED",
            "APPROVED",
            "CANONICAL",
            "FINAL",
            "PUBLISHED",
            "REJECTED",
            "SUPERSEDED",
        }
        if isinstance(value, dict):
            for key, child in value.items():
                if key in decision_fields and isinstance(child, str) and child.upper() in forbidden_values:
                    raise CoreAlphaError(
                        f"{stage}: replay result asserts semantic acceptance"
                    )
                CoreAlphaPipeline._reject_semantic_promotion(stage, child)
        elif isinstance(value, list):
            for child in value:
                CoreAlphaPipeline._reject_semantic_promotion(stage, child)

    def _artifact_reference(
        self,
        *,
        stage: str,
        kind: str,
        schema_id: str,
        payload: bytes,
        relative_path: str,
        origin: dict[str, Any],
        parents: tuple[dict[str, Any], ...],
        operation_id: str,
        schema_version: str = "1.0",
        source_locator: dict[str, Any] | None = None,
        semantic_status: str = "NOT_APPLICABLE",
    ) -> dict[str, Any]:
        digest = sha256_bytes(payload)
        return self._artifact_reference_from_digest(
            stage=stage,
            kind=kind,
            schema_id=schema_id,
            digest=digest,
            size_bytes=len(payload),
            relative_path=relative_path,
            origin=origin,
            parents=parents,
            operation_id=operation_id,
            schema_version=schema_version,
            source_locator=source_locator,
            semantic_status=semantic_status,
        )

    def _artifact_reference_from_digest(
        self,
        *,
        stage: str,
        kind: str,
        schema_id: str,
        digest: str,
        size_bytes: int,
        relative_path: str,
        origin: dict[str, Any],
        parents: tuple[dict[str, Any], ...],
        operation_id: str,
        schema_version: str = "1.0",
        source_locator: dict[str, Any] | None = None,
        semantic_status: str = "NOT_APPLICABLE",
    ) -> dict[str, Any]:
        provenance: dict[str, Any] = {
            "parent_artifact_ids": [item["artifact_id"] for item in parents],
            "operation_id": operation_id,
        }
        if source_locator is not None:
            provenance["source_locator"] = source_locator
        reference = {
            "artifact_id": derive_imported_id("artifact", origin["component_id"], stage, digest),
            "kind": kind,
            "schema_id": schema_id,
            "schema_version": schema_version,
            "semantic_status": semantic_status,
            "content_sha256": digest,
            "size_bytes": size_bytes,
            "storage_scope": "INTEGRA_STORE",
            "relative_path": relative_path,
            "origin": origin,
            "provenance": provenance,
        }
        validate_artifact_reference(reference)
        return reference

    def _require_confined_store_path(self, path: Path) -> Path:
        candidate = path.absolute()
        try:
            relative = candidate.relative_to(self.store_root)
            cursor = self.store_root
        except ValueError:
            try:
                relative = candidate.relative_to(self.raw_store_root)
                cursor = self.raw_store_root
            except ValueError as error:
                raise CoreAlphaError("Core Alpha path must remain inside the store") from error
        if cursor.is_symlink():
            raise CoreAlphaError("Core Alpha store path contains a symlink")
        for part in relative.parts:
            cursor = cursor / part
            if cursor.is_symlink():
                raise CoreAlphaError("Core Alpha store path contains a symlink")
        resolved = candidate.resolve(strict=False)
        if resolved != self.store_root and self.store_root not in resolved.parents:
            raise CoreAlphaError("Core Alpha path escapes the store")
        return candidate

    def _copy_immutable(self, source: Path, target: Path, expected_hash: str) -> int:
        target = self._require_confined_store_path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if sha256_file(target) != expected_hash:
                raise CoreAlphaError("content-addressed source collision")
            return target.stat().st_size
        descriptor, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
        digest = hashlib.sha256()
        size_bytes = 0
        try:
            with source.open("rb") as input_stream, os.fdopen(descriptor, "wb") as output_stream:
                for chunk in iter(lambda: input_stream.read(1024 * 1024), b""):
                    digest.update(chunk)
                    size_bytes += len(chunk)
                    output_stream.write(chunk)
                output_stream.flush()
                os.fsync(output_stream.fileno())
            if digest.hexdigest() != expected_hash:
                raise CoreAlphaError("source changed during ingest")
            os.replace(temporary, target)
            CoreAlphaPipeline._sync_directory(target.parent)
            return size_bytes
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    @staticmethod
    def _next_stage(stage: str) -> str | None:
        index = STAGE_ORDER.index(stage) + 1
        return STAGE_ORDER[index] if index < len(STAGE_ORDER) else None

    def _write_immutable(self, path: Path, payload: bytes) -> None:
        path = self._require_confined_store_path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if path.read_bytes() != payload:
                raise CoreAlphaError("content-addressed artifact collision")
            return
        descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            CoreAlphaPipeline._sync_directory(path.parent)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def _write_mutable(self, path: Path, payload: bytes) -> None:
        path = self._require_confined_store_path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            CoreAlphaPipeline._sync_directory(path.parent)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    @staticmethod
    def _sync_directory(path: Path) -> None:
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
