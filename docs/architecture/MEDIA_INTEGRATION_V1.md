# Media Integration v1

Status: `ACCEPTED`

## Purpose

R9B exposes VideoText's accepted media capabilities through one closed Integra
recipe and derivative-output contract. VideoText remains a pinned read-only
worker at commit `2e098d1705b6815628bee1e023f4742718eabf02`; its standalone
repository and projects are not modified.

The v1 capabilities are clip extraction, subtitle rendering, translation,
TTS/dubbing, speed adjustment, static blur, watermarking, audio enhancement,
filler-word mute and media QA. Each recipe step records the exact VideoText
function name, expected VideoText artifact kind, source implementation path
and SHA-256, complete parameters, optional model identity and configuration
hash. Auxiliary inputs such as subtitle cues, translation/TTS text, watermark
image, transcript revision and filler analysis are exact ArtifactReferences;
their content hashes are part of both the recipe and execution plan. A recipe
is immutable and bound to the input artifact IDs and bytes, source locator,
operation ID, component commit/tree and source contracts.

## Operational boundary

Media execution is a `heavy-media` / `FFMPEG_HEAVY` job owned by the accepted
Operations & Diagnostics service. That service remains authoritative for
capability preflight, Project Lease-compatible resource reservation, playlist
serialization, monotonic progress, cancellation acknowledgement, checkpoint
revalidation, model residency and child-process cleanup. R9B does not create a
second scheduler or job lifecycle.

`media_operation_plan` supplies the exact job and resource request facts. Its
closed capability report is a content-addressed `INTEGRA_STORE` artifact from
the pinned VideoText origin and is a bound execution input. Function hashes
are explicitly `PINNED_CONTRACT`, not an invented availability measurement.
The local ffprobe executable and every recipe model are measured from regular
files; their byte identities are remeasured before output registration. The
report hash is the Operations preflight identity. Every model is addressed in
owner-scoped residency by its complete ID, version and content hash; the
recipe never treats a pre-existing user model as owned by Integra.

## Output acceptance

A derivative can be registered only after all of the following are true:

- the original source bytes and every auxiliary input still match their recipe
  ArtifactReference sizes and SHA-256 values in confined stores;
- the durable JobStore reports the same operation and capability as
  `SUCCEEDED`, with terminal progress complete;
- its final checkpoint binds the exact plan, capability report, pinned worker
  commit, all source/auxiliary input hashes, output hash and QA-artifact hash;
- the output is an `INTEGRA_STORE` artifact produced by the exact pinned
  VideoText component;
- provenance contains both the source artifact and recipe IDs;
- the output kind was actually requested by the recipe;
- Operations Integrity rereads both confined regular files and matches their
  sizes and SHA-256 values;
- a separate VideoText QA artifact binds the job, recipe, plan and exact output.
  Video outputs require the parseable output of `strictValidationReport`;
  audio requires parseable VideoText
  `validate` plus `duration`; SRT requires `parseWithReport` plus
  `validateTimeline`. Structural container parsing alone is never represented
  as functional media validation;
- registration independently runs the measured ffprobe over video/audio bytes,
  or independently parses the exact SRT bytes, and rejects even a fully
  rehashed QA report when observed output facts differ;
- every recipe-bound translation/TTS model has a durable owner-scoped
  `RELEASED` residency record for the same job and operation.

Cancellation, recovery and cleanup evidence are prerequisites of the durable
`SUCCEEDED` transition under Operations v1. The final checkpoint is a required
promotion barrier after worker QA, so a detached callback, generic successful
job or render exit code cannot register an output from another recipe.

## Authority and limitations

Recipes and derivative artifacts have `DERIVATIVE_ONLY` authority and
`semantic_status=NOT_APPLICABLE`. They cannot rewrite Canonical Evidence,
Canonical Knowledge, source transcripts, Topics, or ReviewDecisions.
Translation and TTS model identity are technical provenance, not semantic
acceptance.

R9B uses deterministic synthetic contract evidence plus a valid generated
audio fixture to verify binding and failure behavior. Arbitrary non-media bytes
cannot pass through a caller-authored probe string. Live functional acceptance
still requires both the content-addressed VideoText QA artifact and the
independent local output probe.
R9B does not render user media, access protected datasets or Gold, select a
model on semantic quality, publish externally, connect an account, or change
either source product. Live worker execution remains governed by R3/R6 and
Operations preflight.
