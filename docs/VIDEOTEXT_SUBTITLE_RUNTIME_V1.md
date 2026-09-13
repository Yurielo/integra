# VideoText subtitle runtime v1

Issue: #127. VideoText source remains unchanged at pinned commit
`2e098d1705b6815628bee1e023f4742718eabf02`.

Integra calls the original `SRTService` through its bundled Swift worker, not a
replacement Python subtitle parser. `scripts/build_videotext_worker.sh` checks
the clean pinned source and service SHA, compiles the worker, and emits the
binary/service identity manifest. The macOS build bundles both. No VideoText
checkout or Ollama is needed at runtime for subtitle operations.

## Contract and safety

`--subtitle-request` accepts a JSON file with `schema_version: "1.0"`,
`operation: normalize|clip|speed`, absolute `input_srt` and `output_srt`, and
optional `media_duration`, `start_seconds`, `end_seconds`, `speed_factor`.
The application-service boundary is `integra_core.videotext_subtitles.process`.
Speed limits are the component's 0.5–2 range. Clip output is rebased to zero.

SeminarText's unnumbered blocks receive transport cue IDs only. VideoText owns
timestamp parsing, validation and serialization. Empty, zero-duration, malformed,
overlapping or unsafe timelines fail closed. Written text and times are checked
against the expected cues (maximum rounding difference 0.000501 seconds).
Original source bytes remain unchanged; outputs cannot overwrite existing files.
The adapter verifies the component commit, service hash and worker hash, and
records source/output hashes in ASR provenance. No semantic acceptance occurs.

Translation also uses this parser with the same fail-closed timeline validation
before calling the existing translation component.

## Implementation matrix

| Source | Capability | Component / production path | Evidence | UI status |
|---|---|---|---|---|
| Audio/video | SRT after ASR | application runtime → SeminarText ASR adapter → VideoText subtitle adapter → pinned SRTService | Real worker normalization and source-first runtime tests | Existing SRT result; no new controls |
| SRT | Translation input validation | bundled worker → SRTService → TranslationAdapter | Invalid cue rejection before translation | Existing translation path; model still required |
| SRT | Clip/rebase and speed | subtitle adapter → pinned SRTService | Real worker clip/speed tests | Backend only; no additional UI capability claimed |

Focused tests: `python3 -m unittest tests.test_videotext_subtitles
tests.test_seminartext_asr_runtime -q`. Actual-worker tests require the built
worker; missing runtime is an explicit skip, not integration evidence.

## Verification on 2026-09-13

- Focused source-first/ASR/subtitle regression suite: 55 passed.
- Full macOS suite: 551 passed, no skips, 444.942 seconds. Includes native
  launch/close/icon probes and two reproducible signed application packages.
- Bundled adapter under `/usr/bin/python3`, outside the repository working
  directory: existing real SeminarText SRT normalized (5 cues), clipped to
  30 seconds (2 cues), speed-adjusted to 1.25 (5 cues). All outputs recognized
  by ffprobe as subrip; source hashes unchanged. No ASR rerun or private
  transcript committed.
- Independent review found timestamp overflow and translation zero-duration
  cue loss; both fixed with regressions verified red before, green after.
- One first bundled invocation exceeded the 30-second adapter timeout during
  concurrent packaging. Immediate subsequent normalization and full three-op
  smoke passed unchanged. Cause unconfirmed; timeout fails without promoting
  an output, and is not treated as success. This remains a cold-start limitation
  to monitor, not evidence of an always-successful first invocation.
- Source products unchanged; no external publishing or semantic acceptance.
