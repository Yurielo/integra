# Process v1: ASR quality settings proof

Date: 2026-09-27. Status: `CURRENT_CANDIDATE_REVALIDATED`.

This is the bounded evidence for Excel #16 / S04 + V02, **ASR quality
settings**. It reconciles the frozen row with the already canonical Excel #11
Careful ASR mode. It does not add a second selector, change `CURRENT`, rebuild
the Candidate, change a provider pin, start ASR diagnostics (#17), or expand
Process scope.

## Exact #16 semantics and distinction from #11

The pinned production runtime supports exactly two user-selectable recognition
quality profiles:

| Normal-user selection | Requested/executed mode | Default | Production first-pass profile |
| --- | --- | --- | --- |
| `Обычный` | `normal` | Yes | beam `5`, best-of `5`, VAD threshold `0.55`, silence `550 ms` |
| `Тщательный` | `careful` | No | beam `8`, best-of `8`, VAD threshold `0.45`, silence `700 ms` |

The one normal Process control is labelled `Режим распознавания`; its help text
states the user-facing trade-off: careful mode prioritizes recognition
completeness over speed. It intentionally contains no provider name, model
identifier, command-line flag, or internal parameter.

Excel #11 named the `careful` member of this selector and proved its production
route. Excel #16 names the complete quality-setting outcome: the same single
selector, its truthful normal default, both valid values, and their persisted
requested/executed state. There is no distinct third provider-supported quality
parameter to expose. Creating another control would be contradictory and would
not reach a separate production capability.

The automatic protective retry uses beam `3`, best-of `3`, VAD threshold
`0.68`, and silence `350 ms` after a quality rejection. It is deliberately not
a user setting and remains the separately accepted **Protective retry** outcome:
it is automatic, reported in the ASR artifacts, and never silently reclassifies
a failed retry as success.

## Candidate and runtime binding

| Field | Value |
| --- | --- |
| Candidate | `candidate-v1-43bdfe7b93052a3f2f9b5b6b089179580ef5387ebe82d0e96ef69e612257b0cd` |
| Product source A | `ccdc8bf1f63280df889483904720a9fb2d618345` / tree `e71db703513b66ebe17148bfaeb671586bf21e7f` |
| Bundle digest | `306e3301484b24f1933c3b3ef51583ab4c786263b4ac3ecea241060177aa5eb1` |
| Manifest digest | `4e50d4156dca216d9b3fd90d8dfb72112f02d3889b90b101af6511ee1fb9d019` |
| Private provider pin | SeminarText `13644d262776aacdf36221b9a9fc7ebd0a7c0737` |
| Provider entrypoint digest | `30d8c1bd6f5ca717391b168cba71228a030009feaec4eb443bb1e76dab230a6c` |

No application or runtime byte changed for this reconciliation. The Candidate
archive was rehashed on 2026-09-27: `COMPLETE`, byte-integrity `PASS`, 29,604
files and 2,201,504,086 application bytes. Its native `--self-test` also
returned `INTEGRA_MACOS_SELF_TEST: PASS`.

## Production route, persistence, and failure boundaries

The native UI submits `recognition_mode` and `source_speech_language` to the
bridge. The Integra-owned application runtime validates the only two modes,
records `recognition.requested_mode`, and gives each media job the same mode.
The isolated adapter invokes the pinned runtime with `--careful` only for
`careful`; the normal route has no such flag. The media result rejects any
mismatch between the requested and adapter-reported mode, then persists both
`requested_mode` and `executed_mode` together with internal runtime identity.

The existing current-Candidate E2E for Excel #15 executed both representative
combinations on an isolated synthetic Russian audio fixture:

| Mode | Language requested/executed | Result |
| --- | --- | --- |
| `normal` | `ru -> ru` / `FIXED` | `COMPLETED`, TXT and SRT persisted |
| `careful` | `ru -> ru` / `FIXED` | `COMPLETED`, TXT and SRT persisted |

An unsupported language is rejected before ASR. An unsupported recognition mode
is rejected before job creation. The adapter and media layer reject a provider
mode or language mismatch, so neither quality nor language can silently fall
back. The ASR reuse key includes the recognition mode and language, preventing
cross-profile reuse. Reopened runs read the persisted requested/executed values;
Results, Topic Review, recovery, and multi-source behavior were covered by the
same focused Candidate suite.

## Regression evidence

`tests/test_seminartext_asr_runtime.py` executes the real pinned project CLI
against deterministic test-only media executables. It proves the normal
first-pass profile, careful first-pass profile, automatic retry profile, and
persisted `normal`/`careful` provenance. Existing application, reuse, native UI,
Results, Topic Review, recovery, and multi-source tests protect the surrounding
Process routes. Full-suite and GitHub Quality Gate results are recorded with the
delivery PR.

## Scope result

Excel #16 is complete because all of its frozen requirements are already met by
one non-duplicated normal-user setting that reaches the real production path,
has a truthful default and failure behavior, composes with source-speech
language, and persists requested/executed provenance. This acceptance does not
close Excel #17 ASR diagnostics, add arbitrary tuning, add automatic language
detection, introduce another provider, or change the user-visible scope of
Careful ASR mode.
