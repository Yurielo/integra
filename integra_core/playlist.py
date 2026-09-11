"""Deterministic, offline-safe YouTube playlist planning and resume contracts."""

from __future__ import annotations

import copy
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path, PurePosixPath
import stat
from typing import Any, Callable

from .identity import derive_imported_id
from .protocol import content_sha256


class PlaylistError(RuntimeError):
    """Raised when playlist evidence or continuation authority is inconsistent."""


AVAILABILITY = {"AVAILABLE", "INACCESSIBLE"}


def discover_playlist(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Normalize one already-fetched official-adapter snapshot; performs no network I/O."""

    _validate_snapshot_input(snapshot)
    identity_revision = content_sha256({
        "provider": "youtube",
        "playlist_native_id": snapshot["playlist_native_id"],
    })
    collection_id = derive_imported_id(
        "source", "youtube", snapshot["playlist_native_id"], identity_revision
    )
    snapshot_sha256 = content_sha256(snapshot)
    items = []
    for item in snapshot["items"]:
        video_revision = content_sha256({
            "provider": "youtube", "video_id": item["video_id"]
        })
        items.append({
            **copy.deepcopy(item),
            "video_source_id": derive_imported_id(
                "source", "youtube", item["video_id"], video_revision
            ),
        })
    discovery = {
        "schema_version": "1.0",
        "provider": "youtube",
        "collection_id": collection_id,
        "playlist_native_id": snapshot["playlist_native_id"],
        "snapshot_id": derive_imported_id(
            "artifact", "youtube.playlist", snapshot["playlist_native_id"], snapshot_sha256
        ),
        "snapshot_sha256": snapshot_sha256,
        "fetched_at": snapshot["fetched_at"],
        "network_access_performed": False,
        "items": items,
    }
    validate_discovery(discovery)
    return discovery


def validate_discovery(discovery: dict[str, Any]) -> None:
    required = {
        "schema_version", "provider", "collection_id", "playlist_native_id",
        "snapshot_id", "snapshot_sha256", "fetched_at",
        "network_access_performed", "items",
    }
    if not isinstance(discovery, dict) or set(discovery) != required:
        raise PlaylistError("playlist discovery differs from v1")
    if discovery["schema_version"] != "1.0" or discovery["provider"] != "youtube":
        raise PlaylistError("playlist discovery provider is unsupported")
    if discovery["network_access_performed"] is not False:
        raise PlaylistError("offline discovery cannot claim network access")
    raw = {
        "schema_version": "1.0",
        "provider": "youtube",
        "playlist_native_id": discovery["playlist_native_id"],
        "fetched_at": discovery["fetched_at"],
        "items": [
            {key: item[key] for key in (
                "video_id", "position", "title", "availability", "duration_seconds",
                "estimated_download_bytes",
            )}
            for item in discovery["items"]
        ],
    }
    _validate_snapshot_input(raw)
    snapshot_sha256 = content_sha256(raw)
    if snapshot_sha256 != discovery["snapshot_sha256"]:
        raise PlaylistError("playlist snapshot hash differs")
    identity_revision = content_sha256({
        "provider": "youtube",
        "playlist_native_id": discovery["playlist_native_id"],
    })
    if discovery["collection_id"] != derive_imported_id(
        "source", "youtube", discovery["playlist_native_id"], identity_revision
    ):
        raise PlaylistError("playlist collection identity differs")
    if discovery["snapshot_id"] != derive_imported_id(
        "artifact", "youtube.playlist", discovery["playlist_native_id"], snapshot_sha256
    ):
        raise PlaylistError("playlist snapshot identity differs")
    for item in discovery["items"]:
        if set(item) != {
            "video_id", "position", "title", "availability", "duration_seconds",
            "estimated_download_bytes", "video_source_id",
        }:
            raise PlaylistError("playlist discovered item differs from v1")
        revision = content_sha256({
            "provider": "youtube", "video_id": item["video_id"]
        })
        if item["video_source_id"] != derive_imported_id(
            "source", "youtube", item["video_id"], revision
        ):
            raise PlaylistError("playlist video identity differs")


def build_playlist_plan(
    discovery: dict[str, Any], selected_video_ids: list[str] | None = None
) -> dict[str, Any]:
    validate_discovery(discovery)
    available_ids = [item["video_id"] for item in discovery["items"]]
    selected = available_ids if selected_video_ids is None else selected_video_ids
    if (
        not isinstance(selected, list)
        or not selected
        or len(selected) != len(set(selected))
        or not all(isinstance(item, str) and item in available_ids for item in selected)
    ):
        raise PlaylistError("playlist selection is invalid")
    by_id = {item["video_id"]: item for item in discovery["items"]}
    selected_items = [copy.deepcopy(by_id[video_id]) for video_id in selected]
    execution = {
        "collection_kind": "PLAYLIST",
        "sequential": True,
        "max_parallel_items": 1,
        "completed_item_policy": "SKIP_VERIFIED",
        "inaccessible_item_policy": "RECORD_AND_CONTINUE",
    }
    estimates = _storage_estimate(selected_items)
    identity = {
        "collection_id": discovery["collection_id"],
        "snapshot_id": discovery["snapshot_id"],
        "snapshot_sha256": discovery["snapshot_sha256"],
        "selected_video_ids": list(selected),
        "items": selected_items,
        "execution": execution,
        "storage_estimate": estimates,
    }
    plan_sha256 = content_sha256(identity)
    plan = {
        "schema_version": "1.0",
        "plan_id": derive_imported_id(
            "operation", "integra.youtube.playlist", discovery["collection_id"], plan_sha256
        ),
        "job_id": derive_imported_id(
            "job", "integra.youtube.playlist", discovery["collection_id"], plan_sha256
        ),
        "collection_id": discovery["collection_id"],
        "snapshot_id": discovery["snapshot_id"],
        "snapshot_sha256": discovery["snapshot_sha256"],
        "plan_sha256": plan_sha256,
        "selected_video_ids": list(selected),
        "items": selected_items,
        "execution": execution,
        "storage_estimate": estimates,
    }
    validate_plan(plan)
    return plan


def validate_plan(plan: dict[str, Any]) -> None:
    required = {
        "schema_version", "plan_id", "job_id", "collection_id", "snapshot_id",
        "snapshot_sha256", "plan_sha256", "selected_video_ids", "items",
        "execution", "storage_estimate",
    }
    if not isinstance(plan, dict) or set(plan) != required or plan["schema_version"] != "1.0":
        raise PlaylistError("playlist plan differs from v1")
    if not all(
        isinstance(plan[key], str) and plan[key]
        for key in ("plan_id", "job_id", "collection_id", "snapshot_id")
    ) or not _is_sha256(plan["snapshot_sha256"]):
        raise PlaylistError("playlist plan identity is invalid")
    selected = plan["selected_video_ids"]
    items = plan["items"]
    if (
        not isinstance(selected, list) or not selected
        or len(selected) != len(set(selected))
        or not isinstance(items, list)
        or [item.get("video_id") for item in items] != selected
    ):
        raise PlaylistError("playlist plan selection differs from items")
    for item in items:
        _validate_planned_item(item)
    if plan["execution"] != {
        "collection_kind": "PLAYLIST", "sequential": True,
        "max_parallel_items": 1, "completed_item_policy": "SKIP_VERIFIED",
        "inaccessible_item_policy": "RECORD_AND_CONTINUE",
    }:
        raise PlaylistError("playlist execution policy differs from v1")
    if plan["storage_estimate"] != _storage_estimate(items):
        raise PlaylistError("playlist storage estimate differs")
    identity = {
        "collection_id": plan["collection_id"],
        "snapshot_id": plan["snapshot_id"],
        "snapshot_sha256": plan["snapshot_sha256"],
        "selected_video_ids": selected,
        "items": items,
        "execution": plan["execution"],
        "storage_estimate": plan["storage_estimate"],
    }
    if content_sha256(identity) != plan["plan_sha256"]:
        raise PlaylistError("playlist plan hash differs")
    if plan["plan_id"] != derive_imported_id(
        "operation", "integra.youtube.playlist", plan["collection_id"], plan["plan_sha256"]
    ) or plan["job_id"] != derive_imported_id(
        "job", "integra.youtube.playlist", plan["collection_id"], plan["plan_sha256"]
    ):
        raise PlaylistError("playlist plan identifiers differ")


def process_playlist(
    plan: dict[str, Any],
    processor: Callable[[dict[str, Any]], dict[str, Any]],
    checkpoint: dict[str, Any] | None = None,
    *,
    artifact_root: Path,
    checkpoint_writer: Callable[[dict[str, Any]], None],
    max_new_items: int | None = None,
) -> dict[str, Any]:
    """Process sequentially, verify artifacts and persist after every handled item."""

    validate_plan(plan)
    current = _empty_checkpoint(plan) if checkpoint is None else copy.deepcopy(checkpoint)
    validate_checkpoint(plan, current, artifact_root)
    if not callable(checkpoint_writer):
        raise PlaylistError("playlist checkpoint writer is invalid")
    if current["status"] == "COMPLETE":
        return current
    if max_new_items is not None and (
        not isinstance(max_new_items, int)
        or isinstance(max_new_items, bool)
        or max_new_items < 0
    ):
        raise PlaylistError("playlist processing limit is invalid")
    completed_ids = {item["video_id"] for item in current["completed"]}
    unavailable_ids = {item["video_id"] for item in current["inaccessible"]}
    processed = 0
    for item in plan["items"]:
        video_id = item["video_id"]
        if video_id in completed_ids or video_id in unavailable_ids:
            continue
        if max_new_items is not None and processed >= max_new_items:
            break
        if item["availability"] == "INACCESSIBLE":
            current["inaccessible"].append({
                "video_id": video_id,
                "video_source_id": item["video_source_id"],
                "snapshot_id": plan["snapshot_id"],
                "snapshot_position": item["position"],
                "reason": "REMOTE_ITEM_INACCESSIBLE",
            })
        else:
            result = processor(copy.deepcopy(item))
            current["completed"].append(
                _validated_result(plan, item, result, artifact_root)
            )
        processed += 1
        _finalize_checkpoint(plan, current)
        validate_checkpoint(plan, current, artifact_root, verify_artifacts=False)
        checkpoint_writer(copy.deepcopy(current))
    _finalize_checkpoint(plan, current)
    validate_checkpoint(plan, current, artifact_root)
    return current


def validate_checkpoint(
    plan: dict[str, Any],
    checkpoint: dict[str, Any],
    artifact_root: Path,
    *,
    verify_artifacts: bool = True,
) -> None:
    validate_plan(plan)
    required = {
        "schema_version", "run_id", "plan_id", "collection_id", "snapshot_id",
        "status", "next_index", "completed", "inaccessible", "checkpoint_sha256",
    }
    if not isinstance(checkpoint, dict) or set(checkpoint) != required:
        raise PlaylistError("playlist checkpoint differs from v1")
    if any(checkpoint[key] != plan[key] for key in ("plan_id", "collection_id", "snapshot_id")):
        raise PlaylistError("playlist checkpoint identity differs from plan")
    expected_run = derive_imported_id(
        "operation", "integra.youtube.playlist.run", plan["plan_id"], plan["plan_sha256"]
    )
    if checkpoint["run_id"] != expected_run or checkpoint["status"] not in {"PAUSED", "COMPLETE"}:
        raise PlaylistError("playlist checkpoint lifecycle differs")
    if (
        not isinstance(checkpoint["completed"], list)
        or not isinstance(checkpoint["inaccessible"], list)
        or not isinstance(checkpoint["next_index"], int)
        or isinstance(checkpoint["next_index"], bool)
        or checkpoint["next_index"] < 0
    ):
        raise PlaylistError("playlist checkpoint collections or index are invalid")
    handled: set[str] = set()
    artifact_paths: set[str] = set()
    for record in checkpoint["completed"]:
        _validate_completed_record(
            plan, record, artifact_root, verify_artifact=verify_artifacts
        )
        if record["video_id"] in handled:
            raise PlaylistError("playlist checkpoint contains duplicate video")
        if record["relative_path"] in artifact_paths:
            raise PlaylistError("playlist checkpoint reuses an artifact path")
        handled.add(record["video_id"])
        artifact_paths.add(record["relative_path"])
    for record in checkpoint["inaccessible"]:
        _validate_inaccessible_record(plan, record)
        if record["video_id"] in handled:
            raise PlaylistError("playlist checkpoint contains duplicate video")
        handled.add(record["video_id"])
    expected_next = next(
        (index for index, video_id in enumerate(plan["selected_video_ids"]) if video_id not in handled),
        len(plan["selected_video_ids"]),
    )
    if checkpoint["next_index"] != expected_next:
        raise PlaylistError("playlist checkpoint next index differs")
    expected_status = "COMPLETE" if len(handled) == len(plan["items"]) else "PAUSED"
    if checkpoint["status"] != expected_status:
        raise PlaylistError("playlist checkpoint completion differs")
    if checkpoint["checkpoint_sha256"] != _checkpoint_hash(checkpoint):
        raise PlaylistError("playlist checkpoint hash differs")


def diff_playlist_refresh(
    previous: dict[str, Any],
    current: dict[str, Any],
    checkpoint: dict[str, Any] | None = None,
    *,
    artifact_root: Path | None = None,
) -> dict[str, Any]:
    validate_discovery(previous)
    validate_discovery(current)
    if previous["collection_id"] != current["collection_id"]:
        raise PlaylistError("playlist refresh collection differs")
    retained = []
    if checkpoint is not None:
        if artifact_root is None:
            raise PlaylistError("retained evidence requires an artifact root")
        _validate_retained_checkpoint(previous, checkpoint, artifact_root)
        retained = copy.deepcopy(checkpoint.get("completed", []))
    payload = _refresh_payload(previous, current, retained)
    refresh_sha256 = content_sha256(payload)
    refresh = {
        **payload,
        "refresh_id": derive_imported_id(
            "artifact",
            "youtube.playlist.refresh",
            previous["collection_id"],
            refresh_sha256,
        ),
        "refresh_sha256": refresh_sha256,
    }
    validate_refresh(previous, current, refresh, artifact_root=artifact_root)
    return refresh


def validate_refresh(
    previous: dict[str, Any],
    current: dict[str, Any],
    refresh: dict[str, Any],
    *,
    artifact_root: Path | None = None,
) -> None:
    validate_discovery(previous)
    validate_discovery(current)
    if previous["collection_id"] != current["collection_id"]:
        raise PlaylistError("playlist refresh collection differs")
    required = {
        "schema_version", "refresh_id", "refresh_sha256", "collection_id",
        "previous_snapshot_id", "previous_snapshot_sha256",
        "current_snapshot_id", "current_snapshot_sha256",
        "added_video_ids", "removed_video_ids",
        "reordered_video_ids", "became_inaccessible_video_ids",
        "restored_video_ids", "retained_completed_evidence",
    }
    if not isinstance(refresh, dict) or set(refresh) != required:
        raise PlaylistError("playlist refresh differs from v1")
    retained = refresh.get("retained_completed_evidence")
    if not isinstance(retained, list):
        raise PlaylistError("playlist retained evidence is invalid")
    if retained:
        if artifact_root is None:
            raise PlaylistError("retained evidence requires an artifact root")
        _validate_retained_records(previous, retained, artifact_root)
    payload = _refresh_payload(previous, current, retained)
    refresh_sha256 = content_sha256(payload)
    expected = {
        **payload,
        "refresh_id": derive_imported_id(
            "artifact",
            "youtube.playlist.refresh",
            previous["collection_id"],
            refresh_sha256,
        ),
        "refresh_sha256": refresh_sha256,
    }
    if refresh != expected:
        raise PlaylistError("playlist refresh differs from exact snapshots")


def _refresh_payload(
    previous: dict[str, Any],
    current: dict[str, Any],
    retained: list[dict[str, Any]],
) -> dict[str, Any]:
    old = {item["video_id"]: item for item in previous["items"]}
    new = {item["video_id"]: item for item in current["items"]}
    shared = set(old) & set(new)
    return {
        "schema_version": "1.0",
        "collection_id": previous["collection_id"],
        "previous_snapshot_id": previous["snapshot_id"],
        "previous_snapshot_sha256": previous["snapshot_sha256"],
        "current_snapshot_id": current["snapshot_id"],
        "current_snapshot_sha256": current["snapshot_sha256"],
        "added_video_ids": [
            item["video_id"]
            for item in current["items"]
            if item["video_id"] not in old
        ],
        "removed_video_ids": [
            item["video_id"]
            for item in previous["items"]
            if item["video_id"] not in new
        ],
        "reordered_video_ids": sorted(
            video_id
            for video_id in shared
            if old[video_id]["position"] != new[video_id]["position"]
        ),
        "became_inaccessible_video_ids": sorted(
            video_id
            for video_id in shared
            if old[video_id]["availability"] == "AVAILABLE"
            and new[video_id]["availability"] == "INACCESSIBLE"
        ),
        "restored_video_ids": sorted(
            video_id
            for video_id in shared
            if old[video_id]["availability"] == "INACCESSIBLE"
            and new[video_id]["availability"] == "AVAILABLE"
        ),
        "retained_completed_evidence": copy.deepcopy(retained),
    }


def _empty_checkpoint(plan: dict[str, Any]) -> dict[str, Any]:
    checkpoint = {
        "schema_version": "1.0",
        "run_id": derive_imported_id(
            "operation", "integra.youtube.playlist.run", plan["plan_id"], plan["plan_sha256"]
        ),
        "plan_id": plan["plan_id"], "collection_id": plan["collection_id"],
        "snapshot_id": plan["snapshot_id"], "status": "PAUSED", "next_index": 0,
        "completed": [], "inaccessible": [], "checkpoint_sha256": "",
    }
    checkpoint["checkpoint_sha256"] = _checkpoint_hash(checkpoint)
    return checkpoint


def _finalize_checkpoint(plan: dict[str, Any], checkpoint: dict[str, Any]) -> None:
    handled = {
        item["video_id"]
        for item in checkpoint["completed"] + checkpoint["inaccessible"]
    }
    checkpoint["status"] = (
        "COMPLETE" if handled == set(plan["selected_video_ids"]) else "PAUSED"
    )
    checkpoint["next_index"] = next(
        (
            index
            for index, video_id in enumerate(plan["selected_video_ids"])
            if video_id not in handled
        ),
        len(plan["selected_video_ids"]),
    )
    checkpoint["checkpoint_sha256"] = _checkpoint_hash(checkpoint)


def _validated_result(
    plan: dict[str, Any],
    item: dict[str, Any],
    result: dict[str, Any],
    artifact_root: Path,
) -> dict[str, Any]:
    if not isinstance(result, dict) or set(result) != {"relative_path"}:
        raise PlaylistError("playlist processor result differs from v1")
    relative_path = _validate_relative_artifact_path(result["relative_path"])
    size_bytes, content_sha256 = _hash_confined_regular_file(
        artifact_root, relative_path
    )
    artifact_id = derive_imported_id(
        "artifact", "youtube.playlist.item", item["video_source_id"], content_sha256
    )
    return {
        "video_id": item["video_id"], "video_source_id": item["video_source_id"],
        "artifact_id": artifact_id, "content_sha256": content_sha256,
        "size_bytes": size_bytes, "relative_path": relative_path,
        "snapshot_id": plan["snapshot_id"], "snapshot_position": item["position"],
        "provenance_status": "EXACT", "integrity_status": "PASS",
    }


def _validate_completed_record(
    plan: dict[str, Any],
    record: dict[str, Any],
    artifact_root: Path,
    *,
    verify_artifact: bool,
) -> None:
    fields = {
        "video_id", "video_source_id", "artifact_id", "content_sha256", "size_bytes",
        "relative_path", "snapshot_id", "snapshot_position", "provenance_status",
        "integrity_status",
    }
    if (
        not isinstance(record, dict)
        or set(record) != fields
        or record["provenance_status"] != "EXACT"
        or record["integrity_status"] != "PASS"
    ):
        raise PlaylistError("completed playlist record differs from v1")
    item = _plan_item(plan, record["video_id"])
    if any(record[key] != value for key, value in {
        "video_source_id": item["video_source_id"], "snapshot_id": plan["snapshot_id"],
        "snapshot_position": item["position"],
    }.items()) or not _is_sha256(record["content_sha256"]):
        raise PlaylistError("completed playlist provenance differs")
    if record["artifact_id"] != derive_imported_id(
        "artifact", "youtube.playlist.item", item["video_source_id"], record["content_sha256"]
    ) or (
        not isinstance(record["size_bytes"], int)
        or isinstance(record["size_bytes"], bool)
        or record["size_bytes"] < 0
    ):
        raise PlaylistError("completed playlist artifact identity differs")
    relative_path = _validate_relative_artifact_path(record["relative_path"])
    if verify_artifact:
        size_bytes, content_sha256 = _hash_confined_regular_file(
            artifact_root, relative_path
        )
        if (
            size_bytes != record["size_bytes"]
            or content_sha256 != record["content_sha256"]
        ):
            raise PlaylistError("completed playlist artifact bytes differ")


def _validate_inaccessible_record(plan: dict[str, Any], record: dict[str, Any]) -> None:
    if not isinstance(record, dict) or set(record) != {
        "video_id", "video_source_id", "snapshot_id", "snapshot_position", "reason"
    } or record["reason"] != "REMOTE_ITEM_INACCESSIBLE":
        raise PlaylistError("inaccessible playlist record differs from v1")
    item = _plan_item(plan, record["video_id"])
    if item["availability"] != "INACCESSIBLE" or any(record[key] != value for key, value in {
        "video_source_id": item["video_source_id"], "snapshot_id": plan["snapshot_id"],
        "snapshot_position": item["position"],
    }.items()):
        raise PlaylistError("inaccessible playlist provenance differs")


def _plan_item(plan: dict[str, Any], video_id: str) -> dict[str, Any]:
    matches = [item for item in plan["items"] if item["video_id"] == video_id]
    if len(matches) != 1:
        raise PlaylistError("playlist checkpoint video is outside plan")
    return matches[0]


def _checkpoint_hash(checkpoint: dict[str, Any]) -> str:
    return content_sha256({key: value for key, value in checkpoint.items() if key != "checkpoint_sha256"})


def _validate_retained_checkpoint(
    discovery: dict[str, Any], checkpoint: dict[str, Any], artifact_root: Path
) -> None:
    checkpoint_fields = {
        "schema_version", "run_id", "plan_id", "collection_id", "snapshot_id",
        "status", "next_index", "completed", "inaccessible", "checkpoint_sha256",
    }
    if (
        not isinstance(checkpoint, dict)
        or set(checkpoint) != checkpoint_fields
        or checkpoint.get("schema_version") != "1.0"
        or checkpoint.get("status") not in {"PAUSED", "COMPLETE"}
        or checkpoint.get("collection_id") != discovery["collection_id"]
        or checkpoint.get("snapshot_id") != discovery["snapshot_id"]
        or checkpoint.get("checkpoint_sha256") != _checkpoint_hash(checkpoint)
        or not isinstance(checkpoint.get("completed"), list)
    ):
        raise PlaylistError("retained playlist checkpoint differs from snapshot")
    _validate_retained_records(discovery, checkpoint["completed"], artifact_root)


def _validate_retained_records(
    discovery: dict[str, Any],
    records: list[dict[str, Any]],
    artifact_root: Path,
) -> None:
    items = {item["video_id"]: item for item in discovery["items"]}
    seen: set[str] = set()
    artifact_paths: set[str] = set()
    for record in records:
        item = items.get(record.get("video_id")) if isinstance(record, dict) else None
        record_fields = {
            "video_id", "video_source_id", "artifact_id", "content_sha256",
            "size_bytes", "relative_path", "snapshot_id", "snapshot_position",
            "provenance_status", "integrity_status",
        }
        if (
            item is None
            or set(record) != record_fields
            or record.get("video_id") in seen
            or record.get("relative_path") in artifact_paths
            or record.get("video_source_id") != item["video_source_id"]
            or record.get("snapshot_id") != discovery["snapshot_id"]
            or record.get("snapshot_position") != item["position"]
            or record.get("provenance_status") != "EXACT"
            or record.get("integrity_status") != "PASS"
            or not isinstance(record.get("size_bytes"), int)
            or isinstance(record.get("size_bytes"), bool)
            or record.get("size_bytes") < 0
            or not _is_sha256(record.get("content_sha256"))
            or record.get("artifact_id") != derive_imported_id(
                "artifact",
                "youtube.playlist.item",
                item["video_source_id"],
                record.get("content_sha256"),
            )
        ):
            raise PlaylistError("retained playlist evidence is invalid")
        try:
            size_bytes, content_sha256 = _hash_confined_regular_file(
                artifact_root,
                _validate_relative_artifact_path(record.get("relative_path")),
            )
        except (OSError, PlaylistError) as error:
            raise PlaylistError("retained playlist artifact is unavailable") from error
        if (
            size_bytes != record["size_bytes"]
            or content_sha256 != record["content_sha256"]
        ):
            raise PlaylistError("retained playlist artifact bytes differ")
        seen.add(record["video_id"])
        artifact_paths.add(record["relative_path"])


def _storage_estimate(items: list[dict[str, Any]]) -> dict[str, int]:
    source = sum(item["estimated_download_bytes"] for item in items if item["availability"] == "AVAILABLE")
    extracted_audio = source // 5
    cache = source // 10
    intermediate = source // 10
    final_output = source // 20
    safety_margin = (source + extracted_audio + cache + intermediate + final_output) // 5
    result = {
        "source": source, "extracted_audio": extracted_audio, "cache": cache,
        "intermediate_media": intermediate, "final_output": final_output,
        "safety_margin": safety_margin,
    }
    result["required_disk_bytes"] = sum(result.values())
    return result


def _validate_snapshot_input(snapshot: dict[str, Any]) -> None:
    if not isinstance(snapshot, dict) or set(snapshot) != {
        "schema_version", "provider", "playlist_native_id", "fetched_at", "items"
    } or snapshot.get("schema_version") != "1.0" or snapshot.get("provider") != "youtube":
        raise PlaylistError("playlist snapshot input differs from v1")
    if not isinstance(snapshot["playlist_native_id"], str) or not snapshot["playlist_native_id"]:
        raise PlaylistError("playlist native identity is invalid")
    if not _is_utc_timestamp(snapshot["fetched_at"]):
        raise PlaylistError("playlist snapshot time is invalid")
    items = snapshot["items"]
    if not isinstance(items, list) or not items:
        raise PlaylistError("playlist snapshot item inventory is empty")
    seen: set[str] = set()
    for position, item in enumerate(items):
        if not isinstance(item, dict) or set(item) != {
            "video_id", "position", "title", "availability", "duration_seconds",
            "estimated_download_bytes",
        }:
            raise PlaylistError("playlist snapshot item differs from v1")
        if not isinstance(item["video_id"], str) or not item["video_id"] or item["video_id"] in seen:
            raise PlaylistError("playlist snapshot video identity is invalid")
        seen.add(item["video_id"])
        if not isinstance(item["title"], str) or not item["title"].strip():
            raise PlaylistError("playlist snapshot title is invalid")
        if (
            isinstance(item["position"], bool)
            or item["position"] != position
            or item["availability"] not in AVAILABILITY
        ):
            raise PlaylistError("playlist snapshot order or availability is invalid")
        if (
            not isinstance(item["duration_seconds"], int)
            or isinstance(item["duration_seconds"], bool)
            or item["duration_seconds"] < 0
        ):
            raise PlaylistError("playlist duration estimate is invalid")
        if (
            not isinstance(item["estimated_download_bytes"], int)
            or isinstance(item["estimated_download_bytes"], bool)
            or item["estimated_download_bytes"] < 0
        ):
            raise PlaylistError("playlist byte estimate is invalid")


def _validate_planned_item(item: dict[str, Any]) -> None:
    if not isinstance(item, dict) or set(item) != {
        "video_id", "position", "title", "availability", "duration_seconds",
        "estimated_download_bytes", "video_source_id",
    }:
        raise PlaylistError("playlist plan item differs from v1")
    if (
        not isinstance(item["video_id"], str)
        or not item["video_id"]
        or not isinstance(item["title"], str)
        or not item["title"].strip()
        or item["availability"] not in AVAILABILITY
        or not isinstance(item["position"], int)
        or isinstance(item["position"], bool)
        or item["position"] < 0
        or not isinstance(item["duration_seconds"], int)
        or isinstance(item["duration_seconds"], bool)
        or item["duration_seconds"] < 0
        or not isinstance(item["estimated_download_bytes"], int)
        or isinstance(item["estimated_download_bytes"], bool)
        or item["estimated_download_bytes"] < 0
        or not isinstance(item["video_source_id"], str)
        or not item["video_source_id"].startswith("urn:integra:source:")
    ):
        raise PlaylistError("playlist plan item state is invalid")


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _validate_relative_artifact_path(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise PlaylistError("playlist artifact path is invalid")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or str(path) != value
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
        or ".staging" in path.parts
        or any(part.startswith(".staging-") for part in path.parts)
    ):
        raise PlaylistError("playlist artifact path is unsafe")
    return value


def _hash_confined_regular_file(root: Path, relative_path: str) -> tuple[int, str]:
    parts = PurePosixPath(relative_path).parts
    descriptors: list[int] = []
    try:
        current = os.open(
            Path(root), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        )
        descriptors.append(current)
        if not stat.S_ISDIR(os.fstat(current).st_mode):
            raise PlaylistError("playlist artifact root is not a directory")
        for part in parts[:-1]:
            current = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=current,
            )
            descriptors.append(current)
        file_descriptor = os.open(
            parts[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=current
        )
        descriptors.append(file_descriptor)
        metadata = os.fstat(file_descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise PlaylistError("playlist artifact is not a single-linked regular file")
        signature = _stable_file_metadata(metadata)
        digest = hashlib.sha256()
        size = 0
        while True:
            chunk = os.read(file_descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
        if _stable_file_metadata(os.fstat(file_descriptor)) != signature:
            raise PlaylistError("playlist artifact changed during verification")
        return size, digest.hexdigest()
    except PlaylistError:
        raise
    except OSError as error:
        raise PlaylistError("playlist artifact is missing or unsafe") from error
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _stable_file_metadata(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_nlink,
        metadata.st_uid,
        metadata.st_gid,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _is_utc_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value.endswith("Z"):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo == timezone.utc
