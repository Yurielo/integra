# R4 Minimal Adapter Spike Certification

Status: `PASS`

Verified: 2026-09-10

## Outcome

The isolated Integra adapter invoked one bounded capability from each pinned
source component through the accepted R3 JSONL contract:

- SeminarText `a94936c`: Canonical Evidence v1 validation;
- VideoText `2e098d1`: legacy project manifest migration and Project Schema v7
  probe.

Each run completed the same contract sequence:

`HANDSHAKE_REQUEST → HANDSHAKE_RESPONSE → JOB_REQUEST → PROGRESS → PROGRESS → RESULT`

Inputs were hash-verified `SOURCE_READ_ONLY` artifacts. Reports were written
atomically to directories outside the source checkouts and referenced by
SHA-256. Source HEAD, tree SHA, and clean status were identical before and
after each invocation.

## Safety evidence

- Both sources were fresh temporary checkouts at the exact R1 commits.
- No source repository or user project was modified.
- VideoText compilation output and both adapter reports stayed outside the
  source checkout.
- No private data, credential, live account, network service, semantic
  decision, publication, migration, or deployment was used.
- Raw worker output is not copied into protocol errors; only hashes, byte
  counts, exit status, and elapsed time are retained.

## Failure behavior

Dependency-free tests prove cancellation acknowledgement, bounded timeout as
`UNKNOWN_OUTCOME` with retry denied, structured non-zero-exit reporting,
unknown-capability rejection, pin/hash mismatch rejection, dirty-source
rejection, and output-path isolation.

The exact machine-readable evidence, hashes, runtimes, and message sequences
are in `state/adapter_spike_v1.json`. Runtime report files are not committed;
their content and protocol-stream hashes are pinned in that record.

## Scope boundary

R4 establishes the adapter boundary only. It does not select the winning
implementation for overlapping capabilities; that comparison belongs to R5.
It does not migrate projects or replace either standalone application.
