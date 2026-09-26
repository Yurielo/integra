# Proposed Baseline Lite — Issue #165

Status: `PROPOSED_BASELINE_LITE_READY` only after this branch's Quality Gate is
green. This document does not promote any product change.

## Boundary

This is the deliberately small implementation of the #163 design:

```text
CURRENT → PROPOSED_BASELINE_VALID / AWAITING_OWNER_ACCEPTANCE
        → explicit human-owner reference → exact promotion → CURRENT(next)
```

It protects against accidental/self-consistent implementation drift. It is not
the full external-authority security design: it does not introduce a protected
branch rule, external signature service, or out-of-band approval store. In
particular, a developer with repository-admin authority could change both code
and the Lite validator; that residual governance limitation is explicit, not
silently treated as solved.

Technical GREEN, a branch name, a PR state, test output, a candidate manifest,
or a generic evidence file is never an owner acceptance reference. The helper
requires a separately supplied explicit owner reference and only **prepares** a
next state file. It does not merge, deploy, alter GitHub state, or claim
`USER_ACCEPTED` on its own.

## Truthful CURRENT v2 bootstrap

`state/current_product_baseline_v2.json` records the accepted scope exactly:

- candidate `candidate-v1-c5851d168b116fed83109014519ebc01c0291e23705ac9d2ec0a4e5df2471960`;
- bundle digest `90c6c816c7f4ec82b8a3393c46a5a96239ce7cbc16ba50a83677d78a0cdea8cb`;
- accepted-owner decision [Issue #156 owner comment](https://github.com/Yurielo/integra/issues/156#issuecomment-5768296395), scoped only to the Local Russian Video Primary Journey;
- promotion correspondence: `main` commit `4f20ed5ad76af164a5561e33510b7d36b903eee8`, tree `746f31102bb46ee223fe4417378ea74ffa55bdb9`, after the owner-authorized #160 promotion.

The record also binds repository `Yurielo/integra`, the #156 report head,
the #159 owner-authorization comment, and PR #160. These are factual
correspondence references, not fabricated prior attestations.

It does **not** retroactively say that every path in `main`, any secondary
journey, or any future candidate is user accepted. Its historical predecessor
hashes bind untouched `current_canonical_baseline_v1.json`, R12, and R13.
Those records remain historical certification; they are not rewritten.

## Contracts and validator states

- `schemas/current_product_baseline_v2.schema.json` defines the CURRENT
  register. Its active record has exact Candidate, scoped owner acceptance,
  historical predecessor hashes, and current governed-file hashes.
- `schemas/proposed_baseline_lite_v1.schema.json` defines a PROPOSED record:
  exact base CURRENT/main, product source **and exact PR HEAD/tree**,
  intended WP/journey, Candidate/manifest/bundle digests, before/after delta,
  all mandatory gates with evidence references and hashes, candidate-bound
  evidence, and a deliberately null `owner_acceptance`.
- `scripts/validate_governance.py` reports `CURRENT_VALID` only while the v2
  governed bytes match. A malformed/missing/stale CURRENT or unaccounted byte
  drift fails closed. It cannot output a USER_ACCEPTED decision.
- A separately supplied valid proposal evaluates as
  `PROPOSED_BASELINE_VALID / AWAITING_OWNER_ACCEPTANCE`. It remains a proposal;
  it cannot mutate CURRENT.
- `scripts/promote_proposed_baseline_lite.py` validates both contracts and
  refuses to run without `--owner-acceptance-ref`, `--candidate-archive`, and
  `--current-archive`. The proposed archive must match
  all three proposal identifiers: Candidate ID, bundle digest, and manifest
  digest. The outgoing CURRENT archive must match its recorded Candidate ID
  and bundle digest. Missing, altered or metadata-only archives block all
  output writes. Output paths inside either archive are rejected.
  See [Candidate retention](CANDIDATE_RETENTION.md). It re-resolves HEAD/tree,
  each declared before/after Git blob, the candidate manifest/bundle tuple,
  candidate evidence and named gate/report hashes before writing an explicit
  output requested by the caller rather than replacing repository state. It
  also requires a repository-relative history-output path and writes the
  prior CURRENT record there before producing CURRENT(next), so promotion does
  not erase the prior record. Both outputs must be distinct new files;
  existing outputs are never overwritten.

The proposal record binds a source commit/tree and an exact delta. The bounded
overlay list is only for proposal metadata/report paths; it is not a broad
branch or whole-tree exception. The next promotion must be reviewed and merged
as its own governed transaction.

## Add-only delta proof

A delta still has exactly `path`, `before_sha256`, and `after_sha256`.
Existing replacements retain their before/after SHA-256 strings. An addition
uses JSON `null` for `before_sha256` only when the canonical, literal path is
absent from both the verified BASE commit tree and the active CURRENT governed
inventory. Empty strings, missing fields, lookup errors, unavailable commits,
directories, symlinks, gitlinks, and non-directory ancestors are not absence.
The source A entry must be a regular Git blob (`100644` or `100755`), and its
exact bytes must match the non-null `after_sha256`. Deletions are unsupported.

The lookup walks exact tree components with literal pathspecs, checking each
entry's mode and object type. BASE and A must resolve as the exact declared
commit/tree identities. Proposal validation, material verification, and the
in-memory `next_current` constructor all enforce addition proofs; the latter
accepts an explicit repository `root` for isolated fixtures and otherwise uses
this helper's repository. No CURRENT file is written by these checks.

The complete governed BASE-to-A changed-path set must still equal the declared
delta. Rename detection is disabled so a removed path cannot hide behind an
addition. Candidate source A, evidence overlay B, and proposal-only declaration
C retain their existing identity, lineage, evidence, and approval checks.
This bounded addition support does not authorize a promotion or relax any
Candidate/READY gate, including evidence that requires an available baseline
bundle. Missing baseline size evidence must remain blocked, not estimated.

## Anti-bypass coverage

`tests/test_proposed_baseline_lite.py` covers: missing/malformed CURRENT,
duplicate/stale current selection, governed-byte drift, historical predecessor
substitution, Candidate ID substitution, malformed/stale proposal, base-current
or base-main mismatch, malformed/duplicate delta, failed/skipped gate,
unbound evidence, inferred owner acceptance, branch-name injection, technical
green masquerading as owner acceptance, missing explicit owner reference, and
preservation of the prior CURRENT record during a prepared promotion.

Temporary Git BASE-to-A-to-B-to-C fixtures additionally cover regular and
executable additions, literal pathspec characters, unavailable/mismatched Git
identities, forged absence in either authority, invalid entry types and path
ancestors, malformed/null/duplicate delta fields, omitted changes, unsupported
deletions, exact binary-byte hashes, and in-memory successor construction
without CURRENT writes. These focused tests do not build or launch an app.

## Recovery #162 test accounting (classification only)

This branch does not modify Recovery code and does not create a Recovery
proposal. The existing #162 report's local full-suite line was corrected by
standard `unittest` accounting:

| Reported field | Evidence | Correct interpretation |
| --- | --- | --- |
| `646 run` | `Ran 646 tests` | total `testsRun`, including skips |
| `73 skipped` | runner summary | not successful tests |
| `3 failures`, `2 errors` | runner summary | not pass |
| `641 pass` | report text | invalid arithmetic; `646 - 73 - 3 - 2 = 568` successful tests at most |

The two errors were GUI/package-local checks (`test_macos_app` and
`test_ready_app`), and the three failures were the prior canonical-baseline
governance mismatch. They are retained as evidence, not hidden as green.

The mandatory Recovery gate ledger is therefore:

| Required gate | Evidence present | Classification |
| --- | --- | --- |
| controlled non-zero failure → retry | candidate-bound controlled probe cited by #162 | technically evidenced |
| timeout, stale RUNNING, startup reconciliation | `test_recovery_contract.py` on #162 | technically evidenced |
| cancellation and orphan cleanup | shutdown tests plus candidate-bound realistic cancellation/retry evidence | technically evidenced |
| subsequent successful run | candidate-bound realistic cancellation/retry evidence | technically evidenced |
| governed reuse and invalidation | all 12 `tests.test_asr_reuse` cases were skipped because the pinned SeminarText ASR runtime is unavailable; realistic retry only recorded `CREATED` | **not proven for the proposed candidate** |

The fresh read-only reproduction on the #162 worktree was `46 run, 17 skipped,
0 failures, 0 errors`: 12 skips were `Pinned SeminarText ASR runtime is
unavailable`; two further primary-ASR application cases had that same reason;
three VideoText media cases were skipped because `VideoText media runtime is
unavailable`. The shutdown/reconciliation cases were executed, rather than
skipped. The last row is mandatory. A skipped test is not a PASS and `CREATED` does not
prove reuse or invalidation. Thus Recovery #162 remains `BLOCKED` pending a
fresh reconciliation after this governance mechanism is merged and a
candidate-bound, non-skipped reuse/invalidation proof. It is neither promoted
nor USER_ACCEPTED here.

## Operator sequence after this Lite PR is merged

1. Rebase a product change onto the then-current `main`.
2. Build a fresh immutable candidate and preserve manifest, bundle validation,
   gate results, and exact source identity.
3. Add a strict PROPOSED record with every changed governed path and before/
   after SHA-256 values. Validate it to get only
   `PROPOSED_BASELINE_VALID / AWAITING_OWNER_ACCEPTANCE`.
4. Obtain an explicit, scoped human-owner acceptance reference. CI remains
   technical evidence only.
5. Run the promotion helper to prepare the next CURRENT record, review the
   exact transaction, and merge only under separately applicable repository
   authority.
