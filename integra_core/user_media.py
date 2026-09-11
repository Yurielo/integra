"""Local, copy-on-write media transcription and provisional knowledge workflow."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .identity import derive_imported_id
from .onedrive import build_onedrive_package
from .protocol import canonical_json, content_sha256
from .publishing import sha256_bytes, validate_package


class _RunCancelled(Exception):
    """Internal control-signal for user cancellation."""

SUPPORTED = {".aac", ".aif", ".aiff", ".flac", ".m4a", ".m4v", ".mkv", ".mov", ".mp3", ".mp4", ".ogg", ".wav", ".webm"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
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
        record = json.loads(_run_path(project_dir, run_id).read_bytes())
    except Exception:
        return False
    return record.get("state") == "CANCELLED"


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
    ffmpeg = _executable("INTEGRA_FFMPEG", "ffmpeg")
    whisper = _executable("INTEGRA_WHISPER_CLI", "whisper-cli")
    model = os.environ.get("INTEGRA_WHISPER_MODEL") or str(Path.home() / "whisper-models/ggml-large-v3.bin")
    if not ffmpeg: raise ValueError("ffmpeg is not installed")
    if not whisper: raise ValueError("whisper-cli is not installed")
    model_path = Path(model)
    if model_path.is_symlink() or not model_path.is_file(): raise ValueError("Whisper model is missing; set INTEGRA_WHISPER_MODEL")
    return ffmpeg, whisper, str(model_path.resolve(strict=True))


def preflight(*, hash_model: bool = True) -> dict[str, Any]:
    ffmpeg, whisper, model = _tools()
    result={"state":"READY", "ffmpeg":ffmpeg, "whisper_cli":whisper,
            "model":model, "supported_extensions":sorted(SUPPORTED)}
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
        checkpoint("RUNNING", 5, "Preparing audio", run_stage="media_preparation")
        ffmpeg, whisper, model = _tools(); source = Path(job["owned_path"])
        work = project_dir / "artifacts" / job_id.removeprefix("urn:integra:job:"); work.mkdir(parents=True, exist_ok=True)
        wav = work / "audio.wav"
        subprocess.run([ffmpeg, "-nostdin", "-y", "-i", str(source), "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(wav)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        checkpoint("RUNNING", 25, "Transcribing locally", run_stage="transcript")
        output = work / "transcript"
        subprocess.run([whisper, "-m", model, "-f", str(wav), "-l", "auto", "-osrt", "-of", str(output), "-np"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        segments = _parse_srt((output.with_suffix(".srt")).read_text(errors="replace"), job["source_id"])
        if not segments: raise ValueError("transcription produced no timed speech segments")
        requested=job.get("requested_outputs")
        legacy_semantics=requested is None
        checkpoint("RUNNING", 80, "Saving timed transcript and subtitles", run_stage="subtitles")
        transcript = {"schema_version":"1.0", "source_id":job["source_id"], "assurance":"MACHINE_TRANSCRIPT_UNREVIEWED",
                      "model_sha256":hashlib.sha256(Path(model).read_bytes()).hexdigest(), "segments":segments}
        transcript_text = "\n".join(segment["text"] for segment in segments)
        transcript_txt = work / "transcript.txt"
        transcript_txt.write_text((transcript_text + "\n") if transcript_text else "", encoding="utf-8")
        atomic_json(work / "transcript.json", transcript)
        subtitles=output.with_suffix(".srt")
        job["outputs"]={"transcript":str(transcript_txt),"transcript_json":str(work/"transcript.json"),"subtitles":str(subtitles)}
        if not legacy_semantics:
            topics = _provisional_topics(segments, job["source_id"])
            knowledge = {"schema_version":"1.0", "source_id":job["source_id"], "semantic_authority":"PROVISIONAL",
                        "review_state":"REVIEW_REQUIRED", "concepts":[{"knowledge_id":topic["topic_id"].replace(":topic:",":knowledge:"),
                        "label":topic["label"], "status":"REVIEW_REQUIRED", "topic_id":topic["topic_id"], "locator":topic["locator"]} for topic in topics]}
            navigation = {"schema_version":"1.0", "source_id":job["source_id"], "routes":[{"topic_id":topic["topic_id"],
                         "knowledge_id":knowledge["concepts"][i]["knowledge_id"], "segment_ids":topic["evidence_segment_ids"], "locator":topic["locator"]} for i,topic in enumerate(topics)]}
            package = None
            if (project_dir / "project.json").is_file():
                package = build_project_package(project_dir, job, transcript, topics, knowledge, navigation)
                job["outputs"]["package_dir"] = str(package)
            job.update(state="COMPLETED",progress=100,message="Requested real outputs are ready",completed_at=now(),
                       artifact_dir=str(work), package_dir=str(package) if package else None, transcript_segments=len(segments))
            atomic_json(jobs_path,jobs); return job
        topics = _provisional_topics(segments, job["source_id"])
        knowledge = {"schema_version":"1.0", "source_id":job["source_id"], "semantic_authority":"PROVISIONAL",
                     "review_state":"REVIEW_REQUIRED", "concepts":[{"knowledge_id":topic["topic_id"].replace(":topic:",":knowledge:"),
                     "label":topic["label"], "status":"REVIEW_REQUIRED", "topic_id":topic["topic_id"], "locator":topic["locator"]} for topic in topics]}
        navigation = {"schema_version":"1.0", "source_id":job["source_id"], "routes":[{"topic_id":topic["topic_id"],
                      "knowledge_id":knowledge["concepts"][i]["knowledge_id"], "segment_ids":topic["evidence_segment_ids"], "locator":topic["locator"]} for i,topic in enumerate(topics)]}
        for name, value in (("topics.json",topics),("knowledge.json",knowledge),("navigation.json",navigation)):
            atomic_json(work / name, value)
        package = build_project_package(project_dir, job, transcript, topics, knowledge, navigation)
        job.update(state="COMPLETED", progress=100, message="Ready for review and publication preview", completed_at=now(),
                   artifact_dir=str(work), package_dir=str(package), transcript_segments=len(segments), provisional_topics=len(topics))
        atomic_json(jobs_path, jobs); return job
    except Exception as error:
        if isinstance(error, _RunCancelled) or _is_run_cancelled(project_dir, job.get("run_id")):
            job.update(state="CANCELLED", message="Cancelled by user", updated_at=now())
            atomic_json(jobs_path, jobs)
            return job
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
