"""Validation helpers for the normalized Integra capability benchmark."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


CAPABILITY_IDS = (
    "media_preparation",
    "asr",
    "alignment",
    "translation",
    "topics",
    "review_mechanics",
    "cache",
    "recovery",
    "quality_validation",
)
COMPONENT_IDS = {"seminartext", "videotext"}
PASSING_CANDIDATE_STATES = {"PASS", "LIMITED_PASS"}


class BenchmarkValidationError(ValueError):
    """Raised when benchmark evidence is incomplete or overclaims its basis."""


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_benchmark_record(record: dict[str, Any]) -> None:
    """Fail closed on incomplete, untraceable, or semantically overstated R5 evidence."""

    errors: list[str] = []
    if record.get("schema_version") != "1.0":
        errors.append("schema_version must be 1.0")
    if record.get("status") != "PASS":
        errors.append("benchmark status must be PASS")
    if record.get("source_repositories_changed") is not False:
        errors.append("source repositories must remain unchanged")
    if record.get("protected_data_accessed") is not False:
        errors.append("protected data access must remain false")
    if record.get("gold_accessed") is not False:
        errors.append("Gold access must remain false")
    if record.get("semantic_acceptance_performed") is not False:
        errors.append("R5 cannot perform semantic acceptance")

    fixture = record.get("fixture_manifest", {})
    if fixture.get("path") != "tests/fixtures/capability_benchmark_v1/manifest.json":
        errors.append("benchmark must pin the normalized fixture manifest")
    _require_hash(fixture.get("sha256"), "fixture manifest sha256", errors)
    raw_replay = record.get("raw_replay", {})
    if raw_replay.get("path") != "state/capability_benchmark_raw_v1.json":
        errors.append("benchmark must retain the raw replay record")
    _require_hash(raw_replay.get("sha256"), "raw replay sha256", errors)

    capabilities = record.get("capabilities")
    if not isinstance(capabilities, list):
        errors.append("capabilities must be a list")
        capabilities = []
    ids = [item.get("id") for item in capabilities if isinstance(item, dict)]
    if tuple(ids) != CAPABILITY_IDS:
        errors.append("capability inventory or order differs from R5")

    for capability in capabilities:
        if not isinstance(capability, dict):
            errors.append("capability entries must be objects")
            continue
        capability_id = capability.get("id", "unknown")
        assertions = capability.get("normalized_assertions")
        if not isinstance(assertions, list) or not assertions or len(assertions) != len(set(assertions)):
            errors.append(f"{capability_id}: normalized assertions must be non-empty and unique")
            assertions = []
        candidates = capability.get("candidates")
        if not isinstance(candidates, list) or {
            item.get("component_id") for item in candidates if isinstance(item, dict)
        } != COMPONENT_IDS:
            errors.append(f"{capability_id}: both pinned components must be recorded")
            candidates = []
        candidate_by_id = {
            item.get("component_id"): item for item in candidates if isinstance(item, dict)
        }
        for component_id, candidate in candidate_by_id.items():
            state = candidate.get("status")
            if state not in {"PASS", "LIMITED_PASS", "NOT_QUALIFIED"}:
                errors.append(f"{capability_id}/{component_id}: invalid candidate status")
            for field in (
                "hard_correctness",
                "provenance",
                "quality",
                "correction_burden",
                "resources",
                "reproducibility",
            ):
                if field not in candidate:
                    errors.append(f"{capability_id}/{component_id}: missing {field}")
            if state in PASSING_CANDIDATE_STATES:
                if candidate.get("hard_correctness", {}).get("status") != "PASS":
                    errors.append(f"{capability_id}/{component_id}: selected-capable candidate lacks correctness")
                if candidate.get("provenance", {}).get("status") != "PASS":
                    errors.append(f"{capability_id}/{component_id}: selected-capable candidate lacks provenance")
                if candidate.get("reproducibility", {}).get("status") != "PASS":
                    errors.append(f"{capability_id}/{component_id}: selected-capable candidate lacks reproducibility")
                runs = candidate.get("runs", [])
                if not isinstance(runs, list) or len(runs) < 2:
                    errors.append(f"{capability_id}/{component_id}: two replay runs are required")
                for run in runs:
                    _require_hash(run.get("stdout_sha256"), f"{capability_id}/{component_id} stdout", errors)
                    _require_hash(run.get("stderr_sha256"), f"{capability_id}/{component_id} stderr", errors)
                    if run.get("status") != "PASS":
                        errors.append(f"{capability_id}/{component_id}: replay run did not pass")
            if candidate.get("quality", {}).get("semantic_quality") == "PASS":
                errors.append(f"{capability_id}/{component_id}: semantic quality cannot be accepted in R5")

        selection = capability.get("selection", {})
        primary = selection.get("primary", [])
        fallback = selection.get("fallback", [])
        challenger = selection.get("challenger", [])
        selected = primary + fallback + challenger
        if not primary:
            errors.append(f"{capability_id}: at least one primary implementation is required")
        if len(selected) != len(set(selected)):
            errors.append(f"{capability_id}: selection roles must not overlap")
        for component_id in selected:
            candidate = candidate_by_id.get(component_id)
            if candidate is None or candidate.get("status") not in PASSING_CANDIDATE_STATES:
                errors.append(f"{capability_id}: {component_id} selected without passing evidence")
        if selection.get("semantic_superiority_claimed") is not False:
            errors.append(f"{capability_id}: R5 must not claim semantic superiority")
        if not selection.get("basis"):
            errors.append(f"{capability_id}: selection basis is required")

    if errors:
        raise BenchmarkValidationError("\n".join(errors))


def _require_hash(value: Any, label: str, errors: list[str]) -> None:
    if not isinstance(value, str) or len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        errors.append(f"{label} must be lowercase SHA-256")
