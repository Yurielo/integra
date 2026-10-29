# Issue #304 — Seminar Library native GUI candidate for PR #305

## Scope and governance

Read-only AppKit Seminar Library preview using the existing catalog engine and schema. Explicit session-only selection of manifests for SeminarText, VideoText, BookText, and Integra. No automatic discovery, semantic merging, source modification, installation, activation, or production promotion. Candidate source is clean commit `827f1531374ab38c73612ccafe84515a716fac88` (tree `869d979b7f0ff0b2ea4d8412b5271b8d335adfda`). Active CURRENT v2 remains `current-v2-1b29ea21cb9dbab3c423b5770f6f2eb972bb6dcdfbbb694b7a19a0c9db9fc434`. Owner acceptance and promotion are pending.

## Issue #312 exact archive recovery

The 25 added `.pyc` files and their five resulting empty `__pycache__` directories were the sole deletions from the affected managed archive. The files were preserved outside the managed archive at `/Users/yurielokhin/Documents/integra-issue-312-preserved-bytecode-073396d` with their original paths and SHA-256 in `issue312-preservation-manifest.json`. The original inventory SHA-256 `7f21559a79e644ddcd23417344a5b000fd1f9c79fd5c33827bb6ff06a318607d` and COMPLETE SHA-256 `70dd0501b3d24bcb4deeee3490296e62f5c47c2d4c612c54d41f8330de2f6daa` were unchanged. Full archive verification passed. See `issue312-recovery-result.json`.

## Automatic eight-build rotation

The managed catalog records the eight-copy order in `rotation_order_v2`. Legacy copies use observed APFS directory creation time solely as order evidence; this is not a confirmed publication timestamp. New copies use lifecycle publication timestamps. Candidate ID breaks ties deterministically. The oldest legacy copy `candidate-v1-14b3c10e4d779ff8b5a520bf15e2b7087673aec2cd0abd25aac4e1d0ded77892` was retired with transaction `rotation-v2-3456cb579bb04874b4c023c1da0fbb4f`, before the new Candidate was published. The receipt is `rotation-receipt.json`; the recorded order is `rotation-order-v2.json`.

## Candidate and checks

Candidate `candidate-v1-9a009cecd86aeb72550e7ecdbf820a3d7683a7ccf830c20143a3f04c0c976144` has bundle digest `3b20a60744a8a20ff856778df0e1ea250da735a49ae6ec35f3b02cdf6ad9f5fe` and manifest SHA-256 `249bffca02a71e08ee3e23bf3ba0d4524416180a7a12546c732ca90678d1668c`. It is retained in the managed Build Archive with status COMPLETE; verification reports 29,612 inventory files and `ARCHIVAL_BYTE_INTEGRITY`. No runtime validation or Owner acceptance is implied by archival verification.

The focused Seminar Library tests passed (13 tests). The migration compatibility tests passed (11 tests) using `jsonschema` installed in a temporary test-only path outside the repository. The native macOS test passed, including bundled resources, native project detail rendering, launch/close, and existing workflows. Logs and archive receipt are in this evidence directory. The full Python suite and governance/Quality Gate must be rerun after the Proposal declaration commit, because CURRENT v2 requires the Candidate-bound Proposal to explain the governed GUI byte changes.

## Owner test boundary

Open the archived `Integra.app` only for explicit Owner testing. Do not replace the installed application, activate production, merge PR #305, or promote CURRENT until the required Owner acceptance and lifecycle checks are completed.
