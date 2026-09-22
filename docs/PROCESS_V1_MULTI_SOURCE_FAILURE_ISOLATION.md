# Process v1: bounded multi-source failure isolation

Status: technical proposal evidence only. It is not `PROCESS V1 USER_ACCEPTED`,
does not change CURRENT, and does not authorize merge or promotion.

## Source A and Candidate

| Binding | Exact value |
| --- | --- |
| CURRENT base | `ac7dd908b90da6c9b5a3636f24a9eb1deb0c4ede` |
| Product source A | `d93f0fa8dfda452a8817635c8cf58ee9ce93c330` |
| Product source tree | `5d4f03a752e9e00136a6049161845b369d2588ba` |
| Candidate ID | `candidate-v1-589ef6063fd6d8b1bba248fce7fa1f8fa1494df17c4e930e7fc295f873686c1a` |
| Candidate bundle digest | `9a902e47d83ef9e7e27f744d6438d885558cda53f8dba735d954544e100713a2` |
| Candidate manifest SHA-256 | `9e0583a8f67b2631f635ab1544890374b204687670b0306926a08922fe2778e1` |

The Candidate was built in a new isolated path. It binds pinned SeminarText
`970bde598ddd649599295139986933e0e06cb9c0` and CLI SHA-256
`f7f411bf106341ae970bc40d759e1e3c964273b977bdb12d0f1840e629def13a`.
Its native `--self-test` passed. The source build initially stopped because the
fresh worktree lacked the governed review-wheel cache; the exact hash-locked
five-wheel cache was restored into an isolated temporary path using the
repository-prescribed `pip download --require-hashes` command and passed
`validate_review_wheel_cache.py`. No dependency pin or product byte changed.

## Bounded repair

The old `execute_run()` caught a local MEDIA exception outside the source loop.
It made the entire run `FAILED`, stopped later independent sources, and only
added an inspectable failed result for `ASRQualityError`.

For a plan with more than one selected local MEDIA source, the repair records a
bounded `FAILED` source result (`source_id`, display name, state, empty
successful-output map, bounded error; ASR-quality artifacts where present) and
continues later source-isolated jobs. Any failed source keeps the run terminal
state `FAILED`; an all-success run remains `COMPLETED`; cancellation remains
`CANCELLED` and stops remaining work. A single-source exception retains its
previous fail-closed behavior. The native result view now renders retained
per-source results for a truthful `FAILED` multi-source run.

No Recovery semantics, component pin, ASR setting, folder/playlist/Zoom flow,
or Process scope changed.

## Evidence

| Gate | Result | Evidence |
| --- | --- | --- |
| Deterministic orchestration matrix | PASS | `tests.test_application_runtime`: good→good, good→corrupt, good→fail→good, fail→good, retry/re-entry, cancellation; all six pass. |
| Existing focused runtime/bridge/reuse/recovery/UI suite | PASS | 51 run, 20 environment skips; no test is counted through a skip. |
| Candidate manifest | PASS | Candidate manifest validation; immutable source A and bundle bindings above. |
| Native self-test | PASS | `INTEGRA_MACOS_SELF_TEST: PASS`. |
| Packaged Finder-like multi-source proof | PASS | Bundled bridge under minimal `PATH`; project `d6bf9ff8-a00e-4aba-8e99-74d7b646ab65`, run `530e3742-c5e9-4a07-a74b-8da812387590`; output evidence SHA-256 `28c3e745bcc4e7c2b3c65aed5c2ca095a3d5dd39816f4aa7e27993c99f3b30d2`. |

The packaged proof used selected `enhance_audio` to isolate orchestration from
ASR/model cost: `first.wav`, controlled-corrupt `corrupt.mp3`, then `later.wav`.
Its source result order is exactly the selected order and states are exactly
`COMPLETED / FAILED / COMPLETED`; global state is `FAILED`, two valid owned
outputs remain readable, the failed source has no successful output, and a
fresh bundled-bridge status read returned the same persisted record. This is
the required partial-persistence proof, not a substitute for the separate
protective-ASR-retry gate.

## Completion Board transition

Before: **12 DONE / 16 IN_PROGRESS / 19 NOT_DONE / 1 BLOCKED**.

After: **14 DONE / 16 IN_PROGRESS / 17 NOT_DONE / 1 BLOCKED**.

Only `Several local files` and `Ordered processing` moved `NOT_DONE → DONE`.
The next Board-selected action remains a future, uncreated item: **Folder
discovery/confirmation integration**, because it is still `NOT_DONE` and is
not part of this bounded repair.
