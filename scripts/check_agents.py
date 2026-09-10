#!/usr/bin/env python3
"""Validate the governed Integra Codex agent registrations and contracts."""

from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "state" / "agent_team_v1.json"

EXPECTED_ROLES = {
    "product-owner",
    "backend-developer",
    "frontend-developer",
    "database-architect",
    "qa-test-engineer",
    "ci-cd-engineer",
    "github-pr-reviewer",
    "jira-sprint-planner",
    "confluence-doc-writer",
}

EXPECTED_MODES = {
    "product-owner": "LEAD_READ_ONLY",
    "backend-developer": "IMPLEMENTATION",
    "frontend-developer": "IMPLEMENTATION",
    "database-architect": "DESIGN_AND_IMPLEMENTATION",
    "qa-test-engineer": "TEST_IMPLEMENTATION",
    "ci-cd-engineer": "IMPLEMENTATION",
    "github-pr-reviewer": "READ_ONLY",
    "jira-sprint-planner": "PLANNING",
    "confluence-doc-writer": "DOCUMENTATION",
}

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
        errors.append("agent role inventory must contain exactly the nine governed roles")

    for role in roles:
        role_id = role.get("id", "unknown")
        if set(role) != {"id", "mode", "registration", "contract"}:
            errors.append(f"role fields must match the v1 contract for {role_id}")
        if role.get("mode") != EXPECTED_MODES.get(role_id):
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
        if role_id in {"product-owner", "github-pr-reviewer"} and parsed.get("sandbox_mode") != "read-only":
            errors.append(f"{role_id} must remain read-only")

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
    print("AGENT_ROLES: 9")
    print("ACTIVATION_POLICY: RISK_BASED_MINIMAL_SET")
    print("HUMAN_PRODUCT_OWNER_AUTHORITY: RETAINED_FOR_GENUINE_GATES")
    print("ROUTINE_HUMAN_DISPATCH_REQUIRED: NO")
    return 0


if __name__ == "__main__":
    sys.exit(main())
