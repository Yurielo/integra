"""Exact, fail-closed cross-component navigation for the Integra shell."""

from __future__ import annotations

import copy
from datetime import datetime, timezone
import json
import re
from typing import Any

from .documents import validate_document_record
from .identity import derive_imported_id
from .knowledge import validate_knowledge_view
from .media import validate_derivative_record, validate_media_recipe
from .multi_source_alignment import validate_alignment
from .protocol import canonical_json, content_sha256


class CrossNavigationError(RuntimeError):
    """Raised when navigation cannot be proven from current source truth."""


class NavigationUnavailableError(CrossNavigationError):
    """Raised when a known target has no currently available source."""


KINDS = {
    "KNOWLEDGE_ENTITY", "EVIDENCE", "TOPIC", "WORD_TIMELINE", "TRANSCRIPT",
    "VIDEO", "AUDIO", "DOCUMENT", "PAGE", "SLIDE", "MEDIA_SOURCE", "MEDIA_CLIP",
}
BRIDGE_RELATIONS = {
    "KNOWLEDGE_EVIDENCE_TO_ALIGNMENT_EVIDENCE": ({"EVIDENCE"}, {"EVIDENCE"}),
    "KNOWLEDGE_TOPIC_TO_ALIGNMENT_TOPIC": ({"TOPIC"}, {"TOPIC"}),
    "MEDIA_SOURCE_TO_ALIGNMENT_MEDIA": ({"MEDIA_SOURCE"}, {"VIDEO", "AUDIO"}),
}
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def build_cross_navigation(
    *, alignment: dict[str, Any], registry: dict[str, Any],
    upstream_records: list[dict[str, Any]], knowledge_view: dict[str, Any],
    evidence_payload: bytes, source_evidence_payload: bytes, knowledge_payload: bytes,
    media_records: list[dict[str, Any]], bridges: list[dict[str, str]],
    unavailable_targets: list[dict[str, str]], created_at: str,
) -> dict[str, Any]:
    """Compose validated R8C/R9A/R9B projections into one reversible UI index."""

    _timestamp(created_at)
    validate_alignment(alignment, registry, upstream_records)
    validate_knowledge_view(
        knowledge_view, evidence_payload, source_evidence_payload, knowledge_payload,
    )
    if not isinstance(media_records, list) or not media_records:
        raise CrossNavigationError("cross-navigation requires registered media records")
    validated_media = [_validate_media_record(item) for item in media_records]

    targets: dict[str, dict[str, Any]] = {}
    routes: list[dict[str, Any]] = []
    mappings = _source_mappings(
        alignment, registry, knowledge_view, evidence_payload, media_records,
    )
    sources = {
        "alignment": {"record_id": alignment["alignment_id"], "record_sha256": alignment["record_sha256"]},
        "knowledge": {"record_id": knowledge_view["view_id"], "record_sha256": knowledge_view["record_sha256"]},
        "media": [], "mappings": mappings,
    }

    _index_alignment(targets, routes, alignment)
    _index_upstream(targets, routes, upstream_records)
    _index_knowledge(targets, routes, knowledge_view)
    for recipe, derivative in validated_media:
        _index_media(targets, routes, recipe, derivative)
        sources["media"].append({
            "recipe_id": recipe["recipe_id"], "recipe_sha256": recipe["recipe_sha256"],
            "derivative_id": derivative["derivative_id"],
            "derivative_sha256": derivative["record_sha256"],
        })
    sources["media"].sort(key=lambda item: item["derivative_id"])

    _add_bridges(targets, routes, bridges, mappings)
    _add_unavailable(targets, unavailable_targets)
    ordered_targets = sorted(targets.values(), key=lambda item: item["target_id"])
    ordered_routes = _canonical_routes(routes)
    identity = content_sha256({
        "sources": sources,
        "targets": [{"target_id": item["target_id"], "target_sha256": item["target_sha256"]}
                    for item in ordered_targets],
        "routes": [{"route_id": item["route_id"], "route_sha256": item["route_sha256"]}
                   for item in ordered_routes],
    })
    value = {
        "schema_version": "1.0",
        "navigation_id": derive_imported_id(
            "artifact", "integra.cross_navigation", alignment["project_id"], identity,
        ),
        "project_id": alignment["project_id"], "sources": sources,
        "created_at": created_at, "targets": ordered_targets, "routes": ordered_routes,
        "semantic_authority": "PRESENTATION_ONLY_SOURCE_TRUTH_PRESERVED",
        "source_artifacts_modified": False, "record_sha256": "",
    }
    value["record_sha256"] = _record_hash(value)
    _validate_structure(value)
    return value


def media_source_target_id(recipe: dict[str, Any]) -> str:
    """Return the stable presentation identity for one exact media source selection."""

    validate_media_recipe(recipe)
    return derive_imported_id(
        "evidence", "integra.cross_navigation", recipe["source"]["artifact_id"],
        content_sha256({
            "source_sha256": recipe["source_sha256"],
            "source_locator": recipe["source_locator"],
        }),
    )


def _media_source_revision_id(recipe: dict[str, Any]) -> str:
    return derive_imported_id(
        "revision", "integra.cross_navigation", recipe["source"]["artifact_id"],
        recipe["source_sha256"],
    )


def navigate(index: dict[str, Any], target_id: str, *, authority: dict[str, Any]) -> dict[str, Any]:
    """Resolve one target and both directions without inventing a fallback."""

    validate_cross_navigation(index, authority=authority)
    targets = {item["target_id"]: item for item in index["targets"]}
    target = targets.get(target_id)
    if target is None:
        raise CrossNavigationError("navigation target is unknown")
    if not target["available"]:
        raise NavigationUnavailableError(target["unavailable_reason"])
    forward = [_hop(route, targets[route["to_id"]], "FORWARD") for route in index["routes"]
               if route["from_id"] == target_id]
    reverse = [_hop(route, targets[route["from_id"]], "REVERSE") for route in index["routes"]
               if route["to_id"] == target_id]
    key = lambda item: (item["relation"], item["target_id"], item["route_id"])
    return {"origin": copy.deepcopy(target), "forward": sorted(forward, key=key),
            "reverse": sorted(reverse, key=key)}


def dumps_cross_navigation(index: dict[str, Any], *, authority: dict[str, Any]) -> bytes:
    validate_cross_navigation(index, authority=authority)
    return canonical_json(index) + b"\n"


def loads_cross_navigation(payload: bytes, *, authority: dict[str, Any]) -> dict[str, Any]:
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CrossNavigationError("cross-navigation serialization is invalid") from error
    validate_cross_navigation(value, authority=authority)
    return value


def validate_cross_navigation(index: dict[str, Any], *, authority: dict[str, Any]) -> None:
    """Rebuild against current authoritative inputs and require byte-for-byte truth."""

    _validate_structure(index)
    required = {
        "alignment", "registry", "upstream_records", "knowledge_view", "evidence_payload",
        "source_evidence_payload", "knowledge_payload", "media_records", "bridges",
        "unavailable_targets",
    }
    if not isinstance(authority, dict) or set(authority) != required:
        raise CrossNavigationError("complete cross-navigation authority is required")
    rebuilt = build_cross_navigation(**authority, created_at=index["created_at"])
    if canonical_json(index) != canonical_json(rebuilt):
        raise CrossNavigationError("cross-navigation differs from current authoritative sources")


def _validate_structure(index: dict[str, Any]) -> None:
    fields = {"schema_version", "navigation_id", "project_id", "sources", "created_at",
              "targets", "routes", "semantic_authority", "source_artifacts_modified",
              "record_sha256"}
    if not isinstance(index, dict) or set(index) != fields:
        raise CrossNavigationError("cross-navigation fields differ from v1")
    if index["schema_version"] != "1.0" or index["semantic_authority"] != "PRESENTATION_ONLY_SOURCE_TRUTH_PRESERVED":
        raise CrossNavigationError("cross-navigation version or authority differs")
    if index["source_artifacts_modified"] is not False:
        raise CrossNavigationError("cross-navigation claims source mutation")
    _timestamp(index["created_at"])
    if not isinstance(index["project_id"], str) or not index["project_id"]:
        raise CrossNavigationError("cross-navigation project ID is invalid")
    _validate_sources(index["sources"])
    targets = index["targets"]
    if not isinstance(targets, list) or targets != sorted(targets, key=lambda item: item.get("target_id", "")):
        raise CrossNavigationError("navigation targets are not canonical")
    by_id: dict[str, dict[str, Any]] = {}
    for target in targets:
        _validate_target(target)
        if target["target_id"] in by_id:
            raise CrossNavigationError("navigation target ID is duplicated")
        by_id[target["target_id"]] = target
    routes = index["routes"]
    if not isinstance(routes, list) or routes != _canonical_routes(routes):
        raise CrossNavigationError("navigation routes are not canonical")
    for route in routes:
        if not isinstance(route, dict) or set(route) != {
            "route_id", "from_id", "from_sha256", "to_id", "to_sha256",
            "relation", "semantic_status", "bidirectional", "route_sha256",
        } or route["bidirectional"] is not True:
            raise CrossNavigationError("navigation route fields differ")
        if route["from_id"] not in by_id or route["to_id"] not in by_id:
            raise CrossNavigationError("navigation route endpoint is unknown")
        if (not all(isinstance(route[name], str) and route[name] for name in
                    ("route_id", "from_id", "to_id", "relation", "semantic_status"))
                or not SHA256.fullmatch(route["from_sha256"])
                or not SHA256.fullmatch(route["to_sha256"])):
            raise CrossNavigationError("navigation route binding is invalid")
        if not by_id[route["from_id"]]["available"] or not by_id[route["to_id"]]["available"]:
            raise CrossNavigationError("unavailable target cannot have a fabricated route")
        if (route["from_sha256"] != by_id[route["from_id"]]["target_sha256"] or
                route["to_sha256"] != by_id[route["to_id"]]["target_sha256"]):
            raise CrossNavigationError("navigation route endpoint binding is stale")
        if route["route_sha256"] != _record_hash(route, "route_sha256"):
            raise CrossNavigationError("navigation route hash differs")
    identity = content_sha256({
        "sources": index["sources"],
        "targets": [{"target_id": item["target_id"], "target_sha256": item["target_sha256"]}
                    for item in targets],
        "routes": [{"route_id": item["route_id"], "route_sha256": item["route_sha256"]}
                   for item in routes],
    })
    expected_id = derive_imported_id(
        "artifact", "integra.cross_navigation", index["project_id"], identity,
    )
    if index["navigation_id"] != expected_id:
        raise CrossNavigationError("cross-navigation stable identity differs")
    if index["record_sha256"] != _record_hash(index):
        raise CrossNavigationError("cross-navigation record hash differs")


def _index_alignment(targets: dict[str, dict[str, Any]], routes: list[dict[str, Any]], alignment: dict[str, Any]) -> None:
    kind_map = {"SUPPORTING_DOCUMENT": "DOCUMENT"}
    for node in alignment["nodes"]:
        _put_target(targets, node["node_id"], kind_map.get(node["kind"], node["kind"]),
                    "integra.multi_source_alignment", node["node_sha256"], node["locators"],
                    node["semantic_status"], node["source_id"], node["source_revision_id"],
                    node["artifact_id"])
    for link in alignment["links"]:
        _put_route(routes, targets, link["from_node_id"], link["to_node_id"],
                   link["relation"], link["semantic_status"], link["link_id"])


def _index_upstream(targets: dict[str, dict[str, Any]], routes: list[dict[str, Any]], records: list[dict[str, Any]]) -> None:
    for binding in records:
        record = binding["record"]
        if binding["contract"] == "TRANSCRIPT_TOPIC_STUDIO_V1":
            source_id = record["source"]["source_id"]
            source_revision_id = record["source"]["source_revision_id"]
            for artifact in record["artifacts"]:
                kind = {"MACHINE_TRANSCRIPT": "TRANSCRIPT", "WORD_TIMELINE": "WORD_TIMELINE",
                        "MEDIA_PREPARATION": "VIDEO" if record["source"]["source_type"] != "LOCAL_AUDIO" else "AUDIO"}.get(artifact["kind"])
                if kind:
                    _put_target(targets, artifact["artifact_id"], kind, "integra.transcript_topic_studio",
                                content_sha256(artifact), artifact["locators"], artifact["semantic_status"],
                                source_id, source_revision_id, artifact["artifact_id"])
            for topic_set in record["topic_sets"]:
                for topic in topic_set["topics"]:
                    _put_target(targets, topic["topic_id"], "TOPIC", "integra.transcript_topic_studio",
                                content_sha256(topic), topic["locators"], topic["semantic_status"],
                                source_id, source_revision_id, topic["topic_id"])
                    if topic_set["timeline_id"] in targets:
                        _put_route(routes, targets, topic["topic_id"], topic_set["timeline_id"],
                                   "TOPIC_TO_WORD_TIMELINE", topic["semantic_status"])
            for artifact in record["artifacts"]:
                for parent in artifact["parent_ids"]:
                    if parent in targets:
                        _put_route(routes, targets, parent, artifact["artifact_id"], "LINEAGE", "NOT_APPLICABLE")
        elif binding["contract"] == "DOCUMENT_EXTRACTION_V1":
            validate_document_record(record)
            source_id = record["source"]["source_id"]
            kind = "SLIDE" if record["source"]["format"] == "PPTX" else "PAGE" if record["source"]["format"] in {"PDF", "IMAGE"} else "DOCUMENT"
            for block in record["native_extraction"]["blocks"] + record["ocr"]["blocks"]:
                _put_target(targets, block["block_id"], kind, "integra.document_pipeline",
                            content_sha256(block), _document_locators(record, block), "PROVISIONAL",
                            source_id, record["source"]["revision_id"], record["document_id"])
    for node in [item for item in targets.values() if item["owner"] == "integra.multi_source_alignment"]:
        if node["artifact_id"] in targets:
            _put_route(routes, targets, node["target_id"], node["artifact_id"], "REPRESENTS", node["semantic_status"])


def _index_knowledge(targets: dict[str, dict[str, Any]], routes: list[dict[str, Any]], view: dict[str, Any]) -> None:
    evidence = {item["id"]: item for item in view["evidence"]}
    records = {
        item["id"]: item for name in ("seminars", "topics", "concepts", "relations", "review_decisions")
        for item in view["records"][name]
    }
    for node in view["graph"]["nodes"]:
        kind = "EVIDENCE" if node["kind"] == "EVIDENCE" else "TOPIC" if node["kind"] == "TOPIC" else "KNOWLEDGE_ENTITY"
        item = evidence.get(node["id"])
        referenced = [evidence[value] for value in records.get(node["id"], {}).get("evidence_refs", [])]
        source_pairs = sorted({
            (value["source_id"], value["transcript_revision_id"])
            for value in referenced
        })
        exact_pair = (
            (item["source_id"], item["transcript_revision_id"])
            if item else source_pairs[0] if len(source_pairs) == 1 else None
        )
        # Aggregate Knowledge nodes are presentation destinations, not source
        # destinations.  Combining locators from distinct source revisions
        # would make seek/open actions ambiguous; exact navigation remains on
        # each Evidence node connected by the source-truth graph.
        locators = (
            [item["locator"]] if item
            else [value["locator"] for value in referenced] if exact_pair else []
        )
        source_id = exact_pair[0] if exact_pair else None
        source_revision_id = exact_pair[1] if exact_pair else None
        _put_target(targets, node["id"], kind, "integra.knowledge", node["sha256"], locators,
                    node["status"], source_id, source_revision_id, node["id"])
    for edge in view["graph"]["edges"]:
        _put_route(routes, targets, edge["from_id"], edge["to_id"], edge["kind"], "SOURCE_TRUTH")


def _validate_media_record(item: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    fields = {"recipe", "derivative", "operation_plan", "job", "checkpoint",
              "model_records", "qa_reference", "qa_report"}
    if not isinstance(item, dict) or set(item) != fields:
        raise CrossNavigationError("media navigation record fields differ")
    recipe, derivative = item["recipe"], item["derivative"]
    try:
        validate_derivative_record(
            derivative, recipe, item["operation_plan"], item["job"], item["checkpoint"],
            item["model_records"], item["qa_reference"], item["qa_report"],
        )
    except (KeyError, TypeError, ValueError, RuntimeError) as error:
        raise CrossNavigationError("registered media derivative binding differs") from error
    return recipe, derivative


def _index_media(targets: dict[str, dict[str, Any]], routes: list[dict[str, Any]], recipe: dict[str, Any], derivative: dict[str, Any]) -> None:
    locator = recipe["source_locator"]
    source_target_id = media_source_target_id(recipe)
    _put_target(targets, source_target_id, "MEDIA_SOURCE", "integra.media",
                recipe["source_sha256"], [locator], recipe["source"].get("semantic_status", "NOT_APPLICABLE"),
                recipe["source"]["artifact_id"], _media_source_revision_id(recipe),
                recipe["source"]["artifact_id"])
    output = derivative["output"]
    _put_target(targets, derivative["derivative_id"], "MEDIA_CLIP", "integra.media",
                derivative["record_sha256"], [locator], "NOT_APPLICABLE",
                recipe["source"]["artifact_id"],
                derivative["derivative_id"], output["artifact_id"])
    _put_route(routes, targets, source_target_id, derivative["derivative_id"],
               "SOURCE_TO_MEDIA_CLIP", "NOT_APPLICABLE")


def _add_bridges(
    targets: dict[str, dict[str, Any]], routes: list[dict[str, Any]], bridges: Any,
    mappings: list[dict[str, str]],
) -> None:
    if not isinstance(bridges, list):
        raise CrossNavigationError("navigation bridges must be a list")
    for bridge in bridges:
        if not isinstance(bridge, dict) or set(bridge) != {"from_id", "to_id", "relation"}:
            raise CrossNavigationError("navigation bridge fields differ")
        relation = bridge["relation"]
        if relation not in BRIDGE_RELATIONS or bridge["from_id"] not in targets or bridge["to_id"] not in targets:
            raise CrossNavigationError("navigation bridge is unsupported")
        source, target = targets[bridge["from_id"]], targets[bridge["to_id"]]
        allowed_from, allowed_to = BRIDGE_RELATIONS[relation]
        if source["kind"] not in allowed_from or target["kind"] not in allowed_to:
            raise CrossNavigationError("navigation bridge endpoint kinds differ")
        mapping_kind = (
            "MEDIA_TO_ALIGNMENT_SOURCE"
            if relation == "MEDIA_SOURCE_TO_ALIGNMENT_MEDIA"
            else "KNOWLEDGE_TO_PROJECT_SOURCE"
        )
        if not any(
            item["kind"] == mapping_kind
            and item["from_source_id"] == source["source_id"]
            and item["from_revision_id"] == source["source_revision_id"]
            and item["to_source_id"] == target["source_id"]
            and item["to_revision_id"] == target["source_revision_id"]
            for item in mappings
        ):
            raise CrossNavigationError("navigation bridge lacks validated source/revision mapping")
        if not _common_locator(source["locators"], target["locators"]):
            raise CrossNavigationError("navigation bridge lacks an exact common locator")
        _put_route(routes, targets, source["target_id"], target["target_id"], relation, "EXACT_LOCATOR_MATCH")


def _add_unavailable(targets: dict[str, dict[str, Any]], values: Any) -> None:
    if not isinstance(values, list):
        raise CrossNavigationError("unavailable navigation targets must be a list")
    for value in values:
        if not isinstance(value, dict) or set(value) != {"target_id", "kind", "reason"}:
            raise CrossNavigationError("unavailable navigation target fields differ")
        if value["target_id"] in targets or value["kind"] not in KINDS or not value["reason"]:
            raise CrossNavigationError("unavailable navigation target is invalid")
        _put_target(targets, value["target_id"], value["kind"], "integra.availability",
                    content_sha256(value), [], "UNAVAILABLE", None, None, None,
                    available=False, reason=value["reason"])


def _put_target(targets: dict[str, dict[str, Any]], target_id: str, kind: str, owner: str,
                content_hash: str, locators: list[dict[str, Any]], semantic_status: str,
                source_id: str | None, source_revision_id: str | None,
                artifact_id: str | None, *, available: bool = True,
                reason: str | None = None) -> None:
    if kind not in KINDS:
        return
    normalized = sorted(copy.deepcopy(locators), key=canonical_json)
    actions = _actions(kind, normalized) if available else []
    scope = {"target_id": target_id, "kind": kind, "owner": owner,
             "content_sha256": content_hash, "source_id": source_id,
             "source_revision_id": source_revision_id,
             "artifact_id": artifact_id, "locators": normalized,
             "semantic_status": semantic_status, "available": available,
             "unavailable_reason": reason, "actions": actions}
    target = {**scope, "target_sha256": ""}
    target["target_sha256"] = _record_hash(target, "target_sha256")
    existing = targets.get(target_id)
    if existing is not None and existing != target:
        raise CrossNavigationError("stable navigation target has conflicting representations")
    targets[target_id] = target


def _put_route(routes: list[dict[str, Any]], targets: dict[str, dict[str, Any]], from_id: str,
               to_id: str, relation: str, semantic_status: str, native_id: str | None = None) -> None:
    if from_id == to_id or from_id not in targets or to_id not in targets:
        return
    scope = {"from_id": from_id, "from_sha256": targets[from_id]["target_sha256"],
             "to_id": to_id, "to_sha256": targets[to_id]["target_sha256"],
             "relation": relation, "semantic_status": semantic_status,
             "bidirectional": True}
    digest = content_sha256(scope)
    route = {"route_id": native_id or derive_imported_id(
        "evidence", "integra.cross_navigation", relation, digest), **scope,
             "route_sha256": ""}
    route["route_sha256"] = _record_hash(route, "route_sha256")
    routes.append(route)


def _actions(kind: str, locators: list[dict[str, Any]]) -> list[str]:
    actions = {"OPEN_ENTITY"}
    for locator in locators:
        locator_type = locator.get("type", "").upper()
        actions.update({
            "TIME_INTERVAL": {"SEEK_MEDIA"}, "WORD_INTERVAL": {"SELECT_WORD_RANGE"},
            "PAGE_RANGE": {"OPEN_PAGE"}, "SLIDE_RANGE": {"OPEN_SLIDE"},
            "REGION": {"HIGHLIGHT_REGION"}, "CHARACTER_RANGE": {"SELECT_TEXT"},
            "ARTIFACT_REVISION": {"OPEN_REVISION"},
        }.get(locator_type, set()))
    if kind == "MEDIA_CLIP":
        actions.add("OPEN_CLIP")
    return sorted(actions)


def _document_locators(record: dict[str, Any], block: dict[str, Any]) -> list[dict[str, Any]]:
    locator = block["locator"]
    values: list[dict[str, Any]] = []
    if locator["unit_kind"] in {"SLIDE", "SLIDE_NOTES"}:
        values.append({"type": "SLIDE_RANGE", "start_slide": locator["unit_index"],
                       "end_slide": locator["unit_index"]})
    elif locator["unit_kind"] in {"PAGE", "IMAGE"}:
        values.append({"type": "PAGE_RANGE", "start_page": locator["unit_index"],
                       "end_page": locator["unit_index"]})
    values.append({"type": "CHARACTER_RANGE", "start_char": locator["character_start"],
                   "end_char": locator["character_end"]})
    if locator["region"] is not None:
        container = "SLIDE" if locator["unit_kind"] in {"SLIDE", "SLIDE_NOTES"} else "IMAGE" if locator["unit_kind"] == "IMAGE" else "PAGE"
        values.append({"type": "REGION", "container_type": container,
                       "container_index": locator["unit_index"], **copy.deepcopy(locator["region"])})
    values.append({
        "type": "ARTIFACT_REVISION", "artifact_id": record["source"]["source_id"],
        "revision_id": record["source"]["revision_id"],
        "content_sha256": record["source"]["sha256"],
    })
    return sorted(values, key=canonical_json)


def _source_mappings(
    alignment: dict[str, Any], registry: dict[str, Any],
    knowledge_view: dict[str, Any], evidence_payload: bytes,
    media_records: list[dict[str, Any]],
) -> list[dict[str, str]]:
    try:
        canonical = json.loads(evidence_payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CrossNavigationError("Canonical Evidence source mapping is invalid") from error
    alignment_nodes = alignment["nodes"]
    aligned_sources = {
        (item["source_id"], item["source_revision_id"])
        for item in alignment["sources"]
    }
    required_knowledge = {
        (item["source_id"], item["transcript_revision_id"])
        for item in knowledge_view["evidence"]
    }
    canonical_sources = {item["id"]: item for item in canonical["sources"]}
    canonical_revisions = {item["id"]: item for item in canonical["transcript_revisions"]}
    registry_projects = [
        item for item in registry["projects"]
        if item["project_id"] == alignment["project_id"]
    ]
    if len(registry_projects) != 1:
        raise CrossNavigationError("alignment project lacks one authoritative registry project")
    expected_canonical_project_id = f"project:{registry_projects[0]['project_key']}"
    if canonical.get("project", {}).get("id") != expected_canonical_project_id:
        raise CrossNavigationError("Canonical Evidence project differs from the alignment project")
    result: list[dict[str, str]] = []
    for source_id, revision_id in sorted(required_knowledge):
        source = canonical_sources.get(source_id)
        revision = canonical_revisions.get(revision_id)
        if (
            source is None or revision is None
            or revision["source_id"] != source_id
            or not source_id.startswith("source:")
        ):
            raise CrossNavigationError("indexed Knowledge source/revision is not canonical")
        native_id = source["id"].removeprefix("source:")
        matches = [item for item in registry["sources"]
                   if item["origin"].get("native_id") == native_id]
        if len(matches) != 1:
            raise CrossNavigationError("indexed Knowledge source lacks one exact project mapping")
        target = matches[0]
        if (
            alignment["project_id"] not in target["project_ids"]
            or (target["source_id"], target["current_revision_id"]) not in aligned_sources
        ):
            raise CrossNavigationError("indexed Knowledge source maps outside the alignment project")
        current_revision = next(
            item for item in target["revisions"]
            if item["revision_id"] == target["current_revision_id"]
        )
        content_bound = any(
            item["source_id"] == target["source_id"]
            and item["source_revision_id"] == current_revision["revision_id"]
            and item["kind"] in {"VIDEO", "AUDIO"}
            and item["artifact_sha256"] == source["content_sha256"]
            for item in alignment_nodes
        )
        if not content_bound:
            raise CrossNavigationError("indexed Knowledge source lacks content-bound alignment")
        facts = {
            "kind": "KNOWLEDGE_TO_PROJECT_SOURCE", "from_source_id": source["id"],
            "from_revision_id": revision["id"], "source_content_sha256": source["content_sha256"],
            "to_source_id": target["source_id"],
            "to_revision_id": current_revision["revision_id"],
            "to_revision_sha256": current_revision["revision_sha256"],
            "registry_native_id": native_id,
        }
        evidence_hash = content_sha256(facts)
        result.append({
            "mapping_id": derive_imported_id(
                "evidence", "integra.cross_navigation", source["id"], evidence_hash,
            ),
            "kind": facts["kind"], "from_source_id": source["id"],
            "from_revision_id": revision["id"], "to_source_id": target["source_id"],
            "to_revision_id": current_revision["revision_id"],
            "evidence_sha256": evidence_hash,
        })
    media_nodes = [item for item in alignment_nodes if item["kind"] in {"VIDEO", "AUDIO"}]
    media_mapping_targets: dict[tuple[str, str], tuple[str, str]] = {}
    for item in media_records:
        recipe = item["recipe"]
        parent_ids = set(recipe["source"]["provenance"]["parent_artifact_ids"])
        matches = [
            node for node in media_nodes
            if node["artifact_id"] in parent_ids
            and (node["source_id"], node["source_revision_id"]) in aligned_sources
        ]
        if len(matches) != 1:
            raise CrossNavigationError("registered media source lacks one exact alignment mapping")
        node = matches[0]
        from_pair = (recipe["source"]["artifact_id"], _media_source_revision_id(recipe))
        to_pair = (node["source_id"], node["source_revision_id"])
        previous = media_mapping_targets.get(from_pair)
        if previous is not None:
            if previous != to_pair:
                raise CrossNavigationError("registered media source has conflicting alignment mappings")
            continue
        media_mapping_targets[from_pair] = to_pair
        facts = {
            "kind": "MEDIA_TO_ALIGNMENT_SOURCE",
            "from_source_id": from_pair[0],
            "from_revision_id": from_pair[1],
            "source_sha256": recipe["source_sha256"],
            "parent_artifact_id": node["artifact_id"],
            "parent_artifact_sha256": node["artifact_sha256"],
            "to_source_id": node["source_id"],
            "to_revision_id": node["source_revision_id"],
        }
        evidence_hash = content_sha256(facts)
        result.append({
            "mapping_id": derive_imported_id(
                "evidence", "integra.cross_navigation", node["artifact_id"], evidence_hash,
            ),
            "kind": facts["kind"], "from_source_id": facts["from_source_id"],
            "from_revision_id": facts["from_revision_id"],
            "to_source_id": facts["to_source_id"], "to_revision_id": facts["to_revision_id"],
            "evidence_sha256": evidence_hash,
        })
    return sorted(result, key=lambda item: (
        item["kind"], item["from_source_id"], item["from_revision_id"], item["to_source_id"],
    ))


def _common_locator(left: list[dict[str, Any]], right: list[dict[str, Any]]) -> bool:
    for first in left:
        for second in right:
            left_type, right_type = first.get("type", "").upper(), second.get("type", "").upper()
            if left_type != right_type:
                continue
            if canonical_json({**first, "type": left_type}) == canonical_json({**second, "type": right_type}):
                return True
            if left_type == "TIME_INTERVAL" and (
                first["start_seconds"] < second["end_seconds"]
                and second["start_seconds"] < first["end_seconds"]
            ):
                return True
            if left_type == "WORD_INTERVAL" and (
                first["start_sequence"] <= second["end_sequence"]
                and second["start_sequence"] <= first["end_sequence"]
            ):
                return True
    return False


def _canonical_routes(routes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique = {item.get("route_id"): item for item in routes}
    if len(unique) != len(routes):
        first = sorted(routes, key=lambda item: (item.get("route_id", ""), canonical_json(item)))
        for left, right in zip(first, first[1:]):
            if left.get("route_id") == right.get("route_id") and left != right:
                raise CrossNavigationError("navigation route ID conflicts")
    return sorted(unique.values(), key=lambda item: (item["relation"], item["from_id"], item["to_id"], item["route_id"]))


def _validate_target(target: Any) -> None:
    fields = {"target_id", "kind", "owner", "content_sha256", "source_id",
              "source_revision_id", "artifact_id",
              "locators", "semantic_status", "available", "unavailable_reason", "actions",
              "target_sha256"}
    if not isinstance(target, dict) or set(target) != fields or target["kind"] not in KINDS:
        raise CrossNavigationError("navigation target fields or kind differ")
    if not isinstance(target["target_id"], str) or not target["target_id"]:
        raise CrossNavigationError("navigation target ID is invalid")
    if not isinstance(target["owner"], str) or not target["owner"] or not SHA256.fullmatch(target["content_sha256"]):
        raise CrossNavigationError("navigation target binding is invalid")
    if target["source_id"] is not None and (not isinstance(target["source_id"], str) or not target["source_id"]):
        raise CrossNavigationError("navigation source ID is invalid")
    if target["source_revision_id"] is not None and (
        not isinstance(target["source_revision_id"], str) or not target["source_revision_id"]
    ):
        raise CrossNavigationError("navigation source revision ID is invalid")
    if (target["source_id"] is None) != (target["source_revision_id"] is None):
        raise CrossNavigationError("navigation source/revision identity is incomplete")
    if target["artifact_id"] is not None and (not isinstance(target["artifact_id"], str) or not target["artifact_id"]):
        raise CrossNavigationError("navigation artifact ID is invalid")
    if not isinstance(target["semantic_status"], str) or not target["semantic_status"]:
        raise CrossNavigationError("navigation semantic status is invalid")
    if not isinstance(target["locators"], list):
        raise CrossNavigationError("navigation target locators are invalid")
    for locator in target["locators"]:
        _validate_locator(locator)
    if not isinstance(target["available"], bool):
        raise CrossNavigationError("navigation availability is invalid")
    if target["available"] and (target["unavailable_reason"] is not None or not target["actions"]):
        raise CrossNavigationError("available navigation target lacks actions")
    if not target["available"] and (not target["unavailable_reason"] or target["locators"] or target["actions"]):
        raise CrossNavigationError("unavailable navigation target fabricates access")
    if (
        target["available"] and target["owner"] == "integra.knowledge"
        and target["source_id"] is None
        and (target["locators"] or target["actions"] != ["OPEN_ENTITY"])
    ):
        raise CrossNavigationError("aggregate Knowledge target fabricates a source route")
    if target["available"] and target["actions"] != _actions(target["kind"], target["locators"]):
        raise CrossNavigationError("navigation target actions differ from exact locators")
    if target["target_sha256"] != _record_hash(target, "target_sha256"):
        raise CrossNavigationError("navigation target hash differs")


def _hop(route: dict[str, Any], target: dict[str, Any], direction: str) -> dict[str, Any]:
    return {"direction": direction, "route_id": route["route_id"],
            "relation": route["relation"], "semantic_status": route["semantic_status"],
            "target_id": target["target_id"], "kind": target["kind"],
            "locators": copy.deepcopy(target["locators"]), "actions": copy.deepcopy(target["actions"])}


def _validate_sources(sources: Any) -> None:
    if not isinstance(sources, dict) or set(sources) != {"alignment", "knowledge", "media", "mappings"}:
        raise CrossNavigationError("cross-navigation source bindings differ")
    for name in ("alignment", "knowledge"):
        binding = sources[name]
        if (not isinstance(binding, dict) or set(binding) != {"record_id", "record_sha256"}
                or not isinstance(binding["record_id"], str)
                or not SHA256.fullmatch(binding["record_sha256"])):
            raise CrossNavigationError("cross-navigation source binding is invalid")
    media = sources["media"]
    if not isinstance(media, list) or not media or media != sorted(media, key=lambda item: item.get("derivative_id", "")):
        raise CrossNavigationError("cross-navigation media bindings are not canonical")
    seen = set()
    for item in media:
        if (not isinstance(item, dict) or set(item) != {
            "recipe_id", "recipe_sha256", "derivative_id", "derivative_sha256",
        } or not all(isinstance(item[name], str) and item[name] for name in ("recipe_id", "derivative_id"))
                or not all(SHA256.fullmatch(item[name]) for name in ("recipe_sha256", "derivative_sha256"))
                or item["derivative_id"] in seen):
            raise CrossNavigationError("cross-navigation media binding is invalid")
        seen.add(item["derivative_id"])
    mappings = sources["mappings"]
    if not isinstance(mappings, list) or mappings != sorted(
        mappings, key=lambda item: (item.get("kind", ""), item.get("from_source_id", ""),
                                    item.get("from_revision_id", ""), item.get("to_source_id", ""))
    ):
        raise CrossNavigationError("cross-navigation source mappings are not canonical")
    mapping_ids = set()
    for item in mappings:
        fields = {"mapping_id", "kind", "from_source_id", "from_revision_id",
                  "to_source_id", "to_revision_id", "evidence_sha256"}
        if (not isinstance(item, dict) or set(item) != fields
                or item["kind"] not in {"KNOWLEDGE_TO_PROJECT_SOURCE", "MEDIA_TO_ALIGNMENT_SOURCE"}
                or not all(isinstance(item[name], str) and item[name] for name in fields - {"kind", "evidence_sha256"})
                or not SHA256.fullmatch(item["evidence_sha256"])
                or item["mapping_id"] in mapping_ids):
            raise CrossNavigationError("cross-navigation source mapping is invalid")
        mapping_ids.add(item["mapping_id"])


def _validate_locator(locator: Any) -> None:
    if not isinstance(locator, dict) or not isinstance(locator.get("type"), str):
        raise CrossNavigationError("navigation locator is invalid")
    kind = locator["type"].upper()
    fields = {
        "TIME_INTERVAL": {"type", "start_seconds", "end_seconds"},
        "WORD_INTERVAL": {"type", "start_word_id", "end_word_id", "start_sequence", "end_sequence"},
        "PAGE_RANGE": {"type", "start_page", "end_page"},
        "SLIDE_RANGE": {"type", "start_slide", "end_slide"},
        "REGION": {"type", "container_type", "container_index", "x", "y", "width", "height"},
        "CHARACTER_RANGE": {"type", "start_char", "end_char"},
        "ARTIFACT_REVISION": {"type", "artifact_id", "revision_id", "content_sha256"},
    }
    if kind not in fields or set(locator) != fields[kind]:
        raise CrossNavigationError("navigation locator fields differ")
    number = lambda value: isinstance(value, (int, float)) and not isinstance(value, bool)
    integer = lambda value: isinstance(value, int) and not isinstance(value, bool)
    if kind == "TIME_INTERVAL" and (
        not number(locator["start_seconds"]) or not number(locator["end_seconds"])
        or locator["start_seconds"] < 0 or locator["end_seconds"] <= locator["start_seconds"]
    ):
        raise CrossNavigationError("navigation time locator range is invalid")
    if kind == "WORD_INTERVAL" and (
        not integer(locator["start_sequence"]) or not integer(locator["end_sequence"])
        or locator["start_sequence"] < 0 or locator["end_sequence"] < locator["start_sequence"]
        or not locator["start_word_id"] or not locator["end_word_id"]
    ):
        raise CrossNavigationError("navigation word locator range is invalid")
    if kind in {"PAGE_RANGE", "SLIDE_RANGE"}:
        prefix = "page" if kind == "PAGE_RANGE" else "slide"
        start, end = locator[f"start_{prefix}"], locator[f"end_{prefix}"]
        if not integer(start) or not integer(end) or start < 1 or end < start:
            raise CrossNavigationError("navigation document locator range is invalid")
    if kind == "CHARACTER_RANGE" and (
        not integer(locator["start_char"]) or not integer(locator["end_char"])
        or locator["start_char"] < 0 or locator["end_char"] <= locator["start_char"]
    ):
        raise CrossNavigationError("navigation character locator range is invalid")
    if kind == "REGION" and (
        locator["container_type"] not in {"PAGE", "SLIDE", "IMAGE"}
        or not integer(locator["container_index"]) or locator["container_index"] < 1
        or not all(number(locator[name]) for name in ("x", "y", "width", "height"))
        or locator["x"] < 0 or locator["y"] < 0 or locator["width"] <= 0 or locator["height"] <= 0
        or locator["x"] + locator["width"] > 1 or locator["y"] + locator["height"] > 1
    ):
        raise CrossNavigationError("navigation region locator is invalid")
    if kind == "ARTIFACT_REVISION" and (
        not all(isinstance(locator[name], str) and locator[name] for name in ("artifact_id", "revision_id"))
        or not SHA256.fullmatch(locator["content_sha256"])
    ):
        raise CrossNavigationError("navigation revision locator is invalid")


def _record_hash(value: dict[str, Any], field: str = "record_sha256") -> str:
    clean = copy.deepcopy(value)
    clean[field] = ""
    return content_sha256(clean)


def _timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise CrossNavigationError("cross-navigation timestamp is invalid")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise CrossNavigationError("cross-navigation timestamp is invalid") from error
    if result.tzinfo is None or result.utcoffset() != timezone.utc.utcoffset(result):
        raise CrossNavigationError("cross-navigation timestamp must be UTC")
    return result
