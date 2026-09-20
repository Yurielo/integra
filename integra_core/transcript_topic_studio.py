"""Deterministic Transcript & Topic Studio v1 control-plane contract.

The studio indexes immutable outputs owned by pinned source components.  It
never rewrites those outputs.  Human decisions are stored as a separate,
content-bound Integra review layer.
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
import json
import re
from typing import Any

from .identity import derive_imported_id
from .project_lease import LeaseConflict, LeaseStore
from .projects_sources import RegistryError, validate_registry
from .protocol import canonical_json, content_sha256


SHA256 = re.compile(r"^[0-9a-f]{64}$")
URN = re.compile(
    r"^urn:integra:[a-z][a-z0-9_]{1,31}:"
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
GIT_SHA = re.compile(r"^[0-9a-f]{40}$")

TOPIC_LEVELS = ("DETAILED", "NORMAL", "COARSE")
SEMANTIC_STATES = {"PROVISIONAL", "REVIEW_REQUIRED"}
ARTIFACT_KINDS = {
    "MEDIA_PREPARATION",
    "MACHINE_TRANSCRIPT",
    "TRANSLATION",
    "WORD_TIMELINE",
    "QUALITY_REPORT",
    "TOPIC_SET",
    "TOPIC_HIERARCHY",
}
CAPABILITY_OWNERS = {
    "media_preparation": ("videotext",),
    "asr": ("videotext",),
    "translation": ("videotext",),
    "word_timeline": ("seminartext",),
    "topics": ("seminartext",),
    "review_mechanics": ("seminartext", "videotext"),
    "quality_validation": ("seminartext", "videotext"),
}
R5_SELECTIONS_SHA256 = "38ec6db0172c6bd61d8515b71c32be0554e311684364758cf87c598723dc20c3"
PINNED_COMPONENT_COMMITS = {
    "seminartext": "970bde598ddd649599295139986933e0e06cb9c0",
    "videotext": "2e098d1705b6815628bee1e023f4742718eabf02",
}
PINNED_COMPONENT_CONTRACTS = {
    "seminartext": {"canonical_evidence_v1", "canonical_knowledge_v1", "topic_review_workflow_v2"},
    "videotext": {"project_schema_v7", "project_store_v7", "build_identity_0_6_4"},
}
CAPABILITY_CONTRACTS = {
    "media_preparation": ("project_schema_v7",),
    "asr": ("project_schema_v7",),
    "translation": ("project_schema_v7",),
    "word_timeline": ("canonical_evidence_v1",),
    "topics": ("topic_review_workflow_v2",),
    "review_mechanics": ("topic_review_workflow_v2", "project_schema_v7"),
    "quality_validation": ("canonical_evidence_v1", "project_schema_v7"),
}
PINNED_COMPONENT_MODELS = {
    "seminartext": {
        "gemma3:4b": "ed1e8a40017e648c133188919a5a0105ce1916726dbc657fecb5ccb5d717c46d",
        "gemma3:4b:manifest": "a2af6cc3eb7fa8be8504abaf9b04e88f17a119ec3f04a3addf55f92841195f5a",
        "gemma3:4b:weights": "aeda25e63ebd698fab8638ffb778e68bed908b960d39d0becc650fa981609d25",
    },
    "videotext": {
        "ggml-large-v3.bin": "64d182b440b98d5203c4f9bd541544d84c605196c4f7b845dfa11fb23594d1e2",
    },
}
LOCATOR_TYPES = {
    "TIME_INTERVAL",
    "WORD_INTERVAL",
    "PAGE_RANGE",
    "SLIDE_RANGE",
    "REGION",
    "CHARACTER_RANGE",
    "ARTIFACT_REVISION",
}


class StudioError(RuntimeError):
    """Raised when studio state or input would violate the v1 contract."""


def new_studio(
    registry: dict[str, Any], *, project_id: str, source_id: str,
    source_revision_id: str, bindings: list[dict[str, Any]], created_at: str,
) -> dict[str, Any]:
    """Create a studio view bound to one exact accepted source revision."""

    _timestamp(created_at)
    try:
        validate_registry(registry)
    except RegistryError as error:
        raise StudioError("project/source registry is invalid") from error
    project = _find(registry.get("projects", []), "project_id", project_id, "project")
    source = _find(registry.get("sources", []), "source_id", source_id, "source")
    if project_id not in source.get("project_ids", []):
        raise StudioError("source is not linked to project")
    revision = _find(source.get("revisions", []), "revision_id", source_revision_id, "source revision")
    if source.get("current_revision_id") != source_revision_id:
        raise StudioError("studio must bind the current source revision")
    binding_map = _validate_bindings(bindings)
    registry_binding = {
        "registry_id": registry["registry_id"],
        "registry_record_sha256": registry["record_sha256"],
        "project_record_sha256": content_sha256(project),
        "source_record_sha256": content_sha256(source),
    }
    source_binding_sha256 = content_sha256({
        "project_id": project_id,
        "source_id": source_id,
        "source_revision_id": source_revision_id,
        "source_revision_sha256": revision["revision_sha256"],
        "source_type": source["source_type"],
        "registry_binding": registry_binding,
    })
    identity_hash = source_binding_sha256
    studio_id = derive_imported_id(
        "artifact", "integra.transcript_topic_studio", source_revision_id, identity_hash
    )
    value = {
        "schema_version": "1.0",
        "studio_id": studio_id,
        "project_id": project_id,
        "registry_binding": registry_binding,
        "source": {
            "source_id": source_id,
            "source_revision_id": source_revision_id,
            "source_revision_sha256": revision["revision_sha256"],
            "source_type": source["source_type"],
            "source_binding_sha256": source_binding_sha256,
        },
        "created_at": created_at,
        "updated_at": created_at,
        "revision": 0,
        "status": "ACTIVE",
        "component_bindings": binding_map,
        "artifacts": [],
        "quality_findings": [],
        "topic_sets": [],
        "hierarchies": [],
        "review_packages": [],
        "review_decisions": [],
        "semantic_authority": "MACHINE_OUTPUT_REQUIRES_HUMAN_DECISION",
        "cross_source_alignment": "OUT_OF_SCOPE_R8C",
        "source_artifacts_modified": False,
        "record_sha256": "",
    }
    return _seal(value)


def register_artifact(
    studio: dict[str, Any], *, registry: dict[str, Any], kind: str, native_id: str, content_sha256: str,
    created_at: str, capability: str, parents: list[str], locators: list[dict[str, Any]],
    semantic_status: str = "PROVISIONAL", metadata: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], str]:
    """Index one immutable component-owned output with complete provenance."""

    validate_studio(studio, registry)
    _active(studio)
    _timestamp(created_at)
    _sha(content_sha256, "artifact content hash")
    _text(native_id, "artifact native ID")
    if kind not in ARTIFACT_KINDS:
        raise StudioError("artifact kind is unsupported")
    binding = studio["component_bindings"].get(capability)
    if binding is None:
        raise StudioError("artifact capability has no accepted binding")
    if semantic_status not in SEMANTIC_STATES and semantic_status != "NOT_APPLICABLE":
        raise StudioError("artifact semantic status is invalid")
    if kind in {"MACHINE_TRANSCRIPT", "TRANSLATION", "TOPIC_SET", "TOPIC_HIERARCHY"}:
        if semantic_status not in SEMANTIC_STATES:
            raise StudioError("machine semantic artifact cannot be accepted automatically")
    _unique_text(parents, "artifact parents")
    known_ids = {studio["source"]["source_revision_id"]}
    known_ids.update(item["artifact_id"] for item in studio["artifacts"])
    if any(parent not in known_ids for parent in parents):
        raise StudioError("artifact parent is unknown")
    normalized_locators = [_locator(item) for item in locators]
    if not normalized_locators:
        raise StudioError("artifact requires an exact source locator")
    _require_source_locator(studio["source"]["source_type"], normalized_locators)
    _require_exact_source_revision(studio, normalized_locators)
    component_identity = "+".join(
        item["component_id"] for item in binding["components"]
    )
    identity_hash = content_sha256_fn(
        {
            "kind": kind,
            "component_ids": [item["component_id"] for item in binding["components"]],
            "native_id": native_id,
            "content_sha256": content_sha256,
        }
    )
    artifact_id = derive_imported_id(
        "artifact", component_identity, native_id, identity_hash
    )
    record = {
        "artifact_id": artifact_id,
        "native_id": native_id,
        "kind": kind,
        "content_sha256": content_sha256,
        "created_at": created_at,
        "capability": capability,
        "component_binding_sha256": content_sha256_fn(binding),
        "parent_ids": sorted(parents),
        "locators": normalized_locators,
        "semantic_status": semantic_status,
        "metadata": copy.deepcopy(metadata or {}),
        "metadata_sha256": content_sha256_fn(metadata or {}),
    }
    result = copy.deepcopy(studio)
    existing = _find(result["artifacts"], "artifact_id", artifact_id, "artifact", required=False)
    if existing is not None:
        if existing != record:
            raise StudioError("artifact identity conflict")
        return studio, artifact_id
    if any(item["native_id"] == native_id and item["kind"] == kind for item in result["artifacts"]):
        raise StudioError("artifact native ID conflicts with different content")
    result["artifacts"].append(record)
    result["artifacts"].sort(key=lambda item: item["artifact_id"])
    return _advance(result, created_at), artifact_id


def register_transcript(
    studio: dict[str, Any], *, registry: dict[str, Any], native_id: str, content_sha256: str, created_at: str,
    language: str, word_count: int, confidence: float, locators: list[dict[str, Any]],
) -> tuple[dict[str, Any], str]:
    """Index an original machine transcript without accepting its semantics."""

    _text(language, "transcript language")
    _positive_int(word_count, "transcript word count")
    _probability(confidence, "transcript confidence")
    status = "REVIEW_REQUIRED" if confidence < 0.8 else "PROVISIONAL"
    return register_artifact(
        studio, registry=registry, kind="MACHINE_TRANSCRIPT", native_id=native_id,
        content_sha256=content_sha256, created_at=created_at, capability="asr",
        parents=[studio["source"]["source_revision_id"]], locators=locators,
        semantic_status=status,
        metadata={
            "language": language,
            "word_count": word_count,
            "confidence": confidence,
            "wording": "ORIGINAL_MACHINE_WORDING",
        },
    )


def register_translation(
    studio: dict[str, Any], *, registry: dict[str, Any], native_id: str, content_sha256: str, created_at: str,
    transcript_id: str, source_language: str, target_language: str,
    confidence: float, locators: list[dict[str, Any]],
) -> tuple[dict[str, Any], str]:
    """Index a translation separately and bind it to the original transcript."""

    transcript = _artifact(studio, transcript_id, "MACHINE_TRANSCRIPT")
    _text(source_language, "translation source language")
    _text(target_language, "translation target language")
    if source_language == target_language:
        raise StudioError("translation languages must differ")
    if transcript["metadata"].get("language") != source_language:
        raise StudioError("translation source language differs from transcript")
    _probability(confidence, "translation confidence")
    status = "REVIEW_REQUIRED" if confidence < 0.8 else "PROVISIONAL"
    return register_artifact(
        studio, registry=registry, kind="TRANSLATION", native_id=native_id,
        content_sha256=content_sha256, created_at=created_at, capability="translation",
        parents=[transcript_id], locators=locators, semantic_status=status,
        metadata={
            "source_language": source_language,
            "target_language": target_language,
            "confidence": confidence,
            "original_transcript_id": transcript_id,
            "wording": "DERIVED_TRANSLATION",
        },
    )


def register_word_timeline(
    studio: dict[str, Any], *, registry: dict[str, Any], native_id: str, content_sha256: str, created_at: str,
    transcript_id: str, words: list[dict[str, Any]], locators: list[dict[str, Any]],
) -> tuple[dict[str, Any], str]:
    """Expose a component-owned Canonical Word Timeline with exact word lineage."""

    _artifact(studio, transcript_id, "MACHINE_TRANSCRIPT")
    if not isinstance(words, list) or not words:
        raise StudioError("word timeline must contain words")
    normalized: list[dict[str, Any]] = []
    last_end = -1.0
    for index, word in enumerate(words):
        if not isinstance(word, dict) or set(word) != {
            "word_id", "sequence", "text", "start_seconds", "end_seconds", "confidence"
        }:
            raise StudioError("word timeline entry fields are invalid")
        _text(word["word_id"], "word ID")
        if word["sequence"] != index:
            raise StudioError("word timeline sequence must be contiguous")
        _text(word["text"], "word text")
        start = _number(word["start_seconds"], "word start")
        end = _number(word["end_seconds"], "word end")
        _probability(word["confidence"], "word confidence")
        if end <= start or start < last_end:
            raise StudioError("word intervals must be ordered and non-overlapping")
        last_end = end
        normalized.append(copy.deepcopy(word))
    return register_artifact(
        studio, registry=registry, kind="WORD_TIMELINE", native_id=native_id,
        content_sha256=content_sha256, created_at=created_at, capability="word_timeline",
        parents=[transcript_id], locators=locators, semantic_status="NOT_APPLICABLE",
        metadata={"transcript_id": transcript_id, "words": normalized},
    )


def add_quality_finding(
    studio: dict[str, Any], *, registry: dict[str, Any], native_id: str, created_at: str, capability: str,
    artifact_id: str, code: str, severity: str, confidence: float | None,
    locators: list[dict[str, Any]], detail: str,
) -> tuple[dict[str, Any], str]:
    """Add a reproducible visible quality finding; low confidence never disappears."""

    validate_studio(studio, registry)
    _active(studio)
    _timestamp(created_at)
    _artifact(studio, artifact_id)
    if capability != "quality_validation":
        raise StudioError("quality finding must use composed quality validation")
    _text(native_id, "finding native ID")
    _text(code, "finding code")
    _text(detail, "finding detail")
    if severity not in {"INFO", "WARN", "ERROR"}:
        raise StudioError("quality severity is invalid")
    if confidence is not None:
        _probability(confidence, "finding confidence")
    normalized_locators = [_locator(item) for item in locators]
    if not normalized_locators:
        raise StudioError("quality finding requires an exact source locator")
    _require_source_locator(studio["source"]["source_type"], normalized_locators)
    finding_hash = content_sha256_fn(
        {
            "artifact_id": artifact_id,
            "code": code,
            "severity": severity,
            "confidence": confidence,
            "locators": normalized_locators,
            "detail": detail,
        }
    )
    finding_id = derive_imported_id(
        "evidence", "integra.quality", native_id, finding_hash
    )
    finding = {
        "finding_id": finding_id,
        "native_id": native_id,
        "artifact_id": artifact_id,
        "code": code,
        "severity": severity,
        "confidence": confidence,
        "locators": normalized_locators,
        "detail": detail,
        "created_at": created_at,
        "review_required": severity == "ERROR" or confidence is not None and confidence < 0.8,
        "finding_sha256": finding_hash,
    }
    result = copy.deepcopy(studio)
    existing = _find(result["quality_findings"], "finding_id", finding_id, "finding", required=False)
    if existing is not None:
        if existing != finding:
            raise StudioError("quality finding identity conflict")
        return studio, finding_id
    result["quality_findings"].append(finding)
    result["quality_findings"].sort(key=lambda item: item["finding_id"])
    return _advance(result, created_at), finding_id


def register_topic_set(
    studio: dict[str, Any], *, registry: dict[str, Any], native_id: str, content_sha256: str, created_at: str,
    timeline_id: str, level: str, topics: list[dict[str, Any]],
) -> tuple[dict[str, Any], str]:
    """Register one detailed/normal/coarse Topic set with per-source locators."""

    validate_studio(studio, registry)
    _active(studio)
    _artifact(studio, timeline_id, "WORD_TIMELINE")
    if level not in TOPIC_LEVELS:
        raise StudioError("topic level is unsupported")
    _sha(content_sha256, "topic-set content hash")
    _text(native_id, "topic-set native ID")
    _timestamp(created_at)
    if not isinstance(topics, list) or not topics:
        raise StudioError("topic set must contain topics")
    set_hash = content_sha256_fn(
        {"native_id": native_id, "level": level, "content_sha256": content_sha256}
    )
    topic_set_id = derive_imported_id("artifact", "seminartext", native_id, set_hash)
    normalized_topics: list[dict[str, Any]] = []
    for sequence, topic in enumerate(topics):
        normalized_topics.append(
            _topic(studio, timeline_id, topic_set_id, level, sequence, topic)
        )
    _ensure_non_overlapping(normalized_topics)
    status = (
        "REVIEW_REQUIRED"
        if any(item["semantic_status"] == "REVIEW_REQUIRED" for item in normalized_topics)
        else "PROVISIONAL"
    )
    topic_set = {
        "topic_set_id": topic_set_id,
        "native_id": native_id,
        "content_sha256": content_sha256,
        "created_at": created_at,
        "timeline_id": timeline_id,
        "level": level,
        "semantic_status": status,
        "component_binding_sha256": content_sha256_fn(studio["component_bindings"]["topics"]),
        "topics": normalized_topics,
        "payload_sha256": content_sha256_fn(normalized_topics),
    }
    result = copy.deepcopy(studio)
    existing = _find(result["topic_sets"], "topic_set_id", topic_set_id, "topic set", required=False)
    if existing is not None:
        if existing != topic_set:
            raise StudioError("topic-set identity conflict")
        return studio, topic_set_id
    if any(item["level"] == level for item in result["topic_sets"]):
        raise StudioError("only one Topic set per level is allowed in v1")
    result["topic_sets"].append(topic_set)
    result["topic_sets"].sort(key=lambda item: TOPIC_LEVELS.index(item["level"]))
    return _advance(result, created_at), topic_set_id


def register_hierarchy(
    studio: dict[str, Any], *, registry: dict[str, Any], native_id: str, created_at: str,
    edges: list[dict[str, str]],
) -> tuple[dict[str, Any], str]:
    """Bind child Topics to strictly coarser parents without cross-source alignment."""

    validate_studio(studio, registry)
    _active(studio)
    _timestamp(created_at)
    _text(native_id, "hierarchy native ID")
    topics = _all_topics(studio)
    if not edges:
        raise StudioError("Topic hierarchy must contain edges")
    normalized: list[dict[str, str]] = []
    children: set[str] = set()
    for edge in edges:
        if not isinstance(edge, dict) or set(edge) != {"child_topic_id", "parent_topic_id"}:
            raise StudioError("hierarchy edge fields are invalid")
        child = topics.get(edge["child_topic_id"])
        parent = topics.get(edge["parent_topic_id"])
        if child is None or parent is None:
            raise StudioError("hierarchy references unknown Topic")
        if child["topic_id"] in children:
            raise StudioError("Topic has multiple parents")
        if TOPIC_LEVELS.index(parent["level"]) <= TOPIC_LEVELS.index(child["level"]):
            raise StudioError("Topic parent must be strictly coarser")
        if not _locator_contains(parent["locators"], child["locators"]):
            raise StudioError("Topic parent does not contain child locator")
        children.add(child["topic_id"])
        normalized.append(copy.deepcopy(edge))
    normalized.sort(key=lambda item: (item["parent_topic_id"], item["child_topic_id"]))
    hierarchy_hash = content_sha256_fn(normalized)
    hierarchy_id = derive_imported_id(
        "artifact", "seminartext", native_id, hierarchy_hash
    )
    record = {
        "hierarchy_id": hierarchy_id,
        "native_id": native_id,
        "created_at": created_at,
        "content_sha256": hierarchy_hash,
        "semantic_status": "PROVISIONAL",
        "edges": normalized,
    }
    result = copy.deepcopy(studio)
    existing = _find(result["hierarchies"], "hierarchy_id", hierarchy_id, "hierarchy", required=False)
    if existing is not None:
        if existing != record:
            raise StudioError("hierarchy identity conflict")
        return studio, hierarchy_id
    result["hierarchies"].append(record)
    result["hierarchies"].sort(key=lambda item: item["hierarchy_id"])
    return _advance(result, created_at), hierarchy_id


def build_exception_package(
    studio: dict[str, Any], *, registry: dict[str, Any], native_id: str, created_at: str,
    member_ids: list[str], neighbor_count: int = 1,
) -> tuple[dict[str, Any], str]:
    """Cluster explicitly enumerated exceptions with adjacent Topic evidence."""

    validate_studio(studio, registry)
    _active(studio)
    _timestamp(created_at)
    _text(native_id, "review package native ID")
    _unique_text(member_ids, "review package members", non_empty=True)
    if isinstance(neighbor_count, bool) or not isinstance(neighbor_count, int) or neighbor_count < 0:
        raise StudioError("neighbor count must be a non-negative integer")
    candidates = _exception_candidates(studio)
    if any(item not in candidates for item in member_ids):
        raise StudioError("review package contains a non-exception member")
    topic_orders = [
        [topic["topic_id"] for topic in topic_set["topics"]]
        for topic_set in studio["topic_sets"]
    ]
    neighbor_ids: set[str] = set()
    for member_id in member_ids:
        for topic_order in topic_orders:
            if member_id in topic_order:
                index = topic_order.index(member_id)
                neighbor_ids.update(
                    topic_order[max(0, index - neighbor_count): index]
                    + topic_order[index + 1: index + 1 + neighbor_count]
                )
                break
    neighbor_ids.difference_update(member_ids)
    member_bindings = [
        {"member_id": item, "content_sha256": content_sha256_fn(_review_candidate(studio, item))}
        for item in sorted(member_ids)
    ]
    neighbor_bindings = [
        {"topic_id": item, "content_sha256": content_sha256_fn(_review_candidate(studio, item))}
        for item in sorted(neighbor_ids)
    ]
    scope = {
        "member_ids": sorted(member_ids),
        "neighbor_topic_ids": sorted(neighbor_ids),
        "member_bindings": member_bindings,
        "neighbor_bindings": neighbor_bindings,
        "source_revision_id": studio["source"]["source_revision_id"],
    }
    scope_hash = content_sha256_fn(scope)
    package_id = derive_imported_id(
        "review", "integra.review_service", native_id, scope_hash
    )
    package = {
        "package_id": package_id,
        "native_id": native_id,
        "created_at": created_at,
        "status": "REVIEW_REQUIRED",
        "scope_sha256": scope_hash,
        **scope,
    }
    result = copy.deepcopy(studio)
    existing = _find(result["review_packages"], "package_id", package_id, "review package", required=False)
    if existing is not None:
        if existing != package:
            raise StudioError("review package identity conflict")
        return studio, package_id
    covered = {
        member
        for item in result["review_packages"]
        for member in item["member_ids"]
        if item["status"] == "REVIEW_REQUIRED"
    }
    if covered.intersection(member_ids):
        raise StudioError("exception is already in an unresolved package")
    result["review_packages"].append(package)
    result["review_packages"].sort(key=lambda item: item["package_id"])
    return _advance(result, created_at), package_id


def apply_review_decision(
    studio: dict[str, Any], *, registry: dict[str, Any], package_id: str, native_id: str,
    decided_at: str, authority: str, scope_sha256: str,
    resolutions: list[dict[str, str]], lease: dict[str, Any], lease_store: LeaseStore,
) -> tuple[dict[str, Any], str]:
    """Persist an explicitly authorized human decision without mutating drafts."""

    validate_studio(studio, registry)
    _active(studio)
    _timestamp(decided_at)
    _text(native_id, "decision native ID")
    if authority != "HUMAN_DOMAIN_REVIEW":
        raise StudioError("review decision requires explicit human domain authority")
    package = _find(studio["review_packages"], "package_id", package_id, "review package")
    if package["status"] != "REVIEW_REQUIRED" or scope_sha256 != package["scope_sha256"]:
        raise StudioError("review decision scope is stale or already resolved")
    _validate_review_package_scope(studio, package)
    _validate_review_lease(studio, package, lease, lease_store, decided_at)
    if not isinstance(resolutions, list) or len(resolutions) != len(package["member_ids"]):
        raise StudioError("decision must resolve every package member exactly once")
    normalized: list[dict[str, str]] = []
    for item in resolutions:
        if not isinstance(item, dict) or set(item) != {
            "member_id", "resolution", "decision_payload_sha256"
        }:
            raise StudioError("review resolution fields are invalid")
        if item["resolution"] not in {"ACCEPT", "REJECT", "ADJUST"}:
            raise StudioError("review resolution is unsupported")
        _sha(item["decision_payload_sha256"], "review decision payload hash")
        normalized.append(copy.deepcopy(item))
    normalized.sort(key=lambda item: item["member_id"])
    if [item["member_id"] for item in normalized] != package["member_ids"]:
        raise StudioError("decision members differ from package scope")
    decision_hash = content_sha256_fn(
        {
            "package_id": package_id,
            "scope_sha256": scope_sha256,
            "authority": authority,
            "lease_operation_id": lease["operation_id"],
            "resolutions": normalized,
        }
    )
    decision_id = derive_imported_id(
        "review", "integra.review_service", native_id, decision_hash
    )
    decision = {
        "decision_id": decision_id,
        "native_id": native_id,
        "package_id": package_id,
        "scope_sha256": scope_sha256,
        "authority": authority,
        "decided_at": decided_at,
        "lease_id": lease["lease_id"],
        "lease_generation": lease["generation"],
        "lease_operation_id": lease["operation_id"],
        "resolutions": normalized,
        "decision_sha256": decision_hash,
        "source_artifacts_modified": False,
    }
    result = copy.deepcopy(studio)
    result_package = _find(result["review_packages"], "package_id", package_id, "review package")
    result_package["status"] = "DECIDED"
    result_package["decision_id"] = decision_id
    result["review_decisions"].append(decision)
    result["review_decisions"].sort(key=lambda item: item["decision_id"])
    return _advance(result, decided_at), decision_id


def dumps_studio(studio: dict[str, Any], registry: dict[str, Any]) -> bytes:
    validate_studio(studio, registry)
    return canonical_json(studio) + b"\n"


def loads_studio(payload: bytes, registry: dict[str, Any]) -> dict[str, Any]:
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise StudioError("studio serialization is invalid") from error
    validate_studio(value, registry=registry)
    return value


def validate_studio(studio: dict[str, Any], registry: dict[str, Any]) -> None:
    fields = {
        "schema_version", "studio_id", "project_id", "registry_binding", "source", "created_at",
        "updated_at", "revision", "status", "component_bindings", "artifacts",
        "quality_findings", "topic_sets", "hierarchies", "review_packages",
        "review_decisions", "semantic_authority", "cross_source_alignment",
        "source_artifacts_modified", "record_sha256",
    }
    if not isinstance(studio, dict) or set(studio) != fields:
        raise StudioError("studio fields differ from v1")
    if studio["schema_version"] != "1.0" or studio["status"] not in {"ACTIVE", "CANCELLED"}:
        raise StudioError("studio version or status is invalid")
    _urn(studio["studio_id"], "studio ID")
    _urn(studio["project_id"], "project ID")
    registry_binding = studio["registry_binding"]
    if not isinstance(registry_binding, dict) or set(registry_binding) != {
        "registry_id", "registry_record_sha256", "project_record_sha256", "source_record_sha256"
    }:
        raise StudioError("studio registry binding is invalid")
    _urn(registry_binding["registry_id"], "registry ID")
    for field in ("registry_record_sha256", "project_record_sha256", "source_record_sha256"):
        _sha(registry_binding[field], field.replace("_", " "))
    _timestamp(studio["created_at"])
    if _timestamp(studio["updated_at"]) < _timestamp(studio["created_at"]):
        raise StudioError("studio update predates creation")
    if isinstance(studio["revision"], bool) or not isinstance(studio["revision"], int) or studio["revision"] < 0:
        raise StudioError("studio revision is invalid")
    source = studio["source"]
    if not isinstance(source, dict) or set(source) != {
        "source_id", "source_revision_id", "source_revision_sha256", "source_type",
        "source_binding_sha256",
    }:
        raise StudioError("studio source binding is invalid")
    _urn(source["source_id"], "source ID")
    _urn(source["source_revision_id"], "source revision ID")
    _sha(source["source_revision_sha256"], "source revision hash")
    _text(source["source_type"], "source type")
    expected_source_binding = content_sha256_fn({
        "project_id": studio["project_id"],
        "source_id": source["source_id"],
        "source_revision_id": source["source_revision_id"],
        "source_revision_sha256": source["source_revision_sha256"],
        "source_type": source["source_type"],
        "registry_binding": registry_binding,
    })
    if source["source_binding_sha256"] != expected_source_binding:
        raise StudioError("studio source binding hash differs")
    expected_studio_id = derive_imported_id(
        "artifact", "integra.transcript_topic_studio",
        source["source_revision_id"], expected_source_binding,
    )
    if studio["studio_id"] != expected_studio_id:
        raise StudioError("studio identity differs from source binding")
    _validate_registry_binding(studio, registry)
    validated_bindings = _validate_bindings(list(studio["component_bindings"].values()))
    if studio["component_bindings"] != validated_bindings:
        raise StudioError("component binding keys differ from capabilities")
    if studio["semantic_authority"] != "MACHINE_OUTPUT_REQUIRES_HUMAN_DECISION":
        raise StudioError("studio semantic authority changed")
    if studio["cross_source_alignment"] != "OUT_OF_SCOPE_R8C":
        raise StudioError("studio cross-source boundary changed")
    if studio["source_artifacts_modified"] is not False:
        raise StudioError("studio claims source artifact mutation")
    _validate_records(studio)
    claimed = studio["record_sha256"]
    _sha(claimed, "studio record hash")
    unsigned = copy.deepcopy(studio)
    unsigned["record_sha256"] = ""
    if content_sha256_fn(unsigned) != claimed:
        raise StudioError("studio record hash differs")


def content_sha256_fn(value: Any) -> str:
    return content_sha256(value)


def _validate_registry_binding(studio: dict[str, Any], registry: dict[str, Any]) -> None:
    """Prove the embedded source tuple against the authoritative registry snapshot."""

    try:
        validate_registry(registry)
    except RegistryError as error:
        raise StudioError("project/source registry is invalid") from error
    binding = studio["registry_binding"]
    if (
        registry["registry_id"] != binding["registry_id"]
        or registry["record_sha256"] != binding["registry_record_sha256"]
    ):
        raise StudioError("authoritative registry snapshot differs")
    project = _find(registry["projects"], "project_id", studio["project_id"], "project")
    source = _find(registry["sources"], "source_id", studio["source"]["source_id"], "source")
    revision = _find(
        source["revisions"], "revision_id", studio["source"]["source_revision_id"],
        "source revision",
    )
    if (
        content_sha256_fn(project) != binding["project_record_sha256"]
        or content_sha256_fn(source) != binding["source_record_sha256"]
        or studio["project_id"] not in source["project_ids"]
        or source["current_revision_id"] != revision["revision_id"]
        or source["source_type"] != studio["source"]["source_type"]
        or revision["revision_sha256"] != studio["source"]["source_revision_sha256"]
    ):
        raise StudioError("studio source is not present in authoritative registry snapshot")


def _validate_bindings(bindings: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    if not isinstance(bindings, list) or not bindings:
        raise StudioError("component bindings are required")
    result: dict[str, dict[str, Any]] = {}
    for binding in bindings:
        fields = {"capability", "components", "config_sha256", "r5_selection_sha256"}
        if not isinstance(binding, dict) or set(binding) != fields:
            raise StudioError("component binding fields are invalid")
        capability = binding["capability"]
        if capability not in CAPABILITY_OWNERS:
            raise StudioError("component binding capability is unsupported")
        if capability in result:
            raise StudioError("component capability binding is duplicated")
        _sha(binding["config_sha256"], "component config hash")
        if binding["r5_selection_sha256"] != R5_SELECTIONS_SHA256:
            raise StudioError("component binding differs from accepted R5 selection")
        components = binding["components"]
        if not isinstance(components, list) or not components:
            raise StudioError("component binding components are required")
        component_ids: list[str] = []
        for component_index, component in enumerate(components):
            component_fields = {
                "component_id", "commit_sha", "contract_id", "model_id", "model_sha256"
            }
            if not isinstance(component, dict) or set(component) != component_fields:
                raise StudioError("bound component fields are invalid")
            _text(component["component_id"], "component ID")
            _git_sha(component["commit_sha"], "component commit")
            _text(component["contract_id"], "component contract")
            component_id = component["component_id"]
            if component["commit_sha"] != PINNED_COMPONENT_COMMITS.get(component_id):
                raise StudioError("component commit differs from accepted R1 baseline")
            if component["contract_id"] not in PINNED_COMPONENT_CONTRACTS.get(component_id, set()):
                raise StudioError("component contract differs from accepted R1 baseline")
            if component["contract_id"] != CAPABILITY_CONTRACTS[capability][component_index]:
                raise StudioError("component contract differs from accepted R5 capability contract")
            if (component["model_id"] is None) != (component["model_sha256"] is None):
                raise StudioError("component model identity is incomplete")
            if component["model_id"] is not None:
                _text(component["model_id"], "model ID")
                _sha(component["model_sha256"], "model hash")
                if PINNED_COMPONENT_MODELS.get(component_id, {}).get(component["model_id"]) != component["model_sha256"]:
                    raise StudioError("component model differs from accepted R1 baseline")
            component_ids.append(component["component_id"])
        if tuple(component_ids) != CAPABILITY_OWNERS[capability]:
            raise StudioError("components differ from accepted ordered R5 capability owners")
        if capability == "asr" and (
            components[0]["model_id"] != "ggml-large-v3.bin"
            or components[0]["model_sha256"] != PINNED_COMPONENT_MODELS["videotext"]["ggml-large-v3.bin"]
        ):
            raise StudioError("ASR model differs from accepted R1 runtime identity")
        if capability == "topics" and (
            components[0]["model_id"] != "gemma3:4b"
            or components[0]["model_sha256"] != PINNED_COMPONENT_MODELS["seminartext"]["gemma3:4b"]
        ):
            raise StudioError("Topic model differs from accepted R6 runtime identity")
        result[capability] = copy.deepcopy(binding)
    required = {"media_preparation", "asr", "translation", "word_timeline", "topics", "quality_validation", "review_mechanics"}
    if set(result) != required:
        raise StudioError("component binding inventory is incomplete")
    return dict(sorted(result.items()))


def _topic(
    studio: dict[str, Any], timeline_id: str, topic_set_id: str, level: str, sequence: int,
    topic: dict[str, Any],
) -> dict[str, Any]:
    fields = {"native_id", "title", "summary", "confidence", "conflict", "locators", "evidence_refs"}
    if not isinstance(topic, dict) or set(topic) != fields:
        raise StudioError("Topic fields are invalid")
    _text(topic["native_id"], "Topic native ID")
    _text(topic["title"], "Topic title")
    _text(topic["summary"], "Topic summary")
    confidence = _probability(topic["confidence"], "Topic confidence")
    if not isinstance(topic["conflict"], bool):
        raise StudioError("Topic conflict must be boolean")
    _unique_text(topic["evidence_refs"], "Topic evidence", non_empty=True)
    locators = [_locator(item) for item in topic["locators"]]
    locator_types = [item["type"] for item in locators]
    if len(locator_types) != len(set(locator_types)):
        raise StudioError("Topic locator types must be unique")
    _require_source_locator(studio["source"]["source_type"], locators)
    if not any(item["type"] == "ARTIFACT_REVISION" for item in locators):
        raise StudioError("Topic must bind an artifact revision locator")
    _require_exact_source_revision(studio, locators)
    timeline = _artifact(studio, timeline_id, "WORD_TIMELINE")
    words = timeline["metadata"]["words"]
    by_id = {word["word_id"]: word for word in words}
    word_locators = [item for item in locators if item["type"] == "WORD_INTERVAL"]
    if len(word_locators) != 1:
        raise StudioError("Topic must contain exactly one Word Timeline interval")
    interval = word_locators[0]
    start_word = by_id.get(interval["start_word_id"])
    end_word = by_id.get(interval["end_word_id"])
    if (
        start_word is None or end_word is None
        or start_word["sequence"] != interval["start_sequence"]
        or end_word["sequence"] != interval["end_sequence"]
    ):
        raise StudioError("Topic word locator does not resolve in bound Word Timeline")
    evidence = set(topic["evidence_refs"])
    allowed_evidence = {
        word["word_id"] for word in words
        if interval["start_sequence"] <= word["sequence"] <= interval["end_sequence"]
    }
    if not evidence.issubset(allowed_evidence):
        raise StudioError("Topic evidence does not resolve inside its Word Timeline interval")
    if studio["source"]["source_type"] in {"LOCAL_VIDEO", "LOCAL_AUDIO", "YOUTUBE_VIDEO", "YOUTUBE_PLAYLIST"}:
        time_locators = [item for item in locators if item["type"] == "TIME_INTERVAL"]
        if len(time_locators) != 1:
            raise StudioError("media Topic must contain exactly one time interval")
        time_interval = time_locators[0]
        if (
            time_interval["start_seconds"] > start_word["start_seconds"]
            or time_interval["end_seconds"] < end_word["end_seconds"]
        ):
            raise StudioError("Topic time interval does not contain its Word Timeline interval")
    status = "REVIEW_REQUIRED" if topic["conflict"] or confidence < 0.8 else "PROVISIONAL"
    identity_hash = content_sha256_fn(
        {"topic_set_id": topic_set_id, "native_id": topic["native_id"], "locators": locators}
    )
    topic_id = derive_imported_id("topic", "seminartext", topic["native_id"], identity_hash)
    return {
        "topic_id": topic_id,
        "native_id": topic["native_id"],
        "topic_set_id": topic_set_id,
        "level": level,
        "sequence": sequence,
        "title": topic["title"],
        "summary": topic["summary"],
        "confidence": confidence,
        "conflict": topic["conflict"],
        "semantic_status": status,
        "locators": locators,
        "evidence_refs": sorted(topic["evidence_refs"]),
    }


def _locator(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("type") not in LOCATOR_TYPES:
        raise StudioError("source locator type is invalid")
    kind = value["type"]
    expected: dict[str, set[str]] = {
        "TIME_INTERVAL": {"type", "start_seconds", "end_seconds"},
        "WORD_INTERVAL": {"type", "start_word_id", "end_word_id", "start_sequence", "end_sequence"},
        "PAGE_RANGE": {"type", "start_page", "end_page"},
        "SLIDE_RANGE": {"type", "start_slide", "end_slide"},
        "REGION": {"type", "container_type", "container_index", "x", "y", "width", "height"},
        "CHARACTER_RANGE": {"type", "start_char", "end_char"},
        "ARTIFACT_REVISION": {"type", "artifact_id", "revision_id", "content_sha256"},
    }
    if set(value) != expected[kind]:
        raise StudioError("source locator fields are invalid")
    result = copy.deepcopy(value)
    if kind == "TIME_INTERVAL":
        start = _number(value["start_seconds"], "time locator start")
        end = _number(value["end_seconds"], "time locator end")
        if end <= start:
            raise StudioError("time locator must have positive duration")
    elif kind == "WORD_INTERVAL":
        _text(value["start_word_id"], "word locator start ID")
        _text(value["end_word_id"], "word locator end ID")
        start = _nonnegative_int(value["start_sequence"], "word locator start")
        end = _nonnegative_int(value["end_sequence"], "word locator end")
        if end < start:
            raise StudioError("word locator range is reversed")
    elif kind in {"PAGE_RANGE", "SLIDE_RANGE"}:
        prefix = "page" if kind == "PAGE_RANGE" else "slide"
        start = _positive_int(value[f"start_{prefix}"], f"{prefix} locator start")
        end = _positive_int(value[f"end_{prefix}"], f"{prefix} locator end")
        if end < start:
            raise StudioError(f"{prefix} locator range is reversed")
    elif kind == "REGION":
        if value["container_type"] not in {"PAGE", "SLIDE", "IMAGE"}:
            raise StudioError("region container type is invalid")
        _positive_int(value["container_index"], "region container index")
        for field in ("x", "y", "width", "height"):
            number = _number(value[field], f"region {field}")
            if number > 1:
                raise StudioError("region coordinates must be normalized")
        if value["width"] <= 0 or value["height"] <= 0 or value["x"] + value["width"] > 1 or value["y"] + value["height"] > 1:
            raise StudioError("region is outside its container")
    elif kind == "CHARACTER_RANGE":
        start = _nonnegative_int(value["start_char"], "character locator start")
        end = _positive_int(value["end_char"], "character locator end")
        if end <= start:
            raise StudioError("character locator must be non-empty")
    else:
        _urn(value["artifact_id"], "locator artifact ID")
        _urn(value["revision_id"], "locator revision ID")
        _sha(value["content_sha256"], "locator content hash")
    return result


def _require_source_locator(source_type: str, locators: list[dict[str, Any]]) -> None:
    kinds = {item["type"] for item in locators}
    media = {"LOCAL_VIDEO", "LOCAL_AUDIO", "YOUTUBE_VIDEO", "YOUTUBE_PLAYLIST"}
    if source_type in media and not kinds.intersection({"TIME_INTERVAL", "WORD_INTERVAL"}):
        raise StudioError("media artifact lacks a source locator")
    expected_document_locators = {
        "PDF": {"PAGE_RANGE", "REGION"},
        "PPTX": {"SLIDE_RANGE", "REGION"},
        "DOCX": {"CHARACTER_RANGE"},
        "TXT": {"CHARACTER_RANGE"},
        "MARKDOWN": {"CHARACTER_RANGE"},
        "IMAGE": {"REGION"},
        "SCAN": {"REGION"},
    }
    expected = expected_document_locators.get(source_type)
    if expected is not None and not kinds.intersection(expected):
        raise StudioError("document artifact lacks a source-type-native locator")
    region_container = {"PDF": "PAGE", "PPTX": "SLIDE", "IMAGE": "IMAGE", "SCAN": "PAGE"}.get(source_type)
    if region_container is not None and any(
        item["type"] == "REGION" and item["container_type"] != region_container
        for item in locators
    ):
        raise StudioError("region locator container differs from source type")
    if source_type not in media and source_type not in expected_document_locators:
        raise StudioError("studio source type is unsupported")


def _require_exact_source_revision(studio: dict[str, Any], locators: list[dict[str, Any]]) -> None:
    source = studio["source"]
    expected = {
        "type": "ARTIFACT_REVISION",
        "artifact_id": source["source_id"],
        "revision_id": source["source_revision_id"],
        "content_sha256": source["source_revision_sha256"],
    }
    if expected not in locators:
        raise StudioError("artifact does not bind the studio source revision exactly")


def _validate_records(studio: dict[str, Any]) -> None:
    artifact_ids: set[str] = set()
    artifact_map: dict[str, dict[str, Any]] = {}
    native_artifacts: set[tuple[str, str]] = set()
    for artifact in studio["artifacts"]:
        required = {
            "artifact_id", "native_id", "kind", "content_sha256", "created_at",
            "capability", "component_binding_sha256", "parent_ids", "locators",
            "semantic_status", "metadata",
            "metadata_sha256",
        }
        if not isinstance(artifact, dict) or set(artifact) != required:
            raise StudioError("artifact record fields are invalid")
        _urn(artifact["artifact_id"], "artifact ID")
        if artifact["artifact_id"] in artifact_ids:
            raise StudioError("artifact IDs must be unique")
        artifact_ids.add(artifact["artifact_id"])
        artifact_map[artifact["artifact_id"]] = artifact
        _text(artifact["native_id"], "artifact native ID")
        _timestamp(artifact["created_at"])
        _sha(artifact["content_sha256"], "artifact content hash")
        _sha(artifact["metadata_sha256"], "artifact metadata hash")
        _sha(artifact["component_binding_sha256"], "artifact component binding hash")
        if artifact["kind"] not in ARTIFACT_KINDS or artifact["capability"] not in studio["component_bindings"]:
            raise StudioError("artifact kind or capability is invalid")
        if content_sha256_fn(studio["component_bindings"][artifact["capability"]]) != artifact["component_binding_sha256"]:
            raise StudioError("artifact component binding drifted")
        if (artifact["native_id"], artifact["kind"]) in native_artifacts:
            raise StudioError("artifact native identity is duplicated")
        native_artifacts.add((artifact["native_id"], artifact["kind"]))
        locators = [_locator(locator) for locator in artifact["locators"]]
        _require_source_locator(studio["source"]["source_type"], locators)
        _require_exact_source_revision(studio, locators)
        if artifact["semantic_status"] not in SEMANTIC_STATES | {"NOT_APPLICABLE"}:
            raise StudioError("artifact semantic status is invalid")
        if artifact["kind"] in {"MACHINE_TRANSCRIPT", "TRANSLATION", "TOPIC_SET", "TOPIC_HIERARCHY"} and artifact["semantic_status"] not in SEMANTIC_STATES:
            raise StudioError("machine semantic artifact escaped review authority")
        if content_sha256_fn(artifact["metadata"]) != artifact["metadata_sha256"]:
            raise StudioError("artifact metadata hash differs")
        binding = studio["component_bindings"][artifact["capability"]]
        component_identity = "+".join(item["component_id"] for item in binding["components"])
        identity_hash = content_sha256_fn({
            "kind": artifact["kind"],
            "component_ids": [item["component_id"] for item in binding["components"]],
            "native_id": artifact["native_id"],
            "content_sha256": artifact["content_sha256"],
        })
        if artifact["artifact_id"] != derive_imported_id(
            "artifact", component_identity, artifact["native_id"], identity_hash
        ):
            raise StudioError("artifact stable identity differs")
    known_parent_ids = artifact_ids | {studio["source"]["source_revision_id"]}
    for artifact in studio["artifacts"]:
        _unique_text(artifact["parent_ids"], "artifact parents")
        if artifact["parent_ids"] != sorted(artifact["parent_ids"]):
            raise StudioError("artifact parents must be sorted")
        if any(parent not in known_parent_ids or parent == artifact["artifact_id"] for parent in artifact["parent_ids"]):
            raise StudioError("artifact parent is unknown or self-referential")
        _validate_artifact_metadata(artifact, artifact_map)
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(artifact_id: str) -> None:
        if artifact_id in visiting:
            raise StudioError("artifact provenance contains a cycle")
        if artifact_id in visited:
            return
        visiting.add(artifact_id)
        for parent in artifact_map[artifact_id]["parent_ids"]:
            if parent in artifact_map:
                visit(parent)
        visiting.remove(artifact_id)
        visited.add(artifact_id)

    for artifact_id in artifact_ids:
        visit(artifact_id)

    seen_levels: set[str] = set()
    expected_level_order: list[str] = []
    for topic_set in studio["topic_sets"]:
        required = {
            "topic_set_id", "native_id", "content_sha256", "created_at",
            "timeline_id", "level", "semantic_status",
            "component_binding_sha256", "topics",
            "payload_sha256",
        }
        if not isinstance(topic_set, dict) or set(topic_set) != required:
            raise StudioError("Topic set fields are invalid")
        level = topic_set["level"]
        if level not in TOPIC_LEVELS or level in seen_levels:
            raise StudioError("Topic set level is invalid or duplicated")
        seen_levels.add(level)
        expected_level_order.append(level)
        _text(topic_set["native_id"], "Topic-set native ID")
        _sha(topic_set["content_sha256"], "Topic-set content hash")
        _sha(topic_set["payload_sha256"], "Topic-set payload hash")
        _timestamp(topic_set["created_at"])
        timeline = artifact_map.get(topic_set["timeline_id"])
        if timeline is None or timeline["kind"] != "WORD_TIMELINE":
            raise StudioError("Topic set timeline is unknown")
        expected_binding = content_sha256_fn(studio["component_bindings"]["topics"])
        if topic_set["component_binding_sha256"] != expected_binding:
            raise StudioError("Topic set component binding drifted")
        set_hash = content_sha256_fn({
            "native_id": topic_set["native_id"],
            "level": level,
            "content_sha256": topic_set["content_sha256"],
        })
        if topic_set["topic_set_id"] != derive_imported_id(
            "artifact", "seminartext", topic_set["native_id"], set_hash
        ):
            raise StudioError("Topic-set stable identity differs")
        if not isinstance(topic_set["topics"], list) or not topic_set["topics"]:
            raise StudioError("Topic set is empty")
        for sequence, stored_topic in enumerate(topic_set["topics"]):
            expected_topic_fields = {
                "topic_id", "native_id", "topic_set_id", "level", "sequence",
                "title", "summary", "confidence", "conflict", "semantic_status",
                "locators", "evidence_refs",
            }
            if not isinstance(stored_topic, dict) or set(stored_topic) != expected_topic_fields:
                raise StudioError("Topic record fields are invalid")
            topic_input = {
                key: copy.deepcopy(stored_topic[key])
                for key in ("native_id", "title", "summary", "confidence", "conflict", "locators", "evidence_refs")
            }
            expected_topic = _topic(
                studio, topic_set["timeline_id"], topic_set["topic_set_id"],
                level, sequence, topic_input,
            )
            if stored_topic != expected_topic:
                raise StudioError("Topic record differs from deterministic proposal")
        _ensure_non_overlapping(topic_set["topics"])
        if topic_set["payload_sha256"] != content_sha256_fn(topic_set["topics"]):
            raise StudioError("Topic-set payload hash differs")
        expected_status = "REVIEW_REQUIRED" if any(
            item["semantic_status"] == "REVIEW_REQUIRED" for item in topic_set["topics"]
        ) else "PROVISIONAL"
        if topic_set["semantic_status"] != expected_status:
            raise StudioError("Topic-set authority differs from members")
    if expected_level_order != sorted(expected_level_order, key=TOPIC_LEVELS.index):
        raise StudioError("Topic sets are not in level order")
    topics = _all_topics(studio)
    finding_ids: set[str] = set()
    for finding in studio["quality_findings"]:
        required = {
            "finding_id", "native_id", "artifact_id", "code", "severity",
            "confidence", "locators", "detail", "created_at", "review_required",
            "finding_sha256",
        }
        if not isinstance(finding, dict) or set(finding) != required:
            raise StudioError("quality finding fields are invalid")
        _urn(finding["finding_id"], "quality finding ID")
        if finding["finding_id"] in finding_ids:
            raise StudioError("quality finding ID is duplicated")
        finding_ids.add(finding["finding_id"])
        _text(finding["native_id"], "quality finding native ID")
        _text(finding["code"], "quality finding code")
        _text(finding["detail"], "quality finding detail")
        _timestamp(finding["created_at"])
        if finding["severity"] not in {"INFO", "WARN", "ERROR"}:
            raise StudioError("quality finding severity is invalid")
        if finding["confidence"] is not None:
            _probability(finding["confidence"], "quality finding confidence")
        locators = [_locator(item) for item in finding["locators"]]
        if not locators:
            raise StudioError("quality finding requires an exact source locator")
        _require_source_locator(studio["source"]["source_type"], locators)
        if finding["artifact_id"] not in artifact_ids:
            raise StudioError("quality finding artifact is unknown")
        if content_sha256_fn({key: finding[key] for key in ("artifact_id", "code", "severity", "confidence", "locators", "detail")}) != finding["finding_sha256"]:
            raise StudioError("quality finding hash differs")
        expected_finding_id = derive_imported_id(
            "evidence", "integra.quality", finding["native_id"], finding["finding_sha256"]
        )
        if finding["finding_id"] != expected_finding_id:
            raise StudioError("quality finding stable identity differs")
        expected_review = finding["severity"] == "ERROR" or finding["confidence"] is not None and finding["confidence"] < 0.8
        if finding["review_required"] is not expected_review:
            raise StudioError("quality finding review status differs")
    hierarchy_ids: set[str] = set()
    for hierarchy in studio["hierarchies"]:
        required = {
            "hierarchy_id", "native_id", "created_at", "content_sha256",
            "semantic_status", "edges",
        }
        if not isinstance(hierarchy, dict) or set(hierarchy) != required:
            raise StudioError("Topic hierarchy fields are invalid")
        _urn(hierarchy["hierarchy_id"], "Topic hierarchy ID")
        if hierarchy["hierarchy_id"] in hierarchy_ids:
            raise StudioError("Topic hierarchy ID is duplicated")
        hierarchy_ids.add(hierarchy["hierarchy_id"])
        _text(hierarchy["native_id"], "Topic hierarchy native ID")
        _timestamp(hierarchy["created_at"])
        if hierarchy["semantic_status"] != "PROVISIONAL":
            raise StudioError("Topic hierarchy escaped provisional authority")
        if not isinstance(hierarchy["edges"], list) or not hierarchy["edges"]:
            raise StudioError("Topic hierarchy is empty")
        if hierarchy["edges"] != sorted(
            hierarchy["edges"], key=lambda item: (item.get("parent_topic_id", ""), item.get("child_topic_id", ""))
        ):
            raise StudioError("Topic hierarchy edges are not sorted")
        children: set[str] = set()
        for edge in hierarchy["edges"]:
            if not isinstance(edge, dict) or set(edge) != {"child_topic_id", "parent_topic_id"}:
                raise StudioError("Topic hierarchy edge fields are invalid")
            child = topics.get(edge["child_topic_id"])
            parent = topics.get(edge["parent_topic_id"])
            if child is None or parent is None:
                raise StudioError("Topic hierarchy references unknown Topic")
            if child["topic_id"] in children:
                raise StudioError("Topic hierarchy gives a child multiple parents")
            children.add(child["topic_id"])
            if TOPIC_LEVELS.index(parent["level"]) <= TOPIC_LEVELS.index(child["level"]):
                raise StudioError("Topic hierarchy parent is not coarser")
            if not _locator_contains(parent["locators"], child["locators"]):
                raise StudioError("Topic hierarchy parent does not contain child")
        expected_hash = content_sha256_fn(hierarchy["edges"])
        if hierarchy["content_sha256"] != expected_hash:
            raise StudioError("Topic hierarchy hash differs")
        if hierarchy["hierarchy_id"] != derive_imported_id(
            "artifact", "seminartext", hierarchy["native_id"], expected_hash
        ):
            raise StudioError("Topic hierarchy stable identity differs")

    candidates = set(_exception_candidates(studio))
    package_ids: set[str] = set()
    covered_unresolved: set[str] = set()
    for package in studio["review_packages"]:
        required = {
            "package_id", "native_id", "created_at", "status", "scope_sha256",
            "member_ids", "neighbor_topic_ids", "member_bindings",
            "neighbor_bindings", "source_revision_id",
        }
        if package.get("status") == "DECIDED":
            required.add("decision_id")
        if not isinstance(package, dict) or set(package) != required:
            raise StudioError("review package fields are invalid")
        _urn(package["package_id"], "review package ID")
        if package["package_id"] in package_ids:
            raise StudioError("review package ID is duplicated")
        package_ids.add(package["package_id"])
        _text(package["native_id"], "review package native ID")
        _timestamp(package["created_at"])
        if package["status"] not in {"REVIEW_REQUIRED", "DECIDED"}:
            raise StudioError("review package status is invalid")
        _unique_text(package["member_ids"], "review package members", non_empty=True)
        _unique_text(package["neighbor_topic_ids"], "review package neighbors")
        if package["member_ids"] != sorted(package["member_ids"]) or package["neighbor_topic_ids"] != sorted(package["neighbor_topic_ids"]):
            raise StudioError("review package scope lists must be sorted")
        if package["source_revision_id"] != studio["source"]["source_revision_id"]:
            raise StudioError("review package source revision differs")
        if any(member not in candidates for member in package["member_ids"]):
            raise StudioError("review package member is no longer an exception")
        _validate_review_package_scope(studio, package)
        if package["package_id"] != derive_imported_id(
            "review", "integra.review_service", package["native_id"], package["scope_sha256"]
        ):
            raise StudioError("review package stable identity differs")
        if any(item not in topics for item in package["neighbor_topic_ids"]):
            raise StudioError("review package neighbor is unknown")
        if package["status"] == "REVIEW_REQUIRED":
            if covered_unresolved.intersection(package["member_ids"]):
                raise StudioError("exception appears in multiple unresolved packages")
            covered_unresolved.update(package["member_ids"])
    decision_ids: set[str] = set()
    for decision in studio["review_decisions"]:
        required = {
            "decision_id", "native_id", "package_id", "scope_sha256", "authority",
            "decided_at", "lease_id", "lease_generation", "lease_operation_id", "resolutions",
            "decision_sha256", "source_artifacts_modified",
        }
        if not isinstance(decision, dict) or set(decision) != required:
            raise StudioError("review decision fields are invalid")
        _urn(decision["decision_id"], "review decision ID")
        if decision["decision_id"] in decision_ids or decision["package_id"] not in package_ids:
            raise StudioError("review decision identity or package is invalid")
        decision_ids.add(decision["decision_id"])
        if decision["authority"] != "HUMAN_DOMAIN_REVIEW" or decision["source_artifacts_modified"] is not False:
            raise StudioError("review decision authority or mutation claim is invalid")
        _text(decision["native_id"], "review decision native ID")
        _timestamp(decision["decided_at"])
        _urn(decision["lease_id"], "review decision lease ID")
        _urn(decision["lease_operation_id"], "review decision operation ID")
        _positive_int(decision["lease_generation"], "review decision lease generation")
        package = next(item for item in studio["review_packages"] if item["package_id"] == decision["package_id"])
        if decision["scope_sha256"] != package["scope_sha256"]:
            raise StudioError("review decision scope differs from package")
        if not isinstance(decision["resolutions"], list) or len(decision["resolutions"]) != len(package["member_ids"]):
            raise StudioError("review decision does not resolve complete package")
        if decision["resolutions"] != sorted(decision["resolutions"], key=lambda item: item.get("member_id", "")):
            raise StudioError("review decision resolutions are not sorted")
        for resolution in decision["resolutions"]:
            if not isinstance(resolution, dict) or set(resolution) != {"member_id", "resolution", "decision_payload_sha256"}:
                raise StudioError("review resolution fields are invalid")
            if resolution["resolution"] not in {"ACCEPT", "REJECT", "ADJUST"}:
                raise StudioError("review resolution is unsupported")
            _sha(resolution["decision_payload_sha256"], "review decision payload hash")
        if [item["member_id"] for item in decision["resolutions"]] != package["member_ids"]:
            raise StudioError("review decision members differ from package")
        expected_decision_hash = content_sha256_fn({
            "package_id": decision["package_id"],
            "scope_sha256": decision["scope_sha256"],
            "authority": decision["authority"],
            "lease_operation_id": decision["lease_operation_id"],
            "resolutions": decision["resolutions"],
        })
        if decision["decision_sha256"] != expected_decision_hash:
            raise StudioError("review decision hash differs")
        if decision["decision_id"] != derive_imported_id(
            "review", "integra.review_service", decision["native_id"], expected_decision_hash
        ):
            raise StudioError("review decision stable identity differs")
    for package in studio["review_packages"]:
        if package["status"] == "DECIDED" and package.get("decision_id") not in decision_ids:
            raise StudioError("decided package lacks decision")
        if package["status"] == "REVIEW_REQUIRED" and "decision_id" in package:
            raise StudioError("unresolved package contains decision")
def _validate_artifact_metadata(
    artifact: dict[str, Any], artifact_map: dict[str, dict[str, Any]]
) -> None:
    metadata = artifact["metadata"]
    if not isinstance(metadata, dict):
        raise StudioError("artifact metadata must be an object")
    if artifact["kind"] == "MACHINE_TRANSCRIPT":
        if set(metadata) != {"language", "word_count", "confidence", "wording"}:
            raise StudioError("transcript metadata fields are invalid")
        _text(metadata["language"], "transcript language")
        _positive_int(metadata["word_count"], "transcript word count")
        confidence = _probability(metadata["confidence"], "transcript confidence")
        if metadata["wording"] != "ORIGINAL_MACHINE_WORDING":
            raise StudioError("transcript original wording marker changed")
        expected_status = "REVIEW_REQUIRED" if confidence < 0.8 else "PROVISIONAL"
        if artifact["semantic_status"] != expected_status:
            raise StudioError("transcript authority differs from confidence")
    elif artifact["kind"] == "TRANSLATION":
        if set(metadata) != {
            "source_language", "target_language", "confidence",
            "original_transcript_id", "wording",
        }:
            raise StudioError("translation metadata fields are invalid")
        _text(metadata["source_language"], "translation source language")
        _text(metadata["target_language"], "translation target language")
        confidence = _probability(metadata["confidence"], "translation confidence")
        parent = artifact_map.get(metadata["original_transcript_id"])
        if (
            parent is None
            or parent["kind"] != "MACHINE_TRANSCRIPT"
            or artifact["parent_ids"] != [parent["artifact_id"]]
            or parent["metadata"].get("language") != metadata["source_language"]
            or metadata["source_language"] == metadata["target_language"]
        ):
            raise StudioError("translation lineage differs from original transcript")
        if metadata["wording"] != "DERIVED_TRANSLATION":
            raise StudioError("translation wording marker changed")
        expected_status = "REVIEW_REQUIRED" if confidence < 0.8 else "PROVISIONAL"
        if artifact["semantic_status"] != expected_status:
            raise StudioError("translation authority differs from confidence")
    elif artifact["kind"] == "WORD_TIMELINE":
        if set(metadata) != {"transcript_id", "words"}:
            raise StudioError("Word Timeline metadata fields are invalid")
        parent = artifact_map.get(metadata["transcript_id"])
        if (
            parent is None
            or parent["kind"] != "MACHINE_TRANSCRIPT"
            or artifact["parent_ids"] != [parent["artifact_id"]]
            or artifact["semantic_status"] != "NOT_APPLICABLE"
        ):
            raise StudioError("Word Timeline lineage is invalid")
        words = metadata["words"]
        if not isinstance(words, list) or not words:
            raise StudioError("Word Timeline is empty")
        last_end = -1.0
        seen_words: set[str] = set()
        for index, word in enumerate(words):
            if not isinstance(word, dict) or set(word) != {
                "word_id", "sequence", "text", "start_seconds", "end_seconds", "confidence"
            }:
                raise StudioError("Word Timeline entry fields are invalid")
            _text(word["word_id"], "word ID")
            if word["word_id"] in seen_words or word["sequence"] != index:
                raise StudioError("Word Timeline identity or sequence is invalid")
            seen_words.add(word["word_id"])
            _text(word["text"], "word text")
            start = _number(word["start_seconds"], "word start")
            end = _number(word["end_seconds"], "word end")
            _probability(word["confidence"], "word confidence")
            if end <= start or start < last_end:
                raise StudioError("Word Timeline intervals are invalid")
            last_end = end


def _review_candidate(studio: dict[str, Any], candidate_id: str) -> dict[str, Any]:
    for topic_set in studio["topic_sets"]:
        for topic in topic_set["topics"]:
            if topic["topic_id"] == candidate_id:
                return topic
    for finding in studio["quality_findings"]:
        if finding["finding_id"] == candidate_id:
            return finding
    for artifact in studio["artifacts"]:
        if artifact["artifact_id"] == candidate_id:
            return artifact
    raise StudioError("review candidate is unknown")


def _validate_review_package_scope(studio: dict[str, Any], package: dict[str, Any]) -> None:
    member_bindings = [
        {"member_id": item, "content_sha256": content_sha256_fn(_review_candidate(studio, item))}
        for item in package["member_ids"]
    ]
    neighbor_bindings = [
        {"topic_id": item, "content_sha256": content_sha256_fn(_review_candidate(studio, item))}
        for item in package["neighbor_topic_ids"]
    ]
    if package["member_bindings"] != member_bindings or package["neighbor_bindings"] != neighbor_bindings:
        raise StudioError("review package candidate content is stale")
    scope = {
        "member_ids": package["member_ids"],
        "neighbor_topic_ids": package["neighbor_topic_ids"],
        "member_bindings": member_bindings,
        "neighbor_bindings": neighbor_bindings,
        "source_revision_id": studio["source"]["source_revision_id"],
    }
    if content_sha256_fn(scope) != package["scope_sha256"]:
        raise StudioError("review package scope hash differs")


def _validate_review_lease(
    studio: dict[str, Any], package: dict[str, Any], lease: dict[str, Any],
    lease_store: LeaseStore, decided_at: str,
) -> None:
    if not isinstance(lease, dict):
        raise StudioError("review decision lease is required")
    try:
        LeaseStore._validate_shape(lease)
        LeaseStore._validate_temporal_order(lease)
    except (KeyError, LeaseConflict, ValueError) as error:
        raise StudioError("review lease record is invalid") from error
    if not isinstance(lease_store, LeaseStore):
        raise StudioError("review decision requires the authoritative LeaseStore")
    persisted = lease_store.read(studio["project_id"], package["package_id"])
    if persisted != lease:
        raise StudioError("review lease differs from authoritative LeaseStore")
    mutable = lease["mutable_entity"]
    if (
        lease["project_id"] != studio["project_id"]
        or mutable["namespace"] != "review"
        or mutable["entity_id"] != package["package_id"]
    ):
        raise StudioError("review lease does not cover package")
    if (
        lease["state"] != "ACTIVE"
        or lease["artifact_precondition"]["content_sha256"] != package["scope_sha256"]
        or lease["artifact_precondition"]["revision_id"] != package["package_id"]
    ):
        raise StudioError("review lease is not active")
    if lease["writer"]["component_id"] != "integra.review_service":
        raise StudioError("review lease writer is not authorized")
    decided = _timestamp(decided_at)
    if decided < _timestamp(lease["acquired_at"]) or decided >= _timestamp(lease["expires_at"]):
        raise StudioError("review decision is outside active lease interval")
    if datetime.now(timezone.utc) >= _timestamp(lease["expires_at"]):
        raise StudioError("review lease is expired at execution time")


def _exception_candidates(studio: dict[str, Any]) -> dict[str, str]:
    result = {
        item["artifact_id"]: "SEMANTIC_ARTIFACT"
        for item in studio["artifacts"]
        if item["semantic_status"] == "REVIEW_REQUIRED"
    }
    result.update({
        item["finding_id"]: "QUALITY_FINDING"
        for item in studio["quality_findings"]
        if item["review_required"]
    })
    result.update(
        {
            topic["topic_id"]: "TOPIC"
            for topic_set in studio["topic_sets"]
            for topic in topic_set["topics"]
            if topic["semantic_status"] == "REVIEW_REQUIRED"
        }
    )
    return result


def _all_topics(studio: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for topic_set in studio["topic_sets"]:
        for topic in topic_set["topics"]:
            if topic["topic_id"] in result:
                raise StudioError("Topic ID appears in multiple sets")
            result[topic["topic_id"]] = topic
    return result


def _ensure_non_overlapping(topics: list[dict[str, Any]]) -> None:
    intervals: list[tuple[float, float]] = []
    for topic in topics:
        for locator in topic["locators"]:
            if locator["type"] == "TIME_INTERVAL":
                intervals.append((locator["start_seconds"], locator["end_seconds"]))
                break
    if len(intervals) == len(topics):
        ordered = sorted(intervals)
        if any(current[0] < previous[1] for previous, current in zip(ordered, ordered[1:])):
            raise StudioError("Topics in one set overlap")


def _locator_contains(parent_locators: list[dict[str, Any]], child_locators: list[dict[str, Any]]) -> bool:
    parent_by_type = {item["type"]: item for item in parent_locators}
    compared = 0
    for child in child_locators:
        parent = parent_by_type.get(child["type"])
        if parent is None:
            continue
        compared += 1
        kind = child["type"]
        contains = False
        if kind == "TIME_INTERVAL":
            contains = parent["start_seconds"] <= child["start_seconds"] and parent["end_seconds"] >= child["end_seconds"]
        elif kind == "WORD_INTERVAL":
            contains = parent["start_sequence"] <= child["start_sequence"] and parent["end_sequence"] >= child["end_sequence"]
        elif kind == "PAGE_RANGE":
            contains = parent["start_page"] <= child["start_page"] and parent["end_page"] >= child["end_page"]
        elif kind == "SLIDE_RANGE":
            contains = parent["start_slide"] <= child["start_slide"] and parent["end_slide"] >= child["end_slide"]
        elif kind == "CHARACTER_RANGE":
            contains = parent["start_char"] <= child["start_char"] and parent["end_char"] >= child["end_char"]
        elif kind == "REGION":
            contains = (
                parent["container_type"] == child["container_type"]
                and parent["container_index"] == child["container_index"]
                and parent["x"] <= child["x"] and parent["y"] <= child["y"]
                and parent["x"] + parent["width"] >= child["x"] + child["width"]
                and parent["y"] + parent["height"] >= child["y"] + child["height"]
            )
        elif kind == "ARTIFACT_REVISION":
            contains = parent == child
        if not contains:
            return False
    return compared > 0


def _artifact(studio: dict[str, Any], artifact_id: str, kind: str | None = None) -> dict[str, Any]:
    artifact = _find(studio["artifacts"], "artifact_id", artifact_id, "artifact")
    if kind is not None and artifact["kind"] != kind:
        raise StudioError(f"artifact must be {kind}")
    return artifact


def _find(items: list[dict[str, Any]], field: str, value: str, label: str, *, required: bool = True) -> dict[str, Any] | None:
    matches = [item for item in items if item.get(field) == value]
    if len(matches) > 1:
        raise StudioError(f"duplicate {label}")
    if not matches:
        if required:
            raise StudioError(f"{label} not found")
        return None
    return matches[0]


def _seal(studio: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(studio)
    result["record_sha256"] = ""
    result["record_sha256"] = content_sha256_fn(result)
    return result


def _advance(studio: dict[str, Any], occurred_at: str) -> dict[str, Any]:
    if _timestamp(occurred_at) < _timestamp(studio["updated_at"]):
        raise StudioError("studio update time cannot move backwards")
    studio["updated_at"] = occurred_at
    studio["revision"] += 1
    return _seal(studio)


def _active(studio: dict[str, Any]) -> None:
    if studio["status"] != "ACTIVE":
        raise StudioError("studio is not active")


def _timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise StudioError("timestamp must be UTC RFC3339")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise StudioError("timestamp is invalid") from error
    if parsed.tzinfo != timezone.utc:
        raise StudioError("timestamp must use UTC")
    return parsed


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise StudioError(f"{label} must be non-empty text")
    return value


def _sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or not SHA256.fullmatch(value):
        raise StudioError(f"{label} must be a lowercase SHA-256")
    return value


def _git_sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or not GIT_SHA.fullmatch(value):
        raise StudioError(f"{label} must be a lowercase Git SHA")
    return value


def _urn(value: Any, label: str) -> str:
    if not isinstance(value, str) or not URN.fullmatch(value):
        raise StudioError(f"{label} must be an Integra URN")
    return value


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise StudioError(f"{label} must be a non-negative number")
    return float(value)


def _probability(value: Any, label: str) -> float:
    number = _number(value, label)
    if number > 1:
        raise StudioError(f"{label} must be between zero and one")
    return number


def _nonnegative_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise StudioError(f"{label} must be a non-negative integer")
    return value


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise StudioError(f"{label} must be a positive integer")
    return value


def _unique_text(value: Any, label: str, *, non_empty: bool = False) -> list[str]:
    if (
        not isinstance(value, list)
        or non_empty and not value
        or any(not isinstance(item, str) or not item for item in value)
        or len(value) != len(set(value))
    ):
        raise StudioError(f"{label} must be a unique text list")
    return value
