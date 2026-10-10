# Issue 227 — exact pending GUI-repair Candidate protection rebind

Authority: bounded Product Owner recovery/build instruction at
https://github.com/Yurielo/integra/issues/227#issuecomment-6096774200.
This continues that transaction; it does not accept K2 or merge PR239.

## Exact mechanical delta

Canonical input main: `0f9167c3c4b1a580222c3d7bc19d21042c171141`.
Replace only the old PR239 proposal tuple at
`9ed21fb5f8146563a8e58c3a08129cfd45015ba9` with the current declaration HEAD
`1d413700d3775c680fa488cc6ce55ecdcf45c05b` and derive the active survivor set
through the accepted protection resolver. Frozen product source is
`e504491fe5f09dae94ecdf9ebe179a08d945e8d8`, tree
`190df566fc30c4a992bb3c478763ec827dd27894`.

Candidate: `candidate-v1-077114f64a201b8c5d94c154c3a58f29dd93dba622481e549c0b193b7bd7571d`.
Bundle: `9c558edc7928241696a8d40f21b4a35fd3099d3194b41b912eb1237c870d0a9e`.
Manifest: `bbb42f10ec5e156a876dabc4bc0349df89ddd3a2295b1811cc2b2cbb6870c606`.
Owner acceptance remains null. CURRENT and Process Board remain unchanged.

The superseded aee638 Candidate is not deleted or modified. Its exact former
registration remains in Git history and its nonterminal catalog lifecycle remains
unchanged. Removal of an obsolete active-Proposal selector is not deletion
authority. All original nine packages and the new tenth remain byte-identical.

## Completed read-only preflight

`/private/tmp/integra-227-gui-registry-rebind-final.json` records a fresh exhaustive
GitHub capture, all-ten fingerprints against the immutable publication receipt,
accepted survivor derivation, prospective protection COMPLETE with zero blockers,
and exact new archive verification. Catalog, archives, CURRENT, Process state and
the original registry were unchanged during that read-only verification.

Original registry SHA256:
`f5e1839e1dc7b68dd3eaf5928f44764fe288e70ad25f562004c5c51afe04094f`.
Derived registry SHA256:
`d9938b387d8a2d558cee7a41878026704a69e4f0534112be3be674ca7725be1b`.
Pure derivation tests: 6 passed, including refusal of acceptance, substitution,
wrong/duplicate old tuples and changed product source.

PR239 exact-head Quality Gate run 38053004530 passed. Its final full suite ran
1161 tests: 1097 passed, 64 skipped, no failures/errors. The exact 64 skip names
and reasons match the prior source baseline. Actual production native GUI evidence
proves retained modal/input on unchecked Apply, successful checked Apply and
reopen with two Concepts and one Relation; evidence is in PR239 and Issue227.

Historical isolated `knowledge-open: exit 2` and the first-modal disappearance
remain UNVERIFIED; neither is represented as a diagnosed/fixed defect.

## No policy or product expansion

Permanent retention limits remain 8 copies / 20GiB / 15GiB free reserve.
The consumed one-use exception alone accounts for 10 copies / 22GiB; normal-cap
excess is reported separately and is not a protection waiver. All unrelated
registry roles, grants, selectors, historical gaps and lifecycle semantics remain
exact. No product files, Candidate bytes, cleanup, acceptance or promotion change.

This PR must satisfy focused/full tests, governance, independent review and
exact-head CI before canonical activation. Afterwards only the accepted locked
`refresh_protection` API may reconcile catalog protection/lifecycle evidence to
the new main. This document is prospective evidence, not self-activation authority.
Actual post-merge/refresh results are recorded separately in Issue227.

## Proven QA-harness completion-budget repair

The first retention-focused discovery run completed 60 tests with one failure:
`test_24_build_cleanup_common_lock_blocks_race` observed `exitcode=None` at
`worker.join(5)`. An unchanged isolated rerun reproduced that exact failure.
A diagnostic using the same real tiny-archive fixture confirmed exclusion while
the parent held the catalog lock, then observed the real unchanged build preflight
complete with exit 0 and `finished=true` 9.4287 seconds after lock release.
The original five-second deadline was explicitly recorded as failing, not hidden
or relabelled PASS. Actual production snapshot/plan/subprocess calls were retained.

The only QA-harness change increases that post-release completion wait to 60
seconds. The five-second worker-start wait, held-lock `finished.wait(.1)` exclusion,
exit-status-zero and completion-event assertions are unchanged. No lsof, canonical
protection, archive verification or production timeout is replaced/disabled. This
is a test completion-budget defect, not a claimed production retention defect.
Independent review approved the narrow change; the new exact bookkeeping HEAD
must rerun focused/full/governance/CI gates. The earlier full run is superseded and
must not be reported PASS. Candidate/source implementation and permanent policy
remain unchanged; this additional changed file is test-only.
