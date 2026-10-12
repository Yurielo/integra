"""Issue #236: synthetic two-unit execution input, never product acceptance.

Only a fresh governed disposable workspace can receive this fixture. Candidate
code is used only from a separate execution copy. No source demo is read, no
Candidate is built, and no K2 semantic decision is applied.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import uuid

from archive_execution_guard import require_execution_path
from qa_source_copy import _directory, _directories, _regular, read_verified_file, write_receipt, snapshot
from temp_workspace_lifecycle import MARKER, SCHEMA, _process_is_live

PURPOSE = "issue236-k2-fixture"
BASE = Path("/private/tmp" if sys.platform == "darwin" else "/tmp")
NAMESPACE = uuid.UUID("6b56971f-e539-54f9-a9c0-e3b2bdfe5383")
IDENTITY = {kind + "_id": "urn:integra:" + kind + ":" + str(uuid.uuid5(NAMESPACE, kind))
            for kind in ("project", "source", "run")}
PROJECT_UUID = IDENTITY["project_id"].split(":")[-1]
RUN_UUID = IDENTITY["run_id"].split(":")[-1]
TITLES = ("Солнечная панель: преобразование света", "Аккумулятор: хранение энергии")
MEDIA = b"INTEGRA SYNTHETIC QA ONLY; not playable media or production evidence\n"


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def payloads(project):
    """Stable identities/content; absolute locators bind only the isolated root."""
    tokens = (("Солнечная панель преобразует солнечный свет в электрическую энергию для питания приборов ".split() * 5)
              + ("Аккумулятор сохраняет электрическую энергию для последующего питания приборов без солнечного света ".split() * 5))
    midpoint = len(tokens) // 2
    topics = [{"title": title, "summary": title, "start_seconds": start + .1,
               "end_seconds": end + .8, "semantic_status": "REVIEW_REQUIRED"}
              for title, start, end in ((TITLES[0], 0, midpoint - 1),
                                        (TITLES[1], midpoint, len(tokens) - 1))]
    job = "urn:integra:job:" + str(uuid.uuid5(NAMESPACE, "job"))
    return {
        "source.mp4": MEDIA,
        "transcript.txt": (" ".join(tokens) + "\n").encode(),
        "timeline.json": encoded({"model": {"id": "synthetic-qa", "revision": "issue236-v1", "weights_sha256": "0" * 64},
            "aligner": {"name": "synthetic-qa", "version": "1"},
            "words": [{"text": word, "start_seconds": index + .1, "end_seconds": index + .8,
                       "alignment_status": "ALIGNED"} for index, word in enumerate(tokens)]}),
        "topics.json": encoded({"component": "seminartext", "topics": topics}),
        "project.json": encoded({"project_id": IDENTITY["project_id"], "name": "SYNTHETIC QA ONLY — Issue 236"}),
        "jobs.json": encoded({"jobs": [{"job_id": job, "source_id": IDENTITY["source_id"],
            "owned_path": str(project / "source.mp4"), "source_sha256": hashlib.sha256(MEDIA).hexdigest()}]}),
        "runs/" + RUN_UUID + ".json": encoded({"run_id": IDENTITY["run_id"], "state": "COMPLETED",
            "source_results": [{"source_id": IDENTITY["source_id"], "job_id": job, "state": "COMPLETED",
                "outputs": {key: str(project / file) for key, file in
                            (("transcript", "transcript.txt"), ("word_timeline", "timeline.json"), ("topics", "topics.json"))}}]}),
        "QA_ONLY.json": encoded({"issue": 236, "synthetic": True, "production_acceptance": False,
                                  "upstream_processing": False, "identity": IDENTITY}),
    }


def workspace_fd(workspace, *, purpose=PURPOSE):
    """No-follow, live-owner validation before any fixture output is created."""
    if workspace.parent != BASE or not workspace.name.startswith("integra-owned-" + purpose + "-"):
        raise ValueError("fixture requires the exact disposable lifecycle workspace")
    fd = _directory(workspace)
    try:
        metadata = os.fstat(fd)
        if metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o700:
            raise ValueError("fixture workspace must be exclusive current-user owned")
        marker_fd, record = _regular(fd, MARKER)
        os.close(marker_fd)
        marker = json.loads(read_verified_file(workspace, MARKER, record,
                                              expected_root=(metadata.st_dev, metadata.st_ino)))
        required = {"schema_version", "artifact_type", "root", "purpose", "created_at", "run_id",
                    "expected_bytes", "reserve_bytes", "owner", "child", "state", "events"}
        if (set(marker) != required or marker["schema_version"] != SCHEMA
                or marker["artifact_type"] != "integra.disposable_workspace"
                or marker["root"] != str(workspace) or marker["purpose"] != purpose
                or not _process_is_live(marker["owner"])):
            raise ValueError("fixture workspace ownership/purpose must be live and exact")
        return fd
    except BaseException:
        os.close(fd)
        raise


def prepare(workspace, *, purpose=PURPOSE):
    fd = workspace_fd(workspace, purpose=purpose)
    try:
        # Exclusive mkdir refuses an existing project, file, link or foreign data.
        os.mkdir("projects", 0o700, dir_fd=fd)
        projects = _directories(fd, ("projects",))
        try:
            os.mkdir(PROJECT_UUID, 0o700, dir_fd=projects)
            project_fd = _directories(projects, (PROJECT_UUID,))
            try:
                os.mkdir("runs", 0o700, dir_fd=project_fd)
                project = workspace / "projects" / PROJECT_UUID
                for relative, content in payloads(project).items():
                    parent_fd = _directories(project_fd, Path(relative).parts[:-1])
                    try:
                        metadata = os.fstat(parent_fd)
                        write_receipt(project / relative, content,
                                      expected_parent=(metadata.st_dev, metadata.st_ino))
                    finally:
                        os.close(parent_fd)
            finally:
                os.close(project_fd)
        finally:
            os.close(projects)
    finally:
        os.close(fd)
    # No symlink is generated or admitted. Inventory also rejects special files.
    inventory = snapshot(project, ())
    if inventory.get("links"):
        raise ValueError("synthetic fixture must remain symlink-free")
    return project


def relation_input(prepared, fragments):
    concepts = [p for p in prepared["proposals"] if p["entity_kind"] == "concepts"]
    if len(concepts) < 2 or len({p["after"]["id"] for p in concepts}) < 2:
        raise ValueError("QA_FIXTURE_COVERAGE_GAP: two distinct Concept endpoints required")
    return dict(source_concept_id=concepts[0]["after"]["id"], target_concept_id=concepts[1]["after"]["id"],
                relation_type="associated_with", fragment_ids=list(fragments))


def exercise(bridge):
    """Observe actual reviewed units and Relation proposal; never apply K2."""
    opened = bridge("knowledge-open", dict(IDENTITY, create=True))
    decisions = [{"topic_id": topic["id"], "action": "ACCEPT",
                  "reason": "SYNTHETIC QA ONLY; not Product Owner semantic acceptance"}
                 for topic in opened["topics"]]
    reviewed = bridge("knowledge-save", dict(IDENTITY, expected_state_sha256=opened["state_sha256"],
        decisions=decisions, reviewer_id="synthetic-issue236-qa-only"))
    units = reviewed["reviewed"]["semantic_knowledge"]
    if reviewed["status"] != "REVIEWED_FRAGMENTS_V2" or len(units) < 2 or len({u["title"] for u in units}) < 2:
        raise ValueError("QA_FIXTURE_COVERAGE_GAP: two distinct reviewed units required")
    opened_k2 = bridge("knowledge-k2-open", IDENTITY)
    fragments = [item["id"] for item in opened_k2["eligible_fragments"]]
    request = dict(IDENTITY, notebook_id=opened_k2["notebook_id"],
        expected_state_sha256=opened_k2["state_sha256"], selected_fragment_ids=fragments)
    prepared = bridge("knowledge-k2-prepare", request)
    concepts = [p for p in prepared["proposals"] if p["entity_kind"] == "concepts"]
    relation = relation_input(prepared, fragments)
    final = bridge("knowledge-k2-prepare", dict(request, relation_inputs=[relation]))
    relations = [p for p in final["proposals"] if p["entity_kind"] == "relations"]
    if (len(relations) != 1 or any(relations[0]["after"][key] != relation[key]
                                 for key in ("source_concept_id", "target_concept_id", "relation_type"))
            or any(p["review_status"] != "REVIEW_REQUIRED" for p in final["proposals"])
            or final["revision_sha256"] is not None):
        raise ValueError("Relation QA must produce exact provisional endpoints without semantic apply")
    if bridge("knowledge-k2-prepare", dict(request, relation_inputs=[relation])) != final:
        raise ValueError("fixture proposal preparation is not deterministic")
    return {"reviewed_units": len(units), "concepts": len(concepts), "relations": len(relations),
            "package_sha256": final["package_sha256"], "relation": relation,
            "qa_only": True, "semantic_product_acceptance": False, "k2_applied": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=Path, required=True, help="separate owned execution copy only")
    args = parser.parse_args()
    workspace = Path(os.environ.get("INTEGRA_OWNED_WORKSPACE", ""))
    fd = workspace_fd(workspace)
    os.close(fd)
    require_execution_path(args.app)
    app = args.app.resolve(strict=True)
    if not app.is_relative_to(workspace / "execution"):
        raise ValueError("Candidate must execute only from this owned workspace/execution copy")
    resources = app / "Contents/Resources"
    manifest_before = (resources / "candidate-manifest.json").read_bytes()
    project = prepare(workspace)
    environment = {k: v for k, v in os.environ.items() if not k.startswith("INTEGRA_") and k != "PYTHONPATH"}
    environment.update(INTEGRA_APP_DATA_ROOT=str(workspace), PYTHONDONTWRITEBYTECODE="1")

    def bridge(operation, request):
        reply = subprocess.run(["/usr/bin/python3", "-B", str(resources / "bridge.py"), operation],
            input=json.dumps(request), capture_output=True, text=True, env=environment, check=True, timeout=180)
        value = json.loads(reply.stdout)
        if not value.get("ok"):
            raise ValueError(value)
        return value["result"]

    result = exercise(bridge)
    if (resources / "candidate-manifest.json").read_bytes() != manifest_before:
        raise ValueError("execution-copy manifest changed")
    result.update(candidate_id=json.loads(manifest_before)["candidate_id"], project=str(project), identity=IDENTITY,
                  manifest_digest=hashlib.sha256(manifest_before).hexdigest())
    metadata = workspace.stat()
    write_receipt(workspace / "issue236-qa.json", encoded(result), expected_parent=(metadata.st_dev, metadata.st_ino))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
