# Process v1 WP1: existing proof and Recovery closure ledger

Status: `PROCESS_V1_WP1_READY_FOR_OWNER_REVIEW`. Issue: [#169](https://github.com/Yurielo/integra/issues/169).
This is evidence for the frozen Process v1 Board, not a CURRENT or PROPOSED
record, merge authorization, or `USER_ACCEPTED`.

## Starting baseline — before Recovery reconciliation

| Binding | Exact value |
| --- | --- |
| Canonical `main` HEAD | `46373dde99eb02bc25bfffb5ccfe7288acffd335` |
| Canonical `main` tree | `c2de2aee2ea3e50a60323f9326a58a4fe0e50524` |
| Process v1 DoD SHA-256 | `65384726a2985fcb85efbfb87e77c8963b9596a8c451509ce76476b2938418d4` |
| CURRENT baseline | `current-v2-156-160`; record SHA-256 `c133d168e59ec9ca5c0d6c5806c017f34e0af994e75bbeae56957596c58048ff` |
| Recovery source head | `b630ae384f09122c07648094594d68bdd0e2605c` |
| Parity sheet SHA-256 | `63b13dd04b99959f4b0ac84f0c2d0687bba7c3d89a2410113801813f3e18a373` |
| Staged review SHA-256 | `2d95c9f5f0858d93665a73dcfc1973972c280260d5090de03e674c9c553672eb` |

## Reusable Recovery evidence

Recovery `b630ae3` records exact governed SeminarText commit
`970bde598ddd649599295139986933e0e06cb9c0` and CLI SHA-256
`f7f411bf106341ae970bc40d759e1e3c964273b977bdb12d0f1840e629def13a`.
It reports `tests.test_asr_reuse`: **12 run, 12 passed, 0 skipped**. This is
source-bound reuse/invalidation evidence, not final Candidate proof, and is
preserved without rerun unless the relevant runtime identity changes.

## Recovery reconciliation

The prior bounded repair is commit `242e70517bb345e74b84086994639a919daa511a`.
It changes only `integra_core/shutdown_runtime.py`, `macos/Resources/bridge.py`,
and `tests/test_recovery_contract.py`: bounded plan timeout, conservative stale
RUNNING reconciliation, GUI re-entry reconciliation, and deterministic lifecycle
regressions. A three-way merge check against canonical main found no conflict;
the three product files are byte-equivalent to the original repair content.

The historical source evidence also records a fresh isolated build interruption
during pinned VideoText `swiftc`. The interrupted output had no runtime manifest
or Candidate manifest and is not a Candidate. That is not evidence of a
compiler/product defect. No repair cycle is spent or inferred by this ledger.

## Evidence matrix

| BOARD ITEM | USER JOURNEY | PRODUCTION PATH | PROOF LEVEL | RESULT | CANDIDATE/EVIDENCE | BOARD TRANSITION |
| --- | --- | --- | --- | --- | --- | --- |
| Local video / ASR / SRT / Timeline / basic Topics | Deterministic Russian local video | Packaged `bridge.py`: detect → plan → execute → bundled SeminarText → Word Timeline → Topics → persisted navigation | Fresh Candidate, Finder-like minimal PATH | PASS | `candidate-v1-17f50c…`; deterministic fixture SHA-256 `db0cbfd…`; result SHA-256 `d6ca7e…`; Word Timeline evidence SHA-256 `fcb387…`; completed run with 2 navigation segments | Existing `DONE` retained; final-Candidate video proof added. |
| Local audio / ASR / SRT / Timeline / basic Topics | Public natural-Russian local audio | Same packaged production route; source `LOCAL_AUDIO`, no mock worker or source-tree runtime | Fresh Candidate, Finder-like minimal PATH | PASS | `candidate-v1-17f50c…`; Wikimedia fixture SHA-256 `00270ff4…`; result SHA-256 `0bafae…`; Word Timeline evidence SHA-256 `438892…`; completed run with 12 navigation segments | `IN_PROGRESS → DONE`: the Board's packaged-audio gate is satisfied. |
| Multiple local / folder | Multiple selection and folder discovery | Source plan / S06 | Existing path; folder is NOT_DONE integration | Pending | Parity/DoD | No transition. |
| One YouTube | URL ingestion and result | `youtube_runtime → app → media` | Existing path requires packaged proof | Pending | S08 | No transition. |
| Translation | Selected translation outputs | VideoText translation worker | Existing/partial path | Pending | S14/V05/V06 | No transition. |
| Topics/review | Basic Topics and review | Topics worker / review runtime | P156 basic Topics; review unproven | Pending | S12/S20 | No transition. |
| Persistence/reuse | Reopen and invalidation | Project/run records / `asr_reuse` | Existing source-bound proof | Pending final Candidate | V21 and 12/12 ledger | No transition. |
| Recovery reliability | Active close/quit, stale state, downstream failure → retry/reuse | Native app → packaged bridge → reconciled shutdown/runtime and pinned ASR cache | Fresh Candidate plus preserved source-bound ledger | PASS | Close and quit both PASS; `native_asr_retry_probe` PASS (result SHA-256 `a46cf8…`); prior exact 12/12 reuse/invalidation remains valid. The stale-without-ownership case became `FAILED` with `STALE_RUNNING_RECONCILED`, did not signal its unrelated PID, and let the app close. | Technical proposal closure is valid; Process-wide owner acceptance remains reserved. |

No ledger row infers PASS from code, an adapter, historical issue, source test,
skipped test, or fake worker.

## Fresh Candidate identity and bounded results

The isolated application was built without replacing the deployed/current app.
Its manifest validated and native self-test passed. It binds the exact production
inputs: SeminarText `970bde598ddd649599295139986933e0e06cb9c0` / CLI SHA-256
`f7f411bf106341ae970bc40d759e1e3c964273b977bdb12d0f1840e629def13a`,
VideoText `2e098d1705b6815628bee1e023f4742718eabf02`, and the governed Word
Alignment runtime.

| Binding | Value |
| --- | --- |
| Candidate ID / identity SHA-256 | `candidate-v1-17f50c3788518c57b927f2d4f4ddcbc9ec52e8d121de07c24fe9b2bd1d202d26` |
| Bundle digest | `de6c6186918ba084fd74d5146313e9d235e0f7801cdff27f664495bba00a50d1` |
| Candidate manifest SHA-256 | `c2439ec233c03f84e9bf73b908fab2b5718ff8c058ea388df7226b2a0f190c83` |
| Candidate source | clean `e66c800354df847159e0443d339e54e1bb265a66`, tree `56c8cad09d179c39d8af1be6ff255d384957b42d` |

The first run of `native_shutdown_probe.py` did not pass as a whole because its
legacy ambiguous-PID assertion expects a `RUNNING` record without a verified
`.workers` ownership record to remain `RUNNING`. The reconciled current contract
instead classifies that record as `STALE_RUNNING_RECONCILED` / `FAILED`; this is
the behavior asserted by `tests.test_recovery_contract` and required by the
frozen Board's stale-RUNNING outcome. The Candidate did not signal the unrelated
PID. This is a stale negative-probe expectation, not evidence of a new Recovery
product repair. The probe is not counted as PASS.

## Resolved bounded detour: strict PROPOSED material closure

Proposal Lite now records a product source `A`, a separately verified
evidence/governance overlay `B`, and a proposal-only declaration commit. The
Candidate manifest is required to bind exact clean source `A`; the declared
CURRENT→A governed product delta is hash-verified; `A→B` may contain only the
explicit allowlist and no product/runtime path; and the declaration commit may
contain only the PROPOSED record. CURRENT and historical R12/R13 bytes remain
unchanged, while a legitimate declared delta no longer fails simply because it
differs from historical bytes.

The committed Proposal Lite record therefore reports
`PROPOSED_BASELINE_VALID / AWAITING_OWNER_ACCEPTANCE`. It is not a promotion,
merge authorization, or `USER_ACCEPTED` claim.

## Remaining `VERIFY_EXISTING` closure — exact Candidate evidence

This section resumes the original Issue #169 scope after the bounded governance
detour.  It does not rebuild the Candidate, rerun prior valid Recovery cases, or
turn a source test, registry entry, or UI source string into packaged proof.
All new calls used the already-attested app with Finder-like minimal `PATH` and
an isolated `INTEGRA_APP_DATA_ROOT`.

| Coherent proof journey | Board items addressed | Exact result | Evidence |
| --- | --- | --- | --- |
| Public one-video YouTube ingest | One YouTube video | **PASS.** Public non-private `https://www.youtube.com/watch?v=jNQXAC9IVRw` completed through the packaged production route. It produced owned downloaded media (252,182 bytes, SHA-256 `8e18a126899cfb98cfd10f5e1dcdeabfa97e368ca9645f52fd802ba24b07e4f9`) and a source record whose URL exactly matched input (SHA-256 `8c7f1b8e5f6fc0276a4ac291b67ee9ae17e2117c26842161e1d0f1273d812452`). | `/private/tmp/integra169-wp1-youtube2.v8dKat/youtube-packaged-evidence.json`, SHA-256 `a7b94a2878197881bcd216e68aa6bcaea358ed35c0eed2618a799d340b67d2a8`; project `917cd253-8a90-4dc5-a2b0-756c4ad72481`, run `9275c9d6-c857-46a6-9320-17af6ceaf531`. |
| Ordered local inputs plus controlled later failure | Several local files; ordered processing; clean TXT; selected outputs; statuses; upstream preservation | **PARTIAL / exact classification.** The plan preserved input order (`fixture.ogg`, then `corrupt.mp3`) and selected only `transcript, subtitles`. The real first audio source completed and produced TXT/SRT/clean/review/provenance; the corrupt second source made the run truthfully `FAILED`. The completed first result remains readable. However the second selected input has no structured failed `source_result`; the run stops at the first failure. Therefore several-local-files and ordered-processing cannot move to `DONE`: they require bounded **multi-source failure-isolation repair**, not another verification run. | `/private/tmp/integra169-wp1-multi.ijKoOD/multi-local-packaged-evidence.json`, SHA-256 `b04762b0f865860de42e5ff3a1ccd54d14a854635ae781953ec825f688005a1e`; project `ba9c2b38-22c0-4a5d-9aa2-b6f319787267`, run `298a20d6-eeea-4030-9d70-78af7c602c0e`. |
| Persisted derivative and fresh reopen | Clean TXT; review TXT; ordinary files; reopen after restart; open result | **TECHNICAL PASS, GUI acceptance still open.** A fresh packaged bridge process reopened the stored Candidate run and reread the completed source's raw TXT, SRT, clean TXT, review TXT and ASR provenance by SHA-256. The candidate's deterministic completed run also prepared a real transcript-review request bound to its TXT and Word Timeline (`request_sha256` `9b045363570cc2ffd39847d4cc371c0db38f4cf27fff0a7e507bdfdb1ed3632a`). No automated reviewer identity, confirmation, or fake human decision was created. The frozen gates that require actual GUI opening/relaunch and human review stay `IN_PROGRESS`; no repair is inferred. | Reopen: `/private/tmp/integra169-wp1-multi.ijKoOD/reopen-evidence.json`, SHA-256 `5dcd887c9d00056e7fd4838838f5e65b6f172e730e2cb2e25dba17f06dd104d6`. Review preparation: `/private/tmp/integra169-det-journey-1790077742-15100/review_prepare-evidence.json`, SHA-256 `3c653323a1a358d2218d3a7edb5787c2736e5fde7accbcebec494b32ad1d15d3`. |

The first attempted historic yt-dlp fixture URL, `BaW_jenozKc`, returned
`ERROR: [youtube] … This video is unavailable` on 2026-09-22. It is recorded
as an external media availability change, not as an Integra defect; the second
public URL above verifies the same current packaged production path.

### Remaining `VERIFY_EXISTING` items and truthful disposition

| Item(s) | Disposition after this WP1 proof | Why it is not silently marked `DONE` |
| --- | --- | --- |
| Several local files; ordered processing | **REPAIR_INTEGRATION.** Board is now `NOT_DONE`. | The actual Candidate evidence demonstrates missing structured per-source failure accounting/isolation. A further verification run cannot create the required state. |
| Protective retry | **Superseded by controlled packaged proof.** | The later, separate controlled proof uses the exact pinned CLI and a non-private generated audio fixture; it records real first-pass `fuzzy_contextual_repetition`, automatic retry, and truthful persisted final quality failure. See `PROCESS_V1_PROTECTIVE_RETRY_PROOF.md`. It does not change ASR semantics or claim a successful recovery where the retry remains suspicious. |
| Review TXT; Topic edit/confirm | **OWNER_GUI_ACCEPTANCE_REQUIRED.** | Packaged artifacts and review preparation are real; creating a purported human confirmation or topic decision autonomously would be false evidence. The GUI/human decision gates therefore remain open without asserting missing integration. |
| Unified results; open result; ordinary GUI-only use; real progress; clear statuses | **OWNER_GUI_ACCEPTANCE_REQUIRED.** | Existing Candidate bridge/native paths and result artifacts are available, but their frozen gates specifically require the normal visible macOS user journey. No automatic Finder/default-app opening was invoked. |
| Reopen after restart | **VERIFY_EXISTING — GUI relaunch proof remains.** | Fresh packaged bridge process reread persisted records without rerun, but this is not substituted for the frozen native-app close/relaunch/reopen acceptance action. |
| Reuse/invalidation; cancel; retry after failure; subsequent run; timeout; no orphan workers; stale RUNNING; preserve upstream result | **Existing Recovery evidence retained.** | The non-skipped 12/12 matrix, Candidate native retry/close/quit and the new preserved-upstream proof remain valid. Rows moved to `DONE` only where their exact frozen technical gate is already established; no earlier PASS was rerun or inherited as a new Candidate. |
| Translation | **Out of this verification pass.** | Frozen Board classification is `NOT_DONE / INTEGRATE_EXISTING`; it is explicitly not a `VERIFY_EXISTING` item and was not exercised. |

### Board counts and next selection

The aggregated Board (48 rows; some owner items are intentionally represented by
one cross-cutting row) changed from **6 DONE / 24 IN_PROGRESS / 17 NOT_DONE / 1
BLOCKED** to **12 DONE / 16 IN_PROGRESS / 19 NOT_DONE / 1 BLOCKED**. Newly
`DONE`: one YouTube video, clean TXT, reuse intermediates, invalidation,
preserve upstream result, and select outputs before run. `Several local files`
and `Ordered processing` moved from `IN_PROGRESS` to `NOT_DONE` on direct
Candidate evidence; no other row was upgraded by implication.

The single next Board-selected action is **bounded multi-source failure
isolation**: record explicit per-selected-source terminal status and apply an
owner-defined continuation policy after a failed peer. It is not created here,
does not authorize a new WP, and must return to the frozen Board before work.
