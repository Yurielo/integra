# Confirmed duplication and technical debt

## Confirmed, evidence-backed duplication or overlap

| Finding | Classification | Why it exists now | Cost / risk | Smallest safe direction |
| --- | --- | --- | --- | --- |
| Two capable ASR stacks: active SeminarText CLI and unused-for-Process VideoText segmented Whisper | Temporary transition / unintegrated reuse | #125 selected SeminarText for the current native route; #187 later authorized proof-first VideoText-only feasibility | Two sets of profiles, quality semantics and artifacts; risk of false equivalence | Build one bounded VideoText Process adapter and compare before retiring nothing |
| Two topic engines: active SeminarText and VideoText HybridTopicAdapter | Actual capability overlap, not yet production duplication | Current Process contract follows SeminarText shape; VideoText mapping is unproved | Conflicting boundaries/titles/provenance if both are exposed | Map VideoText output once at an explicit Process draft boundary; retain review authority |
| Two translation implementations: VideoText TranslationAdapter and active Integra TranslateGemma | Intentional runtime ownership split | Translation runtime was explicitly migrated to TranslateGemma; VideoText source capability remains bundled for media worker/source product | Confusing architecture wording and possible accidental dual path | State clearly that Integra owns Process translation; do not remove VideoText historical/source support without a separate compatibility decision |
| SRT emitted by SeminarText then normalized/used by VideoText services | Cross-component handoff | Existing selection combines SeminarText ASR with VideoText media functions | Serialization/validation boundary can fail and requires provenance bridging | VideoText-native ASR would remove this handoff only after proof |
| Document native extraction in Integra and BookText native/OCR extraction | Intentional layered separation with partial overlap | Integra supports safe lightweight formats; BookText handles heavier OCR/document review | Divergent document records and loss of BookText fidelity if implicit conversion grows | Keep Integra native extraction; use a single bounded BookText artifact adapter for OCR-heavy inputs |
| Review/Knowledge wrappers in Integra around SeminarText modules | Bounded adapter, not a second semantic engine | Integra needs UI/project bindings and source protection | Packaged copies can drift from source contracts if pin checks weaken | Continue exact byte/hash checks; do not reimplement semantic validators |

## Not confirmed as production duplication

- A synthetic transcript that contains repeated text is not evidence that either
  ASR implementation creates the repetition. The audited evidence does not
  identify whether it belongs to input media, fixture construction, ASR,
  assembly, cleaning or downstream processing.
- Integra's job/cancellation/retention logic is not a duplicate of VideoText
  processing logic. It is intentionally the cross-capability control plane.
- Integra's Word Timeline adapter is not an evidenced VideoText duplicate.
- BookText's CDM/review pipeline is not duplicated in Integra; it is mostly
  missing from the integration boundary.

## Why reuse has not happened everywhere

1. Earlier accepted R5 ownership chose different providers per capability;
   later native user-media work selected SeminarText ASR before #187's
   VideoText-only proof-first decision.
2. Existing VideoText capability is source-level evidence, not automatically a
   compatible packaged Integra Process result.
3. Integra intentionally owns lifecycle, dependency preflight, artifacts,
   project isolation, UI and publication, so a direct source-app project call
   is not an acceptable replacement for the control plane.
4. BookText's richer import contract is still draft and its direct-to-Knowledge
   path needs distinct semantic/provenance verification.

## Debt priority

1. **High:** resolve the Process ASR/topic ownership only through #187's proof
   matrix; this removes the highest operational overlap without risking
   SeminarText retirement.
2. **High:** make selected-capability runtime closure explicit so a VideoText
   route cannot accidentally preflight/import SeminarText.
3. **Medium:** stabilize BookText's artifact adapter before adding any richer
   document Knowledge UI.
4. **Medium:** update architecture wording after evidence changes so the
   documented R5 target and current #125 execution route cannot be confused.
