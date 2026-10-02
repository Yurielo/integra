# Candidate protection and historical recovery gap — Issue #214

Status: PROPOSED_INCOMPLETE. This contract does not promote a Candidate, change
CURRENT, authorize historical deletion, or make PR #213's accepted proposal a
new baseline.

## Single authority root

`state/candidate_protection_registry_v1.json` is the proposed machine-readable
root for protection decisions. It binds the SHA-256 of the canonical `main`
CURRENT record, exact Candidate identity tuples, every open proposal head
(including PR #213), explicit provenance pins, and selected rollback/recovery
roles. The resolver enumerates all open PR proposals and blocks on unregistered
proposals or head drift. It must re-read GitHub/main and PR-head bytes; it may not
trust a filename, local catalog entry, historical receipt, or unmerged policy
file alone. A changed reference, missing pin enumeration, missing archive,
conflicting identity, or incomplete registry returns BLOCKED. The registry is
not active merely because this PR exists or its CI passes.
The existing PR #213 lifecycle policy remains the cap/cleanup executor contract.
Before any later promotion can use this registry, a separately verified
integration must make its promotion helper consume this authority and reconcile
its policy's explicit pins with the registry. The registry's
`promotion_contract_integration_ref` is null until that happens; a standalone
resolver PASS cannot authorize promotion or create a second active authority.

The local ownership catalog remains evidence of who may *possibly* delete a
package. It is never protection authority. A package can be ELIGIBLE only when
the registry is owner-authorized and complete, all protected survivors have
fresh complete byte verification, the exact package has a path and identity-bound
deletion grant, is publisher-owned, terminal, inactive, unpinned, and the
established cleanup transaction passes. This PR contains no deletion grant.
Unknown historical objects remain UNKNOWN even if a cap is full. A matching
identity without a byte-verified selected survivor remains unverified.

## Recovery gap and bootstrap

The accepted CURRENT `d8bd6f…` and immediate accepted predecessor `af81b2…`
have historical COMPLETE receipts, but the actual archive paths are absent.
The two available installed/runtime apps have different bundle digests and no
embedded Candidate manifest. There is no proof that either app is the outgoing
CURRENT. The verified PR #213 Candidate `82ba92…` shares a bundle digest with
CURRENT but has a different Candidate ID and manifest; it is not a replacement
for the missing CURRENT archive.

A recovery archive may be created only from an exact source app with matching
embedded manifest, Candidate ID, bundle digest, canonical historical manifest
SHA-256 and the historical receipt's full-byte inventory digest. The read-only
`verify_exact_recovery_source` preflight recomputes that digest, including bytes
excluded from the bundle tree such as `.pyc`. Creation must be immutable,
no-replace, under both archive caps and the disk reserve, and must not prune
existing packages. On this Mac, that operation is BLOCKED because no exact
source is established and all eight full-copy slots are occupied.

If exact bytes cannot be found, the historical status is
`MISSING_HISTORICAL_RECOVERY_ARTIFACT`; no new archive or receipt may be
fabricated. The machine-readable `bootstrap_plan` records the old CURRENT/rollback gap, all
UNKNOWN copies, the proposed next Candidate, and the remaining physical
headroom. It does not turn the old baseline into a recovered one or write a
successor CURRENT. Any transition that deliberately accepts a recovery gap
requires a separate exact Product Owner decision and a new governed promotion
contract; the existing promotion helper continues to require both exact
archives.

## Non-destructive verification

The Issue #214 resolver reads records and hashes only selected protected
archives. It never imports legacy ownership or performs cleanup. It emits
PROTECTED, UNKNOWN and ELIGIBLE classifications with explicit reasons and
bytes charged once per physical inode. A missing or incomplete authority
cannot produce ELIGIBLE. Candidate archive verification is the existing
`scripts/candidate_archive.py` verifier; a receipt without its package is not
byte evidence. Interruption before an immutable COMPLETE publication leaves
no qualifying archive, and subsequent dry-run remains BLOCKED.

The Issue #212 retention implementation remains in PR #213. This separate PR
does not edit PR #213, its accepted proposal, or its Quality Gate. Integration
with the lifecycle executor is a later governed step after both PRs and
authority decisions are resolved; the resolver's output is deliberately not
a deletion command.
