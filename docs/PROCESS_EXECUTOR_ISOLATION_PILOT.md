# Process executor isolation pilot

Issue #190 / PR #191. Exact Product Owner instruction, 2026-09-26.
Target: `MIGRATE_TO_INTEGRA_PROCESS_RUNTIME`.

The earlier isolated whole-VideoText ASR carrier is superseded, not certified.
Its additions are removed from this PR; historical commits remain available.
No normal Process route, source component, pin, Board outcome or CURRENT is
changed. This is one isolated capability, not Stage B or Process v1 acceptance.

## Capability and representative value

`process.timed_transcript.normalize.v1` validates and serializes an existing
timed transcript. The SRT interoperability boundary is a documented current
integration problem and feeds transcript/alignment/translation/topics. A
deterministic artifact operation provides independent expectations for request
binding, internal executor dispatch, provenance, failure and publication.

The pilot does not repair the normal SRT route. It does not prove ASR quality,
model lifecycle/retry, semantic Topics parity, every NOT_DONE integration, or
general provider substitutability. SRT is an internal Process artifact here,
not a Studio subtitle-export feature.

## Astra design checkpoint before implementation

The dedicated `gpt-6-astra` agent reviewed the selected capability, contract,
fixed dispatch, provider adapter, proof strategy, write scope and stop criteria
before product code was written. Verdict: VALID for bounded implementation,
subject to the following incorporated conditions:

- Integra specifies strict grammar and duration bounds; provider acceptance
  alone is insufficient. Integra validates outputs rather than replacing the
  provider's normalization algorithm.
- Cue labels are positional ordinals, not stable source cue identifiers.
- Effective options and all identity fields enter the request hash; execution
  attempt identity remains separate.
- Failure/cancellation/timeout produce a terminal neutral record and no output
  artifact. Partial files remain private and are discarded.
- Atomic directory publication exposes output and matching success record
  together. Cancellation observed before the commit decision prevents success;
  after committed completion it cannot rewrite the terminal record.
- Descriptive project/source IDs do not grant access to canonical project data.
- The actual executable is verified against the Candidate manifest and its
  bundle, not just an adjacent self-consistent runtime manifest.
- Sharing the existing broadly compiled executable proves invocation/contract
  isolation, not minimal linked dependency closure or bundle size reduction.

Astra judged this representative for a deterministic artifact transformation,
not too trivial. Importing another product workflow, leaking provider semantics,
requiring production routing/state changes or weakened identity checks would
falsify the bounded design. No broad architecture redesign was requested.

## Neutral contract

`integra_core.process_executor_pilot.execute` accepts this exact request:

```json
{
  "schema_version": "1.0",
  "capability_id": "process.timed_transcript.normalize.v1",
  "project_id": "pilot-project",
  "run_id": "pilot-run",
  "source": {"source_id": "fixture-source", "revision": "1"},
  "input": {"artifact_id": "fixture-transcript", "sha256": "<64 lowercase hex>", "format": "srt"},
  "options": {"media_duration_ms": 301250}
}
```

Unknown fields/options/capabilities are rejected. IDs are bounded opaque strings,
not paths. Omitted duration within `options` is canonically expanded to null;
otherwise duration is a positive integer in milliseconds. Canonical JSON uses
sorted keys, UTF-8, compact separators, no non-finite numbers. Its SHA-256 binds
all effective fields. No source model/config is invented: this capability has
no model and does not verify a caller's canonical media record. It verifies the
explicit input artifact bytes and their declared source/revision linkage.

Infrastructure separately supplies the explicit input file and Candidate
Resources path. There is no project directory argument, output destination,
provider selector, plugin registry or environment override for dispatch.
Each invocation creates a fresh owned OS-temporary attempt; identical requests
may produce identical normalized bytes but never overwrite a previous attempt.

Input grammar: UTF-8, LF/CRLF, 2–6 digit nonnegative hours, minutes/seconds
00–59, exactly three millisecond digits, exact ` --> ` separator. Cue labels
are either all absent or positive strictly increasing integers. Mixed labels,
zero duration, overlap, empty text, malformed timestamps, NUL and input over
1 MiB/10,000 cues fail. Outer cue-text whitespace is trimmed, internal multiline
text is preserved. Output labels are 1..N. Supplied duration is an exact upper
bound; the provider's one-second tolerance is not inherited. The input and
every old artifact retain their original bytes and labels.

Public result contains schema/capability, request hash, attempt ID,
project/run/source identities after validation, status, stable neutral
error code/Russian message, `semantic_authority: MACHINE_UNVERIFIED` and
artifacts. Each successful artifact has content ID/hash/byte count, relative
`transcript.srt` path, cue count, `POSITIONAL_ORDINALS` labels and input lineage.
Terminal statuses: COMPLETED, FAILED, CANCELLED, TIMED_OUT. Errors have an empty
artifact inventory. No raw provider exception, CLI vocabulary, branding or
provider layout is copied into this result.

Publication errors discard the unpublished success and retry only a failure
record. If storage remains unavailable, the returned in-memory result is FAILED
with no artifacts; private evidence explicitly marks persistence failure. This
does not claim durable recording when the filesystem cannot accept writes.

The returned infrastructure envelope additionally contains private evidence
and the isolated attempt location. Evidence records normalized request/hash,
executor/adapter implementation hashes, provider commit/service/actual worker
hash, Candidate ID/bundle digest and output hash. It is not the normal result
surface and does not grant semantic approval.

## Executor and private provider

Exactly one fixed dispatch exists: `execute` -> `_timed_transcript_provider`.
The private adapter invokes the existing pinned packaged worker's normalize
operation. Provider-specific paths, CLI fields, metadata and errors terminate
there. Existing Python subtitle adapter, native shared worker and build script
remain unchanged.

Provider pin: `2e098d1705b6815628bee1e023f4742718eabf02`.
SRTService SHA-256:
`417017a6a3becc395e88e2554e8d7c2dca51b09de9743e8c5c0cf81ac9ba6205`.
Runtime location: Candidate `Contents/Resources/runtime/videotext/translation-worker`.
The Candidate manifest binds the actual binary and all bundled bytes; private
preflight verifies it before launch and rechecks the executable after execution.
Executor/adapter hashes record whether execution was from source or packaged
code; only packaged proof can certify the revised Candidate.

The provider normalizer launches no ffmpeg, Whisper, Ollama or SeminarText
operation. Its executable nevertheless contains other existing functionality;
this pilot neither removes it nor adds a duplicate provider binary/library/model.
Semantic algorithms and product runtime pins are not changed.

The adapter has finite timeout, bounded captured stdout/stderr and artifact
size checks, cancellation after launch, and existing Integra owned-tree cleanup
for a live worker. The supplied trusted normalizer does not spawn children.
Fault-process tests are identified separately and do not establish cleanup for
arbitrary model process topologies. This is a trusted-provider isolation boundary,
not an OS sandbox defending against a malicious executable.

## Validation and release boundary

- Independent hand-written expected bytes/failures, not only differential parity.
- Differential comparison against the existing normalizer in separate temporary
  artifacts using the exact same packaged worker.
- Request/hash/grammar/metadata/output/drift/symlink/unknown-field negatives.
- Post-launch cancellation, timeout, output-limit cleanup, unrelated-process
  preservation and later successful attempt, using explicitly fault-injected workers.
- Production route/import source equality and relevant regression evidence.
- One clean revised Candidate only after implementation/focused validation;
  no old Stage A Candidate reuse. Source A -> evidence overlay B -> declaration C.
- Governance all added paths accounted; no CURRENT mutation, promotion or merge.

Stop on protected-source edits, production switching, many-DONE migration,
user-visible provider choice, generic plugins, destructive persistence changes,
Stage B, weakened Candidate identity, uncontained writes or incomplete cleanup.
Missing exact canonical bundle size evidence blocks READY; an alternate bundle
measurement must not be labelled CURRENT or replaced by a source-tree estimate.

The Product Owner's next decision, when all gates are ready, concerns only the
isolated pilot/proposed baseline. It cannot authorize normal routing, another
capability, Stage B or source-product retirement by implication.
