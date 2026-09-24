# Issue #180: temporary build/test artifact lifecycle report

This report records the implementation and validation of ownership-bound
temporary artifact roots. It does not authorize removal of pre-existing
`/private/tmp/integra*` paths.

## Root cause and scope

The observed accumulation came from caller-selected, ad-hoc Candidate output
roots (including `integra-candidate-*`, `integra-wp*-candidate*`,
`integra-pr*-candidate*`, `integra*-final-candidate*`, and
`integra*-build*`). `build_macos_app.sh` is deliberately an explicit-output
primitive, so it retained every root supplied by a candidate/owner/repair/E2E
caller. Those callers had no common ownership marker, signal trap, or safe
post-crash recovery mechanism.

The remaining creation paths and their contract are audited in
`TEMP_ARTIFACT_LIFECYCLE.md`. The GitHub Quality Gate runs governance and unit
tests only; it does not create a macOS Candidate bundle. `package_ready_app.sh`
creates an intentionally retained home-directory app and is outside this
temporary lifecycle.

## Implemented lifecycle

Disposable build/test roots are now created by
`temp_artifact_lifecycle.py create` and have an exact self-binding marker:

- root, purpose, timestamp, cleanup policy;
- PID plus `ps` start token and random run token.

`with_temp_artifact_root.sh` owns one such root and removes only that exact
marker-bound root on success, command failure, `SIGINT`, or `SIGTERM`. It
forwards termination to its child before cleanup. A `SIGKILL` cannot be
trapped; `reap` is a conservative recovery command that scans only direct
children of a supplied base and removes only marker-bound, AUTO_CLEANUP roots
whose owner PID/start token is no longer live. Retained evidence roots and live
or malformed roots are skipped.

`test_macos_app.sh` now uses the same marker/trap contract. Ephemeral native
Candidate checks use `run_macos_candidate_checks.sh`. A retained Candidate must
use `build_macos_candidate.sh --output` outside the system temporary base; it
performs native self-test and manifest validation and is deliberately retained.

No global glob cleanup is introduced. Canonical/current builds, production
runtimes, user data, retained governance evidence, unmarked roots, and roots
of other active processes are excluded.

## Write amplification decision

No copy-elision is safe for the Candidate runtime. The bundle needs private,
hash-closed copies of pinned component runtimes and model material. Hard links
or shared source runtime material would permit a later source mutation to alter
an existing Candidate; reflinks do not supply a portable macOS identity
guarantee. The build already produces one final bundle rather than a second
full staging bundle. Therefore this Issue removes post-run disk retention, not
the one isolated bundle required for reproducible validation.

## Candidate-bound evidence and disk measurement

Two sequential marker-owned full native Candidate builds were completed during
this Issue. Each reached `INTEGRA_MACOS_SELF_TEST: PASS`, and the second also
ran `candidate_manifest.py validate`. The measured live scratch root was
**2.1 GiB** before its wrapper cleanup. After each wrapper exited, its exact
scratch root no longer existed; the remaining marker-owned candidate scratch
space was **0 bytes / 0 roots**. No pre-existing `/private/tmp/integra*`
directory was manually removed.

The second run's immutable manifest is copied as evidence at
`docs/evidence/ISSUE_180_TEMP_ARTIFACT_LIFECYCLE_CANDIDATE_MANIFEST.json`:

- Candidate: `candidate-v1-288ba11ba1b2b850fb186f94b4ab9eba7a1fbbd8d10b910b4b390095c3dc729a`
- product source commit: `5f10a09626868c5dbcccc02866d395ff00f591cb`
- product source tree: `f9c374c6522174d5e86747f718d53a7a63751521`
- bundle digest: `044594f1a632f1c140af28bb7de8e4acf782daca9863d84b9c5d77edb731fdf8`

## Focused regression results

`python3 -m unittest tests.test_temp_artifact_lifecycle -q` passes 8 tests:

1. normal completion removes a large owned root;
2. command failure removes a large owned root;
3. `SIGINT` and `SIGTERM` clean only the interrupted wrapper's root while a
   concurrent root remains intact;
4. stale reaping skips live owners and retained evidence, and removes only a
   dead marked root;
5. an unmarked canonical build cannot be a cleanup target;
6. the existing macOS harness uses marker-bound cleanup;
7. retained Candidate output is rejected under temporary storage;
8. the build app-path stdout contract keeps review-runtime diagnostics on
   stderr.

Native candidate evidence above adds the production-equivalent build,
self-test, manifest-validation, and post-cleanup proof.
