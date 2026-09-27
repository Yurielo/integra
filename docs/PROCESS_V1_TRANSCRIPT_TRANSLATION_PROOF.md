# Process V1 Transcript Translation Proof

Scope: Excel #18, S14 + V05 + V06 only. This proposal binds an ordinary
Process action that translates an already completed transcript from Russian to
English. It does not add target-language selection, translated TXT, topic
translation, routing changes, Stage B, Knowledge, Studio, installation, or
deployment.

## User journey

When a completed source has a timed transcript and SRT, the primary results
surface presents `Перевести`. The action creates a Process run with the fixed,
supported target `en`; it does not expose provider terminology. Completion
presents `Перевод` and opens readable cue text. The raw JSON and provenance
remain under technical data.

The execution validates source/target language, cue count, cue order, cue ID,
millisecond timing, output content, model identity and digest. Provider output
cannot silently substitute the target or runtime. A translation failure leaves
the already verified transcript and subtitles available and presents a
non-provider error.

## Candidate evidence

Candidate `candidate-v1-de25ee770d537b88eafd805249769e50694f7f5b56daab2f0771ec2c7706fd3d`
was built from source `7150d711f127a4aeaecf519c65b91f88fda64447` and its
manifest and bundle digest are bound in the evidence files. Its archive was
copied to permanent local retention and independently byte-verified.

The packaged E2E used a real Russian audio sample, first completed normal ASR,
then invoked the ordinary translation action after reopening that completed
result. The translation run recorded ASR reuse `REUSED`, source `ru`, target
`en`, one translated cue, the pinned VideoText commit
`2e098d1705b6815628bee1e023f4742718eabf02`, adapter digest, and `qwen3:8b`.
The translated output and Integra-owned provenance persisted successfully.

## Regression and limits

Focused translation, reuse, results-surface, capability, runtime and
application tests passed: 63 tests with 23 declared external-runtime skips.
Swift type checking and `git diff --check` passed. The broader suite's only
failures before this overlay were the expected fail-closed governance errors
for new, as-yet undeclared governed paths.

This is a machine translation marked review-required. It makes no semantic
acceptance claim and does not prove arbitrary language pairs, target selection,
translated TXT, topic translation, or provider substitutability.
