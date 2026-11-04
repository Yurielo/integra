"""Generic atomic promotion of one accepted *open* Proposal to CURRENT.

The open Proposal is protected in the transaction PRE-state, but is consumed
from the active proposal set in the POST-state.  This avoids requiring a PR to
contain a registry reference to its own future commit SHA.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

try:
    from scripts import candidate_archive, candidate_protection_audit as protection
    from scripts import proposed_baseline_lite as baseline
except ModuleNotFoundError:
    import candidate_archive
    import candidate_protection_audit as protection
    import proposed_baseline_lite as baseline

ROOT = Path(__file__).resolve().parents[1]
CURRENT = "state/current_product_baseline_v2.json"
REGISTRY = "state/candidate_protection_registry_v1.json"
PROPOSAL = "state/proposed_baseline_lite_v1.json"
HISTORY = "state/history"


def encoded(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def digest(value: object) -> str:
    return hashlib.sha256(encoded(value)).hexdigest()


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def _blob(root: Path, ref: str, path: str) -> bytes:
    return subprocess.check_output(["git", "show", f"{ref}:{path}"], cwd=root)


def _identity(value: dict) -> dict:
    return {key: value[key] for key in protection.IDENTITY}


def _authority(text: str, proposal: dict) -> str:
    required = ("PROMOTE_CURRENT", proposal["proposal_id"], proposal["candidate"]["candidate_id"])
    if not isinstance(text, str) or any(token not in text for token in required):
        raise ValueError("explicit promotion authorization does not bind proposal and Candidate")
    return text


def _paths(proposal: dict) -> dict:
    suffix = proposal["candidate"]["candidate_id"][13:29]
    return {
        "old_current": f"{HISTORY}/open_proposal_{suffix}_outgoing_current_v2.json",
        "old_registry": f"{HISTORY}/open_proposal_{suffix}_outgoing_protection_registry_v1.json",
        "retired": f"{HISTORY}/open_proposal_{suffix}_accepted_proposal_lite_v1.json",
        "event": f"{HISTORY}/open_proposal_{suffix}_promotion_transaction_v1.json",
    }


def _virtual_pre_registry(registry: dict, proposal: dict, pr: int, head: str,
                          proposal_sha256: str | None = None) -> dict:
    result = copy.deepcopy(registry)
    candidate = _identity(proposal["candidate"])
    reference = {"pr": pr, "head_sha": head, **candidate}
    registered = [row for row in result["proposed"] if row.get("pr") == pr]
    if registered:
        # A current protection registry binds newer Proposals by their immutable
        # Proposal bytes rather than a mutable branch head.  Treat that exact
        # binding as the required pre-state protection; reject every partial or
        # conflicting registration instead of replacing it with a synthetic row.
        expected = {"path": PROPOSAL, "pr": pr, "proposal_id": proposal["proposal_id"],
                    "proposal_sha256": proposal_sha256 or digest(proposal), **candidate}
        if len(registered) != 1 or any(registered[0].get(key) != value
                                       for key, value in expected.items()):
            raise ValueError("registered promotion Proposal binding differs from exact target")
    else:
        result["proposed"].append(reference)
    base = Path.home() / "Library/Application Support/Integra"
    result["selected_survivors"][candidate["candidate_id"]] = (
        f"Build Archive/{candidate['candidate_id']}/{candidate['bundle_digest']}")
    return result


def preflight(root: Path, *, pr: int, expected_head: str, expected_base: str,
              authorization: str) -> dict:
    """Read and pin all PRE-state inputs; never writes canonical state."""
    registry = json.loads((root / REGISTRY).read_bytes())
    current, proposals, canonical = protection.fetch_canonical(registry)
    if canonical["main_sha"] != expected_base:
        raise ValueError("canonical main/base changed before promotion")
    remote_pr = protection._api(f"repos/{protection.REPOSITORY}/pulls/{pr}")
    if (remote_pr.get("state") != "open" or remote_pr.get("head", {}).get("sha") != expected_head
            or remote_pr.get("base", {}).get("sha") != expected_base):
        raise ValueError("promotion PR head/base/state differs from external preflight")
    proposal = proposals.get(pr)
    proposal_raw = _blob(root, expected_head, PROPOSAL)
    if proposal is None or json.loads(proposal_raw) != proposal:
        raise ValueError("exact open Proposal is unavailable or differs")
    _authority(authorization, proposal)
    errors = (baseline.validate_current(current, root, proposal)
              + baseline.validate_proposal(proposal, current, root)
              + baseline.verify_promotion_material(proposal, root, root / PROPOSAL,
                                                    acceptance_ref=expected_head))
    if errors:
        raise ValueError("; ".join(errors))
    base = Path.home() / "Library/Application Support/Integra"
    virtual = _virtual_pre_registry(registry, proposal, pr, expected_head,
                                    protection.sha(proposal_raw))
    virtual['selected_survivors'] = protection.reconcile_survivors(
        virtual, current, proposals, canonical, incoming=proposal['candidate'])
    packages = protection.scan_local(virtual, base)
    audit = protection.resolve(virtual, current, proposals, packages,
                               free_bytes=shutil.disk_usage(base).free, canonical=canonical)
    if audit["authority_state"] != "COMPLETE" or not audit["promotion_ready"]:
        raise ValueError("virtual transaction PRE-state is not completely protected: "
                         + ",".join(audit["blockers"] + audit["promotion_blockers"]))
    archive = base / virtual["selected_survivors"][proposal["candidate"]["candidate_id"]]
    receipt = candidate_archive.verify_archive(archive, _identity(proposal["candidate"]))
    return {"pr": pr, "head": expected_head, "base": expected_base, "proposal": proposal,
            "current": current, "registry": registry, "canonical": canonical,
            "authorization": authorization, "archive": str(archive), "receipt": receipt,
            "proposals": proposals}


def package(root: Path, pinned: dict) -> tuple[dict, dict[str, bytes | None]]:
    """Make deterministic POST-state bytes, without a self-referential PR SHA."""
    proposal, current, registry = pinned["proposal"], pinned["current"], copy.deepcopy(pinned["registry"])
    outgoing_identity = {key: registry["canonical_current"][key] for key in protection.IDENTITY}
    paths = _paths(proposal)
    raw_current, raw_registry = encoded(current), encoded(pinned["registry"])
    successor = baseline.next_current(current, proposal, pinned["authorization"],
                                      previous_current_path=paths["old_current"], root=root)
    successor_raw = encoded(successor)
    candidate = _identity(proposal["candidate"])
    registry["canonical_current"] = {"path": CURRENT, "sha256": protection.sha(successor_raw),
                                     "current_id": successor["current_id"], **candidate}
    registry["latest_accepted_candidate_id"] = candidate["candidate_id"]
    registry["rollback"] = {**outgoing_identity,
                            "confirmation_ref": paths["event"]}
    registry["proposed"] = [row for row in registry["proposed"] if row.get("pr") != pinned["pr"]]
    post_proposals = {n: p for n, p in pinned['proposals'].items() if n != pinned['pr']}
    post_canonical = {**pinned['canonical'], 'current_sha256': protection.sha(successor_raw)}
    registry['selected_survivors'] = protection.reconcile_survivors(
        registry, successor, post_proposals, post_canonical, incoming=candidate)
    event = {"artifact_type": "integra.open_proposal_promotion_transaction", "schema_version": "1.0",
             "transaction_id": "open-proposal-v1-" + digest({k: pinned[k] for k in ("pr", "head", "base", "authorization")}),
             "inputs": {"pr": pinned["pr"], "head": pinned["head"], "base": pinned["base"],
                        "proposal_id": proposal["proposal_id"], "proposal_sha256": protection.sha(encoded(proposal)),
                        "candidate": candidate, "outgoing_current_id": current["current_id"],
                        "authorization": pinned["authorization"],
                        "archive_inventory_sha256": pinned["receipt"]["inventory_sha256"]},
             "semantics": {"pre": "OPEN_PROPOSAL_PROTECTED", "post": "CURRENT_PROTECTED_PROPOSAL_CONSUMED",
                           "retry": "EXACT_ALREADY_APPLIED_ONLY"},
             "result": {"current_id": successor["current_id"], "files": {}}}
    files = {CURRENT: successor_raw, REGISTRY: encoded(registry), paths["old_current"]: raw_current,
             paths["old_registry"]: raw_registry, paths["retired"]: encoded(proposal), PROPOSAL: None}
    event["result"]["files"] = {path: None if data is None else protection.sha(data) for path, data in files.items()}
    files[paths["event"]] = encoded(event)
    return event, files


def validate_post(root: Path, event: dict, files: dict[str, bytes | None]) -> dict:
    for path, raw in files.items():
        target = root / path
        if raw is None:
            if target.exists(): raise ValueError("active Proposal is not retired")
        elif not target.is_file() or target.read_bytes() != raw:
            raise ValueError("successor transaction package differs: " + path)
    successor = json.loads(files[CURRENT])
    errors = baseline.validate_current(successor, root)
    if errors: raise ValueError("; ".join(errors))
    registry = json.loads(files[REGISTRY])
    current, proposals, canonical = protection.fetch_canonical(registry)
    if current != successor or event["inputs"]["pr"] in proposals:
        raise ValueError("post-state CURRENT or active proposal set differs")
    base = Path.home() / "Library/Application Support/Integra"
    audit = protection.resolve(registry, current, proposals, protection.scan_local(registry, base),
                               free_bytes=shutil.disk_usage(base).free, canonical=canonical)
    if audit["authority_state"] != "COMPLETE":
        raise ValueError("post-state protection audit fails: " + ",".join(audit["blockers"]))
    identity = event['inputs']['candidate']
    lifecycle = canonical.get('canonical_lifecycles', {}).get(identity['candidate_id'])
    if not lifecycle or any(lifecycle.get(k) != identity[k] for k in protection.IDENTITY):
        raise ValueError('post-state exact canonical lifecycle missing or conflicts')
    audit['registry_sha256'] = protection.sha(files[REGISTRY])
    return audit


def apply(root: Path, *, pr: int, expected_head: str, expected_base: str, authorization: str) -> str:
    try:
        from scripts import candidate_retention as retention
    except ModuleNotFoundError:
        import candidate_retention as retention
    base = Path.home() / 'Library/Application Support/Integra'
    # The same lock used by cleanup spans the final archive verification,
    # canonical transition, post-validation and catalog lifecycle mirror.
    with retention.locked(retention.catalog_path(base / 'Build Archive')) as catalog:
        return _apply_locked(root, pr=pr, expected_head=expected_head,
                             expected_base=expected_base, authorization=authorization,
                             catalog=catalog, base=base)


def _apply_locked(root: Path, *, pr: int, expected_head: str, expected_base: str,
                  authorization: str, catalog: dict, base: Path) -> str:
    pinned = preflight(root, pr=pr, expected_head=expected_head, expected_base=expected_base, authorization=authorization)
    event, files = package(root, pinned)
    checks = protection._api(f"repos/{protection.REPOSITORY}/commits/{expected_head}/check-runs")["check_runs"]
    if not any(row.get("name") == "governance" and row.get("conclusion") == "success" for row in checks):
        raise ValueError("final GitHub Quality Gate is not successful")
    with tempfile.NamedTemporaryFile(prefix="integra-promotion-index-", delete=False) as handle:
        index = handle.name
    try:
        env = {**__import__("os").environ, "GIT_INDEX_FILE": index}
        subprocess.run(["git", "read-tree", expected_head], cwd=root, env=env, check=True)
        for path, raw in files.items():
            if raw is None:
                subprocess.run(["git", "update-index", "--force-remove", "--", path], cwd=root, env=env, check=True)
            else:
                blob = subprocess.check_output(["git", "hash-object", "-w", "--stdin"], cwd=root, input=raw)
                subprocess.run(["git", "update-index", "--add", "--cacheinfo", "100644," + blob.decode().strip() + "," + path], cwd=root, env=env, check=True)
        tree = subprocess.check_output(["git", "write-tree"], cwd=root, env=env, text=True).strip()
        merge = _git(root, "commit-tree", tree, "-p", expected_base, "-p", expected_head,
                     "-m", f"Merge pull request #{pr} with governed open-proposal promotion")
        result = subprocess.run(["git", "push", "origin", merge + ":refs/heads/main"], cwd=root, capture_output=True, text=True, timeout=60)
        if result.returncode: raise ValueError("canonical merge push failed: " + result.stderr.strip())
    finally:
        Path(index).unlink(missing_ok=True)
    # Validate the actual pushed tree in a clean Git context; never overwrite
    # the proposal worktree or claim success from a merely prepared package.
    with tempfile.TemporaryDirectory(prefix='integra-promotion-post-') as directory:
        checkout = Path(directory) / 'checkout'
        subprocess.run(['git', 'worktree', 'add', '--detach', str(checkout), merge], cwd=root, check=True,
                       capture_output=True)
        try:
            audit = validate_post(checkout, event, files)
            try:
                from scripts import candidate_retention as retention
            except ModuleNotFoundError:
                import candidate_retention as retention
            retention.reconcile_catalog(catalog, json.loads(files[REGISTRY]), audit, base)
        finally:
            subprocess.run(['git', 'worktree', 'remove', str(checkout)], cwd=root, check=True,
                           capture_output=True)
    return merge


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pr", type=int, required=True); parser.add_argument("--head", required=True)
    parser.add_argument("--base", required=True); parser.add_argument("--authorization", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.apply:
        print(apply(ROOT, pr=args.pr, expected_head=args.head, expected_base=args.base, authorization=args.authorization))
    else:
        pinned = preflight(ROOT, pr=args.pr, expected_head=args.head, expected_base=args.base, authorization=args.authorization)
        event, files = package(ROOT, pinned); print(json.dumps({"transaction_id": event["transaction_id"], "files": sorted(files)}))
    return 0


if __name__ == "__main__": raise SystemExit(main())
