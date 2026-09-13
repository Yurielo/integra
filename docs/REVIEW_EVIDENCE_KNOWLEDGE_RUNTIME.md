# Controlled Review, Evidence and Knowledge — issue #119

## Workflow

1. Process a local audio/video source with TXT, Word Timeline and topic drafts.
2. In its results, choose **Проверить TXT и создать Evidence**. Open the TXT,
   inspect the complete text, enter a reviewer identifier and explicitly
   confirm it. Cancelling has no semantic effect. Changed source/TXT/timeline
   bytes invalidate that confirmation and require another review.
3. Choose **Подготовить темы к проверке**. Integra binds real drafts to exact
   words in the confirmed Evidence and asks the pinned component to validate
   a review package. Incompatible boundaries are rejected before decisions.
4. Read the topic title, summary and exact quotation. Choose **Принять** or
   **Отклонить** for every topic; no choice is preselected. Enter a lowercase
   reviewer identifier. Only the explicit save action persists decisions and
   invokes SeminarText's knowledge compiler.
5. Open the resulting knowledge and decision artifacts from the source results.

No original SeminarText project is modified. Integra uses an owned source copy
and a separate review snapshot. Failed Evidence attempts remain isolated for
diagnosis; a later attempt does not consume their artifacts. A package with
persisted decisions cannot be silently rewritten by another decision.

## UI implementation matrix

| Source | Capability | Owner | Production/runtime path | Evidence | UI state |
| --- | --- | --- | --- | --- | --- |
| Owned media + TXT + Word Timeline | Human-confirmed Evidence | Integra adapter → pinned SeminarText Evidence Foundation | AppKit → `prepare-transcript-review` / `apply-transcript-review` → `promote-transcript`, `align`, `evidence-check` | Sequential real-component and bridge tests; stale-text and interruption tests | Explicit confirmation only |
| Confirmed Evidence + real SeminarText drafts | Versioned review input | Integra contract adapter | AppKit/bridge → `prepare_topic_review_input` | Real Evidence → topic input test | Drafts remain REVIEW_REQUIRED |
| Compatible complete-segment topics | Topic decisions and knowledge | Pinned SeminarText review workflow and knowledge bridge | AppKit → `prepare-knowledge-review` / `apply-knowledge-review` → pinned subprocesses | Real package → explicit decisions → Canonical Knowledge tests | Explicit accept/reject; no default acceptance |
| Arbitrary topic boundaries | Knowledge compilation | Pinned SeminarText compiler | Rejected before decisions | Compiler requires complete BenchmarkSegments | В разработке |
| Accepted knowledge | Concept/relation editing, arbitrary boundary editing | Future integration | No production authoring path exposed | Not claimed | В разработке |

## Verified component limitation

The pinned `project_knowledge_bridge.py` requires Topic ranges to align to
complete BenchmarkSegments. Evidence Foundation produces these segments
independently of generated topics. Therefore real generated topic boundaries
can be incompatible even when their word/time references are valid.

Integra must not silently widen a topic quotation or alter its canonical
Evidence to satisfy this constraint. Such inputs fail before review decisions.
Issue #119 remains open until a compatible pinned contract or a separately
specified explicit boundary-review workflow resolves this gap. The current
work does not claim general Knowledge Studio completion or a new managed
Obsidian/OneDrive publication package path.

## Reproducible local build

The source component files are verified against exact SHA-256 values by
`scripts/package_review_runtime.py`. The Python review dependencies match the
pinned SeminarText core requirements and are locked by wheel hashes in
`scripts/review-runtime-requirements.txt` (CPython 3.14, macOS arm64).

Download build inputs once:

```sh
python3.14 -m pip download --require-hashes --only-binary=:all: \
  -r scripts/review-runtime-requirements.txt \
  --dest .runtime-components/review-wheels
```

The normal macOS build installs those wheels offline into the application
bundle, retaining dependency metadata/licenses. It does not fetch packages at
application runtime. The Python 3.14 interpreter remains a preflighted host
dependency, as other existing Integra processing tools do. No source checkout
or OneDrive mount is needed by the packaged review component.
