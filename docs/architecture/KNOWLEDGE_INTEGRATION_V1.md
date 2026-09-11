# Knowledge Integration v1

Status: `R9A_ACCEPTED`

Issue: `#13`

## Boundary

Integra exposes SeminarText Canonical Evidence and Canonical Knowledge as a
content-addressed, read-only view. SeminarText remains the authoritative owner;
the view cannot rewrite source records or create semantic decisions.

Applicable source Product Rules read at pinned commit `a94936c`: PR-001 through
PR-007 and PR-012. The integration carries exact vendored copies of the pinned
Canonical Evidence and Canonical Knowledge contracts and validators, verifies
their upstream hashes before use, and pins the exact SeminarText commit and tree
without accepting caller-provided component identity. It preserves the
human-review lifecycle, separates `PROVISIONAL` from `ACCEPTED`, and allows a
reviewed lifecycle only for an explicitly allowlisted source artifact hash from
that pinned repository state.

## Views

- Canonical Topics, Concepts, Relations and ReviewDecisions retain their source
  records and statuses.
- Terms are a mechanical projection of each Concept preferred label and aliases;
  no alias identity is inferred or merged. A source alias is marked
  `LITERAL_SOURCE_EVIDENCE` only when it occurs in its exact source quote;
  otherwise its traceability is truthfully limited to the Concept's semantic
  evidence.
- Practice knowledge remains represented by its source Concept records in v1;
  Integra does not invent a separate Practice identity or classify Concepts.
- The graph links every substantive Topic, Concept and Relation to at least one
  exact source-Evidence quote and canonical Word/time range. Each Evidence view
  exposes the bound TranscriptRevision assurance, including machine/human
  verification provenance.
- Knowledge Diff covers Seminar, Topic, Concept, Relation, ReviewDecision, Term,
  and Evidence records and reports only added, removed and byte-changed stable
  records; it performs no semantic interpretation.

## Safety and limitations

Canonical Evidence, the source Evidence artifact and Canonical Knowledge are
mandatory inputs to every build, validation, serialization, navigation and diff
operation. The pinned source validators enforce cross-record Word, transcript,
assurance, source, range, hash, lifecycle and ReviewDecision invariants. Any
source hash, lifecycle, evidence reference, component or contract drift fails
closed. User-interface rendering and cross-media navigation remain R9C scope.
V1 does not author knowledge, classify Practices, decide aliases, or
accept/reject semantic content.
