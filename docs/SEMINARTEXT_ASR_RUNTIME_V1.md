# SeminarText ASR runtime v1 — issue #125

Authority: explicit Product Owner request to integrate SeminarText transcription
after a legacy Integra result contained runaway repetitions. This selects the
SeminarText production ASR path for native user-media processing; historical R5
benchmark ownership remains historical evidence, not a description of this path.

## Actual implementation

The pinned `seminartext` Bash CLI at commit
`970bde598ddd649599295139986933e0e06cb9c0` is executed unchanged through
`project-transcribe` against an isolated Integra-owned project. The CLI and
`SEMINARTEXT_VERSION` are copied into the macOS bundle only after SHA-256 checks.
No SeminarText source checkout or user project is modified.

The real upstream implementation supplies:

- `process_record`: 300-second audio chunks and independent recognition calls;
- `run_whisper_piece`: Russian recognition, existing domain prompt, Silero VAD,
  bounded retries with stricter VAD and no initial prompt;
- `quality_check`: repetitive sentence/tail/word detection;
- `merge_srt_with_offset`: source-relative subtitle intervals;
- `clean_text`: separate cleaned derivative and review report.

This replaces Integra's former whole-recording `whisper-cli -l auto` call.
The adapter does not reimplement these algorithms in Python or Swift.

## Contract and safety

UI → application runtime → user-media service → SeminarText ASR adapter →
verified bundled CLI → local ffmpeg / whisper-cli / model.

Each invocation gets a new owned workspace. Source bytes are read-only. The
adapter validates runtime identity, tools, model inputs and output files,
records provenance, and owns the subprocess group for cancellation. Progress
contains processing stages/chunk counts, never recognised private text.

The aligned machine TXT/JSON and SRT retain the upstream timed wording.
`transcript_cleaned` is explicitly a derivative: upstream cleanup may remove
repetitions and replace terminology, so it is NOT silently substituted into
Evidence or word alignment. No transcript is labelled human-verified.

The source CLI's merged SRT omits numeric cue identifiers. The adapter retains
that original and supplies cue identifiers to the pinned VideoText SRTService.
VideoText parses, validates and writes the separate interoperable SRT; Integra
checks text and millisecond timing round-trip before accepting it. Downstream
media uses this normalized file. See VIDEOTEXT_SUBTITLE_RUNTIME_V1.md.

Upstream can return exit 0 while reporting suspicious chunks. Integra must
treat that as a failed quality check, retain the report and provenance, and
stop downstream topic/alignment processing. Exit 0 alone is not quality proof.
Passing heuristics is likewise not a claim of verbatim human-verified accuracy.

## UI implementation matrix

| Source | Capability | Component/runtime | UI result |
| --- | --- | --- | --- |
| Local audio/video; owned downloaded media | TXT/SRT | application runtime → pinned SeminarText CLI | Real timed machine text and SRT |
| Same | Cleaned text | upstream `clean_text` | Explicitly labelled derivative |
| Same | Quality report | upstream checks + fail-closed adapter | Report available; unresolved failure cannot be completed |
| Same | Cancellation | Integra-owned process group | Stops owned recognition processes |

## Limitations

The pinned profile is Russian and contains a domain-specific prompt. This task
does not claim equivalent quality for other languages or change that prompt.
Whisper, ffmpeg, and local model dependencies still require successful preflight.
Silero VAD uses the verified existing `ggml-silero-v5.1.2.bin`. Source-repository
changes, model training, canonical semantic acceptance, and full reprocessing of
old user projects are outside this integration. Existing results are preserved;
the new runtime does not silently rewrite historical transcripts.

Applicable source Product Rules: PR-002, PR-008, PR-010, PR-012, PR-013.
No source Product Rule is changed.

## Verification

The focused suite covers the real pinned CLI with test-only media executables:
repetition triggers retry without prompt, persistent repetition fails quality,
raw/derived separation, pin integrity, and cancellation. A real bridge test
checks that even a nested Whisper child ignoring SIGTERM is terminated and the
final run stays CANCELLED. Native failed-report access is regression-checked.

A separate real-model smoke processed a 65-second excerpt around the reported
legacy failure, first through the adapter and then through the clean-built
application's own bridge with `/usr/bin/python3` and no source-checkout override.
TXT, SRT, derivative, review report and provenance were produced; the runaway
phrase no longer filled the excerpt. This is bounded integration evidence,
not a claim that the complete original recording has been reprocessed or that
the transcript has been human-verified. Private audio/text are not committed.
