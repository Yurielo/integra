# Process v1: Source-speech language proof

Date: 2026-09-27. Status: `PROPOSED_BASELINE_VALID / AWAITING_OWNER_ACCEPTANCE`
after the Proposal Lite and Quality Gate are recorded.

This is bounded evidence for Excel #15 / V02, **Source-speech language**. It
does not promote `CURRENT`, change canonical Process routing, replace the
SeminarText ASR provider, start Stage B, install an application, or constitute
`PROCESS V1 USER_ACCEPTED`.

## Delivered behaviour

For a supported audio or video transcription, the normal Process setup shows
`Язык исходной речи`. The only offered value is `Русский`. The control does not
show provider names, model names, CLI flags, or the internal ISO value.

This scope is intentionally narrow because the exact pinned production
SeminarText runtime is fixed to Russian. It has no reliable automatic language
detection contract, so the interface does not claim one. It likewise does not
pretend that English or any other language is available.

The selected value travels through the native GUI, bridge, Process run and
every media job. The run, source result and ASR provenance store requested and
executed values independently. `ru` is accepted only when the provider
preflight confirms the same fixed execution value; an unsupported value fails
before an ASR run can be started. There is no automatic or cross-language
fallback.

Normal and Careful remain independent recognition settings. The language is
included in the ASR reuse configuration binding, so cached output cannot be
reused under a different source-language contract.

## Candidate

| Field | Value |
| --- | --- |
| Product source A | `ccdc8bf1f63280df889483904720a9fb2d618345` / tree `e71db703513b66ebe17148bfaeb671586bf21e7f` |
| Candidate | `candidate-v1-43bdfe7b93052a3f2f9b5b6b089179580ef5387ebe82d0e96ef69e612257b0cd` |
| Bundle digest | `306e3301484b24f1933c3b3ef51583ab4c786263b4ac3ecea241060177aa5eb1` |
| Manifest digest | `4e50d4156dca216d9b3fd90d8dfb72112f02d3889b90b101af6511ee1fb9d019` |
| Private provider pin | SeminarText `13644d262776aacdf36221b9a9fc7ebd0a7c0737` |
| Provider entrypoint digest | `30d8c1bd6f5ca717391b168cba71228a030009feaec4eb443bb1e76dab230a6c` |
| Candidate archive | `~/Library/Application Support/Integra/Build Archive/candidate-v1-43bdfe7b93052a3f2f9b5b6b089179580ef5387ebe82d0e96ef69e612257b0cd/306e3301484b24f1933c3b3ef51583ab4c786263b4ac3ecea241060177aa5eb1` |

The Candidate was built in a fresh temporary directory, validated before use,
and then copied into permanent storage. An independent archive rehash passed:
29,604 files and 2,201,504,086 application bytes.

## Runtime proof

The actual bundled Candidate processed a short local synthetic Russian audio
fixture twice through its own bridge and pinned runtime. No user media was
read.

| Recognition mode | Result | Requested / executed | Output |
| --- | --- | --- | --- |
| Normal | `COMPLETED` | `ru` / `ru` / `FIXED` | transcript and SRT |
| Careful | `COMPLETED` | `ru` / `ru` / `FIXED` | transcript and SRT |

Both persisted a 124-byte transcript and a 156-byte SRT, along with the exact
SeminarText commit above. A separate Candidate bridge request for `en` failed
with `source-speech language is unsupported`; it created no ASR run and did
not claim a Russian execution.

The Candidate manifest validation and native `--self-test` both passed. The
focused regression suite passed **95 tests** with **31 declared environment
skips**. Its executed coverage includes Results UX, Topic Review surfaces,
recovery contracts and multi-source alignment. The skips are source-tree tests
whose external pinned runtime is intentionally unavailable there; the bundled
Candidate provides independent non-skipped Normal and Careful E2E evidence.

The native application was launched for visual verification, but macOS locked
before its accessibility tree could be captured. This is a documented visual
QA limitation, not a claim of visual evidence. Static native UI tests and the
native self-test passed.

## Scope result

This evidence supports only Excel #15 / V02: truthful selection of the
currently supported Russian source speech, real fixed-language execution,
Normal/Careful compatibility, persistent requested/executed provenance, and
fail-closed rejection of unsupported language requests.

It does not add automatic language detection, English transcription, general
ASR quality settings, ASR diagnostics, translation, topics, folders/playlists,
Stage B, Knowledge, Studio, installation, deployment, or provider migration.
