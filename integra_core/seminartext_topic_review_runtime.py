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


RUNTIME_FILES = {
    "seminartext_modules/human_review_workflow.py": "7187819a19360fe023c9ddcc3a723ca638a1b1b74769c02c41829cd344da72dc",
    "seminartext_modules/project_knowledge_bridge.py": "39bc3191cbfa07e32b9a2526ede428289fd020e93f9bd13539321ebb39165a5f",
    "schemas/validate_canonical_knowledge_v1.py": "14869b0d77bed839758afb0455cffcfcba4173495554eddd9159a02309f1c095",
    "schemas/canonical_knowledge_v1.schema.json": "33691770411b4e5fc4e923920619396f7281bcd655202f8f56ddba99b844111b",
    "schemas/canonical_knowledge_lifecycle_v1.json": "c9133fe6ff630dd44475f40d37d731f407ce2f79d1d15613454a1d5c179099bc",
    "schemas/topic_review_workflow_v1.schema.json": "c4ad9201ee217d5d311397cea6daef8d6e6bc75c88e9c7d3ec0d129190bacec1",
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
    return {"status": "REVIEW_REQUIRED", "automatic_acceptance": False,
            "package_path": str(package_path), "package_sha256": _sha256(package_path),
            "topics": [{"id": item["id"], "title": item["proposed_title"],
                        "summary": item["proposed_summary"], "quote": item["quote"],
                        "start_seconds": item["locator"]["start_seconds"],
                        "end_seconds": item["locator"]["end_seconds"]} for item in package["topics"]]}


def _check_segment_ranges(package, evidence):
    """Reject the pinned compiler's unsupported bounds before requesting a decision."""
    words = {item["id"]: item for item in evidence["words"]}
    for topic in package["topics"]:
        first = words[topic["word_start_id"]]["sequence"]
        last = words[topic["word_end_id"]]["sequence"]
        segments = sorted((item for item in evidence["benchmark_segments"]
            if item["transcript_revision_id"] == topic["transcript_revision_id"]
            and words[item["word_start_id"]]["sequence"] >= first
            and words[item["word_end_id"]]["sequence"] <= last), key=lambda item: item["sequence"])
        if not segments or segments[0]["word_start_id"] != topic["word_start_id"] or segments[-1]["word_end_id"] != topic["word_end_id"]:
            raise ValueError(f"Topic '{topic['proposed_title']}' word range {first}–{last} is not supported by the pinned Knowledge compiler: complete BenchmarkSegments required; no boundaries were changed")


def prepare_topic_review(project_dir, *, source_id, canonical_evidence_path, topics_path):
    runtime = preflight()["runtime"]
    root = Path(project_dir).resolve(strict=True)
    evidence = _inside(Path(canonical_evidence_path), root, "Canonical Evidence")
    topics = _inside(Path(topics_path), root, "topic drafts")
    with _locked(root, source_id) as directory:
        binding = {"source_id": source_id, "evidence_path": str(evidence), "evidence_sha256": _sha256(evidence),
                   "topics_path": str(topics), "topics_sha256": _sha256(topics)}
        drafts = prepare_topic_review_input(root, source_id=source_id,
                                           canonical_evidence_path=str(evidence), topics_path=str(topics))
        with tempfile.TemporaryDirectory(prefix=".prepare-", dir=directory) as temporary:
            stage = Path(temporary)
            component = stage / "project"
            (component / "evidence").mkdir(parents=True)
            shutil.copyfile(evidence, component / "evidence/canonical_bundle.json")
            if _sha256(component / "evidence/canonical_bundle.json") != binding["evidence_sha256"]:
                raise ValueError("Canonical Evidence changed during preparation")
            _invoke(runtime, REVIEW_TOOL, "prepare", component, "--drafts", drafts["topic_drafts_path"], "--output", stage / "review")
            package_path = stage / "review/review_package.json"
            _check_segment_ranges(json.loads(package_path.read_text()), json.loads((component / "evidence/canonical_bundle.json").read_text()))
            if _sha256(topics) != binding["topics_sha256"] or _sha256(evidence) != binding["evidence_sha256"]:
                raise ValueError("review inputs changed during preparation")
            digest = _sha256(package_path)
            target = directory / digest
            binding["package_sha256"] = digest
            _write(stage / "binding.json", binding)
            if target.exists():
                prior = _inside(target / "review/review_package.json", root, "review package")
                if _sha256(prior) != digest or json.loads((target / "binding.json").read_text()) != binding:
                    raise ValueError("topic review package collision")
            else:
                os.rename(stage, target)
                # TemporaryDirectory cleanup is harmless after atomic promotion.
            return _presentation(target / "review/review_package.json")


def _choices(package, reviewer_id, decisions):
    if not isinstance(reviewer_id, str) or re.fullmatch(r"[a-z][a-z0-9._:-]{2,127}", reviewer_id) is None:
        raise ValueError("reviewer identifier must be a stable lowercase identifier")
    if not isinstance(decisions, list) or not decisions:
        raise ValueError("explicit accept/reject decisions are required")
    by_id = {item["id"]: item for item in package["topics"]}
    choices = {}
    for item in decisions:
        if not isinstance(item, dict) or set(item) != {"topic_id", "action", "reason"}:
            raise ValueError("each decision requires topic_id, action and reason")
        topic_id = item["topic_id"]
        if not isinstance(topic_id, str) or topic_id not in by_id or topic_id in choices:
            raise ValueError("unknown or duplicate topic decision")
        if item["action"] not in ("ACCEPT", "REJECT") or not isinstance(item["reason"], str) or not item["reason"].strip():
            raise ValueError("an explicit ACCEPT/REJECT action and reason are required")
        choices[topic_id] = dict(item)
    if set(choices) != set(by_id):
        raise ValueError("every topic requires an explicit decision")
    return [choices[key] for key in sorted(choices)]


def apply_topic_review(project_dir, *, source_id, expected_package_sha256, reviewer_id, decisions):
    runtime = preflight()["runtime"]
    root = Path(project_dir).resolve(strict=True)
    if not isinstance(expected_package_sha256, str) or re.fullmatch(r"[0-9a-f]{64}", expected_package_sha256) is None:
        raise ValueError("the displayed review package hash is required")
    with _locked(root, source_id) as directory:
        package_dir = directory / expected_package_sha256
        package_path = _inside(package_dir / "review/review_package.json", root, "review package")
        if _sha256(package_path) != expected_package_sha256:
            raise ValueError("review package changed")
        binding = json.loads(_inside(package_dir / "binding.json", root, "review binding").read_text())
        if binding["source_id"] != source_id or binding["package_sha256"] != expected_package_sha256:
            raise ValueError("review package belongs to another source")
        for name in ("evidence", "topics"):
            current = _inside(Path(binding[name + "_path"]), root, name)
            if _sha256(current) != binding[name + "_sha256"]:
                raise ValueError(f"{name} changed after review preparation")
        package = json.loads(package_path.read_text())
        choices = _choices(package, reviewer_id, decisions)
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
