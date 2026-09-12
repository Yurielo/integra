"""Source-first plan execution outside the native UI layer."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Any

from .capabilities import build_plan
from .documents import extract_document
from .user_media import atomic_json, import_source, now, run_job


def _runs(project_dir: Path) -> Path:
    path=project_dir/"runs"; path.mkdir(parents=True,exist_ok=True); return path


def prepare_run(project_dir: Path, plan: dict[str,Any]) -> dict[str,Any]:
    verified=build_plan(plan.get("sources",[]),plan.get("selected_outputs",[]))
    if verified["plan_id"]!=plan.get("plan_id"): raise ValueError("execution plan identity differs")
    run_id=f"urn:integra:run:{uuid.uuid4()}"
    record={"schema_version":"1.0","run_id":run_id,"plan":verified,"state":"QUEUED","current_stage":None,
            "completed_sources":0,"total_sources":len(verified["sources"]),"source_results":[],"created_at":now()}
    atomic_json(_runs(project_dir)/(run_id.removeprefix("urn:integra:run:")+".json"),record); return record


def run_path(project_dir:Path,run_id:str)->Path:
    try: token=str(uuid.UUID(run_id.removeprefix("urn:integra:run:")))
    except (AttributeError,ValueError) as error: raise ValueError("invalid run ID") from error
    path=_runs(project_dir)/(token+".json")
    if path.is_symlink() or not path.is_file(): raise ValueError("run does not exist")
    return path


def read_run(project_dir:Path,run_id:str)->dict[str,Any]: return json.loads(run_path(project_dir,run_id).read_bytes())


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


def execute_run(project_dir:Path,run_id:str)->dict[str,Any]:
    path=run_path(project_dir,run_id); record=json.loads(path.read_bytes()); plan=record["plan"]
    jobs_path=project_dir/"jobs.json"
    def refresh_record():
        return json.loads(path.read_bytes())
    try:
        record.update(state="RUNNING",started_at=now()); atomic_json(path,record)
        for source_plan,source in zip(plan["source_plans"],plan["sources"]):
            record = refresh_record()
            if record.get("state") != "RUNNING":
                break
            outputs=source_plan["outputs"]
            if not outputs:
                record["source_results"].append({"source_id":source["source_id"],"display_name":source["display_name"],"state":"SKIPPED","outputs":{}}); record["completed_sources"]+=1; atomic_json(path,record); continue
            if source["kind"]=="MEDIA":
                record["current_stage"]="media_preparation"; atomic_json(path,record)
                imported=import_source(project_dir,Path(source["input"]))
                if imported["source_id"] != source["source_id"]:
                    raise ValueError("media source changed after plan creation")
                job={"job_id":f"urn:integra:job:{uuid.uuid4()}","kind":"LOCAL_MEDIA_TRANSCRIPTION","state":"QUEUED","progress":0,"message":"Queued by source-first plan","created_at":now(),"source_id":imported["source_id"],"source_sha256":imported["content_sha256"],"owned_path":imported["owned_path"],"requested_outputs":outputs,"run_id":run_id}
                jobs=json.loads(jobs_path.read_bytes())
                jobs["jobs"].append(job); atomic_json(jobs_path,jobs); result=run_job(project_dir,job["job_id"])
                record["source_results"].append({"source_id":source["source_id"],"display_name":source["display_name"],"state":result["state"],"outputs":result.get("outputs",{}),"job_id":job["job_id"]})
            elif source["kind"]=="DOCUMENT":
                record["current_stage"]="document_analysis"; atomic_json(path,record); owned=_copy_document(project_dir,source)
                artifact_dir=project_dir/"artifacts"/uuid.uuid4().hex; artifact_dir.mkdir(parents=True)
                document=extract_document(owned,captured_at=now())
                if document["source"]["source_id"] != source["source_id"]:
                    raise ValueError("document source changed after plan creation")
                atomic_json(artifact_dir/"document.json",document)
                blocks=document["native_extraction"]["blocks"]+document["ocr"]["blocks"]
                text_path=artifact_dir/"text.md"; text_path.write_text("\n\n".join(item["text"] for item in blocks)+"\n",encoding="utf-8")
                outputs_map={"document_record":str(artifact_dir/"document.json")}
                if "document_structure" in outputs: outputs_map["document_structure"] = _write_document_structure(document, artifact_dir)
                if "discover_images" in outputs: outputs_map["discover_images"] = _write_discovered_images(document, artifact_dir)
                if "document_text" in outputs: outputs_map["text"]=str(text_path)
                record["source_results"].append({"source_id":source["source_id"],"display_name":source["display_name"],"state":"COMPLETED","outputs":outputs_map,"document_properties":{"content_mode":document["content_mode"],"ocr_status":document["ocr"]["status"],"embedded_media_count":len(document["embedded_media"])}})
            record["completed_sources"]+=1; atomic_json(path,record)
        record = refresh_record()
        final_state = "CANCELLED" if record.get("state") == "CANCELLED" else "COMPLETED"
        record.update(state=final_state,current_stage=None,completed_at=now()); atomic_json(path,record)
        project_path=project_dir/"project.json"
        if project_path.is_file():
            project=json.loads(project_path.read_bytes()); project["source_count"]=len(plan["sources"]); project["status"]="READY"; atomic_json(project_path,project)
        return record
    except Exception as error:
        record.update(state="FAILED",error=str(error)[:500],failed_at=now()); atomic_json(path,record); raise
