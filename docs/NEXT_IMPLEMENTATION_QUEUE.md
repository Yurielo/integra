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
| 1 | COMPLETED | Audio enhancement | PR #94, commit `d4ea88a`: source-first local-media output invokes owned ffmpeg, creates an explicit M4A artifact and source-hash record, and is exposed in macOS results with runtime/bridge/build evidence. |
| 2 | COMPLETED | Time-range media clips | PR #96, commit `d04c2f3`: exact persisted SRT cue range renders an owned ffmpeg clip, persists source/time provenance, and is exposed from macOS media navigation. |
| 3 | COMPLETED | Multiple-result publication selection | PR #98, commit `692cac5`: macOS lists only revalidated packages from completed persisted runs and requires explicit selection before the existing preview-before-write and collision protections. |
| 4 | COMPLETED | SeminarText Word Timeline | PR #109: existing SRT is aligned by the bundled personal-use WhisperX 3.8.6 runtime and the pinned Russian Wav2Vec2 model. The output preserves native word timing or explicitly marks a word unaligned; no timing is fabricated. |
| 5 | BLOCKED | VideoText general media runtime | Requires a packaged, version-pinned VideoText adapter for arbitrary user media; certification workers alone are insufficient. |
| 6 | COMPLETED | BookText OCR runtime | Issue #113: the pinned BookText source is packaged into Integra with its exact Apple Vision QA executable; the source-first path invokes real Surya OCR and retains actual TXT, Markdown, JSON, searchable-PDF, raw OCR and review artifacts. |
| 7 | COMPLETED | Individual YouTube video ingest | Issue #117: a user-selected video is downloaded by the local `yt-dlp` adapter into Integra-owned project storage, recorded with URL/runtime/SHA-256 provenance, then handed to selected real media outputs. |
| 9 | COMPLETED | YouTube playlist ingest | Issue #120: a user-selected playlist is discovered through local `yt-dlp`, retaining live acquisition provenance while reusing the accepted offline playlist contracts. Members are downloaded sequentially with per-item checkpoints and verified artifacts. |
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
