# Issue #242 — withdrawn Candidate lifecycle reconciliation

Issue #227 closed PR #239 without merge after its Owner-Test Candidate became
stale: the branch contains product changes that cannot truthfully be bound to
the prior immutable Candidate.  This is a governed Proposal supersession, not
an acceptance, rejection, promotion, or Candidate substitution.

The Product Owner's exact withdrawal authority is
[Issue #227 comment 6101965743](https://github.com/Yurielo/integra/issues/227#issuecomment-6101965743).
It identifies Candidate `077114…`, its bundle and manifest digests, says it is
not accepted or intended for promotion, and limits any physical retirement to
the normal governed cleanup path.

The canonical protection resolver already validates exact withdrawal records
and grants.  This repair closes the remaining mechanical gap: catalog refresh
now mirrors only such a validated withdrawal as `WITHDRAWN_SUPERSEDED`.  It
does not discover a disposition, select a Candidate, change a package, or
weaken the deletion gate.  The existing cleanup still requires fresh canonical
protection, the exact grant, ownership, integrity, inactivity, and its durable
withdrawal journal before it may remove bytes.

No Product Candidate, CURRENT, rollback selection, Process Board, or permanent
retention limit is changed by this governance-only repair.
