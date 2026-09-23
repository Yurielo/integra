# Process v1: controlled protective-retry proof

Status: evidence for the frozen **Protective retry** Board row only. This is
not a product-baseline proposal, a `CURRENT` change, a component-pin change, or
`PROCESS V1 USER_ACCEPTED`.

## Exact runtime and Candidate

| Binding | Exact value |
| --- | --- |
| Canonical source baseline | `8aa2a06fffedcd85ef5d99c03ab9a6aaa935f392` |
| Candidate ID | `candidate-v1-f7f0fd92b37ce8e8b172a6cfedba5c2b98d968f201de0f10c9cff06c61673777` |
| Candidate source | `2eade0c58d5e162bdbb36442c6874a6c21b03967`, tree `b112309d14fb65de1a6eece0a34c79b0b658b9e6` |
| Candidate manifest SHA-256 | `55c96ecde3e8f53bfb648a81dc0ef12abb586b35dbd3037b5c15530508e251d0` |
| Pinned SeminarText commit | `970bde598ddd649599295139986933e0e06cb9c0` |
| Pinned `seminartext` CLI SHA-256 | `f7f411bf106341ae970bc40d759e1e3c964273b977bdb12d0f1840e629def13a` |

The existing isolated Candidate was reused. It was not rebuilt and no
product/runtime byte was changed for this proof.

## Controlled non-private fixture and direct pre-proof

The fixture is a locally generated, non-private Russian TTS WAV. Its spoken
content consists of four deliberately close but distinct sentences about the
same topic; it contains no owner media:

```text
Сегодня мы подробно обсуждаем важную тему практического применения методов в реальной работе.
Сегодня мы подробно обсуждаем важную тему практического применения методов в нашей работе.
Сегодня мы подробно обсуждаем важную тему практического применения методов в учебной работе.
Сегодня мы подробно обсуждаем важную тему практического применения методов в дальнейшей работе.
```

| Item | SHA-256 / result |
| --- | --- |
| Generated 16 kHz mono WAV | `d593f02cfa1caf9d3d51948d49d122b524c670582d078bd63f6e86999ed9fdf2` |
| Direct first-pass transcript fixture | `tests/fixtures/protective_retry/fuzzy_first_pass.txt` — `05b846eb2fb2673e88ad109b9551f25482cbec0eabda7e2b064b06f3274a9b27` |
| Exact pinned `quality_check` result | `REJECT reason=fuzzy_contextual_repetition repeats=4 phrase_words=12 span_words=34 similarity>=0.82` |

The direct pre-proof executed the literal `quality_check` function extracted
from the Candidate's hash-verified pinned CLI against the first-pass transcript;
it neither mocked a detector nor invoked a retry branch directly.

Two bounded negative controls were also run through the same CLI: a single
Russian sentence plus 75 seconds of silence (`1f6a8aba4331d0f2046dbba6e9f64a88383b6ba732dfc8b58fddeb018812aaf2`) and a single connected Russian paragraph plus silence (`2b114ca52237794c97fa0adf611b5cbb0a67d8e1c6f05651da5408f1821a4600`).
Each yielded one VAD speech segment and no quality rejection. They are recorded
only to bound discovery; neither is counted as a retry proof.

## Packaged Finder-like Process proof

The exact existing `Integra.app` was driven through its packaged
`bridge.py → detect-sources → build-plan → execute-plan → run-status` path with
an isolated `INTEGRA_APP_DATA_ROOT` and a minimal Finder-like `PATH`. The only
host-provided dependencies were the normal verified ffmpeg, whisper-cli, Whisper
model, and VAD model used by the Candidate preflight; the SeminarText runtime
came from the app bundle and passed its pinned-byte verification.

| Evidence | Exact result |
| --- | --- |
| Project / run | `urn:integra:project:9172f7ca-9dcd-4f4e-852a-76760467960f` / `urn:integra:run:be4ff6aa-0c3c-41e0-b2c5-0062596131ac` |
| Persisted run evidence SHA-256 | `cf0f5e9167159044cc6185a6da5f26b9d11d6f85e5ca613dc473d266f34822dd` |
| Adapter log SHA-256 | `2559f89520a6e5952ee1e2c868b5c6267003f9983d63064f11d15b53d16df102` |
| Provenance SHA-256 | `deba7b7473de88628747ba0e0012eeff226bf94199c86a2d2d0457daa11050cf` |
| Quality report SHA-256 | `a3fef2469bec7240793f6942eb91d942dac01d2a5214b96ff502de201655c8ff` |

The preserved adapter log proves this unmodified production sequence:

1. NORMAL ran with `5 beams + best of 5`.
2. The real bundled detector emitted `REJECT reason=fuzzy_contextual_repetition repeats=4 phrase_words=12 span_words=34 similarity>=0.82`.
3. The CLI emitted `Обнаружено возможное зацикливание; повторяю с защитными параметрами.`
4. Automatic protective retry ran with `3 beams + best of 3`.
5. Retry also rejected the genuine four-repetition input; the CLI emitted
   `ПРЕДУПРЕЖДЕНИЕ: фрагмент 1 остаётся подозрительным.`
6. Integra persisted `transcript_quality_report` and `transcript_asr_record`,
   with `suspicious_chunks: 1`, then recorded the source and run as `FAILED`.

This is a truthful final result. It intentionally does **not** claim that a
retry recovered a genuine human repetition, and it does not convert a quality
failure into a successful transcript. It proves the frozen Board acceptance
gate — a controlled contextual/fuzzy trigger with evidence of the existing
automatic retry — through the packaged production route.

## Board transition

Before: **26 DONE / 2 IN_PROGRESS / 16 NOT_DONE / 1 BLOCKED**.

After: **27 DONE / 1 IN_PROGRESS / 16 NOT_DONE / 1 BLOCKED**.

Only **Protective retry** transitions `IN_PROGRESS → DONE`. **Topic
edit/confirm** remains the sole `IN_PROGRESS` row and still requires its
frozen human-review acceptance gate; it was not exercised here.

The next Board-selected action is therefore **Topic edit/confirm verification**,
but no work on it is created or started by this proof.
