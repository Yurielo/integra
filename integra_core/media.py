"""Governed VideoText media recipes and derivative-output verification."""

from __future__ import annotations

import copy
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
from typing import Any

from .identity import derive_imported_id
from .operations import JobStore, ModelResidencyStore, validate_job, verify_artifacts
from .protocol import (
    canonical_json,
    content_sha256,
    validate_artifact_reference,
    validate_component_identity,
)
SHA256 = re.compile(r"^[0-9a-f]{64}$")
URN = re.compile(
    r"^urn:integra:[a-z][a-z0-9_]{1,31}:"
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
PINNED_VIDEOTEXT = {
    "component_id": "videotext",
    "repository": "Yurielo/videotext",
    "commit_sha": "2e098d1705b6815628bee1e023f4742718eabf02",
    "tree_sha": "f5ec484df90e4db655d31b4174434c37f4d1491c",
    "version": "0.6.4",
    "contracts": ["project_schema_v7", "project_store_v7", "build_identity_0_6_4"],
    "runtime": {"kind": "swift", "version": "6"},
}
PINNED_CONTRACTS = {
    "project_schema_v7": {
        "path": "Sources/videotext/Core/ArtifactModels.swift",
        "sha256": "23593caac6481f633c42c438d1d31bed06fa18a2102ad59e0d9984febe29b2af",
    },
    "project_store_v7": {
        "path": "Sources/videotext/Services/ProjectStore.swift",
        "sha256": "6e05c4bf5ea2aa0e88090ed65e52df79456e10752682e4199ec9bba09107bce1",
    },
    "build_identity_0_6_4": {
        "path": "Sources/videotext/Core/Models.swift",
        "sha256": "3a296beae82e5c5aa09aed04c1f4e43bd20f57954cc7aa8b47421b46fc96be2a",
    },
}
CAPABILITY_IMPLEMENTATIONS = {
    "clip": {
        "videotext_operations": ["cutAccurate"],
        "artifact_kind": "fragment",
        "implementations": [{"function": "cutAccurate", "path": "Sources/videotext/Adapters/MediaAdapters.swift", "sha256": "4c3d7fee2777291b297679b28b1727d8e54ed74e6d0172da58e83702570cdca5"}],
    },
    "subtitles": {
        "videotext_operations": ["burnSubtitles"],
        "artifact_kind": "subtitledVideo",
        "implementations": [{"function": "burnSubtitles", "path": "Sources/videotext/Adapters/MediaAdapters.swift", "sha256": "4c3d7fee2777291b297679b28b1727d8e54ed74e6d0172da58e83702570cdca5"}],
    },
    "translation": {
        "videotext_operations": ["translate"],
        "artifact_kind": "subtitles",
        "implementations": [{"function": "translate", "path": "Sources/videotext/Adapters/TranslationAdapter.swift", "sha256": "83e55d3cb82522cb431ee20617510b0c39f79ae0fa5309daedf5c7ff9911a577"}],
    },
    "tts": {
        "videotext_operations": ["synthesize"],
        "artifact_kind": "dubbedVideo",
        "implementations": [{"function": "synthesize", "path": "Sources/videotext/Adapters/SpeechSynthesisAdapter.swift", "sha256": "0e7eb600bd619293153d87227a6f0bda8ea506b6cb5f2ac2ead75d08324e2934"}],
    },
    "speed": {
        "videotext_operations": ["adjustSpeed"],
        "artifact_kind": "speedAdjustedVideo",
        "implementations": [{"function": "adjustSpeed", "path": "Sources/videotext/Adapters/MediaAdapters.swift", "sha256": "4c3d7fee2777291b297679b28b1727d8e54ed74e6d0172da58e83702570cdca5"}],
    },
    "blur": {
        "videotext_operations": ["applyStaticBlur"],
        "artifact_kind": "blurredVideo",
        "implementations": [{"function": "applyStaticBlur", "path": "Sources/videotext/Adapters/MediaAdapters.swift", "sha256": "4c3d7fee2777291b297679b28b1727d8e54ed74e6d0172da58e83702570cdca5"}],
    },
    "watermark": {
        "videotext_operations": ["applyWatermark"],
        "artifact_kind": "watermarkedVideo",
        "implementations": [{"function": "applyWatermark", "path": "Sources/videotext/Adapters/MediaAdapters.swift", "sha256": "4c3d7fee2777291b297679b28b1727d8e54ed74e6d0172da58e83702570cdca5"}],
    },
    "audio_enhancement": {
        "videotext_operations": ["enhance"],
        "artifact_kind": "enhancedAudio",
        "implementations": [{"function": "enhance", "path": "Sources/videotext/Adapters/AudioEnhancementAdapter.swift", "sha256": "ab525fe985a0fa1af8ba9ccf6b94e78b0095b0a240f057e8e381116acbd3d9f6"}],
    },
    "filler_mute": {
        "videotext_operations": ["analyze", "muteAudioIntervals"],
        "artifact_kind": "mutedVideo",
        "implementations": [
            {"function": "analyze", "path": "Sources/videotext/Services/FillerWordService.swift", "sha256": "b572fb34f0b91062f07f684172267799c9168b687f700c23ea756312a68c229f"},
            {"function": "muteAudioIntervals", "path": "Sources/videotext/Adapters/MediaAdapters.swift", "sha256": "4c3d7fee2777291b297679b28b1727d8e54ed74e6d0172da58e83702570cdca5"},
        ],
    },
    "qa": {
        "videotext_operations": ["strictValidationReport", "validate", "duration", "parseWithReport", "validateTimeline"],
        "artifact_kind": "reviewReport",
        "implementations": [
            {"function": "strictValidationReport", "path": "Sources/videotext/Adapters/MediaAdapters.swift", "sha256": "4c3d7fee2777291b297679b28b1727d8e54ed74e6d0172da58e83702570cdca5"},
            {"function": "validate", "path": "Sources/videotext/Adapters/MediaAdapters.swift", "sha256": "4c3d7fee2777291b297679b28b1727d8e54ed74e6d0172da58e83702570cdca5"},
            {"function": "duration", "path": "Sources/videotext/Adapters/MediaAdapters.swift", "sha256": "4c3d7fee2777291b297679b28b1727d8e54ed74e6d0172da58e83702570cdca5"},
            {"function": "parseWithReport", "path": "Sources/videotext/Services/SRTService.swift", "sha256": "417017a6a3becc395e88e2554e8d7c2dca51b09de9743e8c5c0cf81ac9ba6205"},
            {"function": "validateTimeline", "path": "Sources/videotext/Services/SRTService.swift", "sha256": "417017a6a3becc395e88e2554e8d7c2dca51b09de9743e8c5c0cf81ac9ba6205"},
        ],
    },
}
MODEL_OPERATIONS = {"translation", "tts", "audio_enhancement"}
INPUT_CONTRACTS = {
    "clip": (), "speed": (), "blur": (), "audio_enhancement": (), "qa": (),
    "subtitles": ("subtitles",),
    "translation": ("transcript",),
    "tts": ("translated_subtitles",),
    "watermark": ("watermark_image",),
    "filler_mute": ("transcript_revision", "filler_analysis"),
}
SAFE_MODEL_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,256}$")
class MediaError(RuntimeError):
    """Raised when media provenance or operational truth is incomplete."""


def create_media_recipe(
    *,
    source: dict[str, Any],
    operation_id: str,
    locator: dict[str, Any],
    steps: list[dict[str, Any]],
    created_at: str,
) -> dict[str, Any]:
    """Create a deterministic derivative-only recipe over a read-only source."""

    validate_artifact_reference(source)
    _timestamp(created_at)
    _urn(operation_id, "operation ID")
    if source["kind"] != "source_media":
        raise MediaError("media source artifact kind differs from v1")
    if source["storage_scope"] != "SOURCE_READ_ONLY":
        raise MediaError("media source must remain read-only")
    normalized_steps = []
    for sequence, requested in enumerate(copy.deepcopy(steps)):
        if not isinstance(requested, dict) or set(requested) != {"kind", "parameters", "model", "inputs"}:
            raise MediaError("media recipe step fields differ from v1")
        kind = requested["kind"]
        if kind not in CAPABILITY_IMPLEMENTATIONS:
            raise MediaError("media recipe operation is unsupported")
        binding = CAPABILITY_IMPLEMENTATIONS[kind]
        normalized_steps.append({
            "sequence": sequence,
            "kind": kind,
            "videotext_operations": copy.deepcopy(binding["videotext_operations"]),
            "videotext_artifact_kind": binding["artifact_kind"],
            "implementations": copy.deepcopy(binding["implementations"]),
            "inputs": copy.deepcopy(requested["inputs"]),
            "parameters": requested["parameters"],
            "model": requested["model"],
            "config_sha256": content_sha256({
                "inputs": requested["inputs"],
                "parameters": requested["parameters"],
                "model": requested["model"],
            }),
        })
    recipe_identity = content_sha256({
        "source_artifact_id": source["artifact_id"],
        "source_sha256": source["content_sha256"],
        "operation_id": operation_id,
        "locator": locator,
        "steps": normalized_steps,
        "component": PINNED_VIDEOTEXT,
        "created_at": created_at,
    })
    recipe = {
        "schema_version": "1.0",
        "recipe_id": derive_imported_id(
            "recipe", "videotext", source["artifact_id"], recipe_identity
        ),
        "operation_id": operation_id,
        "source": copy.deepcopy(source),
        "source_sha256": source["content_sha256"],
        "source_locator": copy.deepcopy(locator),
        "component": copy.deepcopy(PINNED_VIDEOTEXT),
        "contract_binding": copy.deepcopy(PINNED_CONTRACTS),
        "steps": normalized_steps,
        "operations_contract": {
            "capability": {"id": "videotext.media_recipe", "version": "1.0"},
            "job_class": "heavy-media",
            "workload": "FFMPEG_HEAVY",
            "resume_scope": "PIPELINE_PREFIX",
            "progress_owner": "OPERATIONS_AND_DIAGNOSTICS_V1",
            "cancellation_owner": "OPERATIONS_AND_DIAGNOSTICS_V1",
            "recovery_owner": "OPERATIONS_AND_DIAGNOSTICS_V1",
            "model_lifecycle_owner": "OPERATIONS_AND_DIAGNOSTICS_V1",
            "child_process_cleanup_owner": "OPERATIONS_AND_DIAGNOSTICS_V1",
        },
        "created_at": created_at,
        "semantic_authority": "DERIVATIVE_ONLY",
        "knowledge_truth_mutation": "DENIED",
        "recipe_sha256": "",
    }
    recipe["recipe_sha256"] = _record_hash(recipe, "recipe_sha256")
    validate_media_recipe(recipe)
    return recipe


def validate_media_recipe(recipe: dict[str, Any]) -> None:
    fields = {
        "schema_version", "recipe_id", "operation_id", "source", "source_sha256",
        "source_locator", "component", "contract_binding", "steps",
        "operations_contract", "created_at", "semantic_authority",
        "knowledge_truth_mutation", "recipe_sha256",
    }
    if not isinstance(recipe, dict) or set(recipe) != fields:
        raise MediaError("media recipe fields differ from v1")
    if recipe["schema_version"] != "1.0":
        raise MediaError("unsupported media recipe version")
    _urn(recipe["recipe_id"], "recipe ID")
    _urn(recipe["operation_id"], "operation ID")
    _timestamp(recipe["created_at"])
    validate_artifact_reference(recipe["source"])
    if recipe["source"]["kind"] != "source_media":
        raise MediaError("media source artifact kind differs from v1")
    if recipe["source"]["storage_scope"] != "SOURCE_READ_ONLY":
        raise MediaError("media source must remain read-only")
    if recipe["source_sha256"] != recipe["source"]["content_sha256"]:
        raise MediaError("media source hash differs")
    if recipe["component"] != PINNED_VIDEOTEXT:
        raise MediaError("VideoText component identity drift detected")
    validate_component_identity(recipe["component"])
    if recipe["contract_binding"] != PINNED_CONTRACTS:
        raise MediaError("VideoText contract binding drift detected")
    _validate_locator(recipe["source_locator"])
    steps = recipe["steps"]
    if not isinstance(steps, list) or len(steps) < 2:
        raise MediaError("media recipe requires a derivative operation and QA")
    kinds = [step.get("kind") for step in steps if isinstance(step, dict)]
    if len(kinds) != len(steps) or len(kinds) != len(set(kinds)):
        raise MediaError("media recipe operations must be unique")
    if kinds[-1] != "qa":
        raise MediaError("media recipe must finish with QA")
    for sequence, step in enumerate(steps):
        _validate_step(step, sequence)
    _validate_input_identities(recipe)
    model_identities: dict[str, tuple[str, str]] = {}
    for step in steps:
        model = step["model"]
        if model is None:
            continue
        identity = (model["version"], model["identity_sha256"])
        if model["id"] in model_identities and model_identities[model["id"]] != identity:
            raise MediaError("one model ID cannot have conflicting identities")
        model_identities[model["id"]] = identity
    expected_operations = {
        "capability": {"id": "videotext.media_recipe", "version": "1.0"},
        "job_class": "heavy-media", "workload": "FFMPEG_HEAVY",
        "resume_scope": "PIPELINE_PREFIX",
        "progress_owner": "OPERATIONS_AND_DIAGNOSTICS_V1",
        "cancellation_owner": "OPERATIONS_AND_DIAGNOSTICS_V1",
        "recovery_owner": "OPERATIONS_AND_DIAGNOSTICS_V1",
        "model_lifecycle_owner": "OPERATIONS_AND_DIAGNOSTICS_V1",
        "child_process_cleanup_owner": "OPERATIONS_AND_DIAGNOSTICS_V1",
    }
    if recipe["operations_contract"] != expected_operations:
        raise MediaError("media Operations contract differs")
    if recipe["semantic_authority"] != "DERIVATIVE_ONLY" or recipe["knowledge_truth_mutation"] != "DENIED":
        raise MediaError("media recipe attempts to change knowledge authority")
    if recipe["recipe_sha256"] != _record_hash(recipe, "recipe_sha256"):
        raise MediaError("media recipe hash differs")
    identity = content_sha256({
        "source_artifact_id": recipe["source"]["artifact_id"],
        "source_sha256": recipe["source_sha256"],
        "operation_id": recipe["operation_id"],
        "locator": recipe["source_locator"],
        "steps": recipe["steps"],
        "component": recipe["component"],
        "created_at": recipe["created_at"],
    })
    expected_id = derive_imported_id(
        "recipe", "videotext", recipe["source"]["artifact_id"], identity
    )
    if recipe["recipe_id"] != expected_id:
        raise MediaError("media recipe identity differs")


def media_operation_plan(
    recipe: dict[str, Any], *, capability_report: dict[str, Any],
    capability_report_reference: dict[str, Any], capability_report_payload: bytes,
    collection_id: str | None = None,
) -> dict[str, Any]:
    """Return the exact job/resource contract delegated to Operations v1."""

    validate_media_recipe(recipe)
    validate_media_capability_report(capability_report, recipe)
    _validate_capability_report_artifact(
        capability_report_reference, capability_report_payload, recipe,
    )
    if canonical_json(capability_report) + b"\n" != capability_report_payload:
        raise MediaError("capability report artifact payload differs from plan report")
    capability_report_sha256 = capability_report["report_sha256"]
    if collection_id is not None:
        _nonempty(collection_id, "playlist collection ID")
    plan = {
        "schema_version": "1.0",
        "operation_id": recipe["operation_id"],
        "recipe_id": recipe["recipe_id"],
        "recipe_sha256": recipe["recipe_sha256"],
        "capability_report": copy.deepcopy(capability_report),
        "capability_report_reference": copy.deepcopy(capability_report_reference),
        "job": {
            "job_class": "heavy-media",
            "capability_id": "videotext.media_recipe",
            "capability_version": "1.0",
            "resume_scope": "PIPELINE_PREFIX",
        },
        "resource_request": {
            "operation_id": recipe["operation_id"],
            "job_class": "heavy-media",
            "workload": "FFMPEG_HEAVY",
            "model_family": None,
            "collection_id": collection_id,
            "collection_kind": "PLAYLIST" if collection_id is not None else "SINGLE",
            "requires_publication_target": False,
            "capability_report_sha256": capability_report_sha256,
        },
        "model_bindings": sorted(
            {
                (
                    step["model"]["id"], step["model"]["version"],
                    step["model"]["identity_sha256"],
                ): copy.deepcopy(step["model"])
                for step in recipe["steps"] if step["model"] is not None
            }.values(),
            key=lambda item: (item["id"], item["version"], item["identity_sha256"]),
        ),
        "input_hashes": _recipe_input_hashes(recipe) + [
            capability_report_reference["content_sha256"]
        ],
        "stage_order": [step["kind"] for step in recipe["steps"]],
        "plan_sha256": "",
    }
    plan["plan_sha256"] = _record_hash(plan, "plan_sha256")
    return plan


def probe_media_capabilities(
    recipe: dict[str, Any], *, runtime_executable_path: Path,
    model_paths: dict[str, Path], measured_at: str,
) -> dict[str, Any]:
    """Measure the local runtime and every recipe model before execution.

    Pinned function hashes describe the accepted VideoText contract. They are
    deliberately not presented as an availability probe. Runtime and model
    availability are derived from bytes observed on the current host.
    """

    validate_media_recipe(recipe)
    _timestamp(measured_at)
    executable = Path(runtime_executable_path).resolve()
    executable_sha256 = _hash_regular_file(executable, "media probe runtime")
    arguments = ["-version"]
    try:
        outcome = subprocess.run(
            [str(executable), *arguments], capture_output=True, text=True,
            timeout=10, check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise MediaError("media probe runtime is unavailable") from error
    first_line = outcome.stdout.splitlines()[0].strip() if outcome.stdout else ""
    if outcome.returncode != 0 or not first_line.lower().startswith("ffprobe version "):
        raise MediaError("media probe runtime identity could not be measured")
    runtime_probe = {
        "id": "ffprobe",
        "version": first_line,
        "executable_sha256": executable_sha256,
        "probe_arguments_sha256": content_sha256(arguments),
    }
    bindings = _model_bindings(recipe)
    if not isinstance(model_paths, dict) or set(model_paths) != {
        _model_residency_id(model) for model in bindings
    }:
        raise MediaError("exact paths for every media model identity are required")
    measured_models = []
    for model in bindings:
        residency_id = _model_residency_id(model)
        measured_sha256 = _hash_regular_file(
            Path(model_paths[residency_id]), f"media model {model['id']}"
        )
        if measured_sha256 != model["identity_sha256"]:
            raise MediaError("measured media model differs from recipe identity")
        measured_models.append({
            **copy.deepcopy(model),
            "residency_id": residency_id,
            "status": "MEASURED_AVAILABLE",
        })
    capabilities = [
        {
            "kind": step["kind"],
            "implementations": copy.deepcopy(step["implementations"]),
            "status": "PINNED_CONTRACT",
        }
        for step in recipe["steps"]
    ]
    report = {
        "schema_version": "1.0",
        "status": "READY",
        "component": copy.deepcopy(PINNED_VIDEOTEXT),
        "capabilities": capabilities,
        "models": measured_models,
        "runtime_probe": runtime_probe,
        "runtime_probe_sha256": content_sha256(runtime_probe),
        "implementation_probe_sha256": content_sha256(capabilities),
        "measured_at": measured_at,
        "report_sha256": "",
    }
    report["report_sha256"] = _record_hash(report, "report_sha256")
    validate_media_capability_report(report, recipe)
    return report


def validate_media_capability_report(
    report: dict[str, Any], recipe: dict[str, Any]
) -> None:
    fields = {
        "schema_version", "status", "component", "capabilities", "models",
        "runtime_probe", "runtime_probe_sha256", "implementation_probe_sha256",
        "measured_at", "report_sha256",
    }
    if not isinstance(report, dict) or set(report) != fields:
        raise MediaError("media capability report fields differ from v1")
    _timestamp(report["measured_at"])
    expected_capabilities = [
        {
            "kind": step["kind"],
            "implementations": copy.deepcopy(step["implementations"]),
            "status": "PINNED_CONTRACT",
        }
        for step in recipe["steps"]
    ]
    expected_models = [
        {
            **copy.deepcopy(model),
            "residency_id": _model_residency_id(model),
            "status": "MEASURED_AVAILABLE",
        }
        for model in _model_bindings(recipe)
    ]
    runtime_probe = report["runtime_probe"]
    runtime_probe_valid = (
        isinstance(runtime_probe, dict)
        and set(runtime_probe) == {
            "id", "version", "executable_sha256", "probe_arguments_sha256"
        }
        and runtime_probe.get("id") == "ffprobe"
        and isinstance(runtime_probe.get("version"), str)
        and runtime_probe["version"].lower().startswith("ffprobe version ")
        and SHA256.fullmatch(str(runtime_probe.get("executable_sha256"))) is not None
        and SHA256.fullmatch(str(runtime_probe.get("probe_arguments_sha256"))) is not None
    )
    expected_implementation_probe = content_sha256(expected_capabilities)
    if (
        report["schema_version"] != "1.0"
        or report["status"] != "READY"
        or report["component"] != PINNED_VIDEOTEXT
        or report["capabilities"] != expected_capabilities
        or report["models"] != expected_models
        or not runtime_probe_valid
        or report["runtime_probe_sha256"] != content_sha256(runtime_probe)
        or report["implementation_probe_sha256"] != expected_implementation_probe
        or report["report_sha256"] != _record_hash(report, "report_sha256")
    ):
        raise MediaError("media capability report differs from recipe or pinned worker")


def _validate_capability_report_artifact(
    reference: dict[str, Any], payload: bytes, recipe: dict[str, Any]
) -> None:
    validate_artifact_reference(reference)
    if not isinstance(payload, bytes):
        raise MediaError("media capability report payload must be bytes")
    if (
        reference["kind"] != "capabilityReport"
        or reference["schema_id"] != "media_capability_report_v1"
        or reference["schema_version"] != "1.0"
        or reference["storage_scope"] != "INTEGRA_STORE"
        or reference["origin"] != PINNED_VIDEOTEXT
        or reference.get("semantic_status") != "NOT_APPLICABLE"
        or reference["provenance"]["operation_id"] != recipe["operation_id"]
        or recipe["recipe_id"] not in reference["provenance"]["parent_artifact_ids"]
        or reference["size_bytes"] != len(payload)
        or reference["content_sha256"] != hashlib.sha256(payload).hexdigest()
    ):
        raise MediaError("media capability report artifact is not trusted worker evidence")


def validate_media_operation_plan(
    plan: dict[str, Any], recipe: dict[str, Any]
) -> None:
    if not isinstance(plan, dict):
        raise MediaError("media operation plan must be an object")
    expected_fields = {
        "schema_version", "operation_id", "recipe_id", "recipe_sha256",
        "capability_report", "capability_report_reference", "job",
        "resource_request", "model_bindings",
        "input_hashes", "stage_order", "plan_sha256",
    }
    if set(plan) != expected_fields:
        raise MediaError("media operation plan fields differ from v1")
    collection_id = plan.get("resource_request", {}).get("collection_id")
    expected = media_operation_plan(
        recipe,
        capability_report=plan["capability_report"],
        capability_report_reference=plan["capability_report_reference"],
        capability_report_payload=canonical_json(plan["capability_report"]) + b"\n",
        collection_id=collection_id,
    )
    if plan != expected:
        raise MediaError("media operation plan differs from exact recipe execution")


def register_verified_derivative(
    recipe: dict[str, Any],
    *,
    operation_plan: dict[str, Any],
    source_root: Path,
    input_roots: dict[str, Path],
    output_root: Path,
    output_reference: dict[str, Any],
    qa_reference: dict[str, Any],
    job_store: JobStore,
    model_residency_store: ModelResidencyStore | None,
    runtime_executable_path: Path,
    model_paths: dict[str, Path],
    job_id: str,
    completed_at: str,
) -> dict[str, Any]:
    """Bind a byte-verified derivative to durable successful Operations truth."""

    validate_media_recipe(recipe)
    validate_media_operation_plan(operation_plan, recipe)
    measured_capabilities = probe_media_capabilities(
        recipe,
        runtime_executable_path=runtime_executable_path,
        model_paths=model_paths,
        measured_at=operation_plan["capability_report"]["measured_at"],
    )
    if measured_capabilities != operation_plan["capability_report"]:
        raise MediaError("media capability evidence differs from current host measurements")
    _timestamp(completed_at)
    source_root = Path(source_root)
    if source_root.is_symlink() or not source_root.is_dir():
        raise MediaError("media source root must be a real directory")
    _verify_confined_file(
        source_root, recipe["source"]["relative_path"], recipe["source"]["kind"],
        recipe["source"]["size_bytes"], recipe["source_sha256"],
    )
    external_inputs = [
        reference for step in recipe["steps"] for reference in step["inputs"]
    ] + [operation_plan["capability_report_reference"]]
    expected_input_ids = {reference["artifact_id"] for reference in external_inputs}
    if not isinstance(input_roots, dict) or set(input_roots) != expected_input_ids:
        raise MediaError("exact roots for all media input artifacts are required")
    for reference in external_inputs:
        input_root = Path(input_roots[reference["artifact_id"]])
        if input_root.is_symlink() or not input_root.is_dir():
            raise MediaError("media input artifact root must be a real directory")
        _verify_confined_file(
            input_root, reference["relative_path"], reference["kind"],
            reference["size_bytes"], reference["content_sha256"],
        )
    output_root = Path(output_root)
    if output_root.is_symlink() or not output_root.is_dir():
        raise MediaError("media artifact root must be a real directory")
    job = job_store.read(job_id)
    validate_job(job)
    completion_hashes = operation_plan["input_hashes"] + [
        output_reference.get("content_sha256"), qa_reference.get("content_sha256")
    ]
    checkpoint = job.get("checkpoint")
    checkpoint_event_bound = checkpoint is not None and any(
        event["to_state"] == "PAUSE_REQUESTED"
        and event["evidence_sha256"] == checkpoint["binding_sha256"]
        for event in job["events"][:-1]
    )
    if (
        job["operation_id"] != recipe["operation_id"]
        or job["capability"] != recipe["operations_contract"]["capability"]
        or job["job_class"] != "heavy-media"
        or job["resume_scope"] != "PIPELINE_PREFIX"
        or job["state"] != "SUCCEEDED"
        or job["terminal"] is None
        or job["terminal"]["outcome"] != "SUCCEEDED"
        or job["progress"]["fraction"] != 1.0
        or checkpoint is None
        or not checkpoint_event_bound
        or checkpoint["input_hashes"] != completion_hashes
        or checkpoint["worker_commit_sha"] != PINNED_VIDEOTEXT["commit_sha"]
        or checkpoint["capability_report_sha256"]
        != operation_plan["capability_report"]["report_sha256"]
        or checkpoint["config_sha256"] != operation_plan["plan_sha256"]
    ):
        raise MediaError("durable media job does not bind the exact plan and outputs")
    model_records = []
    model_bindings = _model_bindings(recipe)
    if model_bindings and model_residency_store is None:
        raise MediaError("media model lifecycle requires durable residency evidence")
    for model in model_bindings:
        residency_id = _model_residency_id(model)
        residency = model_residency_store.read(residency_id)
        if (
            residency["state"] != "RELEASED"
            or residency["model_id"] != residency_id
            or residency["job_id"] != job["job_id"]
            or residency["operation_id"] != recipe["operation_id"]
        ):
            raise MediaError("media model residency is not safely released by the job owner")
        model_records.append({
            "model": copy.deepcopy(model),
            "state": "RELEASED",
            "residency_sha256": content_sha256(residency),
        })
    validate_artifact_reference(output_reference)
    if output_reference["storage_scope"] != "INTEGRA_STORE":
        raise MediaError("media derivative must be in the Integra artifact store")
    if output_reference["schema_id"] != "media_derivative_v1" or output_reference["schema_version"] != "1.0":
        raise MediaError("media derivative schema binding differs")
    if output_reference["origin"] != PINNED_VIDEOTEXT:
        raise MediaError("media derivative origin differs from pinned VideoText")
    if output_reference.get("semantic_status") != "NOT_APPLICABLE":
        raise MediaError("media derivative must not claim semantic authority")
    provenance = output_reference["provenance"]
    if provenance["operation_id"] != recipe["operation_id"]:
        raise MediaError("media derivative operation differs from recipe")
    required_parents = {recipe["source"]["artifact_id"], recipe["recipe_id"]}
    if not required_parents.issubset(set(provenance["parent_artifact_ids"])):
        raise MediaError("media derivative lacks source and recipe lineage")
    expected_kind = next(
        step["videotext_artifact_kind"]
        for step in reversed(recipe["steps"])
        if step["kind"] != "qa"
    )
    if output_reference["kind"] != expected_kind:
        raise MediaError("media derivative kind differs from the final recipe operation")
    validate_artifact_reference(qa_reference)
    if (
        qa_reference["kind"] != "reviewReport"
        or qa_reference["schema_id"] != "media_qa_report_v1"
        or qa_reference["schema_version"] != "1.0"
        or qa_reference["storage_scope"] != "INTEGRA_STORE"
        or qa_reference["origin"] != PINNED_VIDEOTEXT
        or qa_reference.get("semantic_status") != "NOT_APPLICABLE"
        or qa_reference["provenance"]["operation_id"] != recipe["operation_id"]
        or not {recipe["recipe_id"], output_reference["artifact_id"]}.issubset(
            set(qa_reference["provenance"]["parent_artifact_ids"])
        )
    ):
        raise MediaError("media QA artifact provenance differs from the exact output")
    expectations = [{
        "artifact_id": output_reference["artifact_id"],
        "status": "COMPLETE",
        "reference": output_reference,
    }, {
        "artifact_id": qa_reference["artifact_id"],
        "status": "COMPLETE",
        "reference": qa_reference,
    }]
    integrity = verify_artifacts(output_root, expectations)
    if integrity != {"schema_version": "1.0", "status": "PASS", "findings": []}:
        raise MediaError("media derivative Integrity failed")
    _verify_confined_file(
        output_root, output_reference["relative_path"], output_reference["kind"],
        output_reference["size_bytes"], output_reference["content_sha256"],
    )
    qa_payload = _read_confined_file(
        output_root, qa_reference["relative_path"], qa_reference["size_bytes"],
        qa_reference["content_sha256"], maximum_size=16 * 1024 * 1024,
    )
    qa_report = _load_and_validate_qa_report(
        qa_payload, recipe=recipe, operation_plan=operation_plan,
        output_reference=output_reference, job_id=job_id,
    )
    _verify_qa_against_output(
        output_root, output_reference, qa_report,
        runtime_executable_path=runtime_executable_path,
        expected_runtime_sha256=operation_plan["capability_report"]["runtime_probe"]["executable_sha256"],
    )
    result = {
        "schema_version": "1.0",
        "derivative_id": derive_imported_id(
            "derivative", "videotext", output_reference["artifact_id"],
            content_sha256({
                "recipe_sha256": recipe["recipe_sha256"],
                "plan_sha256": operation_plan["plan_sha256"],
                "output_sha256": output_reference["content_sha256"],
                "qa_report_sha256": qa_reference["content_sha256"],
                "job_sha256": content_sha256(job),
                "completed_at": completed_at,
            }),
        ),
        "recipe_id": recipe["recipe_id"],
        "recipe_sha256": recipe["recipe_sha256"],
        "plan_sha256": operation_plan["plan_sha256"],
        "source_artifact_id": recipe["source"]["artifact_id"],
        "source_sha256": recipe["source_sha256"],
        "output": copy.deepcopy(output_reference),
        "operations_job": {
            "job_id": job["job_id"], "operation_id": job["operation_id"],
            "revision": job["revision"], "state": job["state"],
            "job_sha256": content_sha256(job),
        },
        "execution_checkpoint": {
            "checkpoint_id": checkpoint["checkpoint_id"],
            "binding_sha256": checkpoint["binding_sha256"],
            "input_hashes": copy.deepcopy(checkpoint["input_hashes"]),
            "capability_report_sha256": checkpoint["capability_report_sha256"],
            "config_sha256": checkpoint["config_sha256"],
            "worker_commit_sha": checkpoint["worker_commit_sha"],
        },
        "model_residency": model_records,
        "qa": {
            "artifact_integrity": "PASS",
            "functional_probe": "PASS",
            "reference": copy.deepcopy(qa_reference),
            "report_sha256": qa_report["report_sha256"],
            "validator_kind": qa_report["validator_kind"],
            "content_sha256": output_reference["content_sha256"],
            "size_bytes": output_reference["size_bytes"],
        },
        "completed_at": completed_at,
        "semantic_authority": "DERIVATIVE_ONLY",
        "knowledge_truth_modified": False,
        "record_sha256": "",
    }
    result["record_sha256"] = _record_hash(result, "record_sha256")
    validate_derivative_record(
        result, recipe, operation_plan, job, checkpoint, model_records, qa_reference,
        qa_report,
    )
    return result


def validate_derivative_record(
    record: dict[str, Any], recipe: dict[str, Any], operation_plan: dict[str, Any],
    job: dict[str, Any], checkpoint: dict[str, Any],
    model_records: list[dict[str, Any]], qa_reference: dict[str, Any],
    qa_report: dict[str, Any],
) -> None:
    validate_media_recipe(recipe)
    validate_media_operation_plan(operation_plan, recipe)
    validate_job(job)
    fields = {
        "schema_version", "derivative_id", "recipe_id", "recipe_sha256", "plan_sha256",
        "source_artifact_id", "source_sha256", "output", "operations_job",
        "execution_checkpoint", "model_residency", "qa", "completed_at",
        "semantic_authority", "knowledge_truth_modified",
        "record_sha256",
    }
    if not isinstance(record, dict) or set(record) != fields:
        raise MediaError("media derivative record fields differ from v1")
    _urn(record["derivative_id"], "derivative ID")
    _timestamp(record["completed_at"])
    if (
        record["schema_version"] != "1.0"
        or record["recipe_id"] != recipe["recipe_id"]
        or record["recipe_sha256"] != recipe["recipe_sha256"]
        or record["plan_sha256"] != operation_plan["plan_sha256"]
        or record["source_artifact_id"] != recipe["source"]["artifact_id"]
        or record["source_sha256"] != recipe["source_sha256"]
        or record["semantic_authority"] != "DERIVATIVE_ONLY"
        or record["knowledge_truth_modified"] is not False
    ):
        raise MediaError("media derivative binding or authority differs")
    validate_artifact_reference(record["output"])
    expected_job = {
        "job_id": job["job_id"], "operation_id": job["operation_id"],
        "revision": job["revision"], "state": job["state"],
        "job_sha256": content_sha256(job),
    }
    if record["operations_job"] != expected_job or job["state"] != "SUCCEEDED":
        raise MediaError("media derivative Operations binding differs")
    expected_checkpoint = {
        "checkpoint_id": checkpoint["checkpoint_id"],
        "binding_sha256": checkpoint["binding_sha256"],
        "input_hashes": checkpoint["input_hashes"],
        "capability_report_sha256": checkpoint["capability_report_sha256"],
        "config_sha256": checkpoint["config_sha256"],
        "worker_commit_sha": checkpoint["worker_commit_sha"],
    }
    if record["execution_checkpoint"] != expected_checkpoint:
        raise MediaError("media derivative execution checkpoint differs")
    if record["model_residency"] != model_records:
        raise MediaError("media derivative model residency binding differs")
    expected_qa = {
        "artifact_integrity": "PASS",
        "functional_probe": "PASS",
        "reference": qa_reference,
        "report_sha256": qa_report["report_sha256"],
        "validator_kind": qa_report["validator_kind"],
        "content_sha256": record["output"]["content_sha256"],
        "size_bytes": record["output"]["size_bytes"],
    }
    if record["qa"] != expected_qa:
        raise MediaError("media derivative QA differs")
    identity = content_sha256({
        "recipe_sha256": recipe["recipe_sha256"],
        "plan_sha256": operation_plan["plan_sha256"],
        "output_sha256": record["output"]["content_sha256"],
        "qa_report_sha256": qa_reference["content_sha256"],
        "job_sha256": content_sha256(job),
        "completed_at": record["completed_at"],
    })
    expected_id = derive_imported_id(
        "derivative", "videotext", record["output"]["artifact_id"], identity
    )
    if record["derivative_id"] != expected_id or record["record_sha256"] != _record_hash(record, "record_sha256"):
        raise MediaError("media derivative identity or hash differs")


def dumps_media_recipe(recipe: dict[str, Any]) -> bytes:
    validate_media_recipe(recipe)
    return canonical_json(recipe) + b"\n"


def loads_media_recipe(payload: bytes) -> dict[str, Any]:
    try:
        recipe = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise MediaError("media recipe serialization is invalid") from error
    validate_media_recipe(recipe)
    return recipe


def _validate_step(step: dict[str, Any], sequence: int) -> None:
    fields = {
        "sequence", "kind", "videotext_operations", "videotext_artifact_kind",
        "implementations", "inputs", "parameters", "model", "config_sha256",
    }
    if not isinstance(step, dict) or set(step) != fields or step["sequence"] != sequence:
        raise MediaError("media recipe step fields or sequence differ")
    kind = step["kind"]
    if kind not in CAPABILITY_IMPLEMENTATIONS:
        raise MediaError("media recipe operation is unsupported")
    expected = CAPABILITY_IMPLEMENTATIONS[kind]
    if (
        step["videotext_operations"] != expected["videotext_operations"]
        or step["videotext_artifact_kind"] != expected["artifact_kind"]
        or step["implementations"] != expected["implementations"]
        or step["config_sha256"] != content_sha256({
            "inputs": step["inputs"], "parameters": step["parameters"],
            "model": step["model"],
        })
    ):
        raise MediaError("media recipe source implementation binding differs")
    _validate_step_inputs(kind, step["inputs"])
    _validate_parameters(kind, step["parameters"])
    model = step["model"]
    if kind in MODEL_OPERATIONS:
        _validate_model(model)
    elif model is not None:
        raise MediaError("media operation contains an unexpected model binding")


def _validate_parameters(kind: str, value: Any) -> None:
    if not isinstance(value, dict):
        raise MediaError("media operation parameters must be an object")
    required: dict[str, set[str]] = {
        "clip": {"mode"},
        "subtitles": {"language", "style"},
        "translation": {"source_language", "target_language"},
        "tts": {"language", "voice_id", "voice_provider_version", "mix_mode"},
        "speed": {"factor"},
        "blur": {"region", "intensity", "start_seconds", "end_seconds"},
        "watermark": {"position", "relative_width", "margin", "opacity", "start_seconds", "end_seconds"},
        "audio_enhancement": {"profile"},
        "filler_mute": {"candidate_ids", "intervals", "fade_seconds"},
        "qa": {"checks"},
    }
    if set(value) != required[kind]:
        raise MediaError(f"{kind} parameters differ from v1")
    if kind == "clip" and value["mode"] not in {"timecode", "topic", "quote"}:
        raise MediaError("clip selection mode is invalid")
    elif kind == "subtitles":
        _nonempty(value["language"], "subtitle language")
        _validate_subtitle_style(value["style"])
    elif kind == "translation":
        _nonempty(value["source_language"], "translation source language")
        _nonempty(value["target_language"], "translation target language")
        if value["source_language"] == value["target_language"]:
            raise MediaError("translation languages must differ")
    elif kind == "tts":
        for field in ("language", "voice_id", "voice_provider_version"):
            _nonempty(value[field], f"TTS {field}")
        if value["mix_mode"] not in {"replace", "mixQuietOriginal"}:
            raise MediaError("TTS mix mode is invalid")
    elif kind == "speed":
        _number(value["factor"], "speed factor", minimum=0.5, maximum=2.0)
    elif kind == "blur":
        _validate_region(value["region"])
        _number(value["intensity"], "blur intensity", minimum=0.1, maximum=100.0)
        _optional_interval(value["start_seconds"], value["end_seconds"], "blur")
    elif kind == "watermark":
        if value["position"] not in {"topLeft", "topRight", "bottomLeft", "bottomRight", "manual"}:
            raise MediaError("watermark position is invalid")
        _number(value["relative_width"], "watermark width", minimum=0.01, maximum=1.0)
        _number(value["margin"], "watermark margin", minimum=0.0, maximum=1.0)
        _number(value["opacity"], "watermark opacity", minimum=0.0, maximum=1.0)
        _optional_interval(value["start_seconds"], value["end_seconds"], "watermark")
    elif kind == "audio_enhancement" and value["profile"] not in {"light", "normal", "strong"}:
        raise MediaError("audio enhancement profile is invalid")
    elif kind == "filler_mute":
        if not isinstance(value["candidate_ids"], list) or not value["candidate_ids"] or len(value["candidate_ids"]) != len(set(value["candidate_ids"])):
            raise MediaError("filler candidate IDs must be a non-empty unique list")
        for item in value["candidate_ids"]:
            _nonempty(item, "filler candidate ID")
        if not isinstance(value["intervals"], list) or not value["intervals"]:
            raise MediaError("filler mute intervals are required")
        for interval in value["intervals"]:
            if not isinstance(interval, dict) or set(interval) != {"start_seconds", "end_seconds"}:
                raise MediaError("filler mute interval fields differ")
            _optional_interval(interval["start_seconds"], interval["end_seconds"], "filler mute", optional=False)
        _number(value["fade_seconds"], "filler fade", minimum=0.0, maximum=1.0)
    elif kind == "qa":
        if value["checks"] != [
            "content_hash", "videotext_functional_validation",
            "output_kind_contract", "duration_or_timeline",
        ]:
            raise MediaError("media QA checks differ from v1")


def _validate_step_inputs(kind: str, inputs: Any) -> None:
    if not isinstance(inputs, list):
        raise MediaError("media step inputs must be a list")
    expected_kinds = INPUT_CONTRACTS[kind]
    if len(inputs) != len(expected_kinds):
        raise MediaError(f"{kind} requires exact content-bound input artifacts")
    actual_kinds = []
    for reference in inputs:
        validate_artifact_reference(reference)
        if reference["storage_scope"] not in {"SOURCE_READ_ONLY", "INTEGRA_STORE"}:
            raise MediaError("media step input storage scope is unsupported")
        actual_kinds.append(reference["kind"])
    if tuple(actual_kinds) != expected_kinds:
        raise MediaError(f"{kind} input artifact kinds differ from v1")


def _validate_input_identities(recipe: dict[str, Any]) -> None:
    identities = {recipe["source"]["artifact_id"]}
    for step in recipe["steps"]:
        for reference in step["inputs"]:
            artifact_id = reference["artifact_id"]
            if artifact_id in identities:
                raise MediaError("media input artifact IDs must be globally unique")
            identities.add(artifact_id)


def _model_bindings(recipe: dict[str, Any]) -> list[dict[str, Any]]:
    return sorted(
        {
            (model["id"], model["version"], model["identity_sha256"]): model
            for model in (step["model"] for step in recipe["steps"])
            if model is not None
        }.values(),
        key=lambda item: (item["id"], item["version"], item["identity_sha256"]),
    )


def _model_residency_id(model: dict[str, Any]) -> str:
    return f"media:{content_sha256(model)}"


def _recipe_input_hashes(recipe: dict[str, Any]) -> list[str]:
    hashes = [recipe["source_sha256"]]
    hashes.extend(
        reference["content_sha256"]
        for step in recipe["steps"]
        for reference in step["inputs"]
    )
    hashes.append(recipe["recipe_sha256"])
    return hashes


def _validate_locator(value: Any) -> None:
    if not isinstance(value, dict) or "type" not in value:
        raise MediaError("media source locator is incomplete")
    kind = value["type"]
    if kind == "time_interval":
        if set(value) != {"type", "start_seconds", "end_seconds"}:
            raise MediaError("time locator fields differ")
        _optional_interval(value["start_seconds"], value["end_seconds"], "source", optional=False)
    elif kind == "topic":
        if set(value) != {"type", "topic_id", "start_seconds", "end_seconds"}:
            raise MediaError("topic locator fields differ")
        _nonempty(value["topic_id"], "topic locator ID")
        _optional_interval(value["start_seconds"], value["end_seconds"], "topic", optional=False)
    elif kind == "quote":
        if set(value) != {"type", "quote_start", "quote_end", "start_seconds", "end_seconds"}:
            raise MediaError("quote locator fields differ")
        _nonempty(value["quote_start"], "quote start")
        _nonempty(value["quote_end"], "quote end")
        _optional_interval(value["start_seconds"], value["end_seconds"], "quote", optional=False)
    else:
        raise MediaError("media source locator type is unsupported")


def _validate_subtitle_style(value: Any) -> None:
    fields = {"text_color_hex", "outline_color_hex", "font_name", "font_size", "outline_width", "position", "background_opacity"}
    if not isinstance(value, dict) or set(value) != fields:
        raise MediaError("subtitle style fields differ from VideoText v7")
    for field in ("text_color_hex", "outline_color_hex"):
        if not isinstance(value[field], str) or re.fullmatch(r"#[0-9A-Fa-f]{6}", value[field]) is None:
            raise MediaError("subtitle color is invalid")
    _nonempty(value["font_name"], "subtitle font")
    _number(value["font_size"], "subtitle font size", minimum=1.0, maximum=256.0)
    _number(value["outline_width"], "subtitle outline", minimum=0.0, maximum=32.0)
    _number(value["background_opacity"], "subtitle background", minimum=0.0, maximum=1.0)
    if value["position"] not in {"bottom", "middle", "top"}:
        raise MediaError("subtitle position is invalid")


def _validate_region(value: Any) -> None:
    if not isinstance(value, dict) or set(value) != {"x", "y", "width", "height"}:
        raise MediaError("blur region fields differ")
    x = _number(value["x"], "blur x", minimum=0.0, maximum=1.0)
    y = _number(value["y"], "blur y", minimum=0.0, maximum=1.0)
    width = _number(value["width"], "blur width", minimum=0.000001, maximum=1.0)
    height = _number(value["height"], "blur height", minimum=0.000001, maximum=1.0)
    if x + width > 1.0 or y + height > 1.0:
        raise MediaError("blur region exceeds the frame")


def _validate_model(value: Any) -> None:
    if not isinstance(value, dict) or set(value) != {"id", "version", "identity_sha256"}:
        raise MediaError("media model binding is incomplete")
    if not isinstance(value["id"], str) or SAFE_MODEL_ID.fullmatch(value["id"]) is None:
        raise MediaError("model ID is not safe for durable residency")
    _nonempty(value["version"], "model version")
    _sha(value["identity_sha256"], "model identity")


def _optional_interval(start: Any, end: Any, label: str, *, optional: bool = True) -> None:
    if optional and start is None and end is None:
        return
    if start is None or end is None:
        raise MediaError(f"{label} interval must contain both bounds")
    left = _number(start, f"{label} start", minimum=0.0)
    right = _number(end, f"{label} end", minimum=0.0)
    if right <= left:
        raise MediaError(f"{label} interval must have positive duration")


def _number(value: Any, label: str, *, minimum: float, maximum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise MediaError(f"{label} must be finite")
    number = float(value)
    if number < minimum or (maximum is not None and number > maximum):
        raise MediaError(f"{label} is outside the supported range")
    return number


def _nonempty(value: Any, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise MediaError(f"{label} is required")


def _sha(value: Any, label: str) -> None:
    if not isinstance(value, str) or SHA256.fullmatch(value) is None:
        raise MediaError(f"{label} must be a lowercase SHA-256")


def _urn(value: Any, label: str) -> None:
    if not isinstance(value, str) or URN.fullmatch(value) is None:
        raise MediaError(f"{label} must be a canonical Integra URN")


def _timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise MediaError("timestamp must be RFC3339 UTC")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise MediaError("timestamp must be RFC3339 UTC") from error
    if parsed.tzinfo != timezone.utc:
        raise MediaError("timestamp must use UTC")
    return parsed


def _record_hash(value: dict[str, Any], field: str) -> str:
    payload = copy.deepcopy(value)
    payload[field] = ""
    return content_sha256(payload)


def _verify_confined_file(
    root: Path, relative_path: str, kind: str,
    expected_size: int, expected_sha256: str,
) -> None:
    """Re-hash one confined output without pretending to perform media QA."""

    parts = Path(relative_path).parts
    descriptors: list[int] = []
    try:
        current = os.open(Path(root).resolve(), os.O_RDONLY | os.O_DIRECTORY)
        descriptors.append(current)
        for part in parts[:-1]:
            current = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current)
            descriptors.append(current)
        descriptor = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=current)
        descriptors.append(descriptor)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise MediaError("media derivative is not a single-linked regular file")
        signature = _file_signature(metadata)
        digest = hashlib.sha256()
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
        if metadata.st_size != expected_size or digest.hexdigest() != expected_sha256:
            raise MediaError("media derivative changed between Integrity and registration")
        if _file_signature(os.fstat(descriptor)) != signature:
            raise MediaError("media derivative changed during registration")
    except OSError as error:
        raise MediaError("media derivative path is unsafe") from error
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _read_confined_file(
    root: Path, relative_path: str, expected_size: int, expected_sha256: str,
    *, maximum_size: int,
) -> bytes:
    if expected_size > maximum_size:
        raise MediaError("media evidence exceeds the bounded read limit")
    parts = Path(relative_path).parts
    descriptors: list[int] = []
    try:
        current = os.open(Path(root).resolve(), os.O_RDONLY | os.O_DIRECTORY)
        descriptors.append(current)
        for part in parts[:-1]:
            current = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current)
            descriptors.append(current)
        descriptor = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=current)
        descriptors.append(descriptor)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise MediaError("media evidence is not a single-linked regular file")
        signature = _file_signature(metadata)
        payload = b""
        while len(payload) <= maximum_size:
            chunk = os.read(descriptor, min(1024 * 1024, maximum_size + 1 - len(payload)))
            if not chunk:
                break
            payload += chunk
        if (
            len(payload) != expected_size
            or hashlib.sha256(payload).hexdigest() != expected_sha256
            or _file_signature(os.fstat(descriptor)) != signature
        ):
            raise MediaError("media evidence changed during registration")
        return payload
    except OSError as error:
        raise MediaError("media evidence path is unsafe") from error
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _load_and_validate_qa_report(
    payload: bytes, *, recipe: dict[str, Any], operation_plan: dict[str, Any],
    output_reference: dict[str, Any], job_id: str,
) -> dict[str, Any]:
    try:
        report = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise MediaError("media QA report is not valid JSON") from error
    fields = {
        "schema_version", "status", "validator_kind", "validator_implementations",
        "job_id", "operation_id", "recipe_id", "recipe_sha256", "plan_sha256",
        "output_artifact_id", "output_kind", "output_sha256", "output_size_bytes",
        "expected_duration_seconds", "measured_duration_seconds", "streams",
        "cue_count", "timeline_findings", "probe_payload", "probe_sha256",
        "report_sha256",
    }
    if not isinstance(report, dict) or set(report) != fields:
        raise MediaError("media QA report fields differ from v1")
    probe_payload = report["probe_payload"]
    if not isinstance(probe_payload, str) or not probe_payload:
        raise MediaError("media QA report lacks worker probe evidence")
    if report["probe_sha256"] != hashlib.sha256(probe_payload.encode()).hexdigest():
        raise MediaError("media QA worker probe hash differs")
    qa_implementations = CAPABILITY_IMPLEMENTATIONS["qa"]["implementations"]
    if output_reference["kind"] == "subtitles":
        validator_kind = "VIDEOTEXT_SRT_TIMELINE"
        implementations = qa_implementations[3:]
        variant_valid = (
            report["expected_duration_seconds"] is None
            and report["measured_duration_seconds"] is None
            and report["streams"] == []
            and isinstance(report["cue_count"], int)
            and not isinstance(report["cue_count"], bool)
            and report["cue_count"] > 0
            and report["timeline_findings"] == []
            and _srt_probe_matches(report)
        )
    elif output_reference["kind"] == "enhancedAudio":
        validator_kind = "VIDEOTEXT_AUDIO_PROBE"
        implementations = qa_implementations[1:3]
        variant_valid = _media_probe_facts_valid(
            report, required_stream="audio", strict_video=False
        )
    else:
        validator_kind = "VIDEOTEXT_STRICT_VIDEO"
        implementations = qa_implementations[:1]
        variant_valid = _media_probe_facts_valid(
            report, required_stream="video", strict_video=True
        )
    if (
        report["schema_version"] != "1.0"
        or report["status"] != "PASS"
        or report["validator_kind"] != validator_kind
        or report["validator_implementations"] != implementations
        or report["job_id"] != job_id
        or report["operation_id"] != recipe["operation_id"]
        or report["recipe_id"] != recipe["recipe_id"]
        or report["recipe_sha256"] != recipe["recipe_sha256"]
        or report["plan_sha256"] != operation_plan["plan_sha256"]
        or report["output_artifact_id"] != output_reference["artifact_id"]
        or report["output_kind"] != output_reference["kind"]
        or report["output_sha256"] != output_reference["content_sha256"]
        or report["output_size_bytes"] != output_reference["size_bytes"]
        or not variant_valid
        or report["report_sha256"] != _record_hash(report, "report_sha256")
    ):
        raise MediaError("media functional QA is not bound to the exact execution output")
    return report


def _verify_qa_against_output(
    output_root: Path, output_reference: dict[str, Any], report: dict[str, Any],
    *, runtime_executable_path: Path, expected_runtime_sha256: str,
) -> None:
    """Independently inspect output bytes instead of trusting report text."""

    output_path = (Path(output_root).resolve() / output_reference["relative_path"]).resolve()
    try:
        output_path.relative_to(Path(output_root).resolve())
    except ValueError as error:
        raise MediaError("media QA output escaped the artifact store") from error
    if output_reference["kind"] == "subtitles":
        payload = _read_confined_file(
            output_root, output_reference["relative_path"],
            output_reference["size_bytes"], output_reference["content_sha256"],
            maximum_size=16 * 1024 * 1024,
        )
        cue_count, findings = _inspect_srt(payload)
        if cue_count != report["cue_count"] or findings != report["timeline_findings"]:
            raise MediaError("media QA report differs from independently parsed subtitles")
        return

    executable = Path(runtime_executable_path).resolve()
    if _hash_regular_file(executable, "media QA runtime") != expected_runtime_sha256:
        raise MediaError("media QA runtime changed after capability preflight")
    try:
        outcome = subprocess.run(
            [
                str(executable), "-v", "error", "-show_entries",
                "stream=codec_type:format=duration", "-of",
                "default=noprint_wrappers=1", str(output_path),
            ],
            capture_output=True, text=True, timeout=30, check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise MediaError("media output could not be independently inspected") from error
    if outcome.returncode != 0:
        raise MediaError("media output failed independent ffprobe validation")
    streams = list(dict.fromkeys(re.findall(
        r"(?m)^codec_type=(audio|video)\s*$", outcome.stdout
    )))
    durations = [
        float(value) for value in re.findall(
            r"(?m)^duration=([0-9]+(?:\.[0-9]+)?)\s*$", outcome.stdout
        )
    ]
    measured = durations[-1] if durations else None
    required_stream = "audio" if output_reference["kind"] == "enhancedAudio" else "video"
    if (
        required_stream not in streams
        or measured is None
        or not math.isfinite(measured)
        or measured <= 0
        or report["streams"] != streams
        or not isinstance(report["measured_duration_seconds"], (int, float))
        or isinstance(report["measured_duration_seconds"], bool)
        or abs(float(report["measured_duration_seconds"]) - measured) > 0.001
    ):
        raise MediaError("media QA report differs from independent ffprobe facts")


def _inspect_srt(payload: bytes) -> tuple[int, list[str]]:
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise MediaError("subtitle output is not UTF-8 SRT") from error
    timing = re.compile(
        r"^(\d{2}):(\d{2}):(\d{2}),(\d{3}) --> "
        r"(\d{2}):(\d{2}):(\d{2}),(\d{3})$"
    )
    intervals: list[tuple[int, int]] = []
    blocks = [block for block in re.split(r"\r?\n\r?\n", text.strip()) if block.strip()]
    for expected_index, block in enumerate(blocks, start=1):
        lines = block.splitlines()
        if len(lines) < 3 or lines[0].strip() != str(expected_index):
            raise MediaError("subtitle output failed independent SRT structure validation")
        match = timing.fullmatch(lines[1].strip())
        if match is None or not any(line.strip() for line in lines[2:]):
            raise MediaError("subtitle output failed independent SRT timeline validation")
        values = [int(value) for value in match.groups()]
        start = (((values[0] * 60 + values[1]) * 60 + values[2]) * 1000 + values[3])
        end = (((values[4] * 60 + values[5]) * 60 + values[6]) * 1000 + values[7])
        if end <= start or (intervals and start < intervals[-1][1]):
            raise MediaError("subtitle output has a non-monotonic SRT timeline")
        intervals.append((start, end))
    if not intervals:
        raise MediaError("subtitle output contains no SRT cues")
    return len(intervals), []


def _hash_regular_file(path: Path, label: str) -> str:
    path = Path(path)
    descriptor: int | None = None
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise MediaError(f"{label} is not a regular file")
        digest = hashlib.sha256()
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
        return digest.hexdigest()
    except OSError as error:
        raise MediaError(f"{label} file is unavailable") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _media_probe_facts_valid(
    report: dict[str, Any], *, required_stream: str, strict_video: bool
) -> bool:
    expected = report["expected_duration_seconds"]
    measured = report["measured_duration_seconds"]
    probe = report["probe_payload"]
    stream_matches = re.findall(r"(?m)^codec_type=(audio|video)\s*$", probe)
    streams = list(dict.fromkeys(stream_matches))
    duration_matches = []
    for value in re.findall(r"(?m)^duration=([0-9]+(?:\.[0-9]+)?)\s*$", probe):
        try:
            duration_matches.append(float(value))
        except ValueError:
            return False
    expected_prefix = (
        f"Ожидаемая длительность: {expected:.3f}\n" if isinstance(expected, (int, float)) else ""
    )
    return (
        isinstance(expected, (int, float)) and not isinstance(expected, bool)
        and isinstance(measured, (int, float)) and not isinstance(measured, bool)
        and math.isfinite(expected) and math.isfinite(measured)
        and expected > 0 and measured > 0 and abs(expected - measured) <= 0.25
        and report["streams"] == streams and required_stream in streams
        and any(abs(measured - value) <= 0.001 for value in duration_matches)
        and (not strict_video or probe.startswith(expected_prefix))
        and report["cue_count"] is None and report["timeline_findings"] == []
    )


def _srt_probe_matches(report: dict[str, Any]) -> bool:
    try:
        probe = json.loads(report["probe_payload"])
    except json.JSONDecodeError:
        return False
    return (
        isinstance(probe, dict)
        and set(probe) == {"cue_count", "parse_errors", "timeline_findings"}
        and probe["cue_count"] == report["cue_count"]
        and probe["parse_errors"] == []
        and probe["timeline_findings"] == report["timeline_findings"]
        and canonical_json(probe).decode() == report["probe_payload"]
    )


def _file_signature(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev, metadata.st_ino, metadata.st_mode, metadata.st_nlink,
        metadata.st_size, metadata.st_mtime_ns, metadata.st_ctime_ns,
    )
