# Issue #148 — Packaged pre-acceptance stabilization

## Phase 1 status

`PHASE_1_PASS`. Only the required Phase 1 specialists were activated:
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

## Phase 1 repair and gate evidence

The integration repair preserves fail-closed behavior. Word Timeline now writes
a bounded `word_timeline.worker-diagnostic.json` beside its intended output,
containing the worker command, exit status, and final 16 KiB of stdout/stderr.
A non-zero exit or absent output is still rejected. The diagnostic exists to
make a future failure attributable; it is not accepted as output.

Reusable command:

`python3 scripts/test_packaged_primary_e2e.py <Integra.app> <isolated-work-dir>`

It uses only the built app's bundled bridge/runtimes; clears inherited
`INTEGRA_*` component override variables; creates a bounded non-private Russian
speech fixture; enters through `execute-plan`; polls `run-status` for at most
300 seconds; and retains the isolated app-data tree on either outcome.

Fresh candidate: `/private/tmp/integra-candidate-issue-148-phase1/Integra.app`.
Native self-test passed. The reusable gate passed with fixture SHA-256
`5f1447fc19684f710a4c83b435160725cd5130c106f299074a605b823575b5a1` and
persisted run `urn:integra:run:b84522b9-45e9-461f-8740-0c224fe112f3`:

| Mandatory primary row | Result |
| --- | --- |
| Build, self-test, bundled identities | PASS |
| Source ingestion and capability/plan | PASS |
| Real packaged ASR, transcript, SRT | PASS |
| Real packaged Word Timeline and validation | PASS |
| Topics | PASS |
| Persisted artifacts and navigation metadata | PASS |
| Final state | PASS (`COMPLETED`, mapped to Issue `SUCCESS`) |

## Secondary readiness

Translation was started through the same bundled bridge path on the primary
fixture. It remained `RUNNING` for more than three minutes without producing a
terminal record, so the bounded observation was stopped and is recorded as
`BLOCKED` pending the known translation latency/progress investigation. No
translation repair is made in this issue. BookText and resilience checks remain
`NOT_RUN` at this checkpoint.
