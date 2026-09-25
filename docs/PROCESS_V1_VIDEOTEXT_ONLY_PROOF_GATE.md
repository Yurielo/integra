# Process v1 — VideoText-only proof gate

**Status:** decision-gate evidence for [Issue #187](https://github.com/Yurielo/integra/issues/187).  It is not a scope change, replacement of the Product Definition, or permission to remove SeminarText.

## Purpose

The Product Owner has chosen a proof-first direction: determine whether normal
Process video/audio work can use **VideoText as its only component runtime**,
with Integra retaining its own UI, persistence, recovery and provenance
contracts.  SeminarText remains the current required fallback until the proof
gate is passed and a separate owner decision authorizes removal.

“VideoText-only” means a selected Process execution has no call to a
SeminarText executable or module.  It does **not** mean that a VideoText source
unit test, registry entry, or disabled UI option is proof of user integration.

## Current factual baseline

In canonical `main` at the start of Issue #187:

* `user_media.run_job` invokes `asr_reuse → seminartext_asr_runtime →`
  SeminarText `project-transcribe` for a transcript.
* The resulting SeminarText SRT is adapted through the VideoText subtitle
  normalizer; this handoff has just failed on an ordinary real-video Integra
  run because the two SRT contracts are not compatible as currently composed.
* Word Timeline is a separate WhisperX adapter and can consume a valid SRT.
* Topic drafts and the accepted Process Topic Review route use SeminarText
  runtime contracts.
* VideoText is already the translation-worker owner and has bundled media
  operations.  Its source ASR, quality/review diagnostics and hybrid Topics
  engines are not the active selected Process owner.
* Integra itself owns source records, selected-output planning, persistence,
  reuse/invalidation, cancellation, timeout, stale-run reconciliation and the
  Process UI.

The three real-video comparison recorded before this gate showed that both
products transcribed all three Russian videos.  VideoText generated numbered
SRT and its topic sets on all three; direct standalone SeminarText
`project-topics` failed on two longer videos.  These observations do not score
ASR accuracy: there is no human reference transcript for the comparison.

## Required transition matrix

The table covers every frozen Process requirement whose current implementation
uses, or is materially dependent on, SeminarText.  Grouping is intentional:
the Completion Board has aggregate rows, and one user journey can satisfy more
than one requirement.

| Frozen Process outcome(s) | Current component path | VideoText/Integra target | Classification | Proof still required |
| --- | --- | --- | --- | --- |
| Local video; local audio; automatic TXT; timed SRT | SeminarText `project-transcribe` via `seminartext_asr_runtime` | VideoText `SegmentedWhisperTranscriber` + `SRTService`; Integra persists the existing output contract | `REUSE_VIDEOTEXT` | One VideoText-native Process route on the same three real Russian videos; numbered SRT, readable TXT, hashes and no SeminarText process/module call. |
| Careful ASR mode; source language; ASR settings and diagnostics | SeminarText CLI defaults; controls incomplete | VideoText source language/quality/review diagnostics, exposed only where frozen Process requires them | `REUSE_VIDEOTEXT` | Exact supported controls, recorded selection and an actionable result/diagnostic; no invented “careful” equivalence. |
| Protective retry against contextual/fuzzy Whisper looping | SeminarText `quality_check` + protective retry; prior real failure-class proof | Equivalent detection and retry may live in VideoText or an Integra-owned quality layer | `IMPLEMENT_IN_VIDEOTEXT_OR_INTEGRA` | Reproduce the known deterministic fuzzy-loop class, demonstrate that the retry/recovery preserves the missing speech, and prove no post-hoc dedup is substituted for recovery. |
| Clean TXT; raw/review derivative provenance | SeminarText clean/review derivatives | VideoText transcript plus an Integra-owned, source-linked readable derivative if VideoText has no equivalent | `BOUNDED_ADAPTER` | Defined clean-text contract, source/ASR linkage, and packaged readable result. |
| Word Timeline and timed source navigation | WhisperX adapter consumes SeminarText SRT | Preserve WhisperX as an Integra-owned alignment adapter consuming VideoText numbered SRT | `INTEGRA_OWNED_REUSE` | Same real Russian alignment proof, exact source/SRT hashes and navigation, with no SeminarText dependency. |
| Basic topics/timestamps; topic summary/detail | SeminarText Topic Engine | VideoText `HybridTopicAdapter` / `OllamaTopicProvider` output, mapped to the existing Process draft contract | `REUSE_VIDEOTEXT` | Three-level source output is not enough: prove basic Process topics, selected granularity, source spans and `REVIEW_REQUIRED` semantics in a packaged route. |
| Process Topic Review: edit/confirm; save → close → reopen | SeminarText human-review receipt/contracts | Integra-owned Process-human receipt and reviewed-topic precedence, fed by VideoText drafts | `BOUNDED_ADAPTER` | Preserve `PROCESS_HUMAN_TOPIC_REVIEW`, original machine topic provenance and existing accepted rename/reopen behavior; do not create Knowledge/Evidence acceptance. |
| Translation; language choice; readable translated TXT | VideoText translation worker, currently dependent on upstream SRT | Retain VideoText worker and write its readable output through the Process result contract | `REUSE_VIDEOTEXT` | Selected target, valid source SRT, readable result, provenance and real packaged proof.  The existing SeminarText→VideoText SRT mismatch must not be carried forward. |
| Several ordered inputs; partial failure; combined transcript/provenance; multi-source corpus | Integra sequential planner plus SeminarText project corpus/combined-clear capability | Integra remains owner of run-level ordering/failure accounting; implement only the missing combined/corpus composition on VideoText/Integra artifacts | `INTEGRA_OWNED_REUSE` for order/failure; `BOUNDED_ADAPTER` for combined/corpus | Preserve completed peers after a failure; chronological combined result and per-passage provenance.  Do not use a hidden SeminarText project command. |
| Reuse/invalidation; cancel; retry; timeout; stale RUNNING; orphan cleanup; subsequent success | Integra lifecycle plus `asr_reuse` whose transcriber is SeminarText | Preserve lifecycle semantics; replace only the ASR executor under its governed cache identity | `INTEGRA_OWNED_REUSE` | Existing recovery evidence must be rerun only where ASR executor identity changes: reuse, source/model/config invalidation, failure/retry, cancel/timeout and no owned orphan. |
| Unified results; open/export; persistence/reopen; progress/status; selected outputs | Integra UI/application runtime | No component change | `INTEGRA_OWNED_REUSE` | Regression-only proof on the final VideoText-only Candidate. |
| Selected-Capability Runtime Closure | Current cross-cutting blocked Board row | Integra capability/runtime closure | `INTEGRA_OWNED_REUSE` | A VideoText-only selection may not eagerly require SeminarText; missing VideoText dependencies must be shown before execution with an actionable reason. |

## Gate sequence

1. **Execution inventory — no product change.** Enumerate every process/module
   invoked by the selected normal Process route and establish the exact
   VideoText/Integra replacement boundary.  The three-video comparison and
   known fuzzy-loop evidence are inputs, not acceptance by themselves.
2. **VideoText-native ASR proof.** In an isolated candidate, run the same
   three real local Russian videos and the deterministic fuzzy-loop regression.
   Record transcript, SRT, quality/retry, source hashes, runtime identity and
   the absence of SeminarText invocation.
3. **Bounded replacement only where the matrix requires it.** Do not duplicate
   SeminarText wholesale.  Preserve Integra-owned recovery and Process review;
   add only the adapters or implementations explicitly marked above.
4. **Whole selected Process proof.** Run the frozen Process entry gate on one
   Candidate: normal GUI, outputs, translation, topics/review, persistence,
   controlled failure/recovery and no Terminal/Codex use.

If any required row lacks a credible equivalent, the result is
`VIDEOTEXT_ONLY_PROCESS_NOT_YET_PROVEN`, not a forced migration.

## Explicit non-permission

This gate does not authorize changing Process scope, deleting a SeminarText
pin, retiring historical evidence, starting Knowledge/Studio/BookText, or
claiming `PROCESS V1 USER_ACCEPTED`.
