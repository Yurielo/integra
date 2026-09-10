# Operations & Diagnostics v1

Status: `ACCEPTED`

## Purpose

This control-plane layer owns operational facts for Integra jobs. It is
additive to the accepted R2 Project Lease, R3 worker protocol, and R6 Core
Alpha contracts. Worker messages are evidence; `JobStore` is the sole durable
job-lifecycle authority. A host resource reservation is not a Project Lease.

## Job lifecycle

Every job has versioned job, operation and capability identity, an optimistic
revision, append-only transition history, monotonic progress, explicit
`ESTIMATED` or `UNKNOWN` ETA, cancellation request/acknowledgement, checkpoint,
resume scope and terminal outcome.

The normal path is:

`QUEUED -> PREFLIGHT -> WAITING_RESOURCES -> RUNNING -> SUCCEEDED`

Pause/resume uses:

`RUNNING -> PAUSE_REQUESTED -> PAUSED -> RESUMING -> PREFLIGHT`

A controller restart moves an observed running job to `RECOVERY_REQUIRED`; it
never guesses success. Recovery must then pass through `RESUMING`, revalidate
the checkpoint, job, operation, capability, input, worker, capability-report
and configuration binding and repeat preflight before any execution.
`UNKNOWN_OUTCOME` is terminal and non-retryable until a separate verified
recovery establishes that continuation is safe. R6 workers remain
`supports_resume=false`; Core Alpha may use only `PIPELINE_PREFIX` resume.
Terminal records are immutable.

`SUCCEEDED` is recorded last and requires exact proof that outputs were
promoted, Integrity passed, Project Lease and resource reservation were
released, and no owned live child remains. Terminal transitions reread the
canonical durable LeaseStore and ResourceReservationStore; detached caller
snapshots are not completion evidence, and only `INTEGRA_STORE` artifacts can
prove promotion.

## Capability preflight

Preflight compares the requested capability against exact worker, component,
model, runtime, source, target and schema-contract identities before execution.
The reference probe measures regular-file hashes for the worker, model, source
and contract, hashes the exact runtime executable and version-probe arguments,
executes that no-shell probe, and verifies target availability instead of
accepting caller assertions. A different executable that prints the same
version is runtime drift. Missing, unknown or changed facts block execution.
Resume repeats preflight and revalidates the complete checkpoint execution identity.
`WAITING_RESOURCES` and `RUNNING` are reachable only through the measured
preflight and active-reservation methods; a syntactically valid evidence hash
cannot bypass either gate.

## Resource Scheduler

The accepted classes are `lightweight`, `heavy-model`, and `heavy-media`.
Admission and host reservation occur under one exclusive file lock.

On the 16 GB reference Mac:

- at most one heavy-model and one heavy-media operation may be active;
- Whisper and Ollama do not overlap by default;
- heavy FFmpeg and Whisper do not overlap by default;
- items from the same playlist collection run sequentially;
- unknown/unsafe memory pressure, swap, workspace/device, loaded-model,
  child-process, lease or required publication-target truth blocks admission;
- required disk is the exact sum of source, extracted audio, cache,
  intermediate media, final output and safety margin; this calculated value,
  rather than a fixed free-space threshold, decides admission.

Reservation ownership uses canonical job, operation and reservation URNs plus
PID and process-start token. Admission rereads the durable waiting Job and
active Project Lease, requires matching operation, preflight, job class, host,
PID and start token plus an unexpired lease at the admission instant, and only
then records the reservation. A job or operation may have only one active host
reservation. Terminal paths also
search the durable reservation store by job, closing the interval between
reservation creation and the later `start_reserved` job link; a live or
ambiguous reservation can never be treated as cleanup-free. Recovery
requires `NOT_RUNNING` process truth and a terminal or `RECOVERY_REQUIRED` job.
The reference snapshot obtains host facts from macOS process, memory, swap and
filesystem probes. Canonical workload, model-family and collection-kind values
are closed enums, so alternate spelling or casing cannot bypass exclusions.
The reservation store invokes its configured host probe itself. Missing Project
Lease truth is `UNKNOWN`, and an active lease is accepted only when it is
unexpired and its operation, host, PID and process-start token match the
isolated worker process.

## Diagnostics, logging and Integrity

Persisted log events allowlist operational identities, states, codes, hashes
and sizes. State, classification and reason values use finite operational
vocabularies; artifact IDs are canonical URNs and component/capability IDs use
registered product prefixes. Other single-token values are redacted.
Credentials, authorization, cookies, personal/private content,
paths, argv, environment, stdout, stderr and unknown detail fields are redacted
by default. Job and operation correlation remains visible.

Integrity validates the exact artifact reference, confined path, regular
single-linked file, COMPLETE state, size and SHA-256. Missing, escaped,
symlinked, hard-linked, partial, shortened or altered artifacts fail. Integrity
failure prevents terminal success. Verification uses no-follow descriptor
traversal, rejects staging paths and checks metadata stability while hashing.

Child shutdown owns the process group, escalates TERM to KILL when necessary,
reaps the worker and verifies the group is gone. Model unloading is permitted
only for a durable residency record acquired by the same job and operation;
pre-existing user models are not unloaded and release is recorded only after
absence is observed through the proof-bearing owner-scoped unload path. A
failed observation or durable write after model load
triggers owner-scoped unload. The store persists `LOADING` before invoking the
loader and retains `RECOVERY_REQUIRED` ownership whenever rollback absence
cannot be verified, so an uncertain model can never become an ownerless fact.

## Scope and evidence

Issue #46 uses deterministic synthetic fixtures only. It performs no live
publication, credential/account access, protected/private data access,
semantic decision, source-repository change or release. Governed fixtures cover
success, interruption, resume, unsafe resources, capability drift, Integrity
failure and process cleanup. Governance executes the seven fixtures as
behavioral checks and binds their hashes; inventory alone is not acceptance.
