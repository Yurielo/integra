# Exact Excel #7 successor

This implements the reviewed minimum repair for the already-accepted native
YouTube playlist Candidate. It does not change Candidate product bytes.

The transaction binds outgoing CURRENT and its exact file hash, both Candidate
tuples including manifest, accepted Proposal hash, source/base/evidence anchors,
the exact three Product Owner instruction payloads, historical receipts and the
exact intended successor. Authority copies preserve the original text with one
final LF; both original and serialized SHA-256 values are recorded.

The event and protection registry have no future-commit self-reference. Its
transaction ID derives from immutable inputs. The event lists exact result
file hashes; the registry points at the event by path and transaction ID.
Publication on canonical main consumes authority for that exact result.

The coherent Git tree preserves the outgoing CURRENT and registry snapshots,
all old accepted records and historical receipts, the exact accepted Proposal,
all unrelated open/accepted-unpromoted protections, and truthful missing-byte
semantics. The active Proposal is retired. Excel #7 changes to DONE in both
the Board mapping and definition of done. Counts become
41 DONE / 3 NOT_DONE / 1 BLOCKED.

The missing-outgoing exception applies only to this `d8bd… → 5f6384…` pair.
The new CURRENT must have a COMPLETE archive. Normal later promotion still
requires the outgoing archive and cannot reuse this transaction.

Preflight reads current GitHub main, final PR head/base, all open Proposal
heads, exact authority records and the real archive. Managed retention uses
the same catalog lock as promotion. Archive bytes are rehashed immediately
before merge and after canonical application. External deletion remains a
detectable incident, not something a local lock prevents.

No deploy, installed-runtime change, source-product modification, synthetic
archive, new semantic acceptance or deletion is part of this transaction.

Verification before publication: full local suite 987 run / 895 passed /
92 environment-dependent skips / zero failures or errors; focused successor
matrix 35 passed. The existing 42 protection/audit/promotion checks also pass.
Governance reports CURRENT_VALID. Independent QA and diff review were completed;
live exact-Candidate archive preflight and the production promotion gate passed.
Final PR CI and canonical post-merge audit remain required execution checks.
