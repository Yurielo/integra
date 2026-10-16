#!/usr/bin/env python3
"""Prepare records for the one accepted #214 gap; never install or promote.

The normal promotion helper remains the authority for every other transition.
This helper deliberately has no outgoing archive argument: its evidence says
that exact historical bytes are missing, not recovered.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from candidate_archive import path_is_within, verify_archive  # noqa: E402
from candidate_protection_gate import (HISTORICAL_PROPOSAL_HEAD,
                                       require_historical_gap_transition)  # noqa: E402
from proposed_baseline_lite import (next_current, validate_current, validate_proposal,
                                    verify_promotion_material)  # noqa: E402


def _bytes(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Prepare only the exact accepted historical-gap transition.')
    parser.add_argument('--proposal', required=True, type=Path)
    parser.add_argument('--proposal-checkout', required=True, type=Path,
                        help='clean read-only checkout at exact accepted PR #213 head')
    parser.add_argument('--candidate-archive', required=True, type=Path)
    parser.add_argument('--transition-authority-ref', required=True)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--history-output', required=True, type=Path)
    parser.add_argument('--evidence-output', required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        current_path = ROOT / 'state/current_product_baseline_v2.json'
        current_data = current_path.read_bytes()
        current = json.loads(current_data)
        proposal_root = args.proposal_checkout.resolve(strict=True)
        if args.proposal.resolve(strict=True) != proposal_root / 'state/proposed_baseline_lite_v1.json':
            raise ValueError('proposal must be the exact PR #213 record in its checkout')
        head = subprocess.run(['git', '-C', str(proposal_root), 'rev-parse', 'HEAD'],
                              check=True, capture_output=True, text=True).stdout.strip()
        dirty = subprocess.run(['git', '-C', str(proposal_root), 'status', '--porcelain'],
                               check=True, capture_output=True, text=True).stdout
        if head != HISTORICAL_PROPOSAL_HEAD or dirty:
            raise ValueError('proposal checkout is not the exact clean accepted PR #213 head')
        proposal = json.loads(args.proposal.read_bytes())
        errors = (validate_current(current, proposal_root, proposal)
                  + validate_proposal(proposal, current, proposal_root)
                  + verify_promotion_material(proposal, proposal_root, args.proposal))
        if errors:
            raise ValueError('; '.join(errors))
        receipt = verify_archive(args.candidate_archive, expected={
            key: proposal['candidate'][key]
            for key in ('candidate_id', 'bundle_digest', 'manifest_digest')})
        authority = require_historical_gap_transition(
            proposal, current, args.candidate_archive, args.transition_authority_ref)
        paths = (args.output, args.history_output, args.evidence_output)
        if len({path.resolve() for path in paths}) != 3:
            raise ValueError('all transition outputs must be distinct')
        if any(path.exists() or path.is_symlink() for path in paths):
            raise ValueError('transition output already exists')
        if any(path_is_within(path.resolve(), args.candidate_archive)
               for path in paths):
            raise ValueError('transition output is inside protected Candidate archive')
        try:
            history_relative = args.history_output.resolve().relative_to(ROOT.resolve()).as_posix()
            args.evidence_output.resolve().relative_to(ROOT.resolve())
            args.output.resolve().relative_to(ROOT.resolve())
        except ValueError as error:
            raise ValueError('all transition outputs must be inside the repository') from error
        result = next_current(current, proposal, args.transition_authority_ref,
                              previous_current_path=history_relative, root=proposal_root)
        evidence = {
            'artifact_type': 'integra.historical_gap_transition_evidence',
            'schema_version': '1.0',
            'issue_ref': 'https://github.com/Yurielo/integra/issues/216',
            'status': 'PREPARED_NOT_PROMOTED',
            'outgoing_current_id': current['current_id'],
            'outgoing_current_sha256': hashlib.sha256(current_data).hexdigest(),
            'proposed_candidate': proposal['candidate'],
            'proposed_archive_receipt': receipt,
            **authority,
        }
        # The helper creates new records only. It never replaces CURRENT,
        # historical receipts, the registry, or an existing output.
        for path, value in ((args.history_output, current), (args.evidence_output, evidence),
                            (args.output, result)):
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('xb') as handle:
                handle.write(_bytes(value))
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        print(f'HISTORICAL_GAP_TRANSITION: FAIL\n- {error}')
        return 1
    print('HISTORICAL_GAP_TRANSITION: PREPARED_NOT_PROMOTED')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
