#!/usr/bin/env python3
"""Explicit, fail-closed helper for a reviewed Proposed Baseline Lite record."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from proposed_baseline_lite import next_current, validate_current, validate_proposal, verify_promotion_material  # noqa: E402
from candidate_archive import path_is_within, verify_archive  # noqa: E402
from candidate_protection_gate import require_promotion  # noqa: E402


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare a next CURRENT baseline only after explicit owner acceptance.")
    parser.add_argument("--proposal", type=Path, required=True)
    parser.add_argument("--owner-acceptance-ref", required=True)
    parser.add_argument("--candidate-archive", type=Path, required=True,
                        help="completed durable archive containing the exact proposed application")
    parser.add_argument("--current-archive", type=Path, required=True,
                        help="completed durable archive preserving the outgoing CURRENT application")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--history-output", type=Path, required=True,
                        help="repository-relative immutable copy of the prior CURRENT record")
    args = parser.parse_args(argv)
    current_path = ROOT / "state/current_product_baseline_v2.json"
    current = load(current_path)
    proposal = load(args.proposal)
    # CURRENT must be evaluated in the active PROPOSED context: the proposal
    # verifier, not a historical CURRENT byte check, owns the declared A delta.
    # Pass the actual record path as well, because material validation proves
    # that the declaration commit contains only this file.
    errors = (validate_current(current, ROOT, proposal)
              + validate_proposal(proposal, current, ROOT)
              + verify_promotion_material(proposal, ROOT, args.proposal))
    if errors:
        print("PROMOTION: FAIL")
        print("\n".join(f"- {item}" for item in errors))
        return 1
    try:
        verify_archive(args.candidate_archive, expected={
            key: proposal["candidate"][key]
            for key in ("candidate_id", "bundle_digest", "manifest_digest")
        })
        active = next(record for record in current["records"]
                      if record["baseline_id"] == current["current_id"])
        verify_archive(args.current_archive, expected={
            key: active["candidate"][key] for key in ("candidate_id", "bundle_digest")
        })
        require_promotion(proposal, current, args.candidate_archive, args.current_archive)
        archives = (args.candidate_archive, args.current_archive)
        if any(path_is_within(path.resolve(), archive) for path in (args.output, args.history_output)
               for archive in archives):
            raise ValueError("promotion outputs must be outside both retained archives")
    except (OSError, ValueError) as error:
        print(f"PROMOTION: FAIL\n- candidate archive: {error}")
        return 1
    # This argument is intentionally required and is not derived from CI, a
    # branch name, a PR status, or an evidence artifact.
    try:
        history_relative = args.history_output.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        print("PROMOTION: FAIL\n- history output must be inside the repository")
        return 1
    if args.output.resolve() == args.history_output.resolve() or any(
        path.exists() or path.is_symlink() for path in (args.output, args.history_output)
    ):
        print("PROMOTION: FAIL\n- output and history must be distinct new files")
        return 1
    result = next_current(current, proposal, args.owner_acceptance_ref, previous_current_path=history_relative)
    args.history_output.parent.mkdir(parents=True, exist_ok=True)
    with args.history_output.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(current, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    print("PROMOTION: PREPARED_EXPLICIT_OWNER_AUTHORIZATION_REQUIRED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
