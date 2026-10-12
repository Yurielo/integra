# Issue #227 — exact K2 Candidate protection registration

This governance-only registration binds the exact open Proposal Lite in PR #256 to its already-published immutable K2 Candidate archive.

- PR: #256
- exact PR head: `3afd77f1d94d409265c6d03d5adb002a8ebce357`
- Candidate: `candidate-v1-0f69e617c0841f27afe2238a28d6c25ae5a80ce0fedf01cf0c114638de575032`
- Bundle: `3d4d33a983455572157b06460c3faaef5afd0b977a0e3d2717101588a25718e5`
- Manifest: `3aed49cda900a6af0d0e8abcae4f3db114d988ad9bf16c62c53ba6671d06cbfe`
- exact selected survivor: `Build Archive/candidate-v1-0f69e617c0841f27afe2238a28d6c25ae5a80ce0fedf01cf0c114638de575032/3d4d33a983455572157b06460c3faaef5afd0b977a0e3d2717101588a25718e5`

The Candidate already exists as a complete verified archive. This PR only registers its exact PR/Proposal identity and local survivor path in the canonical protection registry. It does not build, copy, modify, accept, promote, delete, or merge PR #256; it does not change CURRENT or the Process Board. Its purpose is the existing Candidate protection transition required before the Candidate can enter the real Owner handoff.

The registration is valid only while PR #256 remains open at the exact head above and its Proposal Lite and Candidate manifest bind the same identity tuple. Any PR-head drift, Proposal substitution, missing/incomplete archive, or identity mismatch must fail closed.
