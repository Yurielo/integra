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
    "candidate", "delta", "historical_test_successors", "gates", "evidence", "owner_acceptance", "allowed_overlay_paths",
}
HISTORICAL_TEST_AUTHORITIES = {
    "R12": "state/native_macos_app_v1.json",
    "R13": "state/ready_app_v1.json",
}
PILOT_ACCEPTANCE_FIELDS = {
    "decision", "authority_ref", "scope", "promotion_authorized",
}
CANONICAL_PROTECTION_SYNC_PATHS = {
    "docs/evidence/ISSUE_227_PROPOSAL_PROTECTION_BINDING.md",
    "scripts/candidate_protection_audit.py",
    "scripts/proposed_baseline_lite.py",
    "state/candidate_protection_registry_v1.json",
    "tests/test_candidate_protection_audit.py",
    "tests/test_proposed_baseline_lite.py",
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
        or path in {
            "scripts/build_macos_app.sh", "scripts/candidate_manifest.py",
            "schemas/candidate_manifest_v1.schema.json", "scripts/test_macos_app.sh",
            "tests/test_macos_app.py",
        }
    )


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def _commit_identity(root: Path, commit: str) -> dict[str, str]:
    if not _is_git_sha(commit) or _git(root, "cat-file", "-t", commit) != "commit":
        raise ValueError("Git identity is not an exact commit")
    return {"commit_sha": _git(root, "rev-parse", commit),
            "tree_sha": _git(root, "rev-parse", f"{commit}^{{tree}}")}


def _changed_paths(root: Path, left: str, right: str) -> list[str]:
    result = subprocess.run(["git", "-C", str(root), "diff", "--no-renames", "--name-only", "-z", left, right],
                            check=True, capture_output=True).stdout
    return [item.decode("utf-8") for item in result.split(b"\0") if item]


def _proposal_declaration_commit(root: Path, overlay_sha: str, proposal: dict,
                                 relative_proposal: str) -> tuple[str | None, list[str]]:
    """Find the one-file declaration and allow only a narrow main sync after it.

    This keeps the immutable declaration anchored directly to its evidence
    overlay while allowing the open PR to incorporate the canonical protection
    fix that was needed to protect that very Proposal. Arbitrary branch changes
    after declaration remain forbidden.
    """
    errors: list[str] = []
    try:
        revisions = _git(root, "rev-list", "--first-parent", "--reverse",
                         f"{overlay_sha}..HEAD").splitlines()
    except (OSError, subprocess.CalledProcessError):
        return None, ["promotion proposal declaration history is unavailable"]
    declaration = None
    for revision in revisions:
        try:
            paths = _changed_paths(root, f"{revision}^", revision)
        except (OSError, subprocess.CalledProcessError):
            return None, ["promotion proposal declaration history is unavailable"]
        if relative_proposal not in paths:
            continue
        try:
            value = json.loads(_git(root, "show", f"{revision}:{relative_proposal}"))
        except (OSError, subprocess.CalledProcessError, ValueError, TypeError):
            errors.append("promotion proposal declaration content is unavailable")
            continue
        if value != proposal:
            errors.append("promotion proposal changed after its evidence overlay")
        elif declaration is not None:
            errors.append("promotion proposal has multiple declaration commits")
        else:
            declaration = revision
    if declaration is None:
        errors.append("promotion proposal declaration history is unavailable")
        return None, errors
    try:
        parent = _git(root, "rev-parse", f"{declaration}^")
    except (OSError, subprocess.CalledProcessError):
        return declaration, errors + ["promotion proposal declaration parent is unavailable"]
    if parent != overlay_sha:
        errors.append("promotion proposal declaration is not directly atop evidence overlay")
    if _changed_paths(root, parent, declaration) != [relative_proposal]:
        errors.append("promotion declaration overlay must contain only the PROPOSED record")

    tail = revisions[revisions.index(declaration) + 1:]
    if tail:
        if len(tail) != 1:
            errors.append("promotion proposal has noncanonical changes after declaration")
            return declaration, errors
        merge = tail[0]
        try:
            parents = _git(root, "rev-list", "--parents", "-n", "1", merge).split()
        except (OSError, subprocess.CalledProcessError):
            errors.append("promotion post-declaration change is not an exact canonical protection sync")
            return declaration, errors
        if len(parents) != 3 or parents[1] != declaration:
            errors.append("promotion proposal has noncanonical changes after declaration")
            return declaration, errors
        try:
            main = _git(root, "rev-parse", "--verify", "refs/remotes/origin/main")
            paths = _changed_paths(root, parents[1], merge)
            proposal_blob = _git(root, "rev-parse", f"{declaration}:{relative_proposal}")
            head_blob = _git(root, "rev-parse", f"HEAD:{relative_proposal}")
        except (OSError, subprocess.CalledProcessError, IndexError):
            errors.append("promotion canonical-main synchronization identity is unavailable")
        else:
            if (parents[2] != main or not paths
                    or any(path not in CANONICAL_PROTECTION_SYNC_PATHS for path in paths)
                    or proposal_blob != head_blob):
                errors.append("promotion post-declaration change is not an exact canonical protection sync")
    return declaration, errors


def _valid_relative_path(value: object) -> bool:
    return (isinstance(value, str) and bool(value) and "\\" not in value
            and all(part not in {"", ".", ".."} for part in value.split("/"))
            and not any(ord(character) < 32 or ord(character) == 127 for character in value))


def _regular_blob_hash(root: Path, commit: str, path: str) -> str | None:
    """Return None only for an absent literal path in a verified commit tree."""
    if not _is_git_sha(commit) or not _valid_relative_path(path):
        raise ValueError("invalid commit or canonical path")
    if _git(root, "cat-file", "-t", commit) != "commit":
        raise ValueError("Git object is not a commit")
    tree = _git(root, "rev-parse", f"{commit}^{{tree}}")
    parts = path.split("/")
    for index, part in enumerate(parts):
        result = subprocess.run(["git", "--literal-pathspecs", "-C", str(root),
                                 "ls-tree", "-z", tree, "--", part],
                                check=True, capture_output=True).stdout
        if not result:
            return None
        entries = result.split(b"\0")
        if len(entries) != 2 or entries[-1] != b"":
            raise ValueError("Git tree lookup is not exact")
        header, name = entries[0].split(b"\t", 1)
        mode, kind, object_id = header.decode("ascii").split()
        if name != part.encode("utf-8") or not _is_git_sha(object_id):
            raise ValueError("Git tree entry differs from literal path")
        if index < len(parts) - 1:
            if (mode, kind) != ("040000", "tree"):
                raise ValueError("Git path ancestor is not a directory")
            tree = object_id
        else:
            if mode not in {"100644", "100755"} or kind != "blob":
                raise ValueError("Git path is not a regular blob")
            blob = subprocess.run(["git", "-C", str(root), "cat-file", "blob", object_id],
                                  check=True, capture_output=True).stdout
            return hashlib.sha256(blob).hexdigest()
    raise ValueError("empty Git path")


def _delta_errors(delta: object) -> list[str]:
    if not isinstance(delta, list) or not delta:
        return ["PROPOSED baseline exact delta is required"]
    errors: list[str] = []
    paths: set[str] = set()
    for item in delta:
        if (not isinstance(item, dict) or set(item) != {"path", "before_sha256", "after_sha256"}
                or not _valid_relative_path(item.get("path"))
                or (item["before_sha256"] is not None and not _is_sha(item["before_sha256"]))
                or not _is_sha(item["after_sha256"])):
            errors.append("PROPOSED baseline delta record is invalid")
            continue
        if item["path"] in paths:
            errors.append("PROPOSED baseline delta paths must be unique")
        paths.add(item["path"])
    return errors


def _pilot_acceptance_errors(value: object) -> list[str]:
    """Accept a durable pilot decision without treating it as promotion authority."""
    if value is None:
        return []
    if not isinstance(value, dict) or set(value) != PILOT_ACCEPTANCE_FIELDS:
        return ["PROPOSED baseline pilot acceptance is invalid"]
    if (value.get("decision") != "PILOT_ACCEPTED"
            or value.get("promotion_authorized") is not False
            or not isinstance(value.get("authority_ref"), str) or not value["authority_ref"].strip()
            or not isinstance(value.get("scope"), str) or not value["scope"].strip()):
        return ["PROPOSED baseline pilot acceptance is invalid"]
    return []


def _addition_errors(proposal: dict, current: dict, root: Path) -> list[str]:
    additions = [item for item in proposal["delta"] if item["before_sha256"] is None]
    if not additions:
        return []
    active = current_record(current)
    base = proposal.get("base_main")
    source = proposal.get("proposed_source")
    if (active is None or proposal.get("base_current_id") != active.get("baseline_id")
            or not isinstance(base, dict) or base != active.get("main")
            or not isinstance(source, dict)):
        return ["PROPOSED addition does not bind active CURRENT"]
    inventory = active.get("governed_files")
    if not isinstance(inventory, list) or not inventory or any(
        not isinstance(item, dict) or set(item) != {"path", "sha256"}
        or not _valid_relative_path(item.get("path")) or not _is_sha(item.get("sha256"))
        for item in inventory
    ):
        return ["PROPOSED addition CURRENT inventory is invalid"]
    paths = [item["path"] for item in inventory]
    if len(paths) != len(set(paths)):
        return ["PROPOSED addition CURRENT inventory is invalid"]
    errors: list[str] = []
    try:
        if (_commit_identity(root, base["commit_sha"]) != base
                or _commit_identity(root, source["commit_sha"]) != source):
            return ["PROPOSED addition Git identity differs"]
        for item in additions:
            path = item["path"]
            if path in paths or _regular_blob_hash(root, base["commit_sha"], path) is not None:
                errors.append(f"PROPOSED addition is not absent from CURRENT: {path}")
            if _regular_blob_hash(root, source["commit_sha"], path) != item["after_sha256"]:
                errors.append(f"PROPOSED addition after hash differs: {path}")
    except (OSError, subprocess.CalledProcessError, ValueError, KeyError, TypeError):
        errors.append("PROPOSED addition Git absence/blob proof is unavailable or invalid")
    return errors


def _historical_test_hash(root: Path, authority: str, path: str) -> str | None:
    """Return an immutable R12/R13 implementation hash for one exact test."""
    state_path = HISTORICAL_TEST_AUTHORITIES.get(authority)
    if state_path is None:
        return None
    try:
        payload = json.loads((root / state_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    matches = [item.get("sha256") for item in payload.get("implementation", [])
               if isinstance(item, dict) and item.get("path") == path]
    return matches[0] if len(matches) == 1 and isinstance(matches[0], str) else None


def _historical_test_paths(root: Path) -> dict[str, set[str]]:
    """Return only exact test paths named by the immutable R12/R13 records."""
    result: dict[str, set[str]] = {}
    for authority in HISTORICAL_TEST_AUTHORITIES:
        try:
            payload = json.loads((root / HISTORICAL_TEST_AUTHORITIES[authority]).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for item in payload.get("implementation", []):
            if isinstance(item, dict) and isinstance(item.get("path"), str) and item["path"].startswith("tests/"):
                result.setdefault(item["path"], set()).add(authority)
    return result


def _historical_test_successor_errors(successors: object, root: Path) -> list[str]:
    if not isinstance(successors, list):
        return ["PROPOSED historical test successors are invalid"]
    errors: list[str] = []
    seen: set[tuple[str, str]] = set()
    expected_fields = {"path", "historical_authority", "before_sha256", "after_sha256", "reason"}
    for successor in successors:
        if not isinstance(successor, dict) or set(successor) != expected_fields:
            errors.append("PROPOSED historical test successor fields are invalid")
            continue
        path = successor.get("path")
        authority = successor.get("historical_authority")
        before = successor.get("before_sha256")
        after = successor.get("after_sha256")
        reason = successor.get("reason")
        if (not _valid_relative_path(path) or not isinstance(path, str) or not path.startswith("tests/")
                or any(token in path for token in ("*", "?", "[", "]"))):
            errors.append("PROPOSED historical test successor path is not an exact test path")
            continue
        if not isinstance(authority, str) or authority not in HISTORICAL_TEST_AUTHORITIES:
            errors.append("PROPOSED historical test successor authority is invalid")
            continue
        if not _is_sha(before) or not _is_sha(after) or before == after:
            errors.append("PROPOSED historical test successor hashes are invalid")
        if not isinstance(reason, str) or not reason.strip():
            errors.append("PROPOSED historical test successor reason is invalid")
        key = (authority, path)
        if key in seen:
            errors.append("PROPOSED historical test successors must be unique")
        seen.add(key)
        historical = _historical_test_hash(root, authority, path)
        if historical is None:
            errors.append("PROPOSED historical test successor is not in immutable authority inventory")
        elif before != historical:
            errors.append("PROPOSED historical test successor before hash differs from immutable authority")
    return errors


def proposal_declares_historical_test_successor(
    proposal: dict | None, authority: str, path: str, historical_sha256: str, current_sha256: str | None,
) -> bool:
    """Recognize only one exact R12/R13 test successor under active proposal review."""
    if not isinstance(proposal, dict) or not isinstance(current_sha256, str):
        return False
    successors = proposal.get("historical_test_successors")
    if not isinstance(successors, list):
        return False
    return any(
        isinstance(item, dict)
        and item.get("historical_authority") == authority
        and item.get("path") == path
        and item.get("before_sha256") == historical_sha256
        and item.get("after_sha256") == current_sha256
        for item in successors
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


def validate_current(current: object, root: Path, proposal: dict | None = None) -> list[str]:
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
        if path_text in seen or not _valid_relative_path(path_text):
            errors.append("CURRENT v2 governed file path is invalid")
            continue
        seen.add(path_text)
        path = root / path_text
        if proposal is not None and isinstance(main, dict) and _is_git_sha(main.get("commit_sha")):
            try:
                matches = _regular_blob_hash(root, main["commit_sha"], path_text) == item["sha256"]
            except (OSError, subprocess.CalledProcessError, ValueError):
                matches = False
        else:
            matches = path.is_file() and sha256_file(path) == item["sha256"]
        if not matches:
            errors.append(f"CURRENT v2 governed byte drift: {path_text}")
    # The exact inventory catches changes to existing files; this Git-aware
    # check also makes an added executable primary-journey path fail closed.
    # Tiny copied fixture roots intentionally have no Git metadata, so tests of
    # byte validation remain possible without weakening repository validation.
    if proposal is None and isinstance(main, dict) and _is_git_sha(main.get("commit_sha")):
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
    if not isinstance(head, dict) or set(head) != {"commit_sha", "tree_sha"} or not _is_git_sha(head.get("commit_sha")) or not _is_git_sha(head.get("tree_sha")):
        errors.append("PROPOSED baseline evidence overlay identity is invalid")
    intended_scope = proposal.get("intended_scope")
    if not isinstance(intended_scope, dict) or set(intended_scope) != {"wp", "journey"} or not all(isinstance(intended_scope.get(key), str) and intended_scope[key] for key in ("wp", "journey")):
        errors.append("PROPOSED baseline intended WP/journey scope is invalid")
    errors.extend(_candidate_errors(proposal.get("candidate"), "PROPOSED baseline", require_manifest_digest=True))
    delta = proposal.get("delta")
    delta_errors = _delta_errors(delta)
    errors.extend(delta_errors)
    if not delta_errors:
        active = current_record(current)
        inventory = (active or {}).get("governed_files")
        active_hashes = {
            item.get("path"): item.get("sha256")
            for item in (inventory if isinstance(inventory, list) else [])
            if isinstance(item, dict) and isinstance(item.get("path"), str)
            and isinstance(item.get("sha256"), str)
        }
        for item in delta:
            previous = active_hashes.get(item.get("path"))
            if previous is not None and item.get("before_sha256") != previous:
                errors.append("PROPOSED baseline delta does not start from active CURRENT hash")
        errors.extend(_addition_errors(proposal, current, root))
    errors.extend(_historical_test_successor_errors(proposal.get("historical_test_successors"), root))
    gates = proposal.get("gates")
    if not isinstance(gates, list) or not gates or any(not isinstance(item, dict) or set(item) != {"name", "result", "evidence_ref"} or item.get("result") != "PASS" or not isinstance(item.get("evidence_ref"), str) or not item["evidence_ref"] for item in gates):
        errors.append("PROPOSED baseline mandatory gates are not all PASS with evidence")
    evidence = proposal.get("evidence")
    if not isinstance(evidence, dict) or set(evidence) != {"candidate_manifest", "candidate_evidence", "report"}:
        errors.append("PROPOSED baseline candidate-bound evidence is invalid")
    elif any(not isinstance(value, dict) or set(value) != {"path", "sha256"} or not isinstance(value.get("path"), str) or not value["path"] or not _is_sha(value.get("sha256")) for value in evidence.values()):
        errors.append("PROPOSED baseline candidate-bound evidence is invalid")
    # A pilot acceptance is durable evidence, not promotion authority. The
    # distinct promotion helper still needs a new explicit owner reference.
    errors.extend(_pilot_acceptance_errors(proposal.get("owner_acceptance")))
    overlays = proposal.get("allowed_overlay_paths")
    if not isinstance(overlays, list) or not overlays or len(overlays) != len(set(overlays)) or any(not _valid_relative_path(item) for item in overlays):
        errors.append("PROPOSED baseline overlay paths are invalid")
    return errors


def proposal_state(proposal: object, current: dict[str, Any], root: Path) -> tuple[str, list[str]]:
    errors = validate_proposal(proposal, current, root)
    if errors:
        return "FAIL", errors
    if proposal.get("owner_acceptance") is not None:
        return "PILOT_ACCEPTED / AWAITING_CURRENT_PROMOTION_AUTHORIZATION", []
    return "PROPOSED_BASELINE_VALID / AWAITING_OWNER_ACCEPTANCE", []


def verify_promotion_material(proposal: dict[str, Any], root: Path, proposal_path: Path | None = None,
                              *, acceptance_ref: str | None = None) -> list[str]:
    """Verify the exact source, candidate manifest/bundle and named evidence.

    This deliberately has no authority side effect.  It is used by the helper
    after structural proposal validation, not by a green test as a substitute
    for the owner reference.
    """
    errors: list[str] = []
    delta_errors = _delta_errors(proposal.get("delta"))
    if delta_errors:
        return delta_errors
    try:
        commit = _git(root, "rev-parse", "HEAD")
        tree = _git(root, "rev-parse", "HEAD^{tree}")
    except (OSError, subprocess.CalledProcessError):
        return ["promotion source Git identity is unavailable"]
    source = proposal.get("proposed_source", {})
    overlay = proposal.get("proposed_head", {})
    base = proposal.get("base_main")
    base_commit = base.get("commit_sha") if isinstance(base, dict) else None
    if not isinstance(source, dict) or not isinstance(overlay, dict) or not isinstance(base_commit, str):
        return ["promotion proposal identities are unavailable"]
    try:
        if _commit_identity(root, base_commit) != proposal.get("base_main"):
            errors.append("promotion CURRENT base Git identity differs")
        if _commit_identity(root, source["commit_sha"]) != source:
            errors.append("promotion product source identity differs from PROPOSED baseline")
        if _commit_identity(root, overlay["commit_sha"]) != overlay:
            errors.append("promotion evidence overlay identity differs from PROPOSED baseline")
        subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor", base_commit, source["commit_sha"]], check=True)
        subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor", source["commit_sha"], overlay["commit_sha"]], check=True)
    except (OSError, subprocess.CalledProcessError, KeyError, ValueError, TypeError):
        errors.append("promotion source/overlay lineage is invalid")
        return errors
    # The persisted proposal cannot name its own commit/tree without a Git blob
    # self-reference.  It must therefore be the only change immediately after
    # the exact evidence overlay it names.
    try:
        relative_proposal = proposal_path.resolve().relative_to(root.resolve()).as_posix() if proposal_path else None
        if acceptance_ref is not None:
            # A consumed successor preserves acceptance on its merge's second
            # parent. Validate that exact immutable, reachable record rather
            # than searching only the later main first-parent chain.
            if not isinstance(acceptance_ref, str) or re.fullmatch(r"[0-9a-f]{40}", acceptance_ref) is None:
                raise ValueError("invalid acceptance commit")
            subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor",
                            acceptance_ref, "HEAD"], check=True, capture_output=True)
            if (proposal.get("owner_acceptance") is None or relative_proposal is None
                    or json.loads(_git(root, "show", f"{acceptance_ref}:{relative_proposal}")) != proposal):
                raise ValueError("acceptance record differs")
            commit = acceptance_ref
        parent = _git(root, "rev-parse", f"{commit}^")
    except (OSError, subprocess.CalledProcessError, ValueError):
        errors.append("promotion proposal record path or acceptance anchor is invalid")
        relative_proposal = None
        parent = ""
    acceptance = proposal.get("owner_acceptance")
    if acceptance is None:
        if relative_proposal is None:
            errors.append("promotion proposal record path is unavailable")
        else:
            _, declaration_errors = _proposal_declaration_commit(
                root, overlay["commit_sha"], proposal, relative_proposal)
            errors.extend(declaration_errors)
    else:
        # A durable pilot acceptance is a one-file amendment of the original
        # declaration. Governance code may have advanced between those two
        # records, but the declaration itself must remain byte-identical.
        try:
            expected_prior = json.loads(json.dumps(proposal))
            expected_prior["owner_acceptance"] = None
            revisions = _git(root, "rev-list", "--first-parent", "--reverse",
                             f"{overlay['commit_sha']}..{commit}").splitlines()
        except (OSError, subprocess.CalledProcessError, ValueError, TypeError):
            errors.append("promotion pilot acceptance predecessor is unavailable")
        else:
            declaration = None
            acceptance_commit = None
            for revision in revisions:
                # A merge can carry the unchanged proposal file from either
                # parent.  It is not a declaration or acceptance amendment
                # unless this commit actually changed that one governed file.
                if relative_proposal not in _changed_paths(root, f"{revision}^", revision):
                    continue
                try:
                    record = json.loads(_git(root, "show", f"{revision}:{relative_proposal}"))
                except (OSError, subprocess.CalledProcessError, ValueError, TypeError):
                    continue
                if record == expected_prior and declaration is None:
                    declaration = revision
                if record == proposal:
                    acceptance_commit = revision
            if declaration is None or acceptance_commit is None:
                errors.append("promotion pilot acceptance declaration history is unavailable")
            else:
                try:
                    declaration_parent = _git(root, "rev-parse", f"{declaration}^")
                    acceptance_parent = _git(root, "rev-parse", f"{acceptance_commit}^")
                    prior = json.loads(_git(root, "show", f"{acceptance_parent}:{relative_proposal}"))
                except (OSError, subprocess.CalledProcessError, ValueError, TypeError):
                    errors.append("promotion pilot acceptance predecessor is unavailable")
                else:
                    if declaration_parent != overlay.get("commit_sha"):
                        errors.append("promotion proposal declaration is not directly atop evidence overlay")
                    if _changed_paths(root, declaration_parent, declaration) != [relative_proposal]:
                        errors.append("promotion declaration overlay must contain only the PROPOSED record")
                    if prior != expected_prior:
                        errors.append("promotion pilot acceptance changed proposal bytes beyond acceptance")
                    if _changed_paths(root, acceptance_parent, acceptance_commit) != [relative_proposal]:
                        errors.append("promotion pilot acceptance overlay must contain only the PROPOSED record")

    declared = {item["path"]: item for item in proposal["delta"]}
    if any(item["before_sha256"] is None for item in declared.values()):
        try:
            current = json.loads((root / "state/current_product_baseline_v2.json").read_text(encoding="utf-8"))
            errors.extend(_addition_errors(proposal, current, root))
        except (OSError, ValueError, TypeError):
            errors.append("promotion addition active CURRENT is unavailable or invalid")
    try:
        product_changes = [path for path in _changed_paths(root, base_commit, source["commit_sha"])
                           if _governed_product_path(path)]
    except (OSError, subprocess.CalledProcessError):
        errors.append("promotion cannot compare product source to CURRENT base")
        product_changes = []
    if set(product_changes) != set(declared):
        errors.append("promotion governed CURRENT-to-source delta is undeclared or overstated")
    for path_text, item in declared.items():
        try:
            before = _regular_blob_hash(root, base_commit, path_text)
            after = _regular_blob_hash(root, source["commit_sha"], path_text)
        except (OSError, subprocess.CalledProcessError, ValueError):
            errors.append(f"promotion declared delta is unavailable: {path_text}")
            continue
        if before != item["before_sha256"] or after != item["after_sha256"]:
            errors.append(f"promotion declared delta differs: {path_text}")

    successors = proposal.get("historical_test_successors", [])
    declared_successors = {
        (item["historical_authority"], item["path"]): item
        for item in successors if isinstance(item, dict)
        and {"path", "historical_authority", "before_sha256", "after_sha256", "reason"} == set(item)
    }
    historical_test_paths = _historical_test_paths(root)
    changed_historical_tests: set[tuple[str, str]] = set()
    for path_text, authorities in historical_test_paths.items():
        try:
            before = subprocess.run(["git", "-C", str(root), "show", f"{base_commit}:{path_text}"], check=True, capture_output=True).stdout
            after = subprocess.run(["git", "-C", str(root), "show", f"{source['commit_sha']}:{path_text}"], check=True, capture_output=True).stdout
        except (OSError, subprocess.CalledProcessError):
            errors.append(f"promotion historical test path is unavailable: {path_text}")
            continue
        if before == after or path_text in declared:
            continue
        for authority in authorities:
            changed_historical_tests.add((authority, path_text))
    if set(declared_successors) != changed_historical_tests:
        errors.append("promotion historical test drift is undeclared or overstated")
    for (authority, path_text), item in declared_successors.items():
        historical = _historical_test_hash(root, authority, path_text)
        try:
            before = subprocess.run(["git", "-C", str(root), "show", f"{base_commit}:{path_text}"], check=True, capture_output=True).stdout
            after = subprocess.run(["git", "-C", str(root), "show", f"{source['commit_sha']}:{path_text}"], check=True, capture_output=True).stdout
        except (OSError, subprocess.CalledProcessError):
            errors.append(f"promotion historical test successor is unavailable: {path_text}")
            continue
        if (historical is None or hashlib.sha256(before).hexdigest() != historical
                or hashlib.sha256(before).hexdigest() != item["before_sha256"]
                or hashlib.sha256(after).hexdigest() != item["after_sha256"]):
            errors.append(f"promotion historical test successor differs: {path_text}")

    try:
        overlay_changes = _changed_paths(root, source["commit_sha"], overlay["commit_sha"])
    except (OSError, subprocess.CalledProcessError):
        errors.append("promotion cannot compare source to evidence overlay")
        overlay_changes = []
    allowed = set(proposal["allowed_overlay_paths"])
    if any(path not in allowed for path in overlay_changes):
        errors.append("promotion evidence overlay contains undeclared paths")
    if any(_governed_product_path(path) for path in overlay_changes):
        errors.append("promotion evidence overlay contains product/runtime bytes")
    if any(path in historical_test_paths for path in overlay_changes):
        errors.append("promotion evidence overlay contains historical test bytes")
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
        manifest_source = ((manifest.get("identity") or {}).get("source"))
        source_bound = (isinstance(manifest_source, dict)
                        and {key: manifest_source.get(key) for key in ("commit_sha", "tree_sha")} == source
                        and manifest_source.get("dirty") is False)
        if sha256_file(manifest_path) != evidence["candidate_manifest"]["sha256"] or sha256_file(manifest_path) != proposal["candidate"]["manifest_digest"] or manifest.get("candidate_id") != proposal["candidate"]["candidate_id"] or manifest.get("identity_sha256") != proposal["candidate"]["identity_sha256"] or not isinstance(bundle, dict) or bundle.get("digest") != proposal["candidate"]["bundle_digest"] or not source_bound:
            errors.append("promotion candidate manifest does not bind PROPOSED candidate/bundle")
    if candidate_evidence is not None and (sha256_file(root / evidence["candidate_evidence"]["path"]) != evidence["candidate_evidence"]["sha256"] or candidate_evidence.get("candidate_id") != proposal["candidate"]["candidate_id"] or candidate_evidence.get("manifest_identity_sha256") != proposal["candidate"]["identity_sha256"] or candidate_evidence.get("bundle_digest") != proposal["candidate"]["bundle_digest"] or candidate_evidence.get("product_source") != source):
        errors.append("promotion candidate evidence does not bind PROPOSED candidate/bundle")
    for gate in proposal["gates"]:
        if not (root / gate["evidence_ref"]).is_file():
            errors.append(f"promotion gate evidence is unavailable: {gate['name']}")
    report_path = root / evidence["report"]["path"]
    if not report_path.is_file() or sha256_file(report_path) != evidence["report"]["sha256"]:
        errors.append("promotion report reference is unavailable")
    return errors


def next_current(current: dict[str, Any], proposal: dict[str, Any], owner_acceptance_ref: str, *, previous_current_path: str,
                 root: Path | None = None) -> dict[str, Any]:
    """Construct, but do not write, the next CURRENT record after explicit owner input."""
    if not isinstance(owner_acceptance_ref, str) or not owner_acceptance_ref.strip():
        raise ValueError("explicit owner acceptance reference is required")
    if not isinstance(previous_current_path, str) or not previous_current_path or previous_current_path.startswith("/") or ".." in Path(previous_current_path).parts:
        raise ValueError("repository-relative previous CURRENT history path is required")
    record = current_record(current)
    if record is None:
        raise ValueError("CURRENT record is invalid")
    errors = _delta_errors(proposal.get("delta"))
    if not errors:
        errors = _addition_errors(proposal, current, root if root is not None else Path(__file__).resolve().parents[1])
    if errors:
        raise ValueError("; ".join(errors))
    # A successor is cumulative: it retains every previously governed byte
    # unless an exact proposal delta explicitly replaces that path.  Dropping a
    # path would sever the hash-verified historical chain for R12/R13.
    governed = {
        item["path"]: item["sha256"]
        for item in record.get("governed_files", [])
        if isinstance(item, dict) and set(item) == {"path", "sha256"}
    }
    for item in proposal.get("delta", []):
        if not isinstance(item, dict) or set(item) != {"path", "before_sha256", "after_sha256"}:
            raise ValueError("PROPOSED baseline delta is invalid")
        path = item["path"]
        if path in governed and item["before_sha256"] != governed[path]:
            raise ValueError("PROPOSED baseline delta does not start from active CURRENT hash")
        governed[path] = item["after_sha256"]
    # A historical test successor is not executable product delta, but it is
    # an exact current byte that supersedes an immutable R12/R13 test hash.
    # Retiring its PROPOSED record would otherwise erase the only active
    # hash-closed link the historical validator can follow.
    for item in proposal.get("historical_test_successors", []):
        if not isinstance(item, dict) or set(item) != {
            "path", "historical_authority", "before_sha256", "after_sha256", "reason",
        }:
            raise ValueError("PROPOSED historical test successor is invalid")
        path = item["path"]
        if path in governed and item["before_sha256"] != governed[path]:
            raise ValueError("PROPOSED historical test successor does not start from active CURRENT hash")
        governed[path] = item["after_sha256"]
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
        # Match the exact pretty-printed bytes the promotion helper writes to
        # the immutable history file; hashing a different serialization would
        # make a legitimate next CURRENT fail closed after preparation.
        "historical_predecessors": [{"path": previous_current_path, "sha256": hashlib.sha256((json.dumps(current, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()).hexdigest()}],
        "governed_files": [{"path": path, "sha256": governed[path]} for path in sorted(governed)],
    }
    result = json.loads(json.dumps(current))
    result["records"].append(new_record)
    result["current_id"] = new_id
    return result
