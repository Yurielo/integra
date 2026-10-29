# Candidate lifecycle retention policy

Issue #228 implements the Product Owner's bounded standing decision of
2026-10-09. Its exact instruction is bound by the payload digest in
`state/candidate_lifecycle_retention_policy_v1.json`. Canonical main, not a
feature branch or a local pending label, supplies execution authority.

Issue #306 adds the later direct Product Owner capacity-rotation decision in
`state/candidate_archive_rotation_policy_v2.json`. It supersedes the v1
terminal-only eligibility predicate **only when a new archived Candidate needs
the eighth occupied slot**. The v1 rule remains the historical and explicit
terminal-retirement contract. No branch-local v2 file may authorize deletion;
the exact v2 bytes must first be canonical on main. A physical rotation does
not change an open Proposal or Candidate's semantic/lifecycle decision. Its
durable receipt records the loss of bytes separately from that decision.
For capacity rotation, the direct Owner decision is the separately applicable
decision for the four legacy hold prefixes named below; their v1 hold history
remains intact.

## Eligibility

A governed, owned physical archive may be retired without a Candidate-specific
cleanup decision only after exact canonical terminal lineage, complete immutable
history, fresh integrity and fresh protection validation are proven. It must
have no active CURRENT, immediate rollback, recovery, Proposal, pending baseline
acceptance, accepted-unpromoted, pending promotion, unresolved successor,
historical-gap or other protection obligation. No required physical
representation, unresolved integrity incident, unknown ownership or active
writer may be lost. Any uncertainty preserves the archive.

This does not decide acceptance, rejection, withdrawal, rollback or recovery.
Historical acceptance remains immutable. The real prefixes `721d`, `073396`,
`97be` and `14b3` remain absolute holds until a separately applicable decision.

## Transition and evidence

Promotion derives the complete prospective protection domain, preserves exact
survivors for every remaining obligation, and consumes only its exact Proposal.
Old CURRENT becomes immediate rollback; an older promoted Candidate becomes
historical only when its remaining obligations allow that classification.
Canonical promotion history overrides stale local pending labels through exact
Candidate, bundle and manifest lineage, never by age or similar content.

The existing catalog lock covers final verification, promotion, post-validation
and catalog reconciliation. Retirement uses durable PREPARED, PARTIAL and
RETIRED_NOT_AVAILABLE evidence outside the deleted payload. Missing or partial
bytes never become reported as available; a prepared receipt is not deletion.

## Capacity and execution

Build and standalone archive publication run governed maintenance before final
capacity rejection. Limits remain exactly 8 full copies, 21474836480 allocated
bytes and 16106127360 bytes free after reservations. Unknown physical copies
still count. Protected archives are not test execution locations; use fresh
owned execution material and bytecode suppression, without changing retained
payload modes or the archive identity contract.

## Delivery boundary

Phase A is governance-only development tooling under
`scripts/proposed_baseline_lite.py::_governed_product_path` and the existing
Candidate retention repair contract. It must not change packaged product paths,
build a repair Candidate, delete real archives, or mix K2 changes. Tests include
isolated real lifecycle rollover and a read-only real-state dry-run.

Phase B is separate and starts only after verified canonical Phase A. It
refreshes every authority input, reconciles deterministic bookkeeping and may
retire only fully eligible archives using the standing predicate and durable
receipts. It must prove normal capacity admission without building K2. K1 remains
DONE, K2 remains frozen, and the Process Board remains 41 DONE / 3 NOT_DONE /
1 BLOCKED. Stop after the repair and reconciliation.
