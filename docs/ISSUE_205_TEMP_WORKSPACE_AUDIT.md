# Issue #205: temporary-workspace audit

## Scope and safety

This audit distinguishes a directory's name from proven ownership.  The new
reaper acts only on a current-user directory carrying the exact
`.integra-owned-workspace.json` marker written before materialization.  It
never uses `integra*`, age, or size as a deletion predicate.

## Integra creation paths found

| Path | Previous risk | Issue #205 policy |
| --- | --- | --- |
| `scripts/build_macos_app.sh` | Accepts any output directory and deletes its existing `Integra.app`. | Reject temporary outputs unless an ancestor has the lifecycle marker. It remains a low-level durable-output builder. |
| `scripts/test_macos_app.sh` | `mktemp -d` then direct full build. | Runs the whole test inside the authoritative owned workspace runner. |
| `scripts/build_macos_candidate.py` | New authoritative candidate operation. | Marker before copy/compile, disk reservation, bounded process group, manifest validation, optional explicit archive, cleanup in `finally`. |
| `scripts/package_ready_app.sh` | Full release-path build can be directed at a supplied output root. | Its temporary use is protected by the low-level builder guard; normal output is durable and intentional. |
| `scripts/candidate_archive.py` | Failed archive staging copies could remain at multi-GiB scale. | A failed unpublished `.incomplete-*` staging copy is now removed by its proven creator. Published `COMPLETE.json` archives remain immutable retained evidence. |
| Manual/Codex shell commands and old documented `/private/tmp/integra-*` paths | No common owner, process or cleanup record. | The only supported disposable full-build entry point is the lifecycle wrapper. The reaper fails closed for all legacy roots. |

No executable repository path uses `pgrep -f` polling.  The historical
home-wide `find`/poll processes were observed as external Codex-launched
processes, not a tracked Integra script.  The issue implementation uses direct
child PID/PGID ownership and finite timeouts instead.

## Ownership and retention finding on the reference Mac

Baseline captured on 2026-09-28:

- `/private/tmp`: 1.51 GiB, not tens of GiB.
- `/tmp`: alias of the same temporary volume, no separate allocation.
- current macOS `$TMPDIR`: about 0.36 GiB; `/private/var/folders`: about
  4.57 GiB. These are system/application temporary areas with no Integra marker
  and were not modified.
- `~/Library/Application Support/Integra/Build Archive`: 36.15 GiB. These are
  explicit historical Candidate archives, including review/promotion evidence.
- `~/Library/Application Support/Integra/Build Archive/retained`: 4.25 GiB.
  These are explicitly retained historical baselines.
- Integra user projects: 1.10 GiB. They are user data and out of scope.

The remaining tens of GiB are therefore primarily intentional-but-costly
Integra archival retention, not a currently active `/private/tmp` leak. This
issue neither prunes nor mutates those archives.

## Cross-product audit

| Product/location | Observed size | Classification | Action |
| --- | ---: | --- | --- |
| `/Users/yurielokhin/Documents/videotext` | negligible | source checkout, read-only | unchanged |
| `/private/tmp/videotext-seminartext-comparison-20260925` | about 0.53 GiB | unmarked comparison workspace; origin cannot be proved by Integra | not deleted; VideoText owner must classify |
| `/private/tmp/booktext-51` | about 0.31 GiB | unmarked BookText source/workspace | not deleted; BookText owner must classify |
| other `booktext-*` roots | small source/test/review workspaces | source-product owned and unmarked | not deleted |

VideoText's checked source paths did not reveal a tracked full-size candidate
builder. BookText's checked source paths contain several fixed `/tmp` outputs
in ad-hoc tools and ordinary `TemporaryDirectory` use, but the observed roots
were source/review workspaces rather than a packaged multi-GiB app. Neither
finding grants Integra permission to delete those roots or alter the protected
source repositories. Follow-up is recorded in VideoText
[#4](https://github.com/Yurielo/videotext/issues/4) and BookText
[#53](https://github.com/Yurielo/booktext/issues/53), respectively.

## Runtime copy decision

Issue #205 does not share or hard-link runtime payloads between candidates.
Candidate isolation, byte verification, archive integrity and concurrent-build
correctness take precedence over a storage optimization. The primary leak was
unretained workspaces; deleting them deterministically removes their steady
state amplification. Explicit archives remain intentionally duplicated and
need a separate retention policy decision rather than an unsafe deduplication
change.

## Recurrence audit, 2026-09-30

The issue reproduced while PR #206 was still open. At the start of this audit,
the Data volume had about 18 GiB free, `/private/tmp` occupied 24 GiB, and
`/private/var/folders` occupied 4.5 GiB. Eleven unmarked full-size Integra
roots of about 2.1 GiB each dominated `/private/tmp`. Their timestamps were
September 28–29, after the earlier cleanup. They were created by direct,
manually named candidate/release/worktree paths rather than the proposed
`integra-owned-*` lifecycle. No build process held these roots open.

Five exact candidate roots had a matching completed permanent archive. Each
archive passed `candidate_archive.py verify`, each source bundle recomputed to
the embedded bundle digest, and each source manifest hash matched the archive
receipt. Those five roots alone were classified `STALE-SAFE-TO-DELETE` and
removed by exact path. Free space rose from about 18 to 29 GiB. The remaining
large roots include four unarchived candidate/release/current copies and one
open-PR worktree; they remain `UNKNOWN` or active review material and were not
deleted. All completed Build Archive entries and other retained baselines were
preserved. `Build Archive` itself occupies about 53 GiB across 21 completed
Candidate archives plus explicit historical retained/recovery copies. The
accepted retention contract has no automatic pruning authority.

The macOS temp container occupies about 4.5 GiB, including about 2.8 GiB of
Chrome code-sign clones and ordinary caches. These are not Integra-owned
workspaces. BookText and SeminarText temporary roots are below 1 GiB each in
this audit and do not explain the multi-GiB recurrence. No deleted-but-open
file above 100 MiB was found.

| Remaining large root | Classification | Evidence and disposition |
| --- | --- | --- |
| `/private/tmp/integra-excel05-zoom-candidate-b53d3d2` | `UNKNOWN` | Full Candidate, no matching completed archive; preserved. |
| `/private/tmp/integra-excel07-final-current` | `UNKNOWN` | Full app without ownership marker or verified archive mapping; preserved. |
| `/private/tmp/integra-excel07-release` | `UNKNOWN` | Full Candidate without matching completed archive; preserved. |
| `/private/tmp/integra-excel07-source-current` | `UNKNOWN` | Full Candidate without matching completed archive; preserved. |
| `/private/tmp/integra-excel22-topic-translation` | `ACTIVE` | Separate Git worktree for open PR #204, with a full app in its build directory; preserved. |
| `/private/tmp/seminartext-proofread.OFbH7y` | `UNKNOWN` | About 0.9 GiB of separate SeminarText work; preserved. |
| `/private/var/folders/.../X/com.google.Chrome.code_sign_clone` | `UNKNOWN` | About 2.8 GiB of Chrome-owned clones; preserved. |
| `~/Library/Application Support/Integra/Build Archive` | `RETAINED-CANONICAL` | About 53 GiB of completed archived Candidates and historical retained copies; preserved. |

An unrelated but relevant root-owned `find /System/Volumes/Data` diagnostic
started on September 24 and remains orphaned under PID 1. The current user
cannot terminate it without administrator authentication. It was not started
by any tracked Integra script. No new unbounded `find` or `pgrep` polling was
used during this audit.

The additional repair on PR #206 puts the shared run lifecycle in a detached
supervisor. It owns the workspace and child process group, detects loss of its
calling process, and cleans after signal, timeout or killed child. The full
Candidate wrapper now uses that same supervisor and enforces its hard
free-space reserve. The low-level builder still requires a matching owned
marker before a temporary full-size build. New workspaces conservatively reap stale marked
work, while live owners and unproven roots remain protected.

Final repeated-build evidence is in
`docs/evidence/ISSUE_205_REPEATED_BUILD_EVIDENCE_20260930.json` and
`docs/evidence/ISSUE_205_DISK_PEAK_20260930.json`. The first rerun required
fresh local pinned source checkouts because the older Documents checkout
blocked `git checkout` past the bounded 60-second deadline; that failed setup
left no owned roots. The final run exercised two sequential full builds,
two concurrent full builds, failure, timeout, stale/live reaping and the
release path. Every scenario ended with zero owned roots. It recorded 30.53 GB
free before and 29.38 GB immediately after the scenarios (before deleting the
small evidence workspace). The first build warmed system caches and reduced
free space by about 1.09 GB; the second build changed free space by only
about 4.5 MB, so there was no linear 2.2 GB accumulation. The measured peak
was 4.61 GB in owned temporary roots during the concurrent case, with at least
24.81 GB free. The disk monitor sampled every five seconds under a finite
deadline and exited with the exact test process.

## Verification and remaining gates

- Focused workspace lifecycle tests: 11 passed, including killed caller,
  killed child, SIGTERM, timeout, live/stale separation and reserve rejection.
- Final full suite with complete Git history and a renewed Candidate proposal:
  830 tests, 738 passed, 92 skipped, zero failures.
- `scripts/check_agents.py` and `git diff --check`: PASS.
- `scripts/validate_governance.py`: PASS; CURRENT remains valid and the new
  proposal is `PROPOSED_BASELINE_VALID / AWAITING_OWNER_ACCEPTANCE`. A fresh
  Candidate built from exact source commit `3ee6365` was archived and reverified
  under the accepted retention contract. The initial shallow-clone failures
  were caused by unavailable lineage commits and a stale proposal after the
  source change, then resolved by source → evidence → declaration commits.
  The exact new GitHub Quality Gate must pass before merge. This proposal does
  not grant Product Owner acceptance or CURRENT promotion.
- The old root-owned whole-Data-volume `find` cannot be terminated by this
  unprivileged session; administrator action is required. The initial 53 GiB
  archive retention set plus the new approximately 2.1 GiB Candidate remain
  protected by the accepted retention policy
  and requires a separate explicit retention decision before any pruning.

## Evidence contract

## Follow-up: archive provenance and atomic disk admission — 2026-09-30

Final source: `e23aa21e085fba8fbf664f8eb517d4460baffed8`.
Independent QA/review: PASS for that exact source. The independent two-process
admission check used different roots on the same volume and a budget sufficient
for only one reservation: exactly one process was admitted. Injected marker
failure, post-spawn registration failure, archive cancellation and first-root
SIGKILL/retry cases now remove their owned roots and terminate their writers.
The new cross-base stale recovery regression verifies recovery through the
volume ledger even after the destination ancestor changes.

- Final full supported suite: **838 tests, 746 passed, 92 skipped, zero failures**.
- `check_agents.py`, focused regression checks and `git diff --check`: PASS.
- Three controlled sequential full Candidate builds on the follow-up sources
  `2261dea`, `b54d491`, and final `e23aa21` completed with byte-verified archives
  and zero remaining owned build/staging roots. The previous two sequential and
  two concurrent full-build measurements above remain historical evidence for
  the original lifecycle repair; the new admission race was independently
  verified with bounded synthetic processes, not full concurrent app builds.
- Final Candidate: `candidate-v1-e13b57a839bb722fb10cb7d46295ae58e77f4641bfacc1226147eedc28df4277`,
  bundle `dfa6b0102940534f2e06284a3768245d7476052bbe9f3e82713e1679b05a0204`.
  Its archived manifest binds a clean final source commit and tree.

### Inventory and growth accounting

`docs/evidence/ISSUE_205_ARCHIVE_INVENTORY_20260930.json` records every top-level
completed archive, source commit and associated GitHub PR where available,
manifest/receipt identity, dates, logical bytes, duplicate groups and sample
inode/link counts. It also records retained/recovery/runtime copies and legacy
tmp roots. The final inventory has **25 top-level completed Candidate archives,
14 declared bundle digests**, plus two historical canonical Candidates under
`retained` with two additional digests. Initial top-level inventory was 22/14.
The three controlled source revisions each required actual Candidate bytes
under the accepted retention contract: this added 6,604,620,459 logical app
bytes (about 6.15 GiB; filesystem allocation is greater). They are intentionally
accounted as permanent retained growth, not a temporary-cleanup leak.

After these builds, the top-level digest groups contain **24,217,048,837 logical
bytes (22.55 GiB)** beyond one copy per digest. This is a policy-decision upper
bound, not an authorized reclaim estimate: distinct Candidate identities and
some excluded bytecode files differ. Sample executables have separate inodes
and link count one; APFS shared extents were not measured.

### Exact tmp-root conclusion and SAFE CLEANUP PLAN

All four legacy app manifests bind the old builder hash `ad81f7…` and September
29 timestamps, preceding the September 30 repair. The fifth full-size root is
the still-open PR #204 source worktree (`93a080d…`), not an owned disposable run.
The new lifecycle cannot infer ownership from an `integra-excel*` name.

- `integra-excel07-final-current` contains a nested app. Its full computed
  bundle digest equals `d05c0863…`; its exact Candidate `136e1a5…` is retained in
  a separately reverified COMPLETE archive. Bounded `lsof +D` returned exit 1
  with zero rows. **Cleanup-eligible: about 2.12 GiB**, with a fresh no-writer
  check immediately before any deletion. This audit did not delete it.
- `excel05-zoom-candidate-b53d3d2` has no exact Candidate archive; preserve.
- `excel07-source-current` and `excel07-release` share a declared bundle digest
  with archives but their own Candidate identities are not archived; preserve
  until provenance/retention authority is resolved.
- `excel22-topic-translation` is active PR #204; preserve.
- Three additional old skeletons total about 14.6 MiB and lack manifests; they
  are recorded separately and were not mistaken for another full-size leak.
- Canonical CURRENT, historical retained Candidates, installed/runtime copies,
  user projects and source checkouts remain protected. The older runtime is at
  `/Users/yurielokhin/AI/runtimes/integra/current-build`, with no embedded
  Candidate manifest. Its consumers and runtime identity remain unproven.
- Top-level repeated bundles (~22.55 GiB logical), the two historical recovery
  app copies (~4.24 GiB allocated), and the three recovery/review duplicates
  (~6.37 GiB allocated) need an explicit retention decision. No archive count,
  TTL, retirement authority or byte-sharing implementation was invented.

The policy gap and class-based plan are also documented in
`docs/ISSUE_205_ARCHIVE_RETENTION_AUDIT.md`. Proposed owner decision: define
canonical/current protection, review-pending protection, historical-review
retirement authority and an explicit count/age bound, and decide whether equal
verified bundles may share an immutable byte archive while retaining each
Candidate's metadata and evidence. Policy-controlled eviction must remain
fail-closed when any class, reference, active writer or byte-integrity check is
unproven. Until that decision, automatic cleanup applies only to marked
disposable workspaces; repeated archive publication remains permanent growth.

PR #206 remains OPEN / AWAITING_OWNER_ACCEPTANCE. This follow-up does not accept
the proposal, change CURRENT, merge, promote or deploy. Final governance and
GitHub status are checked on the renewed declaration HEAD.

`scripts/verify_temp_workspace_lifecycle.py` runs two sequential full builds,
two concurrent full builds, artificial failure and timeout, and the release
path from a disposable owner root. It writes disk measurements and the list of
remaining owned roots to `docs/evidence/ISSUE_205_REPEATED_BUILD_EVIDENCE.json`.
It creates exact pinned source checkouts and hash-locked review wheels only
inside its own marker root, then removes that root. No source checkout,
installed app, user project or retained Candidate archive is changed.
