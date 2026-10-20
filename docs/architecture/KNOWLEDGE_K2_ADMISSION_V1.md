# Knowledge K2 source-owned admission

Status: `PROPOSED — ISSUE_279`

K2 extends the reviewed K1 notebook with explicit semantic proposals and review.
SeminarText compiles, validates and immutably persists Canonical Knowledge;
Integra prepares requests and exposes only the returned read-only projection.
The original BenchmarkSegment admission remains unchanged.

## Exact source contract

The separate capability pin in `state/knowledge_admission_component_v1.json`
binds SeminarText PR #136, commit
`61ee27de67174377afa0f4955b3cb5abeecb4f03`, tree
`066a4029d791585410afd0aa45de974638b5e1ff`, the versioned admission schema and
all twelve owner dependencies. The existing Process runtime pin is unchanged.
The packaged owner runtime is isolated from the older Process adapter; the
supported review interpreter executes canonical compilation and validation.
Missing or changed pins, dependencies, source or producer bytes fail closed.

## Review and immutable revisions

Selection preserves exact reviewed fragment boundaries and word or cue
precision. Concept and Topic proposals retain stable IDs independent of their
labels. Controlled Relations require explicit endpoints, type and Evidence.
Proposals start `PROVISIONAL / REVIEW_REQUIRED`; no review choice is preselected.
Each proposal requires an explicit ACCEPT, EDIT, REJECT or DEFER decision,
reviewer identity, reason and confirmation of the complete enumerated package
hash. Neither K1 review nor transcript assurance supplies semantic authority.
Equal labels do not merge Concept identities.

The owner receipt binds original Evidence and reviewed-fragment payloads,
source/revision/fragment identities, proposal package, producer and review.
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
managed export and negative integrity checks. Pre-owner native GUI QA runs
against a fresh packaged Candidate in an isolated, Integra-owned fixture. QA
decisions are synthetic test-only records: they prove mechanics and never
constitute Product Owner semantic acceptance or modify user projects.

Every canonical revision requires a human review action for each proposal and
an explicit confirmation of the complete proposal package. K2 has no automatic
admission, default decision, inferred Concept merge, or automatic Relation.

K2 does not authorize imports, multi-source reconciliation, Concept identity
merges, new entity or Relation types, upstream processing, model changes,
CURRENT promotion, Stage 2, or M1–M7. The withdrawn Issue #227 Candidate and
its Proposal remain historical evidence only and cannot be reused for Issue
#279.
