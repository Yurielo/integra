"""Live, user-initiated YouTube playlist acquisition for Integra.

The accepted :mod:`integra_core.playlist` contracts deliberately remain
offline-safe.  This module is the adapter boundary which fetches metadata with
the locally installed yt-dlp, normalizes it into that contract, and then
downloads the selected members one at a time into Integra-owned storage.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from .playlist import build_playlist_plan, discover_playlist, process_playlist
from .user_media import _is_run_cancelled, atomic_json, now
from .youtube_runtime import YouTubeRuntimeError, download_video, preflight


class YouTubePlaylistRuntimeError(ValueError):
    """A truthful failure from the local playlist adapter."""


def _token(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _run_metadata(command: list[str], project_dir: Path, run_id: str | None) -> str:
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        while process.poll() is None:
            if _is_run_cancelled(project_dir, run_id):
                process.terminate()
                raise YouTubePlaylistRuntimeError("YouTube playlist discovery was cancelled")
            time.sleep(0.1)
        stdout, stderr = process.communicate()
        if process.returncode != 0:
            detail = stderr.strip().splitlines()[-1] if stderr.strip() else "yt-dlp failed"
            raise YouTubePlaylistRuntimeError(f"YouTube playlist discovery failed: {detail[:300]}")
        return stdout
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=2)


def _integer(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)) and value >= 0:
        return int(value)
    return 0


def _snapshot_from_yt_dlp(payload: dict[str, Any]) -> dict[str, Any]:
    playlist_id = payload.get("id")
    entries = payload.get("entries")
    if not isinstance(playlist_id, str) or not playlist_id or not isinstance(entries, list) or not entries:
        raise YouTubePlaylistRuntimeError("yt-dlp did not return a usable YouTube playlist inventory")
    items = []
    for position, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise YouTubePlaylistRuntimeError("yt-dlp returned an invalid playlist item")
        video_id = entry.get("id")
        title = entry.get("title")
        if not isinstance(video_id, str) or not video_id or not isinstance(title, str) or not title.strip():
            raise YouTubePlaylistRuntimeError("yt-dlp returned a playlist item without stable identity")
        unavailable = entry.get("availability") in {"private", "subscriber_only", "premium_only"} or title.strip().lower() in {"[private video]", "[deleted video]"}
        items.append({
            "video_id": video_id,
            "position": position,
            "title": title.strip(),
            "availability": "INACCESSIBLE" if unavailable else "AVAILABLE",
            "duration_seconds": _integer(entry.get("duration")),
            # yt-dlp's flat playlist result frequently lacks a byte estimate.
            # Zero records that fact; this adapter never invents one.
            "estimated_download_bytes": _integer(entry.get("filesize") or entry.get("filesize_approx")),
        })
    return {
        "schema_version": "1.0", "provider": "youtube", "playlist_native_id": playlist_id,
        "fetched_at": now(), "items": items,
    }


def discover_live_playlist(project_dir: Path, source: dict[str, Any], *, run_id: str | None) -> dict[str, Any]:
    """Fetch a playlist inventory and preserve the separate live provenance.

    The returned ``discovery`` remains a valid offline playlist contract;
    live network provenance lives in the surrounding adapter record instead of
    weakening that contract's ``network_access_performed=False`` invariant.
    """
    if source.get("source_type") != "YOUTUBE_PLAYLIST" or source.get("kind") != "URL":
        raise YouTubePlaylistRuntimeError("YouTube adapter accepts a playlist URL")
    url = source.get("input")
    if not isinstance(url, str) or not url:
        raise YouTubePlaylistRuntimeError("YouTube playlist source is incomplete")
    runtime = preflight()
    output = _run_metadata([
        runtime["yt_dlp"], "--flat-playlist", "--dump-single-json", "--no-download",
        "--no-warnings", "--skip-download", url,
    ], project_dir, run_id)
    try:
        payload = json.loads(output)
    except json.JSONDecodeError as error:
        raise YouTubePlaylistRuntimeError("yt-dlp returned invalid playlist metadata") from error
    if not isinstance(payload, dict):
        raise YouTubePlaylistRuntimeError("yt-dlp returned invalid playlist metadata")
    snapshot = _snapshot_from_yt_dlp(payload)
    discovery = discover_playlist(snapshot)
    title = payload.get("title")
    if not isinstance(title, str) or not title.strip():
        title = None
    return {
        "schema_version": "1.0",
        "acquisition": {
            "source_url": url, "fetched_at": snapshot["fetched_at"], "runtime": runtime,
            "network_access_performed": True, "mode": "yt-dlp-flat-playlist-metadata",
        },
        "playlist_title": title,
        "snapshot": snapshot,
        "discovery": discovery,
    }


def resolve_live_playlist_sources(project_dir: Path, source: dict[str, Any], *, run_id: str | None) -> dict[str, Any]:
    """Expand a live playlist into ordered, ordinary Process sources.

    Discovery remains at the provider boundary.  The UI receives a truthful
    inventory before it can put any member into a Process plan; the selected
    members then use the existing single-video adapter and source lifecycle.
    """
    live = discover_live_playlist(project_dir, source, run_id=run_id)
    discovery = live["discovery"]
    acquisition = live["acquisition"]
    context = {
        "schema_version": "1.0",
        "collection_id": discovery["collection_id"],
        "playlist_native_id": discovery["playlist_native_id"],
        "playlist_title": live["playlist_title"],
        "snapshot_id": discovery["snapshot_id"],
        "snapshot_sha256": discovery["snapshot_sha256"],
        "fetched_at": discovery["fetched_at"],
        "source_url": acquisition["source_url"],
        "acquisition": acquisition,
        "items": [
            {key: item[key] for key in (
                "video_id", "position", "title", "availability", "duration_seconds",
                "estimated_download_bytes", "video_source_id",
            )}
            for item in discovery["items"]
        ],
    }
    sources: list[dict[str, Any]] = []
    unavailable: list[dict[str, Any]] = []
    for item in discovery["items"]:
        membership = {
            "collection_id": context["collection_id"],
            "playlist_native_id": context["playlist_native_id"],
            "snapshot_id": context["snapshot_id"],
            "snapshot_sha256": context["snapshot_sha256"],
            "position": item["position"],
            "video_id": item["video_id"],
            "title": item["title"],
            "availability": item["availability"],
        }
        if item["availability"] != "AVAILABLE":
            unavailable.append(membership)
            continue
        sources.append({
            "source_id": item["video_source_id"],
            "display_name": item["title"],
            "input": f"https://www.youtube.com/watch?v={item['video_id']}",
            "source_type": "YOUTUBE_VIDEO",
            "kind": "URL",
            "properties": {
                "remote_ingest_supported": True,
                "playlist_membership": membership,
                # Preserve the complete observed inventory with every selected
                # Process source.  This is evidence, not a second execution plan.
                "playlist_context": context,
            },
        })
    return {"schema_version": "1.0", "playlist": context, "sources": sources, "unavailable": unavailable}


def _copy_owned_media(source: Path, artifact_root: Path, video_id: str) -> str:
    if source.is_symlink() or not source.is_file():
        raise YouTubePlaylistRuntimeError("downloaded playlist media is unavailable")
    source = source.resolve(strict=True)
    suffix = source.suffix.lower()
    target_dir = artifact_root / "items"
    target_dir.mkdir(parents=True, exist_ok=True)
    if target_dir.is_symlink() or not target_dir.is_dir():
        raise YouTubePlaylistRuntimeError("playlist artifact directory is unsafe")
    relative = f"items/{_token(video_id)}{suffix}"
    target = artifact_root / relative
    temporary = target.with_name(f".{target.name}.tmp")
    shutil.copyfile(source, temporary)
    if hashlib.sha256(temporary.read_bytes()).hexdigest() != hashlib.sha256(source.read_bytes()).hexdigest():
        temporary.unlink(missing_ok=True)
        raise YouTubePlaylistRuntimeError("playlist artifact copy verification failed")
    os.replace(temporary, target)
    return relative


def execute_playlist(project_dir: Path, source: dict[str, Any], *, run_id: str | None) -> dict[str, str]:
    """Discover and sequentially download one user-selected playlist.

    A checkpoint is atomically persisted after each handled member, so a
    worker interruption never turns unverified media into a completed result.
    """
    live = discover_live_playlist(project_dir, source, run_id=run_id)
    discovery = live["discovery"]
    plan = build_playlist_plan(discovery)
    root = project_dir / "artifacts" / "youtube_playlists" / _token(source["source_id"]) / _token(run_id or plan["plan_id"])
    root.mkdir(parents=True, exist_ok=True)
    if root.is_symlink() or not root.is_dir():
        raise YouTubePlaylistRuntimeError("playlist artifact root is unsafe")
    snapshot_path = root / "playlist_snapshot.json"
    discovery_path = root / "playlist_discovery.json"
    plan_path = root / "playlist_plan.json"
    checkpoint_path = root / "playlist_checkpoint.json"
    downloads_path = root / "playlist_downloads.json"
    atomic_json(snapshot_path, live["snapshot"])
    atomic_json(discovery_path, discovery)
    atomic_json(plan_path, plan)
    downloads: dict[str, dict[str, Any]] = {}
    if downloads_path.is_file() and not downloads_path.is_symlink():
        saved = json.loads(downloads_path.read_bytes())
        if isinstance(saved, dict):
            downloads = saved
    checkpoint = None
    if checkpoint_path.is_file() and not checkpoint_path.is_symlink():
        checkpoint = json.loads(checkpoint_path.read_bytes())

    def write_checkpoint(value: dict[str, Any]) -> None:
        atomic_json(checkpoint_path, value)

    def download_member(item: dict[str, Any]) -> dict[str, str]:
        if _is_run_cancelled(project_dir, run_id):
            raise YouTubePlaylistRuntimeError("YouTube playlist download was cancelled")
        video_source = {
            "source_id": item["video_source_id"], "display_name": item["title"],
            "input": f"https://www.youtube.com/watch?v={item['video_id']}",
            "source_type": "YOUTUBE_VIDEO", "kind": "URL", "properties": {},
        }
        try:
            downloaded = download_video(project_dir, video_source, run_id=run_id)
        except YouTubeRuntimeError as error:
            raise YouTubePlaylistRuntimeError(str(error)) from error
        downloads[item["video_id"]] = downloaded
        atomic_json(downloads_path, downloads)
        return {"relative_path": _copy_owned_media(Path(downloaded["downloaded_path"]), root, item["video_id"])}

    completed = process_playlist(
        plan, download_member, checkpoint, artifact_root=root,
        checkpoint_writer=write_checkpoint,
    )
    return {
        "playlist_snapshot": str(snapshot_path), "playlist_discovery": str(discovery_path),
        "playlist_plan": str(plan_path), "playlist_checkpoint": str(checkpoint_path),
        "playlist_downloads": str(downloads_path), "playlist_artifacts_directory": str(root),
    }
