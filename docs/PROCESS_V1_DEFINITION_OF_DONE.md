# Process v1: canonical Definition of Done and Completion Board

Date: 2026-09-22. Status: `PROCESS_V1_DOD_FINALIZED`.
This is the active vertical planning authority for **Phase 1 / Process v1**.
It is not an implementation authorization, a change to Product Definition/
CURRENT/roadmap, or an acceptance record. It uses the owner workbook, the
published source-parity inventory, staged architecture review, and Process scope
map only. No new capability audit, build, test, Candidate, GUI run, Recovery
continuation, or product change was performed.

## Authority and execution progression

The Product Definition remains the higher-level product authority; this document
does not replace it. For Phase 1, the frozen scope is exactly 50 MUST, 5 OPTIONAL,
13 LATER, and 17 BookText entries
`OUT_OF_PROCESS_V1_PENDING_PROCESS_DOCUMENTS`. #150, #151, #157 and earlier
planning documents remain historical/decision evidence. They cannot independently
expand this frozen Process v1 scope.

Only a new explicit Product Owner decision may change the Process v1 scope. The
next implementation WP must be selected from the Completion Board. No WP2/WP3 is
created in advance: after each coherent WP, update the Board from evidence and
only then select the next WP. The first next WP after this document is merged is
**Existing Process Proof + Recovery Closure**, prioritizing `VERIFY_EXISTING`
while preserving the already obtained #161/#162 evidence.

## A. Product outcome

**Process v1 is one normal native macOS Integra.app journey that lets a user
select supported local media, folders/Zoom folders, a YouTube video or playlist;
select required outputs; review the discovered selection; confirm; process each
selected source; and reopen truthful provenance-bound results without Terminal
or Codex.**

For each selected source it creates an immutable, provenance-preserving
ProcessedSource result with the requested transcript/SRT/Word Timeline,
translation, basic Topics and permitted review output. It can process several
sources in a chosen order. Folder/playlist discovery requires preview and user
confirmation. A failed playlist item does not automatically fail other selected
items. Combined transcript/corpus are independent selected multi-source outputs,
not an implied playlist side effect.

The app visibly reports required-runtime availability before execution, gives
actionable errors, exposes progress and terminal states, preserves valid upstream
work, and safely supports cancel, retry, timeout, stale-state reconciliation,
reuse/invalidation, and a subsequent successful run. It does **not** create
Canonical Knowledge, media derivatives, publication, social/learning products,
or Process Documents in this phase.

`PROCESS V1 USER_ACCEPTED` requires the whole exit gate in §H for one exact
Candidate. Existing source code, unit tests, adapters, static GUI paths, or a
past accepted narrow Candidate do not alone establish that result.

## B. Frozen scope

### Counting rule

The owner workbook contained 51 `MUST`, 5 `OPTIONAL`, and 12 `LATER` rows.
The owner correction moves **Topic hierarchy** from MUST to LATER. Frozen scope
therefore contains **50 owner-facing MUST**, **5 OPTIONAL**, and **13 LATER**
rows. Three MUST rows about preflight/error/unavailable capabilities are one
shared bounded requirement (§D), yielding 48 Board entries without silently
removing any MUST.

### MUST — frozen Process v1 outcomes

| Journey | Frozen MUST outcomes |
| --- | --- |
| Inputs and discovery | Local video; local audio; several video/audio files in one run; folder: select folder → discover supported files → preview/select → user confirmation → process; Zoom folder; one YouTube video; playlist URL → ordered discovery → preview/selection → process selected items independently. |
| Transcript and structure | Automatic TXT transcript; SRT; Word Timeline; careful/enhanced ASR; protective retry; Clean TXT; Review TXT; source-speech language choice; ASR quality settings; ASR quality diagnostics; Topics/timestamps; Topic summary; Topic detail choice; edit/confirm Topics. |
| Translation | Transcript translation; target-language choice; translated TXT; translated SRT; Topic translation. |
| Multi-source | Ordered processing; combined transcript; combined-result provenance; corpus from several materials. Playlist does not imply combined corpus. |
| Results and persistence | Unified results screen; open produced result; reopen after restart; reuse valid intermediates; invalidation after source/model/config change; export selected Process results to ordinary files. |
| Reliability | Cancel; retry after failure; subsequent run without restart; timeout; no orphan workers; stale RUNNING reconciliation; preservation of valid upstream outputs after downstream failure. |
| Normal app UX | GUI-only normal use; selected-capability runtime preflight; actionable missing-dependency error; real progress; clear Processing/Completed/Failed/Cancelled states; select outputs before execution; truthful unavailable functions before execution. |

### OPTIONAL — non-blocking

Loudness measurement, noise analysis, pause analysis, audio-quality diagnostics,
and processing history. These are not accepted by a skipped test and do not delay
the frozen MUST exit gate unless the Product Owner explicitly elevates them.

### LATER — frozen outside Process v1

Topic hierarchy; thematic clips; blur; watermark; speed variants; filler mute;
dereverb; dubbing/TTS; marketing material; Knowledge/Evidence/relations;
Obsidian/OneDrive publication; social adapters; Learning/Assistant.

### OUT_OF_PROCESS_V1_PENDING_PROCESS_DOCUMENTS

The owner left every BookText sheet choice blank. PDF/DOCX/PPTX/TXT/Markdown
document processing, PDF/image OCR, page selection, page/region provenance,
raw geometry, searchable PDF, DjVu, multi-image books, illustrations, OCR engine
selection, table reconstruction, and chapters/outline are **not LATER** and do
not block Process v1. They are preserved as the future `Process Documents`
stage. ProcessedSource v1 must be extensible for page/region provenance without
a destructive redesign (§G), but no document feature is accepted or implemented
by this DoD.

## C. Completion Board

States are only `DONE`, `IN_PROGRESS`, `NOT_DONE`, or `BLOCKED`. `DONE` below
means the named owner outcome has bounded packaged/user evidence — not merely a
source implementation — and remains subject to whole-scope exit evidence.
`IN_PROGRESS` means an existing path/evidence exists but lacks the frozen-scope
Candidate proof. `NOT_DONE` means a required connection/output/control is absent.
`BLOCKED` identifies a documented cross-cutting architectural prerequisite.

| USER OUTCOME | CURRENT STATE | EXISTING CAPABILITY / EVIDENCE | REQUIRED TRANSITION | ACCEPTANCE GATE |
| --- | --- | --- | --- | --- |
| Local video | DONE | S01 + V03; P156 accepted bounded local Russian-video result | Retain exact path in frozen scope | Final Candidate includes representative local video. |
| Local audio | DONE | S01/V01/V03 current local-media path; Issue #169 candidate `candidate-v1-17f50c…` completed public natural-Russian packaged audio with TXT/SRT, Word Timeline, Topics, and persisted navigation | Retain exact local-audio route in frozen scope | Packaged audio journey: Issue #169 result/evidence hashes in `PROCESS_V1_WP1_EXISTING_PROOF_AND_RECOVERY.md`. |
| Several local files | DONE | S06 sequential source plan plus candidate `candidate-v1-589ef606…`: packaged Finder-like `first.wav → corrupt.mp3 → later.wav` retained each source in order as `COMPLETED / FAILED / COMPLETED`; successful peer artifacts persisted and a fresh bridge reread the terminal run | Retain bounded source-scoped failure isolation | Candidate-bound packaged proof in `PROCESS_V1_MULTI_SOURCE_FAILURE_ISOLATION.md`; every selected local source has an explicit terminal result without fabricated failed-source output. |
| Folder discovery/confirmation | NOT_DONE | S06 partial only; no generic folder discovery correspondence | Integrate selected folder discovery → preview/select → confirmation | Packaged folder journey with only confirmed supported files processed. |
| Zoom folder | NOT_DONE | S07 source discovery exists; no current planner connection | Integrate bounded Zoom discovery | Packaged Zoom-folder discovery/selection journey. |
| One YouTube video | DONE | S08; Issue #169 Candidate downloaded public non-private `jNQXAC9IVRw` through `youtube_runtime → app → media`, with owned media and hash-bound source record | Retain exact selected-video path | Packaged source record and owned downloaded-media hashes in `PROCESS_V1_WP1_EXISTING_PROOF_AND_RECOVERY.md`. |
| YouTube playlist | NOT_DONE | S08 and S10 partial; owner now fixed semantics | Integrate ordered discovery, preview/selection and independent per-video ProcessedSources | Packaged playlist with one failed/unavailable item not falsely failing selected peers. |
| Automatic TXT transcript | DONE | S01; P156 accepted bounded result | Retain pinned CLI path | Final Candidate representative transcript. |
| SRT | DONE | V03; P156 persisted SRT | Retain selected SRT service | Final Candidate SRT bound to transcript/media. |
| Word Timeline | DONE | P156 real aligned output; S19 composite row remains VERIFY only for Evidence linkage | Keep alignment/provenance separate from later Evidence | Final Candidate timeline hash/time navigation; no Canonical Evidence requirement. |
| Careful ASR mode | NOT_DONE | S04 exists; selector absent | Integrate bounded mode selection/config recording | Selected mode in GUI, runtime record and result. |
| Protective retry | IN_PROGRESS | S02 pinned CLI quality gate/retry | Verify packaged trigger → retry | Controlled contextual/fuzzy trigger with retry evidence. |
| Clean TXT | DONE | S03; Issue #169 ordered Candidate run persisted readable `transcript_cleaned`, raw TXT, ASR record and source-linked SRT; all listed artifact hashes were reread by a fresh packaged bridge | Retain source-linked derivative route | Candidate artifact hashes in `PROCESS_V1_WP1_EXISTING_PROOF_AND_RECOVERY.md`; this does not assert human review or source replacement. |
| Review TXT | IN_PROGRESS | S03 persisted derivative/output actions | Verify review artifact behavior | Candidate opening/provenance without source replacement. |
| Source-speech language | NOT_DONE | V02 source capability; control not connected | Integrate supported source-language selection | GUI selection and recorded runtime configuration. |
| ASR quality settings | NOT_DONE | S04/V02 exist; no documented control | Integrate bounded settings without changing defaults by implication | Selected settings and provenance in Candidate. |
| ASR diagnostics | NOT_DONE | V02/S02 artifacts exist; diagnostics not connected | Integrate readable diagnosis/status | Packaged actionable diagnostics. |
| Transcript translation | NOT_DONE | S14/V05/V06; current `en` JSON worker path | Integrate requested supported translation result | Selected translation in final Candidate. |
| Translation-language choice | NOT_DONE | V06 worker parameter; no GUI choice | Integrate language control | Target language recorded and visible. |
| Translated TXT | NOT_DONE | V06 JSON output only | Integrate readable TXT artifact | Linked translated TXT. |
| Translated SRT | NOT_DONE | V06 + V03; no composed output | Integrate timed translated SRT | Linked source/target/timing output. |
| Topic translation | NOT_DONE | S15 exists; not connected | Integrate provisional translated headings/references | Candidate output preserves review authority. |
| Topics/timestamps | DONE | S12; P156 accepted bounded result | Retain selected Topic path | Final Candidate basic Topics/timestamps. |
| Topic summary | NOT_DONE | S12 partial; S13 detail capability exists | Integrate defined summary output | Summary bound to source spans. |
| Topic detail choice | NOT_DONE | S13 exists; selector absent | Integrate bounded detail selection | Selected detail config/results. |
| Topic edit/confirm | IN_PROGRESS | S20 review path exists | Verify actual review dialog and exact decision behavior | Packaged human review with authority status. |
| Ordered processing | DONE | Candidate `candidate-v1-589ef606…` ran the configured local input order through the bundled production bridge; the controlled middle failure did not prevent the later independent source | Retain sequential planner and per-source terminal accounting | Candidate-bound packaged proof in `PROCESS_V1_MULTI_SOURCE_FAILURE_ISOLATION.md`: explicit ordered `COMPLETED / FAILED / COMPLETED` results and truthful run-level `FAILED`. |
| Combined transcript | NOT_DONE | S11 exists; current adapter uses single source | Integrate combined-clear output | Chronological output and completeness boundary. |
| Combined provenance | NOT_DONE | S11 manifest/provenance exists; no app path | Integrate provenance output | Source/time trace for each combined passage. |
| Multi-source corpus | NOT_DONE | S10 exists; queue is not corpus | Integrate explicit corpus membership | Corpus completeness/provenance proof. |
| Unified results screen | IN_PROGRESS | Bounded P156 native result composition | Verify all selected Process results together | Packaged result view; unavailable outputs honestly labeled. |
| Open result | IN_PROGRESS | S03/V03 output actions; P156 accessible results | Verify selected output access | Open actual produced Process artifacts from GUI. |
| Reopen after restart | IN_PROGRESS | V21 project/run records | Verify no hidden rerun after relaunch | Candidate close/relaunch/reopen proof. |
| Reuse intermediates | DONE | V21 / `asr_reuse`; preserved Recovery evidence is 12/12 passed, 0 skipped and its relevant reuse implementation is byte-identical in Candidate source A; Candidate native retry additionally reports `REUSED` without a second ASR invocation | Retain governed cache route | Bound 12/12 ledger plus Candidate native retry recorded in `PROCESS_V1_WP1_EXISTING_PROOF_AND_RECOVERY.md`. |
| Invalidation | DONE | V21 governed invalidation; preserved 12/12 Recovery matrix covers source/model/config mismatch with 0 skips, and the relevant implementation is byte-identical in Candidate source A | Retain governed invalidation route | Source-bound 12/12 matrix, exact Candidate source-A comparison, and no skipped scenario; no new rerun because runtime identity did not change. |
| Ordinary-file export | IN_PROGRESS | S01/S03/V03 persisted files | Verify selected output export | Ordinary Process files, not publication. |
| Cancel | DONE | V21 lifecycle; Candidate `candidate-v1-589ef…` native Operations proof invoked real Cancel from RUNNING, recorded CANCELLED and cleaned the owned worker without affecting an unrelated process | Retain exact lifecycle ownership route | `PROCESS_V1_RECOVERY_LIFECYCLE_PROOF.md`: candidate-bound native Operations evidence. |
| Retry after failure | DONE | V21 plus narrower S02; Candidate `candidate-v1-589ef…` native failure → Retry proof recorded FAILED then a distinct COMPLETED retry | Retain user retry separately from protective retry | `PROCESS_V1_RECOVERY_LIFECYCLE_PROOF.md`: native retry evidence; this does not close S02 protective retry. |
| Subsequent run without restart | DONE | V21; the same native Candidate process completed the retry without Integra restart and retained verified ASR reuse | Retain same-session recovery route | `PROCESS_V1_RECOVERY_LIFECYCLE_PROOF.md`: native retry evidence. |
| Timeout | IN_PROGRESS | V21 lifecycle evidence | Verify bounded timeout | Timed-out worker has truthful terminal state. |
| No orphan workers | IN_PROGRESS | V21 shutdown lifecycle | Verify cleanup across completion/failure/cancel | Candidate process audit after each case. |
| Reconcile stale RUNNING | DONE | V21 persisted state; Candidate `candidate-v1-589ef…` native startup changed controlled stale RUNNING to FAILED / STALE_RUNNING_RECONCILED without signalling the unrelated PID | Retain conservative stale reconciliation | `PROCESS_V1_RECOVERY_LIFECYCLE_PROOF.md`: candidate-bound native re-entry evidence. |
| Preserve upstream result | DONE | Issue #169 controlled multi-input Candidate run preserved the completed first source's transcript/SRT/clean/review/ASR artifacts after the later source failed; a fresh packaged bridge reread their hashes | Retain persisted-output route | Candidate multi-input and fresh-reopen evidence in `PROCESS_V1_WP1_EXISTING_PROOF_AND_RECOVERY.md`. |
| GUI-only normal use | IN_PROGRESS | P156 native bounded path | Verify complete selected scope via Finder-like GUI | No Terminal/Codex step in exit journey. |
| Selected-Capability Runtime Closure (covers preflight, clear missing-dependency error, unavailable-before-run) | BLOCKED | Current registry has availability flags but eagerly probes broad runtimes; build/manifest includes broad closure | Bounded isolation retaining selected real dependencies, exact pins, Candidate integrity | Required selected dependencies only; honest unavailable state; actionable GUI error; no raw CLI/Python error; no integrity bypass. |
| Real progress | IN_PROGRESS | Current job progress → bridge/UI path | Verify non-trivial selected run | Observable progress evidence. |
| Clear statuses | DONE | V21 run/job state records; Candidate `candidate-v1-589ef…` native Operations and Retry proofs captured RUNNING, CANCELLED, FAILED and COMPLETED states | Retain existing status vocabulary | `PROCESS_V1_RECOVERY_LIFECYCLE_PROOF.md`: visible native controlled-state evidence. |
| Select outputs before run | DONE | Issue #169 Candidate selected exactly `transcript, subtitles`; its stored plan contained only those requested outputs and the completed source emitted no Timeline/Topics/translation output | Retain selected-output planner | Candidate plan/result evidence in `PROCESS_V1_WP1_EXISTING_PROOF_AND_RECOVERY.md`. |

## D. Cross-cutting blockers

1. **Selected-Capability Runtime Closure — one bounded architectural task.** It
   covers three frozen MUSTs: preflight runtimes/models, clear missing-dependency
   error, and unavailable functions before run. The closure may check only the
   dependencies of outputs the user selected, but it must retain actual selected
   dependencies (including VideoText SRT where selected), governed pins, exact
   runtime identity, Candidate manifest validation, and fail-closed behavior.
   It cannot delete a runtime, turn a skipped check into PASS, or weaken integrity.
2. **ProcessedSource v1/result ownership.** Existing mutable result records need
   a sealed Process boundary so combined provenance, selected-output completeness,
   reopen, output access, reuse/invalidation, and downstream-failure preservation
   can be proven together. Reuse existing leases, atomic writes and CAS; no new
   database or destructive migration.
3. **Reliability carrier: #161/#162.** The existing Recovery work is one
   Process reliability requirement spanning the seven Board lifecycle rows. Its
   already recorded non-skipped reuse/invalidation evidence is retained, but it
   is not a final Process Candidate or owner acceptance. Fresh final
   Candidate-bound evidence remains required; this document does not restart or
   continue the build.

## E. Minimal execution order

The ordering is intentionally `VERIFY_EXISTING → INTEGRATE_EXISTING → BOUNDED
ISOLATION → IMPLEMENT_MISSING`. There is currently no frozen-MUST
`IMPLEMENT_MISSING` item.

1. **Verify existing user journeys and preserve Recovery evidence.** Verify the
   existing local audio/multi-file/one-YouTube/ASR retry/text derivatives/Word
   Timeline/Topic review/results/persistence/lifecycle paths against exact
   selected outputs. Record candidate-bound, non-skipped evidence. Do not repeat
   source audits or create a new Recovery program.
2. **Integrate frozen existing capabilities in coherent journeys.** One journey
   for folder/Zoom/playlist discovery; one for ASR modes/languages/diagnostics;
   one for translation; one for Topics summary/detail/review; one for combined
   multi-source outputs/corpus. Use existing pinned source capabilities and
   prove only affected Process regression/contract paths after each group.
3. **Apply bounded isolation and finalize the Process boundary.** Implement the
   Selected-Capability Runtime Closure and ProcessedSource v1; then produce one
   exact Candidate for the complete §H exit gate. If a later frozen-MUST fact
   proves truly missing behavior, stop for explicit Product Owner/implementation
   authority rather than expanding this DoD.

## F. Recovery position

#161/#162 is neither discarded nor a separate product phase. It is the
reliability carrier for Process v1: cancel, retry, same-session subsequent
success, timeout, orphan cleanup, stale RUNNING reconciliation, governed reuse/
invalidation, and preservation of successful upstream work. Existing 12/12
non-skipped ASR reuse/invalidation source evidence remains historical evidence
in the Board. It must be joined by the final Candidate gates before it can be
used for Process acceptance. No build is resumed, no repair cycle is spent, and
no prior Candidate PASS is inherited here.

## G. ProcessedSource contract target

Future `ProcessedSource v1` is an immutable projection over existing Process
artifacts, not a replacement project database or a Canonical Knowledge schema.
At minimum it must express these product requirements:

- stable ProcessedSource ID, schema version, revision/predecessor, canonical
  source identity and explicit planner/import/source identity mapping;
- source type, owned/original artifact reference, original revision and byte
  hash; normalized text and clean/translation derivatives as distinct linked
  artifacts;
- source segments and actual locators; optional aligned words/time intervals
  with aligner/runtime/config/output provenance; no invented timing;
- requested-output inventory and explicit produced/not-requested/not-applicable/
  unavailable/failed completeness states;
- basic Topics/timestamps and translations as provisional machine outputs,
  with source-span references; review decisions are explicit and not Canonical
  Knowledge creation;
- component/pin/config/model identity where attested, artifact hashes/lineage,
  quality/retry records, and an atomic immutable seal;
- save/reopen validation without silently rerunning ASR/OCR.

The contract reserves optional document fields for original page/slide numbering,
selected-page completeness, raw artifact references, and explicitly typed
PAGE/REGION/WORD precision. No page/region/word precision is fabricated now, and
adding those fields later must not require destructive redesign of Process v1.
Knowledge may later read the sealed boundary; it must not call ASR/OCR/ffmpeg or
mutate the accepted Process artifact to fill missing fields.

## H. Process v1 exit gate

On one exact Candidate, a Product Owner can use ordinary Finder-like macOS GUI
without Terminal/Codex to complete and inspect all frozen MUST outcomes:

1. representative local video and local audio yield requested TXT/SRT/Word
   Timeline/basic Topics, including protective retry where the defined trigger
   occurs, clean/review outputs, selected mode/language/quality options and
   readable diagnostics;
2. folder and Zoom flows discover supported input, present preview/selection,
   require confirmation, and process only selected items; multiple local inputs
   retain chosen order;
3. one YouTube video and playlist flows discover/select ordered items; each
   selected video receives one ProcessedSource; one unavailable/failed playlist
   item does not automatically fail peers;
4. chosen translation outputs, Topic summary/detail/review, combined transcript/
   provenance/corpus and ordinary result files appear only when selected and are
   traceable to their inputs;
5. the unified result screen opens results, the app closes/reopens them without
   unnecessary processing, and the sealed ProcessedSource validates its hashes,
   provenance, requested-output completeness and precision;
6. required runtime preflight is selected-capability scoped; missing required
   dependencies and unavailable capabilities are truthful/actionable before run;
   Candidate/runtime/pin integrity remains fail-closed;
7. controlled cancel, failure/retry, same-session subsequent success, timeout,
   orphan cleanup, stale-RUNNING reconciliation, reuse/invalidation and upstream
   preservation pass with non-skipped candidate-bound evidence;
8. exact Candidate manifest/bundle integrity, relevant Process regressions and
   GitHub Quality Gate are green; then the Product Owner explicitly accepts this
   frozen scope. Technical green never substitutes human acceptance.

## I. Vertical control rule

Every future implementation WP must state all four fields:

`PRODUCT TARGET / CURRENT→TARGET TRANSITION / WHY NOW / DETOUR + RETURN CONDITION (if any)`.

A WP is prohibited when it does not directly advance a frozen Process v1 outcome
or remove a proven blocker in §§C–D. A detour is permitted only when it has an
explicit return condition to the affected Process outcome. New capability scope,
including BookText/Process Documents or Topic hierarchy, requires a new explicit
Product Owner decision before it can enter the Board or gate.

## Proposed next execution packages — not created

1. **Existing Process proof and Recovery ledger:** candidate-bound verification
   of frozen existing paths and recorded reliability scenarios.
2. **Selected Process integrations:** folder/Zoom/playlist discovery, ASR and
   translation controls/outputs, Topic outputs/review, and multi-source results.
3. **Process closure and final acceptance:** Selected-Capability Runtime Closure,
   ProcessedSource v1, one final Candidate, whole §H gate and owner acceptance.

No merge, deployment, implementation Issue, build, test, Candidate, or Recovery
continuation is created by this document.
