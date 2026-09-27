#!/usr/bin/env python3
"""Closed local bridge between the AppKit shell and accepted Integra services."""
from __future__ import annotations
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import fcntl, json, os, re, signal, subprocess, sys, tempfile, uuid
from pathlib import Path

RESOURCES = Path(__file__).resolve().parent
sys.path.insert(0, str(RESOURCES))
sys.path.insert(1, str(RESOURCES.parents[1]))
from integra_core.onedrive import build_onedrive_package, preview_onedrive_publication, publish_onedrive_package, validate_onedrive_package
from integra_core.project_lease import LeaseStore
from integra_core.protocol import canonical_json, content_sha256
from integra_core.publishing import preview_obsidian_export, publish_obsidian_export, validate_managed_package
from integra_core.user_media import _parse_srt, ffmpeg_preflight, import_source, preflight, run_job
from integra_core.capabilities import build_plan, capability_registry, detect_source
from integra_core.application_runtime import execute_run, prepare_run, prepare_transcript_translation_run, read_run, run_path
from integra_core.shutdown_runtime import cancel_run, reconcile_stale_runs, register_worker, requires_shutdown, run_with_timeout
from integra_core.seminartext_runtime import preflight as seminartext_preflight
from integra_core.seminartext_evidence_runtime import prepare_transcript_review, apply_human_transcript_review, prepare_topic_review_input

OPERATIONS = {"workflow", "deferred", "projects", "create-project", "open-project", "jobs", "start-job", "cancel-job", "resume-job", "import-media", "media-preflight", "seminartext-preflight", "process-media-job", "project-view", "detect-sources", "capability-registry", "build-plan", "execute-plan", "translate-transcript", "process-plan", "run-status", "recent-runs", "available-packages", "cancel-run", "retry-run", "media-navigation", "create-media-clip", "prepare-transcript-review", "apply-transcript-review", "prepare-topic-review", "prepare-process-topic-review", "apply-process-topic-review", "package-preview", "package-publish", "obsidian-preview", "onedrive-preview"}

OPERATIONS.add("build-reviewed-package")
OPERATIONS.add("transcript-text")
OPERATIONS.add("shutdown-active-runs")

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
    # A plan worker can persist progress while the bridge records its PID or a
    # cancellation request.  Each writer needs its own staging filename.
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
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
    environment["INTEGRA_RUN_ID"] = run_id; environment["INTEGRA_STAGE_ID"] = "plan"
    request=json.dumps({"project_id":project_id,"run_id":run_id}).encode()
    nonce=uuid.uuid4().hex
    path=run_path(_project_dir(root,project_id),run_id)
    diagnostics = path.parent / "diagnostics"; diagnostics.mkdir(parents=True, exist_ok=True)
    stdout = (diagnostics / (run_id.removeprefix("urn:integra:run:") + ".stdout.log")).open("wb")
    stderr = (diagnostics / (run_id.removeprefix("urn:integra:run:") + ".stderr.log")).open("wb")
    try:
        process=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),"process-plan","--integra-run-owner",nonce],stdin=subprocess.PIPE,stdout=stdout,stderr=stderr,env=environment,start_new_session=True)
    finally:
        stdout.close(); stderr.close()
    try:
        register_worker(path,process.pid,nonce)
        record=json.loads(path.read_bytes()); record["worker_pid"]=process.pid; _atomic_json(path,record)
        process.stdin.write(request); process.stdin.close()
    except Exception:
        process.terminate(); process.wait(timeout=5)
        raise
    return record


def _plan_timeout_seconds():
    raw = os.environ.get("INTEGRA_PLAN_TIMEOUT_SECONDS", "1800")
    try:
        value = float(raw)
    except (TypeError, ValueError) as error:
        raise ValueError("plan timeout must be a finite positive number") from error
    if value <= 0 or value != value or value == float("inf") or value > 7200:
        raise ValueError("plan timeout must be a finite positive number no greater than 7200 seconds")
    return value

def _execute_plan(root,request):
    with _run_lifecycle(root, wait=False):
        plan=request.get("plan"); name=request.get("name") or "Новая обработка"
        project=_create(root,{"name":name}); project_dir=_project_dir(root,project["project_id"])
        run=prepare_run(project_dir,plan,recognition_mode=request.get("recognition_mode","normal"),source_speech_language=request.get("source_speech_language","ru")); return {"project":project,"run":_spawn_plan(root,project["project_id"],run["run_id"])}

def _translate_transcript(root, request):
    with _run_lifecycle(root, wait=False):
        project_id = request.get("project_id")
        project_dir = _project_dir(root, _project(root, project_id)["project_id"])
        run = prepare_transcript_translation_run(project_dir, request.get("run_id"), request.get("source_id"),
                                                 request.get("translation_target_language", "en"))
        return {"project": _project(root, project_id), "run": _spawn_plan(root, project_id, run["run_id"])}

@contextmanager
def _run_lifecycle(root, *, wait):
    path=root/".run-lifecycle.lock"
    if path.is_symlink(): raise ValueError("Run lifecycle lock is unsafe")
    with path.open("a") as lock:
        try: fcntl.flock(lock,fcntl.LOCK_EX | (0 if wait else fcntl.LOCK_NB))
        except BlockingIOError as error: raise ValueError("Cannot start processing while shutdown is in progress") from error
        yield


def _reconcile_stale(root):
    with _run_lifecycle(root, wait=True):
        return reconcile_stale_runs(root)

def _run_action(root,request,action):
    _reconcile_stale(root)
    project_id=request.get("project_id"); project_dir=_project_dir(root,_project(root,project_id)["project_id"]); record=read_run(project_dir,request.get("run_id"))
    if action=="status": return record
    if action=="cancel":
        return cancel_run(project_dir, record["run_id"])
    if record["state"] not in {"FAILED","CANCELLED"}: raise ValueError("run cannot be retried from current state")
    with _run_lifecycle(root, wait=False):
        mode=record.get("recognition",{}).get("requested_mode","normal")
        language=record.get("source_speech_language",{}).get("requested","ru")
        new=prepare_run(project_dir,record["plan"],recognition_mode=mode,source_speech_language=language); return _spawn_plan(root,project_id,new["run_id"])

def _recent_runs(root, *, reconcile=True):
    if reconcile:
        _reconcile_stale(root)
    result=[]
    for project in _projects(root):
        directory=_project_dir(root,project["project_id"])/"runs"
        if not directory.is_dir() or directory.is_symlink(): continue
        for path in directory.glob("*.json"):
            if path.is_file() and not path.is_symlink(): result.append({"project":project,"run":json.loads(path.read_bytes())})
    return sorted(result,key=lambda item:item["run"].get("created_at",""),reverse=True)

def _shutdown_active_runs(root):
    with _run_lifecycle(root, wait=True):
        return _shutdown_active_runs_locked(root)

def _shutdown_active_runs_locked(root):
    reconcile_stale_runs(root)
    stopped=[]
    failures=[]
    for item in _recent_runs(root, reconcile=False):
        try:
            directory=_project_dir(root,item["project"]["project_id"])
            if not requires_shutdown(run_path(directory,item["run"]["run_id"]),item["run"]): continue
            record=cancel_run(directory,item["run"]["run_id"])
            stopped.append({"run_id":record["run_id"],"state":record["state"]})
        except Exception as error:
            failures.append(str(error))
    if failures: raise ValueError("; ".join(failures))
    return {"state":"SHUTDOWN_READY","runs":stopped}

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
    from integra_core.transcript_output import resolve_persisted_project_path
    media = resolve_persisted_project_path(project_dir, job.get("owned_path"), "owned media")
    subtitles = resolve_persisted_project_path(project_dir, outputs["subtitles"], "timed subtitles")
    segments = _parse_srt(subtitles.read_text(encoding="utf-8", errors="replace"), source_id)
    if not segments: raise ValueError("timed subtitles contain no navigable speech")
    return {"source_id":source_id,"media_path":str(media),"subtitles_path":str(subtitles),"segments":segments}

def _review_inputs(root, request):
    project_id=request.get("project_id"); source_id=request.get("source_id")
    if not isinstance(source_id,str) or not source_id: raise ValueError("source ID is required")
    project_dir=_project_dir(root,_project(root,project_id)["project_id"])
    run=read_run(project_dir,request.get("run_id"))
    result=next((item for item in run.get("source_results",[]) if item.get("source_id")==source_id),None)
    if not isinstance(result,dict) or result.get("state")!="COMPLETED": raise ValueError("completed source result is unavailable")
    outputs=result.get("outputs")
    if not isinstance(outputs,dict): raise ValueError("source outputs are unavailable")
    job=next((item for item in _jobs(root,project_id) if item.get("job_id")==result.get("job_id")),None)
    if not isinstance(job,dict) or job.get("source_id")!=source_id: raise ValueError("owned media job is unavailable")
    for key in ("transcript","word_timeline"):
        if not isinstance(outputs.get(key),str): raise ValueError("Transcript review requires the real TXT transcript and Word Timeline")
    from integra_core.transcript_output import resolve_persisted_project_path, resolve_transcript_text
    transcript = resolve_transcript_text(project_dir, source_id, outputs["transcript"])
    return {"project_dir":project_dir,"source_id":source_id,
            "media_path":str(resolve_persisted_project_path(project_dir, job.get("owned_path"), "owned media")),
            "transcript_path":transcript,
            "word_timeline_path":str(resolve_persisted_project_path(project_dir, outputs["word_timeline"], "Word Timeline"))}

def _transcript_text(root, request):
    from integra_core.transcript_output import resolve_transcript_text
    project = _project_dir(root, _project(root, request.get("project_id"))["project_id"])
    run = read_run(project, request.get("run_id"))
    source_id = request.get("source_id")
    source = next((item for item in run.get("source_results", []) if item.get("source_id") == source_id), None)
    if not isinstance(source, dict) or source.get("state") != "COMPLETED":
        raise ValueError("completed transcript source is unavailable")
    path = source.get("outputs", {}).get("transcript")
    if not isinstance(path, str): raise ValueError("transcript is unavailable")
    return {"path": resolve_transcript_text(project, source_id, path), "format": "txt"}

def _prepare_transcript_review(root, request):
    values=_review_inputs(root,request)
    return prepare_transcript_review(**values)

def _create_machine_evidence(root, request):
    from integra_core.seminartext_evidence_runtime import create_machine_evidence
    values = _review_inputs(root, request)
    result = create_machine_evidence(**values)
    _record_review_outputs(values["project_dir"], request.get("run_id"), values["source_id"], {
        "canonical_evidence": result["canonical_evidence_path"],
        "machine_evidence_record": result["evidence_result_path"],
    }, preserve_existing_evidence=True)
    return result

OPERATIONS.add("create-machine-evidence")

_EVIDENCE_DEPENDENTS = ("topic_review_drafts", "topic_review_package", "topic_review_decisions",
                        "reviewed_topics", "process_topic_review_package", "process_topic_review_decisions",
                        "process_reviewed_topics", "process_topic_review_receipt", "canonical_knowledge", "package_dir")
PROCESS_LOCAL_HUMAN_REVIEWER_ID = "integra-process-local-human"

def _record_review_outputs(project_dir, run_id, source_id, updates, *, preserve_existing_evidence=False,
                           expected_outputs=None):
    destination = run_path(project_dir, run_id)
    descriptor = os.open(destination.with_suffix(".review.lock"), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        run = read_run(project_dir, run_id)
        source = next((item for item in run.get("source_results", []) if item.get("source_id") == source_id), None)
        if not isinstance(source, dict) or source.get("state") != "COMPLETED":
            raise ValueError("completed source result is unavailable")
        outputs = source.setdefault("outputs", {})
        from integra_core.transcript_output import resolve_persisted_project_path
        for key, value in tuple(outputs.items()):
            if isinstance(value, str) and Path(value).is_absolute() and key in {"topics", "canonical_evidence", "machine_evidence_record", "topic_review_drafts",
                                                   "topic_review_package", "topic_review_decisions", "reviewed_topics",
                                                   "process_topic_review_package", "process_topic_review_decisions",
                                                   "process_reviewed_topics", "process_topic_review_receipt",
                                                   "reviewed_topics_markdown", "canonical_knowledge", "knowledge_markdown",
                                                   "package_dir"}:
                outputs[key] = str(resolve_persisted_project_path(project_dir, value, key))
        if expected_outputs is not None:
            expected_outputs = dict(expected_outputs)
            for key, value in tuple(expected_outputs.items()):
                if isinstance(value, str) and Path(value).is_absolute():
                    expected_outputs[key] = str(resolve_persisted_project_path(project_dir, value, key))
        if expected_outputs is not None and any(outputs.get(key) != value for key, value in expected_outputs.items()):
            raise ValueError("Review inputs changed during processing; refresh the source results")
        if preserve_existing_evidence and outputs.get("canonical_evidence") not in (None, updates.get("canonical_evidence")):
            raise ValueError("Existing Evidence cannot be replaced by machine Evidence")
        if ("canonical_evidence" in updates and outputs.get("canonical_evidence") is not None
                and outputs["canonical_evidence"] != updates["canonical_evidence"]
                and any(outputs.get(key) for key in _EVIDENCE_DEPENDENTS)):
            raise ValueError("Evidence has dependent review results; create a new run instead of replacing it")
        outputs.update(updates)
        _atomic_json(destination, run)

def _apply_transcript_review(root, request):
    values=_review_inputs(root,request)
    reviewer_id=request.get("reviewer_id")
    acknowledged=request.get("acknowledged")
    if not isinstance(reviewer_id,str) or not isinstance(acknowledged,bool): raise ValueError("reviewer confirmation is required")
    project_id=request.get("project_id"); run_id=request.get("run_id")
    run=read_run(values["project_dir"],run_id)
    source_result=next((item for item in run.get("source_results",[]) if item.get("source_id")==values["source_id"]),None)
    if not isinstance(source_result,dict): raise ValueError("completed source result is unavailable")
    outputs=source_result.setdefault("outputs",{})
    if any(outputs.get(key) for key in _EVIDENCE_DEPENDENTS):
        raise ValueError("Evidence has dependent review results; create a new run instead of replacing it")
    expected = {"canonical_evidence": outputs.get("canonical_evidence")}
    result=apply_human_transcript_review(**values,reviewer_id=reviewer_id,acknowledged=acknowledged,expected_request_sha256=request.get("expected_request_sha256", ""))
    outputs["canonical_evidence"]=result["seminartext"]["canonical_evidence_path"]
    outputs["transcript_review_result"]=result["review_result_path"]
    _record_review_outputs(values["project_dir"],run_id,values["source_id"],
        {key: outputs[key] for key in ("canonical_evidence", "transcript_review_result")}, expected_outputs=expected)
    return result

def _prepare_topic_review(root, request):
    values=_review_inputs(root,request); run_id=request.get("run_id")
    run=read_run(values["project_dir"],run_id)
    source_result=next((item for item in run.get("source_results",[]) if item.get("source_id")==values["source_id"]),None)
    outputs=source_result.get("outputs") if isinstance(source_result,dict) else None
    if not isinstance(outputs,dict) or not isinstance(outputs.get("canonical_evidence"),str) or not isinstance(outputs.get("topics"),str):
        raise ValueError("Topic review requires Canonical Evidence and real SeminarText topic drafts")
    from integra_core.transcript_output import resolve_persisted_project_path
    if Path(outputs["canonical_evidence"]).is_absolute():
        outputs["canonical_evidence"] = str(resolve_persisted_project_path(values["project_dir"], outputs["canonical_evidence"], "Canonical Evidence"))
    if Path(outputs["topics"]).is_absolute():
        outputs["topics"] = str(resolve_persisted_project_path(values["project_dir"], outputs["topics"], "topic drafts"))
    expected = {key: outputs.get(key) for key in ("canonical_evidence", "topics")}
    result=prepare_topic_review_input(values["project_dir"],source_id=values["source_id"],canonical_evidence_path=outputs["canonical_evidence"],topics_path=outputs["topics"])
    outputs["topic_review_drafts"]=result["topic_drafts_path"]
    _record_review_outputs(values["project_dir"],run_id,values["source_id"],
        {"topic_review_drafts": result["topic_drafts_path"]}, expected_outputs=expected)
    return result

def _process_topic_review(root, request, apply=False):
    """Bridge the Process UI to the pinned Topic review contract only.

    This intentionally records no Evidence or Knowledge output on the run.
    Source-bound machine evidence is a private contract-validation input inside
    the Process review package, never a user-facing authority transition.
    """
    from integra_core.seminartext_topic_review_runtime import (
        apply_process_topic_review, load_persisted_process_topic_review,
        prepare_process_topic_review,
    )
    values = _review_inputs(root, request)
    run_id = request.get("run_id")
    run = read_run(values["project_dir"], run_id)
    source = next((item for item in run.get("source_results", []) if item.get("source_id") == values["source_id"]), None)
    outputs = source.get("outputs") if isinstance(source, dict) else None
    if not isinstance(outputs, dict) or not isinstance(outputs.get("topics"), str):
        raise ValueError("real machine Topics are required")
    from integra_core.transcript_output import resolve_persisted_project_path
    if Path(outputs["topics"]).is_absolute():
        outputs["topics"] = str(resolve_persisted_project_path(values["project_dir"], outputs["topics"], "machine Topics"))
    expected = {"topics": outputs.get("topics")}
    if apply:
        result = apply_process_topic_review(values["project_dir"], source_id=values["source_id"],
            expected_package_sha256=request.get("expected_package_sha256"),
            reviewer_id=request.get("reviewer_id", PROCESS_LOCAL_HUMAN_REVIEWER_ID), decisions=request.get("decisions"))
        updates = {
            "process_reviewed_topics": result["reviewed_topics_contract_path"],
            "process_topic_review_receipt": result["process_topic_review_receipt_path"],
            "process_topic_review_decisions": result["decisions_path"],
        }
    else:
        persisted_keys = ("process_reviewed_topics", "process_topic_review_receipt",
                          "process_topic_review_decisions")
        persisted = {key: outputs.get(key) for key in persisted_keys}
        if any(value is not None for value in persisted.values()):
            if not all(isinstance(value, str) for value in persisted.values()):
                raise ValueError("persisted Process Topic review is incomplete")
            resolved = {key: str(resolve_persisted_project_path(values["project_dir"], value, key))
                        for key, value in persisted.items()}
            # Do not prepare a new package from the machine topic artifact once
            # a human Process review exists.  The runtime verifies the receipt,
            # decisions and reviewed contract before materializing it.
            return load_persisted_process_topic_review(values["project_dir"], source_id=values["source_id"],
                reviewed_topics_contract_path=resolved["process_reviewed_topics"],
                receipt_path=resolved["process_topic_review_receipt"],
                decisions_path=resolved["process_topic_review_decisions"])
        result = prepare_process_topic_review(values["project_dir"], source_id=values["source_id"],
            media_path=values["media_path"], transcript_path=values["transcript_path"],
            word_timeline_path=values["word_timeline_path"], topics_path=outputs["topics"])
        updates = {"process_topic_review_package": result["package_path"]}
    _record_review_outputs(values["project_dir"], run_id, values["source_id"], updates,
                           expected_outputs=expected)
    return result

def _knowledge_review(root, request, apply=False):
    from integra_core.seminartext_topic_review_runtime import prepare_topic_review, apply_topic_review
    values = _review_inputs(root, request)
    run = read_run(values["project_dir"], request.get("run_id"))
    source = next(item for item in run["source_results"] if item.get("source_id") == values["source_id"])
    outputs = source["outputs"]
    from integra_core.transcript_output import resolve_persisted_project_path
    for key, label in (("canonical_evidence", "Canonical Evidence"), ("topics", "topic drafts"),
                       ("topic_review_package", "topic review package")):
        if isinstance(outputs.get(key), str) and Path(outputs[key]).is_absolute():
            outputs[key] = str(resolve_persisted_project_path(values["project_dir"], outputs[key], label))
    expected = {key: outputs.get(key) for key in ("canonical_evidence", "topics", "topic_review_package")}
    if apply:
        result = apply_topic_review(values["project_dir"], source_id=values["source_id"],
            expected_package_sha256=request.get("expected_package_sha256"),
            reviewer_id=request.get("reviewer_id"), decisions=request.get("decisions"),
            boundaries_acknowledged=request.get("boundaries_acknowledged", False))
        if result["status"] == "REVIEWED_TOPICS_CREATED":
            outputs["reviewed_topics"] = result["reviewed_topics_path"]
            outputs["reviewed_topics_markdown"] = result["reviewed_topics_markdown_path"]
            keys = ("reviewed_topics", "reviewed_topics_markdown", "topic_review_decisions")
        else:
            outputs["canonical_knowledge"] = result["canonical_knowledge_path"]
            outputs["knowledge_markdown"] = result["knowledge_markdown_path"]
            keys = ("canonical_knowledge", "knowledge_markdown", "topic_review_decisions")
        outputs["topic_review_decisions"] = result["decisions_path"]
    else:
        if not isinstance(outputs.get("canonical_evidence"), str) or not isinstance(outputs.get("topics"), str):
            raise ValueError("reviewed Evidence and real topics are required")
        result = prepare_topic_review(values["project_dir"], source_id=values["source_id"],
            canonical_evidence_path=outputs["canonical_evidence"], topics_path=outputs["topics"])
        from integra_core.seminartext_evidence_runtime import _inside, _sha256
        media = _inside(Path(values["media_path"]), values["project_dir"], "review media")
        evidence = json.loads(Path(outputs["canonical_evidence"]).read_text(encoding="utf-8"))
        if _sha256(media) not in {item.get("content_sha256") for item in evidence.get("sources", [])}:
            raise ValueError("source media changed since Evidence was confirmed")
        result["media_path"] = str(media)
        outputs["topic_review_package"] = result["package_path"]
        keys = ("topic_review_package",)
    _record_review_outputs(values["project_dir"], request.get("run_id"), values["source_id"], {key: outputs[key] for key in keys}, expected_outputs=expected)
    return result

OPERATIONS.update({"prepare-knowledge-review", "apply-knowledge-review"})
OPERATIONS.update({"prepare-process-topic-review", "apply-process-topic-review"})

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
    clip=directory/f"clip_{int(start*1000):010d}_{int(end*1000):010d}_{uuid.uuid4().hex[:8]}.mp4"
    from integra_core.local_audio_clip import cut_media_compatible
    evidence = cut_media_compatible(Path(navigation["media_path"]), clip, start, end)
    _atomic_json(clip.with_suffix(".provenance.json"), evidence)
    manifest=directory/"clips.json"; current={"schema_version":"1.0","source_id":source_id,"source_path":navigation["media_path"],"subtitles_path":navigation["subtitles_path"],"clips":[]}
    if manifest.is_file() and not manifest.is_symlink(): current=json.loads(manifest.read_bytes())
    record={"path":str(clip),"start_seconds":start,"end_seconds":end,"locator":f"media:{source_id}#t={start:.3f},{end:.3f}","provenance_path":str(clip.with_suffix(".provenance.json"))}
    current["clips"]=[item for item in current.get("clips",[]) if item.get("path")!=str(clip)]+[record]; _atomic_json(manifest,current)
    _record_review_outputs(project_dir,run_id,source_id,
        {"clips_manifest":str(manifest), f"clip_{int(start*1000)}_{int(end*1000)}":str(clip)})
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

def _build_reviewed_package(root, request):
    from integra_core.reviewed_result_package import build_reviewed_result_package
    values = _review_inputs(root, request)
    project = values["project_dir"]
    run = read_run(project, request["run_id"])
    outputs = next(item["outputs"] for item in run["source_results"] if item["source_id"] == values["source_id"])
    expected = {key: outputs.get(key) for key in ("canonical_evidence", "topic_review_decisions")}
    decisions = outputs.get("topic_review_decisions")
    if not isinstance(decisions, str):
        raise ValueError("explicit persisted topic decisions are required before packaging")
    manifest, files = build_reviewed_result_package(project_dir=project, source_id=values["source_id"],
        decisions_path=decisions, project_id=request["project_id"],
        project_slug=request["project_id"].removeprefix("urn:integra:project:"))
    exports = project / "reviewed-exports"
    if exports.is_symlink(): raise ValueError("export directory must not be a symlink")
    exports.mkdir(exist_ok=True)
    target = exports / manifest["version_sha256"]
    descriptor = os.open(exports / ".package.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        if target.exists() or target.is_symlink():
            previous, previous_files = _package(str(target))
            if previous != manifest or previous_files != files:
                raise ValueError("existing reviewed export differs")
        else:
            with tempfile.TemporaryDirectory(prefix=".package-", dir=exports) as temporary:
                stage = Path(temporary)
                for name, payload in files.items():
                    destination = stage / "files" / name
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(payload)
                (stage / "package.json").write_bytes(canonical_json(manifest) + b"\n")
                _package(str(stage))
                os.rename(stage, target)
    finally:
        os.close(descriptor)
    _record_review_outputs(project, request["run_id"], values["source_id"], {"package_dir": str(target)}, expected_outputs=expected)
    return {"status": "PACKAGE_CREATED", "package_dir": str(target), "package_id": manifest["package_id"],
            "result_kind": manifest["result_kind"], "published": False}


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
    if manifest.get("artifact_type") in {"integra.obsidian_package", "integra.reviewed_result_package"}: validate_managed_package(manifest, files)
    elif manifest.get("artifact_type") == "integra.onedrive_package": validate_onedrive_package(manifest, files)
    else: raise ValueError("unsupported package type")
    return manifest, files

def _lease(root, manifest, component):
    store = LeaseStore(root / "leases"); now = _now()
    value = {"schema_version":"1.0", "lease_id":f"urn:integra:lease:{uuid.uuid4()}", "project_id":manifest["project_id"], "mutable_entity":{"namespace":"artifact","entity_id":manifest["package_id"]}, "writer":{"component_id":component,"host_id":"local-macos-app","process_id":os.getpid(),"process_start_token":str(uuid.uuid4())}, "operation_id":f"urn:integra:operation:{uuid.uuid4()}", "acquired_at":_instant(now), "heartbeat_at":_instant(now), "expires_at":_instant(now+timedelta(minutes=5)), "artifact_precondition":{"revision_id":manifest["package_id"],"content_sha256":manifest["version_sha256"]}, "readers":["integra.ui"], "generation":1, "state":"ACTIVE"}
    return store.acquire(value), store

def _publication(root, request, publish):
    manifest, files = _package(request.get("package_dir", "")); target = Path(request.get("target_dir", ""))
    destination = request.get("publication_target")
    if destination not in {None, "obsidian", "onedrive"}:
        raise ValueError("unsupported publication target")
    if destination == "obsidian" and manifest["artifact_type"] == "integra.onedrive_package":
        raise ValueError("select an Obsidian or reviewed-result source package")
    if destination == "onedrive" and manifest["artifact_type"] != "integra.onedrive_package":
        manifest, files = build_onedrive_package(manifest, files, created_at=manifest["created_at"])
    workspace_value = request.get("workspace_dir")
    workspace = Path(workspace_value) if workspace_value else root / "publication-workspace"
    if not workspace_value: workspace.mkdir(parents=True, exist_ok=True)
    if manifest["artifact_type"] in {"integra.obsidian_package", "integra.reviewed_result_package"}:
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
        owned_worker = (len(sys.argv) == 4 and sys.argv[1:3] == ["process-plan", "--integra-run-owner"]
                        and re.fullmatch(r"[a-f0-9]{32}", sys.argv[3]))
        if (len(sys.argv) != 2 and not owned_worker) or sys.argv[1] not in OPERATIONS: raise ValueError("unsupported bridge operation")
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
        elif operation == "seminartext-preflight": result = seminartext_preflight()
        elif operation == "import-media": result = _import_media(root, request)
        elif operation == "process-media-job": result = run_job(_project_dir(root, request.get("project_id")), request.get("job_id"))
        elif operation == "project-view": result = _project_view(root, request.get("project_id"))
        elif operation == "detect-sources": result = [detect_source(value) for value in request.get("inputs", [])]
        elif operation == "capability-registry": result = capability_registry(request.get("sources", []))
        elif operation == "build-plan": result = build_plan(request.get("sources", []), request.get("selected_outputs", []))
        elif operation == "execute-plan": result = _execute_plan(root, request)
        elif operation == "translate-transcript": result = _translate_transcript(root, request)
        elif operation == "process-plan":
            result = run_with_timeout(
                lambda: execute_run(_project_dir(root, request.get("project_id")), request.get("run_id")),
                _plan_timeout_seconds(),
            )
        elif operation == "run-status": result = _run_action(root, request, "status")
        elif operation == "recent-runs": result = _recent_runs(root)
        elif operation == "shutdown-active-runs": result = _shutdown_active_runs(root)
        elif operation == "available-packages": result = _available_packages(root)
        elif operation == "media-navigation": result = _media_navigation(root, request)
        elif operation == "create-media-clip": result = _create_media_clip(root, request)
        elif operation == "prepare-transcript-review": result = _prepare_transcript_review(root, request)
        elif operation == "create-machine-evidence": result = _create_machine_evidence(root, request)
        elif operation == "apply-transcript-review": result = _apply_transcript_review(root, request)
        elif operation == "prepare-topic-review": result = _prepare_topic_review(root, request)
        elif operation == "prepare-process-topic-review": result = _process_topic_review(root, request)
        elif operation == "apply-process-topic-review": result = _process_topic_review(root, request, True)
        elif operation == "prepare-knowledge-review": result = _knowledge_review(root, request)
        elif operation == "apply-knowledge-review": result = _knowledge_review(root, request, True)
        elif operation == "cancel-run": result = _run_action(root, request, "cancel")
        elif operation == "retry-run": result = _run_action(root, request, "retry")
        elif operation == "transcript-text": result = _transcript_text(root, request)
        elif operation == "build-reviewed-package": result = _build_reviewed_package(root, request)
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
