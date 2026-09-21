# Issue #157 — Post-MCWMA next-tranche checkpoint

Status: `NEXT_TRANCHE_PLAN_READY` (planning only; no product/test execution)

Date: 2026-09-22

This checkpoint uses the factual records from Issues #150, #151, #153, #155
and #156. It does not promote any capability to `USER_ACCEPTED` and does not
change component pins, product code, or runtime semantics.

## 1. Current truth after MCWMA

The Minimum Correctly Working macOS App (MCWMA) primary journey is now
owner-accepted on one immutable candidate:

`native macOS GUI → local Russian video → ASR/transcript → SRT → Word Timeline → Topics/timestamps → persisted accessible results → COMPLETED`

Evidence: Issue #156 owner acceptance, Candidate
`candidate-v1-c5851d168b116fed83109014519ebc01c0291e23705ac9d2ec0a4e5df2471960`,
bundle SHA-256
`90c6c816c7f4ec82b8a3393c46a5a96239ce7cbc16ba50a83677d78a0cdea8cb`, final
PR #154 HEAD `61afc7667b886cf363134d88c4b39aa813b5780e`, GitHub Quality Gate
run `35655533841` (`PASS`). The owner verified the real Russian video through
the normal GUI: `Готово`, `1 из 1`, transcript acceptable, 174 aligned Word
Timeline entries, and Topics with timestamps. Topics remain semantic
`REVIEW_REQUIRED`; that is intentional and is not a Knowledge acceptance.

The accepted journey is the current product baseline, not a claim that the
long-term Integra vision is complete. Issue #155 classified the historical
Word Timeline failure as
`HISTORICAL_NON_REPRODUCIBLE_WITH_INSUFFICIENT_ORIGINAL_DIAGNOSTICS`; it did
not establish a repair for that historical run. Issue #153 established the
canonical candidate/governance/evidence controls used by #156.

## 2. Journeys still needed for a fully working Integra

“Fully working” is interpreted as a sequence of coherent, user-visible
journeys, not as every planned studio or adapter. The following journeys still
need packaged evidence and, where marked, owner acceptance:

| Journey | Current evidence | What is still needed | Value | Cost | Risk | Decision |
|---|---|---|---:|---:|---:|---|
| Recovery #137 | Partial lifecycle/retry mechanisms; not a completed owner journey | truthful failure, cancel, restart/reuse, and subsequent success without restart; persisted diagnostics and no orphan workers | 5/5 | 3/5 | 5/5 | **NEXT WP1** |
| Translation | VideoText adapter/runtime exists; audit says UI/output path is partial and not owner-accepted | one readable translated TXT/SRT path, provenance, language contract, realistic fixture, recovery/reuse behavior | 4/5 | 2/5 | 3/5 | **NEXT WP2** |
| BookText/OCR | Real BookText CLI and page selection are integrated; broader OCR quality/provenance is not accepted | clean-bundle OCR of permitted PDF/image fixtures, page/region provenance, explicit QA/PDF limitations | 4/5 | 4/5 | 4/5 | **NEXT WP3** |
| YouTube | Single-video ingestion exists; external availability is conditional; playlist does not continue through the full pipeline | deterministic source contract plus one non-private single-video journey; playlist checkpoints and downstream continuation remain open | 3/5 | 3/5 | 4/5 | DEFER |
| Publication | One-way Obsidian and filesystem-backed OneDrive package paths exist | reviewed-package selection, preview/hash/atomic promotion, offline/recovery semantics; no claim of cloud confirmation | 3/5 | 3/5 | 4/5 | DEFER |
| Multi-source | Sequential multiple-file processing exists; no runtime corpus/alignment output with complete lineage | two-source project, completeness guard, cross-source provenance/alignment, review-ready outputs | 5/5 | 5/5 | 5/5 | DEFER until WP1–WP3 and review contract |
| Knowledge/Evidence | machine Evidence and limited V1 bridge exist; Topics are still `REVIEW_REQUIRED` | explicit human review, canonical Evidence/Knowledge creation, source→quote→word/time/page navigation | 5/5 | 5/5 | 5/5 | DEFER until review + multi-source prerequisites |

Scores are relative planning scores (5 = highest), not measurements. The
dominant risk is spending effort on broad downstream semantics before failure
recovery, reusable outputs, and source provenance are reliable.

The minimum additional user-facing set for a credible “working Integra” is
therefore: the accepted primary journey, truthful Recovery, one translation
journey, and one bounded document/OCR journey. Multi-source, Knowledge/Evidence
and publication remain necessary for the broader product definition, but are
not efficient immediate work while the reliability and source-family gates are
still unproven.

## 3. Exactly three dependency-ordered next work packages

### WP1 — Recovery and run-lifecycle acceptance (#137)

**Outcome:** a failed, cancelled, interrupted, or downstream-invalid run is
truthfully represented, leaves no orphan worker, reuses hash/model/config-bound
artifacts when valid, and can be followed by a successful run without an app
restart.

**Dependencies:** accepted MCWMA primary journey; Candidate-bound observability
from #153–#156. **Non-goals:** translation, OCR, YouTube, publication,
multi-source, Knowledge/Evidence.

**Cheapest useful gate:** deterministic controlled worker failure with persisted
command/runtime/exit/timeout/stdout/stderr/input-output identities, followed by
a successful production-orchestration run. Then run the packaged realistic
recovery scenario. Owner entry is allowed only after both packaged gates and a
known-failure regression pass on one new Candidate.

### WP2 — Translation journey

**Outcome:** from an accepted transcript/SRT, the normal GUI/production path
creates a readable translated TXT/SRT with explicit source/target language,
provenance, validation, and persisted result state. Existing VideoText pins and
translation semantics remain unchanged.

**Dependencies:** WP1 recovery/reuse contract and the accepted primary output
contract. **Non-goals:** topic translation, publication, automatic semantic
acceptance, or a new translation engine.

**Cheapest useful gate:** adapter contract and one production-orchestration
integration fixture; then packaged deterministic and realistic language
fixtures, including cancellation/retry and no-empty-success checks. Owner
entry requires a readable output and correct source/result lineage.

### WP3 — Bounded BookText/OCR journey

**Outcome:** a permitted local PDF/image fixture can be selected, processed by
the pinned bundled BookText runtime, and produce OCR text plus page/region
provenance and explicit QA/PDF status through the normal app path.

**Dependencies:** WP1 lifecycle/recovery and the immutable bundle/runtime
contract; it does not import historical source-project state. **Non-goals:**
DjVu, ordered image-book semantics, illustration descriptions, semantic
chaptering, or Knowledge promotion.

**Cheapest useful gate:** preflight/hash and page-selection contract on a tiny
fixture; then packaged OCR smoke and one realistic non-private document. Owner
entry requires visible page identity and truthful failure for optional
searchable-PDF/QA limitations.

Multi-source is intentionally after these three because it multiplies failure
surface and depends on stable lifecycle, source-artifact contracts, and at
least two proven source families. Knowledge/Evidence and publication are after
explicit review/provenance and multi-source contracts; they are not silently
pulled into WP3.

## 4. PR #154 and old Issue disposition

### PR #154 — `codex/stabilization-mcwma`

**Decision: KEEP as the canonical MCWMA stabilization record; do not add the
next tranche to it.** It contains the WP1 governance baseline, WP2 historical
classification, the bounded ffmpeg repair, and the final #156 owner-accepted
primary journey. It should remain a single auditable lineage and be made ready
for owner review/merge only in a separate owner-authorized action. No merge or
deploy is performed by this checkpoint.

The three next WPs must branch from the accepted/main decision explicitly; no
historical PR is to be cherry-picked wholesale and no Candidate evidence is
transferred implicitly.

### Issues #150, #151, #153, #155, #156

| Item | Disposition |
|---|---|
| #150 deep-reset audit | Retain as historical causal audit; close/supersede only after this checkpoint is accepted, with a link to this plan. |
| #151 resource-efficient strategy | Retain as governing strategy record; this checkpoint is its post-MCWMA execution update, not a replacement of its safeguards. |
| #153 WP1 baseline | Technical work complete and evidenced in PR #154; close after owner records the disposition, without rewriting historical evidence. |
| #155 WP2 classification | Complete as `HISTORICAL_NON_REPRODUCIBLE_WITH_INSUFFICIENT_ORIGINAL_DIAGNOSTICS`; close as a classification checkpoint, not as proof the old failure was repaired. |
| #156 WP3 primary journey | Preserve closed `USER_ACCEPTED` record; do not reopen unless a later change invalidates the accepted Candidate/product contract. |
| #137 Recovery | Keep OPEN and promote to the next implementation WP1. |

Older experimental/stacked Issues and PRs should be treated as historical or
superseded evidence unless they contain a current dependency required by one of
the three WPs. Do not revive them by broad cherry-pick, and do not use closure
or a roadmap `ACCEPTED` label as product acceptance evidence.

## 5. Stop rules for the next tranche

- One new immutable Candidate per repair/build identity; no evidence transfer.
- No owner handoff before deterministic **and** realistic packaged gates pass.
- At most two bounded repair cycles per WP before root-cause escalation and
  owner review of scope.
- Stop immediately when a cheaper prerequisite gate is red; do not run the
  full suite or secondary journey to create noise.
- No work on YouTube playlist continuation, publication, multi-source,
  Knowledge/Evidence, Marketing, Learning, Assistant, or social adapters until
  the three WPs above have coherent evidence.

This is a planning checkpoint only. No tests were rerun, no product code was
changed, and no merge/deploy was performed.
