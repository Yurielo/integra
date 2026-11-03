"""Bounded bridge to the packaged SeminarText semantic-review provider.

Integra owns the local presentation and durable workflow location.  SeminarText
continues to validate evidence, decisions and canonical results.  This module
does not parse or recreate provider-private workflow snapshots.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from datetime import datetime, timezone


ROLE_FILENAMES = {
    "evidence": "evidence.json", "fragments": "fragments.json", "proposals": "proposals.json",
    "source": "source.bin", "notebook": "notebook.json", "producer_runtime": "producer-runtime.bin",
}
_DIGEST = re.compile(r"^[0-9a-f]{64}$")


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _inside(path: Path, parent: Path) -> Path:
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise ValueError("review package has a missing or unsafe required file") from error
    try:
        resolved.relative_to(parent.resolve(strict=True))
    except ValueError as error:
        raise ValueError("review package escapes its selected folder") from error
    return resolved


def _regular(path: Path) -> Path:
    _require(not path.is_symlink() and path.is_file(), "review package has a missing or unsafe required file")
    return path.resolve(strict=True)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _provider_root(resources: Path) -> Path:
    root = resources / "runtime" / "seminartext-semantic"
    manifest = root / "runtime.json"
    _require(root.is_dir() and not root.is_symlink() and manifest.is_file() and not manifest.is_symlink(),
             "semantic review component is unavailable in this Integra build")
    value = json.loads(manifest.read_text(encoding="utf-8"))
    _require(value.get("component") == "seminartext.semantic_workflow" and value.get("schema_version") == "1.0.0",
             "semantic review component identity is unsupported")
    files = value.get("files")
    _require(isinstance(files, dict) and files, "semantic review component manifest is incomplete")
    for relative, expected in files.items():
        _require(isinstance(relative, str) and isinstance(expected, str) and _DIGEST.fullmatch(expected),
                 "semantic review component manifest is invalid")
        candidate = root / relative
        _inside(candidate, root)
        _require(_regular(candidate) and _sha256(candidate) == expected,
                 "semantic review component bytes do not match this build")
    return root


def _package(package_dir: str) -> tuple[Path, dict[str, Path], str]:
    root = Path(package_dir).expanduser()
    _require(root.is_absolute(), "select a local prepared review package folder")
    _require(root.is_dir() and not root.is_symlink(), "selected review package folder is unavailable")
    root = root.resolve(strict=True)
    files = {role: _regular(_inside(root / filename, root)) for role, filename in ROLE_FILENAMES.items()}
    identity = hashlib.sha256(json.dumps({role: {"path": str(path), "sha256": _sha256(path)}
                                          for role, path in sorted(files.items())}, sort_keys=True).encode()).hexdigest()
    return root, files, identity


def _workflow(root: Path, package_id: str) -> Path:
    target = root / "semantic-reviews" / package_id
    target.parent.mkdir(parents=True, exist_ok=True)
    _require(not target.parent.is_symlink(), "semantic review storage is unsafe")
    if target.exists():
        _require(target.is_dir() and not target.is_symlink(), "semantic review storage is unsafe")
    else:
        target.mkdir()
    return target


def _atomic_json(path: Path, value: dict) -> None:
    """Persist an Integra transport receipt without making a second review ledger."""
    _require(not path.is_symlink(), "semantic review storage is unsafe")
    temporary = path.with_name("." + path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    os.replace(temporary, path)


def _remember_package(workflow: Path, package_dir: Path, package_id: str) -> None:
    # This is deliberately only a picker/reopen convenience.  Decisions and
    # canonical state remain in the SeminarText provider workflow.
    _atomic_json(workflow / "integra-package.json", {
        "schema_version": "1.0.0", "artifact_type": "integra.semantic_review_package_binding",
        "package_id": package_id, "package_dir": str(package_dir), "display_name": package_dir.name,
    })


def recent_reviews(resources: Path, data_root: Path) -> list[dict]:
    """Return reopenable packages, verifying each against the provider first."""
    parent = data_root / "semantic-reviews"
    if not parent.exists():
        return []
    _require(parent.is_dir() and not parent.is_symlink(), "semantic review storage is unsafe")
    result = []
    for workflow in sorted(parent.iterdir()):
        index = workflow / "integra-package.json"
        if workflow.is_symlink() or not workflow.is_dir() or index.is_symlink() or not index.is_file():
            continue
        try:
            record = json.loads(index.read_text(encoding="utf-8"))
            package_dir = record["package_dir"]
            current = review_projection(resources, data_root, package_dir=package_dir)
            projection = current["projection"]
            result.append({"package_id": current["package_id"],
                           "display_name": str(record.get("display_name") or Path(package_dir).name),
                           "package_dir": package_dir,
                           "status": projection["workflow"]["status"],
                           "pending_count": len(projection["workflow"]["pending"]),
                           "deferred_count": len(projection["workflow"]["deferred"])})
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue
    return result


def _run(resources: Path, command: str, arguments: list[str]) -> dict:
    provider = _provider_root(resources)
    executable = provider / "seminartext_modules" / "semantic_workflow.py"
    _require(executable.is_file() and not executable.is_symlink(), "semantic workflow executable is unavailable")
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONPATH"] = os.pathsep.join((str(provider), str(resources / "runtime" / "review-python" / "site-packages")))
    completed = subprocess.run([sys.executable, str(executable), command, *arguments],
                               env=environment, capture_output=True, text=True, timeout=90)
    if completed.returncode:
        try:
            message = json.loads(completed.stderr).get("error")
        except (ValueError, AttributeError):
            message = None
        raise ValueError(str(message or "semantic review provider did not accept this request"))
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise ValueError("semantic review provider returned an invalid response") from error


def open_review(resources: Path, data_root: Path, *, package_dir: str) -> dict:
    selected, files, package_id = _package(package_dir)
    workflow = _workflow(data_root, package_id)
    arguments = [str(workflow)]
    for role in ROLE_FILENAMES:
        arguments.extend(("--" + role.replace("_", "-"), str(files[role])))
    _run(resources, "prepare", arguments)
    _remember_package(workflow, selected, package_id)
    return {"package_id": package_id, "projection": _run(resources, "projection", [str(workflow)])}


def review_projection(resources: Path, data_root: Path, *, package_dir: str) -> dict:
    _, _, package_id = _package(package_dir)
    workflow = _workflow(data_root, package_id)
    _require(workflow.is_dir(), "open this prepared package before reviewing it")
    return {"package_id": package_id, "projection": _run(resources, "projection", [str(workflow)])}


def submit_review(resources: Path, data_root: Path, *, package_dir: str, reviewer_id: str, decisions: list[dict]) -> dict:
    _require(isinstance(reviewer_id, str) and 1 <= len(reviewer_id.strip()) <= 120,
             "enter your name before saving decisions")
    current = review_projection(resources, data_root, package_dir=package_dir)
    projection = current["projection"]
    package = projection["package"]
    _require(isinstance(decisions, list) and decisions, "choose at least one decision to save")
    known = {item["proposal_id"]: item for item in projection["proposals"]}
    payload = []
    for item in decisions:
        _require(isinstance(item, dict) and item.get("proposal_id") in known, "decision does not belong to this review")
        _require(known[item["proposal_id"]]["saved_decision"] is None,
                 "a saved decision is immutable; reopen only deferred items in the next round")
        action = item.get("action")
        reason = item.get("reason")
        edits = item.get("edited_fields")
        _require(action in {"ACCEPT", "EDIT", "REJECT", "DEFER"}, "choose how to handle every selected proposal")
        _require(isinstance(reason, str) and 1 <= len(reason.strip()) <= 1000,
                 "briefly explain the decision before saving it")
        _require((action == "EDIT") == isinstance(edits, dict) if edits is not None else action != "EDIT",
                 "use editable fields only when choosing ‘Исправить’")
        choice = {"proposal_id": item["proposal_id"], "proposal_sha256": known[item["proposal_id"]]["proposal_sha256"],
                  "action": action, "reason": reason.strip()}
        if edits is not None:
            choice["edited_fields"] = edits
        payload.append(choice)
    _require(len({item["proposal_id"] for item in payload}) == len(payload), "one decision per proposal is required")
    # A submitted transport receipt fixes its timestamp.  If the app loses the
    # response, retrying the same visible choices reuses the exact envelope.
    retry_key = hashlib.sha256(json.dumps({"package_id": package["id"], "package_sha256": package["sha256"],
                                           "reviewer": reviewer_id.strip(), "decisions": payload},
                                          ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    workflow = _workflow(data_root, current["package_id"])
    submission = workflow / ("submission-" + retry_key + ".json")
    if submission.exists():
        _require(submission.is_file() and not submission.is_symlink(), "semantic review submission receipt is unsafe")
        envelope = json.loads(submission.read_text(encoding="utf-8"))
    else:
        stamped = [{**choice, "timestamp": datetime.now(timezone.utc).isoformat()} for choice in payload]
        envelope = {"schema_version": "1.0.0", "package_id": package["id"], "package_sha256": package["sha256"],
                "reviewer": {"actor_type": "human_domain_reviewer", "actor_id": reviewer_id.strip()},
                "explicit_confirmation": True,
                "confirmed_proposal_ids": sorted(item["proposal_id"] for item in stamped), "decisions": stamped}
        _atomic_json(submission, envelope)
    _run(resources, "submit", [str(workflow), "--decisions", str(submission)])
    return review_projection(resources, data_root, package_dir=package_dir)


def apply_review(resources: Path, data_root: Path, *, package_dir: str) -> dict:
    current = review_projection(resources, data_root, package_dir=package_dir)
    _require(not current["projection"]["workflow"]["pending"],
             "choose and save a decision for every proposal before applying this round")
    workflow = _workflow(data_root, current["package_id"])
    _run(resources, "apply", [str(workflow)])
    _run(resources, "validate", [str(workflow)])
    return review_projection(resources, data_root, package_dir=package_dir)


def next_round(resources: Path, data_root: Path, *, package_dir: str) -> dict:
    current = review_projection(resources, data_root, package_dir=package_dir)
    workflow = _workflow(data_root, current["package_id"])
    _run(resources, "next-round", [str(workflow)])
    return review_projection(resources, data_root, package_dir=package_dir)
