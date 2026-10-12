"""K2 preparation and review adapter; SeminarText alone admits canonical records.

Only proposal/working receipts belong to Integra. Canonical revisions are
compiled, independently validated and immutably persisted by the pinned owner.
Opening saved work never regenerates semantic proposals or upstream material.
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

from . import knowledge_notebook as k1
from .knowledge import build_knowledge_view, knowledge_diff
from .protocol import canonical_json, content_sha256
from .seminartext_evidence_runtime import _inside, _review_root
from .seminartext_topic_review_runtime import _locked


RELATIONS = ["associated_with", "contradicts", "depends_on", "refines", "supports"]
EDITABLE = {"concepts": ["preferred_label", "description", "aliases"],
            "topics": ["title", "summary"], "relations": ["relation_type"]}
MACHINE_DERIVED = "MACHINE_DERIVED_FRAGMENTS_V1"


def _runtime():
    from .knowledge_admission_runtime import owner, preflight
    return owner(), preflight()


def _hash(value):
    return hashlib.sha256(value).hexdigest()


def _id(kind, value):
    return kind + "_" + content_sha256(value)


def _evidence_id(fragment_id):
    return "evidence_" + _hash(fragment_id.encode("utf-8"))


def _inputs(project_dir, identities):
    opened = k1.open_notebook(project_dir, **identities)
    if opened["status"] not in {"REVIEWED_FRAGMENTS_V2", MACHINE_DERIVED}:
        raise ValueError("Knowledge requires saved exact source fragments")
    root, _, binding, _ = k1.source_inputs(project_dir, **identities)
    state = k1._read_state(k1._state_path(root, identities["source_id"], opened["notebook_id"]), root)
    k1._validate(root, state, binding)
    evidence_payload = _inside(root / state["review_artifacts"]["evidence"]["path"], root, "K1 Evidence").read_bytes()
    artifact_key = "machine_derived" if opened["status"] == MACHINE_DERIVED else "reviewed_topics"
    reviewed_payload = _inside(root / state["review_artifacts"][artifact_key]["path"], root, "K1 source fragments").read_bytes()
    base = _review_root(root, identities["source_id"]) / "knowledge-k2" / opened["notebook_id"].removeprefix("urn:integra:artifact:")
    return root, base, opened, evidence_payload, reviewed_payload


def _safe_destination(root, path):
    for part in [path, *path.parents]:
        if part == root:
            break
        if part.is_symlink():
            raise ValueError("unsafe K2 artifact path")
    if not path.is_relative_to(root):
        raise ValueError("K2 artifact escaped project")


def _immutable(root, path, payload):
    _safe_destination(root, path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != payload:
            raise ValueError("immutable K2 artifact changed")
        return
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".k2-", delete=True) as stream:
        stream.write(payload); stream.flush(); os.fsync(stream.fileno())
        os.link(stream.name, path)


def _read_work(root, base, opened):
    path = base / "state.json"
    if not path.exists():
        return {"artifact_type": "integra.knowledge_k2_work", "notebook_id": opened["notebook_id"],
                "notebook_sha256": opened["state_sha256"], "package_sha256": None,
                "revision_sha256": None, "revision_history": []}
    state = json.loads(_inside(path, root, "K2 working receipt").read_bytes())
    if state.get("state_sha256") != content_sha256({key: value for key, value in state.items() if key != "state_sha256"}):
        raise ValueError("K2 working receipt changed")
    if state.get("artifact_type") != "integra.knowledge_k2_work" or state.get("notebook_id") != opened["notebook_id"] or state.get("notebook_sha256") != opened["state_sha256"]:
        raise ValueError("K2 notebook review revision is stale")
    return state


def _validate_live_bindings(package, admission, opened, reviewed_payload):
    """An owner-valid receipt alone does not attest the current saved K1 bytes."""
    reviewed = json.loads(reviewed_payload)
    expected_k1 = {"artifact_id": reviewed["artifact_id"], "sha256": _hash(reviewed_payload),
        "notebook_id": opened["notebook_id"], "notebook_sha256": opened["state_sha256"],
        "review_state": opened["status"]}
    if package.get("k1_binding") != expected_k1 or reviewed != opened["reviewed"]:
        raise ValueError("Knowledge receipt belongs to a different current K1 reviewed/source-fragment artifact")
    if package.get("contract") != {"id": admission.CONTRACT_ID, "sha256": admission.CONTRACT_SHA256}:
        raise ValueError("proposal owner contract changed")
    expected_producer = {"component_id": "integra", "runtime_id": "integra_knowledge_k2_v1",
                         "runtime_sha256": _hash(Path(__file__).read_bytes())}
    if package.get("producer") != expected_producer:
        raise ValueError("proposal producer runtime changed")


def _read_package(root, base, package_sha256, admission, opened, reviewed_payload):
    if not re.fullmatch(r"[a-f0-9]{64}", str(package_sha256)):
        raise ValueError("invalid proposal package identity")
    package = json.loads(_inside(base / "packages" / (package_sha256 + ".json"), root, "K2 proposal package").read_bytes())
    if admission.digest(package) != package_sha256:
        raise ValueError("proposal package checksum changed")
    _validate_live_bindings(package, admission, opened, reviewed_payload)
    return package


def _read_revision(root, base, revision_sha256, admission, evidence_payload, opened, reviewed_payload):
    if not re.fullmatch(r"[a-f0-9]{64}", str(revision_sha256)):
        raise ValueError("invalid canonical revision identity")
    revision = json.loads(_inside(base / "revisions" / (revision_sha256 + ".json"), root, "source-owned canonical revision").read_bytes())
    if revision["revision_sha256"] != revision_sha256:
        raise ValueError("canonical revision locator differs")
    receipt = revision
    while receipt is not None:
        request = receipt["source_evidence"]["admission"]
        _validate_live_bindings(request["package"], admission, opened, reviewed_payload)
        if (request["reviewed_payload_utf8"].encode("utf-8") != reviewed_payload
                or request["reviewed_result"] != opened["reviewed"]):
            raise ValueError("canonical receipt differs from the exact current K1 reviewed payload")
        receipt = request["parent"]
    admission.validate_revision(revision, evidence_payload)
    return revision


def _fragment_views(opened, evidence):
    units = {ref: unit for unit in opened["reviewed"]["semantic_knowledge"] for ref in unit["fragment_refs"]}
    revisions = {item["id"]: item for item in evidence["transcript_revisions"]}
    words = {item["id"]: item for item in evidence["words"]}
    cues = {item["id"]: item for item in evidence["cues"]}
    result = []
    for fragment in opened["reviewed"]["fragment_lineage"]:
        if fragment["id"] not in units:
            continue
        word_precise = fragment.get("word_start_id") is not None
        anchors = words if word_precise else cues
        first = anchors[fragment["word_start_id" if word_precise else "cue_start_id"]]
        last = anchors[fragment["word_end_id" if word_precise else "cue_end_id"]]
        revision = revisions[fragment["transcript_revision_id"]]
        unit = units[fragment["id"]]
        result.append({**copy.deepcopy(fragment), "evidence_id": _evidence_id(fragment["id"]),
            "title": unit["title"], "summary": unit["summary"], "precision": "WORD_RANGE" if word_precise else "CUE_RANGE",
            "context": revision["canonical_text"][max(0, first["char_start"] - 100):last["char_end"] + 100],
            "transcript_assurance": copy.deepcopy(revision.get("transcript_provenance")),
            "source_revision_sha256": opened["source_revision_sha256"]})
    return sorted(result, key=lambda item: item["id"])


def _view(revision, evidence_payload, admission):
    timestamp = max(item["timestamp"] for item in revision["semantic_decisions"])
    return build_knowledge_view(evidence_payload, admission.canonical_bytes(revision["source_evidence"]),
                               admission.canonical_bytes(revision["canonical_knowledge"]), created_at=timestamp)


def _present_decisions(revision):
    """Return human review choices without leaking persistence-only metadata.

    The canonical source-owned revision deliberately retains the bound proposal
    digest and timestamp for auditability.  They are not a semantic choice made
    by the reviewer and must not be reintroduced into the normal K2 UI/result
    contract after a local owner identity is supplied automatically.
    """
    visible = {"proposal_id", "action", "reason", "edited_fields"}
    return [
        {key: copy.deepcopy(value) for key, value in decision.items() if key in visible}
        for decision in revision["semantic_decisions"]
    ]


def _exception_questions(proposals, current):
    """Classify only high-impact or ambiguous work for a human decision.

    New source-bound records remain machine-derived/provisional.  Relations,
    identity collisions and updates can change how existing knowledge is
    understood, so they stay exception-only human work.
    """
    questions = []
    current_concepts = current.get("concepts", [])
    for proposal in proposals:
        record, kind = proposal["record"], proposal["entity_kind"]
        if kind == "relations":
            questions.append({
                "proposal_id": proposal["id"], "kind": "RELATION",
                "question": "Нужно ваше решение: подтвердить предложенную связь между понятиями?",
                "options": ["Подтвердить связь", "Не добавлять", "Решить позже"],
            })
            continue
        if proposal["operation"] == "UPDATE":
            questions.append({
                "proposal_id": proposal["id"], "kind": "UPDATE",
                "question": "Нужно ваше решение: заменить существующее описание знаний?",
                "options": ["Подтвердить изменение", "Не изменять", "Решить позже"],
            })
            continue
        if kind == "concepts":
            label = record.get("preferred_label", "").casefold()
            matches = [item["id"] for item in current_concepts
                       if item.get("preferred_label", "").casefold() == label and item.get("id") != record.get("id")]
            if matches:
                questions.append({
                    "proposal_id": proposal["id"], "kind": "IDENTITY",
                    "question": "Нужно ваше решение: похоже, новое понятие может совпадать с уже сохранённым. Как считать?",
                    "options": ["Разные понятия", "Решить позже"],
                })
    return questions


def _presentation(root, base, opened, evidence_payload, reviewed_payload, work, admission):
    fragments = _fragment_views(opened, json.loads(evidence_payload))
    indexed = {item["id"]: item for item in fragments}
    revision = _read_revision(root, base, work["revision_sha256"], admission, evidence_payload, opened, reviewed_payload) if work["revision_sha256"] else None
    package = _read_package(root, base, work["package_sha256"], admission, opened, reviewed_payload) if work["package_sha256"] else None
    current = revision["canonical_knowledge"] if revision else {"topics": [], "concepts": [], "relations": []}
    proposals = []
    for proposal in package["proposals"] if package else []:
        before = next((item for item in current[proposal["entity_kind"]] if item["id"] == proposal["record"]["id"]), None)
        # For an already-applied package, its parent is the exact before state.
        if revision and revision["proposal_package_sha256"] == work["package_sha256"]:
            parent = revision["source_evidence"]["admission"]["parent"]
            before = next((item for item in parent["canonical_knowledge"][proposal["entity_kind"]] if item["id"] == proposal["record"]["id"]), None) if parent else None
        label = proposal["record"].get("preferred_label")
        duplicates = [item["id"] for item in current["concepts"] if label and item["preferred_label"].casefold() == label.casefold() and item["id"] != proposal["record"]["id"]]
        proposals.append({**copy.deepcopy(proposal), "proposal_sha256": admission.digest(proposal),
            "before": copy.deepcopy(before), "after": copy.deepcopy(proposal["record"]),
            "evidence": [indexed[ref["id"]] for ref in proposal["fragment_refs"]],
            "editable_fields": EDITABLE[proposal["entity_kind"]], "possible_duplicate_ids": duplicates})
    view = _view(revision, evidence_payload, admission) if revision else None
    diff = None
    if revision and revision["source_evidence"]["admission"]["parent"]:
        parent = revision["source_evidence"]["admission"]["parent"]
        diff = knowledge_diff(_view(parent, evidence_payload, admission), evidence_payload,
            admission.canonical_bytes(parent["source_evidence"]), admission.canonical_bytes(parent["canonical_knowledge"]),
            view, evidence_payload, admission.canonical_bytes(revision["source_evidence"]), admission.canonical_bytes(revision["canonical_knowledge"]))
    elif revision:
        diff = knowledge_diff(None, b"", b"", b"", view, evidence_payload,
            admission.canonical_bytes(revision["source_evidence"]), admission.canonical_bytes(revision["canonical_knowledge"]))
    available = {item["id"]: item["preferred_label"] for item in current["concepts"]}
    available.update({item["after"]["id"]: item["after"]["preferred_label"] for item in proposals if item["entity_kind"] == "concepts"})
    # A newly prepared package may have an earlier machine-defer receipt as
    # its parent.  Its own exception questions still take precedence over that
    # parent state: otherwise the UI would misleadingly report the work as
    # ready while a relation/update/identity decision is waiting.
    package_is_current = bool(package and (not revision or revision["proposal_package_sha256"] != work["package_sha256"]))
    exception_questions = _exception_questions(package["proposals"], current) if package_is_current else []
    automatic = bool(revision and revision["source_evidence"]["admission"]["decisions"].get("execution_mode") == "SYSTEM_NONAUTHORITATIVE_DEFER")
    status = ("REVIEW_REQUIRED" if exception_questions else
              ("MACHINE_DERIVED_PROVISIONAL_READY" if automatic else
               ("CANONICAL_KNOWLEDGE" if revision else "REVIEW_REQUIRED")))
    return {"notebook_id": opened["notebook_id"], "state_sha256": opened["state_sha256"],
        "status": status, "semantic_authority": "READ_ONLY_SOURCE_LIFECYCLE",
        "eligible_fragments": fragments, "package_sha256": work["package_sha256"], "proposals": proposals,
        "package_applied": bool(revision and revision["proposal_package_sha256"] == work["package_sha256"]),
        "confirmed_proposal_ids": sorted(item["id"] for item in proposals), "revision_sha256": work["revision_sha256"],
        "parent_revision_sha256": revision["parent_revision_sha256"] if revision else None,
        "revision_history": copy.deepcopy(work["revision_history"]), "knowledge_view": view, "diff": diff,
        "semantic_decisions": _present_decisions(revision) if revision else [],
        "semantic_reviewer": copy.deepcopy(revision["source_evidence"]["admission"]["decisions"]["reviewer"]) if revision else None,
        "supported_relation_types": RELATIONS, "available_concepts": [{"id": key, "label": value} for key, value in sorted(available.items())],
        "automatic_acceptance": False, "automatic_defer": automatic and not exception_questions,
        "exception_questions": exception_questions, "upstream_processing_performed": False,
        **{key: opened[key] for key in ("project_id", "run_id", "source_id", "source_revision_sha256")}}


def open_knowledge(project_dir, *, project_id, run_id, source_id):
    identities = dict(project_id=project_id, run_id=run_id, source_id=source_id)
    root, base, opened, evidence_payload, reviewed_payload = _inputs(project_dir, identities)
    admission, _ = _runtime()
    return _presentation(root, base, opened, evidence_payload, reviewed_payload, _read_work(root, base, opened), admission)


def prepare_knowledge(project_dir, *, project_id, run_id, source_id, notebook_id, expected_state_sha256,
                      selected_fragment_ids, relation_inputs=None, entity_edits=None, automatic=False):
    identities = dict(project_id=project_id, run_id=run_id, source_id=source_id)
    root, base, opened, evidence_payload, reviewed_payload = _inputs(project_dir, identities)
    admission, _ = _runtime()
    if notebook_id != opened["notebook_id"] or expected_state_sha256 != opened["state_sha256"]:
        raise ValueError("K1 notebook changed; reopen before preparing Knowledge")
    if not isinstance(selected_fragment_ids, list) or not selected_fragment_ids or len(set(selected_fragment_ids)) != len(selected_fragment_ids):
        raise ValueError("explicit unique reviewed-fragment selection required")
    reviewed, bundle = json.loads(reviewed_payload), json.loads(evidence_payload)
    fragments = {item["id"]: item for item in reviewed["fragment_lineage"]}
    eligible = {ref for unit in reviewed["semantic_knowledge"] for ref in unit["fragment_refs"]}
    if not set(selected_fragment_ids) <= eligible:
        raise ValueError("unreviewed/excluded/missing fragment cannot enter Knowledge")
    work = _read_work(root, base, opened)
    parent = _read_revision(root, base, work["revision_sha256"], admission, evidence_payload, opened, reviewed_payload) if work["revision_sha256"] else None
    current = parent["canonical_knowledge"] if parent else {"topics": [], "concepts": [], "relations": []}
    runtime_hash = _hash(Path(__file__).read_bytes())
    package_id = _id("proposals", {"notebook": notebook_id, "selection": sorted(selected_fragment_ids), "parent": work["revision_sha256"],
                                  "relations": relation_inputs or [], "edits": entity_edits or {}})
    source = next(item for item in bundle["sources"] if item["id"] == fragments[selected_fragment_ids[0]]["source_id"])
    revision = next(item for item in bundle["transcript_revisions"] if item["id"] == fragments[selected_fragment_ids[0]]["transcript_revision_id"])
    proposals = []
    edits = entity_edits or {}
    if not isinstance(edits, dict):
        raise ValueError("entity edits must bind exact stable record IDs")

    def propose(kind, record, refs):
        old = next((item for item in current[kind] if item["id"] == record["id"]), None)
        if old:
            record = copy.deepcopy(old)
        if record["id"] in edits:
            fields = edits[record["id"]]
            if not isinstance(fields, dict) or not set(fields) <= set(EDITABLE[kind]):
                raise ValueError("unsupported semantic fields/identity change")
            record.update(fields)
        record["status"] = "PROVISIONAL"
        record["evidence_refs"] = sorted({_evidence_id(ref) for ref in refs})
        if kind == "concepts":
            record["created_from"] = record["evidence_refs"]
        proposals.append({"id": _id("proposal", {"package": package_id, "kind": kind, "record": record}),
            "entity_kind": kind, "operation": "UPDATE" if old else "CREATE", "record": record,
            "fragment_refs": [{"id": ref, "sha256": admission.digest(fragments[ref])} for ref in sorted(refs)],
            "before_sha256": admission.digest(old) if old else None, "review_status": "REVIEW_REQUIRED",
            "generation_provenance": {"method": "deterministic-reviewed-unit-proposal-v1", "producer_sha256": runtime_hash}})

    provenance = {"origin": "derived", "source_artifact_id": package_id}
    seminar_id = current["seminars"][0]["id"] if parent else "seminar_" + _hash(bundle["project"]["id"].encode())
    for unit in reviewed["semantic_knowledge"]:
        refs = sorted(set(unit["fragment_refs"]) & set(selected_fragment_ids))
        if not refs:
            continue
        concept_id = _id("concept", {"notebook": notebook_id, "unit": unit["id"]})
        propose("concepts", {"id": concept_id, "preferred_label": unit["title"], "aliases": [],
            "scope": "source-bound", "description": unit["summary"] or unit["title"], "version": 1,
            "topic_refs": [], "created_from": [], "supersedes": [], "redirects": [], "provenance": provenance}, refs)
        propose("topics", {"id": _id("topic", {"notebook": notebook_id, "unit": unit["id"]}), "seminar_id": seminar_id,
            "title": unit["title"], "summary": unit["summary"] or unit["title"], "version": 1,
            "source_scope": {"source_ids": [source["id"]], "transcript_revision_ids": [revision["id"]]},
            "concept_refs": [], "provenance": provenance}, refs)
    concepts = {item["id"] for item in current["concepts"]} | {item["record"]["id"] for item in proposals if item["entity_kind"] == "concepts"}
    if relation_inputs is not None and not isinstance(relation_inputs, list):
        raise ValueError("Relation inputs must be an explicit list")
    for relation in relation_inputs or []:
        if not isinstance(relation, dict) or set(relation) != {"source_concept_id", "target_concept_id", "relation_type", "fragment_ids"}:
            raise ValueError("Relation input fields differ")
        if relation["relation_type"] not in RELATIONS:
            raise ValueError("unsupported Relation type")
        if not {relation["source_concept_id"], relation["target_concept_id"]} <= concepts:
            raise ValueError("Relation endpoints must use exact known Concept identities")
        refs = relation["fragment_ids"]
        if not isinstance(refs, list) or not refs or not set(refs) <= set(selected_fragment_ids):
            raise ValueError("Relation needs explicitly selected exact Evidence")
        propose("relations", {"id": _id("relation", {key: relation[key] for key in ("source_concept_id", "target_concept_id", "relation_type")}),
            **{key: relation[key] for key in ("source_concept_id", "target_concept_id", "relation_type")}, "version": 1, "provenance": provenance}, refs)
    if set(edits) - {item["record"]["id"] for item in proposals}:
        raise ValueError("semantic edit target is outside selected proposals")
    package = {"schema_version": "1.0.0", "artifact_type": "seminartext.reviewed_knowledge_proposals", "artifact_id": package_id,
        "contract": {"id": admission.CONTRACT_ID, "sha256": admission.CONTRACT_SHA256},
        "producer": {"component_id": "integra", "runtime_id": "integra_knowledge_k2_v1", "runtime_sha256": runtime_hash},
        "source_binding": {"project_id": bundle["project"]["id"], "source_id": source["id"],
            "source_revision_sha256": source["content_sha256"], "source_sha256": source["content_sha256"],
            "transcript_revision_id": revision["id"], "transcript_sha256": revision["text_sha256"], "evidence_sha256": _hash(evidence_payload)},
        "k1_binding": {"artifact_id": reviewed["artifact_id"], "sha256": _hash(reviewed_payload),
            "notebook_id": notebook_id, "notebook_sha256": opened["state_sha256"], "review_state": opened["status"]},
        "parent_revision_sha256": work["revision_sha256"], "proposals": sorted(proposals, key=lambda item: item["id"])}
    package_sha256 = admission.digest(package)
    with _locked(root, source_id):
        latest = _inputs(root, identities)
        if latest[2]["state_sha256"] != opened["state_sha256"] or _read_work(root, base, opened) != work:
            raise ValueError("Knowledge changed during proposal preparation")
        _immutable(root, base / "packages" / (package_sha256 + ".json"), admission.canonical_bytes(package))
        _safe_destination(root, base / "state.json")
        work.update(package_sha256=package_sha256)
        work = k1._persist(base / "state.json", work)
    prepared = _presentation(root, base, opened, evidence_payload, reviewed_payload, work, admission)
    if automatic:
        if _exception_questions(package["proposals"], current):
            return prepared
        return apply_knowledge(project_dir, **identities, package_sha256=package_sha256,
                               decisions=None, reviewer_id=None, explicit_confirmation=None,
                               confirmed_proposal_ids=None, automatic=True)
    return prepared


def apply_knowledge(project_dir, *, project_id, run_id, source_id, package_sha256, decisions, reviewer_id,
                    explicit_confirmation, confirmed_proposal_ids, automatic=False):
    identities = dict(project_id=project_id, run_id=run_id, source_id=source_id)
    root, base, opened, evidence_payload, reviewed_payload = _inputs(project_dir, identities)
    admission, _ = _runtime()
    if automatic and (reviewer_id is not None or decisions is not None or explicit_confirmation is not None or confirmed_proposal_ids is not None):
        raise ValueError("automatic non-authoritative admission cannot include human decisions")
    if not automatic and (not isinstance(reviewer_id, str) or not re.fullmatch(r"[a-z][a-z0-9._:-]{2,127}", reviewer_id)):
        raise ValueError("explicit stable human reviewer identity required")
    with _locked(root, source_id):
        work = _read_work(root, base, opened)
        if work["package_sha256"] != package_sha256:
            raise ValueError("proposal package is stale; reopen Knowledge")
        package = _read_package(root, base, package_sha256, admission, opened, reviewed_payload)
        proposals = {item["id"]: item for item in package["proposals"]}
        if automatic:
            if opened["status"] != MACHINE_DERIVED or _exception_questions(package["proposals"], {"concepts": []}):
                raise ValueError("automatic path is unavailable for this semantic exception")
            decisions = [{"proposal_id": proposal_id, "action": "DEFER",
                          "reason": "No semantic exception detected; retained as machine-derived provisional knowledge."}
                         for proposal_id in sorted(proposals)]
            reviewer_id = "integra_system"
            explicit_confirmation = False
            confirmed_proposal_ids = sorted(proposals)
        elif explicit_confirmation is not True or confirmed_proposal_ids != sorted(proposals):
            raise ValueError("explicit confirmation of the exact enumerated proposal package required")
        if not isinstance(decisions, list) or len(decisions) != len(proposals):
            raise ValueError("each proposal needs explicit ACCEPT/EDIT/REJECT/DEFER")
        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        choices, seen = [], set()
        for choice in decisions:
            if (not isinstance(choice, dict) or not set(choice) <= {"proposal_id", "action", "reason", "edited_fields"}
                    or choice.get("proposal_id") not in proposals or choice["proposal_id"] in seen
                    or choice.get("action") not in {"ACCEPT", "EDIT", "REJECT", "DEFER"}
                    or not isinstance(choice.get("reason"), str) or not choice["reason"].strip()):
                raise ValueError("invalid/duplicate/missing semantic ReviewDecision")
            seen.add(choice["proposal_id"])
            choices.append({**copy.deepcopy(choice), "proposal_sha256": admission.digest(proposals[choice["proposal_id"]]), "timestamp": timestamp})
        ledger = {"schema_version": "1.0.0", "package_id": package["artifact_id"], "package_sha256": package_sha256,
            "reviewer": {"actor_type": "system_validator" if automatic else "human_domain_reviewer", "actor_id": reviewer_id},
            "execution_mode": "SYSTEM_NONAUTHORITATIVE_DEFER" if automatic else "HUMAN_REVIEW",
            "explicit_confirmation": explicit_confirmation, "confirmed_proposal_ids": confirmed_proposal_ids,
            "decisions": sorted(choices, key=lambda item: item["proposal_id"])}
        parent_hash = package["parent_revision_sha256"]
        if work["revision_sha256"] != parent_hash:
            raise ValueError("package already applied or canonical parent changed; prepare a new package")
        parent = _read_revision(root, base, parent_hash, admission, evidence_payload, opened, reviewed_payload) if parent_hash else None
        revision = admission.compile_revision(evidence_payload, reviewed_payload, package, ledger, parent=parent)
        admission.validate_revision(revision, evidence_payload)
        # Revalidate independent live K1/source inputs before the owner persists.
        latest = _inputs(root, identities)
        if latest[2]["state_sha256"] != opened["state_sha256"] or latest[3:] != (evidence_payload, reviewed_payload):
            raise ValueError("K1 source changed during semantic admission")
        destination = base / "revisions" / (revision["revision_sha256"] + ".json")
        _safe_destination(root, destination)
        admission.persist_revision(destination, revision)
        work["revision_sha256"] = revision["revision_sha256"]
        work["revision_history"] = work["revision_history"] + [revision["revision_sha256"]]
        work = k1._persist(base / "state.json", work)
    return _presentation(root, base, opened, evidence_payload, reviewed_payload, work, admission)


def knowledge_navigation(project_dir, *, project_id, run_id, source_id, revision_sha256, evidence_id):
    identities = dict(project_id=project_id, run_id=run_id, source_id=source_id)
    root, base, opened, evidence_payload, reviewed_payload = _inputs(project_dir, identities)
    admission, _ = _runtime()
    revision = _read_revision(root, base, revision_sha256, admission, evidence_payload, opened, reviewed_payload)
    evidence = next((item for item in revision["source_evidence"]["evidence"] if item["id"] == evidence_id), None)
    if evidence is None:
        raise ValueError("canonical Evidence identity is unavailable")
    navigation = k1.notebook_navigation(root, **identities, notebook_id=opened["notebook_id"], fragment_id=evidence["reviewed_fragment_id"])
    if navigation["quote"] != evidence["quote"] or {key: navigation[key] for key in ("start_seconds", "end_seconds")} != {key: evidence["locator"][key] for key in ("start_seconds", "end_seconds")}:
        raise ValueError("canonical Evidence differs from exact K1 navigation")
    return {**navigation, "revision_sha256": revision_sha256, "evidence_id": evidence_id}


def knowledge_package(project_dir, *, project_id, run_id, source_id, revision_sha256):
    from .reviewed_result_package import build_admitted_knowledge_package
    identities = dict(project_id=project_id, run_id=run_id, source_id=source_id)
    root, base, opened, evidence_payload, reviewed_payload = _inputs(project_dir, identities)
    admission, _ = _runtime()
    revision = _read_revision(root, base, revision_sha256, admission, evidence_payload, opened, reviewed_payload)
    return build_admitted_knowledge_package(revision=revision, evidence_payload=evidence_payload,
        project_id=project_id, project_slug=project_id.removeprefix("urn:integra:project:"), source_id=source_id,
        navigation_context={**identities, "source_revision_sha256": opened["source_revision_sha256"], "notebook_id": opened["notebook_id"]})
