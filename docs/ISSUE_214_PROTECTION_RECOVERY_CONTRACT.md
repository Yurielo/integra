# Candidate protection and historical recovery gap — Issue #214

Status: PRODUCT_OWNER_ACCEPTED_PENDING_INTEGRATION. This contract does not promote a Candidate, change
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
not active merely because this PR exists or its CI passes. The exact Product
Owner decision is recorded at Issue #214 comment 5951189263 and its token hash
is bound in the registry. It accepts `explicit_governance_pins={}` and
`deletion_authorizations={}` while retaining every UNKNOWN artifact.
The existing PR #213 lifecycle policy remains the cap/cleanup executor contract.
Its owned catalog is ownership and transaction evidence only. The registry is
the sole positive protection and deletion authority. The registry's
`promotion_contract_integration_ref` remains null while activation is pending;
a standalone resolver PASS cannot authorize promotion.

The existing promotion helper now requires a fresh canonical registry gate in
addition to its old proposal, acceptance, exact archive and output checks.
The low-level archive publisher requires the same gate before creating a new
managed full copy. `candidate_protection_gate.require_deletion` refuses a target
without exact path/identity grant and fresh ELIGIBLE classification. The
Issue #212 owned cleanup journal and lifecycle deletion path are adapted into
this PR. Planning, package withdrawal and resumed transactions require the
canonical gate. The journal binds the registry digest, grant, identity and
canonical GitHub snapshot. Drift stops recovery. The catalog mirror is derived
from verified registry survivors, not the old policy snapshot. It remains
dormant while the real registry has no grants and incomplete recovery evidence.
Cleanup may reduce an over-cap archive or restore a disk reserve; those two
capacity conditions block new publication, not exact owner-granted deletion.

The local ownership catalog remains evidence of who may *possibly* delete a
package. It is never protection authority. A package can be ELIGIBLE only when
the registry is owner-authorized and complete, all protected survivors have
fresh complete byte verification, the exact package has a path and identity-bound
deletion grant, is publisher-owned, terminal, inactive, unpinned, and the
established cleanup transaction passes. This PR contains no deletion grant.
The accepted decision also keeps `deletion_enabled=false`; even a forged grant
cannot yield ELIGIBLE. A future decision would have to bind an exact grant map
digest and explicitly set `DELETION_ENABLED=true` in its owner token.
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

If exact bytes cannot be found, the accepted historical status is
`MISSING_WITH_AVAILABLE_EVIDENCE`; no new archive or receipt may be
fabricated. The machine-readable `bootstrap_plan` records the old CURRENT/rollback gap, all
UNKNOWN copies, the proposed next Candidate, and the remaining physical
headroom. It does not turn the old baseline into a recovered one or write a
successor CURRENT. Any transition that deliberately accepts a recovery gap
requires a separate exact Product Owner promotion decision and a new governed promotion
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

PR #213 and its accepted proposal remain unchanged. The transferred executor
is independently reviewable in PR #215; no real cleanup, publication, promotion
or CURRENT change occurred. Both PRs remain unmerged.
