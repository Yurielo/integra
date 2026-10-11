# Issue #252 — K2 Owner Candidate canonical protection registration

## Exact scope

This governance-only record registers the exact open Proposal Lite in PR #251
and its existing archived K2 Owner-Test Candidate with canonical protection.

- PR: #251
- exact PR head: `0d28ad0fcadf06b5bfcdf42bd1062d7da18b8e73`
- Candidate: `candidate-v1-cbdbdc7a722d2b4c2c47fbffd08fd2014df43e62872fe9c24995d158190a3e24`
- Bundle: `175f74f53d5d821fafafb27fd80809b0c793944c808bbcc968c699249ce234f8`
- Manifest: `929bbf5a0599ba0c4957711e3e5a88011f3bede220a488d9d5b8347d3e03e101`

The Candidate already exists as one complete immutable archive. This change
does not build, copy, modify, promote, accept, merge, or delete a Candidate.
It does not modify CURRENT or the Process Board. It supplies the canonical
registry reference and exact selected-survivor path required for the resolver
to bind an open Proposal to a verified local archive.

## Preconditions and expected result

The registration is valid only while GitHub reports PR #251 open at the exact
head above and its `state/proposed_baseline_lite_v1.json` binds exactly the
same identity tuple. Any PR head drift, closed PR, Proposal substitution,
archive identity mismatch, or incomplete archive remains fail-closed.

After this standalone registration PR is merged, fresh canonical protection
may treat the Candidate as the protected open-Proposal survivor. It does not
authorize Owner acceptance, CURRENT promotion, or merging PR #251.
