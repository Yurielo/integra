"""Local, copy-on-write media transcription and provisional knowledge workflow."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import signal
import uuid
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .identity import derive_imported_id
from .onedrive import build_onedrive_package
from .protocol import canonical_json, content_sha256
from .publishing import sha256_bytes, validate_package
from .seminartext_runtime import generate_topics
from .word_timeline_runtime import generate_word_timeline
from .videotext_runtime import preflight as videotext_translation_preflight, translate as translate_videotext
from . import seminartext_asr_runtime as asr
from . import videotext_media_runtime as videotext_media
from . import asr_reuse


class _RunCancelled(Exception):
    """Internal control-signal for user cancellation."""

SUPPORTED = {".aac", ".aif", ".aiff", ".flac", ".m4a", ".m4v", ".mkv", ".mov", ".mp3", ".mp4", ".ogg", ".wav", ".webm"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # The bridge and its worker can update the same record concurrently.  A
    # per-write name keeps one writer from replacing another writer's staging
    # file before either atomic rename occurs.
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_bytes(canonical_json(value) + b"\n")
    os.replace(temporary, path)


def _run_path(project_dir: Path, run_id: str) -> Path:
    token = str(uuid.UUID(run_id.removeprefix("urn:integra:run:")))
    path = project_dir / "runs" / f"{token}.json"
    if path.is_symlink() or not path.is_file():
        raise ValueError("run record is not available")
    return path


def _is_run_cancelled(project_dir: Path, run_id: str | None) -> bool:
    if not run_id:
        return False
    try:
        path = _run_path(project_dir, run_id)
        if path.with_suffix(".cancel").exists():
            return True
        record = json.loads(path.read_bytes())
    except Exception:
        return False
    return record.get("state") == "CANCELLED"


def build_asr_diagnostics(provenance: dict[str, Any], recognition_mode: str,
                          source_speech_language: str) -> dict[str, Any]:
    """Build the persisted, Integra-owned ASR diagnostic contract."""
    if not isinstance(provenance, dict):
        raise ValueError("ASR quality diagnostics are unavailable")
    quality = provenance.get("quality_diagnostics")
    if not isinstance(quality, dict):
        raise ValueError("ASR quality diagnostics are unavailable")
    status = quality.get("status")
    suspicious = quality.get("suspicious_chunks")
    retries = quality.get("protective_retry_count")
    recovered = quality.get("recovered_after_retry_count")
    if (status not in {"PASSED", "REQUIRES_ATTENTION"} or
        any(type(value) is not int or value < 0 for value in (suspicious, retries, recovered)) or
        retries != recovered + suspicious or
        (status == "PASSED") != (suspicious == 0)):
        raise ValueError("ASR quality diagnostics cannot be verified")
    executed_mode = provenance.get("mode")
    executed_language = provenance.get("executed_source_speech_language")
    language_mode = provenance.get("source_speech_language_mode")
    if executed_mode != recognition_mode or executed_language != source_speech_language or language_mode != "FIXED":
        raise ValueError("ASR diagnostics do not match the requested execution")
    return {
        "schema_version": "1.0",
        "status": status,
        "suspicious_chunks": suspicious,
        "protective_retry_count": retries,
        "recovered_after_retry_count": recovered,
        "recognition": {"requested_mode": recognition_mode, "executed_mode": executed_mode},
        "source_speech_language": {
            "requested": source_speech_language,
            "executed": executed_language,
            "mode": language_mode,
        },
    }


def _run_with_cancellation(
    command: list[str],
    project_dir: Path,
    run_id: str | None,
    *,
    check: bool = True,
) -> None:
    process = subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        while True:
            if _is_run_cancelled(project_dir, run_id):
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                raise _RunCancelled()
            code = process.poll()
            if code is None:
                time.sleep(0.1)
                continue
            if code != 0 and check:
                raise subprocess.CalledProcessError(returncode=code, cmd=command)
            return
    finally:
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            process.wait(timeout=1)


def _report_run_progress(
    project_dir: Path,
    run_id: str | None,
    stage: str | None,
    progress: int,
    message: str,
) -> None:
    if not run_id:
        return
    try:
        path = _run_path(project_dir, run_id)
        record = json.loads(path.read_bytes())
    except Exception:
        return
    if record.get("state") not in {"QUEUED", "RUNNING"}:
        return
    record["state"] = "RUNNING"
    if stage is not None:
        record["current_stage"] = stage
    record["progress"] = progress
    record["message"] = message
    record["updated_at"] = now()
    atomic_json(path, record)


def import_source(project_dir: Path, source: Path) -> dict[str, Any]:
    if source.is_symlink() or not source.is_file() or source.suffix.lower() not in SUPPORTED:
        raise ValueError("choose a supported regular audio or video file")
    source = source.resolve(strict=True)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    source_id = f"urn:integra:source:{uuid.uuid5(uuid.NAMESPACE_URL, digest)}"
    target_dir = project_dir / "sources" / digest
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / ("original" + source.suffix.lower())
    if not target.exists():
        temporary = target.with_name(target.name + ".tmp")
        shutil.copyfile(source, temporary)
        if hashlib.sha256(temporary.read_bytes()).hexdigest() != digest:
            temporary.unlink(missing_ok=True); raise ValueError("source copy verification failed")
        os.replace(temporary, target)
    record = {"schema_version":"1.0", "source_id":source_id, "display_name":source.name,
              "media_kind":"VIDEO" if source.suffix.lower() in {".m4v",".mkv",".mov",".mp4",".webm"} else "AUDIO",
              "content_sha256":digest, "owned_path":str(target), "imported_at":now(),
              "source_modified":False, "status":"IMPORTED"}
    atomic_json(target_dir / "source.json", record)
    return record


def _executable(env_name: str, command: str) -> str | None:
    configured = os.environ.get(env_name)
    candidates = [configured] if configured else []
    discovered = shutil.which(command)
    if discovered: candidates.append(discovered)
    candidates.extend(f"{prefix}/{command}" for prefix in ("/opt/homebrew/bin", "/usr/local/bin"))
    for value in candidates:
        if not value: continue
        try: path = Path(value).expanduser().resolve(strict=True)
        except OSError: continue
        if path.is_file() and os.access(path, os.X_OK): return str(path)
    return None


def _tools() -> tuple[str, str, str]:
    ffmpeg = ffmpeg_preflight()["ffmpeg"]
    whisper = _executable("INTEGRA_WHISPER_CLI", "whisper-cli")
    model = os.environ.get("INTEGRA_WHISPER_MODEL") or str(Path.home() / "whisper-models/ggml-large-v3.bin")
    if not whisper: raise ValueError("whisper-cli is not installed")
    model_path = Path(model)
    if model_path.is_symlink() or not model_path.is_file(): raise ValueError("Whisper model is missing; set INTEGRA_WHISPER_MODEL")
    return ffmpeg, whisper, str(model_path.resolve(strict=True))


def ffmpeg_preflight() -> dict[str, str]:
    """Verify the standalone local ffmpeg dependency used by owned media jobs."""
    ffmpeg = _executable("INTEGRA_FFMPEG", "ffmpeg")
    if not ffmpeg:
        raise ValueError("ffmpeg is not installed")
    return {"state": "READY", "ffmpeg": ffmpeg}


def preflight(*, hash_model: bool = True, source_speech_language: str = "ru") -> dict[str, Any]:
    ffmpeg, whisper, model = _tools()
    asr_runtime = asr.preflight(Path(ffmpeg), Path(whisper), Path(model),
                                source_speech_language=source_speech_language)
    result={"state":"READY", "ffmpeg":ffmpeg, "whisper_cli":whisper,
            "model":model, "supported_extensions":sorted(SUPPORTED), "asr_runtime":asr_runtime}
    if hash_model: result["model_sha256"]=hashlib.sha256(Path(model).read_bytes()).hexdigest()
    return result


def _parse_srt(value: str, source_id: str) -> list[dict[str, Any]]:
    def seconds(token: str) -> float:
        hours, minutes, tail = token.replace(",", ".").split(":")
        return round(int(hours)*3600 + int(minutes)*60 + float(tail), 3)
    segments = []
    blocks = re.split(r"\n\s*\n", value.strip()) if value.strip() else []
    for block in blocks:
        lines = block.splitlines()
        timing = next((line for line in lines if " --> " in line), None)
        if not timing: continue
        index = lines.index(timing); start, end = timing.split(" --> ")
        text = " ".join(lines[index+1:]).strip()
        if text:
            number = len(segments) + 1
            segments.append({"segment_id":f"{source_id}:segment:{number}", "start_seconds":seconds(start),
                             "end_seconds":seconds(end), "text":text,
                             "locator":f"media:{source_id}#t={seconds(start):.3f},{seconds(end):.3f}"})
    return segments


def _subtitle_filter(path: Path) -> str:
    """Escape an owned SRT path for ffmpeg's subtitles filter syntax."""
    value = str(path.resolve(strict=True))
    for token in ("\\", "'", ":", ",", "[", "]"):
        value = value.replace(token, "\\" + token)
    return "subtitles=filename='" + value + "':charenc=UTF-8"


def _provisional_topics(segments: list[dict[str, Any]], source_id: str) -> list[dict[str, Any]]:
    result = []
    for offset in range(0, len(segments), 6):
        group = segments[offset:offset+6]
        text = " ".join(item["text"] for item in group)
        words = re.findall(r"[\wА-Яа-яЁё-]+", text)
        label = " ".join(words[:7]) or f"Фрагмент {offset//6+1}"
        result.append({"topic_id":f"{source_id}:topic:{offset//6+1}", "label":label[:100],
                       "status":"REVIEW_REQUIRED", "semantic_authority":"PROVISIONAL",
                       "start_seconds":group[0]["start_seconds"], "end_seconds":group[-1]["end_seconds"],
                       "evidence_segment_ids":[item["segment_id"] for item in group],
                       "locator":f"media:{source_id}#t={group[0]['start_seconds']:.3f},{group[-1]['end_seconds']:.3f}"})
    return result


def _translation_provenance(
    value: dict[str, Any], *, source_id: str, transcript_path: Path,
    subtitles: Path, translation_path: Path, expected_source_language: str,
    expected_target_language: str, runtime: dict[str, Any],
) -> dict[str, Any]:
    """Validate the provider payload and retain only Integra-owned result facts."""
    if not isinstance(value, dict):
        raise ValueError("translation did not return a valid result")
    source_language = value.get("source_language")
    target_language = value.get("target_language")
    cues = value.get("cues")
    if (value.get("component") != "videotext" or value.get("capability") != "translation" or
        source_language != expected_source_language or target_language != expected_target_language or
        source_language == target_language or not isinstance(cues, list) or not cues):
        raise ValueError("translation result does not match the requested languages")
    source_cues = _parse_srt(subtitles.read_text(encoding="utf-8"), source_id)
    if len(cues) != len(source_cues):
        raise ValueError("translation result does not match the source transcript")
    def has_same_timestamp(value: Any, expected: float) -> bool:
        # JSON writers may expose harmless IEEE-754 round-off (for example,
        # 3.17 as 3.1699999999999999). Preserve the SRT millisecond contract.
        return (isinstance(value, (int, float)) and not isinstance(value, bool) and
                abs(float(value) - expected) <= 0.0005)

    for translated, original in zip(cues, source_cues):
        if (not isinstance(translated, dict) or not isinstance(translated.get("text"), str) or
            not translated["text"].strip() or translated.get("id") != original["segment_id"].rsplit(":", 1)[-1] or
            not has_same_timestamp(translated.get("start_seconds"), original["start_seconds"]) or
            not has_same_timestamp(translated.get("end_seconds"), original["end_seconds"])):
            raise ValueError("translation timing does not match the source transcript")
    if all(translated["text"].strip() == original["text"].strip()
           for translated, original in zip(cues, source_cues)):
        raise ValueError("translation result duplicates the source transcript")
    if value.get("model") != runtime["model"]:
        raise ValueError("translation runtime did not execute the selected model")
    return {
        "schema_version": "1.0",
        "status": "COMPLETED",
        "source_id": source_id,
        "source_transcript_sha256": hashlib.sha256(transcript_path.read_bytes()).hexdigest(),
        "source_subtitles_sha256": hashlib.sha256(subtitles.read_bytes()).hexdigest(),
        "source_language": source_language,
        "target_language": target_language,
        "translated_cue_count": len(cues),
        "output_sha256": hashlib.sha256(translation_path.read_bytes()).hexdigest(),
        "semantic_status": "MACHINE_TRANSLATION_REVIEW_REQUIRED",
        "runtime": {
            "component": "videotext",
            "commit_sha": runtime["commit_sha"],
            "adapter_sha256": runtime["adapter_sha256"],
            "model": runtime["model"],
        },
    }


def run_job(project_dir: Path, job_id: str) -> dict[str, Any]:
    jobs_path = project_dir / "jobs.json"
    jobs = json.loads(jobs_path.read_bytes())
    job = next(item for item in jobs["jobs"] if item["job_id"] == job_id)
    def checkpoint(state: str, progress: int, message: str, *, run_stage: Optional[str] = None) -> None:
        job.update(state=state, progress=progress, message=message, updated_at=now(), worker_pid=os.getpid())
        atomic_json(jobs_path, jobs)
        _report_run_progress(project_dir, job.get("run_id"), run_stage, progress, message)
        if _is_run_cancelled(project_dir, job.get("run_id")):
            raise _RunCancelled()
    try:
        requested=job.get("requested_outputs")
        legacy_semantics=requested is None
        requested_outputs=set(requested or {"transcript", "subtitles"})
        checkpoint("RUNNING", 5, "Preparing audio", run_stage="media_preparation")
        ffmpeg=ffmpeg_preflight()["ffmpeg"]; source = Path(job["owned_path"])
        work = project_dir / "artifacts" / job_id.removeprefix("urn:integra:job:"); work.mkdir(parents=True, exist_ok=True)
        outputs: dict[str, str] = {}
        for capability, operation, filename in (("audio_analysis", "audio_analysis", "audio_analysis.json"),
                                                 ("speed_video", "speed", "speed_1_25.mp4")):
            if capability in requested_outputs:
                checkpoint("RUNNING", 10, "VideoText: " + capability, run_stage=capability)
                target = work / (uuid.uuid4().hex + "_" + filename)
                options = {"speed_factor": 1.25} if operation == "speed" else {}
                evidence = videotext_media.process(source, target, operation,
                    cancelled=lambda: _is_run_cancelled(project_dir, job.get("run_id")), **options)
                atomic_json(work / (capability + "_provenance.json"), evidence)
                outputs[capability] = str(target)
                outputs[capability + "_record"] = str(work / (capability + "_provenance.json"))
        if "enhance_audio" in requested_outputs:
            checkpoint("RUNNING", 15, "Enhancing audio locally", run_stage="audio_enhancement")
            enhanced = work / "enhanced_audio.m4a"
            _run_with_cancellation(
                [ffmpeg, "-nostdin", "-y", "-i", str(source), "-vn",
                 "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-c:a", "aac", "-b:a", "192k", str(enhanced)],
                project_dir, job.get("run_id"), check=True,
            )
            if enhanced.is_symlink() or not enhanced.is_file() or enhanced.stat().st_size == 0:
                raise ValueError("audio enhancement produced no audio output")
            enhancement_record = {
                "schema_version": "1.0", "source_id": job["source_id"],
                "source_sha256": job["source_sha256"], "engine": "ffmpeg",
                "filter": "loudnorm=I=-16:TP=-1.5:LRA=11", "output": str(enhanced),
            }
            atomic_json(work / "audio_enhancement.json", enhancement_record)
            outputs["enhanced_audio"] = str(enhanced)
            outputs["audio_enhancement_record"] = str(work / "audio_enhancement.json")
        needs_transcript = legacy_semantics or bool(requested_outputs & {"transcript", "subtitles", "burn_subtitles", "word_timeline", "topics", "translation"})
        if not needs_transcript:
            job["outputs"] = outputs
            job.update(state="COMPLETED", progress=100, message="Requested media outputs are ready",
                       completed_at=now(), artifact_dir=str(work))
            atomic_json(jobs_path, jobs)
            return job
        _, whisper, model = _tools()
        recognition_mode = job.get("recognition_mode", "normal")
        source_speech_language = job.get("source_speech_language", "ru")
        checkpoint("RUNNING", 25, "Проверяю возможность повторного использования расшифровки", run_stage="transcript")
        recognized = asr_reuse.transcribe_or_reuse(project_dir, source, work, ffmpeg=Path(ffmpeg), whisper=Path(whisper), model=Path(model),
            expected_source_sha256=job["source_sha256"],
            cancelled=lambda: _is_run_cancelled(project_dir, job.get("run_id")),
            progress=lambda message: checkpoint("RUNNING", 25, message, run_stage="transcript"),
            recognition_mode=recognition_mode, source_speech_language=source_speech_language)
        if recognized["provenance"].get("mode") != recognition_mode:
            raise ValueError("ASR runtime executed a different recognition mode")
        if recognized["provenance"].get("executed_source_speech_language") != source_speech_language:
            raise ValueError("ASR runtime executed a different source-speech language")
        job["asr_reuse"] = recognized["reuse"]
        job["recognition"] = {"requested_mode": recognition_mode,
                              "executed_mode": recognized["provenance"]["mode"],
                              "runtime": {key: recognized["provenance"][key] for key in
                                          ("component", "commit_sha", "entrypoint_sha256", "whisper_sha256", "model_sha256")}}
        job["source_speech_language"] = {"requested": source_speech_language,
                                          "executed": recognized["provenance"]["executed_source_speech_language"],
                                          "mode": recognized["provenance"]["source_speech_language_mode"]}
        job["asr_diagnostics"] = build_asr_diagnostics(
            recognized["provenance"], recognition_mode, source_speech_language)
        subtitles = Path(recognized["srt"])
        segments = _parse_srt(subtitles.read_text(encoding="utf-8"), job["source_id"])
        if not segments: raise ValueError("transcription produced no timed speech segments")
        checkpoint("RUNNING", 80, "Saving timed transcript and subtitles", run_stage="subtitles")
        transcript = {"schema_version":"1.0", "source_id":job["source_id"], "assurance":"MACHINE_TRANSCRIPT_UNREVIEWED",
                      "model_sha256":recognized["provenance"]["model_sha256"], "segments":segments,
                      "asr_provenance": recognized["provenance"], "asr_reuse": recognized["reuse"]}
        transcript_text = "\n".join(segment["text"] for segment in segments)
        transcript_txt = work / "transcript.txt"
        transcript_txt.write_text((transcript_text + "\n") if transcript_text else "", encoding="utf-8")
        atomic_json(work / "transcript.json", transcript)
        outputs.update({"transcript":str(transcript_txt),"transcript_json":str(work/"transcript.json"),"subtitles":str(subtitles)})
        outputs.update({"transcript_cleaned":recognized["cleaned_txt"],
                        "transcript_quality_report":recognized["review_txt"],
                        "transcript_asr_record":recognized["record"]})
        job["outputs"] = outputs
        if requested and "translation" in requested_outputs:
            checkpoint("RUNNING", 84, "Перевожу расшифровку", run_stage="translation")
            translation_path = work / "translation.json"
            target_language = job.get("translation_target_language", "en")
            if target_language != "en":
                raise ValueError("translation target language is unsupported")
            translation_runtime = videotext_translation_preflight()
            translation = translate_videotext(
                subtitles, translation_path, target=target_language, runtime=translation_runtime)
            provenance = _translation_provenance(
                translation, source_id=job["source_id"], transcript_path=work / "transcript.json",
                subtitles=subtitles, translation_path=translation_path,
                expected_source_language=source_speech_language, expected_target_language=target_language,
                runtime=translation_runtime,
            )
            atomic_json(work / "translation_provenance.json", provenance)
            job["outputs"]["translation"] = str(translation_path)
            job["outputs"]["translation_provenance"] = str(work / "translation_provenance.json")
        if requested and requested_outputs & {"word_timeline", "topics"}:
            checkpoint("RUNNING", 85, "Aligning transcript words with WhisperX", run_stage="word_timeline")
            wav = work / "audio.wav"
            _run_with_cancellation([ffmpeg, "-nostdin", "-y", "-i", str(source), "-vn", "-ar", "16000",
                                    "-ac", "1", "-c:a", "pcm_s16le", str(wav)], project_dir, job.get("run_id"))
            timeline_path = work / "word_timeline.json"
            generate_word_timeline(wav, subtitles, timeline_path,
                                   diagnostic_context={"run_id": str(job.get("run_id", "")), "stage": "word_timeline"})
            job["outputs"]["word_timeline"] = str(timeline_path)
        if requested and "topics" in requested:
            checkpoint("RUNNING", 88, "Generating topic drafts with SeminarText", run_stage="topics")
            topics_path = work / "topics.json"
            generate_topics(subtitles, topics_path)
            job["outputs"]["topics"] = str(topics_path)
        if requested and "burn_subtitles" in requested:
            checkpoint("RUNNING", 90, "Burning subtitles into video", run_stage="burn_subtitles")
            burned = work / (uuid.uuid4().hex + "_subtitled.mp4")
            evidence = videotext_media.burn(source, subtitles, burned,
                cancelled=lambda: _is_run_cancelled(project_dir, job.get("run_id")))
            atomic_json(work / "burn_subtitles_provenance.json", evidence)
            job["outputs"]["burn_subtitles_record"] = str(work / "burn_subtitles_provenance.json")
            if burned.is_symlink() or not burned.is_file() or burned.stat().st_size == 0:
                raise ValueError("subtitle rendering produced no video output")
            job["outputs"]["burned_video"] = str(burned)
        # A transcript, a rendered subtitle file, or a Word Timeline is not a
        # semantic result.  Do not manufacture Topics, Knowledge, navigation,
        # or a publication package from heuristic grouping.  Those outputs are
        # emitted only by their explicitly selected real runtime paths above.
        job.update(state="COMPLETED", progress=100, message="Requested real outputs are ready", completed_at=now(),
                   artifact_dir=str(work), transcript_segments=len(segments))
        atomic_json(jobs_path, jobs); return job
    except Exception as error:
        if isinstance(error, (_RunCancelled, asr.ASRCancelled, videotext_media.MediaCancelled)) or _is_run_cancelled(project_dir, job.get("run_id")):
            job.update(state="CANCELLED", message="Cancelled by user", updated_at=now())
            atomic_json(jobs_path, jobs)
            return job
        if isinstance(error, asr.ASRQualityError):
            job["outputs"] = {"transcript_quality_report":error.artifacts["review_txt"],
                              "transcript_asr_record":error.artifacts["record"]}
            job["asr_diagnostics"] = build_asr_diagnostics(
                error.artifacts["provenance"],
                job.get("recognition_mode", "normal"),
                job.get("source_speech_language", "ru"),
            )
        job.update(state="FAILED", message=str(error)[:300], updated_at=now())
        atomic_json(jobs_path, jobs); raise


def build_project_package(project_dir: Path, job: dict[str, Any], transcript: dict[str, Any], topics: list[dict[str, Any]], knowledge: dict[str, Any], navigation: dict[str, Any]) -> Path:
    project = json.loads((project_dir / "project.json").read_bytes())
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", project["name"]).strip("-.")[:96] or "project"
    lines = [f"# {project['name']}", "", "> Machine transcript and semantic drafts. Review required.", ""]
    for segment in transcript["segments"]: lines += [f"- [{segment['start_seconds']:.3f}–{segment['end_seconds']:.3f}] {segment['text']}", f"  - `{segment['locator']}`"]
    files = {"00_START_HERE.md":("\n".join(lines)+"\n").encode(),
             "Transcript/transcript.json":canonical_json(transcript)+b"\n", "Topics/topics.json":canonical_json(topics)+b"\n",
             "Knowledge/provisional.json":canonical_json(knowledge)+b"\n", "_meta/integra_navigation.json":canonical_json(navigation)+b"\n"}
    inventory = [{"path":name,"size_bytes":len(payload),"sha256":sha256_bytes(payload),"ownership_class":"MANAGED_GENERATED"} for name,payload in sorted(files.items())]
    created = now(); source_hash = content_sha256({"source_id":job["source_id"],"source_sha256":job["source_sha256"]})
    knowledge_hash = content_sha256(knowledge); navigation_hash = content_sha256(navigation)
    identity = {"project_id":project["project_id"],"project_slug":slug,"created_at":created,"source_manifest_sha256":source_hash,
                "knowledge_view_id":f"{job['source_id']}:knowledge-view","knowledge_view_sha256":knowledge_hash,
                "navigation_id":f"{job['source_id']}:navigation","navigation_sha256":navigation_hash,"files":inventory}
    version = content_sha256(identity)
    manifest = {"schema_version":"1.0","artifact_type":"integra.obsidian_package","package_id":derive_imported_id("artifact","integra.obsidian",project["project_id"],version),
                "version_sha256":version,"project_id":project["project_id"],"project_slug":slug,"created_at":created,"source_manifest_sha256":source_hash,
                "knowledge":{"view_id":identity["knowledge_view_id"],"record_sha256":knowledge_hash},"navigation":{"navigation_id":identity["navigation_id"],"record_sha256":navigation_hash},
                "files":inventory,"semantic_authority":"DERIVED_SOURCE_TRUTH_PRESERVED","source_artifacts_modified":False}
    validate_package(manifest, files)
    root = project_dir / "packages" / version; payload_root = root / "files"; payload_root.mkdir(parents=True, exist_ok=True)
    for name,payload in files.items():
        path=payload_root/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(payload)
    atomic_json(root/"package.json",manifest)
    one_manifest, one_files = build_onedrive_package(manifest, files, created_at=created)
    one_root = project_dir / "packages" / (one_manifest["version_sha256"]+"-onedrive"); (one_root/"files").mkdir(parents=True,exist_ok=True)
    for name,payload in one_files.items():
        path=one_root/"files"/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(payload)
    atomic_json(one_root/"package.json",one_manifest)
    atomic_json(root/"onedrive_package.json",{"package_dir":str(one_root)})
    return root
