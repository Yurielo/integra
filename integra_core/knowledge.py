"""Read-governed Canonical Evidence and Knowledge projections."""

from __future__ import annotations

import copy
from datetime import datetime, timezone
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .identity import derive_imported_id
from .protocol import canonical_json, content_sha256, validate_component_identity
from ._vendor.seminartext_a94936c.validate_canonical_evidence_v1 import (
    validate_bundle as validate_canonical_evidence,
)
from ._vendor.seminartext_a94936c import validate_canonical_knowledge_v1 as source_knowledge


ID = re.compile(r"^[a-z][a-z0-9._:-]{2,127}$")
PINNED_SEMINARTEXT = {
    "component_id": "seminartext",
    "repository": "Yurielo/seminartext",
    "commit_sha": "a94936cd77cde13561c97c804ece1ac1134e01a6",
    "tree_sha": "5f5951da1d5dcf957ef982510fde3537f601ea15",
    "version": "4.0.0",
    "contracts": ["canonical_evidence_v1", "canonical_knowledge_v1"],
    "runtime": {"kind": "python", "version": "3"},
}
PINNED_CONTRACT_SHA256 = {
    "canonical_evidence_v1": "08bab4381ba435a059a1b58ea5dbedadd57112a18421ea7ef84a10ddb52d44b8",
    "canonical_knowledge_v1": "33691770411b4e5fc4e923920619396f7281bcd655202f8f56ddba99b844111b",
    "canonical_knowledge_lifecycle": "c9133fe6ff630dd44475f40d37d731f407ce2f79d1d15613454a1d5c179099bc",
    "canonical_evidence_validator": "889e6cdf3dc2dd7504f76923c04e2d8d1eceabdb828d0c110ddc1059b107860e",
    "canonical_knowledge_validator": "14869b0d77bed839758afb0455cffcfcba4173495554eddd9159a02309f1c095",
}
PINNED_REVIEWED_KNOWLEDGE_ARTIFACTS = {
    "21470fa1d903254aa51d2d5aed9666dfae6a48419cbaab755300ce71374892d0",
}


class KnowledgeError(RuntimeError):
    """Raised when a knowledge view would overstate source or semantic truth."""


def build_knowledge_view(
    evidence_payload: bytes, source_evidence_payload: bytes,
    knowledge_payload: bytes, *, created_at: str,
) -> dict[str, Any]:
    """Build a deterministic read projection without changing source records."""

    _validate_pinned_contracts()
    _timestamp(created_at)
    evidence = _load_source(evidence_payload, "Canonical Evidence")
    source_evidence = _load_source(source_evidence_payload, "source Evidence")
    knowledge = _load_source(knowledge_payload, "Canonical Knowledge")
    evidence_file_sha256 = hashlib.sha256(evidence_payload).hexdigest()
    knowledge_file_sha256 = hashlib.sha256(knowledge_payload).hexdigest()
    source_evidence_file_sha256 = hashlib.sha256(source_evidence_payload).hexdigest()
    _validate_sources(
        evidence, evidence_file_sha256, source_evidence,
        source_evidence_file_sha256, knowledge, knowledge_file_sha256,
    )
    evidence_hash = content_sha256(evidence)
    knowledge_hash = content_sha256(knowledge)
    binding = {
        "component_id": PINNED_SEMINARTEXT["component_id"],
        "commit_sha": PINNED_SEMINARTEXT["commit_sha"],
        "tree_sha": PINNED_SEMINARTEXT["tree_sha"],
        "component_identity_sha256": content_sha256(PINNED_SEMINARTEXT),
        "contract_sha256": copy.deepcopy(PINNED_CONTRACT_SHA256),
        "canonical_evidence_id": evidence["artifact_id"],
        "canonical_evidence_sha256": evidence_file_sha256,
        "canonical_evidence_content_sha256": evidence_hash,
        "source_evidence_id": source_evidence["artifact_id"],
        "source_evidence_sha256": source_evidence_file_sha256,
        "source_evidence_content_sha256": content_sha256(source_evidence),
        "canonical_knowledge_id": knowledge["artifact_id"],
        "canonical_knowledge_sha256": knowledge_file_sha256,
        "canonical_knowledge_content_sha256": knowledge_hash,
    }
    records = {
        name: sorted(copy.deepcopy(knowledge[name]), key=lambda item: item["id"])
        for name in ("seminars", "topics", "concepts", "relations", "review_decisions")
    }
    revisions = {item["id"]: item for item in evidence["transcript_revisions"]}
    evidence_views = [_evidence_view(item, revisions) for item in sorted(
        source_evidence["evidence"], key=lambda item: item["id"]
    )]
    terms = _terms(records["concepts"], {item["id"]: item for item in source_evidence["evidence"]})
    graph = _graph(records, evidence_views, terms)
    identity = content_sha256({"binding": binding, "graph_sha256": graph["graph_sha256"]})
    result = {
        "schema_version": "1.0",
        "view_id": derive_imported_id(
            "artifact", "integra.knowledge", knowledge["artifact_id"], identity
        ),
        "source_binding": binding,
        "created_at": created_at,
        "semantic_authority": "READ_ONLY_SOURCE_LIFECYCLE",
        "source_artifacts_modified": False,
        "records": records,
        "terms": terms,
        "evidence": evidence_views,
        "graph": graph,
        "record_sha256": "",
    }
    result["record_sha256"] = _record_hash(result)
    validate_knowledge_view(
        result, evidence_payload, source_evidence_payload, knowledge_payload,
    )
    return result


def validate_knowledge_view(
    view: dict[str, Any], evidence_payload: bytes, source_evidence_payload: bytes,
    knowledge_payload: bytes,
) -> None:
    _validate_view_shape(view)
    evidence = _load_source(evidence_payload, "Canonical Evidence")
    source_evidence = _load_source(source_evidence_payload, "source Evidence")
    knowledge = _load_source(knowledge_payload, "Canonical Knowledge")
    evidence_file_sha256 = hashlib.sha256(evidence_payload).hexdigest()
    knowledge_file_sha256 = hashlib.sha256(knowledge_payload).hexdigest()
    source_evidence_file_sha256 = hashlib.sha256(source_evidence_payload).hexdigest()
    _validate_pinned_contracts()
    _validate_sources(
        evidence, evidence_file_sha256, source_evidence,
        source_evidence_file_sha256, knowledge, knowledge_file_sha256,
    )
    expected_binding = {
        "component_id": PINNED_SEMINARTEXT["component_id"],
        "commit_sha": PINNED_SEMINARTEXT["commit_sha"],
        "tree_sha": PINNED_SEMINARTEXT["tree_sha"],
        "component_identity_sha256": content_sha256(PINNED_SEMINARTEXT),
        "contract_sha256": copy.deepcopy(PINNED_CONTRACT_SHA256),
        "canonical_evidence_id": evidence["artifact_id"],
        "canonical_evidence_sha256": evidence_file_sha256,
        "canonical_evidence_content_sha256": content_sha256(evidence),
        "source_evidence_id": source_evidence["artifact_id"],
        "source_evidence_sha256": source_evidence_file_sha256,
        "source_evidence_content_sha256": content_sha256(source_evidence),
        "canonical_knowledge_id": knowledge["artifact_id"],
        "canonical_knowledge_sha256": knowledge_file_sha256,
        "canonical_knowledge_content_sha256": content_sha256(knowledge),
    }
    if view["source_binding"] != expected_binding:
        raise KnowledgeError("knowledge source binding differs")
    expected_records = {
        name: sorted(copy.deepcopy(knowledge[name]), key=lambda item: item["id"])
        for name in ("seminars", "topics", "concepts", "relations", "review_decisions")
    }
    if view["records"] != expected_records:
        raise KnowledgeError("knowledge records differ from source truth")
    revisions = {item["id"]: item for item in evidence["transcript_revisions"]}
    expected_evidence = [_evidence_view(item, revisions) for item in sorted(
        source_evidence["evidence"], key=lambda item: item["id"]
    )]
    if view["evidence"] != expected_evidence:
        raise KnowledgeError("evidence projection differs from source truth")
    expected_terms = _terms(expected_records["concepts"], {
        item["id"]: item for item in source_evidence["evidence"]
    })
    if view["terms"] != expected_terms:
        raise KnowledgeError("term projection differs from Concept truth")
    expected_graph = _graph(expected_records, expected_evidence, expected_terms)
    if view["graph"] != expected_graph:
        raise KnowledgeError("knowledge graph differs")
    identity = content_sha256({
        "binding": expected_binding, "graph_sha256": expected_graph["graph_sha256"]
    })
    expected_id = derive_imported_id(
        "artifact", "integra.knowledge", knowledge["artifact_id"], identity
    )
    if view["view_id"] != expected_id or view["record_sha256"] != _record_hash(view):
        raise KnowledgeError("knowledge view identity or hash differs")


def dumps_knowledge_view(
    view: dict[str, Any], evidence_payload: bytes, source_evidence_payload: bytes,
    knowledge_payload: bytes,
) -> bytes:
    validate_knowledge_view(
        view, evidence_payload, source_evidence_payload, knowledge_payload,
    )
    return canonical_json(view) + b"\n"


def loads_knowledge_view(
    payload: bytes, evidence_payload: bytes, source_evidence_payload: bytes,
    knowledge_payload: bytes,
) -> dict[str, Any]:
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise KnowledgeError("knowledge view serialization is invalid") from error
    validate_knowledge_view(
        value, evidence_payload, source_evidence_payload, knowledge_payload,
    )
    return value


def navigate_knowledge(
    view: dict[str, Any], evidence_payload: bytes, source_evidence_payload: bytes,
    knowledge_payload: bytes, entity_id: str,
) -> dict[str, Any]:
    validate_knowledge_view(view, evidence_payload, source_evidence_payload, knowledge_payload)
    nodes = {item["id"]: item for item in view["graph"]["nodes"]}
    if entity_id not in nodes:
        raise KnowledgeError("knowledge navigation origin is unknown")
    outgoing = [item for item in view["graph"]["edges"] if item["from_id"] == entity_id]
    incoming = [item for item in view["graph"]["edges"] if item["to_id"] == entity_id]
    result = {"node": copy.deepcopy(nodes[entity_id]), "outgoing": outgoing, "incoming": incoming}
    if nodes[entity_id]["kind"] == "EVIDENCE":
        result["exact_evidence"] = copy.deepcopy(next(
            item for item in view["evidence"] if item["id"] == entity_id
        ))
    return result


def knowledge_diff(
    before: dict[str, Any], before_evidence_payload: bytes,
    before_source_evidence_payload: bytes, before_knowledge_payload: bytes,
    after: dict[str, Any], after_evidence_payload: bytes,
    after_source_evidence_payload: bytes, after_knowledge_payload: bytes,
) -> dict[str, Any]:
    """Return a content-addressed mechanical diff; never infer semantic meaning."""
    validate_knowledge_view(
        before, before_evidence_payload, before_source_evidence_payload,
        before_knowledge_payload,
    )
    validate_knowledge_view(
        after, after_evidence_payload, after_source_evidence_payload,
        after_knowledge_payload,
    )
    if before["source_binding"]["canonical_knowledge_id"] != after["source_binding"]["canonical_knowledge_id"]:
        raise KnowledgeError("knowledge diff requires one stable source artifact identity")
    left, right = _diff_index(before), _diff_index(after)
    added = [_diff_identity(item) for item in sorted(set(right) - set(left))]
    removed = [_diff_identity(item) for item in sorted(set(left) - set(right))]
    changed = [_diff_identity(item) for item in sorted(
        item for item in set(left) & set(right) if left[item] != right[item]
    )]
    value = {
        "schema_version": "1.0", "before_view_id": before["view_id"],
        "after_view_id": after["view_id"], "added_ids": added,
        "removed_ids": removed, "changed_ids": changed,
        "semantic_interpretation": "NOT_PERFORMED", "diff_sha256": "",
    }
    value["diff_sha256"] = _record_hash(value, "diff_sha256")
    return value


def _terms(
    concepts: list[dict[str, Any]], evidence: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    result = []
    for concept in concepts:
        for kind, value in [("PREFERRED_LABEL", concept["preferred_label"])] + [
            ("SOURCE_ALIAS", alias) for alias in concept["aliases"]
        ]:
            evidence_refs = sorted(concept["evidence_refs"])
            phrase = re.compile(r"(?<!\w)" + re.escape(value.casefold()) + r"(?!\w)")
            literal = any(
                phrase.search(evidence[item]["quote"].casefold()) is not None
                for item in evidence_refs
            )
            traceability = (
                "LITERAL_SOURCE_EVIDENCE"
                if kind == "SOURCE_ALIAS" and literal
                else "CONCEPT_SEMANTIC_EVIDENCE"
            )
            scope = {
                "concept_id": concept["id"], "kind": kind, "value": value,
                "evidence_refs": evidence_refs, "traceability": traceability,
            }
            digest = content_sha256(scope)
            result.append({
                "term_id": derive_imported_id("evidence", "seminartext.canonical_knowledge", value, digest),
                **scope, "semantic_status": concept["status"], "term_sha256": digest,
            })
    return sorted(result, key=lambda item: item["term_id"])


def _evidence_view(
    item: dict[str, Any], revisions: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    revision = revisions[item["canonical_transcript_revision_id"]]
    return {
        "id": item["id"],
        "claim": item["claim"],
        "source_id": item["canonical_source_id"],
        "transcript_revision_id": revision["id"],
        "word_start_id": item["canonical_word_start_id"],
        "word_end_id": item["canonical_word_end_id"],
        "quote": item["quote"],
        "locator": copy.deepcopy(item["locator"]),
        "timing_status": item["timing_status"],
        "unaligned_word_ids": copy.deepcopy(item["unaligned_word_ids"]),
        "transcript_assurance": {
            "revision_kind": revision["revision_kind"],
            "authority": revision["authority"],
            "lifecycle_status": revision["lifecycle_status"],
            "provenance": copy.deepcopy(revision.get("transcript_provenance")),
        },
        "evidence_sha256": content_sha256(item),
    }


def _diff_index(view: dict[str, Any]) -> dict[str, str]:
    result = {}
    for kind, records in (
        ("SEMINAR", view["records"]["seminars"]),
        ("TOPIC", view["records"]["topics"]),
        ("CONCEPT", view["records"]["concepts"]),
        ("RELATION", view["records"]["relations"]),
        ("REVIEW_DECISION", view["records"]["review_decisions"]),
        ("TERM", view["terms"]),
        ("EVIDENCE", view["evidence"]),
    ):
        id_field = "term_id" if kind == "TERM" else "id"
        for record in records:
            result[f"{kind}\0{record[id_field]}"] = content_sha256(record)
    return result


def _diff_identity(value: str) -> dict[str, str]:
    kind, item_id = value.split("\0", 1)
    return {"kind": kind, "id": item_id}


def _graph(
    records: dict[str, list[dict[str, Any]]], evidence: list[dict[str, Any]],
    terms: list[dict[str, Any]],
) -> dict[str, Any]:
    nodes = []
    edges = []
    for kind in ("seminars", "topics", "concepts", "relations", "review_decisions"):
        node_kind = kind[:-1].upper()
        for item in records[kind]:
            nodes.append({"id": item["id"], "kind": node_kind,
                          "status": item.get("status", "DECISION"), "sha256": content_sha256(item)})
            for evidence_id in item.get("evidence_refs", []):
                edges.append({"from_id": item["id"], "to_id": evidence_id, "kind": "SUPPORTED_BY"})
    for item in evidence:
        nodes.append({"id": item["id"], "kind": "EVIDENCE", "status": "SOURCE_EVIDENCE",
                      "sha256": item["evidence_sha256"]})
    for item in terms:
        nodes.append({
            "id": item["term_id"], "kind": "TERM",
            "status": item["semantic_status"], "sha256": item["term_sha256"],
        })
        edges.append({"from_id": item["term_id"], "to_id": item["concept_id"], "kind": "TERM_OF"})
        for evidence_id in item["evidence_refs"]:
            edges.append({"from_id": item["term_id"], "to_id": evidence_id, "kind": "SUPPORTED_BY"})
    for item in records["seminars"]:
        for topic_id in item["topic_refs"]:
            edges.append({"from_id": item["id"], "to_id": topic_id, "kind": "CONTAINS"})
    for item in records["topics"]:
        for concept_id in item["concept_refs"]:
            edges.append({"from_id": item["id"], "to_id": concept_id, "kind": "MENTIONS"})
    for item in records["relations"]:
        edges.extend([
            {"from_id": item["id"], "to_id": item["source_concept_id"], "kind": "RELATION_SOURCE"},
            {"from_id": item["id"], "to_id": item["target_concept_id"], "kind": "RELATION_TARGET"},
        ])
    for item in records["review_decisions"]:
        for target_id in item["target_ids"]:
            edges.append({"from_id": item["id"], "to_id": target_id, "kind": "REVIEW_TARGET"})
        for result_id in item["result_ids"]:
            edges.append({"from_id": item["id"], "to_id": result_id, "kind": "REVIEW_RESULT"})
    nodes.sort(key=lambda item: item["id"])
    edges.sort(key=lambda item: (item["from_id"], item["kind"], item["to_id"]))
    graph = {"nodes": nodes, "edges": edges, "graph_sha256": ""}
    graph["graph_sha256"] = _record_hash(graph, "graph_sha256")
    return graph


def _validate_pinned_contracts() -> None:
    validate_component_identity(PINNED_SEMINARTEXT)
    root = Path(__file__).with_name("_vendor") / "seminartext_a94936c"
    paths = {
        "canonical_evidence_v1": root / "canonical_evidence_v1.schema.json",
        "canonical_knowledge_v1": root / "canonical_knowledge_v1.schema.json",
        "canonical_knowledge_lifecycle": root / "canonical_knowledge_lifecycle_v1.json",
        "canonical_evidence_validator": root / "validate_canonical_evidence_v1.py",
        "canonical_knowledge_validator": root / "validate_canonical_knowledge_v1.py",
    }
    for name, path in paths.items():
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != PINNED_CONTRACT_SHA256[name]:
            raise KnowledgeError(f"pinned SeminarText {name} contract differs")


def _validate_sources(
    evidence: dict[str, Any], evidence_file_sha256: str,
    source_evidence: dict[str, Any], source_evidence_file_sha256: str,
    knowledge: dict[str, Any], knowledge_file_sha256: str,
) -> None:
    root = Path(__file__).with_name("_vendor") / "seminartext_a94936c"
    evidence_schema = json.loads((root / "canonical_evidence_v1.schema.json").read_bytes())
    evidence_schema_errors: list[str] = []
    _validate_json_schema(evidence, evidence_schema, evidence_schema, "$", evidence_schema_errors)
    if evidence_schema_errors:
        raise KnowledgeError("Canonical Evidence invalid: " + sorted(evidence_schema_errors)[0])
    evidence_errors = validate_canonical_evidence(evidence)
    if evidence_errors:
        raise KnowledgeError("Canonical Evidence invalid: " + evidence_errors[0])
    slice_errors = _validate_source_evidence(source_evidence, evidence)
    if slice_errors:
        raise KnowledgeError("source Evidence invalid: " + slice_errors[0])
    schema = json.loads((root / "canonical_knowledge_v1.schema.json").read_bytes())
    schema_errors: list[str] = []
    _validate_json_schema(knowledge, schema, schema, "$", schema_errors)
    if schema_errors:
        raise KnowledgeError("Canonical Knowledge invalid: " + sorted(schema_errors)[0])
    records = source_knowledge._records(knowledge)
    knowledge_errors = (
        source_knowledge._layer2_field_invariants(knowledge, records)
        + source_knowledge._layer3_reference_integrity(
            knowledge, records, evidence, source_evidence
        )
        + source_knowledge._layer4_lifecycle(knowledge, records)
    )
    if knowledge_errors:
        raise KnowledgeError("Canonical Knowledge invalid: " + sorted(knowledge_errors)[0])
    substantive = knowledge["topics"] + knowledge["concepts"] + knowledge["relations"]
    if any(not item["evidence_refs"] for item in substantive):
        raise KnowledgeError("substantive knowledge lacks exact evidence")
    semantic_statuses = [
        item.get("status") for item in [knowledge["project"]]
        + knowledge["seminars"] + substantive
    ]
    has_human_decision = any(
        item["actor_type"] in {"human_domain_reviewer", "product_owner"}
        for item in knowledge["review_decisions"]
    )
    if (
        (any(item in {"ACCEPTED", "REJECTED", "SUPERSEDED"} for item in semantic_statuses)
         or has_human_decision)
        and knowledge_file_sha256 not in PINNED_REVIEWED_KNOWLEDGE_ARTIFACTS
    ):
        raise KnowledgeError(
            "reviewed lifecycle requires a pinned source artifact attestation"
        )
    source_evidence_index = {item["id"]: item for item in source_evidence["evidence"]}
    source_topics = {item["id"]: item for item in source_evidence["topics"]}
    source_concepts = {item["id"]: item for item in source_evidence["concepts"]}
    for topic in knowledge["topics"]:
        scope = topic["source_scope"]
        for evidence_id in topic["evidence_refs"]:
            item = source_evidence_index[evidence_id]
            if (
                item["canonical_source_id"] not in scope["source_ids"]
                or item["canonical_transcript_revision_id"] not in scope["transcript_revision_ids"]
            ):
                raise KnowledgeError("Topic evidence lies outside its source scope")
        if topic["provenance"]["origin"] == "golden_slice":
            source = source_topics.get(topic["id"])
            if source is None or (
                topic["title"] != source["title"]
                or topic["summary"] != source["summary"]
                or topic["evidence_refs"] != source["evidence_ids"]
                or topic["concept_refs"] != source["concept_ids"]
                or scope["source_ids"] != [source["canonical_source_id"]]
                or scope["transcript_revision_ids"] != [source["canonical_transcript_revision_id"]]
            ):
                raise KnowledgeError("provisional Topic differs from source Evidence")
    for concept in knowledge["concepts"]:
        if concept["provenance"]["origin"] == "golden_slice":
            source = source_concepts.get(concept["id"])
            if source is None or (
                concept["preferred_label"] != source["preferred_label"]
                or concept["aliases"] != source["aliases"]
                or concept["description"] != source["description"]
                or concept["evidence_refs"] != source["evidence_ids"]
                or concept["topic_refs"] != source["topic_ids"]
            ):
                raise KnowledgeError("provisional Concept differs from source Evidence")
    if (
        source_evidence["canonical_evidence"]["artifact_id"] != evidence["artifact_id"]
        or source_evidence["canonical_evidence"]["sha256"] != evidence_file_sha256
        or knowledge["canonical_evidence"]["artifact_id"] != evidence["artifact_id"]
        or knowledge["canonical_evidence"]["sha256"] != evidence_file_sha256
        or knowledge["source_evidence"]["artifact_id"] != source_evidence["artifact_id"]
        or knowledge["source_evidence"]["sha256"] != source_evidence_file_sha256
    ):
        raise KnowledgeError("source artifact hash binding differs")


def _validate_source_evidence(
    document: Any, canonical: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    required = {
        "artifact_id", "artifact_type", "canonical_evidence", "concepts",
        "evidence", "product_review", "schema_version", "seminar", "sources",
        "topics",
    }
    if not isinstance(document, dict) or set(document) != required:
        return ["top-level fields differ from the pinned Golden Slice contract"]
    if document["schema_version"] != "1.0.0" or document["artifact_type"] != "seminartext.golden_knowledge_slice":
        errors.append("identity differs from the pinned Golden Slice contract")
    all_records = [document["seminar"]] + [
        item for name in ("sources", "topics", "concepts", "evidence")
        for item in document[name]
    ]
    ids = [item.get("id") for item in all_records if isinstance(item, dict)]
    if len(ids) != len(all_records) or any(not isinstance(item, str) or ID.fullmatch(item) is None for item in ids) or len(ids) != len(set(ids)):
        errors.append("entity IDs are invalid or duplicated")
    for name in ("topics", "concepts", "evidence"):
        records = document[name]
        if [item.get("sequence") for item in records] != list(range(len(records))) or records != sorted(records, key=lambda item: (item["sequence"], item["id"])):
            errors.append(f"{name} sequence/order is not deterministic")
    words = {item["id"]: item for item in canonical["words"]}
    sources = {item["id"]: item for item in canonical["sources"]}
    revisions = {item["id"]: item for item in canonical["transcript_revisions"]}
    evidence = {item["id"]: item for item in document["evidence"]}
    topics = {item["id"]: item for item in document["topics"]}
    concepts = {item["id"]: item for item in document["concepts"]}
    for item in document["sources"]:
        source = sources.get(item.get("canonical_source_id"))
        expected_fields = {
            "canonical_source_id", "content_sha256", "duration_seconds", "id",
            "kind", "title",
        }
        if (
            set(item) != expected_fields or source is None
            or item["id"] != source["id"]
            or item["content_sha256"] != source["content_sha256"]
            or item["duration_seconds"] != source["duration_seconds"]
            or item["kind"] != source["kind"] or item["title"] != source["title"]
        ):
            errors.append(f"{item.get('id')}: source projection differs from Canonical Evidence")
    for item in evidence.values():
        fields = {
            "canonical_source_id", "canonical_transcript_revision_id",
            "canonical_word_end_id", "canonical_word_start_id", "claim", "id",
            "locator", "quote", "sequence", "timing_status", "unaligned_word_ids",
        }
        if set(item) != fields or not isinstance(item["claim"], str) or not item["claim"]:
            errors.append(f"{item.get('id')}: Evidence fields differ")
            continue
        first, last = words.get(item["canonical_word_start_id"]), words.get(item["canonical_word_end_id"])
        source, revision = sources.get(item["canonical_source_id"]), revisions.get(item["canonical_transcript_revision_id"])
        if first is None or last is None or source is None or revision is None:
            errors.append(f"{item['id']}: orphan canonical reference")
            continue
        if first["source_id"] != source["id"] or last["source_id"] != source["id"] or revision["source_id"] != source["id"]:
            errors.append(f"{item['id']}: cross-source range")
        if first["transcript_revision_id"] != revision["id"] or last["transcript_revision_id"] != revision["id"]:
            errors.append(f"{item['id']}: cross-revision range")
        start, end = first["sequence"], last["sequence"]
        selected = sorted(
            (word for word in words.values() if word["transcript_revision_id"] == revision["id"] and start <= word["sequence"] <= end),
            key=lambda word: word["sequence"],
        )
        if end < start or [word["sequence"] for word in selected] != list(range(start, end + 1)):
            errors.append(f"{item['id']}: non-contiguous Word range")
            continue
        if item["quote"] != revision["canonical_text"][first["char_start"]:last["char_end"]]:
            errors.append(f"{item['id']}: quote does not match canonical text")
        aligned = [word for word in selected if word["alignment_status"] == "aligned"]
        if not aligned:
            errors.append(f"{item['id']}: no aligned timing anchor")
            continue
        expected_locator = {"end_seconds": aligned[-1]["end_seconds"], "start_seconds": aligned[0]["start_seconds"], "type": "time_interval"}
        expected_unaligned = [word["id"] for word in selected if word["alignment_status"] == "unaligned"]
        expected_status = "aligned_word_range" if not expected_unaligned else "aligned_envelope_with_explicit_unaligned_words"
        if item["locator"] != expected_locator or item["unaligned_word_ids"] != expected_unaligned or item["timing_status"] != expected_status:
            errors.append(f"{item['id']}: timing provenance differs from canonical Words")
    for topic in topics.values():
        if topic.get("structure_origin") not in {"gold_dataset_a", "manual_issue_44"}:
            errors.append(f"{topic['id']}: prohibited automatic Topic origin")
        if any(item not in evidence for item in topic.get("evidence_ids", [])) or any(item not in concepts for item in topic.get("concept_ids", [])):
            errors.append(f"{topic['id']}: orphan knowledge reference")
        first, last = words.get(topic.get("canonical_word_start_id")), words.get(topic.get("canonical_word_end_id"))
        source, revision = sources.get(topic.get("canonical_source_id")), revisions.get(topic.get("canonical_transcript_revision_id"))
        if first is None or last is None or source is None or revision is None:
            errors.append(f"{topic['id']}: orphan Topic Word range")
            continue
        if (
            first["source_id"] != source["id"] or last["source_id"] != source["id"]
            or revision["source_id"] != source["id"]
            or first["transcript_revision_id"] != revision["id"]
            or last["transcript_revision_id"] != revision["id"]
        ):
            errors.append(f"{topic['id']}: cross-source or cross-revision Topic range")
        for evidence_id in topic.get("evidence_ids", []):
            if evidence_id in evidence:
                ev = evidence[evidence_id]
                ev_first = words[ev["canonical_word_start_id"]]["sequence"]
                ev_last = words[ev["canonical_word_end_id"]]["sequence"]
                if ev_first < first["sequence"] or ev_last > last["sequence"]:
                    errors.append(f"{topic['id']}: Evidence is outside Topic")
    for concept in concepts.values():
        if concept.get("derivation_status") != "provisional_manual_curation" or concept.get("review_status") != "product_review_required":
            errors.append(f"{concept['id']}: Concept source review state differs")
        if not concept.get("topic_ids") or not concept.get("evidence_ids") or any(item not in evidence for item in concept.get("evidence_ids", [])):
            errors.append(f"{concept['id']}: Concept evidence is incomplete")
        for topic_id in concept.get("topic_ids", []):
            if topic_id not in topics or concept["id"] not in topics[topic_id].get("concept_ids", []):
                errors.append(f"{concept['id']}: non-reciprocal Topic link")
        for evidence_id in concept.get("evidence_ids", []):
            if not any(
                evidence_id in topics[topic_id].get("evidence_ids", [])
                for topic_id in concept.get("topic_ids", []) if topic_id in topics
            ):
                errors.append(f"{concept['id']}: Evidence is outside linked Topics")
    if document["seminar"].get("source_ids") != [item["id"] for item in document["sources"]] or document["seminar"].get("topic_ids") != [item["id"] for item in document["topics"]]:
        errors.append("Seminar links are incomplete")
    if document["canonical_evidence"].get("artifact_id") != canonical["artifact_id"]:
        errors.append("Canonical Evidence artifact identity differs")
    if document["seminar"].get("canonical_project_id") != canonical["project"]["id"]:
        errors.append("Seminar project identity differs")
    if document["product_review"] != {"required": True, "status": "pending"}:
        errors.append("source Product Review state differs")
    return sorted(set(errors))


def _validate_json_schema(
    value: Any, schema: dict[str, Any], root: dict[str, Any], path: str,
    errors: list[str],
) -> None:
    if "$ref" in schema:
        target: Any = root
        for part in schema["$ref"][2:].split("/"):
            target = target[part.replace("~1", "/").replace("~0", "~")]
        _validate_json_schema(value, target, root, path, errors)
        return
    for keyword, exact_one in (("anyOf", False), ("oneOf", True)):
        if keyword in schema:
            branch_errors = []
            matches = 0
            for branch in schema[keyword]:
                candidate: list[str] = []
                _validate_json_schema(value, branch, root, path, candidate)
                branch_errors.append(candidate)
                if not candidate:
                    matches += 1
            if matches == 0 or (exact_one and matches != 1):
                errors.append(f"{path}: does not satisfy {keyword}")
                return
    expected = schema.get("type")
    types = expected if isinstance(expected, list) else [expected] if expected else []
    type_match = {
        "object": lambda item: isinstance(item, dict),
        "array": lambda item: isinstance(item, list),
        "string": lambda item: isinstance(item, str),
        "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
        "number": lambda item: _finite_number(item),
        "null": lambda item: item is None,
        "boolean": lambda item: isinstance(item, bool),
    }
    if types and not any(type_match[item](value) for item in types):
        errors.append(f"{path}: expected {expected}")
        return
    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: differs from const")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: unsupported value")
    if isinstance(value, dict):
        required = set(schema.get("required", []))
        if required - set(value):
            errors.append(f"{path}: missing fields {sorted(required - set(value))}")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False and set(value) - set(properties):
            errors.append(f"{path}: unknown fields {sorted(set(value) - set(properties))}")
        for name, child in value.items():
            if name in properties:
                _validate_json_schema(child, properties[name], root, f"{path}.{name}", errors)
    elif isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            errors.append(f"{path}: too few items")
        if schema.get("uniqueItems") and len({canonical_json(item) for item in value}) != len(value):
            errors.append(f"{path}: duplicate items")
        if "items" in schema:
            for index, child in enumerate(value):
                _validate_json_schema(child, schema["items"], root, f"{path}[{index}]", errors)
    elif isinstance(value, str):
        if len(value) < schema.get("minLength", 0) or ("pattern" in schema and re.search(schema["pattern"], value) is None):
            errors.append(f"{path}: invalid string")
    elif _finite_number(value):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: below minimum")
        if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
            errors.append(f"{path}: below exclusive minimum")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path}: above maximum")


def _validate_view_shape(view: Any) -> None:
    schema_path = Path(__file__).resolve().parents[1] / "schemas" / "knowledge_view_v1.schema.json"
    schema = json.loads(schema_path.read_bytes())
    schema_errors: list[str] = []
    _validate_json_schema(view, schema, schema, "$", schema_errors)
    if schema_errors:
        raise KnowledgeError("knowledge view schema differs: " + sorted(schema_errors)[0])
    fields = {"schema_version", "view_id", "source_binding", "created_at", "semantic_authority",
              "source_artifacts_modified", "records", "terms", "evidence", "graph", "record_sha256"}
    if not isinstance(view, dict) or set(view) != fields or view["schema_version"] != "1.0":
        raise KnowledgeError("knowledge view fields differ")
    if view["semantic_authority"] != "READ_ONLY_SOURCE_LIFECYCLE" or view["source_artifacts_modified"] is not False:
        raise KnowledgeError("knowledge view authority differs")
    _timestamp(view["created_at"])


def _load_source(payload: Any, label: str) -> dict[str, Any]:
    if not isinstance(payload, bytes):
        raise KnowledgeError(f"{label} payload must be bytes")
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise KnowledgeError(f"{label} payload is invalid JSON") from error
    if not isinstance(value, dict):
        raise KnowledgeError(f"{label} payload must contain an object")
    return value


def _finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value == value and abs(value) != float("inf")


def _timestamp(value: Any) -> None:
    pattern = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$"
    if not isinstance(value, str) or re.fullmatch(pattern, value) is None:
        raise KnowledgeError("timestamp must be RFC3339 UTC")
    if int(value[11:13]) > 23 or int(value[14:16]) > 59 or int(value[17:19]) > 59:
        raise KnowledgeError("timestamp must be RFC3339 UTC")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise KnowledgeError("timestamp must be RFC3339 UTC") from error
    if parsed.tzinfo != timezone.utc:
        raise KnowledgeError("timestamp must be UTC")


def _record_hash(value: dict[str, Any], field: str = "record_sha256") -> str:
    clone = copy.deepcopy(value)
    clone[field] = ""
    return content_sha256(clone)
