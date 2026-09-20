# Issue #148 — Packaged pre-acceptance stabilization

## Phase 1 status

`IN_PROGRESS`. Only the required Phase 1 specialists were activated:
backend-developer, qa-test-engineer, and ci-cd-engineer. No other role has a
concrete activation trigger.

## Owner failure

The owner reported that candidate
`/private/tmp/integra-candidate-issue-146e/Integra.app` failed after selecting
Transcript, SRT, Word Timeline, and Topics with:
`Word Timeline worker did not produce a validated output`.

The source of that generic error is
`integra_core/word_timeline_runtime.py:generate_word_timeline`. It currently
collapses a worker non-zero exit and a missing output to the same message while
discarding captured worker stdout, stderr, and exit code. In addition, the
bridge plan child is started with stdout/stderr directed to `DEVNULL`. This is
insufficient evidence for a release-blocking packaged workflow failure.

## Production-equivalent reproduction

On 2026-09-20, the exact #147-lineage candidate was invoked headlessly through
its bundled `Contents/Resources/bridge.py`, not source-tree components:

`detect-sources → capability-registry → build-plan → execute-plan →
process-plan → application_runtime.execute_run → user_media.run_job`.

This is the same path used after the AppKit GUI calls `execute-plan`; headless
execution replaces only the user interaction.

Fixture provenance: generated non-private Russian speech using the macOS `say`
voice `Milena`, muxed into a 7.465-second black-video MP4 using ffmpeg. SHA-256:
`db0cbfd61a3861442114d27633d0b8115af792f6532674298886d86fd57cf3e4`.

The run selected Transcript, SRT, Word Timeline, and Topics. It completed with
the existing persisted terminal token `COMPLETED` (the current product has no
`SUCCESS` token; this is the Issue's successful terminal outcome), and produced
transcript, transcript JSON, SRT, Word Timeline, Topics, ASR provenance, job,
run, source, and navigation-ready artifacts. This proves the reported failure
is not deterministically reproduced by the bounded generated fixture, but is
not yet a reusable release gate.

## Next Phase 1 work

Do not enter Phase 2 or Phase 3. Add a bounded reusable built-app harness and
retain actionable Word Timeline worker diagnostics without weakening the
validator. The primary gate is green only after that harness passes on a fresh
isolated candidate.
