# Process v1 WP1: existing proof and Recovery closure ledger

Status: `IN_PROGRESS`. Issue: [#169](https://github.com/Yurielo/integra/issues/169).
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
| Local media / ASR / SRT / Timeline / basic Topics | Representative local media | App → bridge → plan → `user_media` → pinned runtimes | Historical bounded owner/package proof | Reusable only | P156/CURRENT v2 | No transition until frozen-scope proof. |
| Multiple local / folder | Multiple selection and folder discovery | Source plan / S06 | Existing path; folder is NOT_DONE integration | Pending | Parity/DoD | No transition. |
| One YouTube | URL ingestion and result | `youtube_runtime → app → media` | Existing path requires packaged proof | Pending | S08 | No transition. |
| Translation | Selected translation outputs | VideoText translation worker | Existing/partial path | Pending | S14/V05/V06 | No transition. |
| Topics/review | Basic Topics and review | Topics worker / review runtime | P156 basic Topics; review unproven | Pending | S12/S20 | No transition. |
| Persistence/reuse | Reopen and invalidation | Project/run records / `asr_reuse` | Existing source-bound proof | Pending final Candidate | V21 and 12/12 ledger | No transition. |
| Recovery reliability | Lifecycle carrier | Shutdown/runtime/bridge repair | 12/12 reuse ledger; candidate proof missing | Pending reconciliation and Candidate | #161/#162 | No transition. |

No ledger row infers PASS from code, an adapter, historical issue, source test,
skipped test, or fake worker.
