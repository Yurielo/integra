# Shared artifact contract proposal

Status: **PROPOSAL**, not an accepted replacement schema. Evidence basis: [audit](FOUR_PRODUCT_ARCHITECTURE_AUDIT.md). All FACT, INFERENCE, PROPOSAL and UNVERIFIED classifications below refer to the pinned audit snapshot.

## FACT — preserve existing contracts

Integra R2/R3 already define stable URNs, single field writers, leases, component identities, exact schema negotiation, hashed artifact references, idempotency, cancellation and staged promotion. SeminarText already owns Canonical Evidence/Knowledge and transcript/word provenance; VideoText has native project revision types; BookText has CDM and machine/artifact contracts. Their names and ID schemes are not to be replaced by the candidate vocabulary in the request. See audit I01–I05, S01, B01 and V01.

## PROPOSAL — additive exchange envelope

Use an **exchange manifest around native payloads**, initially alongside Integra's accepted `artifact_reference_v1.schema.json`. Do not add unsupported fields directly to strict v1 payloads. Define a separately versioned extension only after owner acceptance and fixtures. Every reference contains:

| Group | Required meaning |
| --- | --- |
| Exchange identity | Envelope schema/version; native product/type/schema/version and stable native ID; immutable revision ID; predecessor IDs where applicable |
| Content identity | Algorithm, digest and byte length; manifest identity separate from payload identity; complete output inventory |
| Source identity | Origin namespace/native source ID, byte revision hash, explicit aliases, availability and exact locator type |
| Producer identity | Repository/commit/tree or distribution digest, adapter digest, runtime executable/version, dependency profile, model family/tag/full digest/quantization where applicable |
| Operation identity | Capability/version, normalized effective options, prompt/template and QA policy versions, language pair, output purpose, glossary and ordered context hashes, retry profile |
| Provenance | Ordered input references and typed dependency edges; transform receipt; machine/human/imported origin; raw-to-clean-to-review lineage |
| Assurance | Structural validation, quality findings, verification coverage, attributable human decisions and exact reviewed revision; each separate |
| Storage | Product-owned immutable URI/relative locator, completeness receipt, optional verified copy locations; no path in logical identity |
| Authority | Payload owner and allowed writer; review authority/scope; permitted operations; source-owned vs derivative store |

Canonicalize manifest JSON with one specified algorithm and exclude the manifest's own digest field from its hash. Never assume independently serialized JSON has identical bytes. R3 exact-version negotiation remains the compatibility rule until an explicitly accepted extension changes it.

## PROPOSAL — mapping candidate concepts to existing entities

| Requested concept | Existing contract to adapt | Authoritative meaning / new work |
| --- | --- | --- |
| SourceIdentity / SourceManifest | Integra projects/sources and component-native IDs | Cross-product alias envelope is new; registry indexes, does not own original files |
| TranscriptRevision / TranscriptSegment | SeminarText evidence/transcript records; VideoText `TranscriptRevision`; Integra Process transcript | Producer-owned immutable wording with correction lineage; bind exact source range and assurance |
| WordTimeline | SeminarText Canonical Word Timeline; VideoText selected timing; Integra alignment output | Keep raw native token endpoints, playable intervals, aligned word intervals and cue intervals distinct; declare coordinate system and method |
| DocumentBlock | BookText CDM page/block/region and Integra document units | Preserve original block IDs, source pages, normalized regions, reading order and assets; no fabricated transcript CDM |
| CanonicalEvidence | SeminarText `canonical_evidence_v1` | Preserve native validator/authority and exact locators; document import requires approved mapping |
| TranslationUnit / TranslationRevision | BookText `translations/<source>-<target>.json` (`booktext.translation` 1.1); VideoText translation revisions; Integra translation payload/provenance | Shared logical unit request is new; purpose and context are identity inputs, native payload retained |
| SubtitleCue / SubtitleRevision | VideoText cue IDs/revisions and SRT service | Stable source ownership plus millisecond intervals; SRT is an export, not a sufficient canonical provenance record |
| SpeechSegment / SyntheticAudioArtifact | Existing VideoText speech code as bounded foundation | Future versioned speech plan/audio manifest; voice/duration/pronunciation metadata not proved complete |
| MediaRecipe / DerivedArtifact | Integra media recipe and derivative record; VideoText media processing | Bind every auxiliary input, implementation, output and QA receipt; cannot mutate source/Knowledge |
| ReviewDecision | SeminarText review contracts, BookText review layer, VideoText semantic review, Integra review service | Imported decisions immutable; local decisions reference exact scope/revision. Source enums never imply greater authority |
| KnowledgeReference | SeminarText Knowledge IDs and Integra navigation index | Read-only exact references, preserved Concept identity, source terms and review status |

## PROPOSAL — authority and lifecycle

Original files are user/source-system owned. Native producer artifacts are owned by their producing component. Integra owns its registry, jobs, orchestration records, local decisions and publication receipts. Imported decisions and canonical source payloads remain immutable. Derived translations, media and Knowledge views cannot rewrite source wording or acquire semantic authority through a copy.

Do not force existing status enums into one enum. The envelope records separate axes:

- materialization: absent / staged / complete / unavailable;
- validation: unknown / valid / invalid, with validator/version;
- quality: unassessed / findings / passed-for-declared-checks;
- human review: not requested / required / partial / reviewed, with coverage and decision references;
- applicability: current / superseded / stale-for-this-request / revoked;
- semantic authority: native provisional/review-required/accepted state, never inferred from technical success.

These are proposed envelope categories, not new permitted native enum values. Machine transcript evidence can be used with explicit assurance under SeminarText PR-012; full transcript human verification is not a mandatory prerequisite for all downstream automation. Semantic promotion still requires PR-001/002/003 decisions. A translated approved source does not inherit approval for the target language.

## PROPOSAL — dependency graph and invalidation

Edges identify why an output depends on an input: `wording`, `timing`, `ordering`, `layout`, `terminology`, `voice`, `render`, `review-scope` or `publication`. A graph cycle is invalid. Dependencies are exact revisions; “latest” is a UI selection, not a persisted reference.

| Change | Invalidate or revalidate | Preserve |
| --- | --- | --- |
| Source bytes | Extraction/ASR/OCR and all descendants for new source revision | Entire historical graph and review receipts |
| File path/name only | Locator availability | All content-bound processing |
| Corrected transcript wording | Dependent translation units/context, topics/evidence references, affected speech; alignment validation | Original ASR/raw timing, unrelated sources |
| Selected timing/range | Cue layout, source-range playback, speech synchronization and renders | Source wording and compatible un-timed translation |
| Combined source order | Composition, contextual translation if context changes | Per-source recognition and independent transcript views |
| Glossary/version or target language | Relevant translations and target-language descendants | ASR/OCR/source review |
| Voice/pronunciation/rate | Audio segments, alignment/mix/render | Valid text and subtitles unless text constraints change |
| Render style/codec | Render/export QA | Source transcript, translations, audio where unchanged |
| Human decision | Exact dependent semantic/view state; do not automatically overwrite other decisions | Immutable decision history and unaffected scopes |

Reuse key: hash of ordered input revisions + capability/version + effective transformation configuration + producer/runtime/model identity + context/glossary/purpose + applicable QA policy. A human-reviewed revision is a reusable artifact in its own right, not an instruction to overwrite the original cache. Fast hashes or size/mtime can accelerate candidate lookup, but final reuse requires the contract's content verification.

## PROPOSAL — review reuse without repeated work

A ReviewDecision records reviewer authority, time, exact revision hash, selected units/ranges, purpose, language and outcome. Reuse it only for unchanged reviewed content and the same decision scope. A renamed file need not be reviewed again. A changed glossary, target-language text, cue segmentation or speech adaptation may require a new bounded review. Reuse a source-semantic decision as evidence, not as target-translation acceptance. Map VideoText semantic review records explicitly; `reviewStatus=approved` alone is insufficient because some legacy paths auto-approve when review is disabled.

## PROPOSAL — compatibility, migration and rollback

Begin with exported sidecar manifests and read-only consumers. Readers declare exact supported native/envelope versions and capabilities; unknown mandatory fields/versions fail closed. Optional extensions must have explicit semantics and cannot relax a required hash or authority check. Do not downgrade by dropping page regions, raw timing, human edits, decision history or model provenance.

Adopt migrations as pure native-revision → new-envelope transformations with an inventory/diff, converter digest, original hashes and rollback pointer. Verify imported copies before activation. No in-place project upgrade, cross-app writer takeover, or background data consolidation. Retain original schemas and native application reopen tests. Rollback removes the new activation pointer/index entry while retaining immutable data and the prior application path.

## PROPOSAL — minimum contract conformance pack

Publish the same small synthetic fixtures to each adapter: exact reuse; changed bytes; moved source; two concurrent requests; interrupted staging; corrupted payload; unknown schema; mixed source clocks; directed raw token interval; edited transcript with stale timeline; reviewed translation with stale glossary; BookText page/region/table links; imported review with missing actor; unavailable media. Assert producer call counts, preserved IDs/hashes, valid negative behavior and no semantic promotion. Product-native validators remain authoritative; shared transport tests reduce duplicate boundary tests without replacing acoustic, linguistic or visual QA.

## INFERENCE and UNVERIFIED

An additive envelope is lower-risk than replacing four persistence models because it leaves accepted native contracts and rollback paths intact. The cross-product envelope, universal index and conformance pack are proposals; compatibility is not established until all relevant native adapters pass the same fixtures and bounded real-source handoffs.
