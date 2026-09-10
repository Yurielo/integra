#!/usr/bin/env python3
"""Validate Integra R0 repository truth without third-party dependencies."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "state" / "integra_state_v1.json"
SCHEMA_PATH = ROOT / "schemas" / "integra_state_v1.schema.json"
BASELINES_PATH = ROOT / "state" / "component_baselines_v1.json"
BASELINES_SCHEMA_PATH = ROOT / "schemas" / "component_baselines_v1.schema.json"
OWNERSHIP_PATH = ROOT / "state" / "data_ownership_v1.json"
OWNERSHIP_SCHEMA_PATH = ROOT / "schemas" / "data_ownership_v1.schema.json"
LEASE_SCHEMA_PATH = ROOT / "schemas" / "project_lease_v1.schema.json"
WORKER_PROTOCOL_PATH = ROOT / "state" / "worker_protocol_v1.json"
WORKER_PROTOCOL_SCHEMA_PATH = ROOT / "schemas" / "worker_protocol_v1.schema.json"
ARTIFACT_REFERENCE_SCHEMA_PATH = ROOT / "schemas" / "artifact_reference_v1.schema.json"
COMPONENT_IDENTITY_SCHEMA_PATH = ROOT / "schemas" / "component_identity_v1.schema.json"

REQUIRED_DOCUMENTS = (
    "README.md",
    "AGENTS.md",
    "DEVELOPMENT_WORKFLOW.md",
    "docs/INTEGRA_PLAN.md",
    "docs/PRODUCT_DEFINITION.md",
    "docs/ROADMAP.md",
    "docs/RISK_REGISTER.md",
    "docs/ACCEPTANCE_CRITERIA.md",
    "docs/architecture/INTEGRA_ARCHITECTURE.md",
    "docs/baselines/R1_BASELINE_CERTIFICATION.md",
    "schemas/component_baselines_v1.schema.json",
    "state/component_baselines_v1.json",
    "docs/architecture/DATA_OWNERSHIP_AND_PROJECT_LEASE.md",
    "schemas/data_ownership_v1.schema.json",
    "schemas/project_lease_v1.schema.json",
    "state/data_ownership_v1.json",
    "docs/architecture/WORKER_PROTOCOL_V1.md",
    "schemas/worker_protocol_v1.schema.json",
    "schemas/artifact_reference_v1.schema.json",
    "schemas/component_identity_v1.schema.json",
    "state/worker_protocol_v1.json",
)

REQUIRED_MODULES = {
    "projects_and_sources",
    "transcript_and_topic_studio",
    "knowledge_studio",
    "media_studio",
    "marketing_studio_v1",
    "learning_studio_v1",
    "knowledge_assistant_v1",
    "publishing_hub",
    "operations_and_diagnostics",
    "compatibility_and_migration",
}

REQUIRED_SOCIAL_PLATFORMS = {
    "facebook_pages",
    "instagram",
    "threads",
    "youtube",
    "telegram",
    "whatsapp_business",
    "tiktok",
}

EXPECTED_ROADMAP_IDS = {
    "R0", "R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8A", "R8B",
    "R8C", "R9A", "R9B", "R9C", "R10", "R11", "LEARNING_V1",
    "ASSISTANT_V1", "SOCIAL_FOUNDATION", "SOCIAL_FACEBOOK",
    "SOCIAL_INSTAGRAM", "SOCIAL_THREADS", "SOCIAL_YOUTUBE",
    "SOCIAL_TELEGRAM", "SOCIAL_WHATSAPP", "SOCIAL_TIKTOK", "R12", "R13",
    "R14", "R15",
}

EXPECTED_ISSUE_NUMBERS = set(range(2, 32))


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def validate_state(state: dict, root: Path = ROOT) -> list[str]:
    errors: list[str] = []

    for relative in REQUIRED_DOCUMENTS:
        if not (root / relative).is_file():
            errors.append(f"missing required document: {relative}")

    if state.get("schema_version") != "1.0":
        errors.append("schema_version must be 1.0")
    if state.get("product") != "Integra":
        errors.append("product must be Integra")
    if state.get("standalone_products_preserved") is not True:
        errors.append("standalone_products_preserved must be true")
    if state.get("component_baseline_manifest") != "state/component_baselines_v1.json":
        errors.append("component_baseline_manifest must pin the R1 manifest")
    if state.get("data_ownership_contract") != "state/data_ownership_v1.json":
        errors.append("data_ownership_contract must pin the R2 ownership matrix")
    if state.get("project_lease_schema") != "schemas/project_lease_v1.schema.json":
        errors.append("project_lease_schema must pin the R2 lease contract")
    if state.get("worker_protocol_contract") != "state/worker_protocol_v1.json":
        errors.append("worker_protocol_contract must pin the R3 protocol registry")

    execution_policy = state.get("execution_policy", {})
    expected_policy = {
        "safe_roadmap_implementation": "AUTHORIZED_AFTER_DEPENDENCIES",
        "merge": "EXPLICIT_AUTHORITY_REQUIRED",
        "release": "EXPLICIT_AUTHORITY_REQUIRED",
        "live_external_actions": "EXPLICIT_AUTHORITY_REQUIRED",
        "protected_data": "EXPLICIT_AUTHORITY_REQUIRED",
        "semantic_acceptance": "EXPLICIT_HUMAN_DECISION_REQUIRED",
        "destructive_migration": "EXPLICIT_AUTHORITY_REQUIRED",
        "source_repository_changes": "EXPLICIT_SCOPE_REQUIRED",
    }
    if execution_policy != expected_policy:
        errors.append("execution_policy does not match the authorized boundary")

    scope = state.get("release_scope", {})
    modules = set(scope.get("required_modules", []))
    missing_modules = REQUIRED_MODULES - modules
    if missing_modules:
        errors.append(f"missing required modules: {sorted(missing_modules)}")

    platforms = set(scope.get("social_platforms", []))
    missing_platforms = REQUIRED_SOCIAL_PLATFORMS - platforms
    if missing_platforms:
        errors.append(f"missing social platforms: {sorted(missing_platforms)}")

    roadmap = state.get("roadmap")
    if not isinstance(roadmap, list):
        return errors + ["roadmap must be a list"]

    ids = [entry.get("id") for entry in roadmap]
    issues = [entry.get("issue") for entry in roadmap]
    if len(ids) != len(set(ids)):
        errors.append("roadmap IDs must be unique")
    if len(issues) != len(set(issues)):
        errors.append("roadmap issue numbers must be unique")
    if set(issues) != EXPECTED_ISSUE_NUMBERS:
        errors.append("roadmap issue numbers must cover GitHub Issues #2 through #31")

    missing_ids = EXPECTED_ROADMAP_IDS - set(ids)
    extra_ids = set(ids) - EXPECTED_ROADMAP_IDS
    if missing_ids:
        errors.append(f"missing roadmap IDs: {sorted(missing_ids)}")
    if extra_ids:
        errors.append(f"unexpected roadmap IDs: {sorted(extra_ids)}")

    positions = {entry.get("id"): index for index, entry in enumerate(roadmap)}
    statuses = {entry.get("id"): entry.get("status") for entry in roadmap}
    for accepted_id in ("R0", "R1", "R2", "R3"):
        if statuses.get(accepted_id) != "ACCEPTED":
            errors.append(f"{accepted_id} must remain ACCEPTED")
    for entry in roadmap:
        entry_id = entry.get("id")
        for dependency in entry.get("depends_on", []):
            if dependency not in positions:
                errors.append(f"{entry_id} has unknown dependency {dependency}")
            elif positions[dependency] >= positions.get(entry_id, -1):
                errors.append(f"{entry_id} dependency {dependency} must appear earlier")

    if not state.get("stop_conditions") or len(state["stop_conditions"]) < 8:
        errors.append("at least eight fail-closed stop conditions are required")

    return errors


def validate_component_baselines(manifest: dict) -> list[str]:
    errors: list[str] = []
    if manifest.get("schema_version") != "1.0":
        errors.append("component baseline schema_version must be 1.0")
    policy = manifest.get("integration_policy", {})
    if policy != {
        "source_repositories": "READ_ONLY",
        "dependency_mode": "PINNED_COMMIT_AND_VERSIONED_CONTRACT",
        "unmerged_work_allowed": False,
    }:
        errors.append("component integration policy must remain read-only and pinned")
    components = manifest.get("components", [])
    if {component.get("id") for component in components} != {"seminartext", "videotext"}:
        errors.append("component baselines must contain SeminarText and VideoText exactly")
    for component in components:
        component_id = component.get("id", "unknown")
        if component.get("default_branch") != "main":
            errors.append(f"{component_id} baseline must use main")
        for field in ("commit_sha", "tree_sha"):
            value = component.get(field, "")
            if len(value) != 40 or any(char not in "0123456789abcdef" for char in value):
                errors.append(f"{component_id} has invalid {field}")
        if component.get("source_tree_clean") is not True:
            errors.append(f"{component_id} source tree must be clean")
        if not component.get("supported_contracts"):
            errors.append(f"{component_id} must pin at least one supported contract")
        for contract in component.get("supported_contracts", []):
            digest = contract.get("sha256", "")
            if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
                errors.append(f"{component_id} contract {contract.get('id')} has invalid sha256")
    acceptance = manifest.get("r1_acceptance", {})
    if acceptance.get("manifest_reproducible") is not True:
        errors.append("R1 manifest must be reproducible")
    if acceptance.get("unmerged_work_is_dependency") is not False:
        errors.append("unmerged work must not be an R1 dependency")
    if acceptance.get("status") == "PASS" and not acceptance.get("supported_standalone_gates_pass"):
        errors.append("R1 cannot PASS unless supported standalone gates pass")
    if acceptance.get("release_promotion_performed") is not False:
        errors.append("R1 must not promote a source application release")
    return errors


def validate_data_ownership(contract: dict) -> list[str]:
    errors: list[str] = []
    if contract.get("schema_version") != "1.0":
        errors.append("data ownership schema_version must be 1.0")
    id_policy = contract.get("id_policy", {})
    if id_policy.get("derivation") != "UUIDV5_COMPONENT_NATIVE_ID_SOURCE_REVISION_SHA256":
        errors.append("imported stable IDs must use immutable UUIDv5 inputs")
    forbidden = set(id_policy.get("mutable_inputs_forbidden", []))
    if not {"display_name", "filesystem_path", "sort_order"}.issubset(forbidden):
        errors.append("mutable names, paths, and ordering must not define stable IDs")
    ownership = contract.get("ownership", [])
    patterns = [entry.get("field_pattern") for entry in ownership]
    if len(patterns) != len(set(patterns)):
        errors.append("every field pattern must have exactly one ownership entry")
    for entry in ownership:
        if not entry.get("authoritative_owner"):
            errors.append(f"missing authoritative owner for {entry.get('field_pattern')}")
        if entry.get("writer_resolution") not in {"STATIC", "PINNED_ORIGIN_OWNER"}:
            errors.append(f"invalid writer resolution for {entry.get('field_pattern')}")
    collisions = contract.get("collision_policy", {})
    if collisions.get("same_id_different_hash") != "HARD_CONFLICT":
        errors.append("same ID with a different identity hash must hard-fail")
    return errors


def validate_worker_protocol(contract: dict, root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    if contract.get("schema_version") != "1.0" or contract.get("protocol_version") != "1.0":
        errors.append("worker protocol and registry versions must be 1.0")
    if contract.get("transport") != "LOCAL_STDIO_JSONL":
        errors.append("R3 transport must remain local stdio JSONL")
    if contract.get("network_service_required") is not False:
        errors.append("R3 must not require a network service")
    if contract.get("schemas") != {
        "message": "schemas/worker_protocol_v1.schema.json",
        "artifact_reference": "schemas/artifact_reference_v1.schema.json",
        "component_identity": "schemas/component_identity_v1.schema.json",
    }:
        errors.append("R3 schema registry must pin all three accepted schemas")
    compatibility = contract.get("compatibility", {})
    expected_compatibility = {
        "negotiation": "HIGHEST_EXACT_COMMON_PROTOCOL_VERSION",
        "schema_policy": "EXACT_SCHEMA_VERSION",
        "unknown_protocol": "FAIL_CLOSED",
        "unknown_schema": "FAIL_CLOSED",
        "backward_compatible_protocol_versions": [],
    }
    if compatibility != expected_compatibility:
        errors.append("R3 compatibility policy must remain exact and fail closed")
    expected_message_types = {
        "HANDSHAKE_REQUEST", "HANDSHAKE_RESPONSE", "JOB_REQUEST", "PROGRESS",
        "RESULT", "ERROR", "CANCEL_REQUEST", "CANCEL_ACK",
    }
    if set(contract.get("message_types", [])) != expected_message_types:
        errors.append("R3 message type inventory is incomplete")
    artifact_policy = contract.get("artifact_policy", {})
    if artifact_policy.get("content_identity") != "SHA256_CANONICAL_BYTES":
        errors.append("R3 artifacts must be content-addressed by SHA-256")
    if artifact_policy.get("paths") != "NORMALIZED_RELATIVE_ONLY":
        errors.append("R3 artifact paths must be normalized and relative")
    job_policy = contract.get("job_policy", {})
    if job_policy.get("unknown_outcome_retry") != "DENIED":
        errors.append("R3 must deny automatic retry for unknown outcomes")
    if job_policy.get("mutable_write") != "VALID_PROJECT_LEASE_AND_ARTIFACT_PRECONDITION_REQUIRED":
        errors.append("R3 mutable jobs must require the accepted Project Lease")
    if contract.get("component_baseline_manifest") != "state/component_baselines_v1.json":
        errors.append("R3 worker identity must use the pinned R1 component baseline")
    fixtures = contract.get("fixtures", {})
    expected_fixtures = {"success", "cancellation", "retry", "incompatibility", "provenance"}
    if set(fixtures) != expected_fixtures:
        errors.append("R3 fixture inventory is incomplete")
    for name, fixture in fixtures.items():
        path = fixture.get("path", "")
        if not path or not (root / path).is_file():
            errors.append(f"missing R3 {name} fixture: {path}")
            continue
        try:
            loaded = load_json(root / path)
        except (OSError, json.JSONDecodeError):
            errors.append(f"invalid JSON in R3 {name} fixture: {path}")
            continue
        if loaded.get("expected") != fixture.get("expected"):
            errors.append(f"R3 {name} fixture expectation does not match registry")
    if contract.get("status") != "ACCEPTED":
        errors.append("R3 contract status must be ACCEPTED")
    return errors


def main() -> int:
    state = load_json(STATE_PATH)
    baselines = load_json(BASELINES_PATH)
    ownership = load_json(OWNERSHIP_PATH)
    worker_protocol = load_json(WORKER_PROTOCOL_PATH)
    load_json(SCHEMA_PATH)
    load_json(BASELINES_SCHEMA_PATH)
    load_json(OWNERSHIP_SCHEMA_PATH)
    load_json(LEASE_SCHEMA_PATH)
    load_json(WORKER_PROTOCOL_SCHEMA_PATH)
    load_json(ARTIFACT_REFERENCE_SCHEMA_PATH)
    load_json(COMPONENT_IDENTITY_SCHEMA_PATH)
    errors = (
        validate_state(state)
        + validate_component_baselines(baselines)
        + validate_data_ownership(ownership)
        + validate_worker_protocol(worker_protocol)
    )
    if errors:
        print("INTEGRA_GOVERNANCE_VALIDATION: FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    print("INTEGRA_GOVERNANCE_VALIDATION: PASS")
    print(f"ROADMAP_ITEMS: {len(state['roadmap'])}")
    print(f"REQUIRED_MODULES: {len(state['release_scope']['required_modules'])}")
    print(f"SOCIAL_PLATFORMS: {len(state['release_scope']['social_platforms'])}")
    print("STANDALONE_PRODUCTS_PRESERVED: YES")
    print(f"PINNED_COMPONENTS: {len(baselines['components'])}")
    print(f"R1_ACCEPTANCE: {baselines['r1_acceptance']['status']}")
    print(f"R2_OWNERSHIP_ENTRIES: {len(ownership['ownership'])}")
    print("R2_PROJECT_LEASE: DEFINED")
    print("R3_WORKER_PROTOCOL: ACCEPTED")
    print(f"R3_PROTOCOL_FIXTURES: {len(worker_protocol['fixtures'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
