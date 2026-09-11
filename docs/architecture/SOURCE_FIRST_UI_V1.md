# Source-first macOS UI v1

Status: `ACCEPTED`

Issue: #76

## Boundary

```text
AppKit UI
  -> closed bridge
  -> Capability Registry / dependency planner / application runtime
  -> versioned Integra document, media, job and publication contracts
  -> local adapters and pinned component boundaries
```

The UI contains presentation and interaction state only. Source detection,
runtime availability, implementation status, dependency expansion, plan
identity verification, source copying, job execution and artifact production
remain Python application/domain services bundled behind the closed bridge.

## Workflow

The default screen is `Новая обработка`. A user adds one or several local
files, drags files into the window, or enters YouTube URL(s). Integra detects
source types and obtains one centralized capability projection. The user
selects concrete outputs under `Что нужно получить?`; technical prerequisites
are expanded automatically and shown in a human-readable plan. `Выполнить`
verifies the same plan identity and dispatches a background run.

Only `IMPLEMENTED + runtime_available` capabilities are selectable. Every
`NOT_IMPLEMENTED` capability is disabled and labelled exactly `В разработке`.
Runtime-unavailable implementations are disabled with the factual reason.

## Real production paths

- local media copy and SHA-256 verification;
- ffmpeg preparation plus whisper-cli timed transcript and SRT;
- native TXT, Markdown, DOCX, PPTX and text-PDF extraction with exact document
  records and locators;
- document content-mode/OCR requirement detection and embedded-media discovery;
- validated Obsidian and filesystem OneDrive package preview/publication.

The source-first runner does not materialize the legacy provisional topic
grouping as a requested result. SeminarText semantic authoring/review,
VideoText general media operations, BookText OCR, live YouTube ingest,
cross-source semantics, Learning, Marketing and social outputs remain disabled
as `В разработке` until an end-to-end Integra runtime path is accepted.

## Persistence and failure behavior

Plans and runs are persisted under the Integra project. A run contains the
verified plan, current real stage, per-source results and concrete artifact
paths. Multi-source work is sequential to avoid competing writers. Cancel
terminates the owned process group; retry creates a new auditable run from the
same revalidated plan. The app restores the most recent run on relaunch.

There is no fabricated percentage or ETA. The UI reports source completion
counts, the real current stage, persisted backend state and actionable errors.
Human Gate is not used for technical failures and no UI control performs
semantic acceptance.

## Retained boundaries

BookText remote `main` is not an accepted pinned Integra component and has no
versioned adapter contract. The pinned VideoText certification workers are not
a packaged general user runtime. The pinned SeminarText Topic worker is not
connected to arbitrary user-source execution. These repository facts are
visible in `docs/UI_IMPLEMENTATION_MATRIX.md` and are not hidden by UI state.

## Visual evidence

- `docs/screenshots/issue-76-source-first.png` — principal source-first workflow
  in the system light appearance.
- `docs/screenshots/issue-76-source-first-dark.png` — the same real UI state in
  the system dark appearance.

The screenshots use a real local Markdown source and the production source
detection/capability projection. They contain no fabricated processing result.
