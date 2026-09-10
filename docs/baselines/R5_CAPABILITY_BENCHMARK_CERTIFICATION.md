# R5 Normalized Capability Benchmark Certification

Status: `PASS`

Issue: [#7](https://github.com/Yurielo/integra/issues/7)

Verified: 2026-09-10

## Scope and safety

R5 compared the pinned SeminarText and VideoText baselines through nine common
contract-replay capability groups. Each qualified probe ran twice, sequentially,
against temporary detached checkouts. Both checkout identities matched
`state/component_baselines_v1.json` and were `CLEAN` before and after the run.

No Dataset C/D/E, Gold, private project, credential, model inference, external
account, publication, or source-repository modification was used. Semantic
quality and human correction burden are explicitly `NOT_MEASURED` when they
would require unauthorized Gold or human labels.

The normalized fixture manifest is
`tests/fixtures/capability_benchmark_v1/manifest.json`. The raw replay record is
`state/capability_benchmark_raw_v1.json` with SHA-256
`cd7614e1027a1a3e661fb7e4b90ed711faf6bb2890e66d8baf80ebc855c55566`.
The governed record is `state/capability_benchmark_v1.json`.

## Technical selections for Core Alpha

| Capability | Primary | Retained fallback/challenger | Selection boundary |
| --- | --- | --- | --- |
| Media preparation | VideoText | none | bounded media workflow; SeminarText lacks a qualified reusable media-preparation contract |
| ASR | VideoText | none | replayable transcript-quality gate plus accepted real-media evidence |
| Word/cue alignment | SeminarText | VideoText fallback | Canonical Word Timeline and explicit word-level provenance |
| Translation | VideoText | SeminarText fallback | application-integrated adapter/review lifecycle; semantic quality not claimed |
| Topics | SeminarText | VideoText challenger | accepted Topic lifecycle and provenance; semantic superiority not claimed |
| Review mechanics | composed | SeminarText for Topic/knowledge decisions; VideoText for transcript/media checkpoints | follows accepted field ownership |
| Cache | VideoText | none | input/model/config-bound cache behavior |
| Recovery | VideoText | SeminarText fallback | bounded project watchdog plus evidence resume fallback |
| Quality validation | composed | both primary in owned scopes | SeminarText canonical evidence; VideoText media/transcript quality |

These are technical integration defaults for R6. They do not promote machine
semantic output, replace Product Owner authority, alter either source product,
or retire a fallback/challenger.

## Evidence summary

- Capability groups: 9/9 recorded.
- Qualified candidate probes: 15; each passed two repetitions.
- Source identities: SeminarText
  `a94936cd77cde13561c97c804ece1ac1134e01a6`; VideoText
  `2e098d1705b6815628bee1e023f4742718eabf02`.
- Source checkout state before/after: `CLEAN` / `CLEAN` for both.
- Resource metric: wall-clock elapsed time per replay. VideoText values include
  Swift compilation and therefore are not production throughput comparisons.
- Peak RSS: not measured by the dependency-free runner.
- Reproducibility: all repetitions passed; pytest stdout hashes may differ only
  because pytest prints measured duration.

## Limits carried into R6

- R5 does not establish ASR, translation, or Topic semantic superiority.
- R5 does not authorize protected benchmark data, Gold, tuning, or model changes.
- `NOT_QUALIFIED` means no pinned reusable contract satisfied the R5 normalized
  assertions; it does not assert that the source product has no related code.
- R6 must use the selected roles through the R3/R4 contract boundary and keep
  both standalone applications independently usable.
