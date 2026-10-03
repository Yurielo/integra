# Candidate protection and historical recovery gap — Issue #214

Status: PRODUCT_OWNER_AUTHORIZED_ACTIVE in PR #215. The original #214 decision
did not authorize historical deletion; the later exact six-object decision is
recorded below. Neither decision promotes a Candidate, changes CURRENT, or
makes PR #213's accepted proposal a new baseline.

## Single authority root

`state/candidate_protection_registry_v1.json` is the proposed machine-readable
root for protection decisions. It binds the SHA-256 of the canonical `main`
CURRENT record, exact Candidate identity tuples, every open proposal head
(including PR #213), explicit provenance pins, and selected rollback/recovery
roles. The resolver enumerates all open PR proposals and blocks on unregistered
proposals or head drift. It must re-read GitHub/main and PR-head bytes; it may not
trust a filename, local catalog entry, historical receipt, or unmerged policy
file alone. A changed reference, missing pin enumeration, missing selected
archive, conflicting identity, or incomplete registry returns BLOCKED. A null
selected-survivor value expressly claims no verified archive; it never means
that a Candidate was recovered or may be deleted. The exact Product
Owner decision is recorded at Issue #214 comment 5951189263 and its token hash
is bound in the registry. It accepts `explicit_governance_pins={}` and
`deletion_authorizations={}` while retaining every UNKNOWN artifact.
The existing PR #213 lifecycle policy remains the cap/cleanup executor contract.
Its owned catalog is ownership and transaction evidence only. The registry is
the sole positive protection and deletion authority. Activation binds the
accepted Issue #214 decision and draft PR #215 integration. This unmerged
branch state grants neither promotion nor deletion.

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
dormant while the real registry has no grants.
Cleanup may reduce an over-cap archive or restore a disk reserve; those two
capacity conditions block new publication, not exact owner-granted deletion.

The local ownership catalog remains evidence of who may *possibly* delete a
package. It is never protection authority. A package can be ELIGIBLE only when
the registry is owner-authorized and complete, all protected survivors have
fresh complete byte verification, the exact package has a path and identity-bound
deletion grant, is publisher-owned, terminal, inactive, unpinned, and the
established cleanup transaction passes. The automatic executor has no deletion
grant. The original accepted decision keeps `deletion_enabled=false`; even a forged grant
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

The accepted historical status is `MISSING_WITH_AVAILABLE_EVIDENCE`; no new
archive or receipt may be fabricated. `recovery_selection` explicitly records
`NO_VERIFIED_ARCHIVE_ACCEPTED_HISTORICAL_GAP` with `archive_path: null`.
CURRENT and rollback Candidate identities remain protected, without a claim
that their archive bytes survive. Other open proposals without selected
archives remain protected by identity. PR #213 retains its byte-verified
selected archive. The machine-readable `bootstrap_plan` records the old CURRENT/rollback gap, all
UNKNOWN copies, the proposed next Candidate, and the remaining physical
headroom. It does not turn the old baseline into a recovered one or write a
successor CURRENT. Any transition that deliberately accepts a recovery gap
requires a separate exact Product Owner promotion decision and a new governed promotion
contract; the existing promotion helper continues to require both exact
archives. Protection authority may be COMPLETE while promotion remains blocked
by the missing outgoing CURRENT archive and the separate owner promotion gate.

## Historical roles and the exact Excel #7 successor

`historical_gaps.role` means role at the time of the original #214 decision.
The validator resolves that decision's exact identities through its unchanged
token, immutable CURRENT records and receipts. Moving CURRENT to `5f6384…`
does not transfer an archive gap to that Candidate. `af81…` remains a protected
historical gap even after it is no longer the nearest predecessor.
The original `recovery_selection` remains historical truth; it is not a claim
that the active CURRENT was lost or physically recovered.

The separately authorized exact Excel #7 transaction preserves #213 and every
unrelated open Proposal, appends CURRENT, retires the exact #7 Proposal, and
records the exact authorization/result. Its missing outgoing `d8bd…` has
`restorable_from_retained_archive=false` and `rollback_eligible=false`.
Physical availability, accepted historical identity and runtime executability
are independent facts. Deletion grants remain empty and deletion disabled.

## Non-destructive verification

The Issue #214 resolver reads records and hashes only selected protected
archives. It never imports legacy ownership or performs cleanup. It emits
PROTECTED, UNKNOWN and ELIGIBLE classifications with explicit reasons and
bytes charged once per physical inode. A missing or incomplete authority
cannot produce ELIGIBLE. Candidate archive verification is the existing
`scripts/candidate_archive.py` verifier; a receipt without its package is not
byte evidence. Interruption before an immutable COMPLETE publication leaves
no qualifying archive. A missing selected survivor blocks authority; an
explicitly null historical-gap selector stays protected without claiming a
surviving archive.

PR #213 and its accepted proposal remain unchanged. The transferred executor
is independently reviewable in PR #215; no real cleanup, publication, promotion
or CURRENT change occurred. Both PRs remain unmerged.

## Exact six-object historical retirement decision (2026-10-02)

The Product Owner subsequently authorized retirement of the six exact historical
full-size app copies bound by catalog SHA-256
`f146bfb1c3ed397275071528ee1aa0945dbde75a0b1669357051c3a6136e2c76`
in Issue #214 comment `5957484872`. This is a narrow additional decision, not
a change to the earlier missing CURRENT/rollback recovery finding. The
canonical registry binds the decision and the exact catalog; its automatic
publisher-owned deletion grants remain `{}` and `deletion_enabled=false`.
Only `scripts/issue214_exact_legacy_retirement.py` interprets the separately
authorized `EXACT_CATALOG_ONLY` mode. It requires fresh canonical protection,
the original Product Owner decision, the new exact decision, byte-verified
Candidate identity, an inactive app, matching allocation, no hard links or
foreign files, and a durable per-entry journal. Two loose app copies are also
checked against their retained COMPLETE twins before any removal. It removes
only each authorized `Integra.app` child; surrounding proof, receipt, manifest,
inventory, and evidence files remain. An interruption resumes only against the
same registry/catalog and exact inode/entry journal. All other UNKNOWN objects
remain RETAIN_FAIL_CLOSED. No transition, CURRENT change, promotion or PR merge
is implied by this retirement decision.

Once the six payloads are journaled as removed, `--finalize-paths` verifies
that only metadata remains at every exact catalog path. It atomically renames
each metadata root to `Historical Retirement Evidence/issue214-<catalog SHA>/`
with the original relative path, then checks inode and full metadata inventory
SHA-256. A separate durable journal resumes an interrupted rename. The six
original catalog paths disappear while receipt, manifest, inventory and proof
bytes remain preserved, with no new full-size app copy.
