"""Actual packaged K2 bridge over a fresh synthetic two-unit project.

All decisions are QA-only, never product semantic acceptance. No provider or
upstream processing is invoked. The caller owns the fresh disposable data root.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from archive_execution_guard import require_execution_path
from k2_qa_fixture import IDENTITY, PROJECT_UUID, payloads


def exercise(app, data_root):
    require_execution_path(app)
    data_root.mkdir(parents=True, exist_ok=False)
    project = data_root / "projects" / PROJECT_UUID
    project.mkdir(parents=True)
    inputs = payloads(project)
    for relative, content in inputs.items():
        target = project / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    before = {name: hashlib.sha256(content).hexdigest() for name, content in inputs.items()}
    resources = app.resolve(strict=True) / "Contents/Resources"
    manifest = json.loads((resources / "candidate-manifest.json").read_bytes())
    environment = {key: value for key, value in os.environ.items()
                   if not key.startswith("INTEGRA_") and key not in {"PYTHONPATH", "PYTHONHOME"}}
    environment.update(INTEGRA_APP_DATA_ROOT=str(data_root), PYTHONDONTWRITEBYTECODE="1",
                       PATH="/usr/bin:/bin:/usr/sbin:/sbin")
    python = "/usr/bin/python3" if sys.platform == "darwin" else sys.executable
    operations = []

    def bridge(operation, request):
        completed = subprocess.run([python, "-B", str(resources / "bridge.py"), operation],
                                   input=json.dumps(request), text=True, capture_output=True,
                                   cwd=data_root, env=environment, timeout=180)
        if completed.returncode:
            raise RuntimeError(operation + ": " + completed.stdout + completed.stderr)
        value = json.loads(completed.stdout)
        if not value.get("ok"):
            raise RuntimeError(value)
        operations.append(operation)
        return value["result"]

    opened = bridge("knowledge-open", dict(IDENTITY, create=True))
    reviewed = bridge("knowledge-save", dict(IDENTITY,
        expected_state_sha256=opened["state_sha256"],
        decisions=[dict(topic_id=topic["id"], action="ACCEPT", reason="SYNTHETIC QA ONLY")
                   for topic in opened["topics"]], reviewer_id="synthetic-qa-k1"))
    assert reviewed["status"] == "REVIEWED_FRAGMENTS_V2"
    opened = bridge("knowledge-k2-open", IDENTITY)
    fragments = [item["id"] for item in opened["eligible_fragments"]]
    request = dict(IDENTITY, notebook_id=opened["notebook_id"],
                   expected_state_sha256=opened["state_sha256"], selected_fragment_ids=fragments)
    prepared = bridge("knowledge-k2-prepare", request)
    concepts = [p for p in prepared["proposals"] if p["entity_kind"] == "concepts"]
    assert len(concepts) >= 2
    relation = dict(source_concept_id=concepts[0]["after"]["id"],
                    target_concept_id=concepts[1]["after"]["id"],
                    relation_type="associated_with", fragment_ids=fragments)
    prepared = bridge("knowledge-k2-prepare", dict(request, relation_inputs=[relation]))
    decisions = []
    topic_index = 0
    for proposal in prepared["proposals"]:
        action = "ACCEPT"
        if proposal["entity_kind"] == "topics":
            action = "REJECT" if topic_index == 0 else "DEFER"
            topic_index += 1
        decision = dict(proposal_id=proposal["id"], action=action, reason="SYNTHETIC QA ONLY")
        if proposal["entity_kind"] == "concepts" and not any(d["action"] == "EDIT" for d in decisions):
            decision.update(action="EDIT", edited_fields={"preferred_label": "Синтетический QA термин"})
        decisions.append(decision)
    accepted = bridge("knowledge-k2-apply", dict(IDENTITY,
        package_sha256=prepared["package_sha256"], decisions=decisions, reviewer_id="synthetic-qa-k2",
        explicit_confirmation=True, confirmed_proposal_ids=prepared["confirmed_proposal_ids"]))
    assert accepted["status"] == "CANONICAL_KNOWLEDGE"
    assert len(accepted["knowledge_view"]["records"]["concepts"]) == 2
    assert len(accepted["knowledge_view"]["records"]["relations"]) == 1
    assert accepted["knowledge_view"]["records"]["topics"] == []
    assert bridge("knowledge-k2-open", IDENTITY) == accepted
    evidence = prepared["proposals"][0]["evidence"][0]
    navigation = bridge("knowledge-k2-navigation", dict(IDENTITY,
        revision_sha256=accepted["revision_sha256"], evidence_id=evidence["evidence_id"]))
    assert navigation["quote"] == evidence["quote"]
    package = bridge("knowledge-k2-package", dict(IDENTITY, revision_sha256=accepted["revision_sha256"]))
    assert package["published"] is False
    assert before == {name: hashlib.sha256((project / name).read_bytes()).hexdigest() for name in inputs}
    return dict(candidate_id=manifest["candidate_id"], bundle_digest=manifest["bundle"]["digest"],
                product_source=manifest["identity"]["source"], operations=operations,
                concepts=2, relations=1, rejected_and_deferred_topics=True,
                all_four_decision_actions=True, persistence_reopen=True,
                exact_quote_navigation=True, managed_package_unpublished=True,
                source_inputs_unchanged=True, semantic_product_acceptance=False,
                upstream_processing=False, identity=IDENTITY, data_root=str(data_root))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(exercise(args.app, args.data_root), ensure_ascii=False, sort_keys=True))
