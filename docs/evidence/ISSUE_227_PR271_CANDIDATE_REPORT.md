# Issue 227 / PR 271 — final Stage-1 Owner-Test Candidate

This is a technical handoff record, not Product Owner acceptance or permission
to promote CURRENT. Prior Owner-Test launch instructions name historical
Candidates; the exact launcher binding in this overlay supersedes them.

Product source: `b864b6459c902f3f3d605ef8036d5a7f303612e5`.
Tree: `ab20e1c7d9e7db8ed4e4bd738c0b39f4f123a7ed`.
Candidate: `candidate-v1-2d770b6b3ff323a9b60c45cecdb7b5c36652b11cb102f16de63145530997dd11`.
Bundle: `e3c5bce9cefd8facb8ca228b56b66a560443629d94e97dd3e0d630ed06fb9164`.
Manifest: `6d5bb4b9f4abc8863ecfc05222df3651141cb23a37e135e3d19aeb5c4ef57ccc`.

## Proven engineering gates

- Full supported runtime suite at exact product HEAD: 1247 tests discovered,
  1183 passed, 64 existing environment-dependent skips, zero failures/errors.
  Skip classes concern optional ASR/VideoText/BookText/native rebuild/reference
  Candidate inputs. Real packaging, source-viewer GUI and Knowledge admission
  were separately verified; skipped checks are not claimed as passing.
- Pinned K1/K2/governance focused suite: 111 tests PASS. Final native
  controls/routing: 3 PASS. Source-rebase guard: 2 PASS.
- Independent source review and pre-owner evidence review: PASS.
- Complete production native semantic journey on `e757d96c…`: normal provisional
  machine result without human acceptance; explicit optional relation exception;
  DEFER and EDIT; visible confirmation; missing confirmation retains modal/input;
  Apply creates two Concepts and a Depends-on Relation; reopening retains the
  exact revision. Synthetic QA only, not acceptance of real knowledge.
- Subsequent source changes only localize/redact unavailable-source errors.
  Independent diff review approved incremental final GUI coverage.
- Final production-shaped engineering package on `b864b645…`: normal notebook
  and knowledge say “Готово — решений от вас не требуется”; decoded blue video
  is visible; manual seek 0.5 seconds advances to 0.903719912 seconds while
  playing; second exact range 2.2–4.4 seconds opens playing at 2.466083151.
- Missing-source test shows an actionable Russian message, logs only a fixed
  error code, preserves the notebook, and does not expose raw paths/errors.
  Fixture media restored; engineering app exit and supervised cleanup PASS.
- Existing withdrawal/cleanup was completed before this build. No protected
  package was manually deleted or changed. Normal retention limits are intact.
- Published archive COMPLETE: 29626 inventory entries, 2202224208 application
  bytes; inventory SHA256 `259ecf34302bad9ad45fd1fa6fc96c67e321898dcf52ea68a976f2d651af4cf3`.
- Source freeze is active. Its guard rejects rebase of the published branch.

The complete semantic GUI journey is not relabelled as a final-HEAD run.
Final-build source-viewer coverage and the inspected implementation delta are
explicitly recorded in the accompanying JSON evidence.

The earlier runtime-checkout setup failure was followed by a successful exact-pin
full rerun. Its disappearance mechanism is UNVERIFIED. Historical single
`knowledge-open: exit 2` remains UNVERIFIED and is not claimed fixed.

## Candidate-bound delivery

The Candidate is immutable in `CANDIDATE_BOUND_VALIDATION`. The evidence overlay
changes only this report, manifest/evidence copies, launcher tuple/self-test
verification and its Candidate-bound regression pin, never packaged product
bytes. Proposal declaration follows as its own single-file
commit. Canonical registration, final governance/CI, archive/protection/retention
reverification and independent final QA must pass before Owner handoff. Their
completed exact-head results are recorded in Issue 227 rather than modifying
this declaration-bound evidence afterward.

Owner launcher uses a separately verified disposable execution copy. It never
executes or imports the protected archive. It seeds only synthetic QA material;
real semantic acceptance is false. Closing the application removes that isolated
test session, not user content or any protected Candidate.

CURRENT SHA256: `bdd2ea30b3102c59cd8e47bc56a0d53c6b57d3bfb0347e667663b1be951e52e2`.
Process Board SHA256: `549bceeb7ce2a6f6d138bae2726aeb5ee78279999e815b1bb7fc0101d87b4dfb`.
Process Board remains 41 DONE / 3 NOT_DONE / 1 BLOCKED. K2 is a separate Knowledge
outcome. No Stage 2, CURRENT promotion, product merge or Owner acceptance occurs
in this handoff transaction.

Engineering evidence: https://github.com/Yurielo/integra/issues/227#issuecomment-6225004776
