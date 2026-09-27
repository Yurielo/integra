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
| Product source A | `5635bf1573e642c041ade4ad888fb79e5f5f6889` / tree `6c6783858dbd030aa7024a84d7f11d2418cda2ff` |
| Candidate | `candidate-v1-f9ef07f48ff155645239f9c72b454732f53fecabdbf9379ad4d25b1a5acbdc9a` |
| Bundle digest | `448e5ee02ed22c2c77837b25934278750ea9a4a08a9d7f02e70c372886a83d7a` |
| Manifest digest | `5f4de8d844aaf6ba42c2839b8462f79c0e9862b09ec6e513f8ec9b327fc7c40f` |
| Private adapter provider pin | SeminarText `13644d262776aacdf36221b9a9fc7ebd0a7c0737` |
| Provider CLI digest | `30d8c1bd6f5ca717391b168cba71228a030009feaec4eb443bb1e76dab230a6c` |
| Candidate archive | `~/Library/Application Support/Integra/Build Archive/candidate-v1-f9ef07f48ff155645239f9c72b454732f53fecabdbf9379ad4d25b1a5acbdc9a/448e5ee02ed22c2c77837b25934278750ea9a4a08a9d7f02e70c372886a83d7a` |

The archived Candidate was independently rehashed after copying. Its archive
receipt covers 29,604 files and 2,201,500,380 application bytes.

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

The full local suite passed **794 tests** with **83 environment-declared
skips** for unavailable external source runtimes. GitHub PR #194's governance
Quality Gate passed on the Proposal Lite declaration commit. The full native
Candidate gate remains separate evidence and was executed against the archived
Candidate with its pinned runtime sources.

## Packaging note

The final archive is 3,950 bytes larger than the prior retained CURRENT
Candidate. No extra provider or duplicate runtime was added. Candidate logical
bundle identity deliberately excludes `__pycache__` and `.pyc` files; the
immutable archive inventory nonetheless covers every byte of this exact
Candidate.

## Scope result

This evidence closes only bounded row 11/S04: a real selectable careful mode,
accurate configuration/provenance persistence, and retained protective retry.
It does not close the still separate source-language, general ASR quality
settings, ASR diagnostics, translation, topic, folder/playlist, or selected
runtime-closure Board rows.
