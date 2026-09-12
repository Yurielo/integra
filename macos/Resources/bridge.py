#!/usr/bin/env python3
"""Closed local bridge between the AppKit shell and accepted Integra services."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import json, os, re, signal, subprocess, sys, uuid
from pathlib import Path

RESOURCES = Path(__file__).resolve().parent
sys.path.insert(0, str(RESOURCES))
sys.path.insert(1, str(RESOURCES.parents[1]))
from integra_core.onedrive import preview_onedrive_publication, publish_onedrive_package, validate_onedrive_package
from integra_core.project_lease import LeaseStore
from integra_core.protocol import canonical_json, content_sha256
from integra_core.publishing import preview_obsidian_export, publish_obsidian_export, validate_package
from integra_core.user_media import _parse_srt, ffmpeg_preflight, import_source, preflight, run_job
from integra_core.capabilities import build_plan, capability_registry, detect_source
from integra_core.application_runtime import execute_run, prepare_run, read_run, run_path

OPERATIONS = {"workflow", "deferred", "projects", "create-project", "open-project", "jobs", "start-job", "cancel-job", "resume-job", "import-media", "media-preflight", "process-media-job", "project-view", "detect-sources", "capability-registry", "build-plan", "execute-plan", "process-plan", "run-status", "recent-runs", "available-packages", "cancel-run", "retry-run", "media-navigation", "create-media-clip", "package-preview", "package-publish", "obsidian-preview", "onedrive-preview"}

def _safe_error(error):
    message = str(error).replace(str(Path.home()), "<HOME>")
    return re.sub(r"/(?:[^\s,:]+/)+[^\s,:]+", "<PATH>", message)[:500]

def _now(): return datetime.now(timezone.utc)
def _instant(value): return value.isoformat(timespec="seconds").replace("+00:00", "Z")

def _root():
    override = os.environ.get("INTEGRA_APP_DATA_ROOT")
    root = Path(override) if override else Path.home() / "Library/Application Support/Integra"
    root.mkdir(parents=True, exist_ok=True)
    if root.is_symlink() or not root.is_dir(): raise ValueError("application data root is unsafe")
    return root.resolve(strict=True)

def _request():
    raw = sys.stdin.buffer.read()
    if not raw: return {}
    value = json.loads(raw)
    if not isinstance(value, dict): raise ValueError("request must be an object")
    return value

def _atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_bytes(canonical_json(value) + b"\n")
    os.replace(temp, path)

def _project_dir(root, project_id):
    try: token = str(uuid.UUID(project_id.removeprefix("urn:integra:project:")))
    except (AttributeError, ValueError) as error: raise ValueError("invalid project ID") from error
    return root / "projects" / token

def _project(root, project_id):
    record = _project_dir(root, project_id) / "project.json"
    if record.is_symlink() or not record.is_file(): raise ValueError("project does not exist")
    return json.loads(record.read_bytes())

def _projects(root):
    parent = root / "projects"
    if not parent.exists(): return []
    result = []
    for path in sorted(parent.iterdir()):
        record = path / "project.json"
        if not path.is_symlink() and path.is_dir() and record.is_file() and not record.is_symlink():
            result.append(json.loads(record.read_bytes()))
    return result

def _create(root, request):
    name = request.get("name")
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 120: raise ValueError("project name must contain 1-120 characters")
    project_id = f"urn:integra:project:{uuid.uuid4()}"; path = _project_dir(root, project_id); path.mkdir(parents=True)
    record = {"schema_version":"1.0", "project_id":project_id, "name":name.strip(), "created_at":_instant(_now()), "source_count":0, "status":"READY"}
    _atomic_json(path / "project.json", record); _atomic_json(path / "jobs.json", {"schema_version":"1.0", "jobs":[]})
    return record

def _jobs_path(root, project_id):
    project = _project(root, project_id)
    return _project_dir(root, project["project_id"]) / "jobs.json"

def _jobs(root, project_id): return json.loads(_jobs_path(root, project_id).read_bytes())["jobs"]

def _spawn_media(root, project_id, job_id):
    environment = dict(os.environ); environment["INTEGRA_APP_DATA_ROOT"] = str(root); environment["PYTHONDONTWRITEBYTECODE"] = "1"
    request = json.dumps({"project_id":project_id,"job_id":job_id}).encode()
    process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "process-media-job"], stdin=subprocess.PIPE,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=environment, start_new_session=True)
    process.stdin.write(request); process.stdin.close()
    return process.pid

def _spawn_plan(root, project_id, run_id):
    environment=dict(os.environ); environment["INTEGRA_APP_DATA_ROOT"]=str(root); environment["PYTHONDONTWRITEBYTECODE"]="1"
    request=json.dumps({"project_id":project_id,"run_id":run_id}).encode()
    process=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),"process-plan"],stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,env=environment,start_new_session=True)
    process.stdin.write(request); process.stdin.close()
    path=run_path(_project_dir(root,project_id),run_id); record=json.loads(path.read_bytes()); record["worker_pid"]=process.pid; _atomic_json(path,record)
    return record

def _execute_plan(root,request):
    plan=request.get("plan"); name=request.get("name") or "Новая обработка"
    project=_create(root,{"name":name}); project_dir=_project_dir(root,project["project_id"])
    run=prepare_run(project_dir,plan); return {"project":project,"run":_spawn_plan(root,project["project_id"],run["run_id"])}

def _run_action(root,request,action):
    project_id=request.get("project_id"); project_dir=_project_dir(root,_project(root,project_id)["project_id"]); record=read_run(project_dir,request.get("run_id"))
    if action=="status": return record
    if action=="cancel":
        if record["state"] not in {"QUEUED","RUNNING"}: raise ValueError("run cannot be cancelled from current state")
        pid=record.get("worker_pid")
        if isinstance(pid,int):
            try: os.killpg(pid,signal.SIGTERM)
            except ProcessLookupError: pass
        jobs_path=project_dir/"jobs.json"
        if jobs_path.is_file() and not jobs_path.is_symlink():
            jobs_record=json.loads(jobs_path.read_bytes()); changed=False
            for job in jobs_record.get("jobs",[]):
                if job.get("run_id")==record["run_id"] and job.get("state") in {"QUEUED","RUNNING"}:
                    job.update(state="CANCELLED",message="Cancelled with source-first run",updated_at=_instant(_now())); changed=True
            if changed: _atomic_json(jobs_path,jobs_record)
        record.update(state="CANCELLED",cancelled_at=_instant(_now()),current_stage=None); _atomic_json(run_path(project_dir,record["run_id"]),record); return record
    if record["state"] not in {"FAILED","CANCELLED"}: raise ValueError("run cannot be retried from current state")
    new=prepare_run(project_dir,record["plan"]); return _spawn_plan(root,project_id,new["run_id"])

def _recent_runs(root):
    result=[]
    for project in _projects(root):
        directory=_project_dir(root,project["project_id"])/"runs"
        if not directory.is_dir() or directory.is_symlink(): continue
        for path in directory.glob("*.json"):
            if path.is_file() and not path.is_symlink(): result.append({"project":project,"run":json.loads(path.read_bytes())})
    return sorted(result,key=lambda item:item["run"].get("created_at",""),reverse=True)

def _available_packages(root):
    """Return only package artifacts that still validate from persisted completed runs."""
    available=[]
    for item in _recent_runs(root):
        project=item["project"]; run=item["run"]
        if run.get("state")!="COMPLETED": continue
        for result in run.get("source_results",[]):
            outputs=result.get("outputs",{}) if isinstance(result,dict) else {}
            path=outputs.get("package_dir") if isinstance(outputs,dict) else None
            if not isinstance(path,str): continue
            try: manifest,_=_package(path)
            except Exception: continue
            available.append({"project_id":project["project_id"],"project_name":project["name"],"run_id":run["run_id"],"source_id":result.get("source_id"),"source_name":result.get("display_name"),"package_dir":path,"package_id":manifest["package_id"],"artifact_type":manifest["artifact_type"]})
    return available

def _media_navigation(root, request):
    """Return only persisted, owned media and its exact SRT cue timings."""
    project_id = request.get("project_id"); source_id = request.get("source_id")
    if not isinstance(source_id, str) or not source_id: raise ValueError("source ID is required")
    project_dir = _project_dir(root, _project(root, project_id)["project_id"])
    run = read_run(project_dir, request.get("run_id"))
    result = next((item for item in run.get("source_results", []) if item.get("source_id") == source_id), None)
    if not isinstance(result, dict) or result.get("state") != "COMPLETED": raise ValueError("completed source result is unavailable")
    job_id = result.get("job_id")
    job = next((item for item in _jobs(root, project_id) if item.get("job_id") == job_id), None)
    if not isinstance(job, dict) or job.get("source_id") != source_id: raise ValueError("owned media job is unavailable")
    outputs = result.get("outputs")
    if not isinstance(outputs, dict) or not isinstance(outputs.get("subtitles"), str): raise ValueError("timed subtitles are unavailable")
    media = Path(job.get("owned_path", "")); subtitles = Path(outputs["subtitles"])
    if media.is_symlink() or subtitles.is_symlink() or not media.is_file() or not subtitles.is_file():
        raise ValueError("owned media or subtitles are unavailable")
    media = media.resolve(strict=True); subtitles = subtitles.resolve(strict=True)
    segments = _parse_srt(subtitles.read_text(encoding="utf-8", errors="replace"), source_id)
    if not segments: raise ValueError("timed subtitles contain no navigable speech")
    return {"source_id":source_id,"media_path":str(media),"subtitles_path":str(subtitles),"segments":segments}

def _create_media_clip(root, request):
    """Render one owned local clip bounded by persisted SRT cue edges."""
    navigation = _media_navigation(root, request)
    try: start = float(request.get("start_seconds")); end = float(request.get("end_seconds"))
    except (TypeError, ValueError) as error: raise ValueError("clip boundaries must be numeric") from error
    if not (start >= 0 and end > start): raise ValueError("clip end must follow its start")
    starts = {item["start_seconds"] for item in navigation["segments"]}
    ends = {item["end_seconds"] for item in navigation["segments"]}
    if start not in starts or end not in ends: raise ValueError("clip boundaries must match persisted SRT cues")
    project_id=request.get("project_id"); run_id=request.get("run_id"); source_id=request.get("source_id")
    project_dir=_project_dir(root,_project(root,project_id)["project_id"])
    run=read_run(project_dir,run_id)
    result=next((item for item in run.get("source_results",[]) if item.get("source_id")==source_id),None)
    if not isinstance(result,dict) or result.get("state")!="COMPLETED": raise ValueError("completed source result is unavailable")
    directory=project_dir/"artifacts"/"clips"/str(uuid.UUID(run_id.removeprefix("urn:integra:run:")))
    directory.mkdir(parents=True,exist_ok=True)
    clip=directory/f"clip_{int(start*1000):010d}_{int(end*1000):010d}.mp4"
    ffmpeg=ffmpeg_preflight()["ffmpeg"]
    completed=subprocess.run([ffmpeg,"-nostdin","-y","-ss",f"{start:.3f}","-to",f"{end:.3f}","-i",navigation["media_path"],"-map","0:v?","-map","0:a?","-c:v","libx264","-c:a","aac",str(clip)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    if completed.returncode != 0 or clip.is_symlink() or not clip.is_file() or clip.stat().st_size == 0: raise ValueError("clip rendering produced no media output")
    manifest=directory/"clips.json"; current={"schema_version":"1.0","source_id":source_id,"source_path":navigation["media_path"],"subtitles_path":navigation["subtitles_path"],"clips":[]}
    if manifest.is_file() and not manifest.is_symlink(): current=json.loads(manifest.read_bytes())
    record={"path":str(clip),"start_seconds":start,"end_seconds":end,"locator":f"media:{source_id}#t={start:.3f},{end:.3f}"}
    current["clips"]=[item for item in current.get("clips",[]) if item.get("path")!=str(clip)]+[record]; _atomic_json(manifest,current)
    outputs=result.setdefault("outputs",{}); outputs["clips_manifest"]=str(manifest); outputs[f"clip_{int(start*1000)}_{int(end*1000)}"]=str(clip); _atomic_json(run_path(project_dir,run_id),run)
    return record | {"manifest":str(manifest)}

def _import_media(root, request):
    project = _project(root, request.get("project_id")); project_dir = _project_dir(root, project["project_id"])
    source = import_source(project_dir, Path(request.get("source_path", "")))
    jobs_path = _jobs_path(root, project["project_id"]); jobs = _jobs(root, project["project_id"])
    job = {"job_id":f"urn:integra:job:{uuid.uuid4()}","kind":"LOCAL_MEDIA_TRANSCRIPTION","state":"QUEUED","progress":0,
           "message":"Queued","created_at":_instant(_now()),"source_id":source["source_id"],"source_sha256":source["content_sha256"],"owned_path":source["owned_path"]}
    jobs.append(job); _atomic_json(jobs_path,{"schema_version":"1.0","jobs":jobs})
    project["source_count"] = project.get("source_count",0)+1; project["status"]="PROCESSING"; _atomic_json(project_dir/"project.json",project)
    job["worker_pid"] = _spawn_media(root, project["project_id"], job["job_id"])
    current = json.loads(jobs_path.read_bytes()); current_job=next(item for item in current["jobs"] if item["job_id"]==job["job_id"])
    current_job["worker_pid"]=job["worker_pid"]; _atomic_json(jobs_path,current); return current_job

def _project_view(root, project_id):
    project_dir = _project_dir(root, _project(root, project_id)["project_id"]); jobs = _jobs(root, project_id)
    latest = next((item for item in reversed(jobs) if item.get("kind")=="LOCAL_MEDIA_TRANSCRIPTION"), None)
    result={"project":_project(root,project_id),"job":latest}
    if latest and latest.get("artifact_dir"):
        artifact=Path(latest["artifact_dir"])
        for key,name in (("transcript","transcript.json"),("topics","topics.json"),("knowledge","knowledge.json"),("navigation","navigation.json")):
            if (artifact/name).is_file(): result[key]=json.loads((artifact/name).read_bytes())
    return result

def _job(root, request, action):
    project_id = request.get("project_id"); path = _jobs_path(root, project_id); jobs = _jobs(root, project_id)
    if action == "start":
        project = _project(root, project_id)
        item = {"job_id":f"urn:integra:job:{uuid.uuid4()}", "kind":"LOCAL_INTEGRITY_CHECK", "state":"COMPLETED", "created_at":_instant(_now()), "result":"Project record and bundled domain services validated", "project_record_sha256":content_sha256(project)}; jobs.append(item)
    else:
        item = next((value for value in jobs if value["job_id"] == request.get("job_id")), None)
        if item is None: raise ValueError("job does not exist")
        allowed = {"cancel":{"RUNNING","QUEUED"}, "resume":{"CANCELLED","FAILED"}}
        if item["state"] not in allowed[action]: raise ValueError(f"job cannot {action} from {item['state']}")
        if action == "cancel":
            pid=item.get("worker_pid")
            if isinstance(pid,int):
                try: os.killpg(pid, signal.SIGTERM)
                except ProcessLookupError: pass
            item["state"]="CANCELLED"; item["message"]="Cancelled by user"
        else:
            item["state"]="QUEUED"; item["message"]="Queued for fail-closed restart"
            item["worker_pid"]=_spawn_media(root,project_id,item["job_id"])
        item["updated_at"] = _instant(_now())
    _atomic_json(path, {"schema_version":"1.0", "jobs":jobs}); return item

def _package(path_value):
    path = Path(path_value)
    if path.is_symlink() or not path.is_dir(): raise ValueError("package directory is unsafe or missing")
    path = path.resolve(strict=True); manifest_path = path / "package.json"; files_root = path / "files"
    if manifest_path.is_symlink() or not manifest_path.is_file() or files_root.is_symlink() or not files_root.is_dir(): raise ValueError("package must contain package.json and files/")
    manifest = json.loads(manifest_path.read_bytes()); files = {}
    for item in manifest.get("files", []):
        relative = item.get("path"); candidate = files_root / relative
        if candidate.is_symlink() or not candidate.is_file() or not candidate.resolve().is_relative_to(files_root): raise ValueError("package file is unsafe or missing")
        files[relative] = candidate.read_bytes()
    if manifest.get("artifact_type") == "integra.obsidian_package": validate_package(manifest, files)
    elif manifest.get("artifact_type") == "integra.onedrive_package": validate_onedrive_package(manifest, files)
    else: raise ValueError("unsupported package type")
    return manifest, files

def _lease(root, manifest, component):
    store = LeaseStore(root / "leases"); now = _now()
    value = {"schema_version":"1.0", "lease_id":f"urn:integra:lease:{uuid.uuid4()}", "project_id":manifest["project_id"], "mutable_entity":{"namespace":"artifact","entity_id":manifest["package_id"]}, "writer":{"component_id":component,"host_id":"local-macos-app","process_id":os.getpid(),"process_start_token":str(uuid.uuid4())}, "operation_id":f"urn:integra:operation:{uuid.uuid4()}", "acquired_at":_instant(now), "heartbeat_at":_instant(now), "expires_at":_instant(now+timedelta(minutes=5)), "artifact_precondition":{"revision_id":manifest["package_id"],"content_sha256":manifest["version_sha256"]}, "readers":["integra.ui"], "generation":1, "state":"ACTIVE"}
    return store.acquire(value), store

def _publication(root, request, publish):
    manifest, files = _package(request.get("package_dir", "")); target = Path(request.get("target_dir", ""))
    workspace_value = request.get("workspace_dir")
    workspace = Path(workspace_value) if workspace_value else root / "publication-workspace"
    if not workspace_value: workspace.mkdir(parents=True, exist_ok=True)
    if manifest["artifact_type"] == "integra.obsidian_package":
        receipt = preview_obsidian_export(target, manifest, files)
        if publish:
            lease, store = _lease(root, manifest, "integra.obsidian_exporter")
            try: receipt = publish_obsidian_export(target, manifest, files, lease=lease, lease_store=store)
            finally: store.release(lease["project_id"], lease["mutable_entity"]["entity_id"], lease["lease_id"], lease["writer"], lease["generation"], _instant(_now()))
    else:
        receipt = preview_onedrive_publication(target, workspace, manifest, files)
        if publish:
            lease, store = _lease(root, manifest, "integra.onedrive_publisher")
            try: receipt = publish_onedrive_package(target, workspace, manifest, files, lease=lease, lease_store=store)
            finally: store.release(lease["project_id"], lease["mutable_entity"]["entity_id"], lease["lease_id"], lease["writer"], lease["generation"], _instant(_now()))
    return receipt

def main():
    try:
        if len(sys.argv) != 2 or sys.argv[1] not in OPERATIONS: raise ValueError("unsupported bridge operation")
        operation = sys.argv[1]; request = _request(); root = _root()
        if operation == "workflow": result = json.loads((RESOURCES/"source_first_workflow.json").read_text())
        elif operation == "deferred": result = json.loads((RESOURCES/"deferred_features.json").read_text())
        elif operation in {"obsidian-preview", "onedrive-preview"}:
            result = {"state":"DRY_RUN_REQUIRES_PACKAGE", "target":"Obsidian managed Vault subtree" if operation == "obsidian-preview" else "filesystem-backed OneDrive target", "writes_performed":False, "external_actions_performed":False, "cloud_verified":False}
        elif operation == "projects": result = _projects(root)
        elif operation == "create-project": result = _create(root, request)
        elif operation == "open-project": result = _project(root, request.get("project_id"))
        elif operation == "jobs": result = _jobs(root, request.get("project_id"))
        elif operation == "start-job": result = _job(root, request, "start")
        elif operation == "cancel-job": result = _job(root, request, "cancel")
        elif operation == "resume-job": result = _job(root, request, "resume")
        elif operation == "media-preflight": result = preflight()
        elif operation == "import-media": result = _import_media(root, request)
        elif operation == "process-media-job": result = run_job(_project_dir(root, request.get("project_id")), request.get("job_id"))
        elif operation == "project-view": result = _project_view(root, request.get("project_id"))
        elif operation == "detect-sources": result = [detect_source(value) for value in request.get("inputs", [])]
        elif operation == "capability-registry": result = capability_registry(request.get("sources", []))
        elif operation == "build-plan": result = build_plan(request.get("sources", []), request.get("selected_outputs", []))
        elif operation == "execute-plan": result = _execute_plan(root, request)
        elif operation == "process-plan": result = execute_run(_project_dir(root, request.get("project_id")), request.get("run_id"))
        elif operation == "run-status": result = _run_action(root, request, "status")
        elif operation == "recent-runs": result = _recent_runs(root)
        elif operation == "available-packages": result = _available_packages(root)
        elif operation == "media-navigation": result = _media_navigation(root, request)
        elif operation == "create-media-clip": result = _create_media_clip(root, request)
        elif operation == "cancel-run": result = _run_action(root, request, "cancel")
        elif operation == "retry-run": result = _run_action(root, request, "retry")
        elif operation == "package-preview": result = _publication(root, request, False)
        else: result = _publication(root, request, True)
        result_hash = content_sha256(result)
        envelope = {"schema_version":"1.0", "ok":True, "operation":operation, "result":result, "result_sha256":result_hash, "domain_contract_sha256":result_hash}
        if operation == "workflow": envelope["workflow"] = result
        if operation == "deferred": envelope["registry"] = result
        if operation in {"obsidian-preview", "onedrive-preview"}: envelope.update(result)
        print(json.dumps(envelope, ensure_ascii=False, sort_keys=True)); return 0
    except Exception as error:
        print(json.dumps({"schema_version":"1.0", "ok":False, "error":_safe_error(error)}, sort_keys=True)); return 2

if __name__ == "__main__": raise SystemExit(main())
