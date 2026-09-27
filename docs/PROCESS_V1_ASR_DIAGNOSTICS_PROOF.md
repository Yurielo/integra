# Process v1: ASR diagnostics proof

Date: 2026-09-27. Status: `CANDIDATE_READY_FOR_PROPOSAL`.

This is bounded delivery evidence for Excel #17 / V02 + S02, **ASR
diagnostics**. It does not change `CURRENT`, canonical routing, the selected
ASR provider, Stage B, Knowledge, Studio, installation, or deployment.

## Delivered behaviour

Every completed or quality-rejected media source now persists one
Integra-owned `asr_diagnostics` record. It is rendered under `ПРОВЕРКА
РАСШИФРОВКИ` in both the operations result and a reopened result view. The
normal Process UI presents only:

- a readable quality outcome;
- the actually executed recognition mode;
- the actually executed source-speech language;
- whether protective reprocessing was needed and its final outcome.

It does not display a provider name, model identifier, command, raw log line,
threshold, or exception in that surface. A quality rejection instead has the
stable user-facing run message: `Расшифровка не прошла проверку качества.
Проверьте аудио и повторите обработку.` The failed source retains its
diagnostics and technical evidence, but it never receives a successful
transcript or downstream semantic output.

The persisted contract validates the exact consistency relation
`protective_retry_count = recovered_after_retry_count + suspicious_chunks`.
It also rejects a requested/executed mode or language mismatch rather than
inventing a diagnostic. This preserves the existing normal and careful ASR
semantics and the fixed Russian source-language contract.

## Candidate and archive

| Field | Value |
| --- | --- |
| Product source A | `3576de15c915dba90ac8cff30e3f18a47ed858a8` / tree `e17d2ea714da0f4af1c8aa0be4038a257d5bd3b3` |
| Candidate | `candidate-v1-ec1ae4eaccc5a2af225490135dc6385920c5f26ee0433059311be9074f6a2e57` |
| Bundle digest | `4794bca8031cf6ff0d6a8c019e5492646604ba9e66b3e591167c0c9e63929ffd` |
| Manifest digest | `df330c430ff6862f97d7db12d6bcc0362b3241b80989a7ec1935372e7fa2a7df` |
| Private provider pin | SeminarText `13644d262776aacdf36221b9a9fc7ebd0a7c0737` |
| Candidate archive | `~/Library/Application Support/Integra/Build Archive/candidate-v1-ec1ae4eaccc5a2af225490135dc6385920c5f26ee0433059311be9074f6a2e57/4794bca8031cf6ff0d6a8c019e5492646604ba9e66b3e591167c0c9e63929ffd` |

The fresh bundle passed manifest validation and `INTEGRA_MACOS_SELF_TEST:
PASS`. It was copied to a permanent archive and independently rehashed:
29,604 files and 2,201,525,299 application bytes. No existing archive or
installed application was replaced.

## Packaged runtime evidence

The exact packaged Candidate processed isolated synthetic WAV fixtures through
its own bridge and pinned runtime. No user project or media was read.

| Scenario | Requested / executed | Persisted outcome |
| --- | --- | --- |
| Protective retry recovers | `careful → careful`, `ru → ru` / `FIXED` | `PASSED`; one retry, one recovery, zero remaining suspicious fragments; reopened run matched the persisted record. |
| Protective retry cannot recover | `normal → normal`, `ru → ru` / `FIXED` | `REQUIRES_ATTENTION`; one retry, zero recoveries, one remaining suspicious fragment; no transcript was written. |

`PROCESS_V1_ASR_DIAGNOSTICS_E2E.json` holds the exact persisted records and
the fail-closed user-facing run message. The existing native retry probe also
passed against this Candidate, confirming that ASR reuse and retrying a later
stage remain intact.

## Regression boundary

Focused source tests ran `66` tests with `27` declared environment skips and
no failures or errors. They cover the pinned CLI's retry/failure conditions,
diagnostic validation, persisted failed-source result, ASR reuse, application
runtime, and native AppKit result composition. Candidate-specific validation
then passed manifest validation, native self-test, archive rehash, the native
retry probe, and the two packaged diagnostics scenarios above.

This evidence does not claim a general ASR-health score, automatic recovery of
poor audio, a new user quality setting, English ASR, transcript translation,
topic generation, a provider migration, or `PROCESS V1 USER_ACCEPTED`.
