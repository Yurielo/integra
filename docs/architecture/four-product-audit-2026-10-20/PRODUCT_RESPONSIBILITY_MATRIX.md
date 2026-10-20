# Product responsibility matrix

Status: **accepted adapter-first planning direction preserving accepted ownership; implementation remains a PROPOSAL**, with FACT columns describing current evidence. See [audit](FOUR_PRODUCT_ARCHITECTURE_AUDIT.md) and [artifact contract](SHARED_ARTIFACT_CONTRACT_PROPOSAL.md).

The accepted direction adds no shared core, global artifact store, schema replacement, forced migration, engine/model change or product-code authority. Initial interchange is versioned sidecar manifests with explicit read-only handoff/import; any discovery index or resource client is opt-in and future-scoped.

## FACT — the preliminary split needs qualification

SeminarText is not only a transcription UI: it owns accepted Canonical Evidence, Word Timeline and Canonical Knowledge admission contracts. Integra provides Knowledge orchestration, UI, cross-source navigation and publication while consuming that authority. Moving the authoritative store/admission engine to Integra would require an explicit contract change. This proposal **retains the current owner**.

VideoText's current Simple transcription already wraps a pinned SeminarText ASR core. Integra's normal Process route also invokes pinned SeminarText ASR/Topics, and currently owns a TranslateGemma wrapper. BookText contributes bounded OCR to Integra but its full CDM/review/translation package is not integrated. A responsibility label cannot override those execution facts.

## PROPOSAL — product and artifact ownership

| Capability/entity | Primary product experience | Authoritative producer/writer | Other products' role / boundary |
| --- | --- | --- | --- |
| User original files | Product that opens them | User/source system | Read or approved copy-on-write; never overwrite original |
| Cross-source registry and job orchestration | Integra | Integra for its registry/jobs; native products for theirs | Map IDs and revisions; optional rebuildable discovery metadata, never a physical store or shared mutable project directory |
| ASR/transcript workflows A/B/C | SeminarText; VideoText Simple media entry; Integra Process | Current selected SeminarText core plus product adapters | Reuse exact recognized result; do not create another recognizer or falsely label wrapper independent |
| Transcript editing/revisions | SeminarText and consuming review UI | Declared revision writer; inherited origin retained | Human edit creates successor and scoped assurance |
| Combined clear transcript | SeminarText | Composition owner over immutable per-source revisions | Integra references composition; VideoText retains source clocks |
| Raw selected timing / CWT | SeminarText contracts | Source producer/alignment owner as declared | VideoText playable timing and Integra alignment are typed derivatives, not replacement raw truth |
| Native document extraction/OCR | BookText for full document workflow; existing Integra lightweight extraction | BookText document artifacts or declared Integra native extraction | Preserve format routing; avoid replacing working DOCX/PPTX extraction with unsupported BookText ingestion |
| Document structure/CDM/visual assets | BookText | BookText | Read-only rich adapter into evidence/navigation; preserve region/review/asset fidelity |
| Document translation | BookText | BookText TranslationRevision | Shared installed model/contracts; no fake CDM for transcripts |
| Transcript translation | SeminarText outcome UI / Integra Process / VideoText media UI | Selected existing TranslateGemma adapter, recorded per artifact | Shared unit protocol and reuse; do not infer one adapter is universally selected |
| Subtitle translation/reflow | VideoText | VideoText subtitle/translation revisions | Consume transcript/translation evidence; strict cue and timing constraints |
| Speech adaptation/TTS/dubbing | VideoText, future | Separate speech/audio/media derivative writers | Integra may orchestrate after acceptance; BookText narration input via typed text units |
| ReviewDecision | Native product's review surface | Native origin or Integra review service for its new decisions | Reference imported decisions; no rewriting or automatic authority promotion |
| Canonical Evidence/Knowledge | SeminarText authority; Integra user-facing Knowledge | SeminarText accepted admission/validation contract | Integra prepares proposals, gathers decisions, invokes admission and projects result |
| Concepts/aliases/relations | Governed Knowledge workflow | Accepted semantic authority via explicit ReviewDecision | No automatic identity merge based on translation, embedding or label equality |
| Learning/Curriculum | Integra, later | Derived educational artifacts | Consume accepted Knowledge; do not create a competing truth store |
| Marketing | Integra, later | Derived marketing artifacts | Same Knowledge foundation; no dependency on completion of a book |
| Media recipes/rendered derivatives | VideoText; Integra Media UI | VideoText processing; Integra-owned recipe/receipt where selected | Cannot write canonical wording or Knowledge |
| Local exports | Respective standalone products | Native export artifact owner | Exchange references/manifests; retain product-specific formats |
| Managed publication / external adapters | Integra | Integra publication service/receipt | Generation and live publication remain separate; native export still standalone |
| Host resource admission | Opt-in lightweight cooperative contract, based on Integra existing implementation | One reservation authority per configured host store | Participating apps honor it without requiring Integra UI, daemon or server; no name-based model killing |

## FACT — overlaps that should remain vs duplication to reduce

Some overlap is useful: each standalone app must open its own inputs, validate its native artifacts, show review and export results. A shared transport conformance pack does not replace acoustic QA, OCR visual QA, translation meaning review or media readability checks. Integra's job orchestration is not a duplicate of BookText's fixed document pipeline.

Duplicated provider request, cache identity, provenance and model-lifecycle mechanisms are stronger consolidation candidates. Existing SeminarText and VideoText subtitle/export helpers should remain compatible during migration. Common ASR packaging/pin/version metadata can improve before any runtime extraction; simply copying the latest source file into every app is not versioned reuse.

## PROPOSAL — contract owners and future extraction

Integra hosts the **single proposed coordination plan** and interoperability specification review. That makes it a planning home, not the owner of all product data. Native schema changes remain reviewed in their owning repositories. One versioned contract release should identify all compatible producer/consumer commits and conformance fixtures; downstream adoption is explicit and reversible.

Candidate future extractions, in order of evidence: identity/provenance manifest utilities and validators; cooperative resource leases; translation request/checkpoint primitives; shared ASR packaging with preserved CLI/artifact contract. Defer shared semantic engines, generic document/transcript object hierarchies and a platform-wide database. Extraction requires at least two concrete consumers, preserved acceptance fixtures and a measured reduction in duplicated maintenance.

## PROPOSAL — standalone invariant and UX

Each product can perform its basic accepted workflow without Integra installed/running. Initial exchange uses exported versioned sidecars and explicit read-only handoff/import; a later optional local discovery index is not physical storage, mandatory discovery or a prerequisite for that route. A handoff opens an exact result/revision in the destination app, validates capability support and preserves source links. Apps show “existing result reused” or the specific unavailable capability; they do not silently repeat inference to conceal a failed import. Cross-project automatic discovery, copy, reuse and retention remain separately scoped choices.

## INFERENCE / UNVERIFIED / owner boundary

This division minimizes authority conflict and keeps current strengths. Universal standalone interoperability and common resource participation are UNVERIFIED until acceptance tests pass. Changing Canonical Knowledge authority, retiring source apps or replacing selected engines would be materially different options; none is recommended or authorized by this proposal. Genuine decisions are consolidated in [Product Owner decisions](PRODUCT_OWNER_DECISIONS.md).
