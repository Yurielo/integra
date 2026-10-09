# Issue #228 — Phase B canonical bookkeeping

Phase A is canonical through PR #229, merge
`0d20f17068e082ab0dbbc1f923d5a950013a01fa`. Its exact push-to-main Quality Gate
passed: run `37918770797`. This separate Phase B change applies only the
deterministic survivor reconciliation; it contains no product/runtime change.

## Fresh read-only capture

The repaired resolver was executed again against canonical main, current
GitHub Proposals, all eight physical copies and the ownership catalog, without
the prospective-policy flag. The full local capture is
`/tmp/integra-228-phase-b-before.json`, SHA-256
`5d422cbfc0796b716b322287703359b45a6917e622a122ef0aa42488746c9221`.
Authority after in-memory selector reconciliation is COMPLETE with zero
blockers. Ownership catalog SHA-256 before and after remains
`8115cc0ed8ecb545588ab5567a21f47222ad00c2066c5bda6ec9773a28bd3c15`.

The derived protected domain no longer contains
`candidate-v1-5f6384c8d68c96cc84432e3c72039ef1cdb0642f6399c6d5df60387774a7ed1e`.
Its stale selector is the **only** difference produced by
`candidate_protection_audit.reconcile_survivors`. Removing this extra selector
does not choose a new rollback/recovery, withdraw acceptance, or dispose of
any pending Candidate. All other registry fields remain byte-semantically
identical. CURRENT `675acf…`, immediate rollback `15d9…`, accepted-unpromoted
`82ba…`, active Proposal bindings and historical-gap obligations are preserved.

All eight copies remain present at this commit. Only `5f6384…` satisfies every
standing retirement predicate in the fresh dry-run. The absolute holds
`721d…`, `073396…`, `97be…`, `14b3…` remain ineligible. The known integrity
incident and UNKNOWN ownership are neither repaired nor adopted.

## Authorized post-merge execution

Physical retirement is **not executed by this commit**. After this bookkeeping
is canonical and its Quality Gate passes, the existing maintenance entry point
must refresh protection/catalog lifecycle, select eligible terminal archives
deterministically, recheck all predicates and persist durable receipts before
withdrawal. No Candidate-specific manual deletion selection is permitted.

Completion additionally requires CURRENT_VALID, consistent survivors/catalog,
truthful capacity and receipts, all four holds intact, and actual normal K2
capacity reservation followed by release **without invoking a builder**.
Until those real checks finish, this document does not claim admission or
completed retirement. Issue #228 execution evidence records their result.

K1 remains DONE; K2 remains frozen/in progress. Process Board remains
41 DONE / 3 NOT_DONE / 1 BLOCKED. No repair Candidate is necessary under the
canonical GOVERNANCE_ONLY_CHANGE release contract.
