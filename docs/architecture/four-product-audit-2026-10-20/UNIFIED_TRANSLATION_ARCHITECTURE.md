# Unified translation architecture

Status: **accepted profile/reuse planning direction; implementation remains a PROPOSAL**, 2026-10-20. Existing accepted translation paths remain authoritative. [Audit evidence](FOUR_PRODUCT_ARCHITECTURE_AUDIT.md) distinguishes repository implementation, tests, real material, installed runtime and owner acceptance.

The accepted direction fixes four distinct profiles—**document, transcript, cue-safe subtitle and speech-adapted translation**—rather than a universal translation result. A future reuse hit must bind the complete effective source, ordered context, glossary, model, prompt and profile identities. This does not automatically accept a target-language result semantically, authorize a provider/model change or begin implementation.

## FACT — current translation is shared at the model level, not at the execution contract

| Product | Current implementation and boundary | Proven behavior and limitations |
| --- | --- | --- |
| BookText | `tools/translation.py`, CDM logical units, Ollama `/api/chat`, `translategemma:4b` | Source context, glossary, numeric/script/repetition checks, per-unit/chunk checkpoints, language pair EN↔RU. Requires validated `book_document.json`; excludes table/figure/page-break units. Bounded #131 semantic acceptance and #116 real pipeline evidence. |
| VideoText | `TranslationAdapter.swift` plus selected-timing translation branch | Cue ownership, context/coverage, exact source revisions, subtitle clocks and semantic-review contracts. Current TranslateGemma text-only selected-timing path is distinct from historical JSON cue ownership. EN↔RU subtitle acceptance recorded; dubbing remains disabled. |
| Integra | `integra_core/translategemma_runtime.py`, `user_media.py`, `topic_translation.py` | Its own production inference adapter, pinned model/full digest, deterministic cue serialization, RU↔EN, readable TXT and provenance. Source ASR can be reused. Historical VideoText/Qwen proof is not the active provider. |
| SeminarText | `seminartext_modules/seminartext_translate.py` | Executable legacy EN→RU Qwen command with coarse batching/existence reuse; no equivalent current TranslateGemma revision contract. Exclude it from new translation routing; preserve historical artifacts. |

The live read-only Ollama inventory returned both `translategemma:4b` and `translategemma:4b-it-q4_K_M` with identical full digest `c49d986b0764f5881c476eb21435bb62b7abc62347aab3d4a6071e811be510a1`, reported stored size 3,298,875,707 bytes. These aliases do not establish identical prompts, output quality or cache contracts. No inference, download or full layer rehash was performed by this audit. Retain the installed TranslateGemma. There is no evidence here justifying another model.

BookText's `TRANSLATION_QUALITY_FIX_PLAN.md` explicitly marks its older Qwen plan superseded by #131. The #131 owner accepted bounded real EN→RU and RU→EN samples; #116 subsequently proved a four-page, seven-unit document pipeline and interrupted resume. Those findings should not be rebuilt or described as still blocked merely because an earlier Qwen run failed. Conversely, acceptance of one release/sample does not accept every future translated document.

## FACT — what is already valuable and what differs

BookText owns complete logical blocks, passes bounded title/heading/neighbor context, fingerprints source/CDM, model digest, prompt/quality policy, glossary, language and options, and preserves atomic partial checkpoints. Glossary path and whole-CDM hashing constrain reuse across projects. Eligible units omit tables; source-preserving translated export keeps assets rather than inventing translations for them. Quality flags pause its sequential pipeline before export. A full per-revision translation decision/edit command was not found, so runtime semantic review lifecycle is PARTIAL.

VideoText must preserve cue ownership and selected source timing. Its translation review and derived subtitle revision are stronger media constraints than paragraph translation. A legacy `approved` flag may be automatic when review is disabled; interoperability must require actual decision evidence for human-accepted claims. Selected-timing and historical cue protocols cannot be collapsed by comparing only strings.

Integra pins `translategemma:4b-it-q4_K_M`, model digest, weight digest, Ollama runtime and template. It translates cues individually and verifies response completion/model identity, then owns IDs/times and serialization. This is already another inference wrapper; adding a new universal service now would increase duplication. Its per-cue text is not evidence of BookText-style cross-paragraph context/glossary quality. `user_media.py` also validates source/runtime substitution and retains source results after translation failure.

## PROPOSAL — adapters first, one future reusable unit boundary

Keep the three functioning TranslateGemma product adapters in place initially. Define a common request/result envelope and conformance fixtures; reuse complete compatible artifacts before any model call. Add a SeminarText translation handoff to that boundary after explicit transition scope, without routing new work into Qwen or requiring a fake CDM document.

Share these capabilities first: full model identity resolution, language-pair declaration, resource admission, normalized request identity, bounded request/cancellation policy, checkpoint receipts, immutable unit output, provenance, explicit quality findings, glossary content identity, and review references. Preserve product-specific segmentation, context, prompt, output constraints, UI and validators.

Only after two adapters prove equivalent behavior under a common profile should a small provider/unit-execution library or local CLI worker be extracted from existing code. Choose the implementation by measured parity and maintenance cost. BookText's Python engine is a strong source of checkpoint/context/glossary logic, but its CDM API is not a generic transcript translator. Swift VideoText must not import Python document internals to invoke translation. A separate executable/library protocol can bridge languages if accepted; no mandatory server or Integra dependency is required.

### Proposed TranslationUnit

Each unit has native parent artifact/type/revision/hash, stable local unit ID, exact owned source text, language pair, source locators, ordered context references/hash, glossary content/version, output profile/version and constraints. Context is available for interpretation but not owned translated output. Unit order and selection are explicit. A result binds the complete effective model/prompt/options/validator identity, attempts, output text/hash, coverage, findings and review status. The compatibility identity is the exact ordered tuple of source revision and owned units, context, glossary, model/runtime, prompt/template, language pair, profile/version and effective options/QA policy; equality on model digest or target string alone is insufficient.

A TranslationRevision assembles ordered units and their source bindings. Preserve original wording, prior translations and reviewer edits. Correcting a unit makes a new revision; do not overwrite accepted output or silently regenerate its neighbors. If context changes, invalidate only the units whose declared context changed. Fine-grained reuse must never omit a context dependency merely to improve hit rate.

## PROPOSAL — four profiles applied to seven use cases

| Use case | Source units | Constraints / review | Reusable without inference |
| --- | --- | --- | --- |
| 1. Book/document | Real CDM heading/paragraph/list/caption blocks | Structure, terminology, numbers, title/heading context, page/block/asset traceability; table-cell coverage explicitly limited or separately implemented | Exact compatible block translations and export projections |
| 2. Plain transcript | Transcript revision text spans / speakers | Discourse continuity, fillers policy declared, original-source anchors; no fabricated pages or timing | Existing compatible prose translation; format-only output |
| 3. Combined multi-file transcript | Ordered composition of individual revisions | Cross-source transitions, per-passage attribution, context-aware terminology; explicit editorial changes | Individual translations only if context/profile remain valid; otherwise affected composed units |
| 4. Subtitle/cue-safe | Stable source cue/selection IDs | Owned coverage, unchanged clock unless an explicit reflow revision, line/readability/reading-speed limits; no target word-time invention | Existing cue-safe translations with identical timing/layout requirements |
| 5. Synthetic narration | Reviewed semantic text | Spoken style, names/numbers, pronunciation, pauses, voice/language suitability | Semantic translation as input; speech adaptation is another revision |
| 6. Multilingual video | Transcript + subtitle + media recipe | Separate subtitle and speech branches; speaker segmentation, duration fit, sync and mixing | Common semantic units, compatible subtitles/audio segments; render separately |
| 7. Knowledge/Learning | Exact evidence quotes and reviewed Knowledge references | Original-language evidence retained; translated quote/lesson is a derivative; semantic/pedagogical acceptance remains explicit | Accepted compatible translation plus source links, not acceptance transferred between domains |

Document, transcript, subtitle and speech-adapted outputs therefore need different constraints. A subtitle can be too compressed for a book, a literary paragraph too long for a cue, and a valid cue unsuitable for speech. One target string may satisfy several profiles, but that must be validated and recorded, not assumed. A speech-adapted result is a new profile revision, not a semantic-acceptance transfer from a document or subtitle result.

## PROPOSAL — cache and review rules

Compatible reuse requires the exact compatibility identity—source/owned-unit/context/glossary/model/runtime/prompt/profile/options/QA identities—plus supported validators. Hash source and glossary content independently from file locations. Keep the producer's existing native cache until sidecar parity is proved; do not weaken it in place. Reading-order changes affect composition/context, not original ASR. Target language or speech-purpose changes do not trigger transcription.

On a cache hit, run required structural/profile validation, preserve warnings and the attributable human review record, and record zero provider calls. Reusing a target text under a new subtitle or speech profile requires new profile QA; prior semantic review can remain linked but does not certify timing or pronunciation. Reopening an unchanged accepted revision does not ask for the same review again. Technical pass, artifact exportability, release acceptance and semantic acceptance are four distinct claims.

## PROPOSAL — retries, cancellation and resource ownership

One layer owns each retry budget. Product adapters pass declared finite request and quality-repair budgets; the orchestrator must not multiply a three-attempt provider retry by an unbounded stage retry. Persist attempt cause, selected output, truncation/timeout status and checkpoint completeness. Do not retry unknown irreversible publication outcomes. Cancellation stops only owned requests/processes and leaves complete translation units reusable.

BookText has a per-user BookText-specific translation lock and bounded keep-alive, but this does not serialize VideoText or Integra. VideoText's family-based unload behavior can affect other apps. Extend the existing Integra resource reservation precedent only as an opt-in lightweight per-user contract before enabling concurrent cross-app jobs. It must work while Integra is closed and has no daemon/server requirement. Never unload another application's resident model based on name alone; use attributable reservation/process ownership. Read-only capability discovery must not load a model.

## PROPOSAL — acceptance and migration

Retain #131 BookText semantic acceptance and VideoText EN↔RU subtitle acceptance as regression baselines. Test paragraph context/glossary/numbers, a plain transcript, an ordered combined transcript, cue ownership/reflow, and a speech-adaptation fixture separately. Prove byte-preserving old-project reopen, zero inference on compatible hits, precise invalidation, resumable partial units, concurrent request exclusion, and preserved reviewer edits. Real-language review must use approved samples and report actual coverage; unit tests cannot supply it.

Start as an opt-in versioned-sidecar exchange adapter with explicit read-only handoff/import. Rollback uses the native product path and previous immutable revision; no destructive migration or deletion of Qwen-era historical exports. Replacing the legacy SeminarText command or changing an accepted provider/contract requires bounded owner-approved scope. The roadmap does not authorize either change now.

## INFERENCE and UNVERIFIED

The best near-term savings come from artifact reuse, unified identity and resource ownership, not a newly written translator. A shared core may later reduce request/checkpoint duplication, but semantic/profile parity is UNVERIFIED. General multilingual translation beyond the evidenced EN↔RU routes, complete book-table translation, universal translation review exchange, and production dubbing are not established by this audit.
