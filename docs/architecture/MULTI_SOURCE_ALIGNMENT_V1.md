# Multi-source Alignment v1

Status: `R8C_ACCEPTED`

Issue: `#12`

## Purpose

R8C provides one deterministic graph for navigating among a project's media,
transcript, slides, pages, supporting documents, Topics and Evidence. It does
not copy source content or replace the per-source contracts accepted in R8B,
Projects & Sources v1, or Transcript & Topic Studio v1.

## Authority and binding

An alignment is bound to one exact Projects & Sources registry record, project
record and at least two distinct current source revisions. Every node carries
its immutable artifact identity and hash, owning component, lineage and both:

- a source-type-native locator (`TIME_INTERVAL`, `WORD_INTERVAL`,
  `PAGE_RANGE`, `SLIDE_RANGE`, `REGION` or `CHARACTER_RANGE`); and
- the exact `ARTIFACT_REVISION` locator for the bound current source revision.

The embedded artifact catalog is not self-attested. Each ArtifactReference is
validated against an authoritative external `DOCUMENT_EXTRACTION_V1` or
`TRANSCRIPT_TOPIC_STUDIO_V1` record, including its entity identity, content
hash, lineage, source revision, accepted component origin and model binding.
The serialized graph retains only immutable upstream record IDs and hashes;
full upstream records remain mandatory validation inputs and are never copied
into the alignment payload.

Node kind must agree with the Projects & Sources source type. Page and slide
nodes require exactly one native range, region locators must stay inside any
declared range, and video/audio-to-transcript links must use the exact same
source revision.

A later registry or current-revision change makes the existing alignment stale
and validation fails closed. Alignment never mutates the registry, source
artifact or source repository.

## Graph contract

Node kinds are `VIDEO`, `AUDIO`, `TRANSCRIPT`, `SLIDE`, `PAGE`,
`SUPPORTING_DOCUMENT`, `TOPIC` and `EVIDENCE`. V1 supports these typed links:

| Relation | From | To | Cross-source rule |
| --- | --- | --- | --- |
| `VIDEO_TO_TRANSCRIPT` | video/audio | transcript | may bind artifacts of the same source revision |
| `VIDEO_TO_SLIDE` | video/audio | slide | distinct sources required |
| `TOPIC_TO_PAGE` | Topic | page | distinct sources required |
| `TOPIC_TO_SLIDE` | Topic | slide | distinct sources required |
| `EVIDENCE_TO_DOCUMENT` | Evidence | document/page/slide | distinct sources required |

Links bind the complete hashes of their endpoints and every supporting evidence
node. Duplicate native identities, stale hashes, invalid endpoint types and
non-canonical locator/evidence order fail validation.

## Deterministic reversible navigation

`navigate` emits sorted forward and reverse hops. Each hop includes relation,
semantic status, destination/source node identity, artifact hash, source
revision and the complete exact locator set. The graph can therefore resolve
video-to-slide, Topic-to-page/slide and Evidence-to-document paths without
discarding the inverse route or reconstructing mutable display positions.

Canonical JSON serialization is byte-deterministic. Record, node and link
hashes make mutation visible even if a container record is resealed.

## Semantic boundary

R8C creates alignment proposals, not accepted meaning. Confidence below `0.8`
or an explicit conflict yields `REVIEW_REQUIRED`; other machine links remain
`PROVISIONAL`. Neither state is semantic acceptance. A later supported human
review contract may decide a proposal, but R8C performs no automatic semantic
promotion.

## Limitations

- V1 stores deterministic supplied alignment proposals; it does not choose or
  tune a matching model.
- Registry revision changes require an explicit rebuilt alignment rather than
  silently rebasing prior links.
- Validation requires the exact external upstream records whose IDs and hashes
  are bound into the catalog; the alignment is not a standalone evidence store.
- UI presentation and cross-studio interaction belong to R9C.
