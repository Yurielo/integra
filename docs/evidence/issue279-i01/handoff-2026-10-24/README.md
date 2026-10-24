# I01 K2 supersession and archive integrity gate — 24 October 2026

Issue [#279](https://github.com/Yurielo/integra/issues/279), draft product PR
[#280](https://github.com/Yurielo/integra/pull/280).

## Delivered lifecycle decision

The Product Owner explicitly authorized superseding the prior unaccepted fixed
K2 submission and proceeding through governed rotation/archive/proposal handoff,
with CURRENT unchanged. The verbatim directive and exact outgoing identity are
recorded in [the authorization comment](https://github.com/Yurielo/integra/issues/279#issuecomment-6380155631).
Codex transparently recorded the controlling conversation; no semantic acceptance
was inferred.

[PR #289](https://github.com/Yurielo/integra/pull/289) merged the immutable
`AWAITING_OWNER_ACCEPTANCE -> WITHDRAWN_SUPERSEDED` event and exact withdrawal
grant as `a3fb04e177dc31edb435fc5073b9eacade37aa3f`. Its three-file metadata
scope passed independent read-only review, 80 focused tests, full supported
regression (1,180 total; 1,116 passed; 64 skipped; no failures/errors),
`CURRENT_VALID`, diff checks and [CI](https://github.com/Yurielo/integra/actions/runs/40065304992).
The product branch now includes that canonical metadata.

## Actual governed attempt

The canonical governor was clean at commit `a3fb04e177dc31edb435fc5073b9eacade37aa3f`,
tree `ab337d1ecbc1fd7979a2d26a424462e08227542c`. The build source was the clean,
previously tested A `6e6978a5f88930158058df8e90dbe4275f11c29a`.
The ordinary supervised, reserved build path ran canonical maintenance before
building. It reverified CURRENT, rollback and recovery and correctly replayed
the exact withdrawal into the local catalog. The outgoing record now says
`WITHDRAWN_SUPERSEDED`, retaining publication sequence 1 and the owner reference.

Maintenance nevertheless retained the archive because its actual file set no
longer matches the publisher inventory. Build admission then rejected the
eight-copy cap. No new app was built, no archive was removed, no ninth retained
copy was created and no replacement archive or valid proposal was declared.
The empty owned workspace was cleaned by its supervisor. `build-archive.log`
retains the complete failure and cleanup outcome. The earlier suspicion of
stale lifecycle replay was disproved by the catalog: integrity is the cause.

## Read-only integrity findings

Outgoing Candidate:
`candidate-v1-19e3438fea443e1d917b6575131fd67b47b5f44f71202a6940f85adda12b3b56`.
Bundle: `1fe98fb2822b50077f78f22db960dc1f457f5b6374736a3dace704e99e8fe7e0`.
Manifest: `0704fd913f525d050cdf52f16eefae938cd6d2c9776c92abaf39881f7973efbb`.

- All 29,626 recorded files / 2,202,189,271 bytes rehashed successfully.
- All 32,478 recorded entries retain their expected types and modes. None is
  missing; no recorded file changed.
- Both manifest hashes and the publisher inventory/COMPLETE hashes match.
- Exactly 45 extra `.cpython-314.pyc` files, 1,568,777 bytes total, occur in
  three unrecorded `__pycache__` directories under `Contents/Resources/integra_core`.
- The unchanged strict archive verifier rejects the file-set difference:
  `archive checksum/permission inventory differs from disk`.
- The inactive-consumer check returns code 1 with no stdout/stderr, as required.
  File ownership alone does not make unrecorded entries publisher-owned.

The exact paths, sizes, modes and hashes are in `outgoing-integrity-diff.json`;
full recorded-byte verification is `outgoing-recorded-bytes-verification.json`.
The creation mechanism for the extra caches is not established. No archive code
was executed, no cache was removed and no receipt/inventory was rewritten in this
continuation.

## Concrete recovery decision

`exact-recovery-plan.json` proposes preserving the three exact unrecorded cache
trees in a fresh owned durable quarantine, then running the unchanged strict
verifier against the original archive. It does not delete the unexpected bytes,
rewrite receipts, adopt different ownership or relax any retirement predicate.
The plan SHA-256 is
`d89bed43693b767fc510076ff9a8330a9222c63af960173241137d134fa89b50`.

This plan is **not executed or authorized**. The accepted
`docs/CANDIDATE_RETENTION.md` says: “Existing archive destinations must be
verified, never replaced or repaired in place.” It treats damaged archives as a
recovery incident. Independent boundary review found no existing safe automatic
exception. The owner’s supersession/ordinary-rotation directive therefore does
not authorize moving these unexpected entries out of the immutable archive.
An exact recovery exception is required before that action. All proposed
preconditions, preservation, journal, rollback and stop conditions are recorded
in the plan; quarantine deletion is explicitly not authorized.

After an authorized recovery restores strict integrity, continue ordinary
oldest-eligible rotation and build/archive the unchanged tested replacement
Candidate `candidate-v1-e8064cba8acad3282d86b9d7eea043f85c5eed54ac7db015ccdf089943dee943`.
Then finish exact source A -> evidence B -> proposal-only C, full regression,
candidate-bound proposal validation, canonical proposal/archive registration,
independent review and CI. Owner semantic/product acceptance remains separate.

## Verification scope and CURRENT

The schema repair, packaged regressions and bounded native GUI evidence remain
the previously recorded results for unchanged product source A. The full source-A
suite remains 1,211 total, 1,143 passed, 64 skipped and four missing-proposal
governance failures. These are not relabelled PASS; PR #280 remains draft.
No implementation change or archive creation occurred during the blocked build.

The accepted K1 CURRENT remains
`current-v2-675acf457d65e7633481bcea700036b7e9ef6298e0c6d6eb097e513d3bff249f`.
Both CURRENT files remain unchanged:

- `state/current_product_baseline_v2.json`:
  `bdd2ea30b3102c59cd8e47bc56a0d53c6b57d3bfb0347e667663b1be951e52e2`.
- `state/current_canonical_baseline_v1.json`:
  `0493fbad50f1a5518b01be90e3ffb0cd10d3d8b7a97ae12918fc4595c4438840`.

No source-product repository/pin, installed application, original project,
semantic owner acceptance, live publication or CURRENT promotion changed.
