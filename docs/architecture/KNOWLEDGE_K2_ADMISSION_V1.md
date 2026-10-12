# Knowledge K2 source owned admission

K2 extends the reviewed K1 notebook with explicit semantic proposals and review.
SeminarText compiles, validates and immutably persists Canonical Knowledge;
Integra prepares requests and exposes only the returned read-only projection.
The original BenchmarkSegment admission remains unchanged.

## Exact source contract

The separate capability pin in `state/knowledge_admission_component_v1.json`
binds SeminarText PR #139, commit
`a39de3143e78e25be8ecce242a5fe812c9af137c`, tree
`0abf57be59522955d997b38848b118001dc7151c`, the versioned admission schema and
all twelve owner dependencies. The existing Process runtime pin is unchanged.
The packaged owner runtime is isolated from the older Process adapter; the
supported review interpreter executes canonical compilation and validation.
Missing or changed pins, dependencies, source or producer bytes fail closed.

## Owner interaction by exception and immutable revisions

Selection preserves exact source fragment boundaries and word or cue precision.
Concept and Topic proposals retain stable IDs independent of their labels.
For the ordinary Stage-1 path, exact machine-derived K1 units are compiled
only as enumerated `DEFER` records by `system_validator`: they remain
provisional, are not human-reviewed, and create no accepted canonical record.
This allows independent processing to finish without treating silence as an
acceptance, rejection, or semantic confirmation.

Human interaction is reserved for a real semantic exception: an explicit
semantic edit or rejection, an identity collision, a replacement/update, or a
controlled Relation with explicit endpoints, type, and Evidence.  The normal
interface presents only a plain-language question and can safely offer
"Решить позже"; a deferred exception does not block unrelated source work.
Human review still requires an explicit enumerated package confirmation.  A
reviewer identity, proposal digest and timestamp are automatic audit metadata,
not ordinary user input or semantic decisions.  Neither K1 review nor
transcript assurance supplies semantic authority. Equal labels never merge
Concept identities automatically.

The owner receipt binds original Evidence and either the exact human-reviewed
or exact machine-derived fragment payload, source/revision/fragment identities,
proposal package, producer and decision execution mode.
Accepted changes produce a new immutable revision with its exact parent.
Rejected and deferred proposals remain visible in the decision receipt without
becoming accepted canonical records. Integra revalidates the complete owner
receipt and current K1/source bindings for reopen, navigation and export.
Reads never regenerate proposals or rerun processing.

## Projection and export

Existing Knowledge views supply Topics, Concepts, Terms, controlled Relations,
Evidence, graph edges and mechanical record diffs. Exact source navigation
uses preserved word/cue ranges and media timestamps. Export reuses the source
managed-view generator and existing collision-safe Obsidian publisher. User
notes remain protected; preview does not publish automatically.

## Verification and boundary

`tests/test_knowledge_k2.py`, `tests/test_knowledge_k2_bridge.py` and
`tests/test_knowledge_admission_runtime.py` cover owner admission, explicit
review, stable identity, parent revisions, reopen, navigation, graph/diff,
managed export and negative integrity checks. Native acceptance runs against
the archived packaged Candidate in an isolated copy of the existing generated
speech demonstration. QA decisions are synthetic test-only records, never
Product Owner semantic acceptance or modifications to user projects.

K2 does not authorize imports, multi-source reconciliation, Concept identity
merges, new entity or Relation types, upstream processing, model changes,
CURRENT promotion or K3. Process remains `41 DONE / 3 NOT_DONE / 1 BLOCKED`.
