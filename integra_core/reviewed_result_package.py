"""Portable, cross-bound export of already-reviewed real component results.

This package is distinct from the historical R9A/navigation publication contract.
Building replays only an existing decision/result. Validation checks semantic
cross-bindings independently of the outer transport checksums. V1 additionally
requires the pinned runtime to reproduce its derived view in an isolated
temporary snapshot; V2 validation does not require runtime or filesystem access.
"""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile
from datetime import datetime, timezone

from .identity import derive_imported_id
from .protocol import canonical_json, content_sha256
from .publishing import PublishingError, validate_source_export
from .seminartext_evidence_runtime import _inside, _review_root, _sha256
from .seminartext_topic_review_runtime import _environment, _locked, _python, apply_topic_review, preflight


TYPE = "integra.reviewed_result_package"
V1 = "CANONICAL_KNOWLEDGE_V1"
V2 = "REVIEWED_FRAGMENTS_V2"


_RENDER_VERIFICATION = """
import base64, json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from seminartext_modules.project_knowledge_bridge import compile_documents, build_vault, make_manifest, canonical_bytes, sha256_bytes
project = Path(sys.argv[2])
document = json.loads((project / 'knowledge_input.json').read_text())
evidence, source, knowledge, coverage = compile_documents(project, document)
resolver = {item['id']: 'RESOLVER_UNAVAILABLE' for item in evidence['sources']}
view = build_vault(evidence, source, knowledge, coverage, resolver)
manifest = make_manifest(view, {
    'kind': 'obsidian_derived_view',
    'canonical_evidence_artifact_id': evidence['artifact_id'],
    'canonical_evidence_sha256': sha256_bytes(canonical_bytes(evidence)),
    'canonical_knowledge_artifact_id': knowledge['artifact_id'],
    'canonical_knowledge_sha256': sha256_bytes(canonical_bytes(knowledge)),
    'coverage': coverage, 'resolver_states': resolver,
})
artifacts = {'compiled_evidence': canonical_bytes(evidence), 'source_evidence': canonical_bytes(source), 'knowledge': canonical_bytes(knowledge)}
print(json.dumps({'artifacts': {key: base64.b64encode(value).decode('ascii') for key, value in artifacts.items()},
                  'view': {key: base64.b64encode(value).decode('ascii') for key, value in view.items()}, 'manifest': manifest}))
"""


def _verify_pinned_view(files, refs, result_ref, derived):
    """Reproduce existing derived bytes, never create or apply semantic decisions."""
    runtime = preflight()["runtime"]
    with tempfile.TemporaryDirectory(prefix="integra-reviewed-export-check-") as temporary:
        project = Path(temporary)
        (project / "evidence").mkdir()
        (project / "evidence/canonical_bundle.json").write_bytes(files[refs["evidence"]["path"]])
        (project / "knowledge_input.json").write_bytes(files[refs["knowledge_input"]["path"]])
        try:
            checked = subprocess.run([_python(), "-c", _RENDER_VERIFICATION, runtime, str(project)],
                env=_environment(), capture_output=True, text=True, timeout=120)
        except subprocess.SubprocessError as error:
            raise ValueError("pinned derived-view verification could not finish") from error
        _require(checked.returncode == 0, "pinned derived-view compiler rejected the reviewed input")
        generated = json.loads(checked.stdout)
    for key, ref in (("compiled_evidence", refs["compiled_evidence"]), ("source_evidence", refs["source_evidence"]), ("knowledge", result_ref)):
        _require(base64.b64decode(generated["artifacts"][key], validate=True) == files[ref["path"]], "compiled artifact differs from pinned compiler")
    expected_view = {"view/" + name: base64.b64decode(value, validate=True) for name, value in generated["view"].items()}
    _require(expected_view == {name: value for name, value in files.items() if name.startswith("view/")}, "derived note differs from pinned renderer")
    _require(generated["manifest"] == derived, "derived manifest coverage or resolver differs from pinned renderer")


def _require(condition, message):
    if not condition:
        raise ValueError("Reviewed result package: " + message)


def _sha(payload):
    return hashlib.sha256(payload).hexdigest()


def _component_sha(value):
    return _sha((json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode())


def _relative(path):
    _require(isinstance(path, str) and path and "\\" not in path, "invalid relative path")
    parsed = PurePosixPath(path)
    _require(not parsed.is_absolute() and str(parsed) == path and all(part not in {".", ".."} for part in parsed.parts), "unsafe relative path")
    return path


def _identity(manifest):
    return {key: value for key, value in manifest.items() if key not in {"package_id", "version_sha256"}}


def _index(items):
    _require(isinstance(items, list) and all(isinstance(item, dict) and isinstance(item.get("id"), str) for item in items), "invalid record inventory")
    result = {item["id"]: item for item in items}
    _require(len(result) == len(items), "duplicate record IDs")
    return result


def _span(item, evidence):
    words = _index(evidence["words"])
    revisions = _index(evidence["transcript_revisions"])
    first, last = words[item["word_start_id"]], words[item["word_end_id"]]
    revision = revisions[item["transcript_revision_id"]]
    _require(first["source_id"] == last["source_id"] == revision["source_id"] == item["source_id"], "source range differs")
    _require(first["transcript_revision_id"] == last["transcript_revision_id"] == revision["id"], "revision range differs")
    selected = sorted((word for word in words.values() if word["transcript_revision_id"] == revision["id"]
                       and first["sequence"] <= word["sequence"] <= last["sequence"]), key=lambda word: word["sequence"])
    _require(selected and [word["sequence"] for word in selected] == list(range(first["sequence"], last["sequence"] + 1)), "non-contiguous word range")
    aligned = [word for word in selected if word["alignment_status"] != "unaligned"]
    _require(aligned, "range has no exact timing")
    return {"quote": revision["canonical_text"][first["char_start"]:last["char_end"]],
            "locator": {"type": "time_interval", "start_seconds": aligned[0]["start_seconds"], "end_seconds": aligned[-1]["end_seconds"]},
            "word_start_sequence": first["sequence"], "word_end_sequence": last["sequence"]}


def _validate(manifest, files):
    expected_fields = {"schema_version", "artifact_type", "package_id", "version_sha256", "project_id", "project_slug",
                       "source_id", "created_at", "files", "semantic_authority", "source_artifacts_modified", "result_kind", "result", "provenance"}
    _require(isinstance(manifest, dict) and set(manifest) == expected_fields, "manifest fields differ")
    _require(manifest["schema_version"] == "1.0" and manifest["artifact_type"] == TYPE, "wrong package contract")
    _require(manifest["semantic_authority"] == "DERIVED_SOURCE_TRUTH_PRESERVED" and manifest["source_artifacts_modified"] is False, "authority differs")
    _require(isinstance(manifest["project_id"], str) and manifest["project_id"].startswith("urn:integra:project:"), "project ID missing")
    _require(isinstance(manifest["source_id"], str) and manifest["source_id"], "source ID missing")
    _require(isinstance(manifest["project_slug"], str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,95}", manifest["project_slug"]), "unsafe slug")
    instant = datetime.fromisoformat(manifest["created_at"].replace("Z", "+00:00"))
    _require(manifest["created_at"].endswith("Z") and instant.tzinfo == timezone.utc, "timestamp is not UTC")
    _require(isinstance(files, dict) and all(isinstance(value, bytes) for value in files.values()), "payloads must be bytes")
    inventory = [{"path": _relative(name), "size_bytes": len(data), "sha256": _sha(data), "ownership_class": "MANAGED_GENERATED"}
                 for name, data in sorted(files.items())]
    _require(manifest["files"] == inventory, "file inventory/checksum differs")
    version = content_sha256(_identity(manifest))
    _require(manifest["version_sha256"] == version, "version checksum differs")
    _require(manifest["package_id"] == derive_imported_id("artifact", "integra.reviewed_result", manifest["project_id"], version), "package ID differs")

    def payload(ref):
        _require(isinstance(ref, dict) and set(ref) == {"path", "sha256"}, "artifact reference differs")
        name = _relative(ref["path"])
        _require(name in files and _sha(files[name]) == ref["sha256"], "artifact reference hash differs")
        return files[name]

    def record(ref):
        value = json.loads(payload(ref))
        _require(isinstance(value, dict), "artifact must be an object")
        return value

    kind = manifest["result_kind"]
    _require(kind in {V1, V2}, "unknown result kind")
    roles = {"evidence", "decisions", "review_package", "receipt", "binding", "topic_output", "draft_input"}
    roles |= {"knowledge_input", "compiled_evidence", "source_evidence", "derived_manifest"} if kind == V1 else {"word_timeline"}
    refs = manifest["provenance"]
    _require(isinstance(refs, dict) and set(refs) == roles, "provenance roles differ")
    records = {name: record(ref) for name, ref in refs.items()}
    _require(set(manifest["result"]) == {"path", "sha256", "markdown"}, "result reference differs")
    result_ref = {name: manifest["result"][name] for name in ("path", "sha256")}
    result = record(result_ref)
    payload(manifest["result"]["markdown"])
    evidence, package, decisions = (records[name] for name in ("evidence", "review_package", "decisions"))
    receipt, binding, drafts = (records[name] for name in ("receipt", "binding", "draft_input"))
    _require(evidence["artifact_type"] == "seminartext.canonical_evidence", "Evidence contract differs")
    source_id = "source_source_" + hashlib.sha256(manifest["source_id"].encode()).hexdigest()[:24]
    _require(source_id in _index(evidence["sources"]), "Evidence belongs to another source")
    _require(package["artifact_type"] == "seminartext.topic_review_package" and package["schema_version"] == "1.0.0", "review package contract differs")
    _require(package["canonical_evidence"] == {"artifact_id": evidence["artifact_id"], "sha256": refs["evidence"]["sha256"]}, "review package Evidence binding differs")
    _require(package["draft_input"] == {"artifact_id": drafts["artifact_id"], "sha256": refs["draft_input"]["sha256"]}, "draft input binding differs")
    _require(package["project"] == evidence["project"] or package["project"] == {key: evidence["project"][key] for key in ("id", "title")}, "package project differs")
    _require(package["review_policy"]["automatic_acceptance"] is False, "automatic acceptance is forbidden")
    _require(binding == {"source_id": manifest["source_id"], "evidence_sha256": refs["evidence"]["sha256"],
                        "topics_sha256": refs["topic_output"]["sha256"], "package_sha256": refs["review_package"]["sha256"],
                        "review_mode": V1 if kind == V1 else "EXACT_FRAGMENTS_V2",
                        **({"timeline_sha256": refs["word_timeline"]["sha256"]} if kind == V2 else {})}, "portable original binding differs")
    _require(drafts["generator"]["configuration_sha256"] == content_sha256({"topic_output_sha256": refs["topic_output"]["sha256"], "canonical_evidence_sha256": refs["evidence"]["sha256"]}), "draft generator input differs")
    topics = _index(package["topics"])
    draft_topics = _index(drafts["topics"])
    _require(set(topics) == set(draft_topics), "draft topic inventory differs")
    for topic in topics.values():
        _require(all(topic[key] == value for key, value in draft_topics[topic["id"]].items()), "reviewed topic differs from original draft")
        core = {key: value for key, value in topic.items() if key != "topic_sha256"}
        _require(topic["topic_sha256"] == _component_sha(core), "topic snapshot hash differs")
        _require(all(topic[key] == value for key, value in _span(topic, evidence).items()), "topic quote or timing differs")
        supporting = [next(item for item in package["evidence"] if item["id"] == ref) for ref in topic["evidence_refs"]]
        _require(topic["evidence_sha256"] == _component_sha(supporting), "topic evidence hash differs")
    for item in package["evidence"]:
        _require(all(item[key] == value for key, value in _span(item, evidence).items()), "supporting quote differs")
    _require(decisions["artifact_type"] == "seminartext.topic_review_decisions", "decision contract differs")
    _require(decisions["review_package_id"] == package["artifact_id"] and decisions["review_package_sha256"] == refs["review_package"]["sha256"], "decision/package binding differs")
    _require(decisions["reviewer"]["actor_type"] == "human_domain_reviewer" and decisions["reviewer"]["actor_id"], "human actor missing")
    decision_records = _index(decisions["decisions"])
    by_topic = {}
    for decision in decision_records.values():
        _require(len(decision["target_ids"]) == 1, "unsupported decision target shape")
        target = decision["target_ids"][0]
        _require(target in topics and target not in by_topic, "duplicate/unknown decision target")
        _require(decision["expected_topics"] == [{"topic_id": target, "topic_sha256": topics[target]["topic_sha256"]}], "decision snapshot differs")
        _require(isinstance(decision["reason"], str) and decision["reason"].strip(), "decision reason missing")
        by_topic[target] = decision
    _require(set(by_topic) == set(topics), "unreviewed topics remain")
    _require(manifest["created_at"] == max(item["timestamp"] for item in decision_records.values()), "timestamp differs from decisions")
    _require(receipt["package_sha256"] == refs["review_package"]["sha256"] and receipt["decisions_sha256"] == refs["decisions"]["sha256"] and receipt["automatic_acceptance"] is False, "receipt input binding differs")
    expected_files = {ref["path"] for ref in refs.values()} | {result_ref["path"], manifest["result"]["markdown"]["path"]}
    if kind == V1:
        _require(decisions["schema_version"] == "1.0.0" and receipt["status"] == "KNOWLEDGE_CREATED", "V1 contract differs")
        _require(receipt["canonical_knowledge_sha256"] == result_ref["sha256"] and receipt["knowledge_markdown_sha256"] == manifest["result"]["markdown"]["sha256"], "V1 receipt result differs")
        compiled, source, knowledge_input = (records[name] for name in ("compiled_evidence", "source_evidence", "knowledge_input"))
        _require(result["artifact_type"] == "seminartext.canonical_knowledge", "Canonical Knowledge contract differs")
        for role, record_key in (("compiled_evidence", "canonical_evidence"), ("source_evidence", "source_evidence")):
            _require(result[record_key]["sha256"] == refs[role]["sha256"] and result[record_key]["artifact_id"] == records[role]["artifact_id"], "compiled input binding differs")
        _require(receipt["source_evidence_sha256"] == refs["source_evidence"]["sha256"], "receipt source Evidence differs")
        _require(all(compiled[key] == value for key, value in evidence.items() if key not in {"artifact_id", "topics", "evidence_refs"}), "compiled Evidence changed source truth")
        for key in ("project", "seminars", "topics", "concepts", "relations", "review_decisions", "relation_type_registry"):
            _require(result[key] == knowledge_input[key], "knowledge differs from reviewed input")
        _require(result["concepts"] == [] and result["relations"] == [], "unexpected inferred concepts or relations")
        final_topics = _index(result["topics"])
        final_decisions = _index(result["review_decisions"])
        _require(set(final_topics) == set(topics) and set(final_decisions) == set(decision_records), "knowledge inventory differs")
        source_items = _index(source["evidence"])
        package_items = _index(package["evidence"])
        compiled_refs = _index(compiled["evidence_refs"])
        _require(set(source_items) == set(package_items) == set(compiled_refs), "source Evidence inventory differs")
        _require(source["source_input_artifact_id"] == knowledge_input["artifact_id"], "source Evidence input identity differs")
        words = _index(evidence["words"])
        for evidence_id, original in package_items.items():
            span = _span(original, evidence)
            unaligned = [word["id"] for word in sorted(words.values(), key=lambda word: word["sequence"])
                         if word["transcript_revision_id"] == original["transcript_revision_id"]
                         and span["word_start_sequence"] <= word["sequence"] <= span["word_end_sequence"]
                         and word["alignment_status"] == "unaligned"]
            expected_source = {"id": evidence_id, "claim": original["claim"], "canonical_source_id": original["source_id"],
                "canonical_transcript_revision_id": original["transcript_revision_id"], "canonical_word_start_id": original["word_start_id"],
                "canonical_word_end_id": original["word_end_id"], "quote": span["quote"], "locator": span["locator"],
                "timing_status": "aligned_envelope_with_explicit_unaligned_words" if unaligned else "aligned_word_range", "unaligned_word_ids": unaligned}
            _require(source_items[evidence_id] == expected_source, "source Evidence quote/lineage differs")
            _require(compiled_refs[evidence_id] == {"id": evidence_id, "project_id": evidence["project"]["id"],
                "source_id": original["source_id"], "transcript_revision_id": original["transcript_revision_id"],
                "target": {"entity_type": "word", "entity_id": original["word_start_id"]},
                "locator": span["locator"], "lifecycle_status": "verified"}, "compiled Evidence reference differs")
        compiled_topics = _index(compiled["topics"])
        _require(set(compiled_topics) == set(topics), "compiled topic inventory differs")
        for target, decision in by_topic.items():
            _require(decision["action"] in {"ACCEPT", "REJECT"} and decision["result_topics"] == [], "unsupported semantic transformation")
            final, original = final_topics[target], topics[target]
            _require(final["title"] == original["proposed_title"] and final["summary"] == (original["proposed_summary"] or "No summary supplied."), "knowledge wording differs")
            _require(final["status"] == ("ACCEPTED" if decision["action"] == "ACCEPT" else "REJECTED"), "knowledge contradicts decision")
            _require(final["source_scope"] == {"source_ids": [original["source_id"]],
                "transcript_revision_ids": [original["transcript_revision_id"]],
                "order_start": original["word_start_sequence"], "order_end": original["word_end_sequence"]}, "knowledge source range differs")
            _require(final["temporal_scope"] == {key: original["locator"][key] for key in ("start_seconds", "end_seconds")}
                and final["evidence_refs"] == original["evidence_refs"] and final["order_scope"] == {"sequence": original["sequence"]}, "knowledge locator/evidence differs")
            converted = final_decisions[decision["id"]]
            _require(all(converted[key] == decision[key] for key in ("action", "target_ids", "reason", "timestamp")), "knowledge decision differs")
            _require(converted["actor_id"] == decisions["reviewer"]["actor_id"] and converted["provenance"]["source_artifact_id"] == decisions["artifact_id"], "knowledge actor/provenance differs")
            _require(final["provenance"]["source_artifact_id"] == decisions["artifact_id"], "topic decision provenance differs")
            compiled_topic = compiled_topics[target]
            _require(all(compiled_topic[key] == original[key] for key in ("word_start_id", "word_end_id", "transcript_revision_id", "topic_set_id", "sequence"))
                and compiled_topic["title"] == original["proposed_title"], "compiled topic bounds differ")
        markdown = ["# Проверенные темы", ""]
        for final in result["topics"]:
            origin = topics[final["id"]]
            markdown.extend(["## " + final["title"], "", "Статус: " + final["status"], "", final["summary"], "",
                f"Источник: {manifest['source_id']}; {origin['locator']['start_seconds']}–{origin['locator']['end_seconds']} с.", "",
                "> " + origin["quote"].replace("\n", "\n> "), ""])
        _require(payload(manifest["result"]["markdown"]) == "\n".join(markdown).encode(), "readable Knowledge contradicts verified result")
        derived = records["derived_manifest"]
        _require(derived["artifact_type"] == "seminartext.managed_generated_export" and derived["kind"] == "obsidian_derived_view", "derived view contract differs")
        _require(derived["canonical_evidence_sha256"] == refs["compiled_evidence"]["sha256"] and derived["canonical_knowledge_sha256"] == result_ref["sha256"], "derived view input differs")
        for name, digest in derived["files"].items():
            path = "view/" + _relative(name)
            _require(path in files and _sha(files[path]) == digest, "derived view file differs")
            expected_files.add(path)
        validate_source_export({name: files["view/" + name] for name in derived["files"]}, derived)
        _verify_pinned_view(files, refs, result_ref, derived)
    else:
        _require(decisions["schema_version"] == "2.0.0" and decisions["boundary_authority"] == "PRODUCT_OWNER_DOMAIN_REVIEW", "V2 boundary confirmation missing")
        _require(receipt["status"] == "REVIEWED_TOPICS_CREATED" and receipt["reviewed_topics_sha256"] == result_ref["sha256"] and receipt["reviewed_topics_markdown_sha256"] == manifest["result"]["markdown"]["sha256"], "V2 receipt result differs")
        _require(result["artifact_type"] == "seminartext.human_review_result" and result["schema_version"] == "2.0.0" and result["application_status"] == "APPLIED", "V2 result contract differs")
        _require(result["decision_artifact"] == {"artifact_id": decisions["artifact_id"], "sha256": refs["decisions"]["sha256"]}, "V2 decision provenance differs")
        _require(result["canonical_evidence"] == package["canonical_evidence"] and result["review_package"] == {"artifact_id": package["artifact_id"], "sha256": refs["review_package"]["sha256"]}, "V2 source provenance differs")
        _require(result["word_timeline"]["sha256"] == refs["word_timeline"]["sha256"] and records["word_timeline"]["words"] == evidence["words"], "V2 timeline differs")
        _require(result["source_topic_snapshots"] == package["topics"] and result["seminar_structure"] == [], "V2 source topic inventory differs")
        units = _index(result["semantic_knowledge"] + result["non_semantic_excluded"])
        _require(all(item["disposition"] == "SEMANTIC_KNOWLEDGE" for item in result["semantic_knowledge"])
            and all(item["disposition"] == "NON_SEMANTIC_EXCLUDED" for item in result["non_semantic_excluded"]), "V2 container contradicts disposition")
        fragments = _index(result["fragment_lineage"])
        _require(len(units) == len(topics) == len(fragments), "V2 result count differs")
        for target, decision in by_topic.items():
            _require(decision["operations"] in (["ACCEPT"], ["EXCLUDE"]) and len(decision["source_fragments"]) == len(decision["results"]) == 1, "unsupported V2 transformation")
            fragment, unit_input = decision["source_fragments"][0], decision["results"][0]
            original = topics[target]
            _require(all(fragment[key] == original[key] for key in ("source_id", "transcript_revision_id", "word_start_id", "word_end_id", "evidence_refs")), "V2 changes original bounds")
            lineage = fragments[fragment["id"]]
            _require(all(lineage[key] == value for key, value in fragment.items()) and all(lineage[key] == value for key, value in _span(fragment, evidence).items()), "V2 lineage quote/range differs")
            unit = units[unit_input["id"]]
            _require(all(unit[key] == value for key, value in unit_input.items()), "V2 result differs from decision")
            disposition = "SEMANTIC_KNOWLEDGE" if decision["operations"] == ["ACCEPT"] else "NON_SEMANTIC_EXCLUDED"
            _require(unit["disposition"] == disposition and unit["title"] == original["proposed_title"] and unit["summary"] == original["proposed_summary"], "V2 decision meaning differs")
            _require(unit["fragment_refs"] == [fragment["id"]], "V2 fragment consumption differs")
            _require(all(unit[key] == value for key, value in _span(fragment, evidence).items() if key != "quote"), "V2 result range differs")
            provenance = unit["provenance"]
            _require(provenance["review_decision_id"] == decision["id"] and provenance["decision_artifact_sha256"] == refs["decisions"]["sha256"] and provenance["canonical_evidence_sha256"] == refs["evidence"]["sha256"] and provenance["word_timeline_sha256"] == refs["word_timeline"]["sha256"], "V2 result lineage differs")
            actor = lineage["review_decision_provenance"]
            _require(actor["actor_id"] == decisions["reviewer"]["actor_id"] and actor["actor_type"] == decisions["reviewer"]["actor_type"]
                and actor["review_decision_id"] == decision["id"] and actor["decision_artifact_sha256"] == refs["decisions"]["sha256"], "V2 fragment actor differs")
        markdown = ["# Проверенные фрагменты", "", "Результат проверки точных фрагментов; Canonical Knowledge не создавался.", ""]
        for disposition, label in (("semantic_knowledge", "Включён в знания"), ("non_semantic_excluded", "Исключён из знаний")):
            for unit in result[disposition]:
                quote = " ".join(fragments[ref]["quote"] for ref in unit["fragment_refs"])
                markdown.extend(["## " + unit["title"], "", "Решение: " + label, "", unit["summary"], "",
                    f"Источник: {manifest['source_id']}; {unit['locator']['start_seconds']}–{unit['locator']['end_seconds']} с.", "",
                    "> " + quote.replace("\n", "\n> "), ""])
        _require(payload(manifest["result"]["markdown"]) == "\n".join(markdown).encode(), "readable fragments contradict verified result")
    accepted = sum(item.get("action") == "ACCEPT" or item.get("operations") == ["ACCEPT"] for item in decision_records.values())
    _require(receipt["accepted"] == accepted and receipt["rejected"] == len(topics) - accepted, "receipt counts differ")
    _require(set(files) == expected_files, "unexpected unbound package files")


def validate_reviewed_result_package(manifest, files):
    """Validate V2 in memory; V1 also reproduces derived bytes in a temporary pinned runtime snapshot."""
    try:
        _validate(manifest, files)
    except (ValueError, KeyError, TypeError, IndexError, StopIteration, AttributeError, OSError) as error:
        raise PublishingError("Reviewed result package validation failed: " + str(error)) from error


def build_reviewed_result_package(*, project_dir, source_id, decisions_path, project_id, project_slug):
    root = Path(project_dir).resolve(strict=True)
    decision_file = _inside(Path(decisions_path), root, "saved review decisions")
    package_dir = decision_file.parent
    expected_parent = _review_root(root, source_id) / "topic-review"
    _require(package_dir.parent == expected_parent and decision_file.name == "decisions.json", "decisions are not owned by this source")
    _require(re.fullmatch(r"[0-9a-f]{64}", package_dir.name) is not None, "invalid review package identity")
    # Never use the runtime replay to create a new result or decision.
    receipt_path = _inside(package_dir / "result/result.json", root, "completed review receipt")
    ledger = json.loads(decision_file.read_text())
    v2 = ledger.get("schema_version") == "2.0.0"
    choices = [{"topic_id": item["target_ids"][0],
                "action": ("ACCEPT" if item["operations"] == ["ACCEPT"] else "REJECT") if v2 else item["action"],
                "reason": item["reason"]} for item in ledger["decisions"]]
    before = _sha256(decision_file)
    replay = apply_topic_review(root, source_id=source_id, expected_package_sha256=package_dir.name,
                               reviewer_id=ledger["reviewer"]["actor_id"], decisions=choices,
                               boundaries_acknowledged=v2 and ledger.get("boundary_authority") == "PRODUCT_OWNER_DOMAIN_REVIEW")
    _require(before == _sha256(decision_file), "replay modified saved decisions")
    with _locked(root, source_id):
        binding = json.loads(_inside(package_dir / "binding.json", root, "review binding").read_text())
        files, provenance = {}, {}

        def add(role, path, relative):
            data = _inside(path, root, role).read_bytes()
            files[relative] = data
            provenance[role] = {"path": relative, "sha256": _sha(data)}

        add("evidence", Path(binding["evidence_path"]), "provenance/canonical_evidence.json")
        add("topic_output", Path(binding["topics_path"]), "provenance/topic_output.json")
        add("review_package", package_dir / "review/review_package.json", "provenance/review_package.json")
        add("decisions", decision_file, "provenance/decisions.json")
        add("receipt", receipt_path, "provenance/receipt.json")
        package = json.loads(files["provenance/review_package.json"])
        draft_candidates = (_review_root(root, source_id) / "topic-drafts").glob("*.json")
        draft = next((path for path in draft_candidates if not path.is_symlink() and _sha256(path) == package["draft_input"]["sha256"]), None)
        _require(draft is not None, "original versioned topic draft is unavailable")
        add("draft_input", draft, "provenance/topic_drafts.json")
        kind = V2 if replay["status"] == "REVIEWED_TOPICS_CREATED" else V1
        portable_binding = {key: binding[key] for key in ("source_id", "evidence_sha256", "topics_sha256", "package_sha256")}
        portable_binding["review_mode"] = "EXACT_FRAGMENTS_V2" if kind == V2 else V1
        if kind == V2:
            add("word_timeline", Path(binding["timeline_path"]), "provenance/word_timeline.json")
            portable_binding["timeline_sha256"] = binding["timeline_sha256"]
            result_path, markdown_path = Path(replay["reviewed_topics_path"]), Path(replay["reviewed_topics_markdown_path"])
        else:
            result_path, markdown_path = Path(replay["canonical_knowledge_path"]), Path(replay["knowledge_markdown_path"])
            add("knowledge_input", package_dir / "result/reviewed_topics.json", "provenance/knowledge_input.json")
            add("compiled_evidence", result_path.parent / "canonical_evidence.json", "provenance/compiled_evidence.json")
            add("source_evidence", Path(replay["source_evidence_path"]), "provenance/source_evidence.json")
            derived_path = package_dir / "result/derived-view/.seminartext-export.json"
            add("derived_manifest", derived_path, "provenance/derived_manifest.json")
            derived = json.loads(files["provenance/derived_manifest.json"])
            for name in derived["files"]:
                _relative(name)
                files["view/" + name] = _inside(derived_path.parent / name, root, "derived note").read_bytes()
        files["provenance/binding.json"] = canonical_json(portable_binding) + b"\n"
        provenance["binding"] = {"path": "provenance/binding.json", "sha256": _sha(files["provenance/binding.json"])}
        files["result/result.json"] = _inside(result_path, root, "review result").read_bytes()
        files["result/result.md"] = _inside(markdown_path, root, "review Markdown").read_bytes()
        result_ref = {"path": "result/result.json", "sha256": _sha(files["result/result.json"]),
                      "markdown": {"path": "result/result.md", "sha256": _sha(files["result/result.md"])}}
        manifest = {"artifact_type": TYPE, "schema_version": "1.0", "project_id": project_id, "project_slug": project_slug,
                    "source_id": source_id, "created_at": max(item["timestamp"] for item in ledger["decisions"]),
                    "result_kind": kind, "result": result_ref, "provenance": provenance,
                    "semantic_authority": "DERIVED_SOURCE_TRUTH_PRESERVED", "source_artifacts_modified": False,
                    "files": [{"path": name, "size_bytes": len(data), "sha256": _sha(data), "ownership_class": "MANAGED_GENERATED"}
                              for name, data in sorted(files.items())]}
        manifest["version_sha256"] = content_sha256(_identity(manifest))
        manifest["package_id"] = derive_imported_id("artifact", "integra.reviewed_result", project_id, manifest["version_sha256"])
        _require(not any(str(root).encode() in data for data in files.values()), "upstream artifact contains a local project path; exact source bytes cannot be exported portably")
        validate_reviewed_result_package(manifest, files)
        return manifest, dict(sorted(files.items()))
