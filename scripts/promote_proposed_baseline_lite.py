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


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare a next CURRENT baseline only after explicit owner acceptance.")
    parser.add_argument("--proposal", type=Path, required=True)
    parser.add_argument("--owner-acceptance-ref", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--history-output", type=Path, required=True,
                        help="repository-relative immutable copy of the prior CURRENT record")
    args = parser.parse_args()
    current_path = ROOT / "state/current_product_baseline_v2.json"
    current = load(current_path)
    proposal = load(args.proposal)
    errors = validate_current(current, ROOT) + validate_proposal(proposal, current, ROOT) + verify_promotion_material(proposal, ROOT)
    if errors:
        print("PROMOTION: FAIL")
        print("\n".join(f"- {item}" for item in errors))
        return 1
    # This argument is intentionally required and is not derived from CI, a
    # branch name, a PR status, or an evidence artifact.
    try:
        history_relative = args.history_output.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        print("PROMOTION: FAIL\n- history output must be inside the repository")
        return 1
    result = next_current(current, proposal, args.owner_acceptance_ref, previous_current_path=history_relative)
    args.history_output.parent.mkdir(parents=True, exist_ok=True)
    args.history_output.write_text(json.dumps(current, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print("PROMOTION: PREPARED_EXPLICIT_OWNER_AUTHORIZATION_REQUIRED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
