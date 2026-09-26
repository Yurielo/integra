# Process v1: Careful ASR mode proof

Date: 2026-09-27. Status: `PROPOSED_BASELINE_VALID / AWAITING_OWNER_ACCEPTANCE`.

This is bounded evidence for Excel row 11 / S04, **Careful ASR mode**. It does
not promote `CURRENT`, switch canonical Process routing, select VideoText as the
ASR provider, retire SeminarText, start Stage B, install an application, or
constitute `PROCESS V1 USER_ACCEPTED`.

## Delivered behaviour

For local-media and YouTube-media transcription, Integra exposes only neutral
user-facing choices: `Обычный` and `Тщательный`. `Обычный` remains the default.
The selected value is carried from the native GUI through the bridge and Process
run into every source job. A completed result records both requested and
executed mode and retains ASR provenance/runtime identity. ASR reuse includes
the mode in its binding, so a normal result is never reused as a careful result
or conversely.

The user interface does not expose provider names. Provider-specific command
details remain behind the adapter boundary.

## Candidate

| Field | Value |
| --- | --- |
| Product source A | `d5e7c42bbf3b534a72032acd6d1a1dc178001d3f` / tree `bf34fda470c5e5703d55aa7ccc731be7a4061508` |
| Candidate | `candidate-v1-3348b6fc8ed525632d7d0abed1337f2e37b66404f0d6f4488cb3c012c3afca83` |
| Bundle digest | `448e5ee02ed22c2c77837b25934278750ea9a4a08a9d7f02e70c372886a83d7a` |
| Manifest digest | `a9a9c6bc19238bbfc215dc1b40d618c3e2afd74c0c10f99b3ec410d0a5253cf1` |
| Private adapter provider pin | SeminarText `13644d262776aacdf36221b9a9fc7ebd0a7c0737` |
| Provider CLI digest | `30d8c1bd6f5ca717391b168cba71228a030009feaec4eb443bb1e76dab230a6c` |
| Candidate archive | `~/Library/Application Support/Integra/Build Archive/candidate-v1-3348b6fc8ed525632d7d0abed1337f2e37b66404f0d6f4488cb3c012c3afca83/448e5ee02ed22c2c77837b25934278750ea9a4a08a9d7f02e70c372886a83d7a` |

The archived Candidate was independently rehashed after copying. Its archive
receipt covers 29,647 files and 2,202,970,969 application bytes.

## Runtime semantics and proof

The minimal upstream repair is pinned as SeminarText PR #126. It makes the
existing `project-transcribe` command accept `--careful`; without that repair,
the global option parser could not safely reach the project command. Integra
uses that option only when the user chose `Тщательный`. The first careful attempt
was verified with beam size 8, best-of 8, VAD threshold 0.45, and minimum silence
700 ms. The pre-existing automatic protective retry is unchanged: beam/best 3,
VAD 0.68, minimum silence 350 ms.

The exact Candidate passed manifest validation and native self-test. Its native
suite passed a real short-video workflow as well as close-active-run,
quit-active-run, stale-running reconciliation, verified ASR retry, and
stable-operations/real-cancel checks. A separate packaged E2E invoked the
Candidate's bundled bridge with `recognition_mode=careful` on a short audio
fixture, reread persisted run/job/source-result state, and captured the careful
provider invocation. It passed.

Focused contract/runtime tests also prove that invalid modes fail closed and
that normal and careful cache bindings are distinct. No test or implementation
changes the normal provider command when the selected mode is `normal`. The
focused suite recorded **63 passed, 3 skipped**. The skips are VideoText media
runtime tests unavailable in the source-tree test environment; the packaged
Candidate's independent short-video workflow passed and is not a skipped proof.

## Packaging note

The final archive is 1,474,539 bytes larger than the prior retained CURRENT
Candidate. No extra provider or duplicate runtime was added. The difference is
42 Python bytecode cache files created while packaging the already pinned review
runtime. Candidate logical bundle identity deliberately excludes `__pycache__`
and `.pyc` files; the immutable archive inventory nonetheless covers every byte
of this exact Candidate. This is a packaging reproducibility risk to address in
a separate bounded maintenance task, not a reason to conflate this Candidate
with the prior one.

## Scope result

This evidence closes only bounded row 11/S04: a real selectable careful mode,
accurate configuration/provenance persistence, and retained protective retry.
It does not close the still separate source-language, general ASR quality
settings, ASR diagnostics, translation, topic, folder/playlist, or selected
runtime-closure Board rows.
