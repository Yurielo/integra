#!/usr/bin/env python3
"""Fail-closed CURRENT/PROPOSED baseline checks for the Lite transition.

This is deliberately a repository governance helper, not a release or human
acceptance authority.  A technically valid proposal is *always* awaiting an
explicit owner reference before the promotion helper can write a next CURRENT
record.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any


SHA256 = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
CANDIDATE = re.compile(r"^candidate-v1-([0-9a-f]{64})$")
CURRENT_FIELDS = {
    "schema_version", "artifact_type", "current_id", "records",
}
CURRENT_RECORD_FIELDS = {
    "baseline_id", "status", "repository", "main", "candidate", "acceptance", "promotion", "promotion_policy", "historical_predecessors", "governed_files",
}
PROPOSAL_FIELDS = {
    "schema_version", "artifact_type", "proposal_id", "status", "base_current_id", "base_main", "proposed_source", "proposed_head", "intended_scope",
    "candidate", "delta", "gates", "evidence", "owner_acceptance", "allowed_overlay_paths",
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _is_sha(value: object) -> bool:
    return isinstance(value, str) and bool(SHA256.fullmatch(value))


def _is_git_sha(value: object) -> bool:
    return isinstance(value, str) and bool(GIT_SHA.fullmatch(value))


def _governed_product_path(path: str) -> bool:
    """The v2 scope is executable primary-journey code, not docs/governance."""
    return (
        path.startswith(("integra_core/", "macos/", "workers/"))
        or path in {"scripts/build_macos_app.sh", "scripts/candidate_manifest.py", "schemas/candidate_manifest_v1.schema.json"}
    )


def _candidate_errors(candidate: object, label: str, *, require_manifest_digest: bool = False) -> list[str]:
    required = {"candidate_id", "identity_sha256", "bundle_digest"}
    if require_manifest_digest:
        required.add("manifest_digest")
    if not isinstance(candidate, dict) or set(candidate) != required:
        return [f"{label} candidate fields are invalid"]
    candidate_id = candidate.get("candidate_id")
    identity = candidate.get("identity_sha256")
    if not isinstance(candidate_id, str) or not CANDIDATE.fullmatch(candidate_id):
        return [f"{label} candidate ID is invalid"]
    if candidate_id != f"candidate-v1-{identity}":
        return [f"{label} candidate ID is not bound to identity hash"]
    if not _is_sha(identity) or not _is_sha(candidate.get("bundle_digest")) or (require_manifest_digest and not _is_sha(candidate.get("manifest_digest"))):
        return [f"{label} candidate digests are invalid"]
    return []


def current_record(current: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(current, dict) or not isinstance(current.get("records"), list):
        return None
    matches = [item for item in current["records"] if isinstance(item, dict) and item.get("baseline_id") == current.get("current_id")]
    return matches[0] if len(matches) == 1 else None


def validate_current(current: object, root: Path) -> list[str]:
    """Validate the immutable-in-record CURRENT v2 bytes at this checkout."""
    if not isinstance(current, dict) or set(current) != CURRENT_FIELDS:
        return ["CURRENT v2 fields are invalid"]
    errors: list[str] = []
    if current.get("schema_version") != "2.0" or current.get("artifact_type") != "integra.current_product_baseline":
        errors.append("CURRENT v2 schema or artifact type is invalid")
    records = current.get("records")
    if not isinstance(records, list) or not records:
        return errors + ["CURRENT v2 records are missing"]
    if len({item.get("baseline_id") for item in records if isinstance(item, dict)}) != len(records):
        errors.append("CURRENT v2 baseline IDs must be unique")
    record = current_record(current)
    if record is None:
        return errors + ["CURRENT v2 current_id does not select exactly one record"]
    if set(record) != CURRENT_RECORD_FIELDS or record.get("status") != "CURRENT":
        return errors + ["CURRENT v2 active record is invalid"]
    if record.get("repository") != "Yurielo/integra":
        errors.append("CURRENT v2 repository identity is invalid")
    if record.get("promotion_policy") != "EXPLICIT_HUMAN_OWNER_AUTHORIZATION_REQUIRED":
        errors.append("CURRENT v2 promotion policy does not require explicit human owner authorization")
    main = record.get("main")
    if not isinstance(main, dict) or set(main) != {"commit_sha", "tree_sha"} or not _is_git_sha(main.get("commit_sha")) or not _is_git_sha(main.get("tree_sha")):
        errors.append("CURRENT v2 main identity is invalid")
    errors.extend(_candidate_errors(record.get("candidate"), "CURRENT v2"))
    acceptance = record.get("acceptance")
    if not isinstance(acceptance, dict) or set(acceptance) != {"authority_ref", "scope", "decision"}:
        errors.append("CURRENT v2 acceptance binding is invalid")
    elif acceptance.get("decision") != "USER_ACCEPTED" or not all(isinstance(acceptance.get(key), str) and acceptance[key] for key in ("authority_ref", "scope")):
        errors.append("CURRENT v2 acceptance is not an explicit scoped owner decision")
    promotion = record.get("promotion")
    if not isinstance(promotion, dict) or set(promotion) != {"issue_159_ref", "pull_160_ref", "accepted_report_head"} or not all(isinstance(promotion.get(key), str) and promotion[key] for key in ("issue_159_ref", "pull_160_ref", "accepted_report_head")):
        errors.append("CURRENT v2 promotion correspondence is invalid")
    predecessors = record.get("historical_predecessors")
    if not isinstance(predecessors, list) or not predecessors:
        errors.append("CURRENT v2 historical predecessor references are required")
    else:
        for item in predecessors:
            if not isinstance(item, dict) or set(item) != {"path", "sha256"} or not isinstance(item.get("path"), str) or not _is_sha(item.get("sha256")):
                errors.append("CURRENT v2 historical predecessor is invalid")
                continue
            path = root / item["path"]
            if not path.is_file() or sha256_file(path) != item["sha256"]:
                errors.append(f"CURRENT v2 historical predecessor differs: {item['path']}")
    files = record.get("governed_files")
    if not isinstance(files, list) or not files:
        return errors + ["CURRENT v2 governed file inventory is required"]
    seen: set[str] = set()
    for item in files:
        if not isinstance(item, dict) or set(item) != {"path", "sha256"} or not isinstance(item.get("path"), str) or not _is_sha(item.get("sha256")):
            errors.append("CURRENT v2 governed file record is invalid")
            continue
        path_text = item["path"]
        if path_text in seen or path_text.startswith("/") or ".." in Path(path_text).parts:
            errors.append("CURRENT v2 governed file path is invalid")
            continue
        seen.add(path_text)
        path = root / path_text
        if not path.is_file() or sha256_file(path) != item["sha256"]:
            errors.append(f"CURRENT v2 governed byte drift: {path_text}")
    # The exact inventory catches changes to existing files; this Git-aware
    # check also makes an added executable primary-journey path fail closed.
    # Tiny copied fixture roots intentionally have no Git metadata, so tests of
    # byte validation remain possible without weakening repository validation.
    if isinstance(main, dict) and _is_git_sha(main.get("commit_sha")):
        try:
            changed = subprocess.run(
                ["git", "-C", str(root), "diff", "--name-only", main["commit_sha"], "HEAD"],
                check=True, capture_output=True, text=True,
            ).stdout.splitlines()
        except (OSError, subprocess.CalledProcessError):
            changed = []
        for path_text in changed:
            if _governed_product_path(path_text) and path_text not in seen:
                errors.append(f"CURRENT v2 unaccounted governed path: {path_text}")
    return errors


def validate_proposal(proposal: object, current: dict[str, Any], root: Path) -> list[str]:
    """Validate a strict proposal.  It never returns a promotion decision."""
    if not isinstance(proposal, dict) or set(proposal) != PROPOSAL_FIELDS:
        return ["PROPOSED baseline fields are invalid"]
    errors: list[str] = []
    if proposal.get("schema_version") != "1.0" or proposal.get("artifact_type") != "integra.proposed_product_baseline" or not isinstance(proposal.get("proposal_id"), str) or not proposal["proposal_id"]:
        errors.append("PROPOSED baseline schema or artifact type is invalid")
    if proposal.get("status") != "PROPOSED_BASELINE_VALID":
        errors.append("PROPOSED baseline status must be PROPOSED_BASELINE_VALID")
    active = current_record(current)
    if active is None or proposal.get("base_current_id") != active.get("baseline_id"):
        errors.append("PROPOSED baseline does not bind CURRENT")
    if proposal.get("base_main") != (active or {}).get("main"):
        errors.append("PROPOSED baseline base main differs from CURRENT")
    source = proposal.get("proposed_source")
    if not isinstance(source, dict) or set(source) != {"commit_sha", "tree_sha"} or not _is_git_sha(source.get("commit_sha")) or not _is_git_sha(source.get("tree_sha")):
        errors.append("PROPOSED baseline source identity is invalid")
    head = proposal.get("proposed_head")
    if not isinstance(head, dict) or set(head) != {"commit_sha", "tree_sha"} or not _is_git_sha(head.get("commit_sha")) or not _is_git_sha(head.get("tree_sha")) or head != source:
        errors.append("PROPOSED baseline exact HEAD/tree does not match source")
    intended_scope = proposal.get("intended_scope")
    if not isinstance(intended_scope, dict) or set(intended_scope) != {"wp", "journey"} or not all(isinstance(intended_scope.get(key), str) and intended_scope[key] for key in ("wp", "journey")):
        errors.append("PROPOSED baseline intended WP/journey scope is invalid")
    errors.extend(_candidate_errors(proposal.get("candidate"), "PROPOSED baseline", require_manifest_digest=True))
    delta = proposal.get("delta")
    if not isinstance(delta, list) or not delta:
        errors.append("PROPOSED baseline exact delta is required")
    else:
        paths: set[str] = set()
        for item in delta:
            if not isinstance(item, dict) or set(item) != {"path", "before_sha256", "after_sha256"} or not isinstance(item.get("path"), str) or not _is_sha(item.get("before_sha256")) or not _is_sha(item.get("after_sha256")):
                errors.append("PROPOSED baseline delta record is invalid")
                continue
            if item["path"] in paths:
                errors.append("PROPOSED baseline delta paths must be unique")
            paths.add(item["path"])
    gates = proposal.get("gates")
    if not isinstance(gates, list) or not gates or any(not isinstance(item, dict) or set(item) != {"name", "result", "evidence_ref"} or item.get("result") != "PASS" or not isinstance(item.get("evidence_ref"), str) or not item["evidence_ref"] for item in gates):
        errors.append("PROPOSED baseline mandatory gates are not all PASS with evidence")
    evidence = proposal.get("evidence")
    if not isinstance(evidence, dict) or set(evidence) != {"candidate_manifest", "candidate_evidence", "report"}:
        errors.append("PROPOSED baseline candidate-bound evidence is invalid")
    elif any(not isinstance(value, dict) or set(value) != {"path", "sha256"} or not isinstance(value.get("path"), str) or not value["path"] or not _is_sha(value.get("sha256")) for value in evidence.values()):
        errors.append("PROPOSED baseline candidate-bound evidence is invalid")
    # A proposal can never carry an inferred decision.  The empty field is the
    # only valid pre-promotion state.
    if proposal.get("owner_acceptance") is not None:
        errors.append("PROPOSED baseline must await a separate explicit owner acceptance reference")
    overlays = proposal.get("allowed_overlay_paths")
    if not isinstance(overlays, list) or not overlays or len(overlays) != len(set(overlays)) or any(not isinstance(item, str) or item.startswith("/") or ".." in Path(item).parts for item in overlays):
        errors.append("PROPOSED baseline overlay paths are invalid")
    return errors


def proposal_state(proposal: object, current: dict[str, Any], root: Path) -> tuple[str, list[str]]:
    errors = validate_proposal(proposal, current, root)
    return ("PROPOSED_BASELINE_VALID / AWAITING_OWNER_ACCEPTANCE", []) if not errors else ("FAIL", errors)


def verify_promotion_material(proposal: dict[str, Any], root: Path) -> list[str]:
    """Verify the exact source, candidate manifest/bundle and named evidence.

    This deliberately has no authority side effect.  It is used by the helper
    after structural proposal validation, not by a green test as a substitute
    for the owner reference.
    """
    errors: list[str] = []
    try:
        commit = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
        tree = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD^{tree}"], check=True, capture_output=True, text=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ["promotion source Git identity is unavailable"]
    if proposal["proposed_source"] != {"commit_sha": commit, "tree_sha": tree}:
        errors.append("promotion source HEAD/tree differs from PROPOSED baseline")
    base_commit = proposal["base_main"]["commit_sha"]
    declared = {item["path"]: item for item in proposal["delta"]}
    try:
        changed = subprocess.run(["git", "-C", str(root), "diff", "--name-only", base_commit, commit], check=True, capture_output=True, text=True).stdout.splitlines()
    except (OSError, subprocess.CalledProcessError):
        errors.append("promotion cannot compare PROPOSED delta to CURRENT base")
        changed = []
    for path_text in changed:
        if _governed_product_path(path_text) and path_text not in declared:
            errors.append(f"promotion has undeclared governed delta: {path_text}")
    for path_text, item in declared.items():
        try:
            before = subprocess.run(["git", "-C", str(root), "show", f"{base_commit}:{path_text}"], check=True, capture_output=True).stdout
            after = subprocess.run(["git", "-C", str(root), "show", f"{commit}:{path_text}"], check=True, capture_output=True).stdout
        except (OSError, subprocess.CalledProcessError):
            errors.append(f"promotion declared delta is unavailable: {path_text}")
            continue
        if hashlib.sha256(before).hexdigest() != item["before_sha256"] or hashlib.sha256(after).hexdigest() != item["after_sha256"]:
            errors.append(f"promotion declared delta differs: {path_text}")
    evidence = proposal["evidence"]
    def read_record(label: str) -> dict[str, Any] | None:
        path = root / evidence[label]["path"]
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            errors.append(f"promotion {label} is unavailable or invalid")
            return None
        return value if isinstance(value, dict) else None
    manifest = read_record("candidate_manifest")
    candidate_evidence = read_record("candidate_evidence")
    if manifest is not None:
        bundle = manifest.get("bundle")
        manifest_path = root / evidence["candidate_manifest"]["path"]
        if sha256_file(manifest_path) != evidence["candidate_manifest"]["sha256"] or sha256_file(manifest_path) != proposal["candidate"]["manifest_digest"] or manifest.get("candidate_id") != proposal["candidate"]["candidate_id"] or manifest.get("identity_sha256") != proposal["candidate"]["identity_sha256"] or not isinstance(bundle, dict) or bundle.get("digest") != proposal["candidate"]["bundle_digest"]:
            errors.append("promotion candidate manifest does not bind PROPOSED candidate/bundle")
    if candidate_evidence is not None and (sha256_file(root / evidence["candidate_evidence"]["path"]) != evidence["candidate_evidence"]["sha256"] or candidate_evidence.get("candidate_id") != proposal["candidate"]["candidate_id"] or candidate_evidence.get("manifest_identity_sha256") != proposal["candidate"]["identity_sha256"] or candidate_evidence.get("bundle_digest") != proposal["candidate"]["bundle_digest"]):
        errors.append("promotion candidate evidence does not bind PROPOSED candidate/bundle")
    for gate in proposal["gates"]:
        if not (root / gate["evidence_ref"]).is_file():
            errors.append(f"promotion gate evidence is unavailable: {gate['name']}")
    report_path = root / evidence["report"]["path"]
    if not report_path.is_file() or sha256_file(report_path) != evidence["report"]["sha256"]:
        errors.append("promotion report reference is unavailable")
    return errors


def next_current(current: dict[str, Any], proposal: dict[str, Any], owner_acceptance_ref: str, *, previous_current_path: str) -> dict[str, Any]:
    """Construct, but do not write, the next CURRENT record after explicit owner input."""
    if not isinstance(owner_acceptance_ref, str) or not owner_acceptance_ref.strip():
        raise ValueError("explicit owner acceptance reference is required")
    if not isinstance(previous_current_path, str) or not previous_current_path or previous_current_path.startswith("/") or ".." in Path(previous_current_path).parts:
        raise ValueError("repository-relative previous CURRENT history path is required")
    record = current_record(current)
    if record is None:
        raise ValueError("CURRENT record is invalid")
    new_id = "current-v2-" + proposal["candidate"]["identity_sha256"]
    new_record = {
        "baseline_id": new_id,
        "status": "CURRENT",
        "repository": record["repository"],
        "main": proposal["proposed_head"],
        "candidate": {key: proposal["candidate"][key] for key in ("candidate_id", "identity_sha256", "bundle_digest")},
        "acceptance": {"authority_ref": owner_acceptance_ref, "scope": "owner-authorized proposed baseline promotion", "decision": "USER_ACCEPTED"},
        "promotion_policy": "EXPLICIT_HUMAN_OWNER_AUTHORIZATION_REQUIRED",
        "promotion": {"issue_159_ref": "superseded-by-next-owner-promotion", "pull_160_ref": "superseded-by-next-owner-promotion", "accepted_report_head": proposal["proposed_head"]["commit_sha"]},
        "historical_predecessors": [{"path": previous_current_path, "sha256": hashlib.sha256(json.dumps(current, sort_keys=True, separators=(",", ":")).encode()).hexdigest()}],
        "governed_files": [{"path": item["path"], "sha256": item["after_sha256"]} for item in proposal["delta"]],
    }
    result = json.loads(json.dumps(current))
    result["records"].append(new_record)
    result["current_id"] = new_id
    return result
