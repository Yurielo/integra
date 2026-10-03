# Integra Transcript & Topic Studio v1

Status: `ACCEPTED`

Issue: `#48`

## Purpose

The studio exposes one source-scoped, reproducible view of media preparation,
ASR, translation, Canonical Word Timeline, quality findings, Topic levels,
hierarchy and exception-only review. It composes the accepted R5 owners over
the exact current source revision from Projects & Sources v1. It does not copy
authority from SeminarText or VideoText into Integra.

## Capability ownership

- VideoText owns media preparation and ASR outputs. Integra owns the bounded
  TranslateGemma translation runtime and derivative output provenance.
- SeminarText owns Canonical Word Timeline and Topic proposals.
- SeminarText and VideoText jointly supply review-mechanics and quality signals.
- Integra owns only the studio index, clustered package and an explicitly
  authorized `ReviewDecision` record. Operations v1 exclusively owns jobs and
  checkpoints.

Every binding includes the accepted R5 selection-record SHA-256, an exact
component commit and runtime contract. Source-owned capabilities require their
pinned R1 commit; the Integra translation component records the exact Integra
build commit at execution time and its local TranslateGemma runtime identity.
Pinned model identity is retained when one exists (including the VideoText ASR
model and the R6 SeminarText `gemma3:4b` manifest/weights identity),
and configuration SHA-256. Unknown commits, contracts and models fail closed.
Artifacts bind the hash of that complete capability record. Operations v1
binds job admission and resume; Studio never duplicates that lifecycle.

## Source and lineage contract

A studio is bound to one Project, Source and current SourceRevision, plus the
content hashes of their exact authoritative Projects & Sources registry
records. Authoritative reload validates those bindings against the supplied
registry snapshot; a self-resealed source tuple cannot replace that check. Every
artifact retains immutable parent IDs, content hash, component binding and
source locator. Supported locator types are time interval, Canonical Word
interval, page range, slide range, normalized page/slide/image region,
character range and artifact revision. Topic proposals require an exact
artifact-revision locator plus a locator meaningful for their source type.
Every Topic also resolves one exact Word interval and every evidence reference
to actual word IDs inside that interval; media time intervals must contain the
resolved word timing.

Original transcript wording and derived translation are separate immutable
artifacts. A translation points to its original transcript and records both
languages. No normalization rewrites the original machine wording.

The studio owns per-source binding only. Cross-source alignment is explicitly
`OUT_OF_SCOPE_R8C`; a Topic cannot acquire provenance from another source by
being placed in this registry.

## Topic levels and hierarchy

Exactly one optional Topic set may be registered at each of `DETAILED`,
`NORMAL`, and `COARSE`. Set members are ordered, non-overlapping where time is
available, and preserve evidence references. Hierarchy edges are acyclic by
strict level ordering: a parent must be coarser and its locator must contain
the child. This provides navigable structure without treating machine titles,
summaries or groupings as accepted semantics.

Low-confidence or conflicting proposals are always `REVIEW_REQUIRED`; all
other machine semantic output remains `PROVISIONAL`. The contract has no path
that promotes machine output to `ACCEPTED`.

## Exception-only review

Review packages explicitly enumerate every low-confidence/conflicting Topic or
quality finding and include neighboring Topic IDs as context. The package scope
content-hashes the complete current member and neighbor records, not only their
stable IDs. An application operation succeeds only when:

1. authority is exactly `HUMAN_DOMAIN_REVIEW`;
2. the package is still unresolved and its scope hash matches;
3. one unexpired Project Lease, read back byte-for-byte from the authoritative
   `LeaseStore`, covers that exact package and names the review service writer;
4. every enumerated member has exactly one supported resolution.

The resulting decision is a separate audit record. Artifacts, Word Timeline,
Topic Drafts and source files are byte-for-byte untouched. One stale, partial,
machine-authored or out-of-scope decision fails closed.

## Cancellation and resume

The studio deliberately has no job store or lifecycle-transition API.
Cancellation, resume, checkpoints, capability admission and terminal-output
validation use the sole durable Operations & Diagnostics v1 `JobStore`. Studio
artifacts retain the resulting component/model/config hashes and immutable
lineage; they never create a parallel source of job truth.

## Safety boundary

The acceptance fixture is local and synthetic. It does not access protected
datasets, Gold, private media, accounts, credentials or a network. It performs
no semantic acceptance and no cross-source alignment. SeminarText and
VideoText repositories and source-owned artifacts remain unchanged.
