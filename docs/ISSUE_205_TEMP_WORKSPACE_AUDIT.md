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

`scripts/verify_temp_workspace_lifecycle.py` runs two sequential full builds,
two concurrent full builds, artificial failure and timeout, and the release
path from a disposable owner root. It writes disk measurements and the list of
remaining owned roots to `docs/evidence/ISSUE_205_REPEATED_BUILD_EVIDENCE.json`.
It creates exact pinned source checkouts and hash-locked review wheels only
inside its own marker root, then removes that root. No source checkout,
installed app, user project or retained Candidate archive is changed.
