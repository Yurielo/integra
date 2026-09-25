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
row DONE. PR #188 recorded the initial plan. The owner's subsequent instruction
to correct it after critical review establishes the two-stage sequence below.
Documentation updates reference #187; they do not complete or close it.

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
| Protective retry against contextual/fuzzy Whisper looping | SeminarText `quality_check` + protective retry; bounded trigger/retry/failure proof, not recovery accuracy | Reuse VideoText detection; name exactly one retry owner at the Stage A contract checkpoint | `IMPLEMENT_IN_VIDEOTEXT_OR_INTEGRA` | Distinguish detector accuracy, bounded retry, safe failure and successful recovery using the evidence matrix below. Genuine spoken repetitions must not become a required rejection oracle; no dedup as a substitute for lost speech. |
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

## Execution authority and ordering

For the #187 executor transition, this sequence and DoD section E describe the
same active order. It supersedes the former instruction to finish verification
of the outgoing runtime before investigating the new one. Historical Board
evidence remains unchanged. Missing implementation for a replacement executor
is not automatically a new product requirement: reuse first, then define a
bounded adapter/repair under the existing MUST. New capabilities, source-product
changes or altered semantic/acceptance policy still require exact authority.

Stage A answers whether a bounded VideoText transition is viable. Stage B
finishes and proves all 47 MUST outcomes. Stage A cannot close #187, replace
the user's app, remove SeminarText, or claim full Process acceptance. Select
one next bounded Issue from evidence; this plan does not start implementation.

## Stage A: bounded feasibility proof

1. **Freeze contracts and inputs before adapters.** Record exact commits,
   models/configs, the same three Russian control videos and existing loop
   fixtures. Keep Gold and user projects unchanged. Specify a versioned worker
   result mapping for source identity, TXT/SRT, quality, output hashes, actual
   executor and errors/progress. Integra owns jobs, leases and cancellation;
   name one owner for protective retry and its attempt/time budget to prevent
   nested retry loops. Reuse existing storage; ProcessedSource is a target to
   implement, not an already completed immutable result contract.
2. **Minimum real dependency closure.** Before the first packaged ASR proof,
   specify and test the selected worker's imports, preflight and bundle/runtime
   requirements. No unrelated SeminarText probe or integrity bypass may be
   necessary to execute it. Keep the old route available and preserve its known
   SRT limitation. Review relevant lifecycle work in #183 against this proof's
   needs; do not make completion of every draft change a prerequisite. Record
   exact rollback and owned-process cleanup before expensive runs.
3. **Fresh ASR proof, then reuse.** Reuse VideoText's existing transcriber and
   quality services through the narrow adapter. Each control input first runs
   in an isolated test project with no transcript or result cache: record
   actual VideoText execution, raw numbered SRT/TXT and hash-linked outputs.
   Model/embedding downloads are not transcript caches. No SeminarText calls
   and no pre-existing SeminarText artifacts may satisfy this first proof.
   A separate unchanged-input run must demonstrate valid reuse with no ASR.
   Never delete the user's cache to obtain a cold test.
4. **Bounded topic compatibility probe.** On a fresh, validated transcript,
   map existing HybridTopicAdapter output to Process topics with actual cue
   IDs/times and the normal-quality, selected-only variant. Verify a minimal
   review/save/reopen round trip without losing machine provenance. This
   checks the second replacement boundary; it is not full topic acceptance.
5. **Decision checkpoint.** Before starting runs, record the finite case list,
   maximum retry attempts/time per case, one repair-and-rerun budget and the
   acceptance comparison rules. Exhaustion returns an evidence package, not
   unlimited tuning. Proceed to Stage B only when fresh execution, valid
   output mapping, safe lifecycle and topic compatibility are demonstrated
   and remaining gaps have bounded owners/solutions. A technical pass is
   permission to select the next authorized implementation item, not a new
   mandatory human approval stop. Missing equivalence returns
   `VIDEOTEXT_ONLY_PROCESS_NOT_YET_PROVEN`; an authority/architecture conflict
   returns `BLOCKED` for the appropriate decision. Do not force the migration.

## Stage B: integration and full Process completion

1. **Implement the result boundary before downstream consumers.** Create the
   minimal immutable ProcessedSource projection over existing artifacts per
   DoD section G, with revision/predecessor and atomic completeness. Do not
   replace the database. Define compatibility for old results explicitly;
   preserve their executor labels and human edits. Invalidation is per derived
   output: changing topic detail/model must not require ASR; changing source
   or transcript revision invalidates dependent topics/alignment/translation,
   retaining old reviewed versions without silently rebasing them.
2. **Integrate ASR, then topics in separate reviewable changes.** Preserve
   Integra Clean TXT derivatives and Russian WhisperX alignment. Prove fresh
   execution and warm reuse, source/model/config invalidation, failure, cancel,
   timeout, reopen and subsequent success. For topics, prove summaries,
   selected detail/language only, no draft fallback, real source spans and
   human edits surviving restart. Apply compatible Gold checks without
   changing Gold or inheriting a different algorithm's PASS. Process review
   does not create Knowledge acceptance.
3. **Finish remaining frozen MUST journeys using existing work.** Review and
   reuse relevant #186 translation implementation; prove Topic translation
   separately. Connect truthful ASR controls, folder/Zoom/playlist preview and
   confirmation, ordered sources, partial failure, combined transcript and
   corpus with per-passage provenance. Never hide a SeminarText corpus call.
   Complete selected dependency closure incrementally with each output,
   rather than postponing its design to final QA.
4. **Full exact-Candidate verification.** Map each of the 47 MUST outcomes to
   its actual native action, produced artifact/state, negative case, test and
   evidence on one packaged Candidate. Repeat two short-video native E2E runs
   on those same bytes for stability, alongside long-media and fault cases;
   these repetitions do not replace the full matrix. Independent QA/review,
   applicable non-skipped runtime proofs, regression and integrity gates must
   pass before user acceptance. Serialize expensive local model/build runs.

Only the whole matrix supports `VIDEOTEXT_ONLY_PROCESS_PROVEN`. Technical
proof, human `PROCESS V1 USER_ACCEPTED`, runtime promotion and authority to
remove SeminarText remain separate events.

## Evidence and acceptance matrix

Freeze checks before execution, not after seeing output. A proof record binds
input/hash, exact Candidate/runtime/model/config, cold/warm state, expected
outcome, actual result and artifact/log evidence. Numerical semantic/performance
thresholds must be justified from the control material and measured baseline;
none are invented by this documentation update. Unspecified criteria mean
NOT_READY to start the relevant proof, not permission to choose post-hoc limits.

| Evidence | What it proves and required interpretation |
| --- | --- |
| Same three real Russian videos, including long-media/chunk boundaries | Fresh executor integration, numbered valid SRT, preserved source identity and inspected speech coverage. Without a reference transcript report observations, not ASR accuracy percentages. Include short/long and VAD/no-VAD cases where the paths differ; preserve the original controls. |
| Artificial ASR-loop regression | Detector and bounded automatic retry are exercised. A suspicious retry stays failed/review-required as the supported contract specifies; it is never a completed valid transcript. |
| Genuine spoken repetitions | False-positive control: preserve the words. The old repeated-speech fixture proved a trigger/retry/failure path, not that rejecting correct repeated speech is desirable. Record false positives independently; do not turn the old rejection into a mandatory quality oracle. |
| Recoverable failure case | Compare retry output to known source speech and prove recovery separately. Safe failure is not recovery. Do not require every acoustic failure to recover; do not strengthen the historical safety-only Board claim silently. |
| Topic quality | On an authorized compatible reference, fix boundary matching tolerance, missed/spurious-boundary and title/summary review criteria before comparison. Valid JSON/cue IDs prove structure, not semantic quality. No Gold edits or fabricated new reference labels. |
| Model/worker failures | Cover malformed/truncated JSON, unavailability, timeout, cancellation and retry exhaustion. Verify valid upstream artifacts survive and the next run works without restart. |
| Performance | Record cold/warm wall time, time per media minute, peak memory, temporary disk and model request/variant counts on the reference Mac. Define allowed regression limits before running. Only requested topic detail/language executes. |
| Full 47-MUST matrix | Product completeness on the exact packaged Candidate, not inherited component tests or historical DONE counts. |
| Two consecutive short-video native E2E runs | Repeatability of the declared GUI workflow/outputs on the same Candidate; not long-media quality, all MUST outcomes or installation proof. Record actual packaged entrypoint, actions and expected files before running. |

## Explicit non-permission

This gate does not authorize changing Process scope, deleting a SeminarText
pin, retiring historical evidence, starting Knowledge/Studio/BookText, or
claiming `PROCESS V1 USER_ACCEPTED`.
