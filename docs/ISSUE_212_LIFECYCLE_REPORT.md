# Issue #212 — bounded build/archive/TMP lifecycle evidence

Scope: https://github.com/Yurielo/integra/issues/212 only. Source A:
`74785b5f34cb12e1cd557b34731bffbe191cbe15`, tree
`c86f8451b1ca49372e12885fa752a4962b15ef80`. Independent QA/review is in
`docs/evidence/issue212/integra-212-independent-review.md`.

## Implemented policy and mechanics

Both limits apply simultaneously: **8 full copies**, **20 GiB attributed
allocated bytes** across managed archive roots, and **15 GiB free after planned
peak space plus live volume reservations**. Existing unknown bytes and copies
are charged, never treated as free slots. Device/inode accounting avoids counting
a nested root or physical inode twice; APFS shared extents are not asserted to
be exclusive reclaimable space.

Protected: CURRENT/latest accepted baseline, one confirmed rollback, one
confirmed recovery, pending Product Owner acceptance and explicit active
provenance/governance requirements. Automatic selection requires exact publisher
ownership, a terminal disposition (completed/rejected/superseded/unused), fresh
canonical authority, full byte verification and inactive consumers. Active,
foreign, unknown, mismatched and symlink/hardlink objects fail closed. New
publications default to pending acceptance. No historical ownership adoption or
bulk cleanup is performed by this delivery.

Before build/copy, automatic maintenance reevaluates eligible owned terminal
artifacts and recovers authorized journals, then atomic admission rechecks limits.
After actual promotion, an already confirmed role context is refreshed from
canonical CURRENT/open PRs and protected survivors. It does not promote or accept
products. Cleanup requires a complete canonical pin registry and confirmed role
selectors. Production pins remain unresolved; absent authority preserves bytes
and admission may reject further copies. This restriction is explicit, not a
claim that legacy automatic deletion is enabled.

Raw builders require a live shared reservation and fresh output beneath an owned
workspace. Candidate/native-test/package workflows share the detached supervisor;
normal completion, failure, SIGINT, SIGTERM, parent crash, timeout and exact-base
stale recovery are bounded. No global `/private/tmp/integra*` deletion is used.
Archive publication is immutable and journaled; interrupted deletion reauthorizes
and verifies remaining bytes before resuming. Only exact empty owned Candidate
containers are removed. Diagnostics are JSON stderr events, avoiding another
unbounded archived log. Reported allocation and observed free-space delta are
separate values.

Exact Candidate/bundle/manifest/inventory reuse avoids redundant archives.
Heavyweight asset deduplication was investigated: no hard links, compulsory
external model store or unproven APFS reclaim optimization is introduced; integrity,
portability, signing and self-contained recovery remain intact.

## Automated and controlled E2E validation

Focused: **98 PASS** (3 disk admission, 28 archive, 24 retention, 16 governance,
15 TMP lifecycle, 5 native admission, 7 Issue #212). Raw logs and machine results
are in `docs/evidence/issue212/`. Actual macOS `lsof` exclusion is exercised.
Interruption, crash recovery, active workspaces, low disk, concurrent reservations,
foreign collisions, payload tampering and idempotent retry are covered.

Twelve controlled filesystem build/publication and fixture-promotion cycles run
real admission, ownership, inventory, archive verification, role reconciliation
and cleanup. The payload and canonical API/activity adapter are synthetic; the
64-GiB free-space probe is simulated. This is not native/product acceptance.

| Measurement | Result |
| --- | ---: |
| Initial fixture copies / bytes | 4 / 16,891,904 |
| Maximum copies during a cycle | 6 |
| Copies after each of 12 cycles | 5 |
| Allocated bytes after each cycle | 21,114,880 |
| Owned TMP roots after each cycle | 0 |
| Idempotent second cleanup deletions | 0 |

Retained fixture identities and reasons are in the controlled E2E JSON: CURRENT
and latest accepted baseline share a copy, plus rollback, recovery, pending
acceptance and explicit provenance pin. Protected receipt identities survive.
All fixture objects are isolated from the user's real archives.

## Actual native validation

Four successful admitted workflows used fresh owned paths and pinned clean
SeminarText/VideoText inputs fetched into owned workspaces; BookText was read only.
Hash-locked review wheels were downloaded into the owned input workspace. The
word-alignment dependency tree was read from retained65 and freshly matched its
manifest digest `66d2ad50eac6194b8808b0316d37bdb64d69d27560847a671cc0f593119ac0c7`.
No protected archive was written or repaired.

1. Native build + manifest validation + immutable archive publication/full byte
   verification: PASS, 151.42 seconds.
2. Native disposable rebuild + manifest validation: PASS, 104.86 seconds. Its
   entire manifest equals run 1; no second archive is retained.
3. Disposable READY_APP packaging: PASS, 110.25 seconds. Existing helper performs
   ad-hoc codesign, deep/strict verification and self-test. Post-signing bytes are
   explicitly not claimed as the retained Candidate identity.
4. Existing native tests: PASS, 143.56 seconds: Finder/Dock icon, launch/close,
   bundled SeminarText/word-timeline/BookText preflight, real fixture VideoText
   workflow, active-run shutdown/quit, stale reconciliation, verified ASR retry,
   stable operations and real cancellation. Input data and GUI probe output are
   isolated, no live external publication.

Every run reports zero remaining owned TMP roots; both outer input workspaces and
bases were removed. Failed dirty-input/missing-wheel attempts were also cleaned.
One deliberately cancelled stalled Documents dependency copy confirms actual
SIGTERM cleanup (exit 128 is recorded as cancellation, never counted as PASS).

The sole retained new review Candidate is:
`candidate-v1-82ba92224a7dcdc0f1738155ba2e3f73dbdfc529ce2a8ffc461be73fa1351f29`.
Bundle `fedc5481c20a8829f92fd6f6579e53197b1495bd960c238efe9fdd14c2cb5582`;
manifest `667539142be8f7909dc56acb60be1e1fa30c05c6cec44ab931f32fcc8dd36c39`.
Its source is clean A. The bundle digest equals the accepted runtime's existing
bundle digest; this is a workflow change with unchanged packaged runtime bytes.
Actual archive path/receipt is recorded in `candidate-evidence.json`; it is in a
new `~/Library/Application Support/Integra/Validation/integra-212-native-35e6f9101278`
root, preserved pending owner review. Logical app size: 2,201,629,355 bytes;
charged allocation: 2,280,722,432 bytes.

The actual shared catalog observes 7 pre-existing full copies plus this one:
**8 copies / 18,278,240,256 charged bytes**. A ninth archive build is rejected
before workspace materialization. Deletion records and historical adoptions
remain empty. Legacy 15,997,517,824 bytes stay UNKNOWN/unowned for cleanup; the new
pending review copy is protected. Canonical cleanup authority remains unavailable,
so no real historical deletion is inferred from fixture success.

## Preservation, governance and boundaries

Protected retained/recovery/candidate trees and CURRENT/accepted governance JSON
were compared before/after all native runs. **162,377 entries unchanged**, with
identical device/inode/size/mode/mtime/ctime digest and matching governance JSON
SHA-256. No added/missing/changed entries. This is full metadata invariance, not a
fresh rehash of every legacy multi-GiB payload; the readonly runtime subset was
separately hashed. See `integra-212-protected-preservation.json`.

Only development lifecycle tooling, related tests, policy docs, evidence and a
new Proposed Baseline declaration change. Source-product repositories, product
code, real CURRENT, immutable acceptance/history, Quality Gate code and historical
certification tests remain unchanged. PR #206 is OPEN at `02150c9…`; its reusable
lifecycle implementation is carried here without its forensic records/proposal.
No changes are made to Issue #205 or PR #206.

The initial full suite exposed three expected immutable-governance hash failures
because the builder/test entrypoint now differ from CURRENT/R12. Their assertions
and historical records were preserved. The new actual Candidate is bound through
the existing source A → evidence B → declaration-only Proposed Baseline contract.
At evidence B, final full-suite/governance results on the declaration head are
not yet asserted: those exact-head outcomes and GitHub Quality Gate are attached
in the PR and Issue #212 after execution. No quality bypass is introduced.

## First GitHub CI and portable cancellation test repair

At declaration `13ea0b8…`, local full suite and governance passed. The first
Linux Quality Gate ran 905 tests (99 conditional skips) and found one error:
the SIGTERM test waited 5 seconds although cancellation can use its 1-second
signal-handler grace plus the supervisor's 5-second termination grace before
reaping a Linux zombie process group and notifying the caller. The test's
bounded wait is corrected to 10 seconds. Exit-code and workspace-removal
assertions are preserved. No production lifecycle/native code, policy, historical
assertion or protected artifact changes. The raw failed CI log and original
local PASS bindings remain evidence, not a claim of first-CI success.

This nonhistorical test-only fix is explicitly declared in the new evidence
overlay under the existing contract. The actual native source/Candidate stays A
`74785b5…`; its product/runtime/tooling bytes remain unchanged. Final declaration
full-suite/governance and Linux CI must be rerun before the PR is reported green.

Next genuine boundary: owner acceptance of the new Candidate, complete canonical
protection/pin authority, and any separately authorized historical migration or
promotion. No acceptance, promotion, runtime reconciliation, deployment or
historical cleanup is performed here.

PRODUCT_RULES_READ: YES
APPLICABLE_PRODUCT_RULES: PR-010, PR-011, PR-013
PRODUCT_RULE_CONFLICTS: NONE
