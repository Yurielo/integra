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
It concerns the selected Process runtime, not automatic removal of SeminarText
from every Integra bundle or other product domain. The current fallback has a
documented SRT interoperability defect; retaining it is not a claim that every
existing media journey is reliable.

## Owner decisions recorded 2026-09-25

- Continue the full product on **Integra**, reusing verified VideoText engines
  through bounded adapters rather than rebuilding Integra inside VideoText.
- The first completed Process journey is **Russian-speech first**. Complete
  English-speech ASR/alignment/topics may follow as a separate increment.
  Transcript translation, target-language choice, translated TXT and Topic
  translation remain frozen MUST outcomes. RU-to-EN text translation is not
  equivalent to a completed English-source-speech workflow.
- After Process, prioritize **Documents and Knowledge before full Studio**.
  This sets priority, not implementation/semantic acceptance of either domain.
- Plan proof against the reviewed VideoText 0.6.8 source revision recorded in
  the [execution inventory](PROCESS_V1_VIDEOTEXT_ONLY_EXECUTION_INVENTORY.md).
  Do not silently advance the integrated pin or inherit source-product PASS.

These decisions do not change the 47 MUST count or mark any Completion Board
row DONE. This documentation PR references #187; it does not complete or close
the runtime-proof Issue.

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
| Basic topics/timestamps; topic summary/detail | SeminarText Topic Engine | VideoText `HybridTopicAdapter` / `OllamaTopicProvider` output, mapped to the existing Process draft contract | `REUSE_VIDEOTEXT` | Prove normal-quality default, only selected granularity/language, no draft fallback, source cue IDs/times and `REVIEW_REQUIRED` semantics in a packaged route. |
| Process Topic Review: edit/confirm; save → close → reopen | SeminarText human-review receipt/contracts | Integra-owned Process-human receipt and reviewed-topic precedence, fed by VideoText drafts | `BOUNDED_ADAPTER` | Preserve `PROCESS_HUMAN_TOPIC_REVIEW`, original machine topic provenance and existing accepted rename/reopen behavior; do not create Knowledge/Evidence acceptance. |
| Translation; language choice; readable translated TXT | VideoText translation worker, currently dependent on upstream SRT | Retain VideoText worker and write its readable output through the Process result contract | `REUSE_VIDEOTEXT` | Selected target, valid source SRT, readable result, provenance and real packaged proof.  The existing SeminarText→VideoText SRT mismatch must not be carried forward. |
| Topic translation | No completed packaged journey established by the current translation PR | Translate topic labels/summaries through a bounded adapter; preserve topic IDs, source spans and source revision | `BOUNDED_ADAPTER` | Separate selected-output proof and reopen; transcript translation alone does not satisfy this MUST. Failed validation or retained original text must not be reported as successful translation. |
| Several ordered inputs; partial failure; combined transcript/provenance; multi-source corpus | Integra sequential planner plus SeminarText project corpus/combined-clear capability | Integra remains owner of run-level ordering/failure accounting; implement only the missing combined/corpus composition on VideoText/Integra artifacts | `INTEGRA_OWNED_REUSE` for order/failure; `BOUNDED_ADAPTER` for combined/corpus | Preserve completed peers after a failure; chronological combined result and per-passage provenance.  Do not use a hidden SeminarText project command. |
| Reuse/invalidation; cancel; retry; timeout; stale RUNNING; orphan cleanup; subsequent success | Integra lifecycle plus `asr_reuse` whose transcriber is SeminarText | Preserve lifecycle semantics; replace only the ASR executor under its governed cache identity | `INTEGRA_OWNED_REUSE` | Existing recovery evidence must be rerun only where ASR executor identity changes: reuse, source/model/config invalidation, failure/retry, cancel/timeout and no owned orphan. |
| Unified results; open/export; persistence/reopen; progress/status; selected outputs | Integra UI/application runtime | No component change | `INTEGRA_OWNED_REUSE` | Regression-only proof on the final VideoText-only Candidate. |
| Selected-Capability Runtime Closure | Current cross-cutting blocked Board row | Integra capability/runtime closure, reusing existing planning infrastructure | `IMPLEMENT_IN_VIDEOTEXT_OR_INTEGRA` | Not completed reuse: implement/prove selected dependency resolution across preflight, imports and packaged workers. A VideoText-only selection may not eagerly require SeminarText; missing selected dependencies must be shown before execution with an actionable reason. |

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

## Dependency-ordered implementation plan

This is sequencing within the existing scope, not new pre-created work packages
or authority to bypass the Completion Board. Select one bounded next Issue
from evidence after each coherent change.

1. **Freeze proof inputs and lifecycle prerequisites.** Record exact Integra,
   VideoText, model/config and control-media identities. Review the relevant
   temporary-Candidate ownership/cleanup work in PR #183 before expensive
   proof runs; it is still draft work, not inherited acceptance. Preserve the
   current route and owner projects. Use the same three Russian videos and the
   deterministic fuzzy-loop regression, including short/long and VAD/no-VAD
   behavior where applicable. No Gold rewriting.
2. **Isolated native ASR adapter.** Reuse VideoText's transcriber and quality
   services, not only a bare whisper command. Prove numbered SRT, readable TXT,
   quality rejection and bounded recovery without deleting repeated speech as
   a substitute. Preserve raw artifacts and exact executor provenance; no
   hidden SeminarText executable or module.
3. **Integra result contract and recovery.** Bind reuse to source/revision,
   executor/version, model, language and configuration. Keep old results and
   receipts; reuse them only through explicit compatibility, never relabeling.
   Retain Integra-owned Clean TXT derivatives, Russian WhisperX alignment and
   immutable ProcessedSource/provenance contracts. Rerun failure, cancel,
   timeout, reopen, invalidation and subsequent-success checks after the swap.
4. **Hybrid topics and Process human review.** Map real SRT cue IDs/times to
   existing Process topics, with normal-quality default and selected variant
   only. Prove summaries, review edits, save/close/reopen and preserved machine
   provenance. Applicable Gold regression does not inherit PASS from a different
   algorithm; Process review never creates Knowledge acceptance.
5. **Close remaining MUST gaps.** Reuse relevant translation work in PR #186
   after review/proof rather than rebuilding it; complete Topic translation
   separately. Verify actual ASR controls, folder/Zoom/playlist discovery with
   preview/confirmation, ordered inputs, partial failures, combined transcript
   and corpus with per-passage provenance. No hidden SeminarText corpus command.
6. **Selected dependency closure and final proof.** Prove preflight, import
   and bundle dependencies for the chosen outputs. Run the full 47-MUST exit
   matrix for the first RU journey on one exact packaged Candidate, with
   independent QA/review and two consecutive real short-video E2E passes on
   that same Candidate. Include the known SRT mismatch and fuzzy-loop regression;
   standalone VideoText tests are not Integra native-UI proof. Expensive local
   model/build runs are serialized. Technical proof, human acceptance, runtime
   promotion and permission to remove SeminarText are separate events.

The gate records `VIDEOTEXT_ONLY_PROCESS_PROVEN`,
`VIDEOTEXT_ONLY_PROCESS_NOT_YET_PROVEN`, or `BLOCKED`, with exact evidence and
remaining gaps. None alone means `PROCESS V1 USER_ACCEPTED`.

## Explicit non-permission

This gate does not authorize changing Process scope, deleting a SeminarText
pin, retiring historical evidence, starting Knowledge/Studio/BookText, or
claiming `PROCESS V1 USER_ACCEPTED`.
