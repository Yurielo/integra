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
from typing import Any

from .identity import derive_imported_id
from .onedrive import build_onedrive_package
from .protocol import canonical_json, content_sha256
from .publishing import sha256_bytes, validate_package

SUPPORTED = {".aac", ".aif", ".aiff", ".flac", ".m4a", ".m4v", ".mkv", ".mov", ".mp3", ".mp4", ".ogg", ".wav", ".webm"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(canonical_json(value) + b"\n")
    os.replace(temporary, path)


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


def _tools() -> tuple[str, str, str]:
    ffmpeg = os.environ.get("INTEGRA_FFMPEG") or shutil.which("ffmpeg")
    whisper = os.environ.get("INTEGRA_WHISPER_CLI") or shutil.which("whisper-cli")
    model = os.environ.get("INTEGRA_WHISPER_MODEL") or str(Path.home() / "whisper-models/ggml-large-v3.bin")
    if not ffmpeg: raise ValueError("ffmpeg is not installed")
    if not whisper: raise ValueError("whisper-cli is not installed")
    model_path = Path(model)
    if model_path.is_symlink() or not model_path.is_file(): raise ValueError("Whisper model is missing; set INTEGRA_WHISPER_MODEL")
    return ffmpeg, whisper, str(model_path.resolve(strict=True))


def preflight() -> dict[str, Any]:
    ffmpeg, whisper, model = _tools()
    return {"state":"READY", "ffmpeg":ffmpeg, "whisper_cli":whisper,
            "model":model, "model_sha256":hashlib.sha256(Path(model).read_bytes()).hexdigest(),
            "supported_extensions":sorted(SUPPORTED)}


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
    def checkpoint(state: str, progress: int, message: str) -> None:
        job.update(state=state, progress=progress, message=message, updated_at=now(), worker_pid=os.getpid())
        atomic_json(jobs_path, jobs)
    try:
        checkpoint("RUNNING", 5, "Preparing audio")
        ffmpeg, whisper, model = _tools(); source = Path(job["owned_path"])
        work = project_dir / "artifacts" / job_id.removeprefix("urn:integra:job:"); work.mkdir(parents=True, exist_ok=True)
        wav = work / "audio.wav"
        subprocess.run([ffmpeg, "-nostdin", "-y", "-i", str(source), "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(wav)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        checkpoint("RUNNING", 25, "Transcribing locally")
        output = work / "transcript"
        subprocess.run([whisper, "-m", model, "-f", str(wav), "-l", "auto", "-osrt", "-of", str(output), "-np"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        segments = _parse_srt((output.with_suffix(".srt")).read_text(errors="replace"), job["source_id"])
        if not segments: raise ValueError("transcription produced no timed speech segments")
        checkpoint("RUNNING", 80, "Building provisional Topics and Knowledge")
        topics = _provisional_topics(segments, job["source_id"])
        transcript = {"schema_version":"1.0", "source_id":job["source_id"], "assurance":"MACHINE_TRANSCRIPT_UNREVIEWED",
                      "model_sha256":hashlib.sha256(Path(model).read_bytes()).hexdigest(), "segments":segments}
        knowledge = {"schema_version":"1.0", "source_id":job["source_id"], "semantic_authority":"PROVISIONAL",
                     "review_state":"REVIEW_REQUIRED", "concepts":[{"knowledge_id":topic["topic_id"].replace(":topic:",":knowledge:"),
                     "label":topic["label"], "status":"REVIEW_REQUIRED", "topic_id":topic["topic_id"], "locator":topic["locator"]} for topic in topics]}
        navigation = {"schema_version":"1.0", "source_id":job["source_id"], "routes":[{"topic_id":topic["topic_id"],
                      "knowledge_id":knowledge["concepts"][i]["knowledge_id"], "segment_ids":topic["evidence_segment_ids"], "locator":topic["locator"]} for i,topic in enumerate(topics)]}
        for name, value in (("transcript.json",transcript),("topics.json",topics),("knowledge.json",knowledge),("navigation.json",navigation)):
            atomic_json(work / name, value)
        package = build_project_package(project_dir, job, transcript, topics, knowledge, navigation)
        job.update(state="COMPLETED", progress=100, message="Ready for review and publication preview", completed_at=now(),
                   artifact_dir=str(work), package_dir=str(package), transcript_segments=len(segments), provisional_topics=len(topics))
        atomic_json(jobs_path, jobs); return job
    except Exception as error:
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
