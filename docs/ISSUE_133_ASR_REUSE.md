# Issue #133: verified project-local ASR reuse

Bounded P1 work in the completion plan; not general pipeline resume or an ASR
quality certification. Source products remain read-only pinned components.

## Contract

The native Retry action starts a new run through the existing bridge. Before
recognition, the application service checks for a complete successful ASR
result in the same project. Reuse requires matching source content, runtime,
model, configuration and output hashes. Missing, partial, stale, corrupted or
symlinked cache data never proves a valid transcript. Such entries remain for
inspection; recognition must run again rather than silently trusting them.

Publication of a reusable record happens only after successful ASR quality
checks, before downstream stages. Thus a later alignment/topic/rendering error
does not itself require repeating recognition. A cancelled or quality-failed
ASR invocation cannot publish success. Reuse retains original provenance and
machine-unreviewed assurance; it supplies no semantic review authority.

Scope is project-local ASR reuse, not shared cross-project storage, partial
chunk resume, reuse of semantic decisions, or automatic recovery of every
pipeline stage. Prior artifacts are preserved, not rewritten in place.

## Implementation matrix

| Source | Capability | Owner / production path | Callable UI path | Evidence | UI state |
|---|---|---|---|---|---|
| Local media / downloaded video in same project | Reuse complete ASR | Integra `asr_reuse.transcribe_or_reuse` → pinned SeminarText on cache miss | Retry → bridge → run_job | Counted recognizer calls, downstream failure, invalidation, native retry probe | Show REUSED only when returned by service |
| Any failed/cancelled run | Retry dispatch | Existing bridge `retry-run` → new owned run | Native Retry, serialized off main thread, duplicate-click guard | Existing shutdown tests and native retry probe | Active only for supported terminal states |
| Media | Partial ASR chunk resume / cross-project reuse | No production path added | None | Not claimed | Not exposed as working |

## Native behavior and evidence

Retry service dispatch is off the main thread. A real reuse result is carried
from the job into the run and displayed as verified reuse. The UI does not
infer reuse from the mere presence of a text file.

`tests/native_asr_retry_probe.py` uses isolated source/app-data roots and actual
native Execute/Retry actions. Its recognizer and alignment executables are
explicit test fixtures: alignment fails once after ASR, then succeeds. The
assertion requires a new completed run, one recognizer invocation, two alignment
attempts and a service-proven REUSED result. This proves the retry integration,
not speech recognition or alignment accuracy. Other existing native media and
shutdown probes remain required.

## Verification

- Full supported local suite: **621 tests PASS, zero skips, 398.036 seconds**.
- Clean macOS candidate: PASS; all core files match the reviewed working tree.
- Native Retry acceptance on the clean candidate: PASS; one recognizer launch,
  two alignment attempts, new COMPLETED run with REUSED metadata.
- Active close, Quit and ambiguous-ownership refusal on that candidate: PASS.
- Full suite includes clean native build and byte-reproducible packaged builds.
- Independent cache/UI review and focused boundary tests: PASS; malformed
  manifests, duplicate clicks and validation-time mutation are covered.
- Governance validation and `git diff --check`: PASS.
- Existing installed app backup was verified against its source inventory.
  Installation of this change remains a separate post-merge step.

## Related blocking cancellation regression

The wider test run exposed a race in #130: writing the cancellation marker
before freezing workers let a cooperative recognizer exit during descendant
capture. The marker now appears only after successful complete freezing, before
termination. Identity checks were not weakened. Timeout leaves the run active
without false cancellation; owned processes suspended by the attempt are
resumed. A deterministic ordering test and ten consecutive real nested-process
cancellation tests passed. This minimum correction is included because it
blocked safe delivery of this retry path.
