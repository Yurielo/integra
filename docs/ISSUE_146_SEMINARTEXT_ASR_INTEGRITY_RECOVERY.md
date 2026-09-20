# Issue #146 — SeminarText ASR integrity recovery

## Scope and result

This is a minimal stacked change after #141 → #143 → #145. It corrects the
active expected SHA-256 used by the SeminarText ASR adapter. It does not change
the SeminarText commit, ASR parameters or semantics, component/model pins,
historical evidence, or deployment state.

Status: `READY_FOR_OWNER_RETEST` after the headless checks below. Owner GUI E2E
remains required and was not run by automation.

## Root cause and evidence

The #144 candidate contained the final, correct SeminarText CLI bytes:

| Artifact | Expected final value | #144 candidate actual |
| --- | --- | --- |
| SeminarText commit | `970bde598ddd649599295139986933e0e06cb9c0` | `970bde598ddd649599295139986933e0e06cb9c0` |
| `runtime/seminartext/seminartext` SHA-256 | `f7f411bf106341ae970bc40d759e1e3c964273b977bdb12d0f1840e629def13a` | `f7f411bf106341ae970bc40d759e1e3c964273b977bdb12d0f1840e629def13a` |
| `SEMINARTEXT_VERSION` SHA-256 | `e1d49c569ae09b2ede16e2d83820a3809b35eb6c44c13ba9b5330598d6b8f43c` | `e1d49c569ae09b2ede16e2d83820a3809b35eb6c44c13ba9b5330598d6b8f43c` |

`integra_core/seminartext_asr_runtime.py` independently used the obsolete
`ENTRYPOINT_SHA256` value `020cc5fcd36fa3040b59e3e725afb1439e15c00cb4ad1fda03e171fa94a1c9d7`.
`capability_registry()` calls `user_media.preflight()`, which calls
`seminartext_asr_runtime.preflight()`, then `_runtime()`. That old expectation
therefore rejected a correctly packaged runtime and disabled both Transcript
and SRT before execution. The build manifest and Topic runtime had already
migrated to the final pin; this ASR-specific active identity was omitted.

## Change

`ENTRYPOINT_SHA256` now equals the final CLI SHA-256. The check still requires
both regular, non-symlink files to have exact hashes. A byte change still raises
`SeminarText ASR runtime differs from pinned bytes`; there is no bypass,
fallback, or post-hoc acceptance.

## Regression coverage

- The ASR runtime test pins the active CLI hash to `f7f411…def13a`.
- A verified runtime is accepted; modifying its CLI byte sequence is rejected.
- Capability regression confirms a READY ASR boundary exposes both Transcript
  and SRT as `Доступно`.
- Candidate-level checks use the packaged runtime itself: valid preflight,
  local-video Transcript/SRT capability availability, then a copied bundle with
  modified CLI bytes rejected fail-closed.

## Fresh isolated candidate

Path: `/private/tmp/integra-candidate-issue-146e/Integra.app`

The candidate was newly built from the final SeminarText checkout, the clean
#142 Word Alignment runtime, and the #144 Ollama resolver. It was not deployed;
the existing current build and standalone components were untouched.

Headless results:

- `INTEGRA_MACOS_SELF_TEST: PASS`
- bundled SeminarText ASR identity: PASS
- bundled ASR preflight: PASS
- selected local-video Transcript/SRT capability check: PASS
- modified bundled CLI: fail-closed PASS
- bundled Word Alignment preflight: PASS
- bundled BookText preflight: PASS

Source validation also passed `bash -n scripts/build_macos_app.sh`, `git diff
--check`, the focused ASR/capability/Ollama tests (27 run, 6 environment
skips), `scripts/check_agents.py`, and `scripts/validate_governance.py`. A
full `unittest discover` was stopped at the pre-existing, unrelated
`test_closed_bridge_rejects_unknown_and_previews_without_writes`: its bridge
preview subprocess has no timeout and remained blocked. This issue does not
change that path.

## Owner retest

Use this candidate only. Select a local video and confirm Transcript and SRT
are enabled before starting a run. GUI E2E is intentionally deferred to the
owner; no GUI/Finder/Preview automation was run.
