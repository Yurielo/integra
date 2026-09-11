# Cross-navigation v1

Issue #15 / R9C provides one presentation-only navigation index across the
accepted R8C alignment graph, R9A Knowledge projection, and registered R9B
media derivatives. It adds no semantic or source authority.

## Contract

`build_cross_navigation` validates the complete upstream records before it
indexes them:

- R8C alignment against the current Project Registry and its external Studio
  and document records;
- R9A Knowledge view against the exact Canonical Evidence, source Evidence,
  and Canonical Knowledge payloads;
- every R9B derivative against its recipe, operation plan, durable successful
  job and checkpoint, released model records, exact QA reference, and QA
  report.

The resulting target keeps the upstream stable ID, content hash, owner,
semantic status, artifact/source identity, and an ordered copy of the exact
locators. The index never serializes the supplied upstream payloads. Its source
section contains only immutable record identities, hashes, and derived
source/revision mappings. A Knowledge-to-project mapping requires the Canonical
Evidence native source identity plus a content-hash match to the aligned media;
a media-to-alignment mapping requires the registered recipe source to name the
aligned artifact as provenance parent. Locator overlap alone is insufficient.
Every source/revision pair indexed from R9A Evidence and every registered R9B
media source/revision must resolve to exactly one current R8C source binding in
the same Project Registry project. Missing, partial, duplicate, stale, or
cross-project coverage rejects the complete index before any target is exposed.

Every load and navigation call also receives the current authoritative R8C,
R9A, and R9B inputs, the approved bridge set, and the current unavailable-source
catalog. The service rebuilds the index and requires canonical byte equality,
so re-signing a locally altered semantic status, locator, bridge, or availability
claim does not turn that alteration into source truth. Bridge authorization
matches both endpoint source IDs and both endpoint revision IDs.

## Navigation surfaces

The v1 index covers Knowledge entities, Evidence, Topics, Canonical Word
Timeline artifacts, transcripts, video/audio, document blocks, pages, slides,
exact media selections, and verified clips. Locator types map to explicit UI
actions such as seek media, select a word range, open a page or slide, select
text, highlight a region, and open an artifact revision. Document projections
retain page/slide, character, optional normalized region, and exact source
artifact-revision locators. A verified derivative adds `OPEN_CLIP`.

An aggregate Knowledge target backed by more than one source/revision is an
entity destination only. It has no source identity, locators, seek/open-source
actions, or inferred common position; its only action is `OPEN_ENTITY`.
Individual Evidence targets keep their exact source/revision identities and
locators, and graph edges provide the route from the aggregate to each one.

R8C relations and R9A graph edges are copied as hash-bound bidirectional
routes. Studio Topic-to-Word-Timeline and source-to-derivative routes are added
mechanically. Cross-component bridges are accepted only for supported endpoint
kinds with exact or overlapping time/word locators already present on both
validated targets. A bridge preserves both original locators; it never replaces
one with the other.

`navigate` returns the exact origin plus deterministic forward and reverse
hops. A reverse hop returns the same target ID and locators that were present
before the forward hop.

## Fail-closed availability

Unknown target IDs raise `CrossNavigationError`. A known unavailable source is
represented without locators, actions, or routes and raises
`NavigationUnavailableError` with its recorded reason. The UI must show that
reason and must not guess another source, revision, timestamp, page, slide, or
clip.

Cross-navigation construction also raises `CrossNavigationError` when even one
indexed Knowledge or registered media source lacks exact current alignment
coverage. It never publishes a partially navigable index.

## Authority and limits

The index is `PRESENTATION_ONLY_SOURCE_TRUTH_PRESERVED`. It does not change
source artifacts, resolve alignment uncertainty, promote machine semantics,
render media, or authorize publication. R9C supplies a dependency-free domain
service and closed JSON contract for the future shell; native macOS view
composition remains part of the combined product stages.
