# Process V1 Translation-language Choice Proof

Scope: Excel #19 / V06 only. This proposal extends the accepted Transcript
translation result from Excel #18. It adds one normal Process control labelled
`Язык перевода`, carries that choice through the existing translation route,
and makes the persisted target visible in the completed result. It does not
create another translation engine or result model.

## Exact V06 semantics

The pinned worker accepts `--target` as an `ArtifactLanguage`. Its source
implementation supports only `ru` and `en`; the translation adapter rejects a
target equal to the source. Integra's accepted source-speech contract remains
Russian-only. Therefore the only valid user-visible target in this bounded
product state is `Английский`. The control is deliberately present and wired
through the ordinary route rather than pretending additional languages exist.

The existing English default remains unchanged. The selected target is part of
the plan identity and source plan, is passed to the spawned job and packaged
worker, and is validated against the worker result. The Integra-owned
provenance separately retains `requested_target_language` and
`executed_target_language`. A Russian target for a Russian source is rejected
before execution, with no fallback or mutation of the completed source.

## Candidate evidence

Candidate `candidate-v1-6545998b95e0f2d84abc7cd82baaea79bf8aa3c80cdd6d76840f47e87a42f996`
was built from source `df45022bd4dbd68ccc7a770e969418d35452bca3`. Its manifest
and permanent byte-verified archive are bound in the evidence files.

The packaged E2E started from a real, short Russian audio source whose normal
ASR result was already complete. The ordinary `translate-transcript` bridge
route created a fresh run with `en` selected, reused the timed transcript,
executed the pinned local worker, and persisted one English cue. The result
and provenance both say `ru` to `en`; requested and executed target are equal.
The provenance binds the pinned VideoText commit, adapter digest and `qwen3:8b`
runtime internally. The normal result card shows only Russian product wording.

## Regression and limits

Focused Process translation, Results UX, ASR reuse, Topic Review and
application regressions pass: 86 tests with 41 declared environment skips.
Native Swift type checking, Python bytecode compilation and diff validation
pass. The broad suite reaches its deliberate governance barrier until this
Candidate and its Proposal Lite are recorded; it reports only CURRENT byte
drift for the five changed governed files.

This is still machine translation marked review-required. It does not accept
semantic correctness, add translated TXT or translate topics. It also does not
alter normal ASR behavior, SeminarText, routing, Stage B, Knowledge or Studio.
