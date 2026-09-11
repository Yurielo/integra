"""Deterministic Projects & Sources v1 registry.

The registry is an Integra-owned control-plane artifact.  It indexes immutable
source evidence and never writes to a source path or remote provider.
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
from typing import Any

from .documents import validate_document_record
from .identity import derive_imported_id
from .playlist import validate_discovery
from .protocol import canonical_json, content_sha256


PROJECT_KINDS = {"SEMINAR", "COURSE", "SERIES", "EVENT"}
PROJECT_LIFECYCLES = {"ACTIVE", "ARCHIVED"}
SOURCE_LIFECYCLES = {"ACTIVE", "UNAVAILABLE", "ARCHIVED"}
SOURCE_TYPES = {
    "LOCAL_VIDEO", "LOCAL_AUDIO", "YOUTUBE_VIDEO", "YOUTUBE_PLAYLIST",
    "PDF", "PPTX", "DOCX", "TXT", "MARKDOWN", "IMAGE", "SCAN",
}
LOCAL_SUFFIXES = {
    ".mp4": ("LOCAL_VIDEO", "video/mp4"),
    ".mov": ("LOCAL_VIDEO", "video/quicktime"),
    ".m4v": ("LOCAL_VIDEO", "video/x-m4v"),
    ".mkv": ("LOCAL_VIDEO", "video/x-matroska"),
    ".mp3": ("LOCAL_AUDIO", "audio/mpeg"),
    ".m4a": ("LOCAL_AUDIO", "audio/mp4"),
    ".wav": ("LOCAL_AUDIO", "audio/wav"),
    ".flac": ("LOCAL_AUDIO", "audio/flac"),
    ".aac": ("LOCAL_AUDIO", "audio/aac"),
}
DOCUMENT_TYPES = {
    "PDF": "PDF", "PPTX": "PPTX", "DOCX": "DOCX", "TXT": "TXT",
    "MARKDOWN": "MARKDOWN", "IMAGE": "IMAGE",
}


class RegistryError(RuntimeError):
    """Raised when registry evidence is incomplete, conflicting, or unsafe."""


def new_registry(registry_key: str, created_at: str) -> dict[str, Any]:
    """Create one empty deterministic registry for an immutable native key."""

    _text(registry_key, "registry key")
    _timestamp(created_at)
    identity_hash = content_sha256(
        {"component": "integra.project_source_registry", "registry_key": registry_key}
    )
    value = {
        "schema_version": "1.0",
        "registry_id": derive_imported_id(
            "artifact", "integra.project_source_registry", registry_key, identity_hash
        ),
        "registry_key": registry_key,
        "created_at": created_at,
        "updated_at": created_at,
        "revision": 0,
        "projects": [],
        "sources": [],
        "record_sha256": "",
    }
    return _seal(value)


def register_project(
    registry: dict[str, Any], *, project_key: str, kind: str, title: str,
    occurred_at: str,
) -> tuple[dict[str, Any], str]:
    """Create or reopen a project; an identical registration is idempotent."""

    validate_registry(registry)
    _text(project_key, "project key")
    _text(title, "project title")
    _timestamp(occurred_at)
    if kind not in PROJECT_KINDS:
        raise RegistryError("project kind is unsupported")
    identity_hash = content_sha256(
        {"component": "integra.project_registry", "project_key": project_key, "kind": kind}
    )
    project_id = derive_imported_id(
        "project", "integra.project_registry", project_key, identity_hash
    )
    result = copy.deepcopy(registry)
    existing = _project_by_id(result, project_id, required=False)
    if existing is not None:
        if existing["project_key"] != project_key or existing["identity_sha256"] != identity_hash:
            raise RegistryError("project identity conflict")
        if existing["kind"] != kind:
            raise RegistryError("project kind conflicts with stable identity")
        return registry, project_id
    if any(item["project_key"] == project_key for item in result["projects"]):
        raise RegistryError("project key already maps to a different identity")
    project = {
        "project_id": project_id,
        "project_key": project_key,
        "identity_sha256": identity_hash,
        "kind": kind,
        "title": title,
        "lifecycle": "ACTIVE",
        "created_at": occurred_at,
        "updated_at": occurred_at,
        "revision": 1,
        "source_ids": [],
        "history": [],
    }
    _append_project_event(project, "CREATED", occurred_at, {"kind": kind, "title": title})
    result["projects"].append(project)
    result["projects"].sort(key=lambda item: item["project_id"])
    return _advance(result, occurred_at), project_id


def update_project(
    registry: dict[str, Any], project_id: str, *, occurred_at: str,
    title: str | None = None, lifecycle: str | None = None,
) -> dict[str, Any]:
    """Record an explicit title or lifecycle transition in project history."""

    validate_registry(registry)
    _timestamp(occurred_at)
    if title is None and lifecycle is None:
        raise RegistryError("project update has no changes")
    result = copy.deepcopy(registry)
    project = _project_by_id(result, project_id)
    changed = False
    if title is not None:
        _text(title, "project title")
        if title != project["title"]:
            previous = project["title"]
            project["title"] = title
            _append_project_event(project, "RENAMED", occurred_at, {"from": previous, "to": title})
            changed = True
    if lifecycle is not None:
        if lifecycle not in PROJECT_LIFECYCLES:
            raise RegistryError("project lifecycle is unsupported")
        if lifecycle != project["lifecycle"]:
            previous = project["lifecycle"]
            project["lifecycle"] = lifecycle
            _append_project_event(
                project, "LIFECYCLE_CHANGED", occurred_at,
                {"from": previous, "to": lifecycle},
            )
            changed = True
    if not changed:
        return registry
    project["revision"] = len(project["history"])
    project["updated_at"] = occurred_at
    return _advance(result, occurred_at)


def register_local_media(
    registry: dict[str, Any], project_id: str, source_path: Path, *, captured_at: str,
) -> tuple[dict[str, Any], str]:
    """Index one local audio/video file by verified bytes without modifying it."""

    path = Path(source_path)
    _timestamp(captured_at)
    media = LOCAL_SUFFIXES.get(path.suffix.lower())
    if media is None:
        raise RegistryError("local media type is unsupported")
    digest, size_bytes, prefix, locator, file_identity = _hash_regular_file(path)
    source_type, media_type = media
    container_validation = _validate_media_signature(path.suffix.lower(), prefix)
    identity_hash = content_sha256(
        {"component": "integra.local_media", "content_sha256": digest}
    )
    source_id = derive_imported_id(
        "source", "integra.local_media", digest, identity_hash
    )
    revision = _source_revision(
        source_id, digest, captured_at, "AVAILABLE",
        {
            "kind": "LOCAL_FILE", "component": "integra.local_media",
            "locator": locator, "media_type": media_type,
            "size_bytes": size_bytes, "container_validation": container_validation,
            "file_identity": file_identity, "locator_verified_at_capture": True,
        },
    )
    source = {
        "source_id": source_id,
        "identity_sha256": identity_hash,
        "source_type": source_type,
        "display_name": path.name,
        "lifecycle": "ACTIVE",
        "origin": {"kind": "LOCAL", "component": "integra.local_media", "native_id": digest},
        "project_ids": [project_id],
        "current_revision_id": revision["revision_id"],
        "revisions": [revision],
        "memberships": [],
        "collection_membership_ids": [],
    }
    return _attach_source(registry, project_id, source, captured_at)


def register_youtube_video(
    registry: dict[str, Any], project_id: str, *, video_id: str, title: str,
    availability: str, captured_at: str,
) -> tuple[dict[str, Any], str]:
    """Index one video independently while reusing R8A's per-video identity."""

    _text(video_id, "YouTube video ID")
    _text(title, "YouTube title")
    _timestamp(captured_at)
    if availability not in {"AVAILABLE", "INACCESSIBLE"}:
        raise RegistryError("YouTube availability is unsupported")
    identity_hash = content_sha256({"provider": "youtube", "video_id": video_id})
    source_id = derive_imported_id("source", "youtube", video_id, identity_hash)
    provenance: dict[str, Any] = {
        "kind": "REMOTE_REFERENCE", "component": "youtube", "provider": "youtube",
        "native_id": video_id, "canonical_url": f"https://www.youtube.com/watch?v={video_id}",
        "title": title,
    }
    metadata_hash = content_sha256(
        {"title": title, "availability": availability, "provenance": provenance}
    )
    revision = _source_revision(
        source_id, metadata_hash, captured_at, availability, provenance
    )
    source = {
        "source_id": source_id,
        "identity_sha256": identity_hash,
        "source_type": "YOUTUBE_VIDEO",
        "display_name": title,
        "lifecycle": "ACTIVE" if availability == "AVAILABLE" else "UNAVAILABLE",
        "origin": {"kind": "REMOTE", "component": "youtube", "native_id": video_id},
        "project_ids": [project_id],
        "current_revision_id": revision["revision_id"],
        "revisions": [revision],
        "memberships": [],
        "collection_membership_ids": [],
    }
    return _attach_source(registry, project_id, source, captured_at)


def register_youtube_playlist(
    registry: dict[str, Any], project_id: str, discovery: dict[str, Any], *,
    captured_at: str,
) -> tuple[dict[str, Any], str, list[str]]:
    """Index an accepted R8A discovery and its shared per-video source records."""

    validate_discovery(discovery)
    _timestamp(captured_at)
    if _timestamp(captured_at) < _timestamp(discovery["fetched_at"]):
        raise RegistryError("playlist capture predates provider snapshot")
    collection_id = discovery["collection_id"]
    revision = _source_revision(
        collection_id, discovery["snapshot_sha256"], captured_at, "AVAILABLE",
        {
            "kind": "REMOTE_REFERENCE", "component": "youtube",
            "provider": "youtube", "native_id": discovery["playlist_native_id"],
            "snapshot_id": discovery["snapshot_id"],
        },
    )
    playlist_source = {
        "source_id": collection_id,
        "identity_sha256": content_sha256(
            {"provider": "youtube", "playlist_native_id": discovery["playlist_native_id"]}
        ),
        "source_type": "YOUTUBE_PLAYLIST",
        "display_name": discovery["playlist_native_id"],
        "lifecycle": "ACTIVE",
        "origin": {
            "kind": "REMOTE", "component": "youtube",
            "native_id": discovery["playlist_native_id"],
        },
        "project_ids": [project_id],
        "current_revision_id": revision["revision_id"],
        "revisions": [revision],
        "memberships": [],
        "collection_membership_ids": [],
    }
    result, playlist_id = _attach_source(registry, project_id, playlist_source, captured_at)
    video_ids: list[str] = []
    for item in discovery["items"]:
        result, video_source_id = register_youtube_video(
            result, project_id, video_id=item["video_id"], title=item["title"],
            availability=item["availability"], captured_at=captured_at,
        )
        if video_source_id != item["video_source_id"]:
            raise RegistryError("playlist video identity differs from R8A")
        result = _attach_playlist_membership(
            result, video_source_id, discovery, item, captured_at
        )
        video_ids.append(video_source_id)
    return result, playlist_id, video_ids


def register_document(
    registry: dict[str, Any], project_id: str, document: dict[str, Any], *,
    captured_at: str, image_role: str | None = None,
) -> tuple[dict[str, Any], str]:
    """Index one validated R8B record without reimplementing extraction or OCR."""

    validate_document_record(document)
    _timestamp(captured_at)
    document_source = document["source"]
    source_type = DOCUMENT_TYPES[document_source["format"]]
    if source_type == "IMAGE":
        if image_role is not None and image_role not in {"IMAGE", "SCAN"}:
            raise RegistryError("document image role must be IMAGE or SCAN")
        source_type = image_role or "SCAN"
    elif image_role is not None:
        raise RegistryError("document image role applies only to image sources")
    source_id = document_source["source_id"]
    identity_hash = content_sha256(
        {"component": "integra.document_source", "sha256": document_source["sha256"]}
    )
    revision = _source_revision(
        source_id, document_source["sha256"], captured_at, "AVAILABLE",
        {
            "kind": "PIPELINE_ARTIFACT", "component": "integra.document_pipeline",
            "document_id": document["document_id"],
            "document_record_sha256": document["record_sha256"],
            "source_revision_id": document_source["revision_id"],
            "media_type": document_source["media_type"],
            "source_display_name": document_source["display_name"],
        },
    )
    source = {
        "source_id": source_id,
        "identity_sha256": identity_hash,
        "source_type": source_type,
        "display_name": document_source["display_name"],
        "lifecycle": "ACTIVE",
        "origin": {
            "kind": "PIPELINE", "component": "integra.document_pipeline",
            "native_id": document_source["sha256"],
        },
        "project_ids": [project_id],
        "current_revision_id": revision["revision_id"],
        "revisions": [revision],
        "memberships": [],
        "collection_membership_ids": [],
    }
    return _attach_source(registry, project_id, source, captured_at)


def dumps_registry(registry: dict[str, Any]) -> bytes:
    validate_registry(registry)
    return canonical_json(registry) + b"\n"


def loads_registry(payload: bytes) -> dict[str, Any]:
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RegistryError("registry serialization is invalid") from error
    validate_registry(value)
    return value


def validate_registry(registry: dict[str, Any]) -> None:
    required = {
        "schema_version", "registry_id", "registry_key", "created_at", "updated_at",
        "revision", "projects", "sources", "record_sha256",
    }
    if not isinstance(registry, dict) or set(registry) != required:
        raise RegistryError("project/source registry differs from v1")
    if registry["schema_version"] != "1.0":
        raise RegistryError("registry schema version is unsupported")
    _text(registry["registry_key"], "registry key")
    _timestamp(registry["created_at"])
    _timestamp(registry["updated_at"])
    _integer(registry["revision"], "registry revision")
    identity_hash = content_sha256(
        {"component": "integra.project_source_registry", "registry_key": registry["registry_key"]}
    )
    if registry["registry_id"] != derive_imported_id(
        "artifact", "integra.project_source_registry", registry["registry_key"], identity_hash
    ):
        raise RegistryError("registry identity differs")
    if not isinstance(registry["projects"], list) or not isinstance(registry["sources"], list):
        raise RegistryError("registry collections must be lists")
    project_ids: set[str] = set()
    project_keys: set[str] = set()
    for project in registry["projects"]:
        _validate_project(project)
        if project["project_id"] in project_ids or project["project_key"] in project_keys:
            raise RegistryError("project identity is duplicated")
        project_ids.add(project["project_id"])
        project_keys.add(project["project_key"])
    source_ids: set[str] = set()
    fingerprints: dict[str, str] = {}
    for source in registry["sources"]:
        _validate_source(source)
        if source["source_id"] in source_ids:
            raise RegistryError("source identity is duplicated")
        previous = fingerprints.get(source["identity_sha256"])
        if previous is not None and previous != source["source_id"]:
            raise RegistryError("one source identity maps to multiple source IDs")
        source_ids.add(source["source_id"])
        fingerprints[source["identity_sha256"]] = source["source_id"]
        if not set(source["project_ids"]).issubset(project_ids):
            raise RegistryError("source references an unknown project")
    for project in registry["projects"]:
        if not set(project["source_ids"]).issubset(source_ids):
            raise RegistryError("project references an unknown source")
        for source_id in project["source_ids"]:
            source = next(item for item in registry["sources"] if item["source_id"] == source_id)
            if project["project_id"] not in source["project_ids"]:
                raise RegistryError("project/source relationship is not reciprocal")
        event_types = {
            event["details"]["source_id"]: event["details"]["source_type"]
            for event in project["history"]
            if event["event_type"] == "SOURCE_ATTACHED"
        }
        for source_id in project["source_ids"]:
            source = next(item for item in registry["sources"] if item["source_id"] == source_id)
            if event_types.get(source_id) != source["source_type"]:
                raise RegistryError("source attachment history type differs from source")
    for source in registry["sources"]:
        for project_id in source["project_ids"]:
            project = next(item for item in registry["projects"] if item["project_id"] == project_id)
            if source["source_id"] not in project["source_ids"]:
                raise RegistryError("source/project relationship is not reciprocal")
    sources_by_id = {source["source_id"]: source for source in registry["sources"]}
    memberships_by_collection: dict[str, list[str]] = {}
    for source in registry["sources"]:
        for membership in source["memberships"]:
            playlist_source = sources_by_id.get(membership["collection_id"])
            if playlist_source is None or playlist_source["source_type"] != "YOUTUBE_PLAYLIST":
                raise RegistryError("playlist membership references an unknown playlist")
            if membership["playlist_native_id"] != playlist_source["origin"]["native_id"]:
                raise RegistryError("playlist membership native identity differs")
            if not set(source["project_ids"]).intersection(playlist_source["project_ids"]):
                raise RegistryError("playlist membership has no shared project")
            snapshot_matches = any(
                revision["revision_sha256"] == membership["snapshot_sha256"]
                and revision["provenance"]["snapshot_id"] == membership["snapshot_id"]
                for revision in playlist_source["revisions"]
            )
            if not snapshot_matches:
                raise RegistryError("playlist membership snapshot provenance differs")
            memberships_by_collection.setdefault(membership["collection_id"], []).append(
                membership["membership_id"]
            )
    for source in registry["sources"]:
        expected_memberships = sorted(memberships_by_collection.get(source["source_id"], []))
        if source["collection_membership_ids"] != expected_memberships:
            raise RegistryError("playlist collection membership index differs")
    if registry["projects"] != sorted(registry["projects"], key=lambda item: item["project_id"]):
        raise RegistryError("projects are not in deterministic order")
    if registry["sources"] != sorted(registry["sources"], key=lambda item: item["source_id"]):
        raise RegistryError("sources are not in deterministic order")
    observed_times = [registry["created_at"]]
    observed_times.extend(item["updated_at"] for item in registry["projects"])
    observed_times.extend(
        revision["captured_at"]
        for source in registry["sources"]
        for revision in source["revisions"]
    )
    if _timestamp(registry["updated_at"]) != max(_timestamp(value) for value in observed_times):
        raise RegistryError("registry update time differs from its latest evidence")
    supplied = registry["record_sha256"]
    _digest(supplied, "registry record hash")
    identity = copy.deepcopy(registry)
    identity["record_sha256"] = ""
    if supplied != content_sha256(identity):
        raise RegistryError("registry record hash differs")


def _attach_source(
    registry: dict[str, Any], project_id: str, incoming: dict[str, Any], occurred_at: str,
) -> tuple[dict[str, Any], str]:
    validate_registry(registry)
    _validate_source(incoming)
    result = copy.deepcopy(registry)
    project = _project_by_id(result, project_id)
    existing = next(
        (item for item in result["sources"] if item["source_id"] == incoming["source_id"]),
        None,
    )
    changed = False
    if existing is None:
        conflicting = next(
            (item for item in result["sources"] if item["identity_sha256"] == incoming["identity_sha256"]),
            None,
        )
        if conflicting is not None:
            raise RegistryError("source fingerprint maps to a conflicting identity")
        result["sources"].append(copy.deepcopy(incoming))
        existing = result["sources"][-1]
        changed = True
    else:
        if (
            existing["identity_sha256"] != incoming["identity_sha256"]
            or existing["source_type"] != incoming["source_type"]
            or existing["origin"] != incoming["origin"]
        ):
            raise RegistryError("source identity conflict")
        incoming_revision = incoming["revisions"][0]
        observation = _revision_observation(incoming_revision)
        known_observations = {
            _revision_observation(item) for item in existing["revisions"]
        }
        if observation not in known_observations:
            if _timestamp(incoming_revision["captured_at"]) <= _timestamp(
                existing["revisions"][-1]["captured_at"]
            ):
                raise RegistryError("source revision time must advance")
            new_revision = _link_revision(
                incoming_revision, source_id=incoming["source_id"],
                ordinal=len(existing["revisions"]) + 1,
                previous_revision_id=existing["revisions"][-1]["revision_id"],
            )
            existing["revisions"].append(copy.deepcopy(new_revision))
            existing["current_revision_id"] = new_revision["revision_id"]
            existing["display_name"] = incoming["display_name"]
            existing["lifecycle"] = incoming["lifecycle"]
            changed = True
        if project_id not in existing["project_ids"]:
            existing["project_ids"].append(project_id)
            existing["project_ids"].sort()
            changed = True
    if incoming["source_id"] not in project["source_ids"]:
        project["source_ids"].append(incoming["source_id"])
        project["source_ids"].sort()
        _append_project_event(
            project, "SOURCE_ATTACHED", occurred_at,
            {"source_id": incoming["source_id"], "source_type": incoming["source_type"]},
        )
        project["revision"] = len(project["history"])
        project["updated_at"] = occurred_at
        changed = True
    if not changed:
        return registry, incoming["source_id"]
    result["sources"].sort(key=lambda item: item["source_id"])
    return _advance(result, occurred_at), incoming["source_id"]


def _attach_playlist_membership(
    registry: dict[str, Any], source_id: str, discovery: dict[str, Any],
    item: dict[str, Any], occurred_at: str,
) -> dict[str, Any]:
    validate_registry(registry)
    result = copy.deepcopy(registry)
    source = next(
        (candidate for candidate in result["sources"] if candidate["source_id"] == source_id),
        None,
    )
    if source is None or source["source_type"] != "YOUTUBE_VIDEO":
        raise RegistryError("playlist membership requires a registered YouTube video")
    body = {
        "video_source_id": source_id,
        "collection_id": discovery["collection_id"],
        "playlist_native_id": discovery["playlist_native_id"],
        "snapshot_id": discovery["snapshot_id"],
        "snapshot_sha256": discovery["snapshot_sha256"],
        "observed_at": occurred_at,
        "position": item["position"],
        "item_title": item["title"],
        "availability": item["availability"],
        "duration_seconds": item["duration_seconds"],
        "estimated_download_bytes": item["estimated_download_bytes"],
    }
    relationship_sha256 = content_sha256(body)
    native_id = ":".join(
        (source_id, discovery["collection_id"], discovery["snapshot_id"], str(item["position"]))
    )
    membership = {
        "membership_id": derive_imported_id(
            "artifact", "integra.youtube.membership", native_id, relationship_sha256
        ),
        **body,
        "relationship_sha256": relationship_sha256,
    }
    existing = next(
        (entry for entry in source["memberships"] if entry["membership_id"] == membership["membership_id"]),
        None,
    )
    if existing is not None:
        if existing != membership:
            raise RegistryError("playlist membership identity conflict")
        return registry
    source["memberships"].append(membership)
    source["memberships"].sort(key=lambda entry: entry["membership_id"])
    playlist_source = next(
        candidate for candidate in result["sources"]
        if candidate["source_id"] == discovery["collection_id"]
    )
    playlist_source["collection_membership_ids"].append(membership["membership_id"])
    playlist_source["collection_membership_ids"].sort()
    return _advance(result, occurred_at)


def _source_revision(
    source_id: str, revision_sha256: str, captured_at: str,
    availability: str, provenance: dict[str, Any],
) -> dict[str, Any]:
    _urn(source_id, "source ID")
    _digest(revision_sha256, "source revision hash")
    _timestamp(captured_at)
    if availability not in {"AVAILABLE", "INACCESSIBLE"}:
        raise RegistryError("source revision availability is unsupported")
    provenance_hash = content_sha256(provenance)
    identity = content_sha256(
        {
            "source_id": source_id, "ordinal": 1, "previous_revision_id": None,
            "revision_sha256": revision_sha256,
            "captured_at": captured_at, "availability": availability,
            "provenance_sha256": provenance_hash,
        }
    )
    return {
        "revision_id": derive_imported_id("revision", "integra.source_registry", source_id, identity),
        "ordinal": 1,
        "previous_revision_id": None,
        "captured_at": captured_at,
        "revision_sha256": revision_sha256,
        "availability": availability,
        "provenance_sha256": provenance_hash,
        "provenance": copy.deepcopy(provenance),
    }


def _revision_observation(revision: dict[str, Any]) -> str:
    return content_sha256(
        {
            "captured_at": revision["captured_at"],
            "revision_sha256": revision["revision_sha256"],
            "availability": revision["availability"],
            "provenance_sha256": revision["provenance_sha256"],
            "provenance": revision["provenance"],
        }
    )


def _link_revision(
    revision: dict[str, Any], *, source_id: str, ordinal: int,
    previous_revision_id: str,
) -> dict[str, Any]:
    linked = copy.deepcopy(revision)
    linked["ordinal"] = ordinal
    linked["previous_revision_id"] = previous_revision_id
    linked.pop("revision_id")
    identity = content_sha256(
        {
            "source_id": source_id,
            "ordinal": ordinal,
            "previous_revision_id": previous_revision_id,
            "revision_sha256": linked["revision_sha256"],
            "captured_at": linked["captured_at"],
            "availability": linked["availability"],
            "provenance_sha256": linked["provenance_sha256"],
        }
    )
    linked["revision_id"] = derive_imported_id(
        "revision", "integra.source_registry", source_id, identity
    )
    return linked


def _validate_playlist_membership(
    membership: dict[str, Any], source_id: str
) -> None:
    body_fields = {
        "video_source_id", "collection_id", "playlist_native_id", "snapshot_id",
        "snapshot_sha256", "observed_at", "position", "item_title",
        "availability", "duration_seconds", "estimated_download_bytes",
    }
    if not isinstance(membership, dict) or set(membership) != (
        body_fields | {"membership_id", "relationship_sha256"}
    ):
        raise RegistryError("playlist membership differs from v1")
    if membership["video_source_id"] != source_id:
        raise RegistryError("playlist membership video identity differs")
    _urn(membership["membership_id"], "playlist membership ID")
    _urn(membership["collection_id"], "playlist collection ID")
    _urn(membership["snapshot_id"], "playlist snapshot ID")
    _digest(membership["snapshot_sha256"], "playlist snapshot hash")
    _timestamp(membership["observed_at"])
    _text(membership["playlist_native_id"], "playlist native ID")
    _text(membership["item_title"], "playlist item title")
    _integer(membership["position"], "playlist item position")
    _integer(membership["duration_seconds"], "playlist item duration")
    _integer(membership["estimated_download_bytes"], "playlist estimated bytes")
    if membership["availability"] not in {"AVAILABLE", "INACCESSIBLE"}:
        raise RegistryError("playlist membership availability differs")
    body = {field: membership[field] for field in body_fields}
    relationship_sha256 = content_sha256(body)
    if membership["relationship_sha256"] != relationship_sha256:
        raise RegistryError("playlist membership hash differs")
    native_id = ":".join(
        (
            source_id, membership["collection_id"], membership["snapshot_id"],
            str(membership["position"]),
        )
    )
    if membership["membership_id"] != derive_imported_id(
        "artifact", "integra.youtube.membership", native_id, relationship_sha256
    ):
        raise RegistryError("playlist membership stable identity differs")


def _append_project_event(
    project: dict[str, Any], event_type: str, occurred_at: str, details: dict[str, Any]
) -> None:
    ordinal = len(project["history"]) + 1
    identity = content_sha256(
        {
            "project_id": project["project_id"], "ordinal": ordinal,
            "event_type": event_type, "occurred_at": occurred_at, "details": details,
        }
    )
    project["history"].append(
        {
            "event_id": derive_imported_id(
                "artifact", "integra.project_history", f"{project['project_id']}:{ordinal}", identity
            ),
            "ordinal": ordinal,
            "event_type": event_type,
            "occurred_at": occurred_at,
            "details": copy.deepcopy(details),
        }
    )


def _validate_project(project: dict[str, Any]) -> None:
    required = {
        "project_id", "project_key", "identity_sha256", "kind", "title", "lifecycle",
        "created_at", "updated_at", "revision", "source_ids", "history",
    }
    if not isinstance(project, dict) or set(project) != required:
        raise RegistryError("project record differs from v1")
    _text(project["project_key"], "project key")
    _text(project["title"], "project title")
    _digest(project["identity_sha256"], "project identity hash")
    _urn(project["project_id"], "project ID")
    if project["kind"] not in PROJECT_KINDS or project["lifecycle"] not in PROJECT_LIFECYCLES:
        raise RegistryError("project kind or lifecycle differs")
    expected_identity = content_sha256(
        {"component": "integra.project_registry", "project_key": project["project_key"], "kind": project["kind"]}
    )
    if project["identity_sha256"] != expected_identity or project["project_id"] != derive_imported_id(
        "project", "integra.project_registry", project["project_key"], expected_identity
    ):
        raise RegistryError("project stable identity differs")
    created = _timestamp(project["created_at"])
    updated = _timestamp(project["updated_at"])
    if updated < created:
        raise RegistryError("project update predates creation")
    _positive_integer(project["revision"], "project revision")
    _unique_urn_list(project["source_ids"], "project sources")
    if not isinstance(project["history"], list) or not project["history"]:
        raise RegistryError("project history is empty")
    reconstructed_title: str | None = None
    reconstructed_lifecycle = "ACTIVE"
    attached_sources: list[str] = []
    previous_time: datetime | None = None
    for index, event in enumerate(project["history"], start=1):
        if not isinstance(event, dict) or set(event) != {
            "event_id", "ordinal", "event_type", "occurred_at", "details"
        }:
            raise RegistryError("project history event differs from v1")
        _urn(event["event_id"], "project event ID")
        if event["ordinal"] != index or not isinstance(event["details"], dict):
            raise RegistryError("project history order or details differ")
        event_time = _timestamp(event["occurred_at"])
        if previous_time is not None and event_time < previous_time:
            raise RegistryError("project history time moves backwards")
        previous_time = event_time
        event_type = event["event_type"]
        details = event["details"]
        if index == 1:
            if (
                event_type != "CREATED"
                or set(details) != {"kind", "title"}
                or details["kind"] != project["kind"]
            ):
                raise RegistryError("project history must begin with its creation")
            _text(details.get("title"), "created project title")
            reconstructed_title = details["title"]
            if event["occurred_at"] != project["created_at"]:
                raise RegistryError("project creation timestamp differs from history")
        elif event_type == "RENAMED":
            if set(details) != {"from", "to"} or details["from"] != reconstructed_title:
                raise RegistryError("project rename history is inconsistent")
            _text(details["to"], "renamed project title")
            reconstructed_title = details["to"]
        elif event_type == "LIFECYCLE_CHANGED":
            if (
                set(details) != {"from", "to"}
                or details["from"] != reconstructed_lifecycle
                or details["to"] not in PROJECT_LIFECYCLES
            ):
                raise RegistryError("project lifecycle history is inconsistent")
            reconstructed_lifecycle = details["to"]
        elif event_type == "SOURCE_ATTACHED":
            if set(details) != {"source_id", "source_type"} or details["source_type"] not in SOURCE_TYPES:
                raise RegistryError("project source attachment history is invalid")
            _urn(details["source_id"], "attached source ID")
            if details["source_id"] in attached_sources:
                raise RegistryError("project source attachment is duplicated")
            attached_sources.append(details["source_id"])
        else:
            raise RegistryError("project history event type is unsupported")
        identity = content_sha256(
            {
                "project_id": project["project_id"], "ordinal": index,
                "event_type": event["event_type"], "occurred_at": event["occurred_at"],
                "details": event["details"],
            }
        )
        if event["event_id"] != derive_imported_id(
            "artifact", "integra.project_history", f"{project['project_id']}:{index}", identity
        ):
            raise RegistryError("project history identity differs")
    if (
        reconstructed_title != project["title"]
        or reconstructed_lifecycle != project["lifecycle"]
        or sorted(attached_sources) != project["source_ids"]
        or project["revision"] != len(project["history"])
        or project["updated_at"] != project["history"][-1]["occurred_at"]
    ):
        raise RegistryError("project current state differs from its history")


def _validate_source(source: dict[str, Any]) -> None:
    required = {
        "source_id", "identity_sha256", "source_type", "display_name", "lifecycle",
        "origin", "project_ids", "current_revision_id", "revisions", "memberships",
        "collection_membership_ids",
    }
    if not isinstance(source, dict) or set(source) != required:
        raise RegistryError("source record differs from v1")
    _urn(source["source_id"], "source ID")
    _digest(source["identity_sha256"], "source identity hash")
    _text(source["display_name"], "source display name")
    if source["source_type"] not in SOURCE_TYPES or source["lifecycle"] not in SOURCE_LIFECYCLES:
        raise RegistryError("source type or lifecycle differs")
    origin = source["origin"]
    if not isinstance(origin, dict) or set(origin) != {"kind", "component", "native_id"}:
        raise RegistryError("source origin differs from v1")
    if origin["kind"] not in {"LOCAL", "REMOTE", "PIPELINE"}:
        raise RegistryError("source origin kind differs")
    _text(origin["component"], "source origin component")
    _text(origin["native_id"], "source native ID")
    if source["source_type"] in {"LOCAL_VIDEO", "LOCAL_AUDIO"}:
        if origin["kind"] != "LOCAL" or origin["component"] != "integra.local_media":
            raise RegistryError("local source origin differs")
        _digest(origin["native_id"], "local source native hash")
        expected_identity = content_sha256(
            {"component": "integra.local_media", "content_sha256": origin["native_id"]}
        )
        expected_id = derive_imported_id(
            "source", "integra.local_media", origin["native_id"], expected_identity
        )
    elif source["source_type"] == "YOUTUBE_VIDEO":
        if origin["kind"] != "REMOTE" or origin["component"] != "youtube":
            raise RegistryError("YouTube source origin differs")
        expected_identity = content_sha256(
            {"provider": "youtube", "video_id": origin["native_id"]}
        )
        expected_id = derive_imported_id(
            "source", "youtube", origin["native_id"], expected_identity
        )
    elif source["source_type"] == "YOUTUBE_PLAYLIST":
        if origin["kind"] != "REMOTE" or origin["component"] != "youtube":
            raise RegistryError("YouTube playlist origin differs")
        expected_identity = content_sha256(
            {"provider": "youtube", "playlist_native_id": origin["native_id"]}
        )
        expected_id = derive_imported_id(
            "source", "youtube", origin["native_id"], expected_identity
        )
    else:
        if origin["kind"] != "PIPELINE" or origin["component"] != "integra.document_pipeline":
            raise RegistryError("document source origin differs")
        _digest(origin["native_id"], "document source native hash")
        expected_identity = content_sha256(
            {"component": "integra.document_source", "sha256": origin["native_id"]}
        )
        expected_id = derive_imported_id(
            "source", "integra.document_source", origin["native_id"], expected_identity
        )
    if source["identity_sha256"] != expected_identity or source["source_id"] != expected_id:
        raise RegistryError("source stable identity differs")
    _unique_urn_list(source["project_ids"], "source projects", non_empty=True)
    if not isinstance(source["revisions"], list) or not source["revisions"]:
        raise RegistryError("source revisions are empty")
    revision_ids: set[str] = set()
    for ordinal, revision in enumerate(source["revisions"], start=1):
        if not isinstance(revision, dict) or set(revision) != {
            "revision_id", "ordinal", "previous_revision_id", "captured_at",
            "revision_sha256", "availability",
            "provenance_sha256", "provenance",
        }:
            raise RegistryError("source revision differs from v1")
        _urn(revision["revision_id"], "source revision ID")
        _timestamp(revision["captured_at"])
        _digest(revision["revision_sha256"], "source revision hash")
        _digest(revision["provenance_sha256"], "source provenance hash")
        if revision["availability"] not in {"AVAILABLE", "INACCESSIBLE"}:
            raise RegistryError("source availability differs")
        if not isinstance(revision["provenance"], dict) or content_sha256(revision["provenance"]) != revision["provenance_sha256"]:
            raise RegistryError("source provenance differs")
        identity = content_sha256(
            {
                "source_id": source["source_id"],
                "ordinal": revision["ordinal"],
                "previous_revision_id": revision["previous_revision_id"],
                "revision_sha256": revision["revision_sha256"],
                "captured_at": revision["captured_at"],
                "availability": revision["availability"],
                "provenance_sha256": revision["provenance_sha256"],
            }
        )
        if revision["revision_id"] != derive_imported_id(
            "revision", "integra.source_registry", source["source_id"], identity
        ):
            raise RegistryError("source revision identity differs")
        expected_previous = (
            None if ordinal == 1 else source["revisions"][ordinal - 2]["revision_id"]
        )
        if (
            revision["ordinal"] != ordinal
            or revision["previous_revision_id"] != expected_previous
        ):
            raise RegistryError("source revision lineage is broken")
        if revision["revision_id"] in revision_ids:
            raise RegistryError("source revision is duplicated")
        revision_ids.add(revision["revision_id"])
    if any(
        _timestamp(current_revision["captured_at"])
        <= _timestamp(previous_revision["captured_at"])
        for previous_revision, current_revision in zip(
            source["revisions"], source["revisions"][1:]
        )
    ):
        raise RegistryError("source revision time must advance")
    if source["current_revision_id"] != source["revisions"][-1]["revision_id"]:
        raise RegistryError("current source revision is not the latest revision")
    current = source["revisions"][-1]
    expected_lifecycle = "ACTIVE" if current["availability"] == "AVAILABLE" else "UNAVAILABLE"
    if source["lifecycle"] != "ARCHIVED" and source["lifecycle"] != expected_lifecycle:
        raise RegistryError("source lifecycle differs from current availability")
    if source["source_type"] in {"LOCAL_VIDEO", "LOCAL_AUDIO", "PDF", "PPTX", "DOCX", "TXT", "MARKDOWN", "IMAGE", "SCAN"}:
        if any(item["revision_sha256"] != origin["native_id"] for item in source["revisions"]):
            raise RegistryError("content-addressed source revision differs from origin")
    if not isinstance(source["memberships"], list):
        raise RegistryError("source memberships must be a list")
    if source["source_type"] != "YOUTUBE_VIDEO" and source["memberships"]:
        raise RegistryError("only YouTube videos can have playlist memberships")
    membership_ids: set[str] = set()
    for membership in source["memberships"]:
        _validate_playlist_membership(membership, source["source_id"])
        if membership["membership_id"] in membership_ids:
            raise RegistryError("playlist membership is duplicated")
        membership_ids.add(membership["membership_id"])
    if source["memberships"] != sorted(
        source["memberships"], key=lambda entry: entry["membership_id"]
    ):
        raise RegistryError("playlist memberships are not in deterministic order")
    _unique_urn_list(
        source["collection_membership_ids"], "collection membership IDs"
    )
    if source["source_type"] != "YOUTUBE_PLAYLIST" and source["collection_membership_ids"]:
        raise RegistryError("only YouTube playlists can index collection memberships")
    provenance = current["provenance"]
    if source["source_type"] in {"LOCAL_VIDEO", "LOCAL_AUDIO"}:
        for revision in source["revisions"]:
            revision_provenance = revision["provenance"]
            if set(revision_provenance) != {
                "kind", "component", "locator", "media_type", "size_bytes",
                "container_validation", "file_identity", "locator_verified_at_capture",
            }:
                raise RegistryError("local source provenance differs from v1")
            if revision_provenance["kind"] != "LOCAL_FILE" or revision_provenance["component"] != "integra.local_media":
                raise RegistryError("local source provenance origin differs")
            locator = Path(revision_provenance["locator"])
            if not locator.is_absolute():
                raise RegistryError("local source locator must be absolute")
            _integer(revision_provenance["size_bytes"], "local source size")
            _text(revision_provenance["media_type"], "local source media type")
            file_identity = revision_provenance["file_identity"]
            if (
                not isinstance(file_identity, dict)
                or set(file_identity) != {"device", "inode"}
            ):
                raise RegistryError("local source file identity differs")
            _integer(file_identity["device"], "local source device")
            _integer(file_identity["inode"], "local source inode")
            if revision_provenance["locator_verified_at_capture"] is not True:
                raise RegistryError("local source locator was not verified at capture")
            if revision_provenance["container_validation"] not in {
                "ISO_BMFF_FTYP", "MATROSKA_EBML", "RIFF_WAVE", "MPEG_AUDIO",
                "FLAC", "AAC_ADTS_OR_ADIF",
            }:
                raise RegistryError("local source container validation differs")
            suffix = locator.suffix.lower()
            expected_media = LOCAL_SUFFIXES.get(suffix)
            expected_validation = {
                ".mp4": "ISO_BMFF_FTYP", ".mov": "ISO_BMFF_FTYP",
                ".m4v": "ISO_BMFF_FTYP", ".m4a": "ISO_BMFF_FTYP",
                ".mkv": "MATROSKA_EBML", ".wav": "RIFF_WAVE",
                ".mp3": "MPEG_AUDIO", ".flac": "FLAC",
                ".aac": "AAC_ADTS_OR_ADIF",
            }.get(suffix)
            if (
                expected_media is None
                or expected_media != (source["source_type"], revision_provenance["media_type"])
                or revision_provenance["container_validation"] != expected_validation
            ):
                raise RegistryError("local source extension, type and provenance differ")
        if Path(provenance["locator"]).name != source["display_name"]:
            raise RegistryError("local source display name differs from current locator")
    elif source["source_type"] == "YOUTUBE_VIDEO":
        required = {"kind", "component", "provider", "native_id", "canonical_url", "title"}
        for revision in source["revisions"]:
            revision_provenance = revision["provenance"]
            if set(revision_provenance) != required:
                raise RegistryError("YouTube video provenance differs from v1")
            if (
                revision_provenance["kind"] != "REMOTE_REFERENCE"
                or revision_provenance["component"] != "youtube"
                or revision_provenance["provider"] != "youtube"
                or revision_provenance["native_id"] != origin["native_id"]
                or revision_provenance["canonical_url"] != f"https://www.youtube.com/watch?v={origin['native_id']}"
            ):
                raise RegistryError("YouTube video provenance is inconsistent")
            _text(revision_provenance["title"], "YouTube revision title")
            expected_revision = content_sha256(
                {
                    "title": revision_provenance["title"],
                    "availability": revision["availability"],
                    "provenance": revision_provenance,
                }
            )
            if revision["revision_sha256"] != expected_revision:
                raise RegistryError("YouTube video revision metadata hash differs")
        if provenance["title"] != source["display_name"]:
            raise RegistryError("YouTube display name differs from current provenance")
    elif source["source_type"] == "YOUTUBE_PLAYLIST":
        for revision in source["revisions"]:
            revision_provenance = revision["provenance"]
            if set(revision_provenance) != {"kind", "component", "provider", "native_id", "snapshot_id"}:
                raise RegistryError("YouTube playlist provenance differs from v1")
            if (
                revision_provenance["kind"] != "REMOTE_REFERENCE"
                or revision_provenance["component"] != "youtube"
                or revision_provenance["provider"] != "youtube"
                or revision_provenance["native_id"] != origin["native_id"]
            ):
                raise RegistryError("YouTube playlist provenance is inconsistent")
            _urn(revision_provenance["snapshot_id"], "playlist snapshot ID")
        if source["display_name"] != origin["native_id"]:
            raise RegistryError("YouTube playlist display name differs")
    else:
        required = {
            "kind", "component", "document_id", "document_record_sha256",
            "source_revision_id", "media_type", "source_display_name",
        }
        for revision in source["revisions"]:
            revision_provenance = revision["provenance"]
            if set(revision_provenance) != required:
                raise RegistryError("document source provenance differs from v1")
            if (
                revision_provenance["kind"] != "PIPELINE_ARTIFACT"
                or revision_provenance["component"] != "integra.document_pipeline"
            ):
                raise RegistryError("document source provenance is inconsistent")
            _text(revision_provenance["source_display_name"], "document source display name")
            _urn(revision_provenance["document_id"], "document artifact ID")
            _urn(revision_provenance["source_revision_id"], "document source revision ID")
            _digest(revision_provenance["document_record_sha256"], "document record hash")
            _text(revision_provenance["media_type"], "document media type")
        if provenance["source_display_name"] != source["display_name"]:
            raise RegistryError("document display name differs from current provenance")


def _project_by_id(
    registry: dict[str, Any], project_id: str, *, required: bool = True
) -> dict[str, Any] | None:
    project = next((item for item in registry["projects"] if item["project_id"] == project_id), None)
    if project is None and required:
        raise RegistryError("project is not registered")
    return project


def _advance(registry: dict[str, Any], occurred_at: str) -> dict[str, Any]:
    if _timestamp(occurred_at) < _timestamp(registry["updated_at"]):
        raise RegistryError("registry time cannot move backwards")
    registry["updated_at"] = occurred_at
    registry["revision"] += 1
    return _seal(registry)


def _seal(value: dict[str, Any]) -> dict[str, Any]:
    value["record_sha256"] = ""
    value["record_sha256"] = content_sha256(value)
    validate_registry(value)
    return value


def _timestamp(value: Any, label: str = "timestamp") -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise RegistryError(f"{label} must be a UTC RFC3339 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise RegistryError(f"{label} is invalid") from error
    if parsed.tzinfo != timezone.utc:
        raise RegistryError(f"{label} must use UTC")
    return parsed


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RegistryError(f"{label} must be non-empty text")
    return value


def _digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise RegistryError(f"{label} must be a lowercase SHA-256")
    return value


def _urn(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.startswith("urn:integra:"):
        raise RegistryError(f"{label} must be an Integra URN")
    return value


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise RegistryError(f"{label} must be a non-negative integer")
    return value


def _positive_integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise RegistryError(f"{label} must be a positive integer")
    return value


def _unique_urn_list(value: Any, label: str, *, non_empty: bool = False) -> list[str]:
    if not isinstance(value, list) or (non_empty and not value) or value != sorted(value) or len(value) != len(set(value)):
        raise RegistryError(f"{label} must be a sorted unique list")
    for item in value:
        _urn(item, label)
    return value


def _hash_regular_file(path: Path) -> tuple[str, int, bytes, str, dict[str, int]]:
    requested = Path(os.path.abspath(path))
    if requested.name in {"", ".", ".."}:
        raise RegistryError("local media path is invalid")
    try:
        requested_entry = os.stat(requested, follow_symlinks=False)
        if not stat.S_ISREG(requested_entry.st_mode):
            raise RegistryError(
                "local media must be an available regular non-symlink file"
            )
        absolute = requested.resolve(strict=True)
    except OSError as error:
        raise RegistryError(
            "local media must be an available regular non-symlink file"
        ) from error
    directory_flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        directory_flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        directory_flags |= os.O_NOFOLLOW
    file_flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        file_flags |= os.O_NOFOLLOW
    directories: list[int] = []
    directory_entries: list[tuple[int, str, os.stat_result]] = []
    try:
        current = os.open(absolute.anchor, directory_flags)
        directories.append(current)
        for part in absolute.parts[1:-1]:
            before = os.stat(part, dir_fd=current, follow_symlinks=False)
            if not stat.S_ISDIR(before.st_mode):
                raise RegistryError("local media path contains a non-directory or symlink")
            child = os.open(part, directory_flags, dir_fd=current)
            opened = os.fstat(child)
            if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
                os.close(child)
                raise RegistryError("local media directory changed during open")
            directory_entries.append((current, part, opened))
            directories.append(child)
            current = child
        descriptor = os.open(absolute.name, file_flags, dir_fd=current)
    except (OSError, RegistryError) as error:
        for directory in reversed(directories):
            os.close(directory)
        if isinstance(error, RegistryError):
            raise
        raise RegistryError(
            "local media must be an available regular non-symlink file"
        ) from error
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise RegistryError("local media must be an available regular non-symlink file")
        if (before.st_dev, before.st_ino) != (
            requested_entry.st_dev, requested_entry.st_ino
        ):
            raise RegistryError("local media changed while resolving its locator")
        digest = hashlib.sha256()
        size = 0
        prefix = b""
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            if len(prefix) < 32:
                prefix = (prefix + chunk)[:32]
            digest.update(chunk)
            size += len(chunk)
        after = os.fstat(descriptor)
        if (
            before.st_dev != after.st_dev
            or before.st_ino != after.st_ino
            or before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
            or size != after.st_size
        ):
            raise RegistryError("local media changed during fingerprinting")
        for parent, name, opened in directory_entries:
            observed = os.stat(name, dir_fd=parent, follow_symlinks=False)
            if (
                not stat.S_ISDIR(observed.st_mode)
                or (observed.st_dev, observed.st_ino) != (opened.st_dev, opened.st_ino)
            ):
                raise RegistryError("local media directory changed during fingerprinting")
        observed_file = os.stat(
            absolute.name, dir_fd=directories[-1], follow_symlinks=False
        )
        if (
            not stat.S_ISREG(observed_file.st_mode)
            or (observed_file.st_dev, observed_file.st_ino)
            != (after.st_dev, after.st_ino)
        ):
            raise RegistryError("local media locator changed during fingerprinting")
        return (
            digest.hexdigest(), size, prefix, str(absolute),
            {"device": after.st_dev, "inode": after.st_ino},
        )
    except OSError as error:
        raise RegistryError("local media path changed during fingerprinting") from error
    finally:
        os.close(descriptor)
        for directory in reversed(directories):
            os.close(directory)


def _validate_media_signature(suffix: str, prefix: bytes) -> str:
    if suffix in {".mp4", ".mov", ".m4v", ".m4a"}:
        if len(prefix) < 12 or prefix[4:8] != b"ftyp":
            raise RegistryError("local ISO BMFF media signature differs from its extension")
        return "ISO_BMFF_FTYP"
    if suffix == ".mkv":
        if not prefix.startswith(b"\x1a\x45\xdf\xa3"):
            raise RegistryError("local Matroska signature differs from its extension")
        return "MATROSKA_EBML"
    if suffix == ".wav":
        if len(prefix) < 12 or prefix[:4] != b"RIFF" or prefix[8:12] != b"WAVE":
            raise RegistryError("local WAVE signature differs from its extension")
        return "RIFF_WAVE"
    if suffix == ".flac":
        if not prefix.startswith(b"fLaC"):
            raise RegistryError("local FLAC signature differs from its extension")
        return "FLAC"
    if suffix == ".mp3":
        if not (
            prefix.startswith(b"ID3")
            or (len(prefix) >= 2 and prefix[0] == 0xFF and prefix[1] & 0xE0 == 0xE0)
        ):
            raise RegistryError("local MP3 signature differs from its extension")
        return "MPEG_AUDIO"
    if suffix == ".aac":
        if not (
            prefix.startswith(b"ADIF")
            or (len(prefix) >= 2 and prefix[0] == 0xFF and prefix[1] & 0xF6 == 0xF0)
        ):
            raise RegistryError("local AAC signature differs from its extension")
        return "AAC_ADTS_OR_ADIF"
    raise RegistryError("local media type is unsupported")
