# Product Owner decisions

Status: **PROPOSAL**. These are decisions genuinely reserved to the human Product Owner. They do not prevent completing the read-only audit, Issue or PR. FACT evidence and existing authority are in [the audit](FOUR_PRODUCT_ARCHITECTURE_AUDIT.md); implementation remains unstarted.

## D1 — adopt the coordinated architecture and its priority relationship

**FACT:** Four native products and accepted source authority already exist. Integra #257 proposes a sequential Master Knowledge roadmap; it remains OPEN. Current K2 candidate was withdrawn without acceptance. The proposed ecosystem roadmap must not silently replace either current repair scope or accepted canonical ownership.

**Decision:** Approve the adapter-first interoperability direction and its sequencing alongside the existing Knowledge Foundation and #257 proposal, or retain current separate roadmap priorities while deferring shared implementation.

**Recommended PROPOSAL:** Adopt the coordination roadmap as an additive plan: current Knowledge Foundation acceptance remains first for semantic expansion; M1/M2 correctness, provenance and resource contracts precede broad reuse; standalone translation/media work branches only when its own dependencies and scope permit it. Preserve SeminarText Canonical Evidence/Knowledge ownership, BookText document authority and VideoText media authority; Integra orchestrates and projects them. No source retirement or engine rewrite.

**Consequence:** Approval supplies direction, not blanket permission for every future stage, new dataset, release or external action. A bounded implementation issue still names exact native changes and gates. Rejecting/defering the proposal leaves all existing products/contracts/CURRENT unchanged. No new decision to transfer Knowledge ownership is requested; that alternative is unnecessary to the recommendation.

## D2 — shared artifact custody, discovery and cooperative resource participation

**FACT:** Existing caches and identities are product/project scoped. A globally discoverable store changes cross-project visibility, retention and responsibility. Native project ownership and Integra Project Lease cannot be replaced implicitly.

**Decision:** Approve the first exchange boundary and what may be indexed/reused across projects, including the owner of registry metadata and immutable shared copies.

**Recommended PROPOSAL:** Product-owned immutable artifacts plus versioned sidecar manifests and an opt-in, per-user, rebuildable local index. Start with explicit handoff/import; permit automatic compatible reuse only for the approved local scope. Keep source payload ownership in its native product and a single metadata writer per record. All participating apps honor one small host reservation protocol based on Integra's existing resource infrastructure, without requiring the Integra app or a new service.

**Alternative:** Export/import-only manifests with no global discovery initially. Lower privacy/retention complexity, but fewer automatic reuse benefits and no complete cross-app admission guarantee until clients participate.

**Boundary:** The decision must state visibility between projects, storage/copy policy and reference-aware retention. It does not authorize moving/deleting user sources, merging projects, altering protected candidate retention, unloading foreign models or accessing additional data. Technical hashing/schema details follow the approved boundary and do not require repeated permission.

## D3 — translation profile/review reuse and legacy transition scope

**FACT:** BookText document translation, VideoText cue translation and Integra Process translation have different context, validation and review semantics. SeminarText still has a legacy Qwen command; new routing through it is excluded by the user's request. Existing TranslateGemma selection is settled and does not need reopening.

**Decision:** Approve distinct document/transcript/subtitle profiles and the scope in which an existing human decision may be reused; authorize a bounded future SeminarText translation handoff/legacy transition if desired.

**Recommended PROPOSAL:** Reuse exact compatible translation revisions; carry prior semantic review only for unchanged owned text, language and decision scope. New subtitle layout or speech adaptation gets its own applicable QA/review. Preserve current product adapters and legacy artifact readability; do not silently remove the old command or replace native CDM/persistence. Extract common request/checkpoint code only after parity evidence.

**Alternative:** Permit cross-app export/import of translations while retaining all review in the producing application until a shared receipt contract is accepted. This is simpler initially but leaves repeated review and less automation.

**Boundary:** Approval of profiles is not acceptance of every translated output. Actual linguistic acceptance remains scoped to real samples/revisions. No new model, Qwen revival, fake CDM transcript or assumed literary-to-dubbing equivalence.

## Existing and later gates — not additional immediate approvals

These gates already follow native contracts or arise only if the relevant future scope is selected. They should not be presented as prerequisites to review this audit:

- Existing BookText #117 final visual and #114 residual product acceptance; current VideoText #49 exact candidate gates; existing SeminarText semantic/Dataset/Gold boundaries.
- Actual Integra Knowledge Foundation/K2 acceptance and any CURRENT promotion under existing rules. Issue closure or technical synthetic GUI proof does not replace it. The withdrawn candidate must not be re-presented as accepted.
- Before M5 activation: choose neutral voice/language/mix/tempo policy, review real narration/dubbing output, and separately authorize any model installation or distribution if needed. Voice cloning requires explicit appropriate identity/use consent; no such consent is inferred here.
- Before each #257 future semantic stage: input/output/DoD and real workflow acceptance; Publication and Marketing branches need their own approved claims/content.
- Signing/release, destructive migration, protected data, live external publication, credentials/accounts and retirement retain their existing separate authority boundaries.

## Not owner decisions

No approval is requested for reading repositories, recording facts, preserving accepted timing/semantic rules, deterministic documentation repair, keeping dirty worktrees intact, using the already installed TranslateGemma, fixing code to an already accepted policy after bounded implementation authorization, or maintaining one Issue/PR for this audit. Those are settled constraints or routine technical work.

## INFERENCE and UNVERIFIED

Three consolidated adoption decisions are sufficient to set direction; further choices should arise only at concrete milestones. No response, issue state or successful validator is architecture acceptance. No owner decision is recorded as made by this package.
