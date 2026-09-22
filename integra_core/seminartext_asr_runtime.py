"""Owned-process adapter to the exact SeminarText transcription CLI.

Chunking, VAD, decoding retries and text cleaning remain in SeminarText. Its
cleaned text is a derivative; raw text and source SRT are never replaced by it.
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
import sys
import threading
import time
from typing import Callable, Any

from .seminartext_runtime import PINNED_COMMIT
from . import videotext_subtitles

# Active CLI bytes from the final accepted SeminarText pin. Historical evidence
# retains its old hashes; this fail-closed runtime check does not.
ENTRYPOINT_SHA256 = "f7f411bf106341ae970bc40d759e1e3c964273b977bdb12d0f1840e629def13a"
VERSION_SHA256 = "e1d49c569ae09b2ede16e2d83820a3809b35eb6c44c13ba9b5330598d6b8f43c"
VAD_SHA256 = "29940d98d42b91fbd05ce489f3ecf7c72f0a42f027e4875919a28fb4c04ea2cf"
BUNDLED_RUNTIME_ROOT = Path(__file__).resolve().parents[1] / "runtime" / "seminartext"
OWNED_CHECKOUT = Path(__file__).resolve().parents[1] / ".runtime-components" / "seminartext-pinned"


class ASRError(ValueError):
    """The verified production adapter could not produce a usable result."""


class ASRCancelled(ASRError):
    pass


class ASRQualityError(ASRError):
    def __init__(self, message: str, artifacts: dict[str, Any]):
        super().__init__(message)
        self.artifacts = artifacts


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file(path: Path, label: str, executable: bool = False) -> Path:
    try:
        result = Path(path).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise ASRError(f"{label} is unavailable") from error
    if not result.is_file() or (executable and not os.access(result, os.X_OK)):
        raise ASRError(f"{label} is unavailable")
    return result


def _runtime() -> Path:
    configured = os.environ.get("INTEGRA_SEMINARTEXT_CHECKOUT")
    root = Path(configured).expanduser() if configured else (
        BUNDLED_RUNTIME_ROOT if BUNDLED_RUNTIME_ROOT.is_dir() else OWNED_CHECKOUT)
    if root.is_symlink() or not root.is_dir():
        raise ASRError("Pinned SeminarText ASR runtime is unavailable")
    if configured or root == OWNED_CHECKOUT:
        try:
            commit = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                                    capture_output=True, text=True, check=True, timeout=5).stdout.strip()
        except (OSError, subprocess.SubprocessError) as error:
            raise ASRError("SeminarText ASR checkout cannot be verified") from error
        if commit != PINNED_COMMIT:
            raise ASRError("SeminarText ASR checkout differs from pinned commit")
    for name, expected in (("seminartext", ENTRYPOINT_SHA256), ("SEMINARTEXT_VERSION", VERSION_SHA256)):
        path = root / name
        if path.is_symlink() or not path.is_file() or _sha(path) != expected:
            raise ASRError("SeminarText ASR runtime differs from pinned bytes")
    return root.resolve()


def preflight(ffmpeg: Path, whisper: Path, model: Path, vad_model: Path | None = None) -> dict[str, Any]:
    root = _runtime()
    ffmpeg = _file(ffmpeg, "ffmpeg", True)
    whisper = _file(whisper, "whisper-cli", True)
    model = _file(model, "Whisper model")
    configured_vad = os.environ.get("INTEGRA_VAD_MODEL")
    vad_path = vad_model or (Path(configured_vad) if configured_vad else
                             Path.home() / "whisper-models" / "ggml-silero-v5.1.2.bin")
    vad = _file(vad_path, "Silero VAD model")
    if _sha(vad) != VAD_SHA256:
        raise ASRError("Silero VAD model differs from pinned v5.1.2 bytes")
    try:
        subtitle_runtime = videotext_subtitles.preflight()
    except ValueError as error:
        raise ASRError(str(error)) from error
    configured_probe = os.environ.get("INTEGRA_FFPROBE")
    probe = Path(configured_probe) if configured_probe else ffmpeg.parent / "ffprobe"
    if not configured_probe and not probe.is_file():
        probe = Path(shutil.which("ffprobe") or "/opt/homebrew/bin/ffprobe")
    probe = _file(probe, "ffprobe", True)
    return {"schema_version": "1.0", "state": "READY", "component": "seminartext", "commit_sha": PINNED_COMMIT,
            "entrypoint": str(root / "seminartext"), "entrypoint_sha256": ENTRYPOINT_SHA256,
            "version_sha256": VERSION_SHA256, "ffmpeg": str(ffmpeg), "ffprobe": str(probe),
            "whisper": str(whisper), "model": str(model), "vad_model": str(vad),
            "vad_sha256": VAD_SHA256, "chunk_seconds": 300,
            "language": "ru", "mode": "normal", "cleaned_text_authority": "DERIVED_UNVERIFIED",
            "subtitle_runtime": subtitle_runtime}


def _stop(process: subprocess.Popen) -> None:
    # Capture descendants before terminating the CLI session. A recognizer can
    # create its own session; after its direct parent exits it would otherwise
    # be reparented and no longer safely attributable to this app-owned Popen.
    from .shutdown_runtime import terminate_owned_subprocess_tree
    terminate_owned_subprocess_tree(process.pid, timeout=4)
    for sig, timeout in ((signal.SIGTERM, 2), (signal.SIGKILL, 2)):
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            break
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            continue
        # The shell may exit before its descendants; kill the owned group too.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        break
    process.wait(timeout=5)


def _number_srt(source: Path, target: Path) -> dict:
    """Keep source SRT intact; delegate serialization/validation to VideoText."""
    try:
        return videotext_subtitles.normalize(source, target)
    except ValueError as error:
        raise ASRError(str(error)) from error


def transcribe(source: Path, work: Path, *, ffmpeg: Path, whisper: Path, model: Path,
               vad_model: Path | None = None, cancelled: Callable[[], bool] | None = None,
               progress: Callable[[str], None] | None = None) -> dict[str, Any]:
    if threading.current_thread() is not threading.main_thread():
        raise ASRError("SeminarText ASR must run in its owned worker main thread")
    identity = preflight(ffmpeg, whisper, model, vad_model)
    source = _file(source, "ASR source")
    work = Path(work).resolve(strict=True)
    if not work.is_dir():
        raise ASRError("ASR work directory is unavailable")
    if cancelled and cancelled():
        raise ASRCancelled("Transcription cancelled")
    owned = work / "seminartext-asr"
    owned.mkdir()  # Never reuse or overwrite a previous component run.
    project = owned / "project"
    project.mkdir()
    (project / "sources.json").write_text(json.dumps({"videos": [{
        "source_id": "video_001", "type": "local", "file": str(source),
        "order": 1, "title": "Integra source"}]}), encoding="utf-8")
    bindir = owned / "bin"
    bindir.mkdir()
    for name, target in (("ffmpeg", identity["ffmpeg"]), ("ffprobe", identity["ffprobe"]),
                         ("whisper-cli", identity["whisper"]), ("python3", sys.executable)):
        (bindir / name).symlink_to(target)
    # Explicit safe environment: no inherited SeminarText overrides or shell hooks.
    env = {"PATH": str(bindir) + ":/usr/bin:/bin:/usr/sbin:/sbin", "HOME": str(Path.home()),
           "LANG": "en_US.UTF-8", "LC_ALL": "en_US.UTF-8", "PYTHONDONTWRITEBYTECODE": "1",
           "SEMINARTEXT_OUTPUT": str(owned / "output"), "SEMINARTEXT_MODEL": identity["model"],
           "SEMINARTEXT_VAD_MODEL": identity["vad_model"], "SEMINARTEXT_CHUNK_SECONDS": "300"}
    log = owned / "adapter.log"
    if progress:
        progress("Распознавание SeminarText: независимые фрагменты, VAD и проверка повторов")
    terminated = False

    def requested_stop(signum: int, frame: Any) -> None:
        nonlocal terminated
        # Do not raise during Popen: the child must first be assigned so the
        # finally block can always reap it, including a signal during launch.
        terminated = True

    previous_handler = signal.signal(signal.SIGTERM, requested_stop)
    process = None
    try:
        with log.open("wb") as stream:
            if terminated:
                raise ASRCancelled("Transcription cancelled")
            process = subprocess.Popen(["/bin/bash", identity["entrypoint"], "project-transcribe",
                                        str(project), "--only", "video_001"],
                                       cwd=owned, env=env, stdin=subprocess.DEVNULL,
                                       stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
            last_chunk = ""
            while process.poll() is None:
                if terminated or (cancelled and cancelled()):
                    raise ASRCancelled("Transcription cancelled")
                if progress:
                    # Only fixed source-stage metadata escapes the private log.
                    with log.open("rb") as observed:
                        observed.seek(max(0, log.stat().st_size - 16384))
                        tail = observed.read().decode("utf-8", errors="replace")
                    chunks = re.findall(r"^--- Фрагмент (\d+) из (\d+) ---$", tail, re.M)
                    if chunks:
                        chunk = f"Распознавание SeminarText: фрагмент {chunks[-1][0]} из {chunks[-1][1]}"
                        if chunk != last_chunk:
                            progress(chunk)
                            last_chunk = chunk
                time.sleep(0.1)
    finally:
        try:
            if process is not None:
                # A failed shell can exit before descendants. Its owned session
                # must be cleaned regardless of the leader's return status.
                _stop(process)
        finally:
            signal.signal(signal.SIGTERM, previous_handler)
    if terminated or (cancelled and cancelled()):
        raise ASRCancelled("Transcription cancelled")
    if process.returncode:
        raise ASRError(f"SeminarText transcription failed (exit {process.returncode}); see owned adapter.log")
    folder = project / "transcript" / "video_001"
    artifacts = {"raw_txt": str(folder / "transcript.txt"),
                 "cleaned_txt": str(folder / "transcript_clean.txt"),
                 "review_txt": str(folder / "transcript_review.txt"),
                 "source_srt": str(folder / "transcript.srt"),
                 "srt": str(owned / "transcript.srt"),
                 "transcript_json": str(project / "transcript" / "video_001.json"),
                 "log": str(log), "record": str(owned / "provenance.json"), "provenance": identity}
    for key in ("raw_txt", "cleaned_txt", "review_txt", "source_srt", "transcript_json"):
        path = Path(artifacts[key])
        if path.is_symlink() or not path.is_file() or not path.stat().st_size:
            raise ASRError(f"SeminarText did not produce complete {key}")
    subtitle_record = _number_srt(Path(artifacts["source_srt"]), Path(artifacts["srt"]))
    info = folder / "info.txt"
    if info.is_symlink() or not info.is_file() or not (folder / ".seminartext_complete").is_file():
        raise ASRError("SeminarText completion evidence is missing")
    matches = re.findall(r"^Подозрительных фрагментов: (\d+)$", info.read_text(encoding="utf-8"), re.M)
    if len(matches) != 1:
        raise ASRError("SeminarText quality result cannot be verified")
    identity["suspicious_chunks"] = int(matches[0])
    identity["model_sha256"] = _sha(Path(identity["model"]))
    identity["source_sha256"] = _sha(source)
    identity["whisper_sha256"] = _sha(Path(identity["whisper"]))
    identity["ffmpeg_sha256"] = _sha(Path(identity["ffmpeg"]))
    identity["artifact_sha256"] = {key: _sha(Path(artifacts[key])) for key in (
        "raw_txt", "cleaned_txt", "review_txt", "source_srt", "srt", "transcript_json")}
    identity["srt_adaptation"] = "VIDEOTEXT_SRT_SERVICE"
    identity["subtitle_result"] = subtitle_record
    (owned / "provenance.json").write_text(json.dumps(identity, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if int(matches[0]):
        raise ASRQualityError("SeminarText: после повторного распознавания остались подозрительные фрагменты; требуется проверка аудио", artifacts)
    return artifacts
