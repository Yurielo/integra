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

## Evidence contract

`scripts/verify_temp_workspace_lifecycle.py` runs two sequential full builds,
two concurrent full builds, artificial failure and timeout, and the release
path from a disposable owner root. It writes disk measurements and the list of
remaining owned roots to `docs/evidence/ISSUE_205_REPEATED_BUILD_EVIDENCE.json`.
It creates exact pinned source checkouts and hash-locked review wheels only
inside its own marker root, then removes that root. No source checkout,
installed app, user project or retained Candidate archive is changed.
