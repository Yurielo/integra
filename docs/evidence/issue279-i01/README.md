# I01: packaged Knowledge View schema repair

**24 October update:** [resumed native GUI QA](gui-2026-10-24/README.md) completed the bounded concept/relation review, relaunch/reopen and source-navigation checks. The pending-unlock statements below describe the 23 October run. Retained publication and valid proposal remain blocked.

Issue #279 / PR #280. Validation date: 23 October 2026 (Europe/Istanbul).

## Root cause and repair

The native GUI bridge loads integra_core/knowledge.py from Contents/Resources. Its validator resolves schemas/knowledge_view_v1.schema.json relative to that Resources directory. The earlier build omitted that resource. Commit 7c42384 added the exact schema copy; this continuation preserves that fix and replaces byte-presence-only assurance with real build/serialize/reload validation.

The isolated missing-schema case reproduces FileNotFoundError at the same packaged Resources/schemas path. The positive case uses /usr/bin/python3 with isolated imports and unrelated CWD; a deliberately altered schema is rejected, proving the validator executes. The actual native test gate invokes the same probe against the built app.

A separate packaged K2 bridge probe exercises QA-only reviewed fragments, explicit ACCEPT/EDIT/REJECT/DEFER decisions, two Concepts, one controlled Relation, persisted edits, exact source navigation, reopen and an unpublished managed package. Synthetic decisions are not Product Owner semantic acceptance.

## Governance

The pending K2 implementation changes Knowledge View runtime/schema bytes relative to the historical R9A certificate. Exact proposed before/after hashes are now accounted for by the existing candidate-bound proposal mechanism, matching the R12/R13 pattern. The schema is an explicit governed product path. Historical certificates and CURRENT remain unchanged; full proposal structure, source/evidence lineage and candidate checks remain mandatory.

Independent code review passed the packaging/regression work. Independent governance review passed 46 focused tests and diff checks. The initial full supported run executed 1,210 tests: 1,142 passed, 64 skipped, four governance failures because no active candidate-bound proposal exists. The updated governance/proposal/packaging run executed 140 tests: 136 passed, the same four proposal-dependent checks failed. The final full supported suite on source `6e6978a` ran 1,211 tests in 856.203 seconds: 1,143 passed, 64 skipped, and those same four governance failures remained. No additional failures or errors occurred. These failures are retained, not relabelled PASS.

## Retained Candidate publication blocker

The ordinary retained-build gate reports eight retained full copies, 18,293,366,784 attributed bytes, and zero eligible terminal retirements. It refuses a ninth retained copy. CURRENT, rollback, pending proposals and unknown artifacts remain protected. The prior fixed #279 build candidate-v1-19e3438fea443e1d917b6575131fd67b47b5f44f71202a6940f85adda12b3b56 is still AWAITING_OWNER_ACCEPTANCE; it is not automatically eligible for retirement.

Disposable validation used the existing archive_copy=False build admission. No archived bytes are executed, no cap is increased and no retained app is removed. No PROPOSED_BASELINE_VALID / READY_FOR_OWNER_ACCEPTANCE claim can be made while required retained archive/proposal gates are blocked.

## CURRENT byte invariants

- state/current_product_baseline_v2.json SHA-256: bdd2ea30b3102c59cd8e47bc56a0d53c6b57d3bfb0347e667663b1be951e52e2
- state/current_canonical_baseline_v1.json SHA-256: 0493fbad50f1a5518b01be90e3ffb0cd10d3d8b7a97ae12918fc4595c4438840

## Validation sequence and limitations

The first fresh disposable build at source `952bee4` passed candidate-manifest validation, the real packaged Knowledge View schema round trip, and the native self-test. The wider synthetic bridge probe then failed on its own navigation timing assertion (`KeyError: start_seconds`): evidence stores times in `locator`, while navigation flattens those fields. No product failure was observed at that step. Commit `6e6978a5f88930158058df8e90dbe4275f11c29a` corrects that comparison. Its full probe received independent read-only contract review with no remaining findings. The first failed probe trace remains in `first-build-build.log`; its temporary app was cleaned up by the supervisor.

The second fresh disposable build validated exact source `6e6978a5f88930158058df8e90dbe4275f11c29a`, tree `d6a4ba71a2939e62bf7d765270b148ea67034dae`. Its corrected packaged probe passed. Exact identity and the partial native GUI outcome are recorded below.

## Change scope in this continuation

- `scripts/test_macos_app.sh`: execute the actual bundled validator/build/reload regression.
- `tests/test_packaged_knowledge_view.py`: missing schema reproduction, positive round trip, mutated-schema rejection, actual-app entry point.
- `tests/packaged_k2_probe.py`: isolated packaged bridge QA, exact decisions/relation/locators, persistence and unpublished package checks.
- `scripts/proposed_baseline_lite.py`: include the Knowledge View schema in exact governed proposal inventory.
- `scripts/validate_governance.py`: account only for a precisely bound proposed R9A successor; immutable historical evidence remains checked.
- `tests/test_governance.py`: positive and negative exact successor accounting checks.

The merge from main brings canonical a674 withdrawal/retention hardening without changing CURRENT. No SeminarText/VideoText source, model pin, installed app, original project, semantic owner acceptance or promotion is changed.

## Native GUI state

The same fresh app was launched with an isolated data root and GUI-minimal PATH. Its native Knowledge screen opened the reviewed two-unit notebook, displayed exact source/transcript revisions and word ranges, opened the unaccepted K2 state, showed unchecked fragment selectors, generated four preliminary proposals, and opened the explicit relation dialog with unchecked evidence choices and unselected concept/type controls. The operating system locked during first-concept selection. GUI completion, actual review/apply and reopen/source-playback evidence remain PENDING_UNLOCK; they are not reported as passing.

## Latest fresh build identity

- Candidate: `candidate-v1-e8064cba8acad3282d86b9d7eea043f85c5eed54ac7db015ccdf089943dee943`.
- Bundle SHA-256: `1fe98fb2822b50077f78f22db960dc1f457f5b6374736a3dace704e99e8fe7e0`.
- Source: `6e6978a5f88930158058df8e90dbe4275f11c29a`, clean tree `d6a4ba71a2939e62bf7d765270b148ea67034dae`.
- Candidate manifest SHA-256: `25255077dfd65185268ba152c50a1a5ba66d1a425ff9bcab342263f6fbb2c58e`.
- Actual bundle validation, packaged schema round trip, native self-test and corrected packaged K2 bridge probe: PASS.
- Archive publication: BLOCKED by protected capacity. No retained Owner Test Candidate or valid candidate-bound Proposal is claimed.
