"""Source-first plan execution outside the native UI layer."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Any

from .capabilities import TRANSLATION_TARGET_LANGUAGE, build_plan, validate_translation_target_language
from .documents import extract_document, materialize_embedded_media
from .booktext_runtime import run_ocr as run_booktext_ocr
from .user_media import (
    _is_run_cancelled,
    _materialize_translation_txt,
    atomic_json,
    build_asr_diagnostics,
    import_source,
    now,
    run_job,
)
from .youtube_runtime import download_video
from .youtube_playlist_runtime import execute_playlist
from .seminartext_runtime import validate_topic_detail

RECOGNITION_MODES = frozenset({"normal", "careful"})
SOURCE_SPEECH_LANGUAGES = frozenset({"ru"})


def _runs(project_dir: Path) -> Path:
    path=project_dir/"runs"; path.mkdir(parents=True,exist_ok=True); return path


def _recognition_mode(value: Any) -> str:
    if not isinstance(value, str) or value not in RECOGNITION_MODES:
        raise ValueError("recognition mode is unsupported")
    return value


def _source_speech_language(value: Any) -> str:
    if not isinstance(value, str) or value not in SOURCE_SPEECH_LANGUAGES:
        raise ValueError("source-speech language is unsupported")
    return value


def prepare_run(project_dir: Path, plan: dict[str,Any], *, recognition_mode: str = "normal",
                source_speech_language: str = "ru", topic_detail: str = "auto") -> dict[str,Any]:
    selected_outputs = plan.get("selected_outputs", [])
    target_language = plan.get("translation_target_language", TRANSLATION_TARGET_LANGUAGE)
    verified=build_plan(plan.get("sources",[]), selected_outputs,
                        translation_target_language=target_language)
    if verified["plan_id"]!=plan.get("plan_id"): raise ValueError("execution plan identity differs")
    recognition_mode = _recognition_mode(recognition_mode)
    source_speech_language = _source_speech_language(source_speech_language)
    topic_detail = validate_topic_detail(topic_detail)
    run_id=f"urn:integra:run:{uuid.uuid4()}"
    record={"schema_version":"1.0","run_id":run_id,"plan":verified,"state":"QUEUED","current_stage":None,
            "recognition":{"requested_mode":recognition_mode},
            "source_speech_language":{"requested":source_speech_language},
            "topic_detail":{"requested":topic_detail},"completed_sources":0,
            "total_sources":len(verified["sources"]),"source_results":[],"created_at":now()}
    atomic_json(_runs(project_dir)/(run_id.removeprefix("urn:integra:run:")+".json"),record); return record


def prepare_transcript_translation_run(project_dir: Path, run_id: str, source_id: str,
                                       target_language: str = TRANSLATION_TARGET_LANGUAGE) -> dict[str, Any]:
    """Start translation from a completed source without inventing a transcript."""
    previous = read_run(project_dir, run_id)
    source = next((item for item in previous.get("plan", {}).get("sources", [])
                   if item.get("source_id") == source_id), None)
    completed = next((item for item in previous.get("source_results", [])
                      if item.get("source_id") == source_id and item.get("state") == "COMPLETED"), None)
    if not isinstance(source, dict) or not isinstance(completed, dict):
        raise ValueError("completed transcript source is unavailable")
    outputs = completed.get("outputs", {})
    if not isinstance(outputs.get("transcript"), str) or not isinstance(outputs.get("subtitles"), str):
        raise ValueError("completed transcript is unavailable")
    target_language = validate_translation_target_language(target_language)
    mode = previous.get("recognition", {}).get("requested_mode", "normal")
    completed_language = completed.get("source_speech_language", {})
    language = completed_language.get("executed") if isinstance(completed_language, dict) else None
    language = language or previous.get("source_speech_language", {}).get("executed")
    language = language or previous.get("source_speech_language", {}).get("requested", "ru")
    if target_language == language:
        raise ValueError("Язык перевода должен отличаться от языка исходной речи.")
    plan = build_plan([source], ["translation"], translation_target_language=target_language)
    detail = previous.get("topic_detail", {}).get("requested", "auto")
    return prepare_run(project_dir, plan, recognition_mode=mode, source_speech_language=language,
                       topic_detail=detail)


def run_path(project_dir:Path,run_id:str)->Path:
    try: token=str(uuid.UUID(run_id.removeprefix("urn:integra:run:")))
    except (AttributeError,ValueError) as error: raise ValueError("invalid run ID") from error
    path=_runs(project_dir)/(token+".json")
    if path.is_symlink() or not path.is_file(): raise ValueError("run does not exist")
    return path


def _owned_artifact(project_dir: Path, value: Any) -> Path:
    """Resolve one saved result path without trusting a persisted string."""
    if not isinstance(value, str):
        raise ValueError("saved translation artifact path is invalid")
    path = Path(value)
    if path.is_symlink() or not path.is_file():
        raise ValueError("saved translation artifact is unavailable")
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to((project_dir / "artifacts").resolve(strict=True))
    except (OSError, ValueError) as error:
        raise ValueError("saved translation artifact is outside the project") from error
    return resolved


def _recover_saved_translation_text(project_dir: Path, record: dict[str, Any]) -> bool:
    """Materialize legacy translated text only when its saved evidence still binds."""
    if record.get("state") != "COMPLETED":
        return False
    changed = False
    for result in record.get("source_results", []):
        if not isinstance(result, dict) or result.get("state") != "COMPLETED":
            continue
        outputs = result.get("outputs")
        if not isinstance(outputs, dict) or "translation_txt" in outputs:
            continue
        required = ("translation", "translation_provenance", "transcript_json", "subtitles")
        if not all(name in outputs for name in required):
            continue
        translation = _owned_artifact(project_dir, outputs["translation"])
        provenance_path = _owned_artifact(project_dir, outputs["translation_provenance"])
        transcript = _owned_artifact(project_dir, outputs["transcript_json"])
        subtitles = _owned_artifact(project_dir, outputs["subtitles"])
        try:
            provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError) as error:
            raise ValueError("saved translation provenance is invalid") from error
        source_id = result.get("source_id")
        if (not isinstance(provenance, dict) or provenance.get("status") != "COMPLETED" or
            provenance.get("source_id") != source_id or
            provenance.get("source_transcript_sha256") != hashlib.sha256(transcript.read_bytes()).hexdigest() or
            provenance.get("source_subtitles_sha256") != hashlib.sha256(subtitles.read_bytes()).hexdigest() or
            provenance.get("output_sha256") != hashlib.sha256(translation.read_bytes()).hexdigest() or
            provenance.get("source_language") != "ru" or
            provenance.get("requested_target_language") != "en" or
            provenance.get("executed_target_language") != "en"):
            raise ValueError("saved translation does not match its source evidence")
        target = translation.parent / "translation.txt"
        if target.exists() or target.is_symlink():
            raise ValueError("saved translated text has an ambiguous state")
        _materialize_translation_txt(translation, target, provenance)
        outputs["translation_txt"] = str(target)
        changed = True
    return changed


def read_run(project_dir:Path,run_id:str)->dict[str,Any]:
    path = run_path(project_dir, run_id)
    record = json.loads(path.read_bytes())
    if not isinstance(record, dict):
        raise ValueError("saved run is invalid")
    if _recover_saved_translation_text(project_dir, record):
        atomic_json(path, record)
    return record


def _copy_document(project_dir:Path,source:dict[str,Any])->Path:
    path=Path(source["input"])
    if path.is_symlink() or not path.is_file(): raise ValueError("document source is unavailable")
    path=path.resolve(strict=True); digest=hashlib.sha256(path.read_bytes()).hexdigest(); root=project_dir/"sources"/digest; root.mkdir(parents=True,exist_ok=True)
    target=root/("original"+path.suffix.lower())
    if not target.exists():
        temporary=target.with_name(target.name+".tmp"); shutil.copyfile(path,temporary)
        if hashlib.sha256(temporary.read_bytes()).hexdigest()!=digest: temporary.unlink(missing_ok=True); raise ValueError("document copy verification failed")
        os.replace(temporary,target)
    return target


def _write_document_structure(document: dict[str, Any], artifact_dir: Path) -> str:
    entries = []
    for item in document["native_extraction"]["blocks"] + document["ocr"]["blocks"]:
        locator = item["locator"]
        entries.append({
            "block_id": item["block_id"],
            "unit_kind": locator["unit_kind"],
            "unit_index": locator["unit_index"],
            "text": item["text"],
            "extraction_method": item["extraction_method"],
            "character_start": locator["character_start"],
            "character_end": locator["character_end"],
        })
    structure_path = artifact_dir / "document_structure.json"
    structure = {
        "schema_version": "1.0",
        "source_id": document["source"]["source_id"],
        "document_id": document["document_id"],
        "format": document["source"]["format"],
        "page_or_slide_count": document["page_or_slide_count"],
        "content_mode": document["content_mode"],
        "entry_count": len(entries),
        "entries": entries,
    }
    structure_path.write_text(json.dumps(structure, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(structure_path)


def _write_discovered_images(document: dict[str, Any], artifact_dir: Path) -> str:
    manifest_path = artifact_dir / "discover_images.json"
    manifest = {
        "schema_version": "1.0",
        "source_id": document["source"]["source_id"],
        "document_id": document["document_id"],
        "embedded_media_count": len(document["embedded_media"]),
        "embedded_media": [
            {
                "media_id": item["media_id"],
                "part_path": item["part_path"],
                "media_type": item["media_type"],
                "sha256": item["sha256"],
                "size_bytes": item["size_bytes"],
                "parent_locator": item["parent_locator"],
            }
            for item in document["embedded_media"]
        ],
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(manifest_path)


def _materialize_embedded_images(
    document: dict[str, Any], source_path: Path, artifact_dir: Path
) -> tuple[str, str]:
    """Create an Integra-owned, hash-verified copy of embedded media bytes."""

    # The document contract rejects symlinked ancestors.  Temporary and
    # Application Support roots may be reached through a system symlink, so
    # pass the canonical artifact location rather than its display path.
    directory = artifact_dir.resolve(strict=True) / "embedded_media"
    written = materialize_embedded_media(document, source_path, directory)
    manifest_path = artifact_dir / "embedded_media.json"
    atomic_json(
        manifest_path,
        {
            "schema_version": "1.0",
            "source_id": document["source"]["source_id"],
            "document_id": document["document_id"],
            "directory": str(directory),
            "embedded_media_count": len(written),
            "embedded_media": written,
        },
    )
    return str(directory), str(manifest_path)


def _booktext_provider(result: dict[str, Any], source_format: str) -> dict[str, Any]:
    """Translate persisted BookText page evidence into the v1 OCR contract."""
    unit_kind = {"IMAGE": "IMAGE", "PDF": "PAGE"}.get(source_format)
    if unit_kind is None:
        raise ValueError("BookText OCR is only available for images and PDF")
    blocks = result.get("blocks")
    if not isinstance(blocks, list):
        raise ValueError("BookText OCR result has no page evidence")
    return {
        "provider": {
            "component_id": "booktext",
            "implementation_sha256": result["entrypoint_sha256"],
            "model_id": "surya-runtime-unattested; available-local-candidate-only" if result["runtime"].get("model_evidence") else "datalab-to/surya-ocr-2",
            "model_sha256": result["runtime"]["model_sha256"],
        },
        "blocks": [{
            "unit_kind": unit_kind, "unit_index": item["unit_index"],
            "region": {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0},
            "text": item["text"], "confidence": item["confidence"],
        } for item in blocks],
    }


def _booktext_outputs(result: dict[str, Any], output_dir: Path) -> dict[str, str]:
    values = {
        "booktext_text": "book_clean.txt", "booktext_markdown": "book.md",
        "booktext_record": "book.json", "booktext_manifest": "integra_booktext_manifest.json",
        "booktext_review": "review.txt", "booktext_review_json": "review.json",
        "booktext_searchable_pdf": "book_ocr.pdf", "booktext_pages": "pages",
        "booktext_surya_raw": "surya", "booktext_vision_qa": "vision",
    }
    return {key: str(output_dir / value) for key, value in values.items() if (output_dir / value).exists()}


def execute_run(project_dir:Path,run_id:str)->dict[str,Any]:
    path=run_path(project_dir,run_id); record=json.loads(path.read_bytes()); plan=record["plan"]
    recognition_mode = _recognition_mode(record.get("recognition", {}).get("requested_mode", "normal"))
    source_speech_language = _source_speech_language(record.get("source_speech_language", {}).get("requested", "ru"))
    topic_detail = validate_topic_detail(record.get("topic_detail", {}).get("requested", "auto"))
    jobs_path=project_dir/"jobs.json"
    def refresh_record():
        return json.loads(path.read_bytes())
    def failed_media_source(source: dict[str, Any], error: Exception) -> dict[str, Any]:
        """Persist a source-scoped failure without manufacturing successful outputs."""
        outputs: dict[str, str] = {}
        from .seminartext_asr_runtime import ASRQualityError
        if isinstance(error, ASRQualityError):
            outputs = {"transcript_quality_report": error.artifacts["review_txt"],
                       "transcript_asr_record": error.artifacts["record"]}
        result = {"source_id": source["source_id"], "display_name": source["display_name"],
                  "state": "FAILED", "outputs": outputs, "error": str(error)[:500]}
        if isinstance(error, ASRQualityError):
            result["asr_diagnostics"] = build_asr_diagnostics(
                error.artifacts["provenance"], recognition_mode, source_speech_language)
        return result
    try:
        if _is_run_cancelled(project_dir, run_id):
            record.update(state="CANCELLED",current_stage=None,cancelled_at=now()); atomic_json(path,record)
            return record
        record.update(state="RUNNING",started_at=now()); atomic_json(path,record)
        for source_plan,source in zip(plan["source_plans"],plan["sources"]):
            record = refresh_record()
            if record.get("state") != "RUNNING" or _is_run_cancelled(project_dir, run_id):
                break
            outputs=source_plan["outputs"]
            if not outputs:
                record["source_results"].append({"source_id":source["source_id"],"display_name":source["display_name"],"state":"SKIPPED","outputs":{}}); record["completed_sources"]+=1; atomic_json(path,record); continue
            if source["kind"]=="MEDIA":
                try:
                    record["current_stage"]="media_preparation"; atomic_json(path,record)
                    imported=import_source(project_dir,Path(source["input"]))
                    if imported["source_id"] != source["source_id"]:
                        raise ValueError("media source changed after plan creation")
                    job={"job_id":f"urn:integra:job:{uuid.uuid4()}","kind":"LOCAL_MEDIA_TRANSCRIPTION","state":"QUEUED","progress":0,"message":"Queued by source-first plan","created_at":now(),"source_id":imported["source_id"],"source_sha256":imported["content_sha256"],"owned_path":imported["owned_path"],"requested_outputs":outputs,"recognition_mode":recognition_mode,"source_speech_language":source_speech_language,"topic_detail":topic_detail,"translation_target_language":source_plan.get("translation_target_language"),"run_id":run_id}
                    jobs=json.loads(jobs_path.read_bytes())
                    jobs["jobs"].append(job); atomic_json(jobs_path,jobs); result=run_job(project_dir,job["job_id"])
                    record["source_results"].append({"source_id":source["source_id"],"display_name":source["display_name"],"state":result["state"],"outputs":result.get("outputs",{}),"job_id":job["job_id"]})
                    if result.get("asr_reuse"):
                        record["source_results"][-1]["asr_reuse"] = result["asr_reuse"]
                    if result.get("recognition"):
                        record["source_results"][-1]["recognition"] = result["recognition"]
                    if result.get("source_speech_language"):
                        record["source_results"][-1]["source_speech_language"] = result["source_speech_language"]
                        record["source_speech_language"] = result["source_speech_language"]
                    if result.get("topic_detail"):
                        record["source_results"][-1]["topic_detail"] = result["topic_detail"]
                    if result.get("asr_diagnostics"):
                        record["source_results"][-1]["asr_diagnostics"] = result["asr_diagnostics"]
                except Exception as error:
                    # A one-source request retains its established fail-closed
                    # exception behavior.  In a local multi-source plan each
                    # source owns an independent job/artifact directory, so a
                    # failed peer is recorded and later selected peers can run.
                    if _is_run_cancelled(project_dir, run_id) or len(plan["sources"]) == 1:
                        raise
                    record = refresh_record()
                    record["source_results"].append(failed_media_source(source, error))
                    record["current_stage"] = None
                    atomic_json(path, record)
                    continue
            elif source["kind"] == "URL" and source["source_type"] == "YOUTUBE_VIDEO":
                record["current_stage"] = "youtube_ingest"; record["message"] = "Downloading selected YouTube video"; atomic_json(path, record)
                downloaded = download_video(project_dir, source, run_id=run_id)
                downloaded_outputs = {
                    "downloaded_media": downloaded["downloaded_path"],
                    "youtube_source_record": downloaded["record_path"],
                }
                downstream = [item for item in outputs if item != "youtube_ingest"]
                if not downstream:
                    record["source_results"].append({"source_id": source["source_id"], "display_name": source["display_name"], "state": "COMPLETED", "outputs": downloaded_outputs})
                else:
                    record["current_stage"] = "media_preparation"; atomic_json(path, record)
                    job = {"job_id": f"urn:integra:job:{uuid.uuid4()}", "kind": "YOUTUBE_MEDIA_TRANSCRIPTION", "state": "QUEUED", "progress": 0, "message": "Queued after YouTube download", "created_at": now(), "source_id": source["source_id"], "source_sha256": downloaded["content_sha256"], "owned_path": downloaded["downloaded_path"], "requested_outputs": downstream, "recognition_mode": recognition_mode, "source_speech_language": source_speech_language, "topic_detail": topic_detail, "translation_target_language": source_plan.get("translation_target_language"), "run_id": run_id, "youtube_source_record": downloaded["record_path"]}
                    jobs = json.loads(jobs_path.read_bytes())
                    jobs["jobs"].append(job); atomic_json(jobs_path, jobs); result = run_job(project_dir, job["job_id"])
                    record["source_results"].append({"source_id": source["source_id"], "display_name": source["display_name"], "state": result["state"], "outputs": downloaded_outputs | result.get("outputs", {}), "job_id": job["job_id"]})
                    if result.get("asr_reuse"):
                        record["source_results"][-1]["asr_reuse"] = result["asr_reuse"]
                    if result.get("recognition"):
                        record["source_results"][-1]["recognition"] = result["recognition"]
                    if result.get("source_speech_language"):
                        record["source_results"][-1]["source_speech_language"] = result["source_speech_language"]
                        record["source_speech_language"] = result["source_speech_language"]
                    if result.get("topic_detail"):
                        record["source_results"][-1]["topic_detail"] = result["topic_detail"]
                    if result.get("asr_diagnostics"):
                        record["source_results"][-1]["asr_diagnostics"] = result["asr_diagnostics"]
            elif source["kind"] == "URL" and source["source_type"] == "YOUTUBE_PLAYLIST":
                if outputs != ["youtube_playlist_ingest"]:
                    raise ValueError("playlist plan has unsupported outputs")
                record["current_stage"] = "youtube_playlist_ingest"; record["message"] = "Discovering and downloading selected YouTube playlist"; atomic_json(path, record)
                playlist_outputs = execute_playlist(project_dir, source, run_id=run_id)
                record["source_results"].append({"source_id": source["source_id"], "display_name": source["display_name"], "state": "COMPLETED", "outputs": playlist_outputs})
            elif source["kind"]=="DOCUMENT":
                record["current_stage"]="document_analysis"; atomic_json(path,record); owned=_copy_document(project_dir,source)
                artifact_dir=project_dir/"artifacts"/uuid.uuid4().hex; artifact_dir.mkdir(parents=True)
                preliminary = extract_document(owned, captured_at=now())
                selection = {key: source[field] for key, field in (("pages", "booktext_pages"), ("exclude_pages", "booktext_exclude_pages")) if source.get(field)}
                needs_ocr = "ocr" in outputs or bool(selection) or ("document_text" in outputs and preliminary["ocr"]["status"] == "REQUIRED")
                booktext_result = None
                if needs_ocr:
                    record["current_stage"] = "ocr"; record["message"] = "BookText OCR / Surya"; atomic_json(path, record)
                    booktext_dir = artifact_dir / "booktext"
                    booktext_result = run_booktext_ocr(owned, booktext_dir, **selection)
                    document = extract_document(owned, captured_at=now(), ocr_provider=lambda _request: _booktext_provider(booktext_result, preliminary["source"]["format"]))
                else:
                    document = preliminary
                if document["source"]["source_id"] != source["source_id"]:
                    raise ValueError("document source changed after plan creation")
                atomic_json(artifact_dir/"document.json",document)
                blocks=document["native_extraction"]["blocks"]+document["ocr"]["blocks"]
                text_path=artifact_dir/"text.txt"; text_path.write_text("\n\n".join(item["text"] for item in blocks)+"\n",encoding="utf-8")
                outputs_map={"document_record":str(artifact_dir/"document.json")}
                if booktext_result is not None:
                    outputs_map.update(_booktext_outputs(booktext_result, artifact_dir / "booktext"))
                    # Keep original full-document extraction separate from selected
                    # OCR evidence. Native PDFs may not invoke the OCR provider.
                    selected_record = artifact_dir / "selected_ocr_pages.json"
                    atomic_json(selected_record, {"schema_version": "1.0", "component": "booktext",
                        "source_id": source["source_id"], "selection": selection,
                        "scope": "SELECTED_OCR_PAGES_ORIGINAL_NUMBERING",
                        "model_evidence": booktext_result.get("runtime", {}).get("model_evidence", "UNATTESTED"),
                        "blocks": booktext_result["blocks"]})
                    outputs_map["selected_ocr_pages"] = str(selected_record)
                if "document_structure" in outputs: outputs_map["document_structure"] = _write_document_structure(document, artifact_dir)
                if "discover_images" in outputs: outputs_map["discover_images"] = _write_discovered_images(document, artifact_dir)
                if "extract_images" in outputs:
                    directory, manifest = _materialize_embedded_images(document, owned, artifact_dir)
                    outputs_map["embedded_images_directory"] = directory
                    outputs_map["embedded_images_manifest"] = manifest
                if "document_text" in outputs:
                    outputs_map["text"] = outputs_map.get("booktext_text", str(text_path))
                record["source_results"].append({"source_id":source["source_id"],"display_name":source["display_name"],"state":"COMPLETED","outputs":outputs_map,"document_properties":{"content_mode":document["content_mode"],"ocr_status":document["ocr"]["status"],"embedded_media_count":len(document["embedded_media"]),"ocr_selection":selection,"document_record_scope":"FULL_SOURCE_EXTRACTION; SELECTED_OCR_IN_SEPARATE_ARTIFACT"}})
            if _is_run_cancelled(project_dir, run_id) or any(item.get("state") == "CANCELLED" for item in record["source_results"]):
                record.update(state="CANCELLED", current_stage=None, cancelled_at=now())
                atomic_json(path, record)
                return record
            record["completed_sources"]+=1; atomic_json(path,record)
        record = refresh_record()
        failed_sources = [item for item in record["source_results"] if item.get("state") == "FAILED"]
        final_state = "CANCELLED" if _is_run_cancelled(project_dir, run_id) else ("FAILED" if failed_sources else "COMPLETED")
        terminal_at = now()
        record.update(state=final_state,current_stage=None)
        if final_state == "FAILED":
            record.update(error=f"{len(failed_sources)} selected source(s) failed; completed peer results are retained", failed_at=terminal_at)
        else:
            record.update(completed_at=terminal_at)
        atomic_json(path,record)
        project_path=project_dir/"project.json"
        if project_path.is_file():
            project=json.loads(project_path.read_bytes()); project["source_count"]=len(plan["sources"]); project["status"]="READY"; atomic_json(project_path,project)
        return record
    except Exception as error:
        latest = refresh_record()
        if _is_run_cancelled(project_dir, run_id):
            latest.update(state="CANCELLED",current_stage=None,cancelled_at=now()); atomic_json(path,latest)
            return latest
        # Failed ASR quality is inspectable but never a successful transcript.
        from .seminartext_asr_runtime import ASRQualityError
        if isinstance(error, ASRQualityError):
            latest["source_results"].append({"source_id":source["source_id"],
                "display_name":source["display_name"], "state":"FAILED",
                "outputs":{"transcript_quality_report":error.artifacts["review_txt"],
                           "transcript_asr_record":error.artifacts["record"]},
                "asr_diagnostics": build_asr_diagnostics(
                    error.artifacts["provenance"], recognition_mode, source_speech_language)})
            latest.update(state="FAILED",
                          error="Расшифровка не прошла проверку качества. Проверьте аудио и повторите обработку.",
                          failed_at=now())
        else:
            # A downstream translation failure must not hide a durable source
            # transcript behind a raw provider message.  The completed job's
            # upstream outputs remain available from this failed run.
            prior_job = next((item for item in reversed(json.loads(jobs_path.read_bytes()).get("jobs", []))
                              if item.get("run_id") == run_id and item.get("source_id") == source.get("source_id")), None)
            if isinstance(prior_job, dict) and isinstance(prior_job.get("outputs"), dict) and prior_job["outputs"]:
                latest["source_results"].append({"source_id": source["source_id"],
                    "display_name": source["display_name"], "state": "FAILED",
                    "outputs": prior_job["outputs"], "job_id": prior_job.get("job_id")})
            selected = latest.get("plan", {}).get("selected_outputs", [])
            message = ("Перевод расшифровки не выполнен. Исходная расшифровка сохранена; "
                       "повторите попытку после проверки локальной обработки."
                       if "translation" in selected else str(error)[:500])
            latest.update(state="FAILED", error=message, failed_at=now())
        atomic_json(path,latest); raise
