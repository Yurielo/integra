# Local Semantic Review GUI v1 — proposed integration scope

Status: **IMPLEMENTED_IN_ISSUE_317_BRANCH_PENDING_PACKAGED_CANDIDATE_AND_OWNER_TEST**.
Authority: [Integra Issue #315](https://github.com/Yurielo/integra/issues/315),
Owner Option A decision, 2026-11-02, and explicit implementation authorization
for [Issue #317](https://github.com/Yurielo/integra/issues/317). This remains a
bounded first slice under the existing Product Definition, Plan, Roadmap and
State; it is not a semantic acceptance result or an installed release.

## 1. Approved outcome and first boundary

Integra is the primary local macOS interface for source processing, explicit
semantic review and knowledge navigation. Ordinary users must not require Codex,
GitHub, a Git checkout, terminal commands or hand-authored JSON to process a
seminar. Versioned local provider calls are implementation details behind the UI.

The smallest first implementation proposal is **one already prepared review
package for one source/transcript revision**: choose it in Integra, view exact
Topic/Concept/relation proposals and evidence, record explicit choices through
SeminarText, apply, close/reopen and retain earlier decisions and deferred rounds.
It excludes new extraction/generation, Concept identity merging, arbitrary draft
formats, document ingress, cross-seminar UPDATE and a full historical knowledge
browser. It does not claim the complete source-to-knowledge Option A journey.
Automatic preparation from ordinary Process results remains a separately scoped
integration gap; this first slice must not present manual JSON preparation as
the finished end-user workflow.

Four products remain independent:

| Owner | Domain and proposed Integra relationship |
| --- | --- |
| SeminarText | ASR, timing/Word Timeline, Canonical Evidence, semantic proposal/review contracts and Canonical Knowledge admission; Integra displays inputs and sends human choices to its provider interface |
| BookText | Document extraction/OCR/structure and its own document-review contract; a future versioned mapping preserves page/region evidence before ST admission |
| VideoText | Video/media/subtitles; source seeking or derivatives do not change semantic records |
| Integra | Local UI, orchestration, source selection, leases/jobs, adapter error handling and derived views; no second semantic engine or Canonical Knowledge writer |

## 2. Verified source snapshot and reuse

Revisions are planning evidence, not installed releases or new runtime pins:

| Source | Exact revision / state |
| --- | --- |
| Integra main | `55141b8688996a4ba19f1cffb0930bb61a9561f6` |
| SeminarText main / merged #159 | `9177e0cce11d17097b0fd8f46ce553c2a9dba949`; #158 reusable semantic workflow is source-checkout delivery |
| SeminarText #68 / Draft #121 | `70920d686625fb7358ff621dc20d2d8481ea7e0e`; real-seminar DOMAIN_REVIEW remains separate |
| Integra #279 / open #280 | `e32deb6b388d354709a87977abc007fd08aa57c4`; K2 has its own schema/lifecycle gates |
| Integra #304 / Draft #305 | `6fa1e1f218293a563b13ece0d7a61b851e87b315`; read-only AppKit Library, separate Owner Test |
| BookText main | `7219d0e6eee74c2c2f90e8cff6e9da624b6cb52a` |
| VideoText main | `f715f11df72f8e4e806b70b2a2f86cf097a6bf6c`; observed only, not adopted as a replacement pin |
| Four Products main | `ac73a560a2b1fb7f37015d2c3cececb962cd99e8`, `ROADMAP.md` |

Integra already has native Process Topic decisions, K1 exact-fragment review,
source/Word navigation, an R9A read projection, immutable result/package
mechanisms, Operations/Project Lease, and export primitives. Reuse those verified
boundaries; see [current UI matrix](../UI_IMPLEMENTATION_MATRIX.md#issue-315-current-semantic-review-boundary).
K1 reviewed fragments are not full Canonical Knowledge. R9A's pinned Golden
Slice allowlist is not arbitrary user-package admission. K2 #280 and Library
#305 cannot be called merged, installed or accepted by this proposal.

## 3. Exact producer/consumer contracts

| Interface | Producer → consumer | Version / available boundary |
| --- | --- | --- |
| Existing prepared semantic input | Bound proposal producer → SeminarText compiler, via Integra transport | `seminartext.reviewed_knowledge_admission_v1`, schema `1.0.0`, `schemas/reviewed_knowledge_admission_v1.schema.json`; exact schema SHA-256 `8a2bc43300086a04a8d8c2ab19b3b5b895610f00a20ac28393d187e3d69ab1c5` |
| Review orchestration | SeminarText public CLI ↔ proposed Integra adapter | `project-semantic-workflow` v1; provider-owned `seminartext.semantic_workflow` snapshot version `1.0.0`; no dedicated snapshot JSON Schema was introduced |
| Evidence / fragment input | SeminarText formats → provider validation and Integra display | Canonical Evidence v1 and `seminartext.machine_derived_fragment_result` v1; exact source/transcript and Word **or cue** precision retained |
| Applied result | SeminarText compiler → Integra derived result view | `result` returns the validated canonical revision JSON; knowledge schema remains provider-owned `canonical_knowledge_v1`, not an Integra clone |
| Consumer binding | Integra local UI ↔ governed local provider process | **Proposed adapter v1**, not an existing schema/API: fixed provider identity and closure, six input-role hashes, workflow locator, package ID/hash, proposal IDs/hashes, explicit reviewer/envelope and returned revision/parent hashes |
| Existing narrow Topic review | SeminarText Topic contracts ↔ current Integra Topic/K1 adapters | Topic v1 ACCEPT/RENAME/SPLIT/MERGE/REJECT/DEFER and v2 fragment transactions are separate contracts, not aliases for the new workflow's actions |
| BookText machine transport | BookText → future document consumer adapter | `booktext machine` local JSONL protocol `1.1`; CDM `book_document` schema `1.0`, page/block provenance; unsupported majors fail closed |
| BookText portable/OCR artifacts | BookText → existing preview or future mapping | Internal `booktext.document` / `booktext.package_manifest` `0.1`; `booktext.integra_ocr_candidate` `0.1` is DRAFT. Shape/compatibility validation is not Knowledge admission |

The workflow accepts **CREATE only**, one source/revision and machine-derived
fragments. Its admission v1 input restricts the declared proposal producer to
`integra`. Preserve that restriction and the actual generation provenance; do
not relabel arbitrary SeminarText output as Integra-produced or claim that the
wrapper generated proposals. A compatible prepared input is the first-slice
precondition. A broader producer/format mapping needs an explicit versioned
provider contract; no inference engine or permissive re-signing is implied.

Six files are bound by public `prepare`: `--evidence`, `--fragments`,
`--proposals`, `--source`, `--notebook`, `--producer-runtime`. Notebook JSON must
bind the declared notebook ID and hash; producer-runtime bytes are checked,
never executed as part of this workflow. Source bytes and all input hashes are
rechecked on reopen/publication. Symlinks, stale inputs and unsupported formats
fail closed. The app must resolve these roles internally after a user selects a
compatible local package, rather than expose six terminal steps.

## 4. Proposed GUI operation map

The existing public owner command is
`./seminartext project-semantic-workflow {prepare,inspect,status,decide,submit,apply,validate,next-round,result}`.
The future adapter uses its exact reviewed closure through an allowlisted local
process boundary; it must not import provider-private helpers or accept an
arbitrary command from the UI.

| GUI function | Existing provider operation / missing consumer work |
| --- | --- |
| Open prepared review | Resolve six role bindings; `prepare` only for a new Integra-owned workflow directory, otherwise `status`/`inspect` on that exact existing workflow. Current package identity is always returned by ST |
| Show proposal and exact source | Read documented structured proposal/Evidence/fragment inputs after provider validation; preserve IDs, original quote, assurance, precision, locator and availability. `inspect` is human Markdown, **not** a typed inspection endpoint |
| Choose and save | No default acceptance. Collect supported action/reason/reviewer, exact proposal hashes and confirmation of the displayed package. Use `decide` or a `submit` human envelope; partial submissions remain pending |
| Apply explicit round | `apply` only when every proposal has an explicit choice; then `validate` and `result`. Missing choices are not invented DEFER. Accepted relations require accepted endpoints in that batch or an earlier choice |
| Close/reopen and retry | Revalidate current inputs and public `status`; recover the same workflow, package and exact submitted envelopes/operation receipts. An exact lost-response replay is idempotent; a conflicting same-round choice is an error, never overwrite |
| Revisit deferred work | After apply, `next-round` creates a new package ID/hash and parent reference for explicit DEFER only. Old snapshots, accepted entities and decisions remain. Rejected items/new proposals require a new supported input workflow |

For Topic, Concept and Relation records the workflow actions are
**ACCEPT / EDIT / REJECT / DEFER**. EDIT is limited to Topic title/summary,
Concept preferred_label/description/aliases and Relation relation_type. IDs,
source binding, exact evidence and provenance cannot be edited. Alias text
editing is not SAME_CONCEPT/NEW_CONCEPT/RELATED/DISTINCT identity resolution;
merging/redirecting Concept identities is unavailable in this first slice.

Provider numbered/hash-linked snapshots remain authoritative and immutable.
Integra's existing JobStore may retain transport requests/public result receipts
as derived recovery evidence, not another canonical ReviewDecision ledger.
Reopen must verify stored envelopes against the provider (including exact retry
where needed), not trust a local display cache. If those receipts are missing or
cannot be reconciled, show an unavailable/read-only state, not invented edits.
The implementation delivers an ST-owned typed `projection` command alongside
the existing workflow operations. It returns validated visible records, exact
Evidence, transcript assurance, saved choices and compact round history without
exposing provider snapshot filenames or local paths. Integra uses this public
projection; it does not read provider-private snapshots.

Use existing Project Lease and Operations ownership around the Integra-owned
mutable workflow location, plus the provider's nonblocking lock. A busy/stale
lease, interrupted request or lost response must reopen and verify durable
provider state before retry or success. No fabricated progress, rollback of a
published decision, parallel job store or second knowledge database is allowed.

## 5. Dependencies, readiness and exclusions

1. **Provider delivery gap:** #159 is source-checkout functionality, not installed
   activation. Current Integra baseline pins older ST contracts at
   `a94936cd77cde13561c97c804ece1ac1134e01a6`; these pins do not establish the new
   workflow. A future authorized integration must qualify an exact packaged
   workflow/compiler/schema closure and compatibility matrix. #315 changes none
   of those pins or installed files. End-user acceptance cannot depend on a
   developer checkout being present.
2. **Missing consumer:** general proposal display, explicit submit/apply, durable
   reopen/deferred-round UI and error/availability presentation for this workflow
   are not established. Existing Process/K1 adapters are reuse, not a substitute.
3. **Parallel work:** inspect/reuse K2 #280 and Library #305 only after their
   exact accepted compatibility/lifecycle state permits it. Do not edit their
   branches, candidates or Owner results. File-picker + prepared-package review
   need not wait for a library browser; a dynamic Knowledge view cannot borrow
   an unmerged K2 fix or the R9A historical allowlist as proof.
4. **Separate semantic gates:** ST #68/#121 data, human decisions and legacy
   Issue #68 active-only batch helper are not this interface. Reusable workflow
   `next-round` does not prove a migration of those seven deferred links. No real
   Stress Code, Dataset/Gold or other user materials are required for technical
   first-slice verification.
5. **Broader target:** BookText document-to-Evidence/admission mapping, automatic
   prepared-proposal production from ordinary Process results, cross-source
   UPDATE and full accumulated-knowledge history navigation remain explicit
   later bounded integrations. No invented time/Word precision for documents.

Historical R14 acceptance is not reopened. Native GUI integration acceptance,
packaged provider readiness, real-seminar S1 DOMAIN_REVIEW and S2/S3 semantics
are different evidence layers. Synthetic technical work may be authorized
without waiting for semantic acceptance of Stress Code, but cannot supply it.
Four Products **S1 → Release/Integration Readiness → S2 → S3** remains unchanged.

## 6. Proposed implementation acceptance criteria

- A local user opens a compatible prepared package and reviews all three entity
  kinds in native macOS controls, without Codex, GitHub, terminal or JSON editing.
  Missing provider or unsupported package is disabled with a factual reason.
- Displayed package/proposal hashes and exact source/Word-or-cue locator/assurance
  match the validated bytes. Missing media remains visible and cannot acquire a
  fabricated route. No automatic semantic choices or identity merges occur.
- Partial/mixed explicit submissions, invalid batch atomicity, endpoint dependency
  errors, stale/unsupported/changed inputs and lease/lock contention fail safely.
- Close/reopen retains original proposals, explicit choices, current package and
  provider result/parent identities. Lost-response replay is idempotent; crash
  recovery and missing local receipt cases never overwrite historical decisions.
- DEFER → apply → next-round → a different explicit human decision preserves the
  first receipt, uses the new package hash and retains prior accepted entities.
- Reuse ST #158 synthetic astronomy/Word and botany/cue fixtures for contract
  evidence; actual native interaction and independent QA are additional evidence.
  Test actors remain labelled synthetic; PASS does not accept seminar semantics.
- Regress existing Process/K1, navigation/export and provider compatibility;
  perform later Candidate/Owner/release steps only under their normal authority.
  This planning task performs no build, Candidate promotion or activation.

## 7. Next authorized action and references

#315 may complete its documentation/governance PR under the already accepted
safe-merge policy. **Next genuine boundary: explicit authorization of the above
bounded implementation and provider-delivery scope.** Option A is already
decided; do not ask the Owner to choose it again. Do not create a new
implementation Issue, code the GUI, advance #305/#280 or build/promote a
Candidate from this proposal alone.

Primary source contracts inspected at the exact revisions in section 2:

- ST `docs/architecture/SEMANTIC_PROCESSING_WORKFLOW_V1.md`,
  `seminartext_modules/semantic_workflow.py`,
  `docs/architecture/REVIEWED_KNOWLEDGE_ADMISSION_V1.md`,
  `schemas/reviewed_knowledge_admission_v1.schema.json`,
  `tests/test_semantic_workflow.py` (read-only inspection; existing #158 evidence reused).
- Integra `macos/IntegraApp.swift`, `macos/Resources/bridge.py`,
  `integra_core/seminartext_topic_review_runtime.py`, `knowledge_notebook.py`,
  `knowledge.py`, and `docs/architecture/SEMINAR_LIBRARY_PREVIEW_V1.md`.
- BookText `docs/architecture/MACHINE_PROTOCOL.md`, `tools/canonical_document.py`,
  `tools/build_document_package.py`, `docs/INTEGRA_OCR_ADAPTER_CONTRACT.md`.
- [Four Products ROADMAP](https://github.com/Yurielo/four-product-architecture/blob/ac73a560a2b1fb7f37015d2c3cececb962cd99e8/ROADMAP.md), SHA-256 `c9e25d2942c4c8c23ec69949a4671ec69462660b838769494f7987b66fc0e63e`.
- [Unified rules](../governance/UNIFIED_CODEX_RULES.md), read at Integra
  `55141b8688996a4ba19f1cffb0930bb61a9561f6`, SHA-256
  `8b8e31c7620d45e1e14429e07e7b97b2adc118745ce781a55b932213c55b646b`.
- ST `AGENTS.md`, `DEVELOPMENT_WORKFLOW.md`, Roadmap/State and Product Rules
  read at `9177e0cce11d17097b0fd8f46ce553c2a9dba949`; Registry SHA-256
  `b59ba7205120ec1a0dd8fe0f881c26c8056ba7feb61bebd27c7100b59b899492`.

PRODUCT_RULES_READ: YES

APPLICABLE_PRODUCT_RULES: PR-001, PR-002, PR-003, PR-004, PR-005, PR-006,
PR-007, PR-008, PR-010, PR-011, PR-012, PR-013, PR-014.

PRODUCT_RULE_CONFLICTS: NONE. The implementation uses a separate bundled
`runtime/seminartext-semantic` provider closure; it does not replace the active
SeminarText ASR runtime, alter an installed app/CURRENT, or use Stress Code data.

## 8. Implemented human review flow (Issue #317)

The native **База знаний** screen now offers “Проверить подготовленный пакет
знаний…”. The user selects one compatible prepared-package folder; Integra
resolves all six bound input roles and validates them through the packaged
SeminarText provider. The user never edits JSON or invokes a terminal.

For every Topic, Concept or Relation proposal, the screen places the original
wording and exact quote/locator next to four plain-language choices:

- Принять как есть;
- Исправить формулировку;
- Отклонить — не добавлять;
- Отложить на следующий раунд.

Choosing **Исправить** reveals only fields that this v1 contract actually lets
the user change, with human labels. Source bindings, identifiers, exact Evidence
and provenance remain visibly non-editable. A choice is merely local screen
state until the user presses “Сохранить выбранные решения” and confirms the
summary. After saving, the UI labels it as immutable review history rather than
pretending it can be edited. An applied round can open a new round only for
explicitly deferred items, preserving the earlier result and receipt.

Integra retains only package-location and submitted-envelope recovery records
in its app data. SeminarText remains the authority for decisions, validation,
revisions and canonical results. Reopening the package revalidates it against
the provider before displaying it again.

The remaining release gates are deliberate: package the exact provider closure
into a new Candidate, perform native interaction/independent QA using the
synthetic fixtures, then conduct the Owner test. None of those steps can claim
acceptance of any real seminar semantics.
