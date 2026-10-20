# Product Owner decisions

Status: **the Product Owner accepted the adapter-first planning direction and the seven clarification boundaries**. This records that planning decision, not implementation, release, CURRENT promotion or semantic acceptance. FACT evidence and existing authority are in [the audit](FOUR_PRODUCT_ARCHITECTURE_AUDIT.md); implementation remains unstarted.

## D1 — adopt the coordinated architecture and its priority relationship

**FACT:** Four native products and accepted source authority already exist. Integra #257 proposes a sequential Master Knowledge roadmap; it remains OPEN. Current K2 candidate was withdrawn without acceptance. The proposed ecosystem roadmap must not silently replace either current repair scope or accepted canonical ownership.

**Accepted planning direction:** Use adapter-first interoperability and its sequencing alongside the existing Knowledge Foundation and #257 proposal. This does not replace current separate roadmap priorities or authorize shared implementation.

**Recommended PROPOSAL:** Adopt the coordination roadmap as an additive plan: current Knowledge Foundation acceptance remains first for semantic expansion; M1/M2 correctness, provenance and resource contracts precede broad reuse; standalone translation/media work branches only when its own dependencies and scope permit it. Preserve SeminarText Canonical Evidence/Knowledge ownership, BookText document authority and VideoText media authority; Integra orchestrates and projects them. No source retirement or engine rewrite.

**Consequence:** Acceptance supplies direction, not blanket permission for every future stage, new dataset, release or external action. A bounded implementation issue still names exact native changes and gates. All existing products/contracts/CURRENT remain unchanged. No new decision to transfer Knowledge ownership is recorded; that alternative is unnecessary to the recommendation.

## D2 — shared artifact custody, discovery and cooperative resource participation

**FACT:** Existing caches and identities are product/project scoped. A globally discoverable store changes cross-project visibility, retention and responsibility. Native project ownership and Integra Project Lease cannot be replaced implicitly.

**Accepted planning boundary:** Start with versioned sidecar manifests and explicit read-only handoff/import. An opt-in, rebuildable discovery index may later index references and validation metadata, but is distinct from physical storage and does not create a mandatory global store, discovery service or automatic reuse path.

**Implementation still to be scoped:** Keep artifacts product-owned and immutable. A future opt-in local index needs an exact visibility, storage/copy and reference-aware retention scope before it can drive discovery or reuse. Initial handoff/import remains explicit and read-only. Participating apps may adopt one small host reservation protocol based on Integra's existing resource infrastructure, without requiring the Integra app, daemon or new service.

**Alternative:** Export/import-only manifests with no global discovery initially. Lower privacy/retention complexity, but fewer automatic reuse benefits and no complete cross-app admission guarantee until clients participate.

**Boundary:** This planning acceptance does not yet state visibility between projects, storage/copy policy or reference-aware retention for a future implementation. It does not authorize moving/deleting user sources, merging projects, altering protected candidate retention, unloading foreign models based only on model name or accessing additional data. Technical hashing/schema details follow the accepted planning boundary; implementation remains separately scoped.

## D3 — translation profile/review reuse and legacy transition scope

**FACT:** BookText document translation, VideoText cue translation and Integra Process translation have different context, validation and review semantics. SeminarText still has a legacy Qwen command; new routing through it is excluded by the user's request. Existing TranslateGemma selection is settled and does not need reopening.

**Accepted planning boundary:** Preserve distinct document, transcript, cue-safe subtitle and speech-adapted profiles. Permit only exact compatible reuse whose source, ordered context, glossary, model/runtime, prompt and profile identities match. This does not authorize a SeminarText translation handoff or legacy transition.

**Implementation still to be scoped:** Reuse exact compatible translation revisions; carry prior semantic review only as linked evidence for unchanged owned text, language and decision scope. Never transfer semantic acceptance automatically. New subtitle layout or speech adaptation gets its own applicable QA/review. Preserve current product adapters and legacy artifact readability; do not silently remove the old command or replace native CDM/persistence. Extract common request/checkpoint code only after parity evidence.

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

The owner has accepted the three planning directions recorded above and all seven review clarifications. Further choices arise only at concrete milestones. This record is not approval of implementation, a release, a candidate/CURRENT promotion or any semantic result; successful validators and issue state cannot supply those later decisions.
