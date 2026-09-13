"""Versioned transport to original pinned VideoText media services (no media logic)."""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import threading
import time
from typing import Callable

from .videotext_runtime import COMMIT
from .videotext_subtitles import SERVICE_SHA256

ROOT = Path(__file__).resolve().parents[1]
MEDIA_SHA256 = "4c3d7fee2777291b297679b28b1727d8e54ed74e6d0172da58e83702570cdca5"
AUDIO_SHA256 = "ab525fe985a0fa1af8ba9ccf6b94e78b0095b0a240f057e8e381116acbd3d9f6"
# Resolution order of ToolRunner.resolve in the pinned VideoText component.
# PATH and Integra's FFmpeg override are intentionally not used: the component
# does not consult them when resolving these two tools.
MEDIA_TOOL_SEARCH_PATHS = (
    "/opt/homebrew/opt/ffmpeg-full/bin", "/usr/local/opt/ffmpeg-full/bin",
    "/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin",
)


class MediaCancelled(ValueError):
    """The calling job requested cancellation; no derivative was published."""


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def preflight() -> dict:
    bundled = ROOT / "runtime/videotext/translation-worker"
    default = bundled if bundled.is_file() else ROOT / "build/videotext-subtitles/translation-worker"
    worker = Path(os.environ.get("INTEGRA_VIDEOTEXT_MEDIA_WORKER", str(default)))
    manifest = worker.parent / "runtime.json"
    if worker.is_symlink() or not worker.is_file() or not os.access(worker, os.X_OK):
        raise ValueError("VideoText media runtime is unavailable")
    if manifest.is_symlink() or not manifest.is_file():
        raise ValueError("VideoText media runtime identity is unavailable")
    identity = json.loads(manifest.read_bytes())
    expected = {"component": "videotext", "commit_sha": COMMIT,
                "media_adapters_sha256": MEDIA_SHA256, "audio_adapter_sha256": AUDIO_SHA256,
                "srt_service_sha256": SERVICE_SHA256, "worker_sha256": digest(worker)}
    if not isinstance(identity, dict) or any(identity.get(key) != value for key, value in expected.items()):
        raise ValueError("VideoText media runtime identity mismatch")
    tools = {}
    for name in ("ffmpeg", "ffprobe"):
        for directory in MEDIA_TOOL_SEARCH_PATHS:
            candidate = Path(directory) / name
            if candidate.is_file() and os.access(candidate, os.X_OK):
                tools[name] = str(candidate)
                break
        else:
            raise ValueError(f"VideoText media dependency is unavailable: {name}")
    return {"state": "READY", **expected, "worker": str(worker.resolve()), "tools": tools}


def _stop(process: subprocess.Popen) -> None:
    # Always signal the group, including when its leader has already exited.
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            break
        if sig == signal.SIGTERM:
            try:
                process.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                pass
    process.wait(timeout=5)


def _execute(command: list, stage: Path, timeout: float, cancelled: Callable[[], bool] | None) -> dict:
    terminated = False
    def stop_requested(signum, frame):
        nonlocal terminated
        terminated = True
    previous = None
    main_thread = threading.current_thread() is threading.main_thread()
    if main_thread:
        previous = signal.signal(signal.SIGTERM, stop_requested)
    process = None
    try:
        with (stage / "stdout.json").open("wb") as stdout, (stage / "stderr.log").open("wb") as stderr:
            if cancelled and cancelled():
                raise MediaCancelled("Media processing cancelled")
            process = subprocess.Popen(command, stdout=stdout, stderr=stderr, start_new_session=True)
            deadline = time.monotonic() + timeout
            while process.poll() is None:
                if terminated or (cancelled and cancelled()):
                    raise MediaCancelled("Media processing cancelled")
                if time.monotonic() >= deadline:
                    raise TimeoutError("VideoText media processing timed out")
                time.sleep(0.05)
            if terminated or (cancelled and cancelled()):
                raise MediaCancelled("Media processing cancelled")
            if process.returncode:
                raise ValueError("VideoText rejected media data or operation")
        if (stage / "stdout.json").stat().st_size > 2 * 1024 * 1024:
            raise ValueError("VideoText media response exceeds contract limit")
        return json.loads((stage / "stdout.json").read_bytes())
    finally:
        if process is not None:
            _stop(process)
        if main_thread:
            signal.signal(signal.SIGTERM, previous)


def process(source: Path, target: Path, operation: str, *, start_seconds=None,
            end_seconds=None, speed_factor=None, subtitles: Path | None = None,
            timeout: float = 7200, cancelled: Callable[[], bool] | None = None) -> dict:
    source, target = Path(source), Path(target)
    if source.is_symlink() or not source.is_file():
        raise ValueError("Media source is unavailable")
    if target.exists() or target.is_symlink():
        raise FileExistsError("Media output already exists")
    if target.parent.is_symlink() or not target.parent.is_dir():
        raise ValueError("Media output directory is unavailable")
    parameters = {"clip": {"start_seconds", "end_seconds"}, "speed": {"speed_factor"},
                  "burn_subtitles": {"input_srt"}, "audio_analysis": set()}
    values = {"start_seconds": start_seconds, "end_seconds": end_seconds,
              "speed_factor": speed_factor, "input_srt": subtitles}
    if operation not in parameters or {key for key, value in values.items() if value is not None} != parameters[operation]:
        raise ValueError("Unsupported media operation or parameters")
    for number in (start_seconds, end_seconds, speed_factor, timeout):
        if number is not None and (type(number) not in (int, float) or not math.isfinite(number) or number < 0):
            raise ValueError("Media parameters must be finite non-negative numbers")
    if timeout <= 0 or (operation == "clip" and end_seconds <= start_seconds) or (operation == "speed" and not 0.5 <= speed_factor <= 2):
        raise ValueError("Media parameters are outside supported ranges")
    inputs = {"source": source}
    if subtitles is not None:
        subtitles = Path(subtitles)
        if subtitles.is_symlink() or not subtitles.is_file():
            raise ValueError("Subtitle input is unavailable")
        inputs["subtitles"] = subtitles
    runtime = preflight()
    hashes = {key: digest(path) for key, path in inputs.items()}
    with tempfile.TemporaryDirectory(prefix=".videotext-media-", dir=target.parent) as directory:
        stage = Path(directory)
        output = stage / ("result.json" if operation == "audio_analysis" else "result.mp4")
        request = {"schema_version": "1.0", "operation": operation,
                   "input_media": str(source.resolve()), "output_path": str(output.resolve())}
        request.update({key: str(Path(value).resolve()) if key == "input_srt" else value
                        for key, value in values.items() if value is not None})
        request_path = stage / "request.json"
        request_path.write_text(json.dumps(request, allow_nan=False), encoding="utf-8")
        result = _execute([runtime["worker"], "--media-request", str(request_path)], stage, timeout, cancelled)
        if (not isinstance(result, dict) or result.get("schema_version") != "1.0"
                or result.get("component") != "videotext" or result.get("capability") != "media"
                or result.get("operation") != operation or result.get("output_path") != str(output.resolve())
                or output.is_symlink() or not output.is_file() or not output.stat().st_size
                or any(digest(path) != hashes[key] for key, path in inputs.items())):
            raise ValueError("VideoText media result cannot be verified")
        for key in ("source_duration_seconds", "duration_seconds", "expected_duration_seconds"):
            value = result.get(key)
            if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
                raise ValueError("VideoText duration validation is invalid")
        expected = (end_seconds - start_seconds if operation == "clip" else
                    result["source_duration_seconds"] / speed_factor if operation == "speed" else result["source_duration_seconds"])
        if abs(result["duration_seconds"] - expected) > 0.25 or abs(result["expected_duration_seconds"] - expected) > 0.001:
            raise ValueError("VideoText media duration does not match operation")
        if operation == "audio_analysis":
            analysis = json.loads(output.read_bytes())
            if not isinstance(analysis, dict) or analysis.get("schemaVersion") != 1 or analysis.get("duration") != result["source_duration_seconds"]:
                raise ValueError("VideoText audio analysis is invalid")
        elif not isinstance(result.get("validation"), str) or "codec_type=video" not in result["validation"]:
            raise ValueError("VideoText video stream validation is missing")
        if cancelled and cancelled():
            raise MediaCancelled("Media processing cancelled")
        os.link(output, target)
    return {**result, "output_path": str(target.resolve()), "runtime": runtime,
            "input_sha256": hashes, "output_sha256": digest(target)}


def cut(source: Path, target: Path, start: float, end: float, **kwargs) -> dict:
    return process(source, target, "clip", start_seconds=start, end_seconds=end, **kwargs)


def burn(source: Path, subtitles: Path, target: Path, **kwargs) -> dict:
    return process(source, target, "burn_subtitles", subtitles=subtitles, **kwargs)


def adjust_speed(source: Path, target: Path, factor: float, **kwargs) -> dict:
    return process(source, target, "speed", speed_factor=factor, **kwargs)


def analyze_audio(source: Path, target: Path, **kwargs) -> dict:
    return process(source, target, "audio_analysis", **kwargs)
