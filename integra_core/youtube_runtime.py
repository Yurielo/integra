"""Local, user-initiated YouTube video ingest for Integra.

The adapter intentionally handles one video per source.  It downloads only
after the user executes a source-first plan and hands the resulting owned file
to the normal local-media runtime.  Playlist discovery and ingest remain a
separate, deferred capability.
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

from .user_media import SUPPORTED, _is_run_cancelled, atomic_json, now


class YouTubeRuntimeError(ValueError):
    """A truthful failure from the local yt-dlp runtime."""


def _executable() -> str | None:
    configured = os.environ.get("INTEGRA_YTDLP")
    candidates = [configured] if configured else []
    discovered = shutil.which("yt-dlp")
    if discovered:
        candidates.append(discovered)
    candidates.extend(f"{prefix}/yt-dlp" for prefix in ("/opt/homebrew/bin", "/usr/local/bin"))
    for value in candidates:
        if not value:
            continue
        try:
            path = Path(value).expanduser().resolve(strict=True)
        except OSError:
            continue
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
    return None


def preflight() -> dict[str, str]:
    """Verify the locally installed downloader without accessing YouTube."""
    executable = _executable()
    if not executable:
        raise YouTubeRuntimeError("yt-dlp is not installed; install yt-dlp or set INTEGRA_YTDLP")
    try:
        completed = subprocess.run(
            [executable, "--version"], capture_output=True, text=True, timeout=10, check=True
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise YouTubeRuntimeError("yt-dlp preflight failed") from error
    version = completed.stdout.strip()
    if not version:
        raise YouTubeRuntimeError("yt-dlp did not report a version")
    return {"state": "READY", "yt_dlp": executable, "version": version}


def _safe_download_directory(project_dir: Path, source_id: str, run_id: str | None) -> Path:
    source_token = hashlib.sha256(source_id.encode("utf-8")).hexdigest()
    run_token = hashlib.sha256((run_id or "standalone").encode("utf-8")).hexdigest()
    directory = project_dir / "sources" / "youtube" / source_token / run_token
    directory.mkdir(parents=True, exist_ok=True)
    if directory.is_symlink() or not directory.is_dir():
        raise YouTubeRuntimeError("YouTube download directory is unsafe")
    return directory.resolve(strict=True)


def _run_download(command: list[str], project_dir: Path, run_id: str | None) -> None:
    # Keep the downloader in the plan worker's process group.  The bridge's
    # cancellation action terminates that group, so a download cannot survive
    # after the user has stopped its run.
    process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    try:
        while process.poll() is None:
            if _is_run_cancelled(project_dir, run_id):
                process.terminate()
                raise YouTubeRuntimeError("YouTube download was cancelled")
            time.sleep(0.1)
        stderr = process.stderr.read() if process.stderr else ""
        if process.returncode != 0:
            detail = stderr.strip().splitlines()[-1] if stderr.strip() else "yt-dlp failed"
            raise YouTubeRuntimeError(f"YouTube download failed: {detail[:300]}")
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=2)
        if process.stderr and not process.stderr.closed:
            process.stderr.close()


def download_video(project_dir: Path, source: dict[str, Any], *, run_id: str | None) -> dict[str, Any]:
    """Download one selected YouTube video into Integra-owned storage.

    No title, description, transcript, or media content is invented here: the
    persisted record contains the exact user URL and content hash of the media
    file that yt-dlp actually produced.
    """
    if source.get("source_type") != "YOUTUBE_VIDEO" or source.get("kind") != "URL":
        raise YouTubeRuntimeError("YouTube adapter accepts one YouTube video URL")
    url = source.get("input")
    source_id = source.get("source_id")
    if not isinstance(url, str) or not url or not isinstance(source_id, str) or not source_id:
        raise YouTubeRuntimeError("YouTube source is incomplete")
    runtime = preflight()
    directory = _safe_download_directory(project_dir, source_id, run_id)
    template = directory / "source.%(ext)s"
    command = [
        runtime["yt_dlp"], "--no-playlist", "--no-part", "--restrict-filenames",
        "--no-write-thumbnail", "--no-write-info-json", "--no-write-subs",
        "--output", str(template), "--format", "bestaudio/best", url,
    ]
    _run_download(command, project_dir, run_id)
    candidates = [
        item for item in directory.iterdir()
        if not item.is_symlink() and item.is_file() and item.suffix.lower() in SUPPORTED and item.stat().st_size > 0
    ]
    if len(candidates) != 1:
        raise YouTubeRuntimeError("yt-dlp did not produce exactly one supported media file")
    media = candidates[0].resolve(strict=True)
    digest = hashlib.sha256(media.read_bytes()).hexdigest()
    record = {
        "schema_version": "1.0", "source_id": source_id, "source_url": url,
        "downloaded_path": str(media), "content_sha256": digest,
        "size_bytes": media.stat().st_size, "downloaded_at": now(),
        "runtime": runtime,
    }
    record_path = directory / "youtube_source.json"
    atomic_json(record_path, record)
    return record | {"record_path": str(record_path)}
