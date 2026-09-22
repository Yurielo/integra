# Process v1: Recovery lifecycle proof

Date: 2026-09-22. Status: `BLOCKED` — proof-only verification found a bounded
product defect; no repair is included here.

## Scope and identity

This is the frozen Process v1 `VERIFY_EXISTING` lifecycle package only. It
started from `main` `1b02dfd2a1111f4ebf82de36c027a0164fd32a07` and CURRENT
`current-v2-589ef6063fd6d8b1bba248fce7fa1f8fa1494df17c4e930e7fc295f873686c1a`.

The reused immutable Candidate is
`candidate-v1-589ef6063fd6d8b1bba248fce7fa1f8fa1494df17c4e930e7fc295f873686c1a`
at `/private/tmp/integra-multisource-candidate.4v1PCw/Integra.app`. Its
manifest validates and is byte-identical to
`docs/evidence/PROCESS_V1_MULTI_SOURCE_CANDIDATE_MANIFEST.json`
(`9e0583a8f67b2631f635ab1544890374b204687670b0306926a08922fe2778e1`).
Its source is `d93f0fa8dfda452a8817635c8cf58ee9ce93c330`; the lifecycle
governed bytes are unchanged through canonical main:

| Path | SHA-256 in Candidate and current main |
| --- | --- |
| `macos/Resources/bridge.py` | `dbcfae45b247acad40503399f96926ed514ecc863df7f44eea4363aa361d67ec` |
| `integra_core/shutdown_runtime.py` | `cb7c4e7f3aab2fb66ed7c3cd3a53cf7f5a84385968a68a56d195855161e83edc` |
| `integra_core/application_runtime.py` | `7f0f7f32697f1bd51640190f1e97a4fc4c888b13de39ced2b0226279b9092f7a` |

The historical #161/#162 non-skipped `12/12` ASR reuse/invalidation evidence
therefore remains applicable to this Candidate. It was not rerun. The Candidate
itself was not rebuilt. The probes below use the bundled, hash-validated
SeminarText and VideoText runtimes with test-only media executables; they do not
exercise ASR quality or change production bytes.

## Executed Candidate probes

| Probe | Result | Exact evidence |
| --- | --- | --- |
| Native Operations | PASS | `/private/tmp/integra-recovery-lifecycle.drgz6z/operations/ops-probe.json`, SHA-256 `e339b737dfac953086f85c58652815cdb214d8a3fdcc46d7594908d4b3319b08`; visible native Operations snapshot SHA-256 `1dae8d50020a3f31fd6b10d8621aba3459e8fcb62a5a3a380693285aa70fe52f`. |
| Native failure → Retry | PASS | Failed run SHA-256 `4a25c79a716ceeb441263e529be0b7514122730f947e5db11824b6d1ac246d3f`; completed retry SHA-256 `5ce93fee09ae004c274e2a8b7cfa0000f703d6f3263b7af979e3f87516562ffa`; native before-retry/results snapshots SHA-256 `dacbbe2da4ffb81b3555cad533b98da4c4a591ff8dde2a4cbf121309221d7d02` / `e6a12da2b7c193ac77ce48e543ca79f3bdf7cec4553f16a77d7eb370a12a3946`. |
| Native Close / Quit / stale re-entry | PASS | `/private/tmp/integra-recovery-stale.gIGDAP/native-shutdown.log`, SHA-256 `23c7c389719aa72b3b6bd5d6268b6c865833b762e4e946b7c4c711c8a216619b`; reconciled record SHA-256 `c76fefe3e57d19f0b46ff4e6fe101ef3831ae6539d63842a7335634ade91a4a6`. |
| Packaged timeout | FAIL — defect | `/private/tmp/integra-recovery-timeout.Bd036u/run/timeout-evidence.json`, SHA-256 `f20a11a2c66b75ed6e9b61a421196ed7cd8b954680621e9d48bd30f4f0279cd3`; probe log SHA-256 `6f7b1a2d16148028428f2fce6077b5c1981346ed9c933fa4a2e2321597388550`. |

The timeout probe is deliberately candidate-bound: it started a real packaged
bridge plan, reached the actual bounded timeout, and checked its exact test-owned
recognizer descendant. The failed probe cleaned only that exact fixture PID after
recording evidence, so it did not leave a test process behind.

## Seven frozen Board rows

| Board item | Starting state | Exact frozen acceptance gate | Result | Board transition |
| --- | --- | --- | --- | --- |
| Cancel active processing | IN_PROGRESS | Cancellation, truthful final state, saved diagnostics and no false success | PASS: native Operations showed real `RUNNING`, invoked the native Cancel action, persisted `CANCELLED`, cleaned the owned child and preserved an unrelated process. | `IN_PROGRESS → DONE` |
| Retry after failure | IN_PROGRESS | Controlled failure → user retry, distinct lifecycle state | PASS: native Word Timeline failure was `FAILED`; the native Retry action created a distinct run which was `COMPLETED`. | `IN_PROGRESS → DONE` |
| Next run without Integra restart | IN_PROGRESS | Controlled failure then subsequent same-session success | PASS: the same native Candidate process retried without restart; ASR was `REUSED` and the successful result was persisted. | `IN_PROGRESS → DONE` |
| Timeout of stuck process | IN_PROGRESS | Timed-out worker has truthful terminal state and usable recovery | OPEN: the packaged run truthfully became `FAILED` with `Processing exceeded bounded timeout (2s)`, but it left the owned recognizer descendant alive. The required cleanup/usable-after-timeout condition is not met. | unchanged |
| Background-process cleanup | IN_PROGRESS | No orphan workers after completion, failure, cancel | OPEN: Cancel, Close and Quit passed, but the timeout scenario left its owned descendant alive. A general cleanup claim would be false. | unchanged |
| Reconcile stale RUNNING | IN_PROGRESS | Relaunch reconciliation without false completion or lost artifact | PASS: native app startup converted the controlled stale record to `FAILED / STALE_RUNNING_RECONCILED`; the unrelated PID was not signalled and persisted state stayed readable. | `IN_PROGRESS → DONE` |
| Clear processing statuses | IN_PROGRESS | Visible Processing/Completed/Failed/Cancelled states on controlled paths | PASS: native Operations supplied `RUNNING`/`CANCELLED`; native Retry supplied visible `FAILED` then `COMPLETED` snapshots. | `IN_PROGRESS → DONE` |

## Exact blocker and return condition

The bounded failure class is **timeout cleanup of an owned descendant**. The
candidate's timeout state is truthful (`FAILED`), but the test-created recognizer
child remained live after the parent plan worker timed out. This is not a test
skip or a source-only inference. No repair was attempted.

The smallest next Board action is a bounded **timeout-owned-descendant cleanup
repair**, followed by rerunning only the timeout and affected lifecycle probes on
one new Candidate. It must preserve identity-verified ownership, must not signal
unrelated processes, and must not change any Process scope or ASR semantics.

Board counts move only for the five exact PASS rows: **14 DONE / 16 IN_PROGRESS
/ 17 NOT_DONE / 1 BLOCKED** → **19 DONE / 11 IN_PROGRESS / 17 NOT_DONE / 1
BLOCKED**. This is neither a Process v1 user-acceptance record nor a new
implementation authorization.
