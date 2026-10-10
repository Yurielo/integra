# Issue 227 — K2 owner GUI audit and repair

## Scope

This evidence documents the bounded repair required after the Owner Test of
the K2 semantic-review flow. It does not accept semantic content, change
CURRENT, merge PR #239, alter the Process Board, or change a protected K1/K2
Candidate archive.

## Reproduced owner journey

The required production journey is:

```text
Knowledge notebook
→ Structured knowledge
→ Review semantic proposals
→ explicit per-proposal decision and reason
→ explicit package confirmation
→ Apply
→ saved result
→ close/reopen
```

The Owner Test established that the earlier packaged flow did not provide a
clear, complete owner path from review to apply. In particular, the form
exposed an implementation-facing reviewer-ID input even though the product is
a single-owner local application.

## Root-cause evidence

`git blame` assigns the manual `ID проверяющего` form field to initial K2
implementation commit `a26726a`. The later confirmation repair only preserved
the modal on invalid confirmation; it did not introduce the field.

The K2 contract requires a traceable human reviewer identity in the admission
receipt. It does **not** require the local owner to manually invent or enter a
technical identifier. The existing Process bridge already uses a stable local
human identity, which establishes a repository precedent for satisfying
provenance without exposing internal mechanics in the owner interface.

No automatic semantic decision is introduced by this repair: each proposal
still requires an explicit `ACCEPT`, `EDIT`, `REJECT`, or `DEFER`, a reason,
and a second explicit package confirmation before the bridge receives an
apply request.

## Repair

The normal K2 UI now derives the required human reviewer provenance from the
stable local owner identity `integra-local-owner`. The bridge still receives
the existing required reviewer field and stores its existing
`human_domain_reviewer` actor receipt. The backend validation rule is not
weakened.

The owner-facing K2 screens no longer display internal proposal, package,
source, transcript, evidence, fragment, revision, graph, word-range, or
content-hash identifiers. Those identifiers remain in the governed local
records and are still used by the exact-source navigation controls.

The relation selector now displays concept labels while retaining the exact
underlying concept IDs internally. The confirmation modal remains a distinct
second step. If a required decision, reason, edit, or confirmation is absent,
it stays open, retains entered values, and identifies the required action.

## Regression assertions

Focused coverage proves that:

- the UI contains no manual reviewer-ID input;
- `integra-local-owner` is supplied only as provenance to the unchanged
  backend contract;
- empty decisions are rejected and no semantic decision is automatic;
- the persisted revision keeps the expected human reviewer actor;
- the review and confirmation screens do not expose implementation IDs;
- confirmation behavior remains explicit and validation preserves form input.

The fresh Candidate, native packaged GUI lifecycle, archive identities,
governance, CI, and independent QA must be recorded separately after this
source repair. This evidence does not claim those future checks have passed.

## Historical limitations preserved

The historical single `knowledge-open: exit 2` remains **UNVERIFIED**. This
repair neither assigns it a cause nor claims to fix it.
