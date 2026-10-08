"""Explicit topic decisions through the pinned SeminarText review/knowledge tools.

Preparation has no semantic authority. Each topic must receive an explicit
accept/reject choice against the displayed immutable package before compilation.
All component writes are confined to a private Integra-owned snapshot.
"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

from .protocol import canonical_json, content_sha256
from .seminartext_evidence_runtime import (
    _inside, _now, _review_root, _runtime_root, _sha256, prepare_topic_review_input,
)
from .transcript_output import resolve_persisted_project_path


RUNTIME_FILES = {
    "seminartext_modules/human_review_workflow.py": "7187819a19360fe023c9ddcc3a723ca638a1b1b74769c02c41829cd344da72dc",
    "seminartext_modules/project_knowledge_bridge.py": "39bc3191cbfa07e32b9a2526ede428289fd020e93f9bd13539321ebb39165a5f",
    "schemas/validate_canonical_knowledge_v1.py": "14869b0d77bed839758afb0455cffcfcba4173495554eddd9159a02309f1c095",
    "schemas/canonical_knowledge_v1.schema.json": "33691770411b4e5fc4e923920619396f7281bcd655202f8f56ddba99b844111b",
    "schemas/canonical_knowledge_lifecycle_v1.json": "c9133fe6ff630dd44475f40d37d731f407ce2f79d1d15613454a1d5c179099bc",
    "schemas/topic_review_workflow_v1.schema.json": "c4ad9201ee217d5d311397cea6daef8d6e6bc75c88e9c7d3ec0d129190bacec1",
    "schemas/topic_review_workflow_v2.schema.json": "7dede105b8339f46c100c8bed07ad93ace01811e8c26d3a27d204cd6692012b0",
    "schemas/project_knowledge_input_v1.schema.json": "bd9a77e8f99f7a53de8daf9c4c697b049f4f28b10ee6b2e3e00fbd85584cb58b",
}
REVIEW_TOOL = "seminartext_modules/human_review_workflow.py"
KNOWLEDGE_TOOL = "seminartext_modules/project_knowledge_bridge.py"


def _environment():
    env = dict(os.environ)
    bundled = Path(__file__).resolve().parents[1] / "runtime/review-python/site-packages"
    if bundled.is_dir():
        env["PYTHONPATH"] = str(bundled) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _python():
    executable = os.environ.get("INTEGRA_REVIEW_PYTHON") or shutil.which("python3.14")
    if not executable and sys.version_info[:2] == (3, 14):
        executable = sys.executable
    if not executable:
        executable = next((path for path in ("/opt/homebrew/bin/python3.14", "/usr/local/bin/python3.14")
                           if Path(path).is_file() and os.access(path, os.X_OK)), None)
    if not executable:
        raise ValueError("Topic review requires Python 3.14")
    result = subprocess.run([executable, "-c", "import sys; print('%d.%d' % sys.version_info[:2])"],
                            capture_output=True, text=True, timeout=10)
    if result.returncode or result.stdout.strip() != "3.14":
        raise ValueError("Topic review requires Python 3.14")
    return executable


def preflight():
    runtime, origin = _runtime_root()
    for relative, expected in RUNTIME_FILES.items():
        path = _inside(runtime / relative, runtime, "SeminarText review runtime")
        if _sha256(path) != expected:
            raise ValueError(f"SeminarText review runtime differs from the pin: {relative}")
    check = subprocess.run([_python(), "-c", "from jsonschema import Draft202012Validator"],
                           env=_environment(), capture_output=True, text=True, timeout=15)
    if check.returncode:
        raise ValueError("Topic review requires the bundled jsonschema runtime")
    return {"state": "READY", "runtime": str(runtime), "origin": origin}


def _invoke(runtime, tool, *arguments):
    result = subprocess.run([_python(), str(Path(runtime) / tool), *map(str, arguments)],
                            env=_environment(), capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise ValueError((result.stderr or result.stdout or "SeminarText review failed").strip()[:1000])
    value = json.loads(result.stdout)
    if not isinstance(value, dict):
        raise ValueError("SeminarText returned an invalid result")
    return value


def _write(path, value):
    path.write_bytes(canonical_json(value) + b"\n")


def _resolve_binding_paths(root, binding):
    """Use current project locations for legacy absolute binding references.

    The binding itself remains an immutable record in a content-addressed review
    package.  Only this in-memory view is rebased through the same strict
    project-identity rule used by all persisted output paths.
    """
    if not isinstance(binding, dict):
        raise ValueError("review binding is invalid")
    resolved = dict(binding)
    for name, label in (("evidence", "Canonical Evidence"), ("topics", "topic drafts"),
                        ("timeline", "Word Timeline")):
        key = name + "_path"
        if key in resolved:
            if not isinstance(resolved[key], str):
                raise ValueError(f"review binding {name} path is invalid")
            resolved[key] = str(resolve_persisted_project_path(root, resolved[key], label))
    return resolved


@contextmanager
def _locked(root, source_id):
    directory = _review_root(root, source_id) / "topic-review"
    current = root
    for part in directory.relative_to(root).parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("topic review directory is unsafe")
        current.mkdir(exist_ok=True)
    descriptor = os.open(directory / "review.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError("topic review is already running for this source") from error
        try:
            yield directory
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def _presentation(package_path):
    package = json.loads(package_path.read_text(encoding="utf-8"))
    binding = json.loads((package_path.parent.parent / "binding.json").read_text())
    mode = _bound_mode(binding, package, package_path.parent.parent / "project/evidence/canonical_bundle.json")
    return {"status": "REVIEW_REQUIRED", "automatic_acceptance": False,
            "review_mode": mode,
            "package_path": str(package_path), "package_sha256": _sha256(package_path),
            "topics": [{"id": item["id"], "title": item["proposed_title"],
                        "summary": item["proposed_summary"], "quote": item["quote"],
                        "word_start_id": item["word_start_id"], "word_end_id": item["word_end_id"],
                        "transcript_revision_id": item["transcript_revision_id"],
                        "source_id": item["source_id"], "evidence_refs": item["evidence_refs"],
                        "start_seconds": item["locator"]["start_seconds"],
                        "end_seconds": item["locator"]["end_seconds"]} for item in package["topics"]]}


def present_machine_process_topics(project_dir, *, source_id, topics_path):
    """Return the persisted machine Topic result as a Process-only view.

    This is deliberately a reader, not a second Topic generator or a review
    operation.  A non-empty summary is required before the normal result
    surface may present it as one: an absent source summary must remain an
    honest unavailable result rather than being replaced by a title or quote.
    """
    root = Path(project_dir).resolve(strict=True)
    topics_file = _inside(Path(topics_path), root, "machine Topics")
    try:
        payload = json.loads(topics_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("saved machine Topics are invalid") from error
    topics = payload.get("topics") if isinstance(payload, dict) else None
    if payload.get("component") != "seminartext" or not isinstance(topics, list) or not topics:
        raise ValueError("saved machine Topics are unavailable")
    digest = _sha256(topics_file)
    presented = []
    for sequence, topic in enumerate(topics):
        if not isinstance(topic, dict) or topic.get("semantic_status") != "REVIEW_REQUIRED":
            raise ValueError("saved machine Topics have invalid review authority")
        title = topic.get("title")
        summary = topic.get("summary")
        start = topic.get("start_seconds")
        end = topic.get("end_seconds")
        if (not isinstance(title, str) or not title.strip() or not isinstance(summary, str)
                or not summary.strip() or not isinstance(start, (int, float))
                or not isinstance(end, (int, float)) or end <= start):
            raise ValueError("a saved Topic has no usable source summary")
        presented.append({
            "id": f"machine-topic-{digest[:20]}-{sequence:04d}",
            "title": title.strip(),
            "summary": summary.strip(),
            "start_seconds": start,
            "end_seconds": end,
            "source_span": {
                "start_segment_id": topic.get("start_segment_id"),
                "evidence_start_id": topic.get("evidence_start_id"),
                "evidence_end_id": topic.get("evidence_end_id"),
            },
        })
    return {
        "status": "PROCESS_MACHINE_TOPICS",
        "authority": "MACHINE_OUTPUT_REQUIRES_HUMAN_DECISION",
        "automatic_acceptance": False,
        "read_only": True,
        "source_id": source_id,
        "topics_sha256": digest,
        "topics": presented,
    }


def _review_mode(package, evidence):
    """Select a real compatible component path without changing source ranges."""
    words = {item["id"]: item for item in evidence["words"]}
    for topic in package["topics"]:
        first = words[topic["word_start_id"]]["sequence"]
        last = words[topic["word_end_id"]]["sequence"]
        segments = sorted((item for item in evidence["benchmark_segments"]
            if item["transcript_revision_id"] == topic["transcript_revision_id"]
            and words[item["word_start_id"]]["sequence"] >= first
            and words[item["word_end_id"]]["sequence"] <= last), key=lambda item: item["sequence"])
        if not segments or segments[0]["word_start_id"] != topic["word_start_id"] or segments[-1]["word_end_id"] != topic["word_end_id"]:
            return "EXACT_FRAGMENTS_V2"
    return "CANONICAL_KNOWLEDGE_V1"


def _bound_mode(binding, package, snapshot_path):
    """Recover pre-V2 metadata only when unchanged evidence proves the V1 path."""
    if snapshot_path.is_symlink() or _sha256(snapshot_path) != binding["evidence_sha256"]:
        raise ValueError("Evidence snapshot changed")
    mode = ("EXACT_FRAGMENTS_V2" if binding.get("exact_fragments") is True else
            _review_mode(package, json.loads(snapshot_path.read_text())))
    recorded = binding.get("review_mode")
    if "review_mode" not in binding and mode == "CANONICAL_KNOWLEDGE_V1":
        return mode
    if recorded != mode:
        raise ValueError("persisted review mode differs from the Evidence contract")
    return mode


def prepare_topic_review(project_dir, *, source_id, canonical_evidence_path, topics_path, exact_fragments=False):
    """Prepare the pinned review package; opt-in K1 mode never selects the V1 compiler."""
    runtime = preflight()["runtime"]
    root = Path(project_dir).resolve(strict=True)
    evidence = _inside(Path(canonical_evidence_path), root, "Canonical Evidence")
    topics = _inside(Path(topics_path), root, "topic drafts")
    with _locked(root, source_id) as directory:
        binding = {"source_id": source_id, "evidence_path": str(evidence), "evidence_sha256": _sha256(evidence),
                   "topics_path": str(topics), "topics_sha256": _sha256(topics)}
        if exact_fragments:
            binding["exact_fragments"] = True
        drafts = prepare_topic_review_input(root, source_id=source_id,
                                           canonical_evidence_path=str(evidence), topics_path=str(topics),
                                           exact_fragments=exact_fragments)
        binding["boundary_mappings"] = drafts["boundary_mappings"]
        with tempfile.TemporaryDirectory(prefix=".prepare-", dir=directory) as temporary:
            stage = Path(temporary)
            component = stage / "project"
            (component / "evidence").mkdir(parents=True)
            shutil.copyfile(evidence, component / "evidence/canonical_bundle.json")
            if _sha256(component / "evidence/canonical_bundle.json") != binding["evidence_sha256"]:
                raise ValueError("Canonical Evidence changed during preparation")
            _invoke(runtime, REVIEW_TOOL, "prepare", component, "--drafts", drafts["topic_drafts_path"], "--output", stage / "review")
            package_path = stage / "review/review_package.json"
            snapshot = json.loads((component / "evidence/canonical_bundle.json").read_text())
            binding["review_mode"] = ("EXACT_FRAGMENTS_V2" if exact_fragments else
                                      _review_mode(json.loads(package_path.read_text()), snapshot))
            if binding["review_mode"] == "EXACT_FRAGMENTS_V2":
                timeline = _inside(evidence.parent / "word_timeline.json", root, "component Word Timeline")
                timeline_bytes = timeline.read_bytes()
                timeline_record = json.loads(timeline_bytes)
                if timeline_record.get("words") != snapshot["words"]:
                    raise ValueError("component Word Timeline differs from Canonical Evidence")
                binding.update(timeline_path=str(timeline), timeline_sha256=hashlib.sha256(timeline_bytes).hexdigest())
                (component / "evidence/word_timeline.json").write_bytes(timeline_bytes)
            if _sha256(topics) != binding["topics_sha256"] or _sha256(evidence) != binding["evidence_sha256"]:
                raise ValueError("review inputs changed during preparation")
            digest = _sha256(package_path)
            target = directory / digest
            binding["package_sha256"] = digest
            _write(stage / "binding.json", binding)
            if target.exists():
                prior = _inside(target / "review/review_package.json", root, "review package")
                prior_binding = _resolve_binding_paths(root, json.loads(
                    _inside(target / "binding.json", root, "review binding").read_text()))
                prior_binding["review_mode"] = _bound_mode(prior_binding, json.loads(prior.read_text()),
                    _inside(target / "project/evidence/canonical_bundle.json", root, "Evidence snapshot"))
                if _sha256(prior) != digest or prior_binding != binding:
                    raise ValueError("topic review package collision")
            else:
                os.rename(stage, target)
                # TemporaryDirectory cleanup is harmless after atomic promotion.
            return _presentation(target / "review/review_package.json")


def _choices(package, reviewer_id, decisions, *, v2=False):
    if not isinstance(reviewer_id, str) or re.fullmatch(r"[a-z][a-z0-9._:-]{2,127}", reviewer_id) is None:
        raise ValueError("reviewer identifier must be a stable lowercase identifier")
    if not isinstance(decisions, list) or not decisions:
        raise ValueError("explicit accept/reject decisions are required")
    by_id = {item["id"]: item for item in package["topics"]}
    choices = {}
    for item in decisions:
        required = {"topic_id", "action", "reason"}
        optional = {"new_title", "new_summary", "word_start_id", "word_end_id"}
        editing = isinstance(item, dict) and v2 and item.get("action") in {"EDIT", "RENAME"}
        if (not isinstance(item, dict) or not required.issubset(item)
                or (not editing and set(item) != required)
                or (editing and not set(item).issubset(required | optional))):
            raise ValueError("each decision requires topic_id, action and reason")
        topic_id = item["topic_id"]
        if not isinstance(topic_id, str) or topic_id not in by_id or topic_id in choices:
            raise ValueError("unknown or duplicate topic decision")
        if item["action"] not in (("ACCEPT", "REJECT", "EDIT", "RENAME") if v2 else ("ACCEPT", "REJECT")) or not isinstance(item["reason"], str) or not item["reason"].strip():
            raise ValueError("an explicit ACCEPT/REJECT action and reason are required")
        if editing:
            if (not isinstance(item.get("new_title"), str) or not item["new_title"].strip()
                    or not isinstance(item.get("new_summary"), str)):
                raise ValueError("an exact fragment edit requires title and summary")
            if ("word_start_id" in item) != ("word_end_id" in item):
                raise ValueError("an exact fragment edit requires both word endpoints")
            if any(not isinstance(item[key], str) or not item[key] for key in ("word_start_id", "word_end_id") if key in item):
                raise ValueError("an exact fragment edit requires canonical word IDs")
        choices[topic_id] = dict(item)
        if editing:
            choices[topic_id].update(action="EDIT",
                word_start_id=item.get("word_start_id", by_id[topic_id]["word_start_id"]),
                word_end_id=item.get("word_end_id", by_id[topic_id]["word_end_id"]))
    if set(choices) != set(by_id):
        raise ValueError("every topic requires an explicit decision")
    return [choices[key] for key in sorted(choices)]


def _v2_choice_records(package, evidence, choices):
    """Translate bounded UI choices into the existing lossless V2 partition."""
    by_id = {topic["id"]: topic for topic in package["topics"]}
    words = {word["id"]: word for word in evidence["words"]}
    records = []
    for choice in choices:
        topic = by_id[choice["topic_id"]]
        token = hashlib.sha256(topic["id"].encode()).hexdigest()
        first, last = words[topic["word_start_id"]], words[topic["word_end_id"]]
        selected_first = words.get(choice.get("word_start_id", first["id"]))
        selected_last = words.get(choice.get("word_end_id", last["id"]))
        if (selected_first is None or selected_last is None
                or any(word["source_id"] != topic["source_id"] or word["transcript_revision_id"] != topic["transcript_revision_id"]
                       for word in (selected_first, selected_last))
                or not first["sequence"] <= selected_first["sequence"] <= selected_last["sequence"] <= last["sequence"]):
            raise ValueError("edited word range must stay inside the original exact Topic")
        if choice["action"] in {"EDIT", "RENAME"} and any(word.get("alignment_status") == "unaligned"
               or any(isinstance(word.get(key), bool) or not isinstance(word.get(key), (int, float))
                      or not math.isfinite(word[key]) for key in ("start_seconds", "end_seconds"))
               for word in (selected_first, selected_last)):
            raise ValueError("exact fragment endpoints require available aligned timing")
        source_words = {word["sequence"]: word for word in words.values()
                        if word["source_id"] == topic["source_id"] and word["transcript_revision_id"] == topic["transcript_revision_id"]}
        if any(sequence not in source_words for sequence in range(first["sequence"], last["sequence"] + 1)):
            raise ValueError("the original exact Topic has a non-contiguous Word Timeline")
        ranges = []
        if selected_first["sequence"] > first["sequence"]:
            ranges.append(("_prefix", first, source_words[selected_first["sequence"] - 1], False))
        ranges.append(("", selected_first, selected_last, choice["action"] != "REJECT"))
        if selected_last["sequence"] < last["sequence"]:
            ranges.append(("_suffix", source_words[selected_last["sequence"] + 1], last, False))
        editing = choice["action"] in {"EDIT", "RENAME"}
        operations = ["RENAME"] if editing else ["ACCEPT" if choice["action"] == "ACCEPT" else "EXCLUDE"]
        if len(ranges) > 1:
            operations += ["TRIM", "EXCLUDE"]
        fragments, units = [], []
        for suffix, start, end, included in ranges:
            fragment_id = "fragment_" + token + suffix
            fragments.append({"id": fragment_id, "source_topic_id": topic["id"],
                "source_id": topic["source_id"], "transcript_revision_id": topic["transcript_revision_id"],
                "word_start_id": start["id"], "word_end_id": end["id"], "evidence_refs": topic["evidence_refs"]})
            units.append({"id": "reviewed_fragment_" + token + suffix,
                "disposition": "SEMANTIC_KNOWLEDGE" if included else "NON_SEMANTIC_EXCLUDED",
                "title": choice["new_title"] if included and editing else topic["proposed_title"],
                "summary": choice["new_summary"] if included and editing else topic["proposed_summary"],
                "sequence": topic["sequence"], "fragment_refs": [fragment_id], "evidence_refs": topic["evidence_refs"]})
        records.append({"id": "decision_" + token, "operations": operations, "target_ids": [topic["id"]],
            "expected_topics": [{"topic_id": topic["id"], "topic_sha256": topic["topic_sha256"]}],
            "source_fragments": fragments, "results": units, "reason": choice["reason"]})
    return records


def v2_replay_choices(ledger):
    """Recover the exact bounded UI intent, including edits and trimmed ranges."""
    choices = []
    for decision in ledger["decisions"]:
        semantic = [unit for unit in decision["results"] if unit["disposition"] == "SEMANTIC_KNOWLEDGE"]
        editing = "RENAME" in decision["operations"]
        choice = {"topic_id": decision["target_ids"][0],
                  "action": "EDIT" if editing else ("ACCEPT" if semantic else "REJECT"), "reason": decision["reason"]}
        if editing:
            if len(semantic) != 1 or len(semantic[0]["fragment_refs"]) != 1:
                raise ValueError("unsupported edited V2 composition")
            fragments = {fragment["id"]: fragment for fragment in decision["source_fragments"]}
            fragment = fragments[semantic[0]["fragment_refs"][0]]
            choice.update(new_title=semantic[0]["title"], new_summary=semantic[0]["summary"])
            choice.update(word_start_id=fragment["word_start_id"], word_end_id=fragment["word_end_id"])
        choices.append(choice)
    return choices


def _apply_fragments_v2(root, package_dir, runtime, source_id, package_path, package,
                        package_sha256, reviewer_id, choices):
    """Apply explicit fragment inclusion/exclusion; this does not compile Canonical Knowledge."""
    key = content_sha256({"package": package_sha256, "reviewer": reviewer_id, "choices": choices,
                          "boundaries_acknowledged": True, "review_mode": "EXACT_FRAGMENTS_V2"})
    decision_path = package_dir / "decisions.json"
    previous = None
    if decision_path.exists():
        previous = json.loads(_inside(decision_path, root, "persisted fragment decisions").read_text())
        if previous.get("artifact_id") != "review_decisions_" + key:
            raise ValueError("this package already has different persisted decisions")
    evidence = json.loads((package_dir / "project/evidence/canonical_bundle.json").read_text())
    records = _v2_choice_records(package, evidence, choices)
    for number, record in enumerate(records):
        record["timestamp"] = previous["decisions"][number]["timestamp"] if previous else _now()
    ledger = {"schema_version": "2.0.0", "artifact_type": "seminartext.topic_review_decisions",
              "artifact_id": "review_decisions_" + key, "review_package_id": package["artifact_id"],
              "review_package_sha256": package_sha256,
              "reviewer": {"actor_type": "human_domain_reviewer", "actor_id": reviewer_id},
              "boundary_authority": "PRODUCT_OWNER_DOMAIN_REVIEW", "decisions": records,
              "limitations": ["The reviewer explicitly confirmed inclusion/exclusion and the complete displayed word boundaries. No Canonical Knowledge compilation is performed."]}
    if previous is not None and previous != ledger:
        raise ValueError("persisted fragment decisions changed")
    if previous is None:
        temporary = package_dir / "decisions.tmp"
        _write(temporary, ledger)
        os.replace(temporary, decision_path)
    result_dir = package_dir / "result"
    if not result_dir.exists():
        with tempfile.TemporaryDirectory(prefix=".apply-", dir=package_dir) as temporary:
            stage = Path(temporary)
            component = stage / "project"
            shutil.copytree(package_dir / "project", component)
            output = stage / "reviewed_topics.json"
            applied = _invoke(runtime, REVIEW_TOOL, "apply-v2", component, "--package", package_path,
                              "--decisions", decision_path, "--output", output)
            if applied.get("status") != "PASS" or applied.get("output_sha256") != _sha256(output):
                raise ValueError("SeminarText exact fragment review did not pass")
            reviewed = json.loads(output.read_text())
            if reviewed.get("artifact_type") != "seminartext.human_review_result" or reviewed.get("application_status") != "APPLIED":
                raise ValueError("SeminarText exact fragment review returned an invalid contract")
            lineage = {item["id"]: item for item in reviewed["fragment_lineage"]}
            markdown = ["# Проверенные фрагменты", "", "Результат проверки точных фрагментов; Canonical Knowledge не создавался.", ""]
            for disposition, label in (("semantic_knowledge", "Включён в знания"), ("non_semantic_excluded", "Исключён из знаний")):
                for item in reviewed[disposition]:
                    quote = " ".join(lineage[ref]["quote"] for ref in item["fragment_refs"])
                    markdown.extend(["## " + item["title"], "", "Решение: " + label, "", item["summary"], "",
                        f"Источник: {source_id}; {item['locator']['start_seconds']}–{item['locator']['end_seconds']} с.", "",
                        "> " + quote.replace("\n", "\n> "), ""])
            (stage / "reviewed_topics.md").write_text("\n".join(markdown), encoding="utf-8")
            result = {"status": "REVIEWED_TOPICS_CREATED", "review_mode": "EXACT_FRAGMENTS_V2",
                      "package_sha256": package_sha256, "decisions_sha256": _sha256(decision_path),
                      "accepted": len(reviewed["semantic_knowledge"]), "rejected": len(reviewed["non_semantic_excluded"]),
                      "automatic_acceptance": False, "reviewed_topics_sha256": _sha256(output),
                      "reviewed_topics_markdown_sha256": _sha256(stage / "reviewed_topics.md")}
            _write(stage / "result.json", result)
            os.rename(stage, result_dir)
    result = json.loads(_inside(result_dir / "result.json", root, "fragment review result").read_text())
    if result["decisions_sha256"] != _sha256(decision_path) or result.get("status") != "REVIEWED_TOPICS_CREATED":
        raise ValueError("persisted fragment review result changed")
    for key, filename in (("reviewed_topics", "reviewed_topics.json"), ("reviewed_topics_markdown", "reviewed_topics.md")):
        path = _inside(result_dir / filename, root, key)
        if _sha256(path) != result[key + "_sha256"]:
            raise ValueError("reviewed fragment artifact changed")
        result[key + "_path"] = str(path)
    return result | {"decisions_path": str(decision_path), "review_result_path": str(result_dir / "result.json")}


def apply_topic_review(project_dir, *, source_id, expected_package_sha256, reviewer_id, decisions, boundaries_acknowledged=False):
    runtime = preflight()["runtime"]
    root = Path(project_dir).resolve(strict=True)
    if not isinstance(expected_package_sha256, str) or re.fullmatch(r"[0-9a-f]{64}", expected_package_sha256) is None:
        raise ValueError("the displayed review package hash is required")
    with _locked(root, source_id) as directory:
        package_dir = directory / expected_package_sha256
        package_path = _inside(package_dir / "review/review_package.json", root, "review package")
        if _sha256(package_path) != expected_package_sha256:
            raise ValueError("review package changed")
        binding = _resolve_binding_paths(root, json.loads(
            _inside(package_dir / "binding.json", root, "review binding").read_text()))
        if binding["source_id"] != source_id or binding["package_sha256"] != expected_package_sha256:
            raise ValueError("review package belongs to another source")
        for name in ("evidence", "topics"):
            current = _inside(Path(binding[name + "_path"]), root, name)
            if _sha256(current) != binding[name + "_sha256"]:
                raise ValueError(f"{name} changed after review preparation")
        package = json.loads(package_path.read_text())
        snapshot_path = _inside(package_dir / "project/evidence/canonical_bundle.json", root, "Evidence snapshot")
        if _sha256(snapshot_path) != binding["evidence_sha256"]:
            raise ValueError("Evidence snapshot changed")
        mode = _bound_mode(binding, package, snapshot_path)
        choices = _choices(package, reviewer_id, decisions, v2=mode == "EXACT_FRAGMENTS_V2")
        if mode == "EXACT_FRAGMENTS_V2":
            if boundaries_acknowledged is not True:
                raise ValueError("explicit confirmation of the displayed exact boundaries is required")
            for timeline in (Path(binding["timeline_path"]), package_dir / "project/evidence/word_timeline.json"):
                if _sha256(_inside(timeline, root, "Word Timeline")) != binding["timeline_sha256"]:
                    raise ValueError("Word Timeline changed after review preparation")
            return _apply_fragments_v2(root, package_dir, runtime, source_id, package_path, package,
                                       expected_package_sha256, reviewer_id, choices)
        decision_key = content_sha256({"package": expected_package_sha256, "reviewer": reviewer_id, "choices": choices})
        decision_path = package_dir / "decisions.json"
        if decision_path.exists():
            ledger = json.loads(_inside(decision_path, root, "persisted decisions").read_text())
            persisted_choices = [{"topic_id": item["target_ids"][0], "action": item["action"], "reason": item["reason"]} for item in ledger["decisions"]]
            if (ledger["artifact_id"] != "review_decisions_" + decision_key
                    or ledger["reviewer"] != {"actor_type": "human_domain_reviewer", "actor_id": reviewer_id}
                    or persisted_choices != choices):
                raise ValueError("this package already has different persisted decisions")
        else:
            by_id = {item["id"]: item for item in package["topics"]}
            ledger = {"schema_version": "1.0.0", "artifact_type": "seminartext.topic_review_decisions",
                      "artifact_id": "review_decisions_" + decision_key, "review_package_id": package["artifact_id"],
                      "review_package_sha256": expected_package_sha256,
                      "reviewer": {"actor_type": "human_domain_reviewer", "actor_id": reviewer_id},
                      "decisions": [{"id": "decision_" + hashlib.sha256(item["topic_id"].encode()).hexdigest(),
                                     "action": item["action"], "target_ids": [item["topic_id"]],
                                     "result_topics": [], "reason": item["reason"], "timestamp": _now(),
                                     "expected_topics": [{"topic_id": item["topic_id"], "topic_sha256": by_id[item["topic_id"]]["topic_sha256"]}],
                                     "new_title": None, "new_summary": None} for item in choices]}
            temporary = package_dir / "decisions.tmp"
            _write(temporary, ledger)
            os.replace(temporary, decision_path)
        result_dir = package_dir / "result"
        if not result_dir.exists():
            with tempfile.TemporaryDirectory(prefix=".apply-", dir=package_dir) as temporary:
                stage = Path(temporary)
                component = stage / "project"
                shutil.copytree(package_dir / "project", component)
                output = stage / "reviewed_topics.json"
                applied = _invoke(runtime, REVIEW_TOOL, "apply", component, "--package", package_path,
                                  "--decisions", decision_path, "--output", output)
                if applied.get("status") != "PASS":
                    raise ValueError("SeminarText topic review did not pass")
                compiled = _invoke(runtime, KNOWLEDGE_TOOL, component, "--knowledge-input", output,
                                   "--destination", stage / "derived-view")
                if compiled.get("status") != "EXPORTED":
                    raise ValueError("SeminarText knowledge compilation did not pass")
                knowledge = json.loads((component / "knowledge/canonical_knowledge.json").read_text())
                markdown = ["# Проверенные темы", ""]
                package_topics = {topic["id"]: topic for topic in package["topics"]}
                for topic in knowledge["topics"]:
                    origin = package_topics[topic["id"]]
                    markdown.extend(["## " + topic["title"], "", "Статус: " + topic["status"], "", topic["summary"], "",
                                     f"Источник: {source_id}; {origin['locator']['start_seconds']}–{origin['locator']['end_seconds']} с.", "",
                                     "> " + origin["quote"].replace("\n", "\n> "), ""])
                (stage / "knowledge.md").write_text("\n".join(markdown), encoding="utf-8")
                result = {"status": "KNOWLEDGE_CREATED", "package_sha256": expected_package_sha256,
                          "decisions_sha256": _sha256(decision_path), "accepted": applied["ACCEPTED"],
                          "rejected": applied["REJECTED"], "automatic_acceptance": False,
                          "canonical_knowledge_sha256": _sha256(component / "knowledge/canonical_knowledge.json"),
                          "knowledge_markdown_sha256": _sha256(stage / "knowledge.md"),
                          "source_evidence_sha256": _sha256(component / "knowledge/source_evidence.json")}
                _write(stage / "result.json", result)
                os.rename(stage, result_dir)
        result = json.loads(_inside(result_dir / "result.json", root, "review result").read_text())
        if result["decisions_sha256"] != _sha256(decision_path):
            raise ValueError("persisted decisions changed")
        for key in ("canonical_knowledge", "source_evidence"):
            path = _inside(result_dir / "project/knowledge" / (key + ".json"), root, key)
            if _sha256(path) != result[key + "_sha256"]:
                raise ValueError("reviewed knowledge artifact changed")
            result[key + "_path"] = str(path)
        markdown = _inside(result_dir / "knowledge.md", root, "knowledge Markdown")
        if _sha256(markdown) != result["knowledge_markdown_sha256"]:
            raise ValueError("knowledge Markdown changed")
        result["knowledge_markdown_path"] = str(markdown)
        return result | {"decisions_path": str(decision_path), "review_result_path": str(result_dir / "result.json")}


# Process v1 deliberately reuses the exact pinned Topic contract but stops
# before the Knowledge compiler.  The separate authority is persisted below.
PROCESS_V1_ACTIONS = ("ACCEPT", "RENAME", "REJECT", "DEFER")
PROCESS_TOPIC_AUTHORITY = "PROCESS_HUMAN_TOPIC_REVIEW"


def prepare_process_topic_review(project_dir, *, source_id, media_path, transcript_path,
                                 word_timeline_path, topics_path):
    """Prepare Process Topic review without recording an Evidence/Knowledge output."""
    from .seminartext_evidence_runtime import create_machine_evidence
    root = Path(project_dir).resolve(strict=True)
    # Technical machine-bound input is private to the review package; no run
    # output claims Evidence or Knowledge authority.
    machine = create_machine_evidence(root, source_id=source_id, media_path=media_path,
                                      transcript_path=transcript_path, word_timeline_path=word_timeline_path)
    package = prepare_topic_review(root, source_id=source_id,
                                   canonical_evidence_path=machine["canonical_evidence_path"], topics_path=topics_path)
    current_topics = _inside(Path(topics_path), root, "machine Topics")
    return {"status": "PROCESS_TOPIC_REVIEW_REQUIRED", "authority": PROCESS_TOPIC_AUTHORITY,
            "automatic_acceptance": False, "package_path": package["package_path"],
            "package_sha256": package["package_sha256"], "topics": package["topics"],
            "machine_topics_path": str(current_topics), "machine_topics_sha256": _sha256(current_topics)}


def _process_choices(package, reviewer_id, decisions):
    if not isinstance(reviewer_id, str) or re.fullmatch(r"[a-z][a-z0-9._:-]{2,127}", reviewer_id) is None:
        raise ValueError("reviewer identifier must be a stable lowercase identifier")
    if not isinstance(decisions, list) or not decisions:
        raise ValueError("explicit Topic decisions are required")
    topics = {item["id"]: item for item in package["topics"]}; selected = {}
    for value in decisions:
        if not isinstance(value, dict) or set(value) != {"topic_id", "action", "reason", "new_title", "new_summary"}:
            raise ValueError("each Topic decision has invalid fields")
        topic_id, action = value["topic_id"], value["action"]
        if not isinstance(topic_id, str) or topic_id not in topics or topic_id in selected:
            raise ValueError("unknown or duplicate Topic decision")
        if action not in PROCESS_V1_ACTIONS:
            raise ValueError("unsupported Process Topic action")
        if not isinstance(value["reason"], str) or not value["reason"].strip():
            raise ValueError("each Topic decision requires a reason")
        if action == "RENAME":
            if not isinstance(value["new_title"], str) or not value["new_title"].strip() or not isinstance(value["new_summary"], str):
                raise ValueError("a Topic rename requires title and summary")
        elif value["new_title"] is not None or value["new_summary"] is not None:
            raise ValueError("only a Topic rename may change title or summary")
        selected[topic_id] = dict(value)
    if set(selected) != set(topics):
        raise ValueError("every displayed Topic requires an explicit decision")
    return [selected[key] for key in sorted(selected)]


def _process_ledger(package, package_sha256, reviewer_id, choices):
    key = content_sha256({"package": package_sha256, "reviewer": reviewer_id, "choices": choices,
                          "authority": PROCESS_TOPIC_AUTHORITY})
    indexed = {item["id"]: item for item in package["topics"]}; records = []
    for choice in choices:
        topic = indexed[choice["topic_id"]]
        records.append({"id": "decision_" + hashlib.sha256(choice["topic_id"].encode()).hexdigest(),
                        "action": choice["action"], "target_ids": [choice["topic_id"]], "result_topics": [],
                        "reason": choice["reason"].strip(), "timestamp": _now(),
                        "expected_topics": [{"topic_id": choice["topic_id"], "topic_sha256": topic["topic_sha256"]}],
                        "new_title": choice["new_title"].strip() if choice["action"] == "RENAME" else None,
                        "new_summary": choice["new_summary"] if choice["action"] == "RENAME" else None})
    return {"schema_version": "1.0.0", "artifact_type": "seminartext.topic_review_decisions",
            "artifact_id": "review_decisions_" + key, "review_package_id": package["artifact_id"],
            "review_package_sha256": package_sha256,
            "reviewer": {"actor_type": "product_owner", "actor_id": reviewer_id}, "decisions": records}


def _same_process_decisions(left, right):
    def normalized(value):
        copied = json.loads(json.dumps(value))
        for decision in copied.get("decisions", []): decision.pop("timestamp", None)
        return copied
    return normalized(left) == normalized(right)


def apply_process_topic_review(project_dir, *, source_id, expected_package_sha256, reviewer_id, decisions):
    runtime = preflight()["runtime"]; root = Path(project_dir).resolve(strict=True)
    if not isinstance(expected_package_sha256, str) or re.fullmatch(r"[0-9a-f]{64}", expected_package_sha256) is None:
        raise ValueError("the displayed Topic review package hash is required")
    with _locked(root, source_id) as directory:
        package_dir = directory / expected_package_sha256
        package_path = _inside(package_dir / "review/review_package.json", root, "Topic review package")
        if _sha256(package_path) != expected_package_sha256: raise ValueError("Topic review package changed")
        binding = _resolve_binding_paths(root, json.loads(_inside(package_dir / "binding.json", root, "Topic review binding").read_text(encoding="utf-8")))
        if binding.get("source_id") != source_id or binding.get("package_sha256") != expected_package_sha256:
            raise ValueError("Topic review package belongs to another source")
        for name in ("evidence", "topics"):
            if _sha256(_inside(Path(binding[name + "_path"]), root, name)) != binding[name + "_sha256"]:
                raise ValueError(f"{name} changed after Topic review preparation")
        package = json.loads(package_path.read_text(encoding="utf-8")); choices = _process_choices(package, reviewer_id, decisions)
        ledger = _process_ledger(package, expected_package_sha256, reviewer_id, choices); decision_path = package_dir / "process_topic_decisions.json"
        if decision_path.exists():
            existing = json.loads(_inside(decision_path, root, "persisted Topic decisions").read_text(encoding="utf-8"))
            if not _same_process_decisions(existing, ledger): raise ValueError("this Topic review package already has different persisted decisions")
            ledger = existing
        else:
            temporary = package_dir / "process_topic_decisions.tmp"; _write(temporary, ledger); os.replace(temporary, decision_path)
        result_dir = package_dir / "process-result"
        if not result_dir.exists():
            with tempfile.TemporaryDirectory(prefix=".process-apply-", dir=package_dir) as temporary:
                stage = Path(temporary); component = stage / "project"; shutil.copytree(package_dir / "project", component)
                contract = stage / "reviewed_topics_contract.json"
                applied = _invoke(runtime, REVIEW_TOOL, "apply", component, "--package", package_path, "--decisions", decision_path, "--output", contract)
                if applied.get("status") != "PASS": raise ValueError("SeminarText Topic review did not pass")
                payload = json.loads(contract.read_text(encoding="utf-8")); actions = {item["target_ids"][0]: item["action"] for item in ledger["decisions"]}
                receipt = {"schema_version": "1.0", "artifact_type": "integra.process_reviewed_topics", "authority": PROCESS_TOPIC_AUTHORITY,
                           "automatic_acceptance": False, "source_id": source_id, "review_package_sha256": expected_package_sha256,
                           "machine_topics": {"path": binding["topics_path"], "sha256": binding["topics_sha256"]},
                           "boundary_mappings": binding["boundary_mappings"],
                           "review_decisions": {"path": str(decision_path), "sha256": _sha256(decision_path)},
                           "reviewed_topics_contract": {"sha256": _sha256(contract), "topic_count": len(payload.get("topics", []))},
                           "topic_actions": actions,
                           "limitations": ["Process Topic review only; no Evidence acceptance or Knowledge inclusion occurred."]}
                _write(stage / "process_topic_review_receipt.json", receipt)
                result = {"status": "PROCESS_REVIEWED_TOPICS_CREATED", "authority": PROCESS_TOPIC_AUTHORITY, "automatic_acceptance": False,
                          "package_sha256": expected_package_sha256, "decisions_sha256": _sha256(decision_path),
                          "reviewed_topics_contract_sha256": _sha256(contract), "process_topic_review_receipt_sha256": _sha256(stage / "process_topic_review_receipt.json"), "actions": actions}
                _write(stage / "result.json", result); os.rename(stage, result_dir)
        result = json.loads(_inside(result_dir / "result.json", root, "Process Topic review result").read_text(encoding="utf-8"))
        if result.get("decisions_sha256") != _sha256(decision_path) or result.get("status") != "PROCESS_REVIEWED_TOPICS_CREATED":
            raise ValueError("persisted Process Topic review changed")
        for key, name in (("reviewed_topics_contract", "reviewed_topics_contract.json"), ("process_topic_review_receipt", "process_topic_review_receipt.json")):
            path = _inside(result_dir / name, root, key)
            if _sha256(path) != result[key + "_sha256"]: raise ValueError("persisted Process Topic review artifact changed")
            result[key + "_path"] = str(path)
        return result | {"decisions_path": str(decision_path), "review_result_path": str(result_dir / "result.json")}


def load_persisted_process_topic_review(project_dir, *, source_id, reviewed_topics_contract_path,
                                        receipt_path, decisions_path):
    """Materialize an already-saved Process review without returning to machine topics.

    The reviewed contract is the sole user-facing authority after an explicit
    Process-human decision.  All three persisted artifacts are cross-checked
    before their titles are shown again; a partial or tampered saved review is
    an error, never a reason to silently fall back to the machine draft.
    """
    root = Path(project_dir).resolve(strict=True)
    contract_path = _inside(Path(reviewed_topics_contract_path), root, "reviewed Process Topics")
    receipt_path = _inside(Path(receipt_path), root, "Process Topic review receipt")
    decisions_path = _inside(Path(decisions_path), root, "Process Topic decisions")
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    decisions = json.loads(decisions_path.read_text(encoding="utf-8"))
    if (contract.get("artifact_type") != "seminartext.project_knowledge_input"
            or receipt.get("artifact_type") != "integra.process_reviewed_topics"
            or receipt.get("authority") != PROCESS_TOPIC_AUTHORITY
            or receipt.get("automatic_acceptance") is not False
            or receipt.get("source_id") != source_id):
        raise ValueError("persisted Process Topic review has an invalid authority")
    if receipt.get("reviewed_topics_contract", {}).get("sha256") != _sha256(contract_path):
        raise ValueError("persisted reviewed Topics changed")
    if receipt.get("review_decisions", {}).get("sha256") != _sha256(decisions_path):
        raise ValueError("persisted Process Topic decisions changed")
    package_sha256 = receipt.get("review_package_sha256")
    if (not isinstance(package_sha256, str) or re.fullmatch(r"[0-9a-f]{64}", package_sha256) is None
            or decisions.get("review_package_sha256") != package_sha256):
        raise ValueError("persisted Process Topic review package is invalid")
    result_path = _inside(contract_path.parent / "result.json", root, "Process Topic review result")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    if (result.get("status") != "PROCESS_REVIEWED_TOPICS_CREATED"
            or result.get("authority") != PROCESS_TOPIC_AUTHORITY
            or result.get("package_sha256") != package_sha256
            or result.get("reviewed_topics_contract_sha256") != _sha256(contract_path)
            or result.get("process_topic_review_receipt_sha256") != _sha256(receipt_path)
            or result.get("decisions_sha256") != _sha256(decisions_path)):
        raise ValueError("persisted Process Topic review result changed")
    topics = contract.get("topics")
    if not isinstance(topics, list) or not topics:
        raise ValueError("persisted Process Topic review has no Topics")
    presented = []
    for topic in topics:
        scope = topic.get("temporal_scope") if isinstance(topic, dict) else None
        if (not isinstance(topic.get("id"), str) or not isinstance(topic.get("title"), str)
                or not isinstance(topic.get("summary"), str) or not isinstance(scope, dict)
                or not isinstance(scope.get("start_seconds"), (int, float))
                or not isinstance(scope.get("end_seconds"), (int, float))):
            raise ValueError("persisted Process Topic review has an invalid Topic")
        presented.append({"id": topic["id"], "title": topic["title"], "summary": topic["summary"],
                          "start_seconds": scope["start_seconds"], "end_seconds": scope["end_seconds"]})
    return {"status": "PROCESS_TOPIC_REVIEWED", "authority": PROCESS_TOPIC_AUTHORITY,
            "automatic_acceptance": False, "read_only": True, "package_sha256": package_sha256,
            "topics": presented, "actions": receipt.get("topic_actions", {})}
