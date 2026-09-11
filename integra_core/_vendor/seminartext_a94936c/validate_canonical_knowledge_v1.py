#!/usr/bin/env python3
"""Layered validator for Canonical Knowledge Contract v1.

Layer 1 delegates structural truth to the committed JSON Schema. Layers 2-4
add invariants that JSON Schema cannot express cleanly: field mechanics,
cross-record references, and lifecycle/review semantics.
"""
from __future__ import annotations

import argparse
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

try:
    from jsonschema import Draft202012Validator
except ModuleNotFoundError:  # Truthful fail-closed behavior outside dev_test.
    Draft202012Validator = None  # type: ignore[assignment,misc]


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = Path(__file__).with_name("canonical_knowledge_v1.schema.json")
LIFECYCLE_PATH = Path(__file__).with_name("canonical_knowledge_lifecycle_v1.json")
ID_RE = re.compile(r"^[a-z][a-z0-9._:-]{2,127}$")
RELATIONS = {"supports", "contradicts", "refines", "depends_on", "associated_with"}
COLLECTIONS = ("seminars", "topics", "concepts", "relations", "review_decisions")
ENTITY_COLLECTIONS = ("seminars", "topics", "concepts", "relations")


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _schema_validator():
    if Draft202012Validator is None:
        return None
    schema = _load_json(SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


@lru_cache(maxsize=1)
def _lifecycle_contract() -> dict[str, Any]:
    return _load_json(LIFECYCLE_PATH)


def _id(value: Any) -> bool:
    return isinstance(value, str) and ID_RE.fullmatch(value) is not None


def _path_forbidden(value: str) -> bool:
    return (
        value.startswith(("/", "~", "\\"))
        or bool(re.match(r"^[A-Za-z]:[\\/]", value))
        or any(marker in value for marker in ("/Users/", "/home/", "file://", "vscode://"))
    )


def _walk_strings(value: Any, path: str = "$"):
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for key, child in value.items():
            yield from _walk_strings(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk_strings(child, f"{path}[{index}]")


def _layer1_structure(document: Any) -> list[str]:
    validator = _schema_validator()
    if validator is None:
        return [
            "L1_SCHEMA $.dependency: jsonschema is required for authoritative "
            "Canonical Knowledge structural validation; install the supported dev_test profile"
        ]
    errors = sorted(validator.iter_errors(document), key=lambda error: (error.json_path, error.message))
    return [f"L1_SCHEMA {error.json_path}: {error.message}" for error in errors]


def _check_refs(errors: list[str], values: list[str], path: str, available: set[str]) -> None:
    for index, value in enumerate(values):
        if value not in available:
            errors.append(f"L3_REFERENCE {path}[{index}]: dangling reference {value}")


def _records(document: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    return {name: document[name] for name in COLLECTIONS}


def _layer2_field_invariants(document: dict[str, Any], records: dict[str, list[dict[str, Any]]]) -> list[str]:
    errors: list[str] = []

    for path, value in _walk_strings(document):
        if _path_forbidden(value):
            errors.append(f"L2_FIELD {path}: absolute or machine-specific path is forbidden")

    all_ids = [document["project"]["id"]]
    all_ids.extend(item["id"] for name in COLLECTIONS for item in records[name])
    for duplicate in sorted({item_id for item_id in all_ids if all_ids.count(item_id) > 1}):
        errors.append(f"L2_FIELD $: duplicate stable id {duplicate}")

    registry_ids = [entry["id"] for entry in document["relation_type_registry"]]
    if set(registry_ids) != RELATIONS or len(registry_ids) != len(RELATIONS):
        errors.append("L2_FIELD $.relation_type_registry: must contain exactly the controlled relation registry")

    for index, topic in enumerate(records["topics"]):
        source_scope = topic["source_scope"]
        if "order_start" in source_scope and "order_end" in source_scope:
            if source_scope["order_end"] < source_scope["order_start"]:
                errors.append(f"L2_FIELD $.topics[{index}].source_scope: order_end precedes order_start")
        temporal_scope = topic.get("temporal_scope")
        if temporal_scope and "start_seconds" in temporal_scope and "end_seconds" in temporal_scope:
            if temporal_scope["end_seconds"] <= temporal_scope["start_seconds"]:
                errors.append(f"L2_FIELD $.topics[{index}].temporal_scope: end_seconds must follow start_seconds")

    for index, decision in enumerate(records["review_decisions"]):
        path = f"$.review_decisions[{index}]"
        if decision["output_version"] < decision["input_version"]:
            errors.append(f"L2_FIELD {path}: output_version cannot precede input_version")
        action = decision["action"]
        if action == "RENAME" and decision["target_ids"] != decision["result_ids"]:
            errors.append(f"L2_FIELD {path}: RENAME must preserve identity")
        if action == "SPLIT" and len(decision["result_ids"]) < 2:
            errors.append(f"L2_FIELD {path}: SPLIT requires at least two result IDs")
        if action == "MERGE" and len(decision["target_ids"]) < 2:
            errors.append(f"L2_FIELD {path}: MERGE requires at least two target IDs")

    return errors


def _layer3_reference_integrity(
    document: dict[str, Any],
    records: dict[str, list[dict[str, Any]]],
    evidence_bundle: dict[str, Any] | None,
    source_slice: dict[str, Any] | None,
) -> list[str]:
    errors: list[str] = []
    project_id = document["project"]["id"]
    seminar_ids = {item["id"] for item in records["seminars"]}
    topic_ids = {item["id"] for item in records["topics"]}
    concept_ids = {item["id"] for item in records["concepts"]}
    decision_ids = {item["id"] for item in records["review_decisions"]}
    entity_ids = {project_id} | seminar_ids | topic_ids | concept_ids | {item["id"] for item in records["relations"]} | decision_ids
    evidence_ids = {item["id"] for item in (source_slice or {}).get("evidence", []) if _id(item.get("id"))}
    source_ids = {item["id"] for item in (evidence_bundle or {}).get("sources", []) if _id(item.get("id"))}
    revision_ids = {item["id"] for item in (evidence_bundle or {}).get("transcript_revisions", []) if _id(item.get("id"))}

    for index, seminar in enumerate(records["seminars"]):
        path = f"$.seminars[{index}]"
        if seminar["project_id"] != project_id:
            errors.append(f"L3_REFERENCE {path}.project_id: must reference project")
        _check_refs(errors, seminar["topic_refs"], f"{path}.topic_refs", topic_ids)
        _check_refs(errors, seminar.get("evidence_refs", []), f"{path}.evidence_refs", evidence_ids)

    for index, topic in enumerate(records["topics"]):
        path = f"$.topics[{index}]"
        if topic["seminar_id"] not in seminar_ids:
            errors.append(f"L3_REFERENCE {path}.seminar_id: dangling reference {topic['seminar_id']}")
        _check_refs(errors, topic["source_scope"]["source_ids"], f"{path}.source_scope.source_ids", source_ids)
        _check_refs(errors, topic["source_scope"]["transcript_revision_ids"], f"{path}.source_scope.transcript_revision_ids", revision_ids)
        _check_refs(errors, topic["evidence_refs"], f"{path}.evidence_refs", evidence_ids)
        _check_refs(errors, topic["concept_refs"], f"{path}.concept_refs", concept_ids)

    for index, concept in enumerate(records["concepts"]):
        path = f"$.concepts[{index}]"
        _check_refs(errors, concept["evidence_refs"], f"{path}.evidence_refs", evidence_ids)
        _check_refs(errors, concept["topic_refs"], f"{path}.topic_refs", topic_ids)
        _check_refs(errors, concept["created_from"], f"{path}.created_from", evidence_ids | topic_ids | decision_ids)
        _check_refs(errors, concept["supersedes"], f"{path}.supersedes", concept_ids)
        _check_refs(errors, concept["redirects"], f"{path}.redirects", concept_ids)

    for index, relation in enumerate(records["relations"]):
        path = f"$.relations[{index}]"
        if relation["source_concept_id"] not in concept_ids or relation["target_concept_id"] not in concept_ids:
            errors.append(f"L3_REFERENCE {path}: relation endpoint must reference a Concept")
        _check_refs(errors, relation["evidence_refs"], f"{path}.evidence_refs", evidence_ids)

    for index, decision in enumerate(records["review_decisions"]):
        path = f"$.review_decisions[{index}]"
        _check_refs(errors, decision["target_ids"], f"{path}.target_ids", entity_ids)
        _check_refs(errors, decision["result_ids"], f"{path}.result_ids", entity_ids)
        if decision.get("source_revision") and decision["source_revision"] not in decision_ids:
            errors.append(f"L3_REFERENCE {path}.source_revision: dangling decision reference")
        _check_refs(errors, decision.get("supersedes", []), f"{path}.supersedes", decision_ids)

    if evidence_bundle is not None and document["canonical_evidence"]["artifact_id"] != evidence_bundle.get("artifact_id"):
        errors.append("L3_REFERENCE $.canonical_evidence.artifact_id: does not match loaded Canonical Evidence")
    if source_slice is not None:
        if document["source_evidence"]["artifact_id"] != source_slice.get("artifact_id"):
            errors.append("L3_REFERENCE $.source_evidence.artifact_id: does not match loaded Golden Slice")
        for name in ("topics", "concepts"):
            present = {item["id"] for item in records[name]}
            for item in source_slice.get(name, []):
                if item.get("id") not in present:
                    errors.append(f"L3_REFERENCE $: source {name} identity missing from canonical knowledge: {item.get('id')}")
    return errors


def _layer4_lifecycle(document: dict[str, Any], records: dict[str, list[dict[str, Any]]]) -> list[str]:
    errors: list[str] = []
    contract = _lifecycle_contract()
    source_statuses = contract["source_statuses"]
    lifecycle_rules = contract["knowledge_lifecycles"]
    actor_policy = contract["actor_policy"]
    decisions = records["review_decisions"]
    record_by_id = {document["project"]["id"]: document["project"]}
    record_by_id.update({item["id"]: item for name in ENTITY_COLLECTIONS for item in records[name]})

    for index, topic in enumerate(records["topics"]):
        provenance = topic["provenance"]
        source_status = provenance.get("source_status")
        if provenance["origin"] == "golden_slice" and source_status is None:
            errors.append(f"L4_LIFECYCLE $.topics[{index}].provenance.source_status: required for Golden Slice Topic")
        elif source_status is not None and source_status not in source_statuses:
            errors.append(f"L4_LIFECYCLE $.topics[{index}].provenance.source_status: unsupported source status {source_status}")

    for index, decision in enumerate(decisions):
        path = f"$.review_decisions[{index}]"
        actor = decision["actor_type"]
        action = decision["action"]
        if action not in actor_policy[actor]["allowed_actions"]:
            errors.append(f"L4_LIFECYCLE {path}: {actor} cannot perform semantic action {action}")
        target_records = [record_by_id[target_id] for target_id in decision["target_ids"] if target_id in record_by_id]
        if actor == "system_validator":
            if decision["result_ids"]:
                errors.append(f"L4_LIFECYCLE {path}: AUTO DEFER must not create result IDs")
            if any(item["status"] != "PROVISIONAL" for item in target_records):
                errors.append(f"L4_LIFECYCLE {path}: AUTO DEFER targets must remain PROVISIONAL")
        if action == "ACCEPT" and any(item["status"] != "ACCEPTED" for item in target_records):
            errors.append(f"L4_LIFECYCLE {path}: ACCEPT targets must have ACCEPTED lifecycle")
        if action == "REJECT" and any(item["status"] != "REJECTED" for item in target_records):
            errors.append(f"L4_LIFECYCLE {path}: REJECT targets must have REJECTED lifecycle")
        if action in {"MERGE", "SPLIT"} and any(item["status"] != "SUPERSEDED" for item in target_records):
            errors.append(f"L4_LIFECYCLE {path}: {action} targets must have SUPERSEDED lifecycle")
        if action == "DEFER" and any(item["status"] != "PROVISIONAL" for item in target_records):
            errors.append(f"L4_LIFECYCLE {path}: DEFER targets must remain PROVISIONAL")

    for item_id, item in record_by_id.items():
        status = item["status"]
        rule = lifecycle_rules[status]
        if not rule.get("decision_required"):
            continue
        matching = [
            decision
            for decision in decisions
            if item_id in decision["target_ids"] and decision["action"] in rule["required_actions"]
        ]
        if not matching:
            errors.append(
                f"L4_LIFECYCLE $.id[{item_id}]: {status} requires explicit "
                f"{'/'.join(rule['required_actions'])} DOMAIN_REVIEW decision"
            )
    return errors


def validate_knowledge(
    document: Any,
    evidence_bundle: dict[str, Any] | None = None,
    source_slice: dict[str, Any] | None = None,
) -> list[str]:
    """Return deterministic layered validation errors; an empty list is valid."""
    structural_errors = _layer1_structure(document)
    if structural_errors:
        return structural_errors
    records = _records(document)
    return (
        _layer2_field_invariants(document, records)
        + _layer3_reference_integrity(document, records, evidence_bundle, source_slice)
        + _layer4_lifecycle(document, records)
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("document", type=Path)
    parser.add_argument("--canonical-evidence", type=Path)
    parser.add_argument("--source-slice", type=Path)
    args = parser.parse_args()
    document = _load_json(args.document)
    evidence_path = args.canonical_evidence or (ROOT / "analysis/word_timeline_mvp/canonical_evidence_bundle.json")
    source_path = args.source_slice or (ROOT / "analysis/golden_knowledge_slice/golden_knowledge_slice.json")
    evidence = _load_json(evidence_path) if evidence_path.is_file() else None
    source = _load_json(source_path) if source_path.is_file() else None
    errors = validate_knowledge(document, evidence, source)
    if errors:
        print(f"{args.document}: INVALID")
        print("\n".join(f"- {error}" for error in errors))
        return 1
    print(f"{args.document}: VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
