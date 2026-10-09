# Issue #228 — Phase A mechanism proof

Authority: the Product Owner instruction of 2026-10-09, bound by SHA-256
`803ca32ffe5629f919e60cdee5661005463f71d793de3b3f2ef636a9ce1e513d`.
Starting canonical main: `b5aedfc8ff3b7c8bfff7e09f892eed0ca9130371`.
Delivery class: `GOVERNANCE_ONLY_CHANGE`, derived using the current
`scripts/proposed_baseline_lite.py::_governed_product_path` contract. No changed
file is a packaged product path. No repair Candidate was built.

## Executed proofs

- Independent focused QA: **45 tests PASS**, zero failures/skips. This covers
  all 36 requested matrix cases, missing-canonical-protection admission, three
  real rollover tests and five native admission/import tests.
- Existing lifecycle regression: **7 tests PASS**. The missing-authority test
  now checks the earlier fail-closed authority error, still proving both
  archives survive; no cap or guard was weakened.
- Pinned machine Evidence integration: **9 tests PASS**, with synthetic source
  content and the unchanged exact SeminarText pin.
- Governance and agent-team validators: **PASS**, `CURRENT_VALID`.
- Independent diff/scope review: no remaining blocking finding.
- Full supported suite: **1069 passed, 53 skipped**, zero failures/errors.
  All 1122 unique test IDs were collected once and run through the same guarded
  review launcher in three exhaustive partitions (398/298/426). Each partition
  passed. The exact 53 skipped test IDs and reasons match the canonical-main
  comparison in the same environment; skip policy was not changed. GitHub CI
  retains its normal monolithic full-suite command. Local pinned checkouts and
  the existing hash-verified review dependency cache are ignored test setup,
  not packaged or modified source/runtime material.

The primary A→B→C proof uses real archive publication, resolver, survivor
derivation, catalog replay, maintenance, retirement receipts, capacity
reservation, generic promotion `apply()`, local bare Git push, and real
detached-checkout `validate_post()`. Only the external GitHub transport, host
paths and free-space probe are isolated. Governance gates are not mocked.
Initial copies: 8; before B: 7; before C: 8; after C admission: 7.
Three durable retirements occurred **only inside isolated fixtures**; there
were zero Candidate-specific deletion grants. The promotion/cleanup race test
also proves cleanup waits for the common catalog lock during real apply and
post-validation.

## Real-state read-only dry-run

`ISSUE_228_PHASE_A_DRY_RUN.json` records all eight physical copies, exact
Candidate/bundle/manifest identities, canonical roles, local catalog and
reconciled lifecycle, ownership, integrity and every eligibility reason.
The policy and survivor correction were simulated in memory, not activated
from the feature branch. Authority after that simulation is COMPLETE, with no
blockers. Catalog SHA-256 before and after is identical:
`8115cc0ed8ecb545588ab5567a21f47222ad00c2066c5bda6ec9773a28bd3c15`.

Only the obsolete `5f6384…` selector is removed prospectively. Its exact
promoted lineage is terminal, owned and verified, so it is the sole standing
retirement-eligible archive. CURRENT `675acf…`, rollback `15d9…`, and
accepted-unpromoted `82ba…` stay protected. `721d…`, `073396…`, `97be…`,
and `14b3…` remain absolute holds. The known `073396…` cache contamination is
not repaired, adopted or hidden; `97be…` ownership is not inferred.

Physical copies: 8. Package allocation: 18238939136 bytes. Prospective eligible
allocation: 2280747008 bytes. Exact caps remain 8 copies, 21474836480 bytes and
16106127360 bytes free after reservations. Normal requested archive headroom is
2516582400 bytes. The predicted next build first needs canonical selector
reconciliation and fresh standing-policy maintenance. **Admission is not yet
proven**: this Phase A dry-run does not reserve capacity or delete anything.

## Protected boundaries

Real retirements/payload mutations during Phase A: **0**. CURRENT file digest
remains `bdd2ea30b3102c59cd8e47bc56a0d53c6b57d3bfb0347e667663b1be951e52e2`.
K2 tracked diff digest remains
`4b1772a1a552b93df013144dc48cfa83c83a6b283859c251889ff3f147cc3a6f`;
all nine new K2 files retain their original digests. No source-project changes,
runtime/model changes, K2 build, acceptance/promotion or Product Outcome
transition occurred. Process Board remains **41 DONE / 3 NOT_DONE / 1 BLOCKED**.

Phase B must start from fresh canonical authority after the Phase A PR is
merged and verified. It is not part of this implementation commit.
