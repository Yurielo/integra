# Issue #227 — Candidate Proposal protection binding

The pre-owner transaction had a mutable-reference cycle: canonical protection
required an open Proposal PR's exact head SHA, while syncing that PR with the
new canonical protection commit necessarily changed its head. That prevented
the same immutable Candidate from reaching its Owner handoff even when the
Candidate-bound Proposal itself was unchanged.

New protection records may bind the exact SHA-256 of
`state/proposed_baseline_lite_v1.json`, its Proposal ID, and the exact
Candidate/Bundle/Manifest tuple. The audit still requires the referenced PR to
be open against `main`, requires the file digest and Candidate tuple to match,
and keeps legacy exact-head records strict. A moved PR head therefore does not
permit a different Proposal or Candidate to inherit protection.

This record is for the existing Issue #227 K2 Candidate only:

- PR #256, head when this stable binding was prepared `2e639625480eb15de57aea285eb583de0d8c6973`
- Proposal `proposal-knowledge-k2-canonical-knowledge-from-reviewed-fragments-v3`
- Proposal file SHA-256 `05d81bb459bc0d222766f83c6e40420666a51ba2d026f5ca843127d5c165b85d`
- Candidate `candidate-v1-0f69e617c0841f27afe2238a28d6c25ae5a80ce0fedf01cf0c114638de575032`
- Bundle `3d4d33a983455572157b06460c3faaef5afd0b977a0e3d2717101588a25718e5`
- Manifest `3aed49cda900a6af0d0e8abcae4f3db114d988ad9bf16c62c53ba6671d06cbfe`

No Candidate, CURRENT, Process Board, semantic decision, or runtime bytes are
changed by this binding.
