# Integra Continuous Implementation Queue

Status: `PRODUCT_OWNER_AUTHORIZED`

This queue is the operational continuation contract for autonomous Integra
delivery. After a clean merge, Codex must select the first `READY` item, create
its dedicated Issue/branch, deliver it, verify it, merge it, update this queue,
and immediately continue. A routine PR, test run, merge, or report is not a
stopping point.

`READY` means a bounded implementation can be completed without credentials,
private data, semantic acceptance, source-repository changes, external
publication, signing, or destructive actions. `BLOCKED` items remain visible
but cannot be presented as working UI capabilities.

## Ordered queue

| Order | Status | Delivery item | Definition of done |
| ---: | --- | --- | --- |
| 1 | READY | Audio enhancement | A source-first local-media output invokes the owned ffmpeg runtime, produces an explicit enhanced audio artifact, exposes it in macOS results, and has runtime/bridge/build evidence. |
| 2 | READY | Time-range media clips | A user selects exact start/end times from persisted SRT cues; Integra renders an owned clip with ffmpeg, records source/time provenance, and exposes the file. |
| 3 | READY | Multiple-result publication selection | macOS publication view lets the user select a concrete verified package from any completed persisted run, then preserves the existing preview-before-write and collision protections. |
| 4 | BLOCKED | SeminarText Word Timeline and Topic runtime | Requires a packaged, version-pinned SeminarText runtime plus an accepted arbitrary-user-source adapter; no current macOS runtime path exists. |
| 5 | BLOCKED | VideoText general media runtime | Requires a packaged, version-pinned VideoText adapter for arbitrary user media; certification workers alone are insufficient. |
| 6 | BLOCKED | BookText OCR runtime | Requires a pinned BookText identity, versioned Integra adapter, local runtime binding, and OCR smoke evidence. |
| 7 | BLOCKED | Live YouTube ingest | Requires the deferred live discovery/download authority and runtime adapter. |
| 8 | BLOCKED | Marketing, Learning, Assistant, and social adapters | Remain post-ready-app roadmap work and must retain `В разработке` until separately implemented end-to-end. |

## Execution rule

1. Re-read `AGENTS.md`, current state, and the queue before selecting work.
2. Select the first `READY` item only.
3. Do not replace a `BLOCKED` item with a mock, a component-only claim, or a
   disabled control labelled as working.
4. On success, mark the item `COMPLETED`, append its Issue/PR/commit evidence,
   then proceed to the next `READY` item without returning control to the user.
5. Stop only for the concrete safety boundaries in
   `docs/AUTONOMOUS_EXECUTION_POLICY.md`.
