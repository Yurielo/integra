# Process v1: owner scope and completion map

Date: 2026-09-22. Status: `PROCESS_V1_SCOPE_MAPPED` — proposal for Product Owner
review only, not planning authority, a Completion Contract, a roadmap, or
implementation authorization.

## 1. Authority, method, and exact selection

The authority for this document is the completed owner workbook
`Integra_Process_v1_scope_selection.xlsx`, SHA-256
`22ddb5c5c46c850a2c5923607bab0b3ad5faef3de5ef20019255ba70c5718137`.
It was read without modification. Mapping is limited to the already published
[source-parity inventory](SOURCE_PRODUCT_INTEGRA_PARITY_CURRENT.md) and
[staged architecture review](INTEGRA_STAGED_ARCHITECTURE_PROCESS_KNOWLEDGE_STUDIO.md).
No new source-capability audit, source probing, build, test, Candidate, GUI run,
Recovery continuation, or product change was performed.

**Workbook fact:** the filled `Process v1` sheet contains **51 `MUST`**,
**5 `OPTIONAL`**, and **12 `LATER`** choices (68 rows). This differs from the
instructional recount of 52 MUST. The file is authoritative, so this document
records 51, not a fabricated 52. The five OPTIONAL rows are exactly four
audio-analysis rows and History. The subsequent explicit Product Owner domain
correction moves Topic hierarchy to LATER, user-facing SRT and translated SRT
to Studio, and Review TXT/Evidence interaction to Knowledge. The active Process
scope is therefore 47 MUST, 5 OPTIONAL and 16 LATER/out-of-phase entries. The
separate BookText sheet has 17 capability rows and every choice cell is blank; all 17 are therefore
`OUT_OF_PROCESS_V1_PENDING_SEPARATE_DECISION`, not `LATER`.

`CURRENT PARITY` preserves the published source row status, including `UNKNOWN`.
It is not a claim that an item has passed a current packaged user journey. When
several source rows apply, their IDs/statuses remain explicit rather than being
collapsed into a new status. `—` means an Integra user composition has no
one-to-one source-product inventory row; it is not evidence that the function
is absent.

`REQUIRED ACTION` is the single next **primary** action for that owner item.
The cross-cutting Process isolation gates in §5 can also block several items;
they are not duplicated into every table row. `OWNER_CLARIFICATION` is used only
when published evidence does not establish a source-equivalent behavior or a
meaningful acceptance boundary. It does not override the owner's `MUST` choice.

## 2. Frozen owner selections outside the completion table

### LATER — frozen out of Process v1

| Workbook # | Owner item |
| --- | --- |
| 9 | User-facing SRT subtitles — **Studio**; Process retains timing/SRT internally only where required for alignment, Word Timeline, provenance, or a downstream Studio consumer. |
| 14 | Review TXT / Evidence interaction — **Knowledge**; Process retains readable cleaned text, while Evidence/Canonical Evidence and its human confirmation are frozen for Knowledge. |
| 21 | User-facing translated SRT — **Studio**; Process retains translated text plus timing/provenance required downstream. |
| 56 | Topic hierarchy |
| 57 | Thematic video clips |
| 58 | Blur |
| 59 | Watermark |
| 60 | Video speed variants |
| 61 | Filler mute |
| 62 | Dereverb |
| 63 | Dubbing / TTS |
| 64 | Marketing materials |
| 65 | Knowledge / Evidence / relations |
| 66 | Obsidian / OneDrive publication |
| 67 | Social adapters |
| 68 | Learning / Assistant |

These selections freeze Studio, Knowledge, publication, and downstream work
out of this Process v1 proposal. Existing code, internal timing/provenance
artifacts, and historical evidence are not removed or relabeled as missing.

### OUT_OF_PROCESS_V1_PENDING_SEPARATE_DECISION — BookText sheet left blank

PDF text extraction; OCR PDF; OCR images/scans; PPTX extraction; DOCX extraction;
TXT/Markdown import; page inclusion; page exclusion; page/region provenance;
raw geometry/words/tables/lists; searchable PDF; DjVu; ordered multi-image book;
illustration extraction/descriptions; OCR-engine choice; complex-table
reconstruction; and semantic chapters/outline. None is `LATER`, `MUST`, or
`OPTIONAL` in this map. Their source inventory correspondence remains available
for a future separate owner decision; this document does not infer one.

## 3. MUST — completion correspondence

Acceptance shorthand: **P** = exact packaged Candidate evidence followed by
scope-bound owner acceptance; **I** = bounded integration then P; **A** =
bounded architecture proof with no integrity bypass then P; **C** = a narrow
written clarification, then the resulting P/I/A route. These shorthands do not
alter current governance or authorize work.

| OWNER ITEM | PRIORITY | SOURCE CAPABILITY ID(S) | CURRENT PARITY | CURRENT INTEGRA PATH | REQUIRED ACTION | ACCEPTANCE EVIDENCE NEEDED |
| --- | --- | --- | --- | --- | --- | --- |
| Local video | MUST | S01, V03 | PARITY_PROVEN; PARITY_PROVEN | `app.execute_run → media.run_job → ASR` with internal timing/SRT where required | NONE_ALREADY_PROVEN | P156 bounded Russian-video result; scope-bound owner acceptance. |
| Local audio | MUST | S01, V01, V03 | PARITY_PROVEN; VERIFY_EXISTING; PARITY_PROVEN | Same local-media plan/ASR path with internal timing/SRT where required | VERIFY_EXISTING | P for real local audio, readable TXT and provenance; no audio result inferred from video P156. |
| Several video/audio files in one run | MUST | S06 | VERIFY_EXISTING | Source-first plan sequentially processes selected sources | VERIFY_EXISTING | P for ordered multi-file packaged run, per-source results and truthful partial failure. |
| Folder with materials | MUST | S06 (partial only) | VERIFY_EXISTING | Current source selection/plan; no published generic-folder-discovery equivalence | OWNER_CLARIFICATION | C: select-files vs automatic discovery/selection rules; then P/I. |
| Zoom folder | MUST | S07 | INTEGRATE_EXISTING | No Zoom-specific discovery in current planner | INTEGRATE_EXISTING | I for selected source discovery and GUI result; then P. |
| YouTube — one video | MUST | S08 | VERIFY_EXISTING | `youtube_runtime.download_video → app.execute_run → media.run_job` | VERIFY_EXISTING | P for permissible real/non-private URL, source record and resulting artifacts. |
| YouTube playlist | MUST | S08, S10 (partial only) | VERIFY_EXISTING; INTEGRATE_EXISTING | Current evidence covers one URL, not playlist expansion/completeness | OWNER_CLARIFICATION | C for membership/order/failure/completeness semantics; then I/P. |
| Automatic transcript → TXT | MUST | S01 | PARITY_PROVEN | `seminartext_asr_runtime.transcribe → pinned CLI` | NONE_ALREADY_PROVEN | P156 bounded result; scope-bound owner acceptance. |
| Word Timeline | MUST | S19 | VERIFY_EXISTING (aligned subset accepted; full Evidence linkage not) | `word_timeline_runtime → bundled alignment worker` | VERIFY_EXISTING | P for alignment, hash binding, reopen/navigation; no Canonical Evidence claim. |
| Careful / enhanced ASR mode | MUST | S04 | INTEGRATE_EXISTING | Current adapter has no careful selector | INTEGRATE_EXISTING | I for bounded parameter/UI/output provenance; then P. |
| Protective retry | MUST | S02 | VERIFY_EXISTING | Pinned SeminarText CLI quality gate/retry | VERIFY_EXISTING | P showing trigger → retry in packaged path; normal invocation is insufficient. |
| Clean TXT | MUST | S03 | VERIFY_EXISTING | `media.run_job` persists cleaned transcript/quality report | VERIFY_EXISTING | P for readable derivative linked to source transcript. |
| Source-speech language choice | MUST | V02 | INTEGRATE_EXISTING | Generic media composition; source-language control not connected | INTEGRATE_EXISTING | I for supported selection and runtime provenance; then P. |
| ASR quality settings | MUST | S04, V02 | PARITY_PROVEN; PARITY_PROVEN | One neutral `Режим распознавания` selector: `Обычный` default or `Тщательный`; requested/executed mode and fixed source-speech language persist through the Process path | NONE_ALREADY_PROVEN | Current Candidate proof in `PROCESS_V1_ASR_QUALITY_SETTINGS_PROOF.md`. Protective retry is automatic safety logic, not another selectable quality setting. |
| ASR quality diagnostics | MUST | V02, S02 | DONE | Integra-owned persisted diagnostic contract and normal-user result rendering; requested/executed mode and language remain explicit | NONE | Candidate proof in `PROCESS_V1_ASR_DIAGNOSTICS_PROOF.md`; protective retry remains automatic safety logic. |
| Transcript translation | MUST | S14, V05 | DONE | Integra-owned fixed `ru` to `en` Process result, reusable completed transcript, provenance and readable cue result | NONE | `PROCESS_V1_TRANSCRIPT_TRANSLATION_PROOF.md`; target selector and translated TXT remain separate outcomes. |
| Translation-language choice | MUST | V06 | PROPOSED_BASELINE | Normal Process control exposes the currently valid English target, keeps it distinct from source speech language, and persists requested/executed target provenance | NONE | `PROCESS_V1_TRANSLATION_LANGUAGE_CHOICE_PROOF.md`; pending Product Owner acceptance and CURRENT promotion. |
| Translated TXT | MUST | V06 | INTEGRATE_EXISTING | Current worker saves JSON, not user-facing TXT | INTEGRATE_EXISTING | I for readable TXT, source association and P. |
| Topic translation | MUST | S15 | INTEGRATE_EXISTING | Topic translation not connected | INTEGRATE_EXISTING | I for translated headings/references with provisional authority, then P. |
| Topics + timestamps | MUST | S12 | PARITY_PROVEN | `seminartext_topics_worker` after aligned transcript | NONE_ALREADY_PROVEN | P156 Topics/timestamps result; scope-bound owner acceptance. |
| Summary of each Topic | MUST | S12 (partial), S13 | PARITY_PROVEN; INTEGRATE_EXISTING | Basic Topics path; no published selected summary/detail composition | INTEGRATE_EXISTING | I for defined summary field and source-span binding; then P. |
| Topic detail selection | MUST | S13 | INTEGRATE_EXISTING | Detail selector not connected | INTEGRATE_EXISTING | I for bounded selection/config evidence; then P. |
| Edit/confirm Topics | MUST | S20 | VERIFY_EXISTING | `prepare/apply-knowledge-review → topic review runtime` | VERIFY_EXISTING | P for dialog, exact-fragment decision and authority status. Owner MUST prevails over staged allocation only for this scope. |
| Ordered processing | MUST | S06 | VERIFY_EXISTING | Ordered source plan | VERIFY_EXISTING | P for configured order, result ordering and failure behavior. |
| Combined transcript | MUST | S11 | INTEGRATE_EXISTING | ASR adapter calls single-source `--only video_001`; no combined-clear output | INTEGRATE_EXISTING | I for chronological output/input-completeness boundary; then P. |
| Provenance in combined result | MUST | S11 | INTEGRATE_EXISTING | No combined manifest/output path | INTEGRATE_EXISTING | I for source/time links in combined artifact and P. |
| Corpus from several materials | MUST | S10 | INTEGRATE_EXISTING | No runtime corpus output; sequential queue is not corpus | INTEGRATE_EXISTING | I for explicit membership/completeness/provenance; then P. |
| Unified results screen | MUST | — (Integra composition) | Current bounded P156 composition; no source-row equivalent | `macOS GUI → bridge → result actions` | VERIFY_EXISTING | P for all owner-selected Process outputs in one honest result view; unavailable items visible. |
| Open result from Integra | MUST | S03, V03 (partial) | VERIFY_EXISTING; PARITY_PROVEN | GUI output actions open persisted artifacts | VERIFY_EXISTING | P for selected produced artifacts from result screen; no BookText scope inferred. |
| Reopen after restart | MUST | V21 | VERIFY_EXISTING | Integra-owned project/run history and result records | VERIFY_EXISTING | P for close/relaunch/reopen without rerun and valid source binding. |
| Reuse intermediate results | MUST | V21 | VERIFY_EXISTING | `asr_reuse` / governed job records | VERIFY_EXISTING | P for valid reuse and retained identity evidence. |
| Invalidation after changes | MUST | V21 | VERIFY_EXISTING | Governed reuse/invalidation path | VERIFY_EXISTING | P for source/model/config mismatch invalidation, not a skipped test. |
| Export results to ordinary files | MUST | S01, S03 | PARITY_PROVEN; VERIFY_EXISTING | Persisted readable TXT/derivatives and GUI output actions | VERIFY_EXISTING | P for owner-selected readable Process artifacts as ordinary files; not publication/BookText export or Studio subtitle export. |
| Cancel active processing | MUST | V21 | VERIFY_EXISTING | Run/job cancellation lifecycle | VERIFY_EXISTING | P for cancellation, final state, saved diagnostics and no false success. |
| Retry after failure | MUST | V21, S02 | VERIFY_EXISTING; VERIFY_EXISTING | Lifecycle retry; S02 is narrower automatic quality retry | VERIFY_EXISTING | P for controlled failure → retry; distinguish user retry from S02. |
| Next run without Integra restart | MUST | V21 | VERIFY_EXISTING | Reuse/shutdown/runtime lifecycle | VERIFY_EXISTING | P for controlled failure then subsequent same-session success. |
| Timeout of stuck process | MUST | V21 | VERIFY_EXISTING | Worker lifecycle/timeout controls | VERIFY_EXISTING | P for bounded timeout, terminal status and recovery. |
| Background-process cleanup | MUST | V21 | VERIFY_EXISTING | Shutdown/orphan lifecycle | VERIFY_EXISTING | P for no orphan workers after complete/failure/cancel. |
| Reconcile stale RUNNING | MUST | V21 | VERIFY_EXISTING | Persisted run-state reconciliation | VERIFY_EXISTING | P for restart from stale RUNNING without false completion/lost artifacts. |
| Preserve successful upstream results | MUST | V21 | VERIFY_EXISTING | Persisted outputs/downstream failure handling | VERIFY_EXISTING | P for downstream failure preserving valid upstream artifact/reuse eligibility. |
| Ordinary GUI-only use | MUST | — (Integra composition) | P156 bounded native path; no general source-row equivalent | Native `Integra.app → bridge → production orchestration` | VERIFY_EXISTING | P through Finder-like packaged GUI with no Terminal/Codex steps. |
| Preflight runtimes/models | MUST | — (Integra composition) | Current registry preflights broad runtime set | `capabilities.build_capability_registry` | BOUNDED_ARCHITECTURAL_ISOLATION | A proving selected closure preflights required dependencies only, with exact runtime identity. |
| Clear missing-dependency error | MUST | — (Integra composition) | Current availability flags; user-message quality not accepted | Capability registry/GUI status surfaces | BOUNDED_ARCHITECTURAL_ISOLATION | A + P: missing required dependency is actionable; no raw Python/CLI error reaches normal GUI. |
| Real progress | MUST | — (Integra composition) | Existing job progress/state path; no accepted current proof | `user_media` job progress → bridge/UI | VERIFY_EXISTING | P with observable progress across a non-trivial selected Process run. |
| Clear processing statuses | MUST | V21 (lifecycle correspondence) | VERIFY_EXISTING | Run/job state records → bridge/UI | VERIFY_EXISTING | P for Processing/Completed/Failed/Cancelled including controlled paths. |
| Choose needed outputs before run | MUST | — (Integra composition) | Current source-first capability plan/output selection | `capabilities.build_plan → app.execute_run` | VERIFY_EXISTING | P for chosen closure only, with config/result evidence. |
| Unavailable functions shown before run | MUST | — (Integra composition) | Availability flags exist but probe unrelated runtimes eagerly | `capabilities.build_capability_registry` → GUI | BOUNDED_ARCHITECTURAL_ISOLATION | A + P: truthful pre-execution availability; optional absence cannot block selected Process work. |

## 4. OPTIONAL — completion correspondence

OPTIONAL items do not block `PROCESS V1 USER_ACCEPTED` unless the owner later
elevates them. If included because their verification is low-risk, the same
evidence standard applies; they cannot be counted through a skipped test.

| OWNER ITEM | PRIORITY | SOURCE CAPABILITY ID(S) | CURRENT PARITY | CURRENT INTEGRA PATH | REQUIRED ACTION | ACCEPTANCE EVIDENCE NEEDED |
| --- | --- | --- | --- | --- | --- | --- |
| Loudness measurement | OPTIONAL | V13 | VERIFY_EXISTING | `audio_analysis → VideoText media worker → original analyze` | VERIFY_EXISTING | P for actual selected analysis output and units. |
| Noise analysis | OPTIONAL | V13 | VERIFY_EXISTING | Same analysis path | VERIFY_EXISTING | P for actual noise result; not a claim of dereverb. |
| Pause analysis | OPTIONAL | V13 | VERIFY_EXISTING | Same analysis path | VERIFY_EXISTING | P for pause result with source/time binding. |
| Audio-quality diagnostics | OPTIONAL | V13 | VERIFY_EXISTING | Same analysis path | VERIFY_EXISTING | P for clear diagnostic result; not substituted ASR quality. |
| Processing history | OPTIONAL | V21 | VERIFY_EXISTING | Integra-owned project/run history | VERIFY_EXISTING | P for saved history/reopen within final Process Candidate. |

## 5. Exact summary and critical blockers

Counts below are **owner-facing MUST items**, not source-row counts; each row is
counted once by its primary required action. Aggregated source mappings therefore
do not inflate the result.

| MUST primary action | Count | Meaning |
| --- | ---: | --- |
| NONE_ALREADY_PROVEN | 3 | Local video; automatic TXT transcript; Topics/timestamps. Proof remains bounded to P156 and requires scope-bound owner acceptance. |
| VERIFY_EXISTING | 25 | Existing selected/current path needs current packaged, exact-scope proof. |
| INTEGRATE_EXISTING | 14 | Existing source functionality or bounded adapter/output/control needs connection. |
| BOUNDED_ARCHITECTURAL_ISOLATION | 3 | Selected preflight, actionable missing dependencies, and truthful prior availability need the shared closure fix. |
| IMPLEMENT_MISSING | 0 | No owner MUST is established as a missing source algorithm by published evidence. |
| OWNER_CLARIFICATION | 2 | Generic folder behavior and playlist semantics lack an unambiguous published correspondence. |
| **Total active Process MUST after owner scope corrections** | **47** | The original 51 workbook MUST rows are reduced by Topic hierarchy (LATER), user-facing SRT and translated SRT (Studio), and Review TXT/Evidence interaction (Knowledge). |

All five OPTIONAL rows are `VERIFY_EXISTING`: four V13 audio-analysis views and
V21 History. They do not change the MUST total.

### Process v1 critical blockers — cross-cutting only

These are not capability-specific WPs. Each prevents several MUST items from
being honestly accepted at once.

1. **Immutable ProcessedSource v1 boundary and result ownership.** A sealed
   revision over existing artifacts must preserve source identity, hashes,
   normalized/derived text distinction, timing/page precision, requested-output
   completeness, and reopen behavior. It unblocks shared proof of results,
   combined provenance/corpus integration, result opening/export, restart,
   reuse/invalidation, and preservation after downstream failure. Reuse current
   leases, atomic writes, and CAS protections; do not create a new database or
   destructively migrate data.
2. **Selected-capability preflight and truthful Process package closure.** The
   current registry probes media, ASR, ffmpeg, Topics, alignment, translation
   and BookText broadly; build/manifest also package downstream Review and the
   full runtime closure. Bounded isolation must retain actual VideoText SRT,
   preserve byte/hash validation, and stop an unselected missing runtime from
   blocking selected Process. It covers media inputs, ASR/SRT/Timeline/Topics/
   translation, the three UX preflight MUSTs, and a truthful packaged Candidate.
   It must not bypass the Candidate manifest or claim VideoText is unnecessary.
3. **One Process gate ledger for lifecycle evidence.** Required lifecycle cases
   must be candidate-bound and non-skipped: cancel, failure/retry, subsequent
   same-session success, timeout, orphan cleanup, stale RUNNING,
   reuse/invalidation, and upstream retention. Distinguish protective retry from
   user retry. Existing #161/#162 evidence is neither rerun nor changed here;
   its final Candidate proof remains required.

## 6. Minimal dependency-ordered proposal to Process v1 USER_ACCEPTED

This is an ordering proposal for owner review, not authorization to implement,
create issues, alter the roadmap, or continue Recovery.

1. **Resolve the three narrow clarifications**: generic folder behavior,
   YouTube playlist semantics, and required Topic hierarchy meaning. Separately
   decide the blank BookText sheet. This fixes acceptance vocabulary without
   treating 17 unselected BookText functions as later work.
2. **Prove the reversible Process isolation seam** proposed in staged review:
   current full-manifest frozen-runtime reuse first; otherwise an additive,
   fail-closed declared closure. Keep selected VideoText SRT and integrity
   checks. Do not run a pilot until separately authorized.
3. **Establish ProcessedSource v1 and the bounded closure/ledger**, then prove
   four already-proven and 26 VERIFY_EXISTING MUST items on the exact Candidate.
   OPTIONAL V13/V21 work stays non-blocking.
4. **Connect 15 existing integrations** in coherent groups: discovery/playlist;
   ASR selection/diagnostics; translation outputs; Topic detail/review/summary;
   multi-source combination/corpus. Reuse pinned source paths, then repeat only
   impacted Process evidence plus contract/reopen/lifecycle gates.
5. **Run one final Process owner gate** on one exact Candidate: frozen MUST
   scenarios, lifecycle ledger, ProcessedSource save/reopen, packaged Finder-like
   GUI, runtime/manifest integrity, and explicit owner acceptance. OPTIONAL,
   LATER and BookText boundaries remain frozen.

`IMPLEMENT_MISSING` deliberately has no owner-MUST slot. If a later clarification
maps a MUST to missing source behavior, stop and seek scope/implementation
authority rather than adding it silently to this proposal.

## 7. Non-authority and handoff

This map does not modify Product Definition, CURRENT, roadmap, component pins,
BookText, Recovery #161/#162, existing Issues, or cited documents. It does not
declare a Candidate, technical green, merge eligibility, or `USER_ACCEPTED`.
It maps current owner selections to existing evidence so the Product Owner can
freeze a Process v1 Definition of Done without deciding source-code architecture.
