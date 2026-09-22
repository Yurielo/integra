# Recovery WP — reconciled current main evidence

Status: `IN_PROGRESS`. This is technical evidence only; it does not create a
CURRENT record, promote Recovery, or assert `USER_ACCEPTED`.

## Reconciliation

Recovery repair commit `242e70517bb345e74b84086994639a919daa511a` was replayed
without semantic edits onto authoritative `main`
`2af7de54964d267ff47267f9e43bb9c0b41973ac` as this branch's parent repair
commit. The product diff remains exactly three files:

- `integra_core/shutdown_runtime.py` — bounded plan timeout and stale-run
  reconciliation;
- `macos/Resources/bridge.py` — re-entry reconciliation and bounded wrapper;
- `tests/test_recovery_contract.py` — deterministic lifecycle regressions.

No ASR parameters, component pins, or Recovery contract semantics changed.

## Governed runtime restoration and non-skipped reuse ledger

The formerly skipped ASR reuse suite was run against the existing exact
governed SeminarText checkout, without copying or modifying it:

| Binding | Verified value |
| --- | --- |
| SeminarText checkout commit | `970bde598ddd649599295139986933e0e06cb9c0` |
| `seminartext` SHA-256 | `f7f411bf106341ae970bc40d759e1e3c964273b977bdb12d0f1840e629def13a` |
| Silero VAD SHA-256 | `29940d98d42b91fbd05ce489f3ecf7c72f0a42f027e4875919a28fb4c04ea2cf` |

Command (with exact checkout, verified VAD, and an already governed bundled
VideoText subtitle runtime supplied only for the production adapter preflight):

```text
python3 -m unittest tests.test_asr_reuse -v
```

Result: **12 run, 12 passed, 0 skipped**.

Those cases prove exact-identity reuse; source/model/engine/config invalidation;
tampered, missing, incomplete and symlinked cache rejection; downstream
failure does not discard the valid upstream ASR; cancellation does not become
success; and concurrent cache locking. They replace the prior incorrect use of
skips as evidence. A final Candidate-bound rerun is still required before the
Recovery proposal can be valid.

## Candidate state

An initial build attempt proved the old default local SeminarText path was the
historical `a94936c…` checkout and was correctly rejected. The controlled
attempt uses the exact checkout above and a clean detached VideoText checkout
at its already pinned commit. No product source or pin was modified. The next
section will record one fresh isolated build attempt and its complete result.

## Gate ledger

| Mandatory gate | Current state |
| --- | --- |
| non-skipped ASR reuse/invalidation | PASS — source-bound; final Candidate rerun pending |
| recovery targeted matrix | pending final Candidate |
| realistic cancellation/failure → success and orphan cleanup | pending final Candidate |
| Finder-like deterministic and realistic primary journeys | pending final Candidate |
| owner-derived Word Timeline regression | pending final Candidate |
| native self-test | pending final Candidate |
| strict PROPOSED validation | pending final Candidate evidence |

No mandatory pending row is reported as PASS. If the fresh candidate build
cannot finish, this work stops `BLOCKED_ENVIRONMENT`, without consuming repair
cycle 2.
