# Issue #135 — stable, truthful native Operations

Baseline: main `516dd9db42911a2406d93ba9036743d5d67a00d6` after verified
installed delivery of #133. Scope is completion-plan P1 and issue #76 native
execution UX, not a new processing engine or semantic authority.

## Pre-implementation UI matrix

| Source | Capability | Responsible component | Real production implementation | Runtime path | Evidence before change | Target UI state |
|---|---|---|---|---|---|---|
| All persisted runs | Current state/stage/results | Application service + native presentation | `read_run`, persisted run JSON | bridge `run-status` | Existing service/native tests; current UI rereads synchronously and reconstructs every tick | Asynchronous; unchanged rendered state preserves views; no guessed ETA/percent |
| Active source-first runs | Cancel | Application shutdown service | nonce/kernel-birth verified cancellation | bridge `cancel-run` | #130/#133 active process tests | Pending request is explicit; terminal cancellation only from backend |
| Failed/cancelled runs | Retry | Existing application runtime | verified ASR reuse and new run | bridge `retry-run` | #133 native one-recognizer/two-attempt test | No stale callback navigation; no duplicate dispatch |
| Any source | Standard Quit / Cmd+Q | AppKit menu + shutdown service | `applicationShouldTerminate` with verified shutdown | NSMenu shortcut → NSApplication terminate → bridge | Direct terminate probe exists; explicit native menu absent | Actual key-equivalent dispatch tested |
| Any source | Native editing shortcuts | AppKit responder chain | focused native text controls | Edit menu with nil target | No explicit menu currently | Copy/paste/select all reach focused control |
| Any source | Exact processing ETA / unmeasured overall percent | No measured backend implementation | Hard-coded checkpoints are not measured fractions | None | Not proven | Not displayed as measured progress |

## Acceptance and boundaries

Polling has one owned request at a time, independent of long write operations.
Responses are bound to the current screen/navigation generation and run IDs;
late success and error responses cannot replace another screen. Only rendered
fields define view identity: heartbeat time and legacy stage percentages do not.
Polling transport failures remain visible and recover without forcing a redraw.
Cancel/retry responses likewise cannot hijack navigation.

Native acceptance will use an isolated real worker fixture, unchanged snapshot
checks, a bounded queue gate for a real delayed read, navigation away and real
Cancel. No fake production state or test delay in the backend is introduced.
Existing Quit acceptance will dispatch the actual Cmd+Q menu key equivalent.

General crash recovery, lost legacy process ownership, direct-operation
cancellation and stage-by-stage checkpoint recovery remain separate P1 work.
No private media, live publishing, source-product edits or semantic acceptance.

## Implementation and verification in progress

The native presenter now reads status on its own serial queue, admits one
request at a time and binds responses to navigation generation/project/run.
Rendered snapshots exclude heartbeat/legacy progress and include pending
action state. Cancel uses the existing service queue and rejects duplicate
dispatch; retry callbacks no longer replace a different screen. Terminal
status and result files still come only from the actual application service.
Unknown states are reported as invalid responses rather than treated as done.

The application and Edit menus use AppKit actions and responder routing.
The existing native Quit probe now dispatches the actual Cmd+Q menu event.
Shutdown-refusal errors survive subsequent successful status polls.

`tests/native_operations_probe.py` uses an isolated real bundled run with
test-only media executables. It verifies unchanged view identities, late-read
navigation protection, actual native cancellation, owned-child termination,
source preservation and survival of an unrelated process. This is lifecycle
evidence, not an ASR-quality assessment. Static architecture guards reside in
`tests/test_operations_ui.py`; they do not substitute for the native probe.

Initial candidate native Operations, ASR retry and shutdown probes passed.
No installed application update is claimed by this document yet.

Final candidate (before commit):
`/tmp/integra-135-candidate.oYzARW/final/Integra.app`.
Reproducible tree-hash algorithm from `tests/test_ready_app.py` produced
`4767abb3026fcf78d35a6718cb8d25f1cd4b591d2ad0d0828093015b1763bd7a`.
Package build, self-test and strict bundle seal verification PASS. Retained
`operations-final`, `retry-final`, `shutdown-final` probes all PASS, including
actual Cmd+Q and refusal of ambiguous shutdown. The Operations screenshot was
visually inspected: confirmed cancelled state, real source count and retry,
with no stale current-stage or unmeasured percentage.

Independent QA re-review found no remaining blocking issue. Source component
checkouts stayed clean. No private source processing, semantic acceptance,
account operations, cloud publication or distribution signing occurred.

Final full suite: **624 PASS, 0 skips, 438.394 seconds**;
`/tmp/integra-135-candidate.oYzARW/full-suite-final.log`. The first run found one
outdated static assertion for the old synchronous bridge variable; that
assertion was corrected and the complete suite rerun, not waived. Focused UI
guards: 6 PASS. Governance and diff checks PASS. Full suite includes clean
native build/probes and two byte-identical packaged builds. Delivery pending
verified PR/CI/merge and governed installed-runtime reconciliation.
