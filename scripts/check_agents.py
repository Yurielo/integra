#!/usr/bin/env python3
"""Validate the governed Integra Codex agent registrations and contracts."""

from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "state" / "agent_team_v1.json"

PERMANENT_ROLES = {
    "product-owner": "LEAD_READ_ONLY",
    "backend-developer": "IMPLEMENTATION",
    "frontend-developer": "IMPLEMENTATION",
    "database-architect": "DESIGN_AND_IMPLEMENTATION",
    "qa-test-engineer": "TEST_IMPLEMENTATION",
    "ci-cd-engineer": "IMPLEMENTATION",
}

ON_DEMAND_ROLES = {
    "system-architect": "ON_DEMAND_ADVISORY",
    "github-pr-reviewer": "ON_DEMAND_REVIEW",
    "jira-sprint-planner": "ON_DEMAND_PLANNING",
    "confluence-doc-writer": "ON_DEMAND_DOCUMENTATION",
}

EXPECTED_ROLE_MODES = {
    **PERMANENT_ROLES,
    **ON_DEMAND_ROLES,
}

REQUIRED_COVERAGE = {
    "delivery_coordination_and_acceptance": ("product-owner", "PERMANENT"),
    "control_plane_and_worker_implementation": ("backend-developer", "PERMANENT"),
    "native_macos_ui_implementation": ("frontend-developer", "PERMANENT"),
    "persisted_state_and_artifact_contracts": ("database-architect", "PERMANENT"),
    "independent_quality_and_regression_evidence": ("qa-test-engineer", "PERMANENT"),
    "build_runtime_identity_and_ci_evidence": ("ci-cd-engineer", "PERMANENT"),
    "cross_module_architecture_and_nfr_advice": ("system-architect", "ON_DEMAND"),
    "independent_material_diff_review": ("github-pr-reviewer", "ON_DEMAND"),
    "roadmap_and_dependency_planning": ("jira-sprint-planner", "ON_DEMAND"),
    "repository_documentation_from_verified_evidence": (
        "confluence-doc-writer",
        "ON_DEMAND",
    ),
}

EXPECTED_ROLES = set(EXPECTED_ROLE_MODES)

EXPECTED_HANDOFF_FIELDS = {
    "authority",
    "outcome",
    "acceptance_criteria",
    "scope",
    "forbidden_actions",
    "write_owner",
    "evidence",
    "tests",
    "risks",
    "next_boundary",
}

FORBIDDEN_LEGACY_TERMS = ("StarTalk", "RUS-", "ruscord-architect")


def load_registry(path: Path = REGISTRY_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_agent_team(registry: dict, root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    expected_top_level = {
        "schema_version",
        "status",
        "lead_agent",
        "human_product_owner_authority",
        "activation_policy",
        "execution_policy",
        "default_systems",
        "responsibility_coverage",
        "roles",
        "handoff_required_fields",
        "safeguards",
    }
    if set(registry) != expected_top_level:
        errors.append("agent registry top-level fields must match the v1 contract")
    if registry.get("schema_version") != "1.0":
        errors.append("agent team schema_version must be 1.0")
    if registry.get("status") != "PRODUCT_OWNER_AUTHORIZED":
        errors.append("agent team status must be PRODUCT_OWNER_AUTHORIZED")
    if registry.get("lead_agent") != "product-owner":
        errors.append("product-owner must remain the lead agent")
    if registry.get("human_product_owner_authority") != "RETAINED_FOR_GENUINE_GATES":
        errors.append("human Product Owner authority must remain explicit")
    if registry.get("activation_policy") != "RISK_BASED_MINIMAL_SET":
        errors.append("agent activation must remain risk-based and minimal")
    if registry.get("execution_policy") != "AUTONOMOUS_UNTIL_GENUINE_HUMAN_GATE":
        errors.append("agent execution must remain autonomous until a genuine gate")

    roles = registry.get("roles", [])
    role_ids = [role.get("id") for role in roles]
    if len(role_ids) != len(set(role_ids)):
        errors.append("agent role IDs must be unique")
    if set(role_ids) != EXPECTED_ROLES:
        errors.append("agent role inventory must match the accepted current role model")

    for role in roles:
        role_id = role.get("id", "unknown")
        if set(role) != {"id", "mode", "registration", "contract"}:
            errors.append(f"role fields must match the v1 contract for {role_id}")
        if role.get("mode") != EXPECTED_ROLE_MODES.get(role_id):
            errors.append(f"role mode mismatch for {role_id}")
        registration_relative = role.get("registration", "")
        contract_relative = role.get("contract", "")
        expected_registration = f".codex/agents/{role_id}.toml"
        expected_contract = f".codex/agents/{role_id}.md"
        if registration_relative != expected_registration:
            errors.append(f"registration path mismatch for {role_id}")
            continue
        if contract_relative != expected_contract:
            errors.append(f"contract path mismatch for {role_id}")
            continue
        registration = root / registration_relative
        contract = root / contract_relative
        if not registration.is_file():
            errors.append(f"missing agent registration: {registration.relative_to(root)}")
            continue
        if not contract.is_file():
            errors.append(f"missing agent contract: {contract.relative_to(root)}")
            continue
        try:
            parsed = tomllib.loads(registration.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as exc:
            errors.append(f"invalid TOML for {role_id}: {exc}")
            continue
        if parsed.get("name") != role_id:
            errors.append(f"registration name mismatch for {role_id}")
        if not parsed.get("description") or not parsed.get("developer_instructions"):
            errors.append(f"registration fields incomplete for {role_id}")
        text = registration.read_text(encoding="utf-8") + contract.read_text(encoding="utf-8")
        for term in FORBIDDEN_LEGACY_TERMS:
            if term in text:
                errors.append(f"{role_id} retains legacy term: {term}")
        if role_id in {"product-owner", "system-architect", "github-pr-reviewer"} and parsed.get("sandbox_mode") != "read-only":
            errors.append(f"{role_id} must remain read-only")

    coverage = registry.get("responsibility_coverage", [])
    coverage_ids = [item.get("responsibility") for item in coverage]
    if len(coverage_ids) != len(set(coverage_ids)):
        errors.append("responsibility coverage IDs must be unique")
    coverage_by_id = {item.get("responsibility"): item for item in coverage}
    if set(coverage_by_id) != set(REQUIRED_COVERAGE):
        errors.append("responsibility coverage must match the accepted current model")
    for responsibility, (owner, activation) in REQUIRED_COVERAGE.items():
        item = coverage_by_id.get(responsibility, {})
        if item.get("owner") != owner or item.get("activation") != activation:
            errors.append(f"responsibility coverage mismatch for {responsibility}")
        if owner not in role_ids:
            errors.append(f"responsibility owner is not registered: {responsibility}")

    defaults = registry.get("default_systems", {})
    expected_defaults = {
        "planning": "GITHUB_ISSUES_AND_MILESTONES",
        "documentation": "REPOSITORY_MARKDOWN",
        "jira": "EXPLICIT_EXTERNAL_SCOPE_REQUIRED",
        "confluence": "EXPLICIT_EXTERNAL_SCOPE_REQUIRED",
    }
    if defaults != expected_defaults:
        errors.append("default systems differ from the governed v1 contract")
    handoff_fields = registry.get("handoff_required_fields", [])
    if len(handoff_fields) != len(set(handoff_fields)) or set(handoff_fields) != EXPECTED_HANDOFF_FIELDS:
        errors.append("handoff fields must match the governed v1 contract")
    safeguards = registry.get("safeguards", {})
    expected_safeguards = {
        "all_roles_required_for_every_task": False,
        "routine_human_dispatch_required": False,
        "human_product_owner_may_be_impersonated": False,
        "source_repositories_read_only_by_default": True,
        "external_system_access_inferred_from_role_name": False,
        "qa_and_pr_review_independent": True,
    }
    if safeguards != expected_safeguards:
        errors.append("agent safeguards differ from the authorized operating model")
    return errors


def main() -> int:
    errors = validate_agent_team(load_registry())
    if errors:
        print("INTEGRA_AGENT_TEAM_VALIDATION: FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    print("INTEGRA_AGENT_TEAM_VALIDATION: PASS")
    print("LEAD_AGENT: product-owner")
    print(f"PERMANENT_AGENT_ROLES: {len(PERMANENT_ROLES)}")
    print(f"ON_DEMAND_AGENT_ROLES: {len(ON_DEMAND_ROLES)}")
    print(f"RESPONSIBILITY_COVERAGE: {len(REQUIRED_COVERAGE)}")
    print("ACTIVATION_POLICY: RISK_BASED_MINIMAL_SET")
    print("HUMAN_PRODUCT_OWNER_AUTHORITY: RETAINED_FOR_GENUINE_GATES")
    print("ROUTINE_HUMAN_DISPATCH_REQUIRED: NO")
    return 0


if __name__ == "__main__":
    sys.exit(main())
