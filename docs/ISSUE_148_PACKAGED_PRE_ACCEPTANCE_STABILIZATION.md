# Issue #148 — Packaged pre-acceptance stabilization

## Phase 1 status

`BLOCKED` after the Owner Audit Correction. Only the required Phase 1 specialists were activated:
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

## Superseded happy-path evidence

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

The owner correctly rejected this as a Phase 1 acceptance claim. In addition,
the earlier harness invoked the bridge through Homebrew Python 3.14, while the
GUI uses `/usr/bin/python3`; an earlier probe also referenced #146e paths.
Those runs are invalid as fresh-candidate GUI-equivalence evidence. The harness
now explicitly uses `/usr/bin/python3`, but has not been rerun because the
original failure class remains blocked. The short
generated fixture proves only a happy path; it is not an
`ORIGINAL_FAILURE_CLASS_REGRESSION_PASS` and must not be used for owner
handoff.

## Original failure evidence and missing root-cause evidence

The preserved owner run is
`urn:integra:run:0e41299d-0ae3-48c9-b1d8-66526ba9695d`, with job
`urn:integra:job:9b701e50-56f5-4e01-b78c-094ea72820c7`. It proves that the
real local video completed ASR/SRT and failed at `word_timeline` (progress 85),
without a timeline output. It contains only the generic error.

The original app version predated the diagnostic artifact. It persisted neither
the Word Timeline command environment nor worker exit status/stdout/stderr, and
the bridge discarded plan-worker stdout/stderr. Therefore the saved run cannot
distinguish a worker crash, process/environment difference, model load error,
or output validation error. This evidence is irretrievably absent; the new
diagnostic capture cannot reconstruct it retroactively.

The exact packaged worker has since been run against the saved owner WAV and
SRT with the exact bundled runtime and model: exit `0`, stderr empty, 174
words. This disproves a static bad-model/bad-input explanation but does not
identify the historical cause or constitute a repaired regression.

Accordingly the required chain remains incomplete:

`REPRODUCED → ROOT_CAUSE_IDENTIFIED → FIXED → ORIGINAL_FAILURE_CLASS_REGRESSION_PASS → PACKAGED_E2E_PASS`

Only the final happy-path element has evidence. No Phase 2 or Phase 3 result is
claimed; the earlier translation observation is superseded and must not be
treated as Phase 2 execution under the corrected fail-fast order.

## Secondary readiness

Translation was started through the same bundled bridge path on the primary
fixture. It remained `RUNNING` for more than three minutes without producing a
terminal record, so the bounded observation was stopped and is recorded as
`BLOCKED` pending the known translation latency/progress investigation. No
translation repair is made in this issue. BookText and resilience checks remain
`NOT_RUN` at this checkpoint.
