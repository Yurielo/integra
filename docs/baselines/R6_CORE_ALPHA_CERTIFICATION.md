# R6 Core Alpha Certification

Status: `PASS`

Issue: [#8](https://github.com/Yurielo/integra/issues/8)

## Outcome

R6 implements the bounded local-video control-plane path:

`source -> transcript -> Topics -> exception-only review -> knowledge candidate -> media clip`

The path produces immutable content-addressed artifacts, exact parent lineage,
pinned SeminarText and VideoText component identities, deterministic manifests,
and visible provisional semantic authority. Mutable project checkpoint and
manifest writes are guarded by the accepted Project Lease.
Stage-specific output contracts, component origins, operation IDs, semantic
status, and exact lineage are revalidated before a manifest is accepted.

## Cancellation and recovery

Cancellation occurs before a stage and writes an atomic checkpoint containing
the exact completed contiguous prefix and next stage. Resume fails closed unless
the source hash, project ID, component identities, R5 selections, artifact IDs,
origins, parent lineage, paths, sizes, and hashes still match. A concurrent
writer is rejected by the Project Lease; expiry alone does not recover a stale
lease under the accepted R2 contract.

## Safety

- output store must be outside the Integra repository;
- symlinks in source and Integra-owned store paths are rejected before writes;
- source must be a non-empty regular local file and not a symlink;
- source applications are referenced by pinned identity and are not modified;
- protected data, Gold, credentials, models, external accounts, and publication
  are not accessed;
- semantic artifacts remain `PROVISIONAL` or `REVIEW_REQUIRED` and the run has
  `semantic_authority = PROVISIONAL_ONLY`; semantic status is persisted and
  contradictory payload-level lifecycle claims fail closed.

## Evidence and limit

The dependency-free fixture
`tests/fixtures/core_alpha_v1/worker_outputs.json` is bound by SHA-256 in
`state/core_alpha_v1.json`. The implementation and tests prove orchestration,
ownership, cancellation, recovery, deterministic output, and provenance.

This is explicitly `CONTRACT_REPLAY`. It does not claim that ASR, Topic
semantics, knowledge semantics, or media rendering ran on real media in R6.
Those remain later integration and release acceptance layers with authorized
inputs. This limitation prevents replay evidence from being misrepresented as
model or product-quality evidence.
