# VideoText Process Stage A Runtime

Issue: [#190](https://github.com/Yurielo/integra/issues/190)

Stage A is a deliberately isolated proof runtime. It does not change the
production Process path, `user_media`, `asr_reuse`, Candidate state, Board,
Gold, or any user project.

## Source identity

The only accepted source is a clean VideoText checkout at
`c4d851c9b39b2aeb696a12aa357d1ae0df350cd3` (VideoText 0.6.8). The build script
requires its path explicitly through `INTEGRA_VIDEOTEXT_STAGE_A_CHECKOUT`,
checks its Git cleanliness and hashes the transcription and quality adapters.
The generated `runtime.json` records those checks, the worker digest, and
`seminartext_dependency: false`.

## Request and result

`videotext-stage-a-worker --stage-a-request request.json` accepts only a
versioned request with absolute paths to an owned media copy, empty owned
project directory, local Whisper model and Russian language. The worker runs
only VideoText's transcription plus transcription-quality checkpoint. It
returns one result marker for the fixed artifacts:

- `Texts/full.srt`
- `Texts/transcript.txt`
- `Support files/whisper.json`
- `Support files/manifest.json`
- `Support files/Quality/transcription_quality.json`
- `Support files/Review/review_tasks.json`

The Python adapter validates the native runtime identity, takes a private copy
of the source, provides only explicitly supplied `ffmpeg`, `ffprobe` and
`whisper-cli` through a private `PATH`, removes inherited `SEMINARTEXT_*`
settings, confines returned paths, rejects malformed/overlapping SRT cues, and
records content hashes. A valid source-transcript checkpoint remains
`MACHINE_UNVERIFIED` and `REVIEW_REQUIRED`; it is not a ProcessedSource claim.

## Cold and warm behavior

The first run uses a new owned directory. A later result can be reused only
when the source, model, tools, runtime manifest and language hash to the same
key and every cached artifact still exists under the owned root with its
recorded digest. Failed, cancelled, malformed or escaped results are never
cached. The adapter has a finite timeout and terminates its own process group.

## Deliberate boundaries

This proof does not run a user video, does not look at old SeminarText cache,
and does not analyze topics. Cue-to-time mapping is preserved in `full.srt` for
the later topic compatibility probe, but Stage A does not yet convert it to a
Process result projection. Promotion requires the remaining Issue #190 evidence
and the later Process acceptance gate.
