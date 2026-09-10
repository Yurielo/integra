# Integra Local Worker and Artifact Contract v1

Status: `R3_ACCEPTED`

## Purpose

The v1 boundary lets the Integra control plane invoke pinned SeminarText and
VideoText capabilities without importing their internal paths or taking
ownership of their projects. The transport is a controlled local process using
one UTF-8 JSON object per line over standard input/output. No network service
is required.

The normative machine-readable registry is `state/worker_protocol_v1.json`.
Messages, artifact references, and component identities are defined by the
three R3 schemas in `schemas/` and checked by `integra_core.protocol`.

## Handshake and compatibility

The controller and worker exchange exact supported protocol versions and
select the highest exact intersection. A worker declares versioned
capabilities, input/output schema IDs, resume support, its Git commit/tree,
runtime, contracts, and any model hashes. Unknown protocol or schema versions
fail closed; compatibility is never inferred from similar version numbers.

## Jobs and lifecycle

Each job carries stable job and operation IDs, a SHA-256 idempotency key,
capability, positive timeout, and hashed artifact references. Reuse of an
idempotency key with the same canonical request is a replay; reuse with a
different request is a hard conflict.

Progress sequence and completion fraction are monotonic. Result, error, and
cancellation acknowledgement are terminal. Retryable errors include a delay;
unknown outcomes are never retried automatically. Cancellation is complete
only after an explicit acknowledgement.

A resume token is opaque and time-bounded. Its binding hashes the job ID,
capability, pinned worker commit, and ordered input hashes. Possession of a
token does not override protocol, artifact, lease, or component validation.

## Artifact and write safety

Artifact references use stable Integra URNs, exact schema versions, byte
length, SHA-256 content identity, normalized relative paths, origin component
identity, and parent/operation provenance. Source artifacts remain
`SOURCE_READ_ONLY`; Integra-owned artifacts use `INTEGRA_STORE`.

A job that names a mutable entity must carry a Project Lease ID, positive
generation, and artifact-precondition hash. R3 does not itself acquire or
recover a lease and does not permit a second writer. Completed writes are
staged and atomically promoted by the later control-plane implementation.

## Scenario evidence

Committed fixtures cover a successful job, acknowledged cancellation,
classified retry, incompatible handshake, and multi-parent provenance. Tests
also prove non-monotonic progress, unsafe retry, changed-request idempotency,
invalid resume binding inputs, path traversal, and unleased mutation fail
closed.

## R6 operational use

The `PINNED_REAL_MEDIA` Core Alpha path uses one local adapter subprocess per
stage. The controller completes the handshake before submitting the job; the
adapter then executes the pinned source capability and returns progress plus a
terminal result. A result must reference an existing regular file inside the
job-specific `.staging` directory. The controller verifies the exact bytes and
provenance before Core Alpha performs the only permanent atomic promotion.

These bounded adapters declare `supports_resume = false`. Core Alpha's
checkpointed prefix resume is a separate controller capability, not an
intra-job worker resume claim. A stage timeout terminates the adapter process
group and is not retried as a known-safe outcome.

## Scope boundary

R3 defines contracts and a dependency-free reference validator only. It does
not start workers, expose a service, mutate either source repository, migrate a
project, process private data, choose competing implementations, or publish an
artifact.
