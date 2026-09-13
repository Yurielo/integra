"""Versioned file adapter to the pinned VideoText SRTService executable."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

from .videotext_runtime import COMMIT

SERVICE_SHA256 = "417017a6a3becc395e88e2554e8d7c2dca51b09de9743e8c5c0cf81ac9ba6205"
ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def preflight() -> dict:
    bundled = ROOT / "runtime/videotext/translation-worker"
    default = bundled if bundled.is_file() else ROOT / "build/videotext-subtitles/translation-worker"
    worker = Path(os.environ.get("INTEGRA_VIDEOTEXT_SUBTITLE_WORKER", str(default)))
    manifest = worker.parent / "runtime.json"
    if worker.is_symlink() or not worker.is_file() or not os.access(worker, os.X_OK):
        raise ValueError("VideoText subtitle runtime is unavailable")
    if manifest.is_symlink() or not manifest.is_file():
        raise ValueError("VideoText subtitle runtime identity is unavailable")
    identity = json.loads(manifest.read_bytes())
    if (identity.get("component") != "videotext" or identity.get("commit_sha") != COMMIT
            or identity.get("srt_service_sha256") != SERVICE_SHA256
            or identity.get("worker_sha256") != digest(worker)):
        raise ValueError("VideoText subtitle runtime identity mismatch")
    return {"state": "READY", "component": "videotext", "commit_sha": COMMIT,
            "srt_service_sha256": SERVICE_SHA256, "worker_sha256": identity["worker_sha256"],
            "worker": str(worker.resolve())}


def process(source: Path, target: Path, operation: str = "normalize", **options) -> dict:
    source, target = Path(source), Path(target)
    if source.is_symlink() or not source.is_file():
        raise ValueError("Subtitle source is unavailable")
    if target.exists() or target.is_symlink():
        raise FileExistsError("Subtitle output already exists")
    if target.parent.is_symlink() or not target.parent.is_dir():
        raise ValueError("Subtitle output directory is unavailable")
    if operation not in {"normalize", "clip", "speed"} or set(options) - {
        "media_duration", "start_seconds", "end_seconds", "speed_factor"}:
        raise ValueError("Unsupported subtitle operation")
    runtime = preflight()
    source_hash = digest(source)
    with tempfile.TemporaryDirectory(prefix=".videotext-subtitles-", dir=target.parent) as temporary:
        stage = Path(temporary)
        output = stage / "result.srt"
        request = {"schema_version": "1.0", "operation": operation,
                   "input_srt": str(source.resolve()), "output_srt": str(output.resolve()), **options}
        request_path = stage / "request.json"
        request_path.write_text(json.dumps(request), encoding="utf-8")
        completed = subprocess.run([runtime["worker"], "--subtitle-request", str(request_path)],
            capture_output=True, text=True, timeout=30)
        if completed.returncode:
            raise ValueError("VideoText rejected subtitle data or operation")
        result = json.loads(completed.stdout)
        if (result.get("schema_version") != "1.0" or result.get("component") != "videotext"
                or result.get("capability") != "subtitles" or result.get("operation") != operation
                or result.get("output_srt") != str(output.resolve())
                or type(result.get("cue_count")) is not int or result["cue_count"] <= 0
                or result.get("warnings") != [] or result.get("skipped_zero_duration_count") != 0
                or output.is_symlink() or not output.is_file() or not output.stat().st_size
                or digest(source) != source_hash):
            raise ValueError("VideoText subtitle result cannot be verified")
        output.read_text(encoding="utf-8")
        os.link(output, target)  # Exclusive promotion: never overwrite user data.
    return {**result, "output_srt": str(target.resolve()), "runtime": runtime,
            "source_sha256": source_hash, "output_sha256": digest(target)}


def normalize(source: Path, target: Path) -> dict:
    return process(source, target)
