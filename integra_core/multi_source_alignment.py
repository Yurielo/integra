"""Deterministic, reversible, provenance-preserving multi-source alignment v1."""

from __future__ import annotations

import copy
from datetime import datetime, timezone
import json
import math
import re
from typing import Any

from .identity import derive_imported_id
from .documents import DocumentError, validate_document_record
from .projects_sources import RegistryError, validate_registry
from .transcript_topic_studio import StudioError, validate_studio
from .protocol import (
    ProtocolViolation,
    canonical_json,
    content_sha256,
    validate_artifact_reference,
)


SHA256 = re.compile(r"^[0-9a-f]{64}$")
URN = re.compile(
    r"^urn:integra:[a-z][a-z0-9_]{1,31}:"
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)

NODE_KINDS = {
    "VIDEO", "AUDIO", "TRANSCRIPT", "SLIDE", "PAGE",
    "SUPPORTING_DOCUMENT", "TOPIC", "EVIDENCE",
}
RELATIONS = {
    "VIDEO_TO_TRANSCRIPT": ({"VIDEO", "AUDIO"}, {"TRANSCRIPT"}),
    "VIDEO_TO_SLIDE": ({"VIDEO", "AUDIO"}, {"SLIDE"}),
    "TOPIC_TO_PAGE": ({"TOPIC"}, {"PAGE"}),
    "TOPIC_TO_SLIDE": ({"TOPIC"}, {"SLIDE"}),
    "EVIDENCE_TO_DOCUMENT": ({"EVIDENCE"}, {"SUPPORTING_DOCUMENT", "PAGE", "SLIDE"}),
}
LOCATOR_TYPES = {
    "TIME_INTERVAL", "WORD_INTERVAL", "PAGE_RANGE", "SLIDE_RANGE",
    "REGION", "CHARACTER_RANGE", "ARTIFACT_REVISION",
}
SEMANTIC_STATES = {"PROVISIONAL", "REVIEW_REQUIRED", "NOT_APPLICABLE"}


class AlignmentError(RuntimeError):
    """Raised when an alignment would lose provenance or semantic authority."""


def new_alignment(
    registry: dict[str, Any], *, project_id: str,
    source_revision_ids: list[str], artifact_references: list[dict[str, Any]],
    upstream_records: list[dict[str, Any]],
    created_at: str,
) -> dict[str, Any]:
    """Create an alignment graph over at least two current project sources."""

    _timestamp(created_at)
    _validate_registry(registry)
    project = _find(registry["projects"], "project_id", project_id, "project")
    _unique_text(source_revision_ids, "source revisions", non_empty=True)
    if len(source_revision_ids) < 2:
        raise AlignmentError("multi-source alignment requires at least two source revisions")
    bindings = []
    for revision_id in sorted(source_revision_ids):
        source, revision = _source_revision(registry, revision_id)
        if project_id not in source["project_ids"] or source["source_id"] not in project["source_ids"]:
            raise AlignmentError("alignment source is not attached to project")
        if source["current_revision_id"] != revision_id:
            raise AlignmentError("alignment requires current source revisions")
        bindings.append({
            "source_id": source["source_id"],
            "source_revision_id": revision_id,
            "source_revision_sha256": revision["revision_sha256"],
            "source_type": source["source_type"],
            "source_record_sha256": content_sha256(source),
        })
    if len({item["source_id"] for item in bindings}) != len(bindings):
        raise AlignmentError("alignment source revisions must belong to distinct sources")
    artifact_catalog = _artifact_catalog(
        artifact_references, upstream_records, registry, bindings
    )
    registry_binding = {
        "registry_id": registry["registry_id"],
        "registry_record_sha256": registry["record_sha256"],
        "project_record_sha256": content_sha256(project),
    }
    identity_sha256 = content_sha256({
        "project_id": project_id,
        "registry_binding": registry_binding,
        "sources": bindings,
        "artifact_catalog_sha256": artifact_catalog["catalog_sha256"],
    })
    value = {
        "schema_version": "1.0",
        "alignment_id": derive_imported_id(
            "artifact", "integra.multi_source_alignment", project_id, identity_sha256
        ),
        "project_id": project_id,
        "registry_binding": registry_binding,
        "sources": bindings,
        "artifact_catalog": artifact_catalog,
        "created_at": created_at,
        "updated_at": created_at,
        "revision": 0,
        "nodes": [],
        "links": [],
        "semantic_authority": "MACHINE_ALIGNMENT_REQUIRES_HUMAN_DECISION",
        "source_artifacts_modified": False,
        "record_sha256": "",
    }
    return _seal(value)


def add_node(
    alignment: dict[str, Any], *, registry: dict[str, Any],
    upstream_records: list[dict[str, Any]], native_id: str,
    kind: str, source_id: str, source_revision_id: str, artifact_id: str,
    artifact_sha256: str, owner_component: str, locators: list[dict[str, Any]],
    lineage_ids: list[str], semantic_status: str, created_at: str,
) -> tuple[dict[str, Any], str]:
    """Index one immutable source entity without copying or changing it."""

    validate_alignment(alignment, registry, upstream_records)
    _timestamp(created_at)
    _text(native_id, "node native ID")
    _text(owner_component, "node owner component")
    _urn(artifact_id, "node artifact ID")
    _sha(artifact_sha256, "node artifact hash")
    if kind not in NODE_KINDS:
        raise AlignmentError("alignment node kind is unsupported")
    if semantic_status not in SEMANTIC_STATES:
        raise AlignmentError("alignment node semantic status is invalid")
    if kind in {"TRANSCRIPT", "TOPIC", "EVIDENCE"} and semantic_status == "NOT_APPLICABLE":
        raise AlignmentError("semantic node cannot bypass review authority")
    binding = _bound_source(alignment, source_id, source_revision_id)
    normalized = _normalize_locators(locators)
    _require_native_locator(binding["source_type"], normalized)
    _require_revision_locator(binding, normalized)
    _require_kind_source(kind, binding["source_type"], normalized)
    _unique_text(lineage_ids, "node lineage", non_empty=True)
    if artifact_id not in lineage_ids:
        raise AlignmentError("node lineage must include its source artifact")
    reference = _find(
        alignment["artifact_catalog"]["references"], "artifact_id", artifact_id,
        "upstream artifact reference",
    )
    expected_locator = reference["source_locator"]
    expected_lineage = sorted(reference["parent_artifact_ids"] + [artifact_id])
    if (
        reference["kind"] != kind
        or expected_locator["native_id"] != native_id
        or expected_locator["source_id"] != source_id
        or expected_locator["source_revision_id"] != source_revision_id
        or expected_locator["locators"] != normalized
        or reference["content_sha256"] != artifact_sha256
        or reference["owner_component"] != owner_component
        or reference.get("semantic_status") != semantic_status
        or sorted(lineage_ids) != expected_lineage
    ):
        raise AlignmentError("node differs from authoritative upstream artifact reference")
    identity_sha256 = content_sha256({
        "owner_component": owner_component,
        "native_id": native_id,
        "artifact_id": artifact_id,
        "artifact_sha256": artifact_sha256,
        "source_revision_id": source_revision_id,
    })
    node_id = derive_imported_id("evidence", owner_component, native_id, identity_sha256)
    node = {
        "node_id": node_id,
        "native_id": native_id,
        "kind": kind,
        "source_id": source_id,
        "source_revision_id": source_revision_id,
        "artifact_id": artifact_id,
        "artifact_sha256": artifact_sha256,
        "owner_component": owner_component,
        "locators": normalized,
        "lineage_ids": sorted(lineage_ids),
        "semantic_status": semantic_status,
        "created_at": created_at,
        "node_sha256": "",
    }
    node["node_sha256"] = _record_hash(node, "node_sha256")
    result = copy.deepcopy(alignment)
    if any(item["native_id"] == native_id and item["node_id"] != node_id for item in result["nodes"]):
        raise AlignmentError("alignment node native ID conflict")
    existing = _find(result["nodes"], "node_id", node_id, "node", required=False)
    if existing is not None:
        if existing != node:
            raise AlignmentError("alignment node identity conflict")
        return alignment, node_id
    result["nodes"].append(node)
    result["nodes"].sort(key=lambda item: item["node_id"])
    return _advance(result, created_at), node_id


def add_link(
    alignment: dict[str, Any], *, registry: dict[str, Any],
    upstream_records: list[dict[str, Any]], native_id: str,
    relation: str, from_node_id: str, to_node_id: str,
    evidence_node_ids: list[str], confidence: float, conflict: bool,
    method: str, created_at: str,
) -> tuple[dict[str, Any], str]:
    """Add one cross-source machine proposal bound to complete node payloads."""

    validate_alignment(alignment, registry, upstream_records)
    _timestamp(created_at)
    _text(native_id, "link native ID")
    _text(method, "alignment method")
    confidence = _probability(confidence, "alignment confidence")
    if not isinstance(conflict, bool):
        raise AlignmentError("alignment conflict must be boolean")
    if relation not in RELATIONS:
        raise AlignmentError("alignment relation is unsupported")
    nodes = {item["node_id"]: item for item in alignment["nodes"]}
    source = nodes.get(from_node_id)
    target = nodes.get(to_node_id)
    if source is None or target is None or source is target:
        raise AlignmentError("alignment link references unknown or identical nodes")
    allowed_from, allowed_to = RELATIONS[relation]
    if source["kind"] not in allowed_from or target["kind"] not in allowed_to:
        raise AlignmentError("alignment relation endpoints are invalid")
    if relation != "VIDEO_TO_TRANSCRIPT" and source["source_id"] == target["source_id"]:
        raise AlignmentError("alignment link must connect distinct sources")
    if relation == "VIDEO_TO_TRANSCRIPT" and (
        source["source_id"] != target["source_id"]
        or source["source_revision_id"] != target["source_revision_id"]
    ):
        raise AlignmentError("video and transcript must share one source revision")
    _unique_text(evidence_node_ids, "alignment evidence", non_empty=True)
    if any(item not in nodes for item in evidence_node_ids):
        raise AlignmentError("alignment evidence references an unknown node")
    status = "REVIEW_REQUIRED" if conflict or confidence < 0.8 else "PROVISIONAL"
    scope = {
        "relation": relation,
        "from_node_id": from_node_id,
        "from_node_sha256": source["node_sha256"],
        "to_node_id": to_node_id,
        "to_node_sha256": target["node_sha256"],
        "evidence": [
            {"node_id": item, "node_sha256": nodes[item]["node_sha256"]}
            for item in sorted(evidence_node_ids)
        ],
        "method": method,
        "confidence": confidence,
        "conflict": conflict,
    }
    scope_sha256 = content_sha256(scope)
    link_id = derive_imported_id("evidence", "integra.alignment", native_id, scope_sha256)
    link = {
        "link_id": link_id,
        "native_id": native_id,
        **scope,
        "semantic_status": status,
        "created_at": created_at,
        "scope_sha256": scope_sha256,
    }
    result = copy.deepcopy(alignment)
    if any(item["native_id"] == native_id and item["link_id"] != link_id for item in result["links"]):
        raise AlignmentError("alignment link native ID conflict")
    existing = _find(result["links"], "link_id", link_id, "alignment link", required=False)
    if existing is not None:
        if existing != link:
            raise AlignmentError("alignment link identity conflict")
        return alignment, link_id
    result["links"].append(link)
    result["links"].sort(key=lambda item: item["link_id"])
    return _advance(result, created_at), link_id


def navigate(
    alignment: dict[str, Any], registry: dict[str, Any],
    upstream_records: list[dict[str, Any]], node_id: str,
) -> dict[str, list[dict[str, Any]]]:
    """Return deterministic forward and reverse hops with exact destination locators."""

    validate_alignment(alignment, registry, upstream_records)
    nodes = {item["node_id"]: item for item in alignment["nodes"]}
    if node_id not in nodes:
        raise AlignmentError("navigation origin is unknown")
    forward = []
    reverse = []
    for link in alignment["links"]:
        if link["from_node_id"] == node_id:
            forward.append(_hop(link, nodes[link["to_node_id"]], "FORWARD"))
        if link["to_node_id"] == node_id:
            reverse.append(_hop(link, nodes[link["from_node_id"]], "REVERSE"))
    key = lambda item: (item["relation"], item["node_id"], item["link_id"])
    return {"forward": sorted(forward, key=key), "reverse": sorted(reverse, key=key)}


def dumps_alignment(
    alignment: dict[str, Any], registry: dict[str, Any],
    upstream_records: list[dict[str, Any]],
) -> bytes:
    validate_alignment(alignment, registry, upstream_records)
    return canonical_json(alignment) + b"\n"


def loads_alignment(
    payload: bytes, registry: dict[str, Any], upstream_records: list[dict[str, Any]],
) -> dict[str, Any]:
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AlignmentError("alignment serialization is invalid") from error
    validate_alignment(value, registry, upstream_records)
    return value


def validate_alignment(
    alignment: dict[str, Any], registry: dict[str, Any],
    upstream_records: list[dict[str, Any]],
) -> None:
    fields = {
        "schema_version", "alignment_id", "project_id", "registry_binding",
        "sources", "artifact_catalog", "created_at", "updated_at", "revision", "nodes", "links",
        "semantic_authority", "source_artifacts_modified", "record_sha256",
    }
    if not isinstance(alignment, dict) or set(alignment) != fields:
        raise AlignmentError("alignment fields differ from v1")
    if alignment["schema_version"] != "1.0":
        raise AlignmentError("alignment schema version is unsupported")
    _urn(alignment["alignment_id"], "alignment ID")
    _urn(alignment["project_id"], "project ID")
    _timestamp(alignment["created_at"])
    if _timestamp(alignment["updated_at"]) < _timestamp(alignment["created_at"]):
        raise AlignmentError("alignment update predates creation")
    if isinstance(alignment["revision"], bool) or not isinstance(alignment["revision"], int) or alignment["revision"] < 0:
        raise AlignmentError("alignment revision is invalid")
    if alignment["semantic_authority"] != "MACHINE_ALIGNMENT_REQUIRES_HUMAN_DECISION":
        raise AlignmentError("alignment semantic authority changed")
    if alignment["source_artifacts_modified"] is not False:
        raise AlignmentError("alignment claims source artifact mutation")
    if not isinstance(alignment["nodes"], list) or not isinstance(alignment["links"], list):
        raise AlignmentError("alignment nodes and links must be lists")
    if alignment["revision"] != len(alignment["nodes"]) + len(alignment["links"]):
        raise AlignmentError("alignment revision does not match its mutation history")
    _validate_registry_binding(alignment, registry)
    catalog = _artifact_catalog(
        alignment["artifact_catalog"].get("references", [])
        if isinstance(alignment["artifact_catalog"], dict) else [],
        upstream_records,
        registry,
        alignment["sources"],
    )
    if canonical_json(alignment["artifact_catalog"]) != canonical_json(catalog):
        raise AlignmentError("authoritative artifact catalog differs")
    node_ids: set[str] = set()
    node_native_ids: set[str] = set()
    for node in alignment["nodes"]:
        _validate_node(alignment, node)
        if node["node_id"] in node_ids:
            raise AlignmentError("alignment node ID is duplicated")
        if node["native_id"] in node_native_ids:
            raise AlignmentError("alignment node native ID is duplicated")
        node_ids.add(node["node_id"])
        node_native_ids.add(node["native_id"])
    nodes = {item["node_id"]: item for item in alignment["nodes"]}
    link_ids: set[str] = set()
    link_native_ids: set[str] = set()
    for link in alignment["links"]:
        _validate_link(alignment, nodes, link)
        if link["link_id"] in link_ids:
            raise AlignmentError("alignment link ID is duplicated")
        if link["native_id"] in link_native_ids:
            raise AlignmentError("alignment link native ID is duplicated")
        link_ids.add(link["link_id"])
        link_native_ids.add(link["native_id"])
    if alignment["nodes"] != sorted(alignment["nodes"], key=lambda item: item["node_id"]):
        raise AlignmentError("alignment nodes are not sorted")
    if alignment["links"] != sorted(alignment["links"], key=lambda item: item["link_id"]):
        raise AlignmentError("alignment links are not sorted")
    _sha(alignment["record_sha256"], "alignment record hash")
    if _record_hash(alignment, "record_sha256") != alignment["record_sha256"]:
        raise AlignmentError("alignment record hash differs")


def _validate_registry_binding(alignment: dict[str, Any], registry: dict[str, Any]) -> None:
    _validate_registry(registry)
    binding = alignment["registry_binding"]
    if not isinstance(binding, dict) or set(binding) != {
        "registry_id", "registry_record_sha256", "project_record_sha256"
    }:
        raise AlignmentError("alignment registry binding is invalid")
    if not isinstance(alignment["sources"], list):
        raise AlignmentError("alignment source bindings must be a list")
    project = _find(registry["projects"], "project_id", alignment["project_id"], "project")
    if (
        binding["registry_id"] != registry["registry_id"]
        or binding["registry_record_sha256"] != registry["record_sha256"]
        or binding["project_record_sha256"] != content_sha256(project)
    ):
        raise AlignmentError("authoritative registry snapshot differs")
    expected_sources = []
    for stored in alignment["sources"]:
        if not isinstance(stored, dict) or set(stored) != {
            "source_id", "source_revision_id", "source_revision_sha256",
            "source_type", "source_record_sha256",
        }:
            raise AlignmentError("alignment source binding fields are invalid")
        source, revision = _source_revision(registry, stored["source_revision_id"])
        expected = {
            "source_id": source["source_id"],
            "source_revision_id": revision["revision_id"],
            "source_revision_sha256": revision["revision_sha256"],
            "source_type": source["source_type"],
            "source_record_sha256": content_sha256(source),
        }
        if stored != expected or source["current_revision_id"] != revision["revision_id"]:
            raise AlignmentError("alignment source differs from authoritative registry")
        expected_sources.append(expected)
    if len(expected_sources) < 2 or len({item["source_id"] for item in expected_sources}) != len(expected_sources):
        raise AlignmentError("alignment does not bind distinct sources")
    if alignment["sources"] != sorted(expected_sources, key=lambda item: item["source_revision_id"]):
        raise AlignmentError("alignment source bindings are not canonical")
    identity_sha256 = content_sha256({
        "project_id": alignment["project_id"], "registry_binding": binding,
        "sources": alignment["sources"],
        "artifact_catalog_sha256": alignment["artifact_catalog"]["catalog_sha256"],
    })
    expected_id = derive_imported_id(
        "artifact", "integra.multi_source_alignment", alignment["project_id"], identity_sha256
    )
    if alignment["alignment_id"] != expected_id:
        raise AlignmentError("alignment stable identity differs")


def _validate_node(alignment: dict[str, Any], node: dict[str, Any]) -> None:
    fields = {
        "node_id", "native_id", "kind", "source_id", "source_revision_id",
        "artifact_id", "artifact_sha256", "owner_component", "locators",
        "lineage_ids", "semantic_status", "created_at", "node_sha256",
    }
    if not isinstance(node, dict) or set(node) != fields:
        raise AlignmentError("alignment node fields are invalid")
    _urn(node["node_id"], "node ID")
    _urn(node["artifact_id"], "node artifact ID")
    _sha(node["artifact_sha256"], "node artifact hash")
    _text(node["native_id"], "node native ID")
    _text(node["owner_component"], "node owner component")
    created_at = _timestamp(node["created_at"])
    if created_at < _timestamp(alignment["created_at"]) or created_at > _timestamp(alignment["updated_at"]):
        raise AlignmentError("alignment node timestamp is outside its graph history")
    if node["kind"] not in NODE_KINDS or node["semantic_status"] not in SEMANTIC_STATES:
        raise AlignmentError("alignment node kind or semantic status is invalid")
    if node["kind"] in {"TRANSCRIPT", "TOPIC", "EVIDENCE"} and node["semantic_status"] == "NOT_APPLICABLE":
        raise AlignmentError("semantic node bypasses review authority")
    binding = _bound_source(alignment, node["source_id"], node["source_revision_id"])
    locators = _normalize_locators(node["locators"])
    if canonical_json(node["locators"]) != canonical_json(locators):
        raise AlignmentError("alignment node locators are not canonical")
    _require_native_locator(binding["source_type"], locators)
    _require_revision_locator(binding, locators)
    _require_kind_source(node["kind"], binding["source_type"], locators)
    _unique_text(node["lineage_ids"], "node lineage", non_empty=True)
    if node["lineage_ids"] != sorted(node["lineage_ids"]) or node["artifact_id"] not in node["lineage_ids"]:
        raise AlignmentError("node lineage is invalid")
    reference = _find(
        alignment["artifact_catalog"]["references"], "artifact_id", node["artifact_id"],
        "upstream artifact reference",
    )
    source_locator = reference["source_locator"]
    if (
        reference["kind"] != node["kind"]
        or reference["content_sha256"] != node["artifact_sha256"]
        or reference["owner_component"] != node["owner_component"]
        or reference.get("semantic_status") != node["semantic_status"]
        or source_locator["native_id"] != node["native_id"]
        or source_locator["source_id"] != node["source_id"]
        or source_locator["source_revision_id"] != node["source_revision_id"]
        or canonical_json(source_locator["locators"]) != canonical_json(node["locators"])
        or sorted(reference["parent_artifact_ids"] + [node["artifact_id"]]) != node["lineage_ids"]
    ):
        raise AlignmentError("node differs from authoritative upstream artifact reference")
    identity_sha256 = content_sha256({
        "owner_component": node["owner_component"], "native_id": node["native_id"],
        "artifact_id": node["artifact_id"], "artifact_sha256": node["artifact_sha256"],
        "source_revision_id": node["source_revision_id"],
    })
    if node["node_id"] != derive_imported_id(
        "evidence", node["owner_component"], node["native_id"], identity_sha256
    ):
        raise AlignmentError("alignment node stable identity differs")
    if node["node_sha256"] != _record_hash(node, "node_sha256"):
        raise AlignmentError("alignment node hash differs")


def _validate_link(
    alignment: dict[str, Any], nodes: dict[str, dict[str, Any]], link: dict[str, Any]
) -> None:
    fields = {
        "link_id", "native_id", "relation", "from_node_id", "from_node_sha256",
        "to_node_id", "to_node_sha256", "evidence", "method", "confidence",
        "conflict", "semantic_status", "created_at", "scope_sha256",
    }
    if not isinstance(link, dict) or set(link) != fields:
        raise AlignmentError("alignment link fields are invalid")
    _urn(link["link_id"], "link ID")
    _urn(link["from_node_id"], "link source node ID")
    _urn(link["to_node_id"], "link target node ID")
    if not isinstance(link["relation"], str) or link["relation"] not in RELATIONS:
        raise AlignmentError("alignment link relation is unsupported")
    source = nodes.get(link["from_node_id"])
    target = nodes.get(link["to_node_id"])
    if source is None or target is None:
        raise AlignmentError("alignment link source binding is invalid")
    if link["relation"] != "VIDEO_TO_TRANSCRIPT" and source["source_id"] == target["source_id"]:
        raise AlignmentError("alignment link must connect distinct sources")
    if link["relation"] == "VIDEO_TO_TRANSCRIPT" and (
        source["source_id"] != target["source_id"]
        or source["source_revision_id"] != target["source_revision_id"]
    ):
        raise AlignmentError("video and transcript must share one source revision")
    allowed_from, allowed_to = RELATIONS.get(link["relation"], (set(), set()))
    if source["kind"] not in allowed_from or target["kind"] not in allowed_to:
        raise AlignmentError("alignment link relation endpoints are invalid")
    if link["from_node_sha256"] != source["node_sha256"] or link["to_node_sha256"] != target["node_sha256"]:
        raise AlignmentError("alignment link node binding is stale")
    if not isinstance(link["evidence"], list) or any(not isinstance(item, dict) for item in link["evidence"]):
        raise AlignmentError("alignment evidence bindings must be a list of records")
    _unique_text([item.get("node_id") for item in link["evidence"]], "alignment evidence", non_empty=True)
    expected_evidence = []
    for item in sorted(link["evidence"], key=lambda value: value.get("node_id", "")):
        if not isinstance(item, dict) or set(item) != {"node_id", "node_sha256"}:
            raise AlignmentError("alignment evidence binding fields are invalid")
        node = nodes.get(item["node_id"])
        if node is None or node["node_sha256"] != item["node_sha256"]:
            raise AlignmentError("alignment evidence binding is stale")
        expected_evidence.append(item)
    if link["evidence"] != expected_evidence:
        raise AlignmentError("alignment evidence bindings are not canonical")
    _text(link["native_id"], "link native ID")
    _text(link["method"], "alignment method")
    confidence = _probability(link["confidence"], "alignment confidence")
    if not isinstance(link["conflict"], bool):
        raise AlignmentError("alignment conflict is invalid")
    expected_status = "REVIEW_REQUIRED" if link["conflict"] or confidence < 0.8 else "PROVISIONAL"
    if link["semantic_status"] != expected_status:
        raise AlignmentError("alignment semantic authority differs")
    created_at = _timestamp(link["created_at"])
    if created_at < _timestamp(alignment["created_at"]) or created_at > _timestamp(alignment["updated_at"]):
        raise AlignmentError("alignment link timestamp is outside its graph history")
    scope = {
        "relation": link["relation"], "from_node_id": link["from_node_id"],
        "from_node_sha256": link["from_node_sha256"], "to_node_id": link["to_node_id"],
        "to_node_sha256": link["to_node_sha256"], "evidence": link["evidence"],
        "method": link["method"], "confidence": confidence, "conflict": link["conflict"],
    }
    if link["scope_sha256"] != content_sha256(scope):
        raise AlignmentError("alignment link scope hash differs")
    if link["link_id"] != derive_imported_id(
        "evidence", "integra.alignment", link["native_id"], link["scope_sha256"]
    ):
        raise AlignmentError("alignment link stable identity differs")


def _hop(link: dict[str, Any], node: dict[str, Any], direction: str) -> dict[str, Any]:
    return {
        "direction": direction,
        "link_id": link["link_id"],
        "relation": link["relation"],
        "semantic_status": link["semantic_status"],
        "node_id": node["node_id"],
        "node_kind": node["kind"],
        "source_id": node["source_id"],
        "source_revision_id": node["source_revision_id"],
        "artifact_id": node["artifact_id"],
        "artifact_sha256": node["artifact_sha256"],
        "locators": copy.deepcopy(node["locators"]),
    }


def _validated_upstream_records(
    values: Any, registry: dict[str, Any], bindings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not isinstance(values, list) or not values:
        raise AlignmentError("alignment requires validated upstream records")
    result: list[dict[str, Any]] = []
    ids: set[str] = set()
    for raw in values:
        if not isinstance(raw, dict) or set(raw) != {
            "contract", "record_id", "record_sha256", "record"
        }:
            raise AlignmentError("upstream record binding fields are invalid")
        item = copy.deepcopy(raw)
        record = item["record"]
        if item["contract"] == "DOCUMENT_EXTRACTION_V1":
            try:
                validate_document_record(record)
            except (DocumentError, KeyError, TypeError) as error:
                raise AlignmentError("upstream document record is invalid") from error
            expected_id = record["document_id"]
            expected_hash = record["record_sha256"]
            source_id = record["source"]["source_id"]
            matches = [value for value in bindings if value["source_id"] == source_id]
            if len(matches) != 1:
                raise AlignmentError("upstream document is not an alignment source")
            source, revision = _source_revision(registry, matches[0]["source_revision_id"])
            provenance = revision["provenance"]
            if (
                provenance.get("document_id") != expected_id
                or provenance.get("document_record_sha256") != expected_hash
            ):
                raise AlignmentError("document registry provenance differs from upstream record")
        elif item["contract"] == "TRANSCRIPT_TOPIC_STUDIO_V1":
            try:
                validate_studio(record, registry)
            except (StudioError, KeyError, TypeError) as error:
                raise AlignmentError("upstream Transcript & Topic Studio record is invalid") from error
            expected_id = record["studio_id"]
            expected_hash = record["record_sha256"]
            if not any(
                value["source_id"] == record["source"]["source_id"]
                and value["source_revision_id"] == record["source"]["source_revision_id"]
                for value in bindings
            ):
                raise AlignmentError("upstream Studio is not bound to an alignment source")
        else:
            raise AlignmentError("upstream record contract is unsupported")
        if item["record_id"] != expected_id or item["record_sha256"] != expected_hash:
            raise AlignmentError("upstream record identity or hash differs")
        if item["record_id"] in ids:
            raise AlignmentError("upstream record ID is duplicated")
        ids.add(item["record_id"])
        result.append(item)
    result.sort(key=lambda item: item["record_id"])
    return result


def _validate_reference_against_upstream(
    reference: dict[str, Any], upstream: dict[str, Any],
    binding: dict[str, Any], locators: list[dict[str, Any]],
    supplied_origin: dict[str, Any] | None,
) -> None:
    locator = reference["source_locator"]
    if upstream["contract"] == "DOCUMENT_EXTRACTION_V1":
        record = upstream["record"]
        kind = reference["kind"]
        allowed = {
            "PPTX": {"SLIDE", "SUPPORTING_DOCUMENT"},
            "PDF": {"PAGE", "SUPPORTING_DOCUMENT"},
            "DOCX": {"SUPPORTING_DOCUMENT"},
            "TXT": {"SUPPORTING_DOCUMENT"},
            "MARKDOWN": {"SUPPORTING_DOCUMENT"},
            "IMAGE": {"PAGE", "SUPPORTING_DOCUMENT"},
        }[record["source"]["format"]]
        if kind not in allowed:
            raise AlignmentError("document node kind differs from upstream format")
        blocks = record["native_extraction"]["blocks"] + record["ocr"]["blocks"]
        block = _find(
            blocks, "block_id", locator["upstream_entity_id"],
            "upstream document block",
        )
        expected_locators = _document_block_locators(block, binding)
        if canonical_json(locators) != canonical_json(expected_locators):
            raise AlignmentError("document locators differ from exact upstream block")
        selection_hash = content_sha256({
            "record_sha256": upstream["record_sha256"], "kind": kind,
            "native_id": locator["native_id"], "block_id": block["block_id"],
            "block_sha256": block["text_sha256"], "locators": locators,
        })
        expected_id = derive_imported_id(
            "artifact", "integra.document_pipeline", locator["native_id"], selection_hash
        )
        expected_content_hash = content_sha256({
            "record_sha256": upstream["record_sha256"],
            "block_id": block["block_id"], "block_sha256": block["text_sha256"],
            "locators": locators,
        })
        if (
            reference["artifact_id"] != expected_id
            or reference["content_sha256"] != expected_content_hash
            or reference["owner_component"] != "integra.document_pipeline"
            or reference["parent_artifact_ids"] != [record["document_id"]]
            or reference["semantic_status"] != "PROVISIONAL"
        ):
            raise AlignmentError("document artifact reference differs from validated upstream record")
        if supplied_origin is not None and (
            supplied_origin["component_id"] != "integra.document_pipeline"
            or "document_extraction_v1" not in supplied_origin["contracts"]
        ):
            raise AlignmentError("document artifact origin differs")
        count = record.get("page_or_slide_count")
        for value in locators:
            if value["type"] == "PAGE_RANGE" and (count is None or value["end_page"] > count):
                raise AlignmentError("document page locator exceeds upstream record")
            if value["type"] == "SLIDE_RANGE" and (count is None or value["end_slide"] > count):
                raise AlignmentError("document slide locator exceeds upstream record")
        return

    studio = upstream["record"]
    if locator["upstream_entity_id"] != reference["artifact_id"]:
        raise AlignmentError("Studio locator does not identify its upstream entity")
    entity, capability, expected_kind, expected_hash, parents = _studio_entity(
        studio, reference["artifact_id"], binding["source_type"]
    )
    accepted_binding = studio["component_bindings"][capability]
    matching_origins = [
        item for item in accepted_binding["components"]
        if item["component_id"] == reference["owner_component"]
    ]
    if len(matching_origins) != 1:
        raise AlignmentError("artifact origin differs from accepted Studio component binding")
    if supplied_origin is not None:
        accepted_origin = matching_origins[0]
        if (
            supplied_origin["commit_sha"] != accepted_origin["commit_sha"]
            or accepted_origin["contract_id"] not in supplied_origin["contracts"]
        ):
            raise AlignmentError("artifact origin differs from accepted Studio component binding")
        model = accepted_origin.get("model_id")
        model_sha = accepted_origin.get("model_sha256")
        if model is not None and {
            "id": model, "identity_sha256": model_sha
        } not in supplied_origin.get("models", []):
            raise AlignmentError("artifact model differs from accepted Studio binding")
    if (
        reference["kind"] != expected_kind
        or reference["content_sha256"] != expected_hash
        or locator["native_id"] != entity["native_id"]
        or canonical_json(locator["locators"]) != canonical_json(_normalize_locators(entity["locators"]))
        or reference["semantic_status"] != entity["semantic_status"]
        or reference["parent_artifact_ids"] != sorted(parents)
    ):
        raise AlignmentError("artifact reference differs from validated upstream Studio record")


def _studio_entity(
    studio: dict[str, Any], artifact_id: str, source_type: str,
) -> tuple[dict[str, Any], str, str, str, list[str]]:
    artifacts = [item for item in studio["artifacts"] if item["artifact_id"] == artifact_id]
    if artifacts:
        item = artifacts[0]
        kind_map = {
            "MEDIA_PREPARATION": "AUDIO" if source_type == "LOCAL_AUDIO" else "VIDEO",
            "MACHINE_TRANSCRIPT": "TRANSCRIPT",
        }
        kind = kind_map.get(item["kind"])
        if kind is None:
            raise AlignmentError("Studio artifact kind is not alignable in v1")
        return item, item["capability"], kind, item["content_sha256"], item["parent_ids"]
    for topic_set in studio["topic_sets"]:
        matches = [item for item in topic_set["topics"] if item["topic_id"] == artifact_id]
        if matches:
            item = matches[0]
            return (
                item, "topics", "TOPIC", content_sha256(item),
                [topic_set["topic_set_id"], topic_set["timeline_id"]],
            )
    findings = [item for item in studio["quality_findings"] if item["finding_id"] == artifact_id]
    if findings:
        item = copy.deepcopy(findings[0])
        item["semantic_status"] = "REVIEW_REQUIRED" if item["review_required"] else "PROVISIONAL"
        return item, "quality_validation", "EVIDENCE", item["finding_sha256"], [item["artifact_id"]]
    raise AlignmentError("artifact reference is absent from validated upstream Studio record")


def _artifact_catalog(
    references: Any, upstream_records: Any, registry: dict[str, Any],
    bindings: list[dict[str, Any]],
) -> dict[str, Any]:
    if not isinstance(references, list) or not references:
        raise AlignmentError("authoritative artifact catalog must be a non-empty list")
    records = _validated_upstream_records(upstream_records, registry, bindings)
    normalized: list[dict[str, Any]] = []
    artifact_ids: set[str] = set()
    for raw in references:
        supplied_origin = None
        if isinstance(raw, dict) and set(raw) == {
            "artifact_id", "kind", "content_sha256", "semantic_status",
            "owner_component", "parent_artifact_ids", "source_locator",
        }:
            reference = copy.deepcopy(raw)
        else:
            try:
                validate_artifact_reference(raw)
            except ProtocolViolation as error:
                raise AlignmentError("upstream artifact reference is invalid") from error
            supplied_origin = copy.deepcopy(raw["origin"])
            reference = {
                "artifact_id": raw["artifact_id"], "kind": raw["kind"],
                "content_sha256": raw["content_sha256"],
                "semantic_status": raw.get("semantic_status"),
                "owner_component": raw["origin"]["component_id"],
                "parent_artifact_ids": copy.deepcopy(
                    raw["provenance"]["parent_artifact_ids"]
                ),
                "source_locator": copy.deepcopy(
                    raw["provenance"].get("source_locator")
                ),
            }
        if reference.get("kind") not in NODE_KINDS or "semantic_status" not in reference:
            raise AlignmentError("upstream artifact kind or semantic status is invalid")
        artifact_id = reference["artifact_id"]
        if artifact_id in artifact_ids:
            raise AlignmentError("upstream artifact reference is duplicated")
        artifact_ids.add(artifact_id)
        locator = reference.get("source_locator")
        required = {
            "native_id", "source_id", "source_revision_id",
            "source_revision_sha256", "upstream_record_id",
            "upstream_record_sha256", "upstream_entity_id", "locators",
        }
        if not isinstance(locator, dict) or set(locator) != required:
            raise AlignmentError("upstream artifact source locator differs from R8C")
        _text(locator["native_id"], "upstream artifact native ID")
        _urn(locator["source_id"], "upstream artifact source ID")
        _urn(locator["source_revision_id"], "upstream artifact source revision ID")
        _sha(locator["source_revision_sha256"], "upstream artifact source revision hash")
        _urn(locator["upstream_record_id"], "upstream record ID")
        _sha(locator["upstream_record_sha256"], "upstream record hash")
        _urn(locator["upstream_entity_id"], "upstream entity ID")
        matches = [
            item for item in bindings
            if item["source_id"] == locator["source_id"]
            and item["source_revision_id"] == locator["source_revision_id"]
        ]
        if len(matches) != 1 or matches[0]["source_revision_sha256"] != locator["source_revision_sha256"]:
            raise AlignmentError("upstream artifact is not bound to an alignment source revision")
        locators = _normalize_locators(locator["locators"])
        _require_native_locator(matches[0]["source_type"], locators)
        _require_revision_locator(matches[0], locators)
        _require_kind_source(reference["kind"], matches[0]["source_type"], locators)
        locator["locators"] = locators
        _text(reference["owner_component"], "upstream artifact owner component")
        parents = reference["parent_artifact_ids"]
        if artifact_id in parents:
            raise AlignmentError("upstream artifact cannot be its own parent")
        reference["parent_artifact_ids"] = sorted(parents)
        upstream = _find(records, "record_id", locator["upstream_record_id"], "upstream record")
        if upstream["record_sha256"] != locator["upstream_record_sha256"]:
            raise AlignmentError("upstream record hash binding differs")
        _validate_reference_against_upstream(
            reference, upstream, matches[0], locators, supplied_origin
        )
        normalized.append(reference)
    normalized.sort(key=lambda item: item["artifact_id"])
    record_bindings = [
        {key: item[key] for key in ("contract", "record_id", "record_sha256")}
        for item in records
    ]
    value = {
        "schema_version": "1.0", "upstream_record_bindings": record_bindings,
        "references": normalized, "catalog_sha256": "",
    }
    value["catalog_sha256"] = _record_hash(value, "catalog_sha256")
    return value


def _document_block_locators(
    block: dict[str, Any], binding: dict[str, Any],
) -> list[dict[str, Any]]:
    """Resolve one extraction block to exact R8C locators."""

    locator = block["locator"]
    unit_kind = locator["unit_kind"]
    unit_index = locator["unit_index"]
    result: list[dict[str, Any]] = []
    if unit_kind == "PAGE":
        result.append({
            "type": "PAGE_RANGE", "start_page": unit_index, "end_page": unit_index,
        })
    elif unit_kind == "SLIDE":
        result.append({
            "type": "SLIDE_RANGE", "start_slide": unit_index, "end_slide": unit_index,
        })
    elif unit_kind in {"DOCUMENT", "PARAGRAPH", "SLIDE_NOTES"}:
        result.append({
            "type": "CHARACTER_RANGE",
            "start_char": locator["character_start"],
            "end_char": locator["character_end"],
        })
    elif unit_kind != "IMAGE":
        raise AlignmentError("document block unit is not alignable in v1")
    region = locator["region"]
    if region is not None:
        container = {
            "PAGE": "PAGE", "SLIDE": "SLIDE", "IMAGE": "IMAGE"
        }.get(unit_kind)
        if container is None:
            raise AlignmentError("document block region lacks a supported container")
        result.append({
            "type": "REGION", "container_type": container,
            "container_index": unit_index, **region,
        })
    if not result:
        raise AlignmentError("document block lacks an exact alignable locator")
    result.append({
        "type": "ARTIFACT_REVISION", "artifact_id": binding["source_id"],
        "revision_id": binding["source_revision_id"],
        "content_sha256": binding["source_revision_sha256"],
    })
    return _normalize_locators(result)


def _locator(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("type") not in LOCATOR_TYPES:
        raise AlignmentError("alignment locator type is invalid")
    kind = value["type"]
    fields = {
        "TIME_INTERVAL": {"type", "start_seconds", "end_seconds"},
        "WORD_INTERVAL": {"type", "start_word_id", "end_word_id", "start_sequence", "end_sequence"},
        "PAGE_RANGE": {"type", "start_page", "end_page"},
        "SLIDE_RANGE": {"type", "start_slide", "end_slide"},
        "REGION": {"type", "container_type", "container_index", "x", "y", "width", "height"},
        "CHARACTER_RANGE": {"type", "start_char", "end_char"},
        "ARTIFACT_REVISION": {"type", "artifact_id", "revision_id", "content_sha256"},
    }
    if set(value) != fields[kind]:
        raise AlignmentError("alignment locator fields are invalid")
    result = copy.deepcopy(value)
    if kind == "TIME_INTERVAL":
        start, end = _number(value["start_seconds"]), _number(value["end_seconds"])
        if start < 0 or end <= start:
            raise AlignmentError("time locator is invalid")
        result["start_seconds"] = start
        result["end_seconds"] = end
    elif kind == "WORD_INTERVAL":
        _text(value["start_word_id"], "start word ID")
        _text(value["end_word_id"], "end word ID")
        start, end = _integer(value["start_sequence"], 0), _integer(value["end_sequence"], 0)
        if end < start:
            raise AlignmentError("word locator is reversed")
    elif kind in {"PAGE_RANGE", "SLIDE_RANGE"}:
        prefix = "page" if kind == "PAGE_RANGE" else "slide"
        start = _integer(value[f"start_{prefix}"], 1)
        end = _integer(value[f"end_{prefix}"], 1)
        if end < start:
            raise AlignmentError(f"{prefix} locator is reversed")
    elif kind == "CHARACTER_RANGE":
        start, end = _integer(value["start_char"], 0), _integer(value["end_char"], 1)
        if end <= start:
            raise AlignmentError("character locator is empty")
    elif kind == "REGION":
        if value["container_type"] not in {"PAGE", "SLIDE", "IMAGE"}:
            raise AlignmentError("region container is invalid")
        _integer(value["container_index"], 1)
        for field in ("x", "y", "width", "height"):
            number = _number(value[field])
            if number < 0 or number > 1:
                raise AlignmentError("region coordinate is invalid")
            result[field] = number
        if value["width"] <= 0 or value["height"] <= 0 or value["x"] + value["width"] > 1 or value["y"] + value["height"] > 1:
            raise AlignmentError("region lies outside its container")
    else:
        _urn(value["artifact_id"], "locator artifact ID")
        _urn(value["revision_id"], "locator revision ID")
        _sha(value["content_sha256"], "locator content hash")
    return result


def _normalize_locators(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise AlignmentError("alignment node requires exact locators")
    normalized = [_locator(item) for item in value]
    keys = [canonical_json(item) for item in normalized]
    if len(keys) != len(set(keys)):
        raise AlignmentError("alignment locators are duplicated")
    return [item for _, item in sorted(zip(keys, normalized), key=lambda pair: pair[0])]


def _require_native_locator(source_type: str, locators: list[dict[str, Any]]) -> None:
    kinds = {item["type"] for item in locators}
    accepted = {
        "LOCAL_VIDEO": {"TIME_INTERVAL", "WORD_INTERVAL"},
        "LOCAL_AUDIO": {"TIME_INTERVAL", "WORD_INTERVAL"},
        "YOUTUBE_VIDEO": {"TIME_INTERVAL", "WORD_INTERVAL"},
        "YOUTUBE_PLAYLIST": {"TIME_INTERVAL", "WORD_INTERVAL"},
        "PDF": {"PAGE_RANGE", "REGION"},
        "PPTX": {"SLIDE_RANGE", "REGION"},
        "DOCX": {"CHARACTER_RANGE"},
        "TXT": {"CHARACTER_RANGE"},
        "MARKDOWN": {"CHARACTER_RANGE"},
        "IMAGE": {"REGION"},
        "SCAN": {"REGION"},
    }.get(source_type)
    if accepted is None or not kinds.intersection(accepted):
        raise AlignmentError("node lacks a source-type-native locator")
    expected_region = {"PDF": "PAGE", "PPTX": "SLIDE", "IMAGE": "IMAGE", "SCAN": "PAGE"}.get(source_type)
    if expected_region and any(
        item["type"] == "REGION" and item["container_type"] != expected_region
        for item in locators
    ):
        raise AlignmentError("region container differs from source type")


def _require_kind_source(
    kind: str, source_type: str, locators: list[dict[str, Any]],
) -> None:
    allowed_sources = {
        "VIDEO": {"LOCAL_VIDEO", "YOUTUBE_VIDEO"},
        "AUDIO": {"LOCAL_AUDIO"},
        "SLIDE": {"PPTX"},
        "PAGE": {"PDF", "SCAN"},
        "SUPPORTING_DOCUMENT": {"PDF", "PPTX", "DOCX", "TXT", "MARKDOWN", "IMAGE", "SCAN"},
    }.get(kind)
    if allowed_sources is not None and source_type not in allowed_sources:
        raise AlignmentError("node kind is incompatible with source type")
    kinds = {item["type"] for item in locators}
    required_locator = {
        "VIDEO": "TIME_INTERVAL",
        "AUDIO": "TIME_INTERVAL",
        "SLIDE": "SLIDE_RANGE",
        "PAGE": "PAGE_RANGE",
    }.get(kind)
    if required_locator is not None and required_locator not in kinds:
        raise AlignmentError("node kind lacks its exact native locator")
    page_ranges = [item for item in locators if item["type"] == "PAGE_RANGE"]
    slide_ranges = [item for item in locators if item["type"] == "SLIDE_RANGE"]
    if kind == "PAGE" and len(page_ranges) != 1:
        raise AlignmentError("page node requires exactly one page range")
    if kind == "SLIDE" and len(slide_ranges) != 1:
        raise AlignmentError("slide node requires exactly one slide range")
    for region in (item for item in locators if item["type"] == "REGION"):
        if region["container_type"] == "PAGE":
            if page_ranges and (
                len(page_ranges) != 1
                or not page_ranges[0]["start_page"] <= region["container_index"] <= page_ranges[0]["end_page"]
            ):
                raise AlignmentError("region is outside the node page range")
        elif region["container_type"] == "SLIDE":
            if slide_ranges and (
                len(slide_ranges) != 1
                or not slide_ranges[0]["start_slide"] <= region["container_index"] <= slide_ranges[0]["end_slide"]
            ):
                raise AlignmentError("region is outside the node slide range")


def _require_revision_locator(binding: dict[str, Any], locators: list[dict[str, Any]]) -> None:
    expected = {
        "type": "ARTIFACT_REVISION", "artifact_id": binding["source_id"],
        "revision_id": binding["source_revision_id"],
        "content_sha256": binding["source_revision_sha256"],
    }
    revision_locators = [item for item in locators if item["type"] == "ARTIFACT_REVISION"]
    if revision_locators != [expected]:
        raise AlignmentError("node does not bind its source revision exactly")


def _bound_source(alignment: dict[str, Any], source_id: str, revision_id: str) -> dict[str, Any]:
    matches = [
        item for item in alignment["sources"]
        if item["source_id"] == source_id and item["source_revision_id"] == revision_id
    ]
    if len(matches) != 1:
        raise AlignmentError("node source is not bound to alignment")
    return matches[0]


def _source_revision(registry: dict[str, Any], revision_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    matches = []
    for source in registry["sources"]:
        for revision in source["revisions"]:
            if revision["revision_id"] == revision_id:
                matches.append((source, revision))
    if len(matches) != 1:
        raise AlignmentError("source revision is missing or ambiguous")
    return matches[0]


def _validate_registry(registry: dict[str, Any]) -> None:
    try:
        validate_registry(registry)
    except RegistryError as error:
        raise AlignmentError("Projects & Sources registry is invalid") from error


def _find(items: list[dict[str, Any]], field: str, value: str, label: str, *, required: bool = True) -> dict[str, Any] | None:
    matches = [item for item in items if item.get(field) == value]
    if len(matches) > 1:
        raise AlignmentError(f"duplicate {label}")
    if not matches:
        if required:
            raise AlignmentError(f"{label} not found")
        return None
    return matches[0]


def _seal(value: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(value)
    result["record_sha256"] = _record_hash(result, "record_sha256")
    return result


def _advance(value: dict[str, Any], occurred_at: str) -> dict[str, Any]:
    if _timestamp(occurred_at) < _timestamp(value["updated_at"]):
        raise AlignmentError("alignment update time moves backwards")
    value["updated_at"] = occurred_at
    value["revision"] += 1
    return _seal(value)


def _record_hash(value: dict[str, Any], field: str) -> str:
    unsigned = copy.deepcopy(value)
    unsigned[field] = ""
    return content_sha256(unsigned)


def _timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise AlignmentError("timestamp must be canonical UTC")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise AlignmentError("timestamp is invalid") from error
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise AlignmentError("timestamp must be UTC")
    return parsed


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AlignmentError(f"{label} must be non-empty text")
    return value


def _unique_text(value: Any, label: str, *, non_empty: bool = False) -> None:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise AlignmentError(f"{label} must be a text list")
    if len(value) != len(set(value)) or (non_empty and not value):
        raise AlignmentError(f"{label} must contain unique values")


def _sha(value: Any, label: str) -> None:
    if not isinstance(value, str) or not SHA256.fullmatch(value):
        raise AlignmentError(f"{label} must be a lowercase SHA-256")


def _urn(value: Any, label: str) -> None:
    if not isinstance(value, str) or not URN.fullmatch(value):
        raise AlignmentError(f"{label} must be an Integra URN")


def _number(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AlignmentError("locator value must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise AlignmentError("locator value must be finite")
    return number


def _integer(value: Any, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise AlignmentError("locator value must be an integer in range")
    return value


def _probability(value: Any, label: str) -> float:
    number = _number(value)
    if number < 0 or number > 1:
        raise AlignmentError(f"{label} must be between zero and one")
    return number
