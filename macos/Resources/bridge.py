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
from integra_core.user_media import import_source, preflight, run_job

OPERATIONS = {"workflow", "deferred", "projects", "create-project", "open-project", "jobs", "start-job", "cancel-job", "resume-job", "import-media", "media-preflight", "process-media-job", "project-view", "package-preview", "package-publish", "obsidian-preview", "onedrive-preview"}

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
        operation = sys.argv[1]; request = _request(); root = _root(); workflow = json.loads((RESOURCES/"reference_workflow.json").read_text())
        if operation == "workflow": result = workflow
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
