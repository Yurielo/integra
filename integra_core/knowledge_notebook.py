"""K1 downstream notebook over persisted Process and existing fragment review.

The working state stores user choices (including DEFER); only a complete explicit
review is applied through Topic Review V2. Nothing here executes Process or
compiles Canonical Knowledge. Publication uses reviewed_result_package unchanged.
"""
from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import re
import tempfile

from .application_runtime import run_path
from .identity import derive_imported_id
from .protocol import canonical_json, content_sha256
from .seminartext_evidence_runtime import _inside, _review_root, _sha256, _alignment, create_machine_evidence
from .seminartext_topic_review_runtime import _locked, prepare_topic_review, apply_topic_review
from .transcript_output import resolve_persisted_project_path, resolve_transcript_text


def source_inputs(project_dir, *, project_id, run_id, source_id):
    """Strict read-only eligibility; never reconcile or regenerate a Process run."""
    root = Path(project_dir).resolve(strict=True)
    project = json.loads(_inside(root / "project.json", root, "project").read_bytes())
    if project.get("project_id") != project_id:
        raise ValueError("Knowledge project identity differs")
    run = json.loads(run_path(root, run_id).read_bytes())
    if run.get("run_id") != run_id or run.get("state") != "COMPLETED":
        raise ValueError("Knowledge requires a completed Process run")
    sources = [item for item in run.get("source_results", []) if item.get("source_id") == source_id]
    if len(sources) != 1 or sources[0].get("state") != "COMPLETED":
        raise ValueError("completed Process source is unavailable")
    result = sources[0]
    jobs = json.loads(_inside(root / "jobs.json", root, "jobs").read_bytes()).get("jobs", [])
    matched = [item for item in jobs if item.get("job_id") == result.get("job_id")]
    if len(matched) != 1 or matched[0].get("source_id") != source_id:
        raise ValueError("Process source/job identity differs")
    job = matched[0]
    outputs = result.get("outputs", {})
    if not isinstance(outputs, dict):
        raise ValueError("Process outputs are missing")
    paths = {"media": resolve_persisted_project_path(root, job.get("owned_path"), "source media")}
    for role in ("transcript", "word_timeline", "topics"):
        if not isinstance(outputs.get(role), str):
            raise ValueError("K1 requires saved transcript, Topics and Word Timeline; cue-only import is unavailable")
        paths[role] = resolve_persisted_project_path(root, outputs[role], role)
    for role in ("canonical_evidence", "machine_evidence_record"):
        if role in outputs:
            paths[role] = resolve_persisted_project_path(root, outputs[role], role)
    if not re.fullmatch(r"[a-f0-9]{64}", str(job.get("source_sha256", ""))):
        raise ValueError("Process has no verified source revision/hash")
    if _sha256(paths["media"]) != job["source_sha256"]:
        raise ValueError("source media hash/revision changed")
    topics = json.loads(paths["topics"].read_bytes())
    if topics.get("component") != "seminartext" or not topics.get("topics"):
        raise ValueError("compatible persisted Topics are unavailable")
    # Check timing presence before any Evidence preparation. Detailed cross-record
    # validation remains the existing pinned Evidence/review adapter's job.
    timeline = json.loads(paths["word_timeline"].read_bytes())
    if not isinstance(timeline.get("words"), list) or not timeline["words"]:
        raise ValueError("saved Word Timeline timing is missing")
    binding = {"project_id": project_id, "run_id": run_id, "source_id": source_id,
               "job_id": job["job_id"], "source_revision_sha256": job["source_sha256"],
               "artifacts": {role: {"path": path.relative_to(root).as_posix(), "sha256": _sha256(path)}
                             for role, path in paths.items()}}
    return root, paths, binding, result


def _state_path(root, source_id, notebook_id):
    token = notebook_id.removeprefix("urn:integra:artifact:")
    if not re.fullmatch(r"[a-f0-9-]{36}", token):
        raise ValueError("invalid notebook identity")
    return _review_root(root, source_id) / "knowledge" / (token + ".json")


def _read_state(path, root):
    state = json.loads(_inside(path, root, "Knowledge notebook").read_bytes())
    if (state.get("artifact_type") != "integra.knowledge_notebook_v1"
            or state.get("state_sha256") != content_sha256({key: value for key, value in state.items()
                                                          if key != "state_sha256"})):
        raise ValueError("Knowledge notebook receipt changed")
    return state


def _persist(path, state):
    if path.parent.is_symlink() or path.is_symlink():
        raise ValueError("unsafe Knowledge notebook path")
    path.parent.mkdir(parents=True, exist_ok=True)
    state = {key: value for key, value in state.items() if key != "state_sha256"}
    state["state_sha256"] = content_sha256(state)
    with tempfile.TemporaryDirectory(prefix=".notebook-", dir=path.parent) as directory:
        staged = Path(directory) / "state.json"
        staged.write_bytes(canonical_json(state) + b"\n")
        with staged.open("rb") as stream:
            os.fsync(stream.fileno())
        os.replace(staged, path)
    return state


def _validate(root, state, binding):
    if state["source_binding"] != binding:
        raise ValueError("Knowledge source/transcript/Topic revision is stale")
    for role, ref in state["review_artifacts"].items():
        path = _inside(root / ref["path"], root, role)
        if _sha256(path) != ref["sha256"]:
            raise ValueError(f"Knowledge {role} hash/receipt changed")
    evidence = json.loads((root / state["review_artifacts"]["evidence"]["path"]).read_bytes())
    source_hash = binding["source_revision_sha256"]
    canonical_source_id = "source_source_" + hashlib.sha256(binding["source_id"].encode()).hexdigest()[:24]
    source = next((item for item in evidence.get("sources", []) if item.get("id") == canonical_source_id), None)
    if not source or source.get("content_sha256") != source_hash:
        raise ValueError("Knowledge Evidence source revision differs")
    revisions = [item for item in evidence.get("transcript_revisions", []) if item.get("source_id") == canonical_source_id]
    transcript = resolve_transcript_text(root, binding["source_id"], str(root / binding["artifacts"]["transcript"]["path"]))
    if len(revisions) != 1 or " ".join(revisions[0]["canonical_text"].split()) != " ".join(Path(transcript).read_text().split()):
        raise ValueError("Knowledge Evidence transcript revision differs")
    transcript_hash = _sha256(Path(transcript))
    if revisions[0].get("text_sha256") != transcript_hash:
        raise ValueError("Knowledge Evidence transcript exact hash differs")
    alignment = _alignment(json.loads((root / binding["artifacts"]["word_timeline"]["path"]).read_bytes()))
    config_hash = content_sha256(alignment["config"])
    expected = {"source_id": canonical_source_id, "transcript_revision_id": revisions[0]["id"],
                "source_content_sha256": source_hash, "transcript_text_sha256": transcript_hash,
                "config_sha256": config_hash, "status": "valid",
                **{key: alignment[key] for key in ("aligner", "aligner_version", "model", "model_revision", "model_sha256")}}
    if not any(all(run.get(key) == value for key, value in expected.items()) for run in evidence.get("alignment_runs", [])):
        raise ValueError("Knowledge Evidence is stale relative to saved Word Timeline")
    return evidence


def _presentation(root, state, binding):
    evidence = _validate(root, state, binding)
    package_path = root / state["review_artifacts"]["package"]["path"]
    package = json.loads(package_path.read_bytes())
    words = {word["id"]: word for word in evidence["words"]}
    revisions = {revision["id"]: revision for revision in evidence["transcript_revisions"]}
    topics = []
    for topic in package["topics"]:
        first, last = words[topic["word_start_id"]], words[topic["word_end_id"]]
        text = revisions[topic["transcript_revision_id"]]["canonical_text"]
        topics.append({"id": topic["id"], "title": topic["proposed_title"], "summary": topic["proposed_summary"],
                       "quote": topic["quote"], "context": text[max(0, first["char_start"]-100):last["char_end"]+100],
                       "word_start_id": first["id"], "word_end_id": last["id"],
                       "start_seconds": topic["locator"]["start_seconds"],
                       "end_seconds": topic["locator"]["end_seconds"],
                       "transcript_revision_id": topic["transcript_revision_id"],
                       "evidence_refs": topic["evidence_refs"]})
    reviewed = None
    if state["status"] == "REVIEWED_FRAGMENTS_V2":
        result_ref = state["review_artifacts"]["reviewed_topics"]
        reviewed = json.loads((root / result_ref["path"]).read_bytes())
    return {"notebook_id": state["notebook_id"], "state_sha256": state["state_sha256"],
            "status": state["status"], "automatic_acceptance": False,
            "semantic_authority": "REVIEWED_FRAGMENTS_ONLY_NOT_CANONICAL_KNOWLEDGE",
            "precision": "WORD_RANGE", "project_id": binding["project_id"], "run_id": binding["run_id"],
            "source_id": binding["source_id"], "source_revision_sha256": binding["source_revision_sha256"],
            "transcript_revisions": evidence["transcript_revisions"],
            "package_sha256": state["review_artifacts"]["package"]["sha256"],
            "topics": topics, "decisions": state["choices"], "reviewed": reviewed,
            "upstream_processing_performed": False}


def open_notebook(project_dir, *, project_id, run_id, source_id, create=False):
    root, paths, binding, result = source_inputs(project_dir, project_id=project_id, run_id=run_id, source_id=source_id)
    notebook_id = derive_imported_id("artifact", "integra.knowledge_k1", project_id, content_sha256(binding))
    path = _state_path(root, source_id, notebook_id)
    if path.exists():
        return _presentation(root, _read_state(path, root), binding)
    if not create:
        raise ValueError("Knowledge notebook has not been added")
    outputs = result["outputs"]
    if isinstance(outputs.get("canonical_evidence"), str):
        evidence = resolve_persisted_project_path(root, outputs["canonical_evidence"], "Evidence")
    else:
        created = create_machine_evidence(root, source_id=source_id, media_path=str(paths["media"]),
            transcript_path=resolve_transcript_text(root, source_id, str(paths["transcript"])),
            word_timeline_path=str(paths["word_timeline"]))
        evidence = Path(created["canonical_evidence_path"])
    package = prepare_topic_review(root, source_id=source_id, canonical_evidence_path=str(evidence),
                                   topics_path=str(paths["topics"]), exact_fragments=True)
    refs = {"evidence": evidence, "package": Path(package["package_path"]),
            "binding": Path(package["package_path"]).parent.parent / "binding.json"}
    # Source files could have changed while the adapter prepared its snapshot.
    if source_inputs(root, project_id=project_id, run_id=run_id, source_id=source_id)[2] != binding:
        raise ValueError("Process source changed during Knowledge preparation")
    state = {"schema_version": "1.0", "artifact_type": "integra.knowledge_notebook_v1",
             "notebook_id": notebook_id, "source_binding": binding, "status": "REVIEW_REQUIRED",
             "choices": [], "review_artifacts": {role: {"path": value.relative_to(root).as_posix(),
                    "sha256": _sha256(value)} for role, value in refs.items()}}
    with _locked(root, source_id):
        if path.exists():
            state = _read_state(path, root)
        else:
            _validate(root, state, binding)
            state = _persist(path, state)
    return _presentation(root, state, binding)


def save_notebook(project_dir, *, project_id, run_id, source_id, expected_state_sha256, decisions, reviewer_id):
    current = open_notebook(project_dir, project_id=project_id, run_id=run_id, source_id=source_id)
    root, _, binding, _ = source_inputs(project_dir, project_id=project_id, run_id=run_id, source_id=source_id)
    path = _state_path(root, source_id, current["notebook_id"])
    if current["state_sha256"] != expected_state_sha256:
        raise ValueError("Knowledge notebook changed; reopen before saving")
    if not isinstance(reviewer_id, str) or not re.fullmatch(r"[a-z][a-z0-9._:-]{2,127}", reviewer_id):
        raise ValueError("stable reviewer identity is required")
    if not isinstance(decisions, list) or len(decisions) != len(current["topics"]):
        raise ValueError("each fragment needs an explicit choice, including defer")
    by_id = {item["id"]: item for item in current["topics"]}
    chosen = set()
    for choice in decisions:
        if (not isinstance(choice, dict) or choice.get("topic_id") not in by_id
                or choice["topic_id"] in chosen or choice.get("action") not in {"ACCEPT", "EDIT", "RENAME", "REJECT", "DEFER"}
                or not isinstance(choice.get("reason"), str) or not choice["reason"].strip()):
            raise ValueError("invalid or duplicate explicit fragment choice")
        chosen.add(choice["topic_id"])
    choices = sorted(decisions, key=lambda item: item["topic_id"])
    with _locked(root, source_id):
        state = _read_state(path, root)
        _validate(root, state, binding)
        if state["state_sha256"] != expected_state_sha256:
            raise ValueError("Knowledge notebook changed; reopen before saving")
        if state["status"] == "REVIEWED_FRAGMENTS_V2":
            if state["choices"] == choices and state.get("reviewer_id") == reviewer_id:
                return _presentation(root, state, binding)
            raise ValueError("completed fragment decisions are immutable")
        state.update(choices=choices, reviewer_id=reviewer_id, status="REVIEW_REQUIRED")
        state = _persist(path, state)
    if any(choice["action"] == "DEFER" for choice in choices):
        return _presentation(root, state, binding)
    # apply_topic_review owns the same existing review lock. A crash after the
    # apply is recoverable by replaying the identical persisted choices.
    applied = apply_topic_review(root, source_id=source_id, expected_package_sha256=current["package_sha256"],
        reviewer_id=reviewer_id, decisions=choices, boundaries_acknowledged=True)
    if applied.get("status") != "REVIEWED_TOPICS_CREATED":
        raise ValueError("K1 must remain reviewed fragments, never Canonical Knowledge")
    with _locked(root, source_id):
        latest = _read_state(path, root)
        if latest["state_sha256"] != state["state_sha256"]:
            raise ValueError("Knowledge review changed during application")
        for role in ("reviewed_topics", "reviewed_topics_markdown", "decisions", "review_result"):
            value = _inside(Path(applied[role + "_path"]), root, role)
            latest["review_artifacts"][role] = {"path": value.relative_to(root).as_posix(), "sha256": _sha256(value)}
        latest["status"] = "REVIEWED_FRAGMENTS_V2"
        state = _persist(path, latest)
    return _presentation(root, state, binding)


def notebook_navigation(project_dir, *, project_id, run_id, source_id, fragment_id, notebook_id=None):
    opened = open_notebook(project_dir, project_id=project_id, run_id=run_id, source_id=source_id)
    if notebook_id is not None and notebook_id != opened["notebook_id"]:
        raise ValueError("source link belongs to a different notebook/transcript revision")
    root, paths, _, _ = source_inputs(project_dir, project_id=project_id, run_id=run_id, source_id=source_id)
    reviewed = opened.get("reviewed")
    if reviewed:
        fragments = reviewed["fragment_lineage"]
        fragment = next((item for item in fragments if item["id"] == fragment_id), None)
        if fragment is None:
            raise ValueError("reviewed fragment identity is unavailable")
        locator = fragment["locator"]
    else:
        fragment = next((item for item in opened["topics"] if item["id"] == fragment_id), None)
        if fragment is None:
            raise ValueError("fragment identity is unavailable")
        locator = {"start_seconds": fragment["start_seconds"], "end_seconds": fragment["end_seconds"]}
    return {"media_path": str(paths["media"]), "fragment_id": fragment_id, "source_id": source_id,
            "source_revision_sha256": opened["source_revision_sha256"], "precision": "WORD_RANGE",
            "transcript_revision_id": fragment["transcript_revision_id"],
            "word_start_id": fragment["word_start_id"], "word_end_id": fragment["word_end_id"],
            "quote": fragment["quote"], "start_seconds": locator["start_seconds"], "end_seconds": locator["end_seconds"]}


def notebook_package(project_dir, *, project_id, run_id, source_id):
    from .reviewed_result_package import build_reviewed_result_package
    opened = open_notebook(project_dir, project_id=project_id, run_id=run_id, source_id=source_id)
    if opened["status"] != "REVIEWED_FRAGMENTS_V2":
        raise ValueError("deferred/unreviewed fragments cannot be exported as reviewed")
    root = Path(project_dir).resolve(strict=True)
    state = _read_state(_state_path(root, source_id, opened["notebook_id"]), root)
    return build_reviewed_result_package(project_dir=root, source_id=source_id,
        decisions_path=str(root / state["review_artifacts"]["decisions"]["path"]), project_id=project_id,
        project_slug=project_id.removeprefix("urn:integra:project:"), navigation_context={
            "project_id": project_id, "run_id": run_id, "source_id": source_id,
            "source_revision_sha256": opened["source_revision_sha256"], "notebook_id": opened["notebook_id"]})
