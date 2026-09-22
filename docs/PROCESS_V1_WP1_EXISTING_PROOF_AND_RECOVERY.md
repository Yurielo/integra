# Process v1 WP1: existing proof and Recovery closure ledger

Status: `BLOCKED`. Issue: [#169](https://github.com/Yurielo/integra/issues/169).
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
| Recovery reliability | Active close/quit, stale state, downstream failure → retry/reuse | Native app → packaged bridge → reconciled shutdown/runtime and pinned ASR cache | Fresh Candidate plus preserved source-bound ledger | PARTIAL PASS / proposal blocked | Close and quit both PASS; `native_asr_retry_probe` PASS (result SHA-256 `a46cf8…`); prior exact 12/12 reuse/invalidation remains valid. The stale-without-ownership case became `FAILED` with `STALE_RUNNING_RECONCILED`, did not signal its unrelated PID, and let the app close. | No Board transition: a strict PROPOSED record cannot yet be validated; see blocker below. |

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

## Blocker: strict PROPOSED material cannot be closed without a governance repair

`scripts/proposed_baseline_lite.py` requires `proposed_source` and
`proposed_head` to equal the repository's current `HEAD` and tree, and
`verify_promotion_material()` requires the candidate manifest, candidate evidence,
and report to be repository files at that same HEAD. A clean Candidate's manifest
necessarily binds the prior committed source. Adding those generated
Candidate-bound files and the PROPOSED record creates a new commit/tree; rebuilding
from that new tree creates a new manifest that again must be added.

The current validator does **not** compare the manifest's recorded source identity
to `proposed_source`. It could therefore be made structurally green by declaring a
later evidence-only commit as `proposed_source` while the referenced Candidate
truthfully records the earlier build commit. That would not be the strict
Candidate/source closure required by Issue #169, so it is not used. Conversely,
`allowed_overlay_paths` is structurally required but is not applied by the
exact-HEAD or source-binding checks. Producing a truthful
`PROPOSED_BASELINE_VALID / AWAITING_OWNER_ACCEPTANCE` record therefore requires a
governed Proposal Lite transaction/overlay repair, not a product repair and not a
weakening of identity validation. It is outside Issue #169. CURRENT remains
unchanged. This is the single cross-cutting blocker for WP1.

The current governed validator independently proves the same blocker on this
Recovery delta. Its exact fail-closed output is:

```
CURRENT v2 governed byte drift: macos/Resources/bridge.py
CURRENT v2 governed byte drift: integra_core/shutdown_runtime.py
R12 implementation hash differs: macos/Resources/bridge.py
R13 implementation hash differs: macos/Resources/bridge.py
```

`validate_governance.py` validates CURRENT and immutable R12/R13 before it can
consider a PROPOSED record; it has no declared-delta exception for a separately
governed proposal. Thus a real Recovery product delta cannot reach the requested
Proposal Lite state while CURRENT remains unchanged, even before the
Candidate/evidence transaction issue above. Altering CURRENT, historical R12/R13,
or these fail-closed checks is prohibited by this WP. This is one governance
mechanism blocker with two observed symptoms, not a claim that the Recovery
runtime requires repair.
