#!/usr/bin/env python3
"""Read-only prospective survivor/lifecycle report; never leases or deletes."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import shutil

try:
    from scripts import candidate_protection_audit as protection
    from scripts import candidate_retention as retention
except ModuleNotFoundError:
    import candidate_protection_audit as protection
    import candidate_retention as retention


def report(*, prospective_policy=False):
    base = Path.home() / 'Library/Application Support/Integra'
    catalog = retention.catalog_path(base / 'Build Archive')
    before = catalog.read_bytes()
    registry_raw = protection.REGISTRY.read_bytes()
    registry = json.loads(registry_raw)
    current, proposals, canonical = protection.fetch_canonical(registry)
    original = copy.deepcopy(registry['selected_survivors'])
    registry['selected_survivors'] = protection.reconcile_survivors(
        registry, current, proposals, canonical)
    if prospective_policy:
        # This flag describes the already explicit PO policy in a Phase A
        # simulation; it never changes canonical execution authority.
        canonical['standing_policy'] = json.loads((protection.ROOT /
            'state/candidate_lifecycle_retention_policy_v1.json').read_bytes())
    packages = protection.scan_local(registry, base)
    audit = protection.resolve(registry, current, proposals, packages,
                               free_bytes=shutil.disk_usage(base).free,
                               canonical=canonical, for_deletion=True)
    if catalog.read_bytes() != before or protection.REGISTRY.read_bytes() != registry_raw:
        raise ValueError('read-only inputs changed during dry-run')
    return {'artifact_type': 'integra.retention_repair_dry_run',
            'execution_authority': 'NONE_DRY_RUN',
            'prospective_policy': prospective_policy,
            'canonical_main': canonical['main_sha'], 'current_id': current['current_id'],
            'catalog_sha256_before': protection.sha(before),
            'catalog_sha256_after': protection.sha(catalog.read_bytes()),
            'obsolete_selectors': sorted(set(original) - set(registry['selected_survivors'])),
            'selected_survivors': registry['selected_survivors'],
            'audit': audit,
            'next_build': {
                'eligible_terminal_archives': [row['candidate_id'] for row in audit['entries']
                    if row['standing_retirement_eligible']],
                'requires_canonical_reconciliation': original != registry['selected_survivors'],
                'requested_bytes': 2516582400,
                'admission_proven': False,
                'reason': 'READ_ONLY_NOT_A_CAPACITY_RESERVATION'},
            'real_retirements': 0, 'payload_mutations': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prospective-policy', action='store_true')
    args = parser.parse_args()
    result = report(prospective_policy=args.prospective_policy)
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0 if result['audit']['authority_state'] == 'COMPLETE' else 2


if __name__ == '__main__':
    raise SystemExit(main())
