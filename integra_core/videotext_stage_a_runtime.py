"""Isolated, fail-closed Stage A bridge to VideoText 0.6.8 transcription.

This module is deliberately not connected to ``user_media`` or ``asr_reuse``.
It exists to establish runtime evidence before the Process route changes owner.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time
from typing import Any, Callable


COMMIT = "c4d851c9b39b2aeb696a12aa357d1ae0df350cd3"
WORKER_NAME = "videotext-stage-a-worker"
EXPECTED = {
    "component": "videotext", "commit_sha": COMMIT,
    "capability": "stage_a_transcript", "seminartext_dependency": False,
    "segmented_whisper_transcriber_sha256": "81a3c551e4aeb622c636213e011aaec980c43a24f301781691d79c0d8dfd65e3",
    "transcription_quality_service_sha256": "ee6ccf1c604cfd057bdf97314e1c2f05497e8b5f638d29adc3baf828ec69f5a0",
}
RESULT_PREFIX = "INTEGRA_VIDEOTEXT_STAGE_A_RESULT "


class StageAError(ValueError):
    pass


class StageACancelled(StageAError):
    pass


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file(path: Path | str, label: str, executable: bool = False) -> Path:
    try:
        value = Path(path).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise StageAError(f"{label} is unavailable") from error
    if value.is_symlink() or not value.is_file() or (executable and not os.access(value, os.X_OK)):
        raise StageAError(f"{label} is unavailable")
    return value


def _inside(path: Path, parent: Path) -> Path:
    try:
        value = path.resolve(strict=False)
        value.relative_to(parent.resolve(strict=True))
    except (OSError, RuntimeError, ValueError) as error:
        raise StageAError("Stage A path escapes its owned directory") from error
    return value


def _runtime(worker: Path | str) -> dict[str, Any]:
    worker = _file(worker, "VideoText Stage A worker", True)
    manifest = worker.parent / "runtime.json"
    if manifest.is_symlink() or not manifest.is_file():
        raise StageAError("VideoText Stage A runtime identity is unavailable")
    try:
        identity = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise StageAError("VideoText Stage A runtime identity is invalid") from error
    if any(identity.get(key) != value for key, value in EXPECTED.items()) or identity.get("worker_sha256") != _sha(worker):
        raise StageAError("VideoText Stage A runtime identity mismatch")
    return {**identity, "worker": str(worker)}


def preflight(*, worker: Path | str, ffmpeg: Path | str, ffprobe: Path | str,
              whisper: Path | str, model: Path | str, vad_model: Path | str | None = None) -> dict[str, Any]:
    runtime = _runtime(worker)
    tools = {
        "ffmpeg": _file(ffmpeg, "ffmpeg", True),
        "ffprobe": _file(ffprobe, "ffprobe", True),
        "whisper": _file(whisper, "whisper-cli", True),
        "model": _file(model, "Whisper model"),
    }
    if vad_model is not None:
        tools["vad_model"] = _file(vad_model, "Silero VAD model")
    return {"schema_version": "1.0", "state": "READY", "runtime": runtime,
            "tools": {name: {"path": str(path), "sha256": _sha(path)} for name, path in tools.items()}}


def _validate_srt(path: Path) -> int:
    try:
        chunks = [chunk for chunk in path.read_text(encoding="utf-8").replace("\r\n", "\n").strip().split("\n\n") if chunk]
    except OSError as error:
        raise StageAError("VideoText SRT is unavailable") from error
    previous_end = -1
    for expected, chunk in enumerate(chunks, 1):
        lines = chunk.split("\n")
        if len(lines) < 3 or lines[0] != str(expected):
            raise StageAError("VideoText SRT numbering is invalid")
        match = re.fullmatch(r"(\d+):(\d{2}):(\d{2}),(\d{3}) --> (\d+):(\d{2}):(\d{2}),(\d{3})", lines[1])
        if not match or not any(line.strip() for line in lines[2:]):
            raise StageAError("VideoText SRT cue is invalid")
        values = [int(value) for value in match.groups()]
        start = ((values[0] * 60 + values[1]) * 60 + values[2]) * 1000 + values[3]
        end = ((values[4] * 60 + values[5]) * 60 + values[6]) * 1000 + values[7]
        if end <= start or start < previous_end:
            raise StageAError("VideoText SRT timeline is invalid")
        previous_end = end
    if not chunks:
        raise StageAError("VideoText SRT is empty")
    return len(chunks)


def _stop(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=3)


def _cache_key(source: Path, runtime: dict[str, Any], identity: dict[str, Any], language: str) -> str:
    data = {"source_sha256": _sha(source), "language": language, "runtime": runtime,
            "tool_hashes": identity["tools"]}
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def run(*, source: Path | str, stage_root: Path | str, worker: Path | str, ffmpeg: Path | str,
        ffprobe: Path | str, whisper: Path | str, model: Path | str, vad_model: Path | str | None = None,
        language: str = "ru", timeout_seconds: float = 3600,
        cancelled: Callable[[], bool] | None = None) -> dict[str, Any]:
    """Run an owned cold job or return only a hash-bound warm result.

    ``stage_root`` must already be an owned, non-symlinked directory. No input
    path or reported artifact may escape it.
    """
    if language != "ru":
        raise StageAError("Stage A currently accepts only Russian source speech")
    source = _file(source, "Stage A source")
    root = Path(stage_root)
    if root.is_symlink() or not root.is_dir():
        raise StageAError("Stage A owned directory is unavailable")
    root = root.resolve()
    identity = preflight(worker=worker, ffmpeg=ffmpeg, ffprobe=ffprobe, whisper=whisper, model=model, vad_model=vad_model)
    key = _cache_key(source, identity["runtime"], identity, language)
    cache = root / ".videotext-stage-a-cache" / f"{key}.json"
    if cache.is_file() and not cache.is_symlink():
        try:
            result = json.loads(cache.read_text(encoding="utf-8"))
            for artifact in result["artifacts"].values():
                _inside(Path(artifact["path"]), root)
                if _sha(Path(artifact["path"])) != artifact["sha256"]:
                    raise StageAError("cached artifact drift")
            return {**result, "state": "REUSED", "cache_state": "WARM"}
        except (KeyError, OSError, json.JSONDecodeError, StageAError):
            cache.unlink(missing_ok=True)
    if cancelled and cancelled():
        raise StageACancelled("VideoText Stage A transcription cancelled")
    run_root = root / "runs" / key
    if run_root.exists():
        raise StageAError("Stage A run directory already exists")
    (run_root / "input").mkdir(parents=True)
    owned_source = run_root / "input" / ("source" + source.suffix.lower())
    shutil.copy2(source, owned_source)
    if _sha(source) != _sha(owned_source):
        raise StageAError("Stage A source copy verification failed")
    project = run_root / "project"
    request = {"schema_version": "1.0", "source_media_path": str(owned_source), "project_path": str(project),
               "whisper_model_path": identity["tools"]["model"]["path"], "language": language}
    request_path = run_root / "request.json"
    request_path.write_text(json.dumps(request, sort_keys=True), encoding="utf-8")
    bindir = run_root / "bin"; bindir.mkdir()
    for name in ("ffmpeg", "ffprobe", "whisper"):
        target = Path(identity["tools"][name]["path"])
        (bindir / ("whisper-cli" if name == "whisper" else name)).symlink_to(target)
    environment = {"PATH": f"{bindir}:/usr/bin:/bin:/usr/sbin:/sbin", "HOME": str(run_root),
                   "LANG": "en_US.UTF-8", "LC_ALL": "en_US.UTF-8", "PYTHONDONTWRITEBYTECODE": "1",
                   "VIDEOTEXT_HISTORY_PATH": str(run_root / "videotext-history.json")}
    if "vad_model" in identity["tools"]:
        # VideoText locates VAD relative to HOME. Copy the explicitly verified
        # optional model into this private home instead of granting it access to
        # an ambient user model directory.
        vad_home = run_root / "whisper-models"; vad_home.mkdir()
        vad_copy = vad_home / Path(identity["tools"]["vad_model"]["path"]).name
        shutil.copy2(identity["tools"]["vad_model"]["path"], vad_copy)
        if _sha(vad_copy) != identity["tools"]["vad_model"]["sha256"]:
            raise StageAError("Stage A VAD copy verification failed")
    log = run_root / "worker.log"
    started = time.monotonic()
    process: subprocess.Popen[bytes] | None = None
    try:
        with log.open("wb") as stream:
            process = subprocess.Popen([identity["runtime"]["worker"], "--stage-a-request", str(request_path)],
                                       cwd=run_root, env=environment, stdin=subprocess.DEVNULL, stdout=stream,
                                       stderr=subprocess.STDOUT, start_new_session=True)
            while process.poll() is None:
                if cancelled and cancelled():
                    raise StageACancelled("VideoText Stage A transcription cancelled")
                if time.monotonic() - started > timeout_seconds:
                    raise StageAError("VideoText Stage A transcription timed out")
                time.sleep(0.05)
    finally:
        if process is not None and process.poll() is None:
            _stop(process)
    if process is None or process.returncode:
        raise StageAError("VideoText Stage A transcription failed; see owned worker.log")
    markers = [line[len(RESULT_PREFIX):] for line in log.read_text(encoding="utf-8", errors="replace").splitlines() if line.startswith(RESULT_PREFIX)]
    if len(markers) != 1:
        raise StageAError("VideoText Stage A result marker is missing or ambiguous")
    try:
        marker = json.loads(markers[0])
    except json.JSONDecodeError as error:
        raise StageAError("VideoText Stage A result marker is invalid") from error
    expected = {"schema_version": "1.0", "component": "videotext", "capability": "stage_a_transcript",
                "review_checkpoint": "SOURCE_TRANSCRIPT", "semantic_authority": "MACHINE_UNVERIFIED"}
    if any(marker.get(key) != value for key, value in expected.items()):
        raise StageAError("VideoText Stage A result contract is invalid")
    locations = {"srt": "srt_path", "transcript": "transcript_path", "whisper_json": "whisper_json_path",
                 "manifest": "manifest_path", "quality": "quality_path", "review_tasks": "review_tasks_path"}
    artifacts: dict[str, dict[str, str]] = {}
    for name, field in locations.items():
        path = _inside(Path(marker.get(field, "")), run_root)
        if path.is_symlink() or not path.is_file() or not path.stat().st_size:
            raise StageAError(f"VideoText Stage A {name} artifact is unavailable")
        artifacts[name] = {"path": str(path), "sha256": _sha(path)}
    cue_count = _validate_srt(Path(artifacts["srt"]["path"]))
    result = {"schema_version": "1.0", "state": "REVIEW_REQUIRED", "cache_state": "COLD",
              "review_checkpoint": "SOURCE_TRANSCRIPT", "semantic_authority": "MACHINE_UNVERIFIED",
              "cue_count": cue_count, "cache_key": key, "runtime": identity["runtime"],
              "source_sha256": _sha(source), "artifacts": artifacts, "log": str(log)}
    cache.parent.mkdir()
    cache.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return result
