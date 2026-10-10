"""Full K2 packaged proof on the accepted #236 disposable synthetic fixture."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

if sys.flags.optimize:
    raise ValueError("optimized Python is forbidden")
REPO = Path("/private/tmp/integra-issue-228-retention-repair")
sys.path.insert(0, str(REPO / "scripts"))
import k2_qa_fixture as fixture
from candidate_archive import verify_archive
from archive_execution_guard import require_execution_path

RECORD = Path.home() / "Library/Application Support/Integra/Retention Exceptions/issue-227-e6cd761-one-use"
EXPECTED = {k:v for k,v in json.loads((RECORD / "incoming-identity.json").read_bytes()).items()
            if k in {"candidate_id", "bundle_digest", "manifest_digest"}}
assert len(EXPECTED) == 3
workspace = Path(os.environ["INTEGRA_OWNED_WORKSPACE"])
fd = fixture.workspace_fd(workspace)
os.close(fd)
archive = Path.home() / "Library/Application Support/Integra/Build Archive" / EXPECTED["candidate_id"] / EXPECTED["bundle_digest"]
before = verify_archive(archive, EXPECTED)
app = workspace / "execution/Integra.app"
app.parent.mkdir(mode=0o700)
shutil.copytree(archive / "Integra.app", app, symlinks=True)
require_execution_path(app)
resources = app / "Contents/Resources"
manifest_bytes = (resources / "candidate-manifest.json").read_bytes()
manifest = json.loads(manifest_bytes)
assert hashlib.sha256(manifest_bytes).hexdigest() == EXPECTED["manifest_digest"]
assert manifest["candidate_id"] == EXPECTED["candidate_id"]
assert manifest["bundle"]["digest"] == EXPECTED["bundle_digest"]
env = {k: v for k, v in os.environ.items() if not k.startswith("INTEGRA_") and k != "PYTHONPATH"}
env.update(PYTHONDONTWRITEBYTECODE="1", INTEGRA_APP_DATA_ROOT=str(workspace / "self-test-data"),
           INTEGRA_OWNED_WORKSPACE=str(workspace))
diagnostics = []

def invoke(args, request=None, timeout=240, expected_exit=0):
    reply = subprocess.run(args, input=json.dumps(request, ensure_ascii=False) if request is not None else None,
        capture_output=True, text=True, env=env, timeout=timeout)
    record = dict(command=args, request=request, exit_status=reply.returncode,
        stdout=reply.stdout, stderr=reply.stderr,
        context=dict(cwd=os.getcwd(), app_data_root=env.get("INTEGRA_APP_DATA_ROOT"),
                     manifest_sha256=EXPECTED["manifest_digest"]))
    diagnostics.append(record)
    print("ISSUE227_PACKAGED_DIAGNOSTIC " + json.dumps(record, ensure_ascii=False, sort_keys=True), file=sys.stderr, flush=True)
    if reply.returncode != expected_exit:
        raise ValueError(record)
    return reply.stdout

validated = json.loads(invoke([sys.executable, "-B", str(REPO / "scripts/candidate_manifest.py"), "validate", str(app)], timeout=900))
assert validated["candidate_id"] == EXPECTED["candidate_id"] and validated["bundle"]["digest"] == EXPECTED["bundle_digest"]
schema = resources / "schemas/knowledge_view_v1.schema.json"
assert schema.read_bytes() == (Path("/private/tmp/integra-issue-227-k2") / "schemas/knowledge_view_v1.schema.json").read_bytes()
self_test = invoke([str(app / "Contents/MacOS/Integra"), "--self-test"])
project = fixture.prepare(workspace)
env["INTEGRA_APP_DATA_ROOT"] = str(workspace)
ids = fixture.IDENTITY

def bridge(operation, request):
    reply = json.loads(invoke(["/usr/bin/python3", "-B", str(resources / "bridge.py"), operation], request))
    if not reply.get("ok"):
        raise ValueError(reply)
    return reply["result"]

coverage = fixture.exercise(bridge)
assert coverage["reviewed_units"] >= 2 and coverage["concepts"] >= 2 and coverage["relations"] == 1
assert not coverage["k2_applied"] and not coverage["semantic_product_acceptance"]
launch_marker = workspace / "native-launch.txt"
env["INTEGRA_LAUNCH_PROBE"] = str(launch_marker)
invoke([str(app / "Contents/MacOS/Integra")], timeout=120)
native_launch = launch_marker.read_text().strip()
assert "LAUNCHED visible=true" in native_launch, native_launch
env.pop("INTEGRA_LAUNCH_PROBE")

def k2(operation, **kwargs):
    return bridge(operation, ids | kwargs)

opened = k2("knowledge-k2-open")
assert opened["revision_sha256"] is None and not opened["automatic_acceptance"]
fragments = [item["id"] for item in opened["eligible_fragments"]]
assert fragments
prepared = k2("knowledge-k2-prepare", notebook_id=opened["notebook_id"],
    expected_state_sha256=opened["state_sha256"], selected_fragment_ids=fragments)
concepts = [p for p in prepared["proposals"] if p["entity_kind"] == "concepts"]
assert len(concepts) >= 2 and len({p["after"]["id"] for p in concepts}) >= 2
relation = fixture.relation_input(prepared, fragments)
prepared = k2("knowledge-k2-prepare", notebook_id=opened["notebook_id"],
    expected_state_sha256=opened["state_sha256"], selected_fragment_ids=fragments, relation_inputs=[relation])
assert all(p["review_status"] == "REVIEW_REQUIRED" for p in prepared["proposals"])
negative = json.loads(invoke(["/usr/bin/python3", "-B", str(resources / "bridge.py"), "knowledge-k2-apply"],
    ids | dict(package_sha256=prepared["package_sha256"], decisions=[], reviewer_id="synthetic-qa-only",
        explicit_confirmation=False, confirmed_proposal_ids=prepared["confirmed_proposal_ids"]), expected_exit=2))
assert not negative.get("ok") and "confirmation" in json.dumps(negative)
assert k2("knowledge-k2-open")["revision_sha256"] is None
decisions = []
topic_index = 0
for proposal in prepared["proposals"]:
    decision = dict(proposal_id=proposal["id"], action="ACCEPT", reason="Isolated synthetic QA only; not Product Owner semantic authority")
    if proposal["entity_kind"] == "topics":
        decision["action"] = "REJECT" if topic_index == 0 else "DEFER"
        topic_index += 1
    if proposal["entity_kind"] == "concepts" and not any(d["action"] == "EDIT" for d in decisions):
        decision.update(action="EDIT", edited_fields={"preferred_label": "Synthetic QA edited concept"})
    decisions.append(decision)
assert {d["action"] for d in decisions} == {"ACCEPT", "EDIT", "REJECT", "DEFER"}
first = k2("knowledge-k2-apply", package_sha256=prepared["package_sha256"], decisions=decisions,
    reviewer_id="synthetic-qa-only", explicit_confirmation=True, confirmed_proposal_ids=prepared["confirmed_proposal_ids"])
assert first["status"] == "CANONICAL_KNOWLEDGE" and first["package_applied"]
assert k2("knowledge-k2-open") == first
records = first["knowledge_view"]["records"]
assert len(records["concepts"]) == 2 and len(records["relations"]) == 1 and records["topics"] == []
edited_id = concepts[0]["after"]["id"]
assert next(c for c in records["concepts"] if c["id"] == edited_id)["preferred_label"] == "Synthetic QA edited concept"
relation_record = records["relations"][0]
assert all(relation_record[key] == relation[key] for key in ("source_concept_id", "target_concept_id", "relation_type"))
edges = first["knowledge_view"]["graph"]["edges"]
assert dict(from_id=relation_record["id"], to_id=concepts[0]["after"]["id"], kind="RELATION_SOURCE") in edges
assert dict(from_id=relation_record["id"], to_id=concepts[1]["after"]["id"], kind="RELATION_TARGET") in edges
evidence = prepared["proposals"][0]["evidence"][0]
navigation = k2("knowledge-k2-navigation", revision_sha256=first["revision_sha256"], evidence_id=evidence["evidence_id"])
assert navigation["quote"] == evidence["quote"] and navigation["fragment_id"] == evidence["id"]
second_package = k2("knowledge-k2-prepare", notebook_id=opened["notebook_id"],
    expected_state_sha256=opened["state_sha256"], selected_fragment_ids=fragments,
    entity_edits={concepts[0]["after"]["id"]: {"description": "Synthetic QA revision two"}})
second = k2("knowledge-k2-apply", package_sha256=second_package["package_sha256"],
    decisions=[dict(proposal_id=p["id"], action="ACCEPT", reason="Synthetic QA parent revision test") for p in second_package["proposals"]],
    reviewer_id="synthetic-qa-only", explicit_confirmation=True, confirmed_proposal_ids=second_package["confirmed_proposal_ids"])
assert second["parent_revision_sha256"] == first["revision_sha256"] and second["diff"] is not None
assert any(item["kind"] == "CONCEPT" and item["id"] == concepts[0]["after"]["id"] for item in second["diff"]["changed_ids"])
assert k2("knowledge-k2-open") == second
second_concepts = second["knowledge_view"]["records"]["concepts"]
assert {c["id"] for c in second_concepts} == {c["id"] for c in records["concepts"]}
assert next(c for c in second_concepts if c["id"] == edited_id)["description"] == "Synthetic QA revision two"
package = k2("knowledge-k2-package", revision_sha256=second["revision_sha256"])
assert not package["published"]
vault = workspace / "export-preview"
vault.mkdir()
preview = json.loads(invoke(["/usr/bin/python3", "-B", str(resources / "bridge.py"), "package-preview"],
    dict(package_dir=package["package_dir"], target_dir=str(vault), publication_target="obsidian")))
assert preview.get("ok") and preview["result"]["state"] == "DRY_RUN" and not list(vault.iterdir())
validated_after = json.loads(invoke([sys.executable, "-B", str(REPO / "scripts/candidate_manifest.py"), "validate", str(app)], timeout=900))
assert validated_after == validated
assert manifest_bytes == (resources / "candidate-manifest.json").read_bytes()
after = verify_archive(archive, EXPECTED)
assert before == after
print(json.dumps(dict(status="PASS", **EXPECTED, manifest_identity_sha256=manifest["identity_sha256"],
    product_source={k: manifest["identity"]["source"][k] for k in ("commit_sha", "tree_sha")},
    fixture_source="Issue #236 / PR #237", fixture_coverage=coverage,
    self_test=self_test.strip(), native_visible_launch=native_launch,
    packaged_manifest_validation="PASS", repaired_packaged_view_schema_sha256=hashlib.sha256(schema.read_bytes()).hexdigest(), knowledge_k2_apply="PASS", archive_byte_identical=True, archive_receipt=after,
    no_unconfirmed_acceptance=True, explicit_review_actions=sorted({d["action"] for d in decisions}),
    persistence_reopen=True, exact_source_navigation=True, graph_and_diff=True,
    parent_revision_binding=True, managed_export_preview=True,
    first_revision_sha256=first["revision_sha256"], second_revision_sha256=second["revision_sha256"],
    original_project_accessed=False, semantic_product_acceptance=False, upstream_processing=False,
    current_changed=False, process_board_changed=False, diagnostic_operation_count=len(diagnostics)), sort_keys=True))
