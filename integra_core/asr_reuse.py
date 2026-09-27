"""Project-local reuse of complete, hash-bound machine ASR artifacts."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
import sys
import uuid

from . import seminartext_asr_runtime as asr

FILE_KEYS = ("raw_txt", "cleaned_txt", "review_txt", "source_srt", "srt",
             "transcript_json", "record", "log")
CACHE_SCHEMA = "integra.verified-asr-reuse.v1"


def _hash(path: Path, cancelled=None) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            _check_cancelled(cancelled)
            value.update(block)
    return value.hexdigest()


def _check_cancelled(cancelled):
    if cancelled and cancelled():
        raise asr.ASRCancelled("Transcription reuse cancelled")


def _canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _owned_file(root: Path, path: Path, *, directory=False) -> Path:
    root_absolute, root_resolved = Path(os.path.abspath(root)), root.resolve(strict=True)
    path = Path(os.path.abspath(path))
    try:
        result = path.resolve(strict=True)
        result.relative_to(root_resolved)
        for parent in (path, *path.parents):
            if parent in {root_absolute, root_resolved}:
                break
            if parent.is_symlink():
                raise ValueError("ASR cache cannot reference symlinks")
    except (OSError, RuntimeError, ValueError) as error:
        raise ValueError("ASR cache artifact is outside the owned project or unsafe") from error
    if not (result.is_dir() if directory else result.is_file()):
        raise ValueError("ASR cache artifact is unavailable")
    return result


def _binding(source: Path, runtime: dict, cancelled=None) -> dict:
    path_fields = ("entrypoint", "ffmpeg", "ffprobe", "whisper", "model", "vad_model")
    configuration = {key: value for key, value in runtime.items()
                     if key not in {*path_fields, "state", "subtitle_runtime"}}
    configuration["subtitle_runtime"] = {key: value for key, value in runtime["subtitle_runtime"].items()
                                         if key not in {"worker", "state"}}
    return {"schema": CACHE_SCHEMA, "source_sha256": _hash(source, cancelled),
            "configuration": configuration,
            "runtime_bytes": {key: _hash(Path(runtime[key]), cancelled) for key in path_fields},
            "adapter_sha256": _hash(Path(asr.__file__), cancelled),
            "cache_adapter_sha256": _hash(Path(__file__), cancelled),
            "python_sha256": _hash(Path(sys.executable), cancelled), "python_version": sys.version}


def _load(root: Path, manifest_path: Path, binding: dict, cancelled=None) -> dict:
    manifest_path = _owned_file(root, manifest_path)
    manifest = json.loads(manifest_path.read_bytes())
    if (not isinstance(manifest, dict) or manifest.get("schema") != CACHE_SCHEMA or manifest.get("state") != "VERIFIED_COMPLETE"
            or manifest.get("binding") != binding or not isinstance(manifest.get("files"), dict)
            or set(manifest["files"]) != set(FILE_KEYS)):
        raise ValueError("ASR cache entry is incomplete or stale")
    recognized = {}
    for key, entry in manifest["files"].items():
        if not isinstance(entry, dict):
            raise ValueError("ASR cached file record is malformed")
        relative = Path(entry["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("ASR cache locator is unsafe")
        path = _owned_file(root, root / relative)
        if path.stat().st_size != entry["size"] or _hash(path, cancelled) != entry["sha256"]:
            raise ValueError("ASR cached artifact changed")
        recognized[key] = str(path)
    provenance = json.loads(Path(recognized["record"]).read_bytes())
    if (not isinstance(provenance, dict) or type(provenance.get("suspicious_chunks")) is not int
            or provenance["suspicious_chunks"] != 0 or provenance.get("source_sha256") != binding["source_sha256"]
            or provenance.get("model_sha256") != binding["runtime_bytes"]["model"]
            or provenance.get("whisper_sha256") != binding["runtime_bytes"]["whisper"]
            or provenance.get("ffmpeg_sha256") != binding["runtime_bytes"]["ffmpeg"]):
        raise ValueError("ASR cache has no matching successful quality evidence")
    for name, expected in binding["configuration"].items():
        if name == "subtitle_runtime":
            actual = provenance.get(name, {})
            if not isinstance(actual, dict) or any(actual.get(key) != value for key, value in expected.items()):
                raise ValueError("ASR cached subtitle runtime identity differs")
        elif provenance.get(name) != expected:
            raise ValueError("ASR cached configuration differs")
    if not isinstance(provenance.get("artifact_sha256"), dict):
        raise ValueError("ASR cached artifact inventory is missing")
    for key in ("raw_txt", "cleaned_txt", "review_txt", "source_srt", "srt", "transcript_json"):
        if provenance.get("artifact_sha256", {}).get(key) != manifest["files"][key]["sha256"]:
            raise ValueError("ASR cache provenance differs from artifact bytes")
    recognized["provenance"] = provenance
    return recognized


def transcribe_or_reuse(project_dir: Path, source: Path, work: Path, *, ffmpeg: Path,
                       whisper: Path, model: Path, expected_source_sha256: str,
                       cancelled=None, progress=None, recognition_mode: str = "normal",
                       source_speech_language: str = "ru") -> dict:
    project_dir = Path(project_dir)
    if project_dir.is_symlink():
        raise ValueError("ASR cache project root is unsafe")
    source = _owned_file(project_dir, Path(source))
    work = _owned_file(project_dir, Path(work), directory=True)
    _check_cancelled(cancelled)
    if progress:
        progress("Проверяю сохранённую расшифровку и версии компонентов")
    runtime = asr.preflight(ffmpeg, whisper, model, recognition_mode=recognition_mode,
                            source_speech_language=source_speech_language)
    binding = _binding(source, runtime, cancelled)
    if binding["source_sha256"] != expected_source_sha256:
        raise ValueError("Owned ASR source changed after import")
    key = hashlib.sha256(_canonical(binding)).hexdigest()
    cache = project_dir / "asr-cache-v1"
    if cache.is_symlink():
        raise ValueError("ASR cache directory is unsafe")
    cache.mkdir(exist_ok=True)
    lock_path = cache / (key + ".lock")
    if lock_path.is_symlink():
        raise ValueError("ASR cache lock is unsafe")
    with lock_path.open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError("Matching project transcription is already being processed") from error
        for candidate in sorted(cache.glob(key + "-*.json")):
            _check_cancelled(cancelled)
            try:
                recognized = _load(project_dir, candidate, binding, cancelled)
            except asr.ASRCancelled:
                raise
            except (OSError, ValueError, TypeError, KeyError):
                # Never repair, overwrite, or delete untrusted/old artifacts.
                continue
            _check_cancelled(cancelled)
            if _binding(source, asr.preflight(ffmpeg, whisper, model, recognition_mode=recognition_mode,
                                              source_speech_language=source_speech_language), cancelled) != binding:
                raise ValueError("ASR source or runtime changed while validating reuse")
            if progress:
                progress("Использую проверенную сохранённую расшифровку — повторное ASR не требуется")
            _check_cancelled(cancelled)
            recognized["reuse"] = {"state": "REUSED", "cache_key": key, "manifest_path": str(candidate.resolve())}
            return recognized
        recognized = asr.transcribe(source, work, ffmpeg=ffmpeg, whisper=whisper, model=model,
                                   cancelled=cancelled, progress=progress, recognition_mode=recognition_mode,
                                   source_speech_language=source_speech_language)
        _check_cancelled(cancelled)
        # Detect tool, model, source or configuration drift during execution.
        if _binding(source, asr.preflight(ffmpeg, whisper, model, recognition_mode=recognition_mode,
                                          source_speech_language=source_speech_language), cancelled) != binding:
            raise ValueError("ASR source or runtime changed during transcription; cache was not published")
        files = {}
        for name in FILE_KEYS:
            artifact = _owned_file(project_dir, Path(recognized[name]))
            files[name] = {"path": str(artifact.relative_to(project_dir.resolve())),
                           "size": artifact.stat().st_size, "sha256": _hash(artifact, cancelled)}
        manifest = {"schema": CACHE_SCHEMA, "state": "VERIFIED_COMPLETE", "binding": binding,
                    "assurance": "MACHINE_TRANSCRIPT_UNREVIEWED", "files": files}
        target = cache / (key + "-" + uuid.uuid4().hex + ".json")
        staged = target.with_suffix(".pending")
        try:
            staged.write_bytes(_canonical(manifest) + b"\n")
            # Exercise the same fail-closed verifier before exclusive publication.
            _load(project_dir, staged, binding, cancelled)
            _check_cancelled(cancelled)
            os.link(staged, target)
        finally:
            staged.unlink(missing_ok=True)
        recognized["reuse"] = {"state": "CREATED", "cache_key": key, "manifest_path": str(target.resolve())}
        return recognized
