# Temporary build and test artifact lifecycle

Issue: #180. This document governs disposable build/test scratch roots; it does
not authorize removal of existing directories or retention-governed evidence.

## Audit and root cause

| Path | Creates large artifact? | Prior behavior | Lifecycle now |
| --- | --- | --- |
| `scripts/build_macos_app.sh OUTPUT_ROOT` | Yes: one self-contained `Integra.app` (about 2.1–2.2 GiB) | Caller-selected `/private/tmp/integra…` roots were deliberately left behind. The build remains an explicit-output primitive: disposable callers use the marker wrapper; retained Candidates use a non-temporary destination. |
| `scripts/test_macos_app.sh` | Yes: one test bundle plus probes | Anonymous `mktemp -d` was cleaned only on ordinary shell exit. It now creates a marker root and traps success, failure, `SIGINT`, and `SIGTERM`. |
| `scripts/package_ready_app.sh` | Yes: ready app | Its named home-directory output is retained, never a stale-reaper target. |
| GitHub Quality Gate | No macOS Candidate | Ubuntu governance/unit workflow; Python `TemporaryDirectory` scopes are process-owned and small. |
| Candidate/final-candidate/owner/repair/E2E commands | Often | Ad-hoc Codex commands supplied `/private/tmp/integra-*` roots without a common ownership contract. Disposable checks now use `with_temp_artifact_root.sh`; retained owner/evidence Candidates use `build_macos_candidate.sh --output` outside temporary storage. |
| Runtime/project helpers | No large app bundle | Scoped `tempfile` or same-directory atomic staging remains unchanged. |

The observed orphan directories are historical caller-owned Candidate roots,
not a single runtime leak. The build makes the required single bundle copy; it
did not create a second persistent bundle itself.

## Marker-bound contract

`scripts/temp_artifact_lifecycle.py create` uses `mkdtemp` and writes
`.integra-temp-artifact.json` with the absolute root, purpose, timestamp,
cleanup policy, owner PID, `ps` process-start token, and random run token.

Only a root with an exact self-binding marker is eligible for deletion.
`cleanup` rejects unmarked/symlinked paths and retained evidence roots. `reap`
examines direct children of an explicitly selected base, not a name glob; it
removes only marked `AUTO_CLEANUP` roots whose owner is no longer live. It
skips live owners, malformed markers, unrelated paths, and `RETAIN_EVIDENCE`.

## Use

Disposable build/test/probe:

```bash
scripts/with_temp_artifact_root.sh --purpose candidate-smoke -- \
  bash -c 'app="$(scripts/build_macos_app.sh "$INTEGRA_TEMP_ARTIFACT_ROOT")"; "$app/Contents/MacOS/Integra" --self-test'
```

The wrapper cleans only its own root on success, failure, `SIGINT`, and
`SIGTERM`, first forwarding termination only to its child. `SIGKILL` cannot be
trapped; a later governed recovery can run:

```bash
scripts/temp_artifact_lifecycle.py reap --base "${TMPDIR:-/private/tmp}"
```

Retained owner/evidence Candidate:

```bash
scripts/build_macos_candidate.sh --output "$HOME/Integra-candidates/topic-review"
```

This helper refuses `/tmp`/`/private/tmp`, validates native self-test and the
Candidate manifest, and deliberately does not auto-delete explicit output.

## Disk and reproducibility

The app must contain private copies of pinned SeminarText, VideoText, BookText,
Review, Word Alignment packages, and model weights. Hard-linking or sharing a
source runtime could let later mutation alter an existing Candidate; reflink
behavior is not a portable macOS identity guarantee. The build already creates
one final bundle rather than a full staging duplicate. No unsafe copy reduction
is implemented: write amplification is one isolated bundle per build, and
ephemeral builds remove it immediately.

## Explicit exclusions

The lifecycle never removes canonical/current builds, production runtime, user
project data, source checkouts, governance evidence, unmarked roots, or roots
owned by a live process. Existing `/private/tmp/integra*` directories are
untouched by this Issue.
