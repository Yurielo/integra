# Bounded Candidate retention — Issue #212

The later direct Product Owner capacity-rotation amendment is documented in
`CANDIDATE_RETENTION.md` and `state/candidate_archive_rotation_policy_v2.json`.
At a full eight-copy archive, its oldest-first rule supersedes this document's
terminal-only eviction predicate for capacity admission. This Issue #212 text
remains historical; all byte-integrity, journaling, installed-application and
honest physical-availability requirements remain in force.

Status: PRODUCT_OWNER_AUTHORIZED, Issue #212 carries the reusable PR #206 implementation plus automatic maintenance.
Authority: [Product Owner decision](https://github.com/Yurielo/integra/issues/205#issuecomment-5917563905).
Machine policy: `state/candidate_retention_policy_v1.json`.

This decision supersedes indefinite full-artifact retention in the earlier
Candidate retention contract. Historical acceptance and provenance records
remain unchanged. A historically accepted Candidate is not protected forever
solely because it was once CURRENT. Explicit active governance requirements
remain protected until their own authority resolves them.

Both limits are mandatory: at most **8 full copies** and **20 GiB attributed
allocation** across the registered managed archive roots. Allocation is charged
once by device/inode; APFS shared extents are not treated as proven savings.
Before a full build, at least **15 GiB free** must remain after all planned
build/copy and live concurrent reservations. Failure blocks the build before
spawning it. A cleanup attempt may select only confirmed owned, inactive,
terminal, unreferenced artifacts; it cannot evict protection to admit a build.

Protected identities are CURRENT, the latest accepted baseline, one confirmed
rollback, one confirmed recovery, every active owner-acceptance Candidate and
explicit active governance/provenance pins. CURRENT and latest accepted
baseline sharing an identity use one archive. Confirmed rollback/recovery
require evidence references and actual retained bytes. Missing or ambiguous
protection context blocks cleanup. New publications default to review pending;
a terminal disposition requires a recorded authority reference. No N/TTL or
implicit acceptance decision beyond the owner instruction is invented.

The catalog binds publisher ownership to exact path, UID, device/inode,
Candidate/bundle/manifest and COMPLETE/inventory hashes. Arbitrary current-user
directories and metadata-only manifests never prove ownership. Roots are
explicitly registered, never discovered for deletion by global tmp masks.
Foreign, active, unknown, worktree, symlink, hardlinked and mismatched artifacts
fail closed. Deletion freshly verifies bytes and rechecks catalog/protection
and filesystem identities under the common catalog lock.

The later v2 capacity-rotation path has one narrow exception to the ordinary
publisher-ownership predicate: a completed pre-timestamp archive whose
current device differs from its catalog record may use the currently recorded
sequence as observed-now order evidence only when its exact receipt, inventory,
identity, UID, inode and full bytes verify. It remains `publisher_owned=false`;
the original device and record are retained separately in a conflicting-record
retirement receipt. See `CANDIDATE_RETENTION.md` (Issue #310). Ordinary terminal
cleanup and historical ownership adoption still fail closed on device drift.

After successful authorized promotion, the post-promotion retention command
reconciles protected identities and reevaluates terminal copies. Owned
temporary output uses the existing common supervised lifecycle on normal
completion, failure, SIGINT, SIGTERM, interruption, crash and stale recovery.
Identical Candidate archives are reused rather than copied without reason.

## Historical migration boundary

Existing Build Archive, retained, Recovery Archive, Build Archive Recovery and
Candidate Builds must first be inventoried. Two stale inventories and unknown
artifacts require forensic classification. Altered original archives are
quarantined in the plan; existing independently verified recovery copies are
recovery evidence, not an automatic CURRENT or canonical-path switch.

The initial migration is **dry-run only**. Existing immutable packages are not
repaired, rewritten or deleted. Legacy publisher ownership must be attested
for exact paths and evidence before those objects become automatically owned.
The historical bulk plan requires a separate Human Gate and an exact plan
digest. It reports BEFORE_BYTES, PROTECTED_BYTES, DELETABLE_BYTES, UNKNOWN_BYTES,
EXPECTED_AFTER_BYTES and EXPECTED_FREE_SPACE. Unknown/protected bytes are never
subtracted as savings; expected APFS reclaim is an estimate, not a guarantee.

CLI `plan` is read-only. `cleanup` applies only newly owned eligible artifacts;
it never implicitly imports historical ownership. Historical authorization and
ownership adoption are distinct from policy acceptance. `post-promotion` is
invoked only after actual promotion, not when a helper merely prepares output.
The v2 physical-copy capacity rotation does not import historical publisher
ownership; it uses its own exact Owner policy and observed-now receipt.

The policy does not accept PR #206's Candidate, promote CURRENT, permit a
substitute build, change source products or bypass Quality Gate. If fresh
Candidate evidence is blocked by the new reserve or archive caps, the PR stays
unmerged at that explicit gate while implementation and dry-run proceed.

## Cleanup transaction and crash recovery

One immutable package is the deletion transaction unit. Immediately before
withdrawing its original path, the executor requires a fresh exhaustive GitHub
snapshot (exact main CURRENT and every open PR head/proposal), an explicit
canonical registry of active provenance pins, all selected protected survivors,
fresh full verification of those survivors and the terminal package, publisher
ownership, and an inactive filesystem snapshot. Missing pins or role selectors
block cleanup. Required Candidate/bundle/manifest tuples cannot be collapsed to
one survivor if they conflict.

A durable PREPARED journal records the exact identity, publisher attestation,
complete inventory, filesystem identities and authorization context. Atomic
no-replace rename withdraws the package into its own journaled trash path. The
original retained path is then unavailable to promotion's archive verifier;
trash is not promotion material. The same package transaction performs bounded
fd-relative deletion with file type, mode, link count, size, timestamp and
inode/UID checks. The catalog lock covers the whole operation. A new Candidate
or disposition is not selected at each individual file unlink.

The journal is committed before destructive operations, including on exception
paths. Recovery starts a new authorization transaction: fresh canonical
protection, protected-survivor verification and hashes of every remaining file
are required, including a PREPARED journal interrupted just after rename.
Foreign additions, replaced files, changed payloads, new protection, missing
context or active consumers preserve the remaining bytes. Completed package
checkpoints persist even if a later package fails. `recover` resumes only exact
catalog-owned journals; ordinary plans charge remaining trash allocation.
There is no scheduled global sweeper and no historical ownership import.

New full builds use a shared user catalog across all registered roots/volumes
and an atomic volume reservation before invoking the native builder. Direct
builder calls require that live admission lease. On build failure/interruption,
peak/slot reservations remain charged until the existing common supervisor
terminates owned descendants and removes the workspace; subsequent admission
reaps only proven stale journaled state. A publication crash is ownership-
recoverable only when the destination inode matches the prepublication stage
journal and the entire published archive freshly verifies. No-replace collisions
remain foreign and cannot become owned artifacts.


## Issue #212 execution and diagnostics

Before a full build or standalone archive copy, maintenance resumes eligible
journaled cleanup and reevaluates publisher-owned terminal copies. The atomic
admission guard rechecks count, charged bytes and live reservations afterwards;
a racing build cannot use a stale free slot. Successful publication is immutable
and closes its writer lease. It starts review-pending, never implicitly accepted.

After a canonical promotion, the next workflow automatically refreshes the
existing confirmed role context from exact canonical CURRENT and all open PRs,
selects the exact new current/rollback tuples and retires newly superseded owned
copies. It preserves recovery, pending acceptance and explicit provenance pins.
The local checkout CURRENT must already equal canonical main.
Ambiguous survivors, stale local CURRENT, absent pin authority or unavailable
GitHub prevent cleanup. Initial role confirmation still uses `post-promotion`
with exact selected archives/recovery authority. That command is not product
promotion. The promotion preparation helper only writes a proposed output and
cannot run cleanup as if canonical promotion had happened.

All supported full builds go through `build_macos_candidate.py`; raw builder
calls require the live admission lease and a fresh child of its owned workspace.
`test_macos_app.sh` uses the same supervisor/admission. `package_ready_app.sh`
is a low-level packaging child; use `python3 scripts/build_macos_candidate.py
--package-tests` for supervised disposable signing/self-test validation. It does
not claim a retained Candidate identity after signing. Arbitrary output roots cannot bypass the guard. Legacy unmarked tmp
paths are diagnosed but never adopted or globally swept. Startup stale reaping
is restricted to its exact base; archive-stage recovery uses exact journal paths.

Events are JSON lines on stderr (`integra.lifecycle_event`), including creation,
protection reasons, cleanup attempt/completion/failure/skips and headroom
rejection. No forever-growing lifecycle log is created in Build Archive or tmp.
Cleanup reports attributed allocation separately from observed df/free change;
neither is asserted as exclusive APFS reclaim. Empty owned Candidate containers
are removed without recursion; foreign/nonempty parents stay, including recovery
from a crash after the last payload unlink.

Immutable asset deduplication: identical package reuse is implemented. Hard links
would couple independently immutable candidates and violate archive integrity.
External content-addressed models would compromise self-contained recovery and
portability. APFS cloning may share extents, but st_blocks does not prove exclusive
reclaim and signing/inventory semantics must remain exact. No fragile model-store
or clone optimization is introduced by #212; both caps charge conservatively.

Controlled E2E uses twelve successive synthetic fresh bundle publications and
fixture canonical promotions through real admission, exact archive verification,
role reconciliation and cleanup. Test-only canonical API/activity adapters and a simulated 64-GiB
free-space probe are explicit; no production CLI bypass is added. Six copies maximum during cycles,
five protected survivors after each, and zero owned tmp roots between cycles
are checked. Native binary/runtime validation is separate evidence, never implied
by synthetic payloads. Real protected archives and real CURRENT are not test targets.
