# R6 Core Alpha Certification

Status: `PASS`

Issue: [#8](https://github.com/Yurielo/integra/issues/8)

## Outcome

R6 implements and verifies the bounded local-video path:

`source -> transcript -> Topics -> exception-only review -> knowledge candidate -> media clip`

The certification combines two evidence layers. `CONTRACT_REPLAY` produces
immutable content-addressed artifacts, exact parent lineage, pinned identities,
deterministic manifests, cancellation checkpoints and fail-closed recovery.
`PINNED_REAL_MEDIA` executes pinned VideoText `0.6.4` and SeminarText `4.0.0`
code on a generated non-private 22.08-second Russian video. VideoText performs
FFmpeg/Whisper transcription and accurate clip rendering; SeminarText performs
local Topic inference, Canonical Evidence validation, exception-only review
preparation and provisional knowledge export.

Both evidence modes traverse the same `INTEGRA_CORE_ALPHA_V1` control plane.
For the real run, each of five adapter processes performs its source-component
operation only after an ordered R3 stdio JSONL handshake and job inside the
Core Alpha stage loop. The controller validates the existing job-staged result,
including schema, origin, ordered parents, operation ID, path, size and hash,
then atomically promotes those exact bytes. There is no post-hoc envelope or
second permanent persistence path.

## Cancellation and recovery

Cancellation occurs before a stage and writes an atomic checkpoint containing
the exact completed contiguous prefix and next stage. Resume fails closed unless
the source hash, project ID, component identities, R5 selections, artifact IDs,
origins, parent lineage, paths, sizes, and hashes still match. A concurrent
writer is rejected by the Project Lease; expiry alone does not recover a stale
lease under the accepted R2 contract.

R3 workers truthfully declare `supports_resume = false`; the verified recovery
is Core Alpha prefix resume between stages. Each process has an enforced
timeout, and a timeout kills its process group and yields an unretried unknown
outcome.

## Safety

- output store must be outside the Integra repository;
- symlinks in source and Integra-owned store paths are rejected before writes;
- source must be a non-empty regular local file and not a symlink;
- source applications are referenced by pinned identity and are not modified;
- actual adapter execution uses safe `git archive` materializations of the
  exact pinned commit rather than mutable `HEAD`; every extracted blob and
  executable bit is checked against the pinned Git tree and the resulting
  read-only tree is verified before and after every worker stage;
- source checkouts are snapshotted including ignored files before and after the
  run, and Python bytecode writes are disabled inside the SeminarText adapter;
- source materializations, builds, intermediate projects and exports use one
  disposable scratch root; only validated, content-addressed artifacts are
  promoted into the durable Integra control store;
- worker configuration and model content identities are hash-bound in the R3
  execution boundary and artifact origins, and active stages refresh the
  Project Lease at bounded intervals;
- protected data, Gold, credentials, external accounts, unapproved models, and
  publication are not accessed; the two approved pinned local model artifacts
  are invoked read-only and their exact content identities are recorded;
- semantic artifacts remain `PROVISIONAL` or `REVIEW_REQUIRED` and the run has
  `semantic_authority = PROVISIONAL_ONLY`; semantic status is persisted and
  contradictory payload-level lifecycle claims fail closed.

## Evidence

The dependency-free fixture
`tests/fixtures/core_alpha_v1/worker_outputs.json` is bound by SHA-256 in
`state/core_alpha_v1.json`. The implementation and tests prove replay
orchestration, ownership, cancellation, recovery, deterministic output, and
lineage validation.

The actual execution is recorded in `state/core_alpha_real_v1.json`, including
source, model, implementation and stage SHA-256 values, exact word/topic/clip
intervals, and the complete parent/operation lineage. Both the mutable Ollama
tag and its manifest/weights digests are bound. It records 37 native
non-zero Whisper word intervals. One native zero-duration token remains
unaligned (`word sequence 31`) rather than receiving fabricated timing. The
Canonical Evidence validator passed with that word explicitly review-required.
Two independent actual runs from one fixed implementation fingerprint produced
identical SHA-256 values for all six stages, including the rendered clip.
The JSON payloads were validated field-by-field down to word, Topic, review and
export-file records. The binary clip passed both the strict ISO-BMFF contract
and a functional ffprobe decode check; arbitrary non-empty bytes fail closed.

The pinned SeminarText CLI currently raises a `NameError` while writing its QA
report after successful Topic inference. The Integra adapter composes the same
pinned boundary, label and materialization functions without modifying the
SeminarText checkout; this limitation is explicit in the evidence record.

## Semantic boundary

VideoText stopped at `SOURCE_TRANSCRIPT` review. The transcript artifact has
semantic status `REVIEW_REQUIRED` while its evidence assurance remains
`MACHINE_UNVERIFIED`. SeminarText emitted one machine-assisted Topic as
`REVIEW_REQUIRED`; the review package has one
unreviewed item, and the knowledge artifact remains `PROVISIONAL`. No human
decision, protected dataset or Gold was used. R6 therefore proves technical
integration and exact provenance, not transcript accuracy, Topic quality or
semantic acceptance on representative user media. Source checkouts were clean
at their pinned commits before and after execution.
