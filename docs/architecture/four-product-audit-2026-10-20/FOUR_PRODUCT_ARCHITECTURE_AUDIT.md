# Four-product architecture audit

Audit date: **2026-10-20, Europe/Istanbul**. Status: **the Product Owner accepted the adapter-first planning direction and the seven boundary clarifications; implementation remains PROPOSED**. Planning home: Integra, Issue [#277](https://github.com/Yurielo/integra/issues/277). This package changes documentation only and does not amend accepted governance, CURRENT, source pins or executable roadmaps.

## Evidence method and vocabulary

**FACT** means inspected pinned source/schema/test, live GitHub record, read-only local observation or an explicitly identified executed check. **INFERENCE** is a conclusion from those facts. **PROPOSAL** is future work without implementation/adoption authority. **UNVERIFIED** names a proof gap. Historical reports remain attributed; they are not fresh test results.

Capability labels are separate, combinable dimensions: **IMPLEMENTED** code exists in the audited canonical revision; **TESTED** named automated coverage or recorded execution exists (the row states which); **ACCEPTED** an exact contract/release/sample has attributable acceptance; **PARTIAL** a bounded implementation or missing outcome; **PLANNED** declared future work; **DEPRECATED** superseded execution path; **UNKNOWN** insufficient evidence. A test file alone is coverage evidence, not a fresh PASS. An issue being closed or a PR merged does not establish semantic acceptance or installed-runtime parity.

The audit used immutable exported snapshots and read-only GitHub metadata/comments. Production/dirty source trees and existing worktrees were left intact. No user media, protected datasets or Gold were opened; no new inference benchmark, dependency/model installation, production app launch/build/promotion, migration, source change or merge occurred. Only planning documentation, an isolated planning worktree and the authorized planning Issue/PR are delivered. Deterministic tests use isolated fixtures; validation results are recorded below.

## FACT — accepted planning direction and retained gates

The Product Owner accepted this package's adapter-first direction and seven review clarifications: initial versioned sidecar manifests with explicit read-only handoff/import; an opt-in rebuildable discovery index distinct from physical storage; four distinct translation profiles with exact compatibility identity and no transferred semantic acceptance; opt-in lightweight host reservations that work while Integra is closed and never evict a foreign Ollama model by name alone; non-blocking M0–M7 planning that preserves #257 and CURRENT/K1/K2 authority; increment-specific M7 readiness; and no forced shared core, migration, schema replacement, engine/model change or product-code work.

This is acceptance of a documentation-level planning direction. It does **not** authorize M1–M7 implementation, a product release, a semantic decision, a CURRENT promotion, a change to Product Rules, or a replacement of existing native authority. Each future vertical slice still needs its own bounded scope, validation and applicable owner acceptance.

## FACT — verified repositories and canonical mains

| Product | Actual local repository / active checkout | Canonical GitHub main SHA | Active checkout HEAD / state |
| --- | --- | --- | --- |
| SeminarText | `/Users/yurielokhin/Documents/seminartext` | `637199c91b1d1141503a8ca6c8abeaf418baf95b` | `9ce002236a974c7766a43905b85127dda8143705`; `codex/issue-68-real-multi-source-vertical-slice`; two untracked documents |
| BookText | `/Users/yurielokhin/AITools/booktext` | `8418319021516323cbf71b2b0c59538840590f2b` | `974cfbfc3e39afab9f0566d371e604d2571e2c9c`; `codex/issue-50-native-review`; modified table reconstruction and two untracked research tools |
| VideoText | `/Users/yurielokhin/Documents/Codex/videotext-simple-project-home` | `f6efe0b2504550aa51d689e6712e7472144d7599` | `c1a83ebfec55a664b65bfec1c6ac4ddf8c8f02ee`; `codex/simple-transcription`; untracked architecture-review directory |
| Integra | `/Users/yurielokhin/Documents/integra` | `2d29bc63d850437c1d7b254f11797fad073f84e1` | `a6f93b43b7b7c943482cace166162ec0bbe171f7`; `codex/review-evidence-knowledge-workflow`; modified source/state and untracked tests/documents |

All remotes were verified as the corresponding `https://github.com/Yurielo/<repository>.git`; all default branches were verified as `main`. The requested `/Users/yurielokhin/AI/BookText` is absent. `/Users/yurielokhin/Documents/videotext` is an uncommitted Git shell without the expected remote. The chat workspace `/Users/yurielokhin/Documents/ChatGPT/Integra` was empty, not the Integra repository. The clean documentation worktree is `planning-277` under that workspace, branched from the pinned Integra main; no dirty development worktree contains these documents.

## FACT — governance and planning authority

Integra `AGENTS.md`, `DEVELOPMENT_WORKFLOW.md`, product definition, architecture, state, autonomous policy and agent-team contract were read at canonical main. They permit bounded repository planning/docs under an exact owner instruction and require issue-first isolation, governance/full tests/diff verification. The original audit instruction authorized a planning Issue/PR while forbidding implementation and merge. The later Product Owner acceptance authorizes completing this documentation-only PR lifecycle, including a governed merge after the actual policy gates pass; it still forbids M1–M7 implementation. Thus Integra is an appropriate **proposal home**, without acquiring authority to rewrite other products' contracts. The proposed files deliberately do not edit `docs/ROADMAP.md`, `state/*` or Product Rules. Existing #257 is linked rather than replaced or duplicated as implementation scope.

SeminarText's full Product Rules Registry has ACTIVE PR-001 through PR-014; all apply to this architecture review's semantic, provenance, governance, autonomy and completion boundaries. BookText and VideoText do not have equivalent Product Rules registry files in the audited snapshots; their accepted instructions/contracts apply locally. Do not import SeminarText policy wholesale into them. BookText's accepted handwriting-exclusion rule is recorded in `DEVELOPMENT_PLAN.md` and must be preserved.

```text
PRODUCT_RULES_READ: YES
APPLICABLE_PRODUCT_RULES: PR-001, PR-002, PR-003, PR-004, PR-005, PR-006, PR-007, PR-008, PR-009, PR-010, PR-011, PR-012, PR-013, PR-014
PRODUCT_RULE_CONFLICTS: NONE in the recommended proposal
```

**Rejected conflicting interpretations:** assigning Canonical Knowledge authority to Integra merely because its UI is named Knowledge; automatically accepting machine semantics; rewriting directed raw timing into positive intervals; making full transcript human verification mandatory for all processing; weakening BookText handwriting exclusion; retiring SeminarText because VideoText wraps it; treating this roadmap as authority to implement future stages. None is adopted. A future owner choice to change a native contract must explicitly supersede it in that repository.

## FACT — current architecture, not only documented intent

**SeminarText:** shell CLI plus Python modules, whisper.cpp/Silero/FFmpeg ASR, selected-attempt timing packages, per-source and combined transcript derivatives, transcript/evidence/Knowledge schemas and review admission. WhisperX alignment-only is a separate controlled timing capability. Legacy translation/media helpers still exist. This is not a transcript-only owner.

**BookText:** Python document/OCR Core with SwiftUI native client and local JSONL machine protocol 1.1. PDF native/scan routing, Surya OCR and independent Apple Vision QA feed raw results, reversible review/final text, CDM, TranslateGemma translation and exports. The fixed pipeline is PROCESS → REVIEW_POLICY → FINAL_BUILD → CDM → TRANSLATE → EXPORT; it is not a general orchestration platform. Supported input is PDF/DjVu/images; DOCX/PPTX/TXT/Markdown are not evidenced BookText input formats.

**VideoText:** Swift application with project schema v8, immutable source/translation/topic revisions and media adapters. Ordinary Simple ASR invokes bundled SeminarText `cf7a8445fa9f9dffc62b7ae24062e80475a3d223`; the retained Swift segmented recognizer is not the selected ordinary path. Current selected-timing TranslateGemma and legacy cue-ownership translation are different profiles. Subtitles and media operations are implemented; dubbing activation is disabled.

**Integra:** native macOS presentation over Python control-plane/domain modules, source registry, JobStore, Project Lease, capability planning, hashed artifacts, review, cross-navigation and publication. Normal Process uses pinned SeminarText ASR/Topics, an Integra WhisperX adapter, Integra-owned TranslateGemma and pinned VideoText media workers. A bounded BookText worker handles OCR; it does not import the full document/CDM/review package. R3 local JSONL is an accepted contract, but native execution also uses direct bounded adapters; do not claim every current call uses one uniform R3 worker.

Current source pins are distinct from repository main: Integra `seminartext_runtime.py` pins `13644d262776aacdf36221b9a9fc7ebd0a7c0737`, `videotext_runtime.py` records `2e098d1705b6815628bee1e023f4742718eabf02`, and `booktext_runtime.py` pins `46396649214275eb18054b670a842bace02d02e1`. Historical `component_baselines_v1.json` still records SeminarText `a94936c…` for the earlier R1 baseline. Updating a pin is a new compatibility exercise, not an audit correction. Canonical source improvements cannot be credited automatically to installed Integra.

## FACT — worker and persistence boundaries

| Product boundary | Transport / payload | Compatibility, resume and authority |
| --- | --- | --- |
| SeminarText | CLI commands and native immutable artifact packages; Python evidence/review modules for pinned consumers | Selected timing v1 plus evidence/Knowledge validators; complete-source ASR marker reuse differs from evidence/alignment resume. No universal network ASR service is selected. |
| BookText | Local JSONL machine protocol 1.1; logical artifact map, CDM 1.0 and translation 1.1 | Unknown major rejected; documented minor extension handling differs from Integra exact negotiation. Fixed pipeline/checkpoints and project lock remain BookText-owned. A wrapper must negotiate its exact supported mapping. |
| VideoText | In-process Swift adapters, bundled ST CLI, native project schema v8 and revision records | Prior project versions supported by native migration; selected-timing/hash/review validators govern imports. Product compatibility code is not permission for an ecosystem converter to discard provenance. |
| Integra | Accepted UTF-8 JSONL R3 process protocol plus current direct bounded Python/compiled-worker adapters | Exact protocol/schema intersection; job idempotency and typed cancellation/error states; source-read-only versus Integra-store artifacts. R6 workers declare no intra-job resume; controller prefix resume is separate. Current native paths must be checked individually. |

The source projects remain independently owned. An adapter owns its exchange/operation receipt, not the original payload or imported ReviewDecision. Migration is copy-on-write and activation follows byte/schema/provenance validation. No common transport currently makes all producer payloads interchangeable.

## FACT — capability matrix

In the evidence column, “recorded” denotes retained tests/real runs; “covered” denotes inspected tests. Installed state is addressed separately, not implied by this matrix.

| Product/capability | Classification | Automated evidence | Real material / Product Owner acceptance and limit |
| --- | --- | --- | --- |
| ST local audio/video ASR RU/explicit EN | IMPLEMENTED, TESTED | `test_transcribe_language.py`, ASR quality tests | #129/#130 real EN sample; not automatic language detection or all project workflows |
| ST chunk/VAD/protective retry | IMPLEMENTED, TESTED | `test_asr_quality_gate.py`; #143 recorded 366 tests | Bounded real loop cases; safe warnings are not universal accuracy |
| ST selected TXT/SRT/JSON from same attempt | IMPLEMENTED, TESTED, ACCEPTED | `test_selected_whisper_timing.py` | #131/#132 exact owner acceptance; one-pass real EN evidence |
| ST prepared vs selected timing ranges | IMPLEMENTED, TESTED | #133/#134 fixtures and real LED | Preserve padded/raw selected envelope; no clamping |
| ST directed raw tokens / no `-nt` | IMPLEMENTED, TESTED, ACCEPTED interpretation | #137/#138 argv/timing coverage | Owner explicitly accepts directed intervals; later VideoText import passed |
| ST combined clear transcript | IMPLEMENTED, TESTED | `test_project_combined_clear.py` | #122 closed; bounded local-source/date-order composition, not universal manual ordering |
| ST project language / durable ASR resume | PARTIAL | General parser vs project parser and marker paths | Project parser lacks `--language`; complete-source skip, not durable chunk resume |
| ST transcript revisions/selective assurance | IMPLEMENTED, TESTED, ACCEPTED contract | Evidence schema/validation tests | PR-012 permits honest machine evidence; semantic decisions separate |
| ST Canonical Word Timeline | TESTED, ACCEPTED controlled MVP; PARTIAL product integration | Controlled 1,434-word evidence, 1,432 aligned / 2 null | State says production integration incomplete; not native selected tokens |
| ST Evidence/Knowledge admission/review | IMPLEMENTED, TESTED, ACCEPTED contracts | `reviewed_knowledge_admission.py`, schema validators | #68 real semantic authoring remains open; canonical semantic completion not inferred |
| ST native PDF/PPTX / YouTube helpers | IMPLEMENTED, PARTIAL | CLI extraction/download paths, mocked tests | Limited extraction; no bound OCR engine or fresh live-source proof |
| ST legacy Qwen translation | IMPLEMENTED legacy; UNKNOWN quality/acceptance | No focused translation tests located | Excluded from proposed path; no provenance-rich TranslateGemma contract |
| BT PDF native/scan routing | IMPLEMENTED, TESTED | `test_automatic_extraction.py` | #117 real native/continuity evidence; final owner visual acceptance pending |
| BT PDF/DjVu/images OCR and Vision QA | IMPLEMENTED, TESTED | OCR safety/review tests | Historical real OCR/resume evidence; not rerun here |
| BT handwriting exclusion | PARTIAL | Inspected bypass/fallback code | Accepted policy exists; universal enforcement not established |
| BT reversible review/CDM/blocks/assets | IMPLEMENTED, TESTED | CDM/review tests; 43 focused tests in this audit include CDM | Source-preserving evidence; unknown table structure stays unknown |
| BT document translation EN↔RU | IMPLEMENTED, TESTED, ACCEPTED bounded release | `test_translation.py`; focused tests executed here | #131 owner accepted samples; not every book/domain/table |
| BT glossary/quality/checkpoint resume | IMPLEMENTED, TESTED | Mocked provider, fingerprint/partial-resume tests | #131/#116 real interrupted translation evidence |
| BT translation artifact Human Review | PARTIAL | Flags, validation and pipeline pause | No complete per-revision decision/edit mutation found; release acceptance differs |
| BT sequential pipeline/exports | IMPLEMENTED, TESTED | Pipeline/export tests | #116 closed, four-page real PDF→translation→DOCX and cancel/resume recorded |
| BT durable project history | IMPLEMENTED, TESTED; acceptance UNKNOWN | History tests | #114 open; don't rebuild code or close issue from test existence |
| BT rich Integra/Knowledge handoff | PARTIAL, PLANNED | Draft candidate-shape tests | No full CDM/region/review/idempotent Knowledge roundtrip proved |
| BT Qwen translation execution | DEPRECATED | TranslateGemma-only guard | #131 supersedes old fix plan; historical artifacts remain readable |
| VT ordinary Simple ASR | IMPLEMENTED, TESTED | Core runner/import probes | Bundled ST reuse; independent VideoText engine claim false for this route |
| VT selected timing / source units | IMPLEMENTED, TESTED | SelectedTimingVerticalSlice probe | Raw reverse endpoints preserved; positive playable units separate |
| VT translated subtitles EN↔RU | IMPLEMENTED, TESTED, ACCEPTED bounded slice | Translation/ownership/review probes | #15 explicit acceptance; #9 earlier semantic failures are historical |
| VT legacy cue translation | IMPLEMENTED, TESTED, PARTIAL semantic proof | Context/ownership/checkpoint probes | Structural correctness is not full semantic parity |
| VT topics/selected variants | IMPLEMENTED, TESTED, ACCEPTED exact scope | #46 two CORE E2E and GUI evidence recorded | Owner PASS explicitly excludes transcript accuracy |
| VT cuts/burn/speed/blur/mute/watermark/audio | IMPLEMENTED, TESTED | Media probes, historical release reports | No fresh feature-by-feature media/listening acceptance in this audit |
| VT neutral TTS/mux | PARTIAL, PLANNED activation | SpeechSynthesis probe exists | Real implementation but runtime gate disables dubbing; not released |
| VT presets | PARTIAL | Draft #49 developer probes | Independent QA/owner/release gates pending; not canonical main behavior |
| I source registry/leases/jobs/protocol | IMPLEMENTED, TESTED, ACCEPTED contracts | Governance fixtures and supported suite | Contract acceptance distinct from complete product journey |
| I ASR reuse/current Process | IMPLEMENTED, TESTED; full journey PARTIAL | `test_asr_reuse.py`, Process tests; runtime cases may skip | Project-local verified reuse; frozen Process acceptance not established by historical R14 |
| I translation + readable TXT/topic derivatives | IMPLEMENTED, TESTED | `test_process_translation.py`, `test_process_topic_translation.py` | Prior candidate proofs plus current TranslateGemma code; not universal translation quality |
| I native documents/BookText OCR | IMPLEMENTED, TESTED, PARTIAL integration | Document tests, BookText selection/probe tests | Page-level OCR bridge; CDM/regions/review/translation lost at current boundary |
| I Knowledge K1 notebook | IMPLEMENTED, TESTED, ACCEPTED promotion record | K1 proof/registry | CURRENT binds K1 candidate; acceptance scope is exact baseline promotion |
| I K2 Knowledge stage | PARTIAL; candidate withdrawn | #227 extensive synthetic GUI/regression evidence | #227 closed; explicit final comment says owner does not accept/promote withdrawn candidate; no Stage-1 final acceptance inferred |
| I multi-source graph/navigation/exports | IMPLEMENTED, TESTED, ACCEPTED bounded contracts | Existing graph/Obsidian/OneDrive fixtures | Not automatic multi-source semantic merging or unattended external publishing |
| I Learning/Marketing/Assistants/social | PLANNED | Deferred registries/issues | No complete current product readiness claim |
| Four-app content reuse/resource lease | PLANNED, UNKNOWN production readiness | Separate local mechanisms only | No four-app end-to-end proof |
| Multilingual dubbing/diarization/cloning | PLANNED, UNKNOWN | Bounded dormant TTS only | No approved full production journey or voice-consent implementation |

## FACT — ASR comparison and retained guarantees

| Aspect | SeminarText canonical | VideoText canonical / Integra consequence |
| --- | --- | --- |
| Runtime | whisper.cpp CLI, large-v3 and Silero paths, FFmpeg PCM16/16 kHz, max 8 threads | Ordinary VT invokes bundled ST cf7a8445; Integra pins older ST 13644d2; no single host-wide runtime |
| Chunk/VAD | Default 300 s chunks; normal/careful/protective profiles | Selected VT inherits bundled core; old Swift no-VAD fallback belongs to retained legacy engine |
| Language | RU default; explicit EN on single `transcribe` | VT has optional sampled `-dl` detection/manual override; project-language parity is incomplete |
| Retry/QA | Bounded execution/quality retries; unresolved suspicious chunks can still finish with warning | VT avoids second local retry for core evidence; Integra adds fail-closed quality admission |
| Revisions/timing | Raw/clean/review distinct; selected attempt TXT/SRT/JSON; separate CWT alignment | Imported native tokens are not CWT or target-language word timestamps |
| Cache/resume | Path/source-marker reuse; no universal content/config key; source completion only | VT requires usable SRT/token JSON/timeline for resume; Integra has hash-bound project-local cache |
| Review | Transcript assurance may be machine/selective/full; semantic review explicit | VT legacy approved enum can be automatic; map attributable decisions, not label alone |

Preserve #129 explicit English behavior; #131 selected-attempt contract implemented/accepted in PR #132; #133 dual ranges; and later #138 directed raw token clarification. Prepared media extent and selected evidence envelope can differ. Store raw endpoints verbatim; derive playable intervals separately. A corrected transcript needs its own alignment validation, not borrowed word precision. No new ASR engine is justified. Workflow A reuses one per-source revision, B composes an ordered clear transcript with passage provenance, and C keeps per-source media clocks; B/C must not repeat recognition.

## FACT — acceptance chronology and installed runtime

- SeminarText #132 owner accepted exact selected-timing baseline; #138 later clarified directed tokens; #143 is current periodic-loop repair. The installed CLI `/Users/yurielokhin/bin/seminartext` resolves to `seminartext_4.0_work`; its SHA-256 matches canonical CLI (`b6bc085caed77f67770e4b7552b861f275f4425e5a61c40da89d84c236ac38c9`). Limited module comparisons matched, but selected schema/admission files are absent from classic deployment locations. Admission is documented as a source-checkout component. No full installed smoke/Integrity was run.
- BookText `/Applications/BookText.app` metadata is `0.1.0` / build `1`; installed Core Git HEAD is `8418319…`. #131 acceptance and #116 installation/pipeline evidence are recorded historical facts, not a new GUI test. #117 final visual acceptance and #114 remain open.
- VideoText `/Users/yurielokhin/Applications/VideoText.app` metadata is `0.6.8` / `2026.09.25.1`, bundled ST cf7a8445. #46 records exact installed candidate digest `eac8160b9e6b55aadd606620c14c900003903fa094a346e6c53db8f59f3bda4c`; audit read metadata only. #15 accepted subtitle translation; dubbing remains deferred.
- Integra installed app metadata at `/Users/yurielokhin/Applications/Integra-READY_APP_V1/Integra.app` is `1.0.0` / `100`, not enough to identify its exact contents. `current_product_baseline_v2.json` selects K1 `current-v2-675acf457d65e7633481bcea700036b7e9ef6298e0c6d6eb097e513d3bff249f`, source `312946d42c9712e4ee3b7974fe657762e8092c1d`, bundle `e3215a28c9ce0a1a54c35dc535bad42a9334cae7ddc5eb3b0533a480e0296d95`. Historical R14 is accepted, but it does not accept all later Process/K2 work. Latest #227 owner comment explicitly withdraws the unaccepted `2d770b6b…` candidate; current main records withdrawal. No archive/app mutation was performed here.

## FACT / INFERENCE — principal duplication, gaps and debt

1. **Shared ASR implementation already exists, but pins/packaging and cache keys diverge.** The Oct 20 #187 comment reports five paired fresh short-audio comparisons with byte-identical raw/clean text and matched cues; this is recorded bounded evidence, not a new benchmark or WER claim. It also confirms VideoText's dependency on ST. #187 independence is still NOT_YET_PROVEN; do not select a different recognizer merely to remove a dependency name.
2. **Three current TranslateGemma wrappers plus dormant Qwen translation.** Model aliases share bytes, not prompts/context/checkpoints/constraints. Reuse compatible artifacts and standardize envelope/resource identity first. Preserve BookText #131 and VideoText #15 baselines; do not revive Qwen.
3. **Source identity is inconsistent.** ST completion markers are path based; VT legacy sameSource compares size/mtime; BT collection hash sorts filenames. A synthetic BT probe confirmed reversing two image arguments leaves that hash unchanged while page order follows arguments. This is a concrete invalidation risk, not evidence of user-data corruption. Integra's stronger ASR cache is project-local, not an ecosystem index.
4. **QA/review states cannot be collapsed.** ST CLI warnings can coexist with completion, BT flags/pipeline pause are not semantic decisions, VT approved may be automatic, and Integra SUCCEEDED is operational truth. Preserve each native state and expose scoped assurance.
5. **BookText integration loses fidelity.** Current OCR worker reduces blocks to page text/confidence. CDM/regions/reading order/review/assets/translation are not a proven Knowledge import. Existing Integra native extraction should remain until a bounded BookText replacement is actually supported.
6. **Accepted document policy has enforcement gaps.** BookText automatic-PDF path can bypass visual/handwriting detection; a detection RuntimeError falls back to whole-page OCR. Treat handwriting exclusion as PARTIAL and repair against the accepted policy before broad integration; this audit does not reinterpret that policy.
7. **Global resources lack common ownership.** VT unloads matching Ollama families without another app's lease; BT translation lock is BookText-only; ST lacks host admission. Integra has suitable existing reservation infrastructure, but universal participation is unproved.
8. **Documentation and evidence are temporally mixed.** VT README schema-v7/dubbing claims lag v8/gates; BT older plan says translation unimplemented; Integra historical R14/R5 and component manifest differ from later CURRENT/runtime paths. Reconcile by exact commit/scope, not deleting historical truth.
9. **Future domain work must stay staged.** #257 proposes Master Knowledge→quality→curriculum→course→Publication/Marketing→assistants→automation. It is OPEN, not accepted executable roadmap. Preserve provenance now, avoid prebuilding those domains into Stage 1.

## PROPOSAL — recommended direction

Use existing producers and product adapters with additive versioned source/artifact/review envelopes; optional Integra orchestration; selective shared-library extraction only after parity evidence. Preserve native projects and one authoritative writer. Coordinate heavy workloads with a small cooperative contract based on Integra's existing resource reservation implementation. Keep text/subtitle/speech translation separate; treat TTS and synchronization as additional derivatives. Full rationale, lifecycle, responsibility matrix, acceptance milestones and owner decisions are in the nine companion documents.

## UNVERIFIED — deliberate limits

No fresh broad ASR/OCR/translation accuracy, real-media acceptance, full installed-bundle parity, target-M5 peak memory/throughput, universal cache compatibility, language support beyond evidenced routes, complete BookText→Knowledge import or multilingual dubbing was established. Reported real runs are scoped historical evidence with links. Private material and model outputs were not copied into the PR. Current implementation gaps do not authorize destructive migration, new models, semantic acceptance or source retirement.

## Evidence index

Every repository link below is pinned to the exact canonical SHA above. These anchors support the companion documents' I/S/B/V references.

- **I01 — integra:** [AGENTS.md](https://github.com/Yurielo/integra/blob/2d29bc63d850437c1d7b254f11797fad073f84e1/AGENTS.md), [DEVELOPMENT_WORKFLOW.md](https://github.com/Yurielo/integra/blob/2d29bc63d850437c1d7b254f11797fad073f84e1/DEVELOPMENT_WORKFLOW.md), [docs/PRODUCT_DEFINITION.md](https://github.com/Yurielo/integra/blob/2d29bc63d850437c1d7b254f11797fad073f84e1/docs/PRODUCT_DEFINITION.md), [docs/architecture/INTEGRA_ARCHITECTURE.md](https://github.com/Yurielo/integra/blob/2d29bc63d850437c1d7b254f11797fad073f84e1/docs/architecture/INTEGRA_ARCHITECTURE.md), [docs/AUTONOMOUS_EXECUTION_POLICY.md](https://github.com/Yurielo/integra/blob/2d29bc63d850437c1d7b254f11797fad073f84e1/docs/AUTONOMOUS_EXECUTION_POLICY.md), [docs/architecture/AGENT_TEAM_OPERATING_MODEL.md](https://github.com/Yurielo/integra/blob/2d29bc63d850437c1d7b254f11797fad073f84e1/docs/architecture/AGENT_TEAM_OPERATING_MODEL.md).
- **I02 — integra:** [state/integra_state_v1.json](https://github.com/Yurielo/integra/blob/2d29bc63d850437c1d7b254f11797fad073f84e1/state/integra_state_v1.json), [docs/ROADMAP.md](https://github.com/Yurielo/integra/blob/2d29bc63d850437c1d7b254f11797fad073f84e1/docs/ROADMAP.md), [state/current_product_baseline_v2.json](https://github.com/Yurielo/integra/blob/2d29bc63d850437c1d7b254f11797fad073f84e1/state/current_product_baseline_v2.json), [state/component_baselines_v1.json](https://github.com/Yurielo/integra/blob/2d29bc63d850437c1d7b254f11797fad073f84e1/state/component_baselines_v1.json), [state/history/knowledge_k2_candidate_2d770_withdrawal_v1.json](https://github.com/Yurielo/integra/blob/2d29bc63d850437c1d7b254f11797fad073f84e1/state/history/knowledge_k2_candidate_2d770_withdrawal_v1.json).
- **I03 — integra:** [integra_core/user_media.py](https://github.com/Yurielo/integra/blob/2d29bc63d850437c1d7b254f11797fad073f84e1/integra_core/user_media.py), [integra_core/asr_reuse.py](https://github.com/Yurielo/integra/blob/2d29bc63d850437c1d7b254f11797fad073f84e1/integra_core/asr_reuse.py), [integra_core/seminartext_asr_runtime.py](https://github.com/Yurielo/integra/blob/2d29bc63d850437c1d7b254f11797fad073f84e1/integra_core/seminartext_asr_runtime.py), [integra_core/seminartext_runtime.py](https://github.com/Yurielo/integra/blob/2d29bc63d850437c1d7b254f11797fad073f84e1/integra_core/seminartext_runtime.py), [integra_core/videotext_runtime.py](https://github.com/Yurielo/integra/blob/2d29bc63d850437c1d7b254f11797fad073f84e1/integra_core/videotext_runtime.py), [integra_core/word_timeline_runtime.py](https://github.com/Yurielo/integra/blob/2d29bc63d850437c1d7b254f11797fad073f84e1/integra_core/word_timeline_runtime.py).
- **I04 — integra:** [integra_core/translategemma_runtime.py](https://github.com/Yurielo/integra/blob/2d29bc63d850437c1d7b254f11797fad073f84e1/integra_core/translategemma_runtime.py), [integra_core/topic_translation.py](https://github.com/Yurielo/integra/blob/2d29bc63d850437c1d7b254f11797fad073f84e1/integra_core/topic_translation.py), [tests/test_process_translation.py](https://github.com/Yurielo/integra/blob/2d29bc63d850437c1d7b254f11797fad073f84e1/tests/test_process_translation.py), [tests/test_process_topic_translation.py](https://github.com/Yurielo/integra/blob/2d29bc63d850437c1d7b254f11797fad073f84e1/tests/test_process_topic_translation.py).
- **I05 — integra:** [docs/architecture/WORKER_PROTOCOL_V1.md](https://github.com/Yurielo/integra/blob/2d29bc63d850437c1d7b254f11797fad073f84e1/docs/architecture/WORKER_PROTOCOL_V1.md), [docs/architecture/DATA_OWNERSHIP_AND_PROJECT_LEASE.md](https://github.com/Yurielo/integra/blob/2d29bc63d850437c1d7b254f11797fad073f84e1/docs/architecture/DATA_OWNERSHIP_AND_PROJECT_LEASE.md), [docs/architecture/PROJECTS_AND_SOURCES_V1.md](https://github.com/Yurielo/integra/blob/2d29bc63d850437c1d7b254f11797fad073f84e1/docs/architecture/PROJECTS_AND_SOURCES_V1.md), [docs/architecture/OPERATIONS_AND_DIAGNOSTICS_V1.md](https://github.com/Yurielo/integra/blob/2d29bc63d850437c1d7b254f11797fad073f84e1/docs/architecture/OPERATIONS_AND_DIAGNOSTICS_V1.md), [schemas/artifact_reference_v1.schema.json](https://github.com/Yurielo/integra/blob/2d29bc63d850437c1d7b254f11797fad073f84e1/schemas/artifact_reference_v1.schema.json), [integra_core/operations.py](https://github.com/Yurielo/integra/blob/2d29bc63d850437c1d7b254f11797fad073f84e1/integra_core/operations.py).
- **I06 — integra:** [integra_core/booktext_runtime.py](https://github.com/Yurielo/integra/blob/2d29bc63d850437c1d7b254f11797fad073f84e1/integra_core/booktext_runtime.py), [workers/booktext_ocr_worker.py](https://github.com/Yurielo/integra/blob/2d29bc63d850437c1d7b254f11797fad073f84e1/workers/booktext_ocr_worker.py), [integra_core/application_runtime.py](https://github.com/Yurielo/integra/blob/2d29bc63d850437c1d7b254f11797fad073f84e1/integra_core/application_runtime.py), [integra_core/documents.py](https://github.com/Yurielo/integra/blob/2d29bc63d850437c1d7b254f11797fad073f84e1/integra_core/documents.py), [docs/audits/issue-187/BOOKTEXT_INTEGRATION_STATUS.md](https://github.com/Yurielo/integra/blob/2d29bc63d850437c1d7b254f11797fad073f84e1/docs/audits/issue-187/BOOKTEXT_INTEGRATION_STATUS.md).
- **S01 — seminartext:** [docs/architecture/SEMINARTEXT_PRODUCT_RULES.md](https://github.com/Yurielo/seminartext/blob/637199c91b1d1141503a8ca6c8abeaf418baf95b/docs/architecture/SEMINARTEXT_PRODUCT_RULES.md), [seminartext](https://github.com/Yurielo/seminartext/blob/637199c91b1d1141503a8ca6c8abeaf418baf95b/seminartext), [docs/architecture/SELECTED_WHISPER_TIMING_V1.md](https://github.com/Yurielo/seminartext/blob/637199c91b1d1141503a8ca6c8abeaf418baf95b/docs/architecture/SELECTED_WHISPER_TIMING_V1.md), [schemas/selected_whisper_timing_v1.schema.json](https://github.com/Yurielo/seminartext/blob/637199c91b1d1141503a8ca6c8abeaf418baf95b/schemas/selected_whisper_timing_v1.schema.json), [schemas/canonical_evidence_v1.schema.json](https://github.com/Yurielo/seminartext/blob/637199c91b1d1141503a8ca6c8abeaf418baf95b/schemas/canonical_evidence_v1.schema.json), [docs/architecture/REVIEWED_KNOWLEDGE_ADMISSION_V1.md](https://github.com/Yurielo/seminartext/blob/637199c91b1d1141503a8ca6c8abeaf418baf95b/docs/architecture/REVIEWED_KNOWLEDGE_ADMISSION_V1.md).
- **S02 — seminartext:** [tests/test_transcribe_language.py](https://github.com/Yurielo/seminartext/blob/637199c91b1d1141503a8ca6c8abeaf418baf95b/tests/test_transcribe_language.py), [tests/test_selected_whisper_timing.py](https://github.com/Yurielo/seminartext/blob/637199c91b1d1141503a8ca6c8abeaf418baf95b/tests/test_selected_whisper_timing.py), [tests/test_asr_quality_gate.py](https://github.com/Yurielo/seminartext/blob/637199c91b1d1141503a8ca6c8abeaf418baf95b/tests/test_asr_quality_gate.py), [tests/test_project_combined_clear.py](https://github.com/Yurielo/seminartext/blob/637199c91b1d1141503a8ca6c8abeaf418baf95b/tests/test_project_combined_clear.py), [seminartext_modules/seminartext_translate.py](https://github.com/Yurielo/seminartext/blob/637199c91b1d1141503a8ca6c8abeaf418baf95b/seminartext_modules/seminartext_translate.py), [SEMINARTEXT_4_STATE.json](https://github.com/Yurielo/seminartext/blob/637199c91b1d1141503a8ca6c8abeaf418baf95b/SEMINARTEXT_4_STATE.json), [analysis/WORD_TIMELINE_MVP_ONE_CONTROLLED_SOURCE.md](https://github.com/Yurielo/seminartext/blob/637199c91b1d1141503a8ca6c8abeaf418baf95b/analysis/WORD_TIMELINE_MVP_ONE_CONTROLLED_SOURCE.md).
- **B01 — booktext:** [AGENTS.md](https://github.com/Yurielo/booktext/blob/8418319021516323cbf71b2b0c59538840590f2b/AGENTS.md), [DEVELOPMENT_PLAN.md](https://github.com/Yurielo/booktext/blob/8418319021516323cbf71b2b0c59538840590f2b/DEVELOPMENT_PLAN.md), [booktext.py](https://github.com/Yurielo/booktext/blob/8418319021516323cbf71b2b0c59538840590f2b/booktext.py), [tools/chunk_lifecycle.py](https://github.com/Yurielo/booktext/blob/8418319021516323cbf71b2b0c59538840590f2b/tools/chunk_lifecycle.py), [tools/canonical_document.py](https://github.com/Yurielo/booktext/blob/8418319021516323cbf71b2b0c59538840590f2b/tools/canonical_document.py), [docs/architecture/CANONICAL_DOCUMENT_MODEL.md](https://github.com/Yurielo/booktext/blob/8418319021516323cbf71b2b0c59538840590f2b/docs/architecture/CANONICAL_DOCUMENT_MODEL.md), [docs/architecture/MACHINE_PROTOCOL.md](https://github.com/Yurielo/booktext/blob/8418319021516323cbf71b2b0c59538840590f2b/docs/architecture/MACHINE_PROTOCOL.md), [docs/INTEGRA_OCR_ADAPTER_CONTRACT.md](https://github.com/Yurielo/booktext/blob/8418319021516323cbf71b2b0c59538840590f2b/docs/INTEGRA_OCR_ADAPTER_CONTRACT.md).
- **B02 — booktext:** [tools/translation.py](https://github.com/Yurielo/booktext/blob/8418319021516323cbf71b2b0c59538840590f2b/tools/translation.py), [docs/architecture/TRANSLATION_LAYER.md](https://github.com/Yurielo/booktext/blob/8418319021516323cbf71b2b0c59538840590f2b/docs/architecture/TRANSLATION_LAYER.md), [docs/architecture/TRANSLATION_QUALITY_FIX_PLAN.md](https://github.com/Yurielo/booktext/blob/8418319021516323cbf71b2b0c59538840590f2b/docs/architecture/TRANSLATION_QUALITY_FIX_PLAN.md), [tests/test_translation.py](https://github.com/Yurielo/booktext/blob/8418319021516323cbf71b2b0c59538840590f2b/tests/test_translation.py), [tools/export_document.py](https://github.com/Yurielo/booktext/blob/8418319021516323cbf71b2b0c59538840590f2b/tools/export_document.py), [docs/evidence/ISSUE_116_PIPELINE_COMPLETION.md](https://github.com/Yurielo/booktext/blob/8418319021516323cbf71b2b0c59538840590f2b/docs/evidence/ISSUE_116_PIPELINE_COMPLETION.md).
- **V01 — videotext:** [AGENTS.md](https://github.com/Yurielo/videotext/blob/f6efe0b2504550aa51d689e6712e7472144d7599/AGENTS.md), [Sources/videotext/Services/WorkflowEngine.swift](https://github.com/Yurielo/videotext/blob/f6efe0b2504550aa51d689e6712e7472144d7599/Sources/videotext/Services/WorkflowEngine.swift), [Sources/videotext/Services/SelectedTimingVerticalSlice.swift](https://github.com/Yurielo/videotext/blob/f6efe0b2504550aa51d689e6712e7472144d7599/Sources/videotext/Services/SelectedTimingVerticalSlice.swift), [Resources/SeminarText/CANONICAL_COMMIT](https://github.com/Yurielo/videotext/blob/f6efe0b2504550aa51d689e6712e7472144d7599/Resources/SeminarText/CANONICAL_COMMIT), [Sources/videotext/Services/ProjectStore.swift](https://github.com/Yurielo/videotext/blob/f6efe0b2504550aa51d689e6712e7472144d7599/Sources/videotext/Services/ProjectStore.swift), [Sources/videotext/Core/ArtifactModels.swift](https://github.com/Yurielo/videotext/blob/f6efe0b2504550aa51d689e6712e7472144d7599/Sources/videotext/Core/ArtifactModels.swift).
- **V02 — videotext:** [Sources/videotext/Adapters/TranslationAdapter.swift](https://github.com/Yurielo/videotext/blob/f6efe0b2504550aa51d689e6712e7472144d7599/Sources/videotext/Adapters/TranslationAdapter.swift), [Sources/videotext/Services/TranslationContextPlan.swift](https://github.com/Yurielo/videotext/blob/f6efe0b2504550aa51d689e6712e7472144d7599/Sources/videotext/Services/TranslationContextPlan.swift), [Sources/videotext/Services/HumanReviewService.swift](https://github.com/Yurielo/videotext/blob/f6efe0b2504550aa51d689e6712e7472144d7599/Sources/videotext/Services/HumanReviewService.swift), [Sources/videotext/Services/OllamaMemoryManager.swift](https://github.com/Yurielo/videotext/blob/f6efe0b2504550aa51d689e6712e7472144d7599/Sources/videotext/Services/OllamaMemoryManager.swift), [Sources/videotext/Adapters/SpeechSynthesisAdapter.swift](https://github.com/Yurielo/videotext/blob/f6efe0b2504550aa51d689e6712e7472144d7599/Sources/videotext/Adapters/SpeechSynthesisAdapter.swift), [Sources/videotext/Core/Models.swift](https://github.com/Yurielo/videotext/blob/f6efe0b2504550aa51d689e6712e7472144d7599/Sources/videotext/Core/Models.swift), [docs/CORE_TRANSLATION_RELEASE_BOUNDARY.md](https://github.com/Yurielo/videotext/blob/f6efe0b2504550aa51d689e6712e7472144d7599/docs/CORE_TRANSLATION_RELEASE_BOUNDARY.md), [Tests/SelectedTimingVerticalSliceProbe.swift](https://github.com/Yurielo/videotext/blob/f6efe0b2504550aa51d689e6712e7472144d7599/Tests/SelectedTimingVerticalSliceProbe.swift).

Exact source locations for critical findings: SeminarText `seminartext:1066` (decoder), `:1274` (completion skip), `:1376` (remaining QA warning), `:4804` (project parser), `:5189` (combined clear); BookText `tools/chunk_lifecycle.py:69`, `booktext.py:1895` and `:1918`, `tools/translation.py:738` and `:761`; VideoText `WorkflowEngine.swift:2332`, `:2488`, `SelectedTimingVerticalSlice.swift:930`, `ProjectStore.swift:217`, `HumanReviewService.swift:76`, `OllamaMemoryManager.swift:16`; Integra `asr_reuse.py:59`, `booktext_runtime.py:19`, `application_runtime.py:324`, `operations.py:1216`, `translategemma_runtime.py:22`. Resolve these against the pinned links, not an active dirty checkout.

### Acceptance and live GitHub evidence

- [SeminarText #129](https://github.com/Yurielo/seminartext/issues/129), [#131](https://github.com/Yurielo/seminartext/issues/131), [#132 owner acceptance](https://github.com/Yurielo/seminartext/pull/132#issuecomment-5984403919), [#133](https://github.com/Yurielo/seminartext/issues/133), [#138 directed-token clarification](https://github.com/Yurielo/seminartext/pull/138#issuecomment-6096393106), [later downstream timing verification](https://github.com/Yurielo/seminartext/pull/138#issuecomment-6102050526).
- [BookText #131 semantic acceptance](https://github.com/Yurielo/booktext/issues/131#issuecomment-5968651778), [#131 installation/completion](https://github.com/Yurielo/booktext/issues/131#issuecomment-5968670770), [#116 final pipeline proof](https://github.com/Yurielo/booktext/issues/116#issuecomment-5968962731), [#117 visual gate](https://github.com/Yurielo/booktext/issues/117#issuecomment-5938882810).
- [VideoText #9 historical semantic failure](https://github.com/Yurielo/videotext/pull/9#issuecomment-5968497963), [#15 EN↔RU subtitle acceptance](https://github.com/Yurielo/videotext/pull/15#issuecomment-6075280639), [#46 scoped owner PASS](https://github.com/Yurielo/videotext/pull/46#issuecomment-6297181044), [#46 installed-candidate record](https://github.com/Yurielo/videotext/pull/46#issuecomment-6297223053).
- [Integra #187 latest ASR comparison](https://github.com/Yurielo/integra/issues/187#issuecomment-6297977638), [#227 final withdrawal authority](https://github.com/Yurielo/integra/issues/227#issuecomment-6298827934), [#257 staged Master Knowledge proposal](https://github.com/Yurielo/integra/issues/257).

## FACT — open GitHub work inventory at audit capture

This is the complete paginated open Issue/PR inventory captured before creation of #277. An open issue can contain already implemented work; a draft PR is not a canonical capability. Historical/stale overlap is listed for reconciliation, not auto-closure. No implementation issues were created from this roadmap.

### seminartext

**Open issues: 10.**

- [#110 Stress Code — Real Semantic Human Review Package v1](https://github.com/Yurielo/seminartext/issues/110)
- [#95 Audit remediation: restore optional runtime profile readiness](https://github.com/Yurielo/seminartext/issues/95)
- [#94 Audit remediation: establish safe Git branch and dangling-object housekeeping](https://github.com/Yurielo/seminartext/issues/94)
- [#93 Audit remediation: make historical analysis artifacts portable without rewriting evidence](https://github.com/Yurielo/seminartext/issues/93)
- [#69 Audit remediation program: sequence and verify all dual-audit fixes](https://github.com/Yurielo/seminartext/issues/69)
- [#68 Integration validation: run one full-seminar multi-source knowledge vertical slice](https://github.com/Yurielo/seminartext/issues/68)
- [#67 Dataset D: run the single frozen blind Topic Engine evaluation](https://github.com/Yurielo/seminartext/issues/67)
- [#66 Dataset D: perform topic-agnostic source repair while preserving LOCKED TEST](https://github.com/Yurielo/seminartext/issues/66)
- [#65 Data review: accept G1/G2 roles, author Gold and freeze evaluation contracts](https://github.com/Yurielo/seminartext/issues/65)
- [#22 Add macOS completion notifications for long-running commands](https://github.com/Yurielo/seminartext/issues/22)

**Open pulls: 1.**

- [#121 Issue #68: prepare real multi-source DOMAIN_AUTHORING gate](https://github.com/Yurielo/seminartext/pull/121) — draft

### booktext

**Open issues: 2.**

- [#117 Unified automatic extraction with source-preserving text and visual assembly](https://github.com/Yurielo/booktext/issues/117)
- [#114 Project history and resumable recent projects](https://github.com/Yurielo/booktext/issues/114)

**Open pulls: 0.**

None at capture.

### videotext

**Open issues: 5.**

- [#48 Simple Mode: Automated Processing Presets](https://github.com/Yurielo/videotext/issues/48)
- [#40 Fragment render reuse and duplicate prevention](https://github.com/Yurielo/videotext/issues/40)
- [#16 Simple Mode: показывать result entities вместо технических файлов](https://github.com/Yurielo/videotext/issues/16)
- [#4 Audit unowned temporary comparison workspace lifecycle](https://github.com/Yurielo/videotext/issues/4)
- [#3 Исправить: тематический таймкодинг строит все детализации вместо выбранной](https://github.com/Yurielo/videotext/issues/3)

**Open pulls: 1.**

- [#49 Add review-assisted processing presets to Simple Mode](https://github.com/Yurielo/videotext/pull/49) — draft

### integra

**Open issues: 36.**

- [#257 Roadmap revision — stage-gated Master Knowledge development](https://github.com/Yurielo/integra/issues/257)
- [#216 Governed one-time promotion transition for accepted historical CURRENT recovery gap](https://github.com/Yurielo/integra/issues/216)
- [#210 Polish Russian singular source count in confirmation](https://github.com/Yurielo/integra/issues/210)
- [#205 Temp lifecycle regression: full-size Integra candidates bypass cleanup and refill disk](https://github.com/Yurielo/integra/issues/205)
- [#187 Process v1: prove VideoText-only runtime before retiring SeminarText dependency](https://github.com/Yurielo/integra/issues/187)
- [#185 Process v1: integrate existing translation journey](https://github.com/Yurielo/integra/issues/185)
- [#181 Harden local temp-build lifecycle: prevent multi-GiB candidate leaks and orphan processes](https://github.com/Yurielo/integra/issues/181)
- [#180 Manage lifecycle of temporary build and test artifacts](https://github.com/Yurielo/integra/issues/180)
- [#163 Astra review — design CURRENT → PROPOSED → PROMOTED governance for evolving accepted baselines](https://github.com/Yurielo/integra/issues/163)
- [#161 Recovery WP — truthful failure, cancel, interruption and safe subsequent run from accepted main](https://github.com/Yurielo/integra/issues/161)
- [#157 Post-MCWMA checkpoint — select the next resource-efficient completion tranche](https://github.com/Yurielo/integra/issues/157)
- [#151 Reset development strategy for resource-efficient completion of working macOS app](https://github.com/Yurielo/integra/issues/151)
- [#150 Deep reset audit: actual product state, development failures, and completion plan to working macOS app](https://github.com/Yurielo/integra/issues/150)
- [#148 Packaged pre-acceptance stabilization: prove primary production E2E before owner acceptance](https://github.com/Yurielo/integra/issues/148)
- [#146 Fix packaged SeminarText ASR pinned-bytes integrity mismatch](https://github.com/Yurielo/integra/issues/146)
- [#144 Fix packaged macOS GUI Ollama executable resolution](https://github.com/Yurielo/integra/issues/144)
- [#142 Reconstruct clean Word Alignment runtime and unblock isolated candidate build](https://github.com/Yurielo/integra/issues/142)
- [#140 Recover #138 isolated candidate build and prove owner-acceptance readiness](https://github.com/Yurielo/integra/issues/140)
- [#139 Full product & architecture audit: plan vs reality and updated Master Plan](https://github.com/Yurielo/integra/issues/139)
- [#138 Audit gate: final SeminarText pin, headless execution, and agent-team reduction](https://github.com/Yurielo/integra/issues/138)
- [#137 P1: truthful recovery after worker or application interruption](https://github.com/Yurielo/integra/issues/137)
- [#129 Audit source-product capabilities and integrate verified production paths](https://github.com/Yurielo/integra/issues/129)
- [#64 DEFERRED_CAPABILITIES_V1 — Register all post-ready-app functionality](https://github.com/Yurielo/integra/issues/64)
- [#31 INTEGRA-R15 — Evaluate optional repository consolidation](https://github.com/Yurielo/integra/issues/31)
- [#27 Integra Social Adapter — TikTok](https://github.com/Yurielo/integra/issues/27)
- [#26 Integra Social Adapter — WhatsApp Business](https://github.com/Yurielo/integra/issues/26)
- [#25 Integra Social Adapter — Telegram](https://github.com/Yurielo/integra/issues/25)
- [#24 Integra Social Adapter — YouTube](https://github.com/Yurielo/integra/issues/24)
- [#23 Integra Social Adapter — Threads](https://github.com/Yurielo/integra/issues/23)
- [#22 Integra Social Adapter — Instagram](https://github.com/Yurielo/integra/issues/22)
- [#21 Integra Social Adapter — Facebook Pages](https://github.com/Yurielo/integra/issues/21)
- [#20 Integra Social Publishing — shared adapter contract and safety layer](https://github.com/Yurielo/integra/issues/20)
- [#19 Integra — Implement Knowledge Assistant v1](https://github.com/Yurielo/integra/issues/19)
- [#18 Integra — Implement Learning Studio v1](https://github.com/Yurielo/integra/issues/18)
- [#17 INTEGRA-R11 — Implement Marketing Studio v1 and project playbooks](https://github.com/Yurielo/integra/issues/17)
- [#1 Integra 1.0 — governed implementation roadmap](https://github.com/Yurielo/integra/issues/1)

**Open pulls: 19.**

- [#217 Add governed one-time promotion path for accepted historical recovery gap](https://github.com/Yurielo/integra/pull/217)
- [#206 fix: govern disposable macOS build workspaces](https://github.com/Yurielo/integra/pull/206) — draft
- [#204 feat: translate persisted Process topics](https://github.com/Yurielo/integra/pull/204)
- [#186 Process v1: integrate existing translation journey](https://github.com/Yurielo/integra/pull/186) — draft
- [#184 Issue #150: document product reality deep reset audit](https://github.com/Yurielo/integra/pull/184) — draft
- [#183 Harden temporary candidate lifecycle and process ownership](https://github.com/Yurielo/integra/pull/183) — draft
- [#182 Manage owned temporary build and test artifacts](https://github.com/Yurielo/integra/pull/182) — draft
- [#178 Process v1: repair persisted paths for Topic Review](https://github.com/Yurielo/integra/pull/178) — draft
- [#177 docs: record Process topic review gap](https://github.com/Yurielo/integra/pull/177) — draft
- [#167 docs: add factual Product Reality Sheet](https://github.com/Yurielo/integra/pull/167) — draft
- [#164 Design CURRENT → PROPOSED → PROMOTED governance (Astra, #163)](https://github.com/Yurielo/integra/pull/164) — draft
- [#162 Recovery WP: bounded lifecycle recovery from current main](https://github.com/Yurielo/integra/pull/162) — draft
- [#158 Issue #157: post-MCWMA next-tranche plan](https://github.com/Yurielo/integra/pull/158) — draft
- [#152 Define resource-efficient completion strategy](https://github.com/Yurielo/integra/pull/152) — draft
- [#149 Add packaged pre-acceptance primary E2E gate](https://github.com/Yurielo/integra/pull/149) — draft
- [#147 Fix SeminarText ASR runtime integrity pin](https://github.com/Yurielo/integra/pull/147) — draft
- [#145 Resolve Ollama for packaged macOS GUI](https://github.com/Yurielo/integra/pull/145) — draft
- [#143 Document clean Word Alignment candidate recovery](https://github.com/Yurielo/integra/pull/143) — draft
- [#141 Document #138 isolated candidate build blocker](https://github.com/Yurielo/integra/pull/141) — draft

## Validation and delivery evidence

Validation completion is recorded here after the documentation review. No application inference or release gate is implied by documentation tests.

**FACT — validation performed on the isolated planning checkout:**

- `python3 scripts/validate_governance.py`: PASS, `BASELINE_STATE: CURRENT_VALID`; `python3 scripts/check_agents.py`: PASS.
- Documentation validation: all ten required Markdown files present; 73 pinned source links resolve to inspected files at the recorded SHAs; 30 relative document links resolve; all four evidence labels and Markdown code fences checked. `git diff --cached --check`: PASS.
- Independent documentation QA/review: PASS after repairing the roadmap's Knowledge Foundation and scope-conditional readiness edges. Independent BookText/translation factual review: PASS after correcting the native translation filename and separating structural/context signals from human semantic validation.
- BookText existing deterministic translation/CDM/Integra-candidate/display-identity suites: **43 tests PASS**, 2.063 s, mocked provider and synthetic fixtures. A separate synthetic fingerprint probe confirmed ordered-image invalidation risk; no OCR inference or user documents used.
- Initial Integra supported suite: 1,165 tests attempted, 113 skips, one import error (`jsonschema` unavailable in default Python). Existing review-wheel cache validation passed for all five wheels; 74 already installed library files in the existing runtime matched wheel bytes. No dependency installation occurred. The 11 previously blocked translation migration compatibility tests then passed.
- Final full supported Integra suite: **PASS — 1,175 tests run in 663.526 s; 1,062 passed, 113 declared environment skips; zero failures/errors**. The skips concern unavailable external/pinned runtime cases, and are not relabeled as successful product execution.
- Canonical GitHub mains were re-read and unchanged; original active checkout HEAD/status inventories remained unchanged. This does not claim a full binary attestation of installed applications.

The full rerun uses the existing supported `scripts/run_review_tests.sh` with `INTEGRA_TEST_REVIEW_PYTHONPATH` pointing to the already installed review libraries in `/Users/yurielokhin/AI/runtimes/integra/current-build/Integra.app/Contents/Resources/runtime/review-python/site-packages`. Its archive-execution guard remains enabled. Environment skips are retained and are not product PASS evidence. No source-product E2E/inference or installed-app acceptance was rerun.

**Delivery scope:** branch `codex/issue-277-four-product-architecture`; exactly the ten files in this directory. No application source, schemas, accepted governance/state, models, user projects or installed apps change. Hosted checks and the final commit are reported on the associated PR. The Product Owner accepted the planning direction; this documentation-only PR may merge under the repository's governed lifecycle once its actual checks and independent review pass. M1–M7 implementation, release, semantic acceptance and all native authority boundaries remain separate.

## Companion documents

1. [Unified source lifecycle](UNIFIED_SOURCE_LIFECYCLE.md)
2. [Unified translation architecture](UNIFIED_TRANSLATION_ARCHITECTURE.md)
3. [Multilingual media pipeline](MULTILINGUAL_MEDIA_PIPELINE.md)
4. [Shared artifact contract proposal](SHARED_ARTIFACT_CONTRACT_PROPOSAL.md)
5. [Product responsibility matrix](PRODUCT_RESPONSIBILITY_MATRIX.md)
6. [Integrated development roadmap](INTEGRATED_DEVELOPMENT_ROADMAP.md)
7. [Architecture options and risks](ARCHITECTURE_OPTIONS_AND_RISKS.md)
8. [Product Owner decisions](PRODUCT_OWNER_DECISIONS.md)
9. [Russian executive summary](EXECUTIVE_SUMMARY_RU.md)
