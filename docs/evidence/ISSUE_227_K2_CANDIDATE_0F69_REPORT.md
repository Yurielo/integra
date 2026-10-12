# Issue #227 — K2 Owner Candidate pre-handoff evidence

Candidate: `candidate-v1-0f69e617c0841f27afe2238a28d6c25ae5a80ce0fedf01cf0c114638de575032`\
Bundle: `3d4d33a983455572157b06460c3faaef5afd0b977a0e3d2717101588a25718e5`\
Manifest: `3aed49cda900a6af0d0e8abcae4f3db114d988ad9bf16c62c53ba6671d06cbfe`\
Product source: `9d28dcdbf74ab039414ed943b12ceddc0f345663` (`1cc7ecbfb2e589d7275f8257e8cec5cff23b731a`)

## Direct package verification

- Archive verifier: `COMPLETE`, exact Candidate/Bundle/Manifest identities and inventory `d07e2a9692c85ef28d92d4ba97b4a0be0bf4d9d33d0365b0110689245963b25f` (29,626 files).
- Packaged manifest validation: PASS.
- Packaged app self-test: `INTEGRA_MACOS_SELF_TEST: PASS`.
- Immutable source in the packaged manifest is clean and matches the exact product source commit/tree above.

## Real packaged GUI evidence

The archived app was used to create a supervised disposable execution copy, then launched through the native macOS UI. K1 and K2 interactions were performed in that UI and inspected through live accessibility state. The isolated Issue #236 fixture contained two reviewed fragments; no SeminarText source project or canonical demo was changed.

The test exercised the previously missed K1 interaction path: a decision was entered for fragment 1 while fragment 2 remained blank, then Save was attempted. The review dialog remained open, the first choice remained selected, and the UI explicitly identified fragment 2 as needing a decision. After choosing the second decision, both fragments appeared in the saved notebook. There was no manual reviewer-ID input and no opaque word/provenance ID in the ordinary UI; provenance remained labeled as machine-produced and not human-verified.

The same packaged GUI session continued through manual K2 proposal review. Two Concepts were accepted with human rationales; a Relation was separately proposed between them with its relation type and evidence bases reviewed. Apply without explicit package confirmation preserved the modal and decisions and reported that no apply had occurred. After confirmation, the UI reported 2 Concepts and 1 Relation applied. Closing and reopening the accepted version displayed both Concepts and the Relation, with source-navigation evidence available.

This is a synthetic QA fixture run, not semantic acceptance of real seminar content. The machine-readable step record is [ISSUE_227_K2_CANDIDATE_0F69_GUI_E2E.json](ISSUE_227_K2_CANDIDATE_0F69_GUI_E2E.json).

## Automated checks and state boundaries

- Focused K2 suite: 45 passed.
- Full supported suite on the macOS host: 1,225 passed, 130 skipped.
- The first exact-head GitHub CI run exposed two errors: the owned-workspace lifecycle and Candidate execution-copy guard hard-coded macOS-only `/private/tmp`, while CI runs on Linux. The helper now selects only `/private/tmp` on macOS or `/tmp` on Linux and retains the exact per-user owned directory, mode-0700, live-owner marker and purpose checks. This changes QA tooling only, not packaged application bytes or the existing Candidate.
- The test fixture uses the same exact platform-specific base; focused validation and the subsequent exact-head full CI run are recorded separately from the earlier macOS full-suite run.
- Current baseline and Process Board were not changed.
- Candidate is still in pre-owner validation state; this evidence does not accept it or promote CURRENT.
- Owner acceptance and product PR merge have not been performed.
