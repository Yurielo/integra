# Issue #142 — Word Alignment runtime recovery

Date: 2026-09-20
Issue: [#142](https://github.com/Yurielo/integra/issues/142)
Final status: `READY_FOR_OWNER_ACCEPTANCE`

## 1. Authoritative runtime contract

| Contract item | Evidence | Required value |
| --- | --- | --- |
| Python | `integra_core/word_timeline_runtime.py` | CPython 3.13, executable, arm64 on this candidate host |
| Worker | `workers/seminartext_word_alignment_worker.py` | Bundled `seminartext_word_alignment_worker.py`; imports `whisperx`, calls `load_align_model` and `whisperx.align` on CPU |
| Runtime package root | `word_timeline_runtime.py` | Bundled `runtime/word-alignment/site-packages`, containing `whisperx` |
| Alignment implementation | worker source | WhisperX `3.8.6`, alignment-only, Russian transcript, no ASR behavior change |
| Core pinned packages | source runtime `pip freeze --all` recorded before reconstruction | `torch==2.8.0`, `torchaudio==2.8.0`, `transformers==4.57.6`, `faster-whisper==1.2.0`, `ctranslate2==4.6.0`, `pyannote-audio==4.0.7`, `whisperx==3.8.6` |
| Model | worker/build script | `jonatasgrosman/wav2vec2-large-xlsr-53-russian`, revision `2329100508896c6d9b157019803ab5601e6f3406`, `pytorch_model.bin` SHA-256 `d1cdb1a7921de7d363f967a9b0101a713602e109dba62b6f3f9ae2e0b2df0c1c` |
| Build verification | `scripts/build_macos_app.sh` | `whisperx` directory exists; pinned model hash is verified before it is bundled |

The worker was not altered. No model, ASR, component or semantic pin was changed.

## 2. Reconstruction provenance and commands

The #140 source runtime was used **only** to read its complete package-version inventory using:

```bash
/Users/yurielokhin/Documents/integra/.runtime-word-alignment/bin/python3.13 \
  -m pip freeze --all
```

This produced an exact 102-distribution freeze. The package payload was not copied. A first `--only-binary=:all:` reconstruction correctly stopped because exact historical `antlr4-python3-runtime==4.9.3` has no CPython 3.13 binary wheel. The successful reconstruction retained the exact frozen version and permitted its source distribution; no package was upgraded, substituted or deleted.

```bash
/opt/homebrew/opt/python@3.13/bin/python3.13 -m venv \
  /private/tmp/integra-word-alignment-runtime-issue-142
/private/tmp/integra-word-alignment-runtime-issue-142/bin/python -m pip install \
  --disable-pip-version-check --no-input -r issue-142-source-freeze.txt
```

The disposable runtime is deliberately in `/private/tmp`, a local non-File-Provider location. It is not installed, deployed, or a replacement for the rejected source runtime.

## 3. Package inventory and hashes

| Evidence | Result |
| --- | --- |
| Source vs reconstructed `pip freeze --all` | Exact equality: 102 distributions |
| `pip check` | `No broken requirements found` |
| Python | `Python 3.13.15`, Mach-O arm64 |
| Reconstructed tree | 45,710 readable regular files |
| Tree inventory SHA-256 | `ec2dc400cff74248b86b6e4f95999979dd75d74e429123770b0afd5c46e2aa49` for sorted per-file SHA-256 manifest |
| File Provider / quarantine scan | No `fileprovider` or `quarantine` attributes in the reconstructed `/private/tmp` runtime |
| Model weights hash | `d1cdb1a7921de7d363f967a9b0101a713602e109dba62b6f3f9ae2e0b2df0c1c` — PASS |

The source freeze, clean freeze, per-file manifests and pip/build logs are retained in the Issue #142 disposable work area for review. They are not product artifacts and contain no private media.

## 4. Health and production alignment-path evidence

| Check | Result | Evidence |
| --- | --- | --- |
| Full reconstructed tree readable | PASS | Every file hashed successfully. |
| `import whisperx` | PASS | Clean runtime. |
| `from whisperx.alignment import load_align_model` | PASS | Clean runtime; warm result 2.36 s. |
| `load_align_model(language_code="ru", device="cpu", model_cache_only=True)` | PASS | Exact hash-pinned Russian model initialized in 2.45 s. |
| Bundled candidate `word_timeline_runtime.preflight()` | PASS | Returned only candidate bundle `site_packages` and model paths. |
| Bundled direct alignment import | PASS | `whisperx.__file__` asserted within candidate bundle, then actual alignment module imported. |
| Bundled worker smoke | PASS | Synthetic WAV/SRT → `/private/tmp/integra-candidate-issue-142-word-smoke/timeline.json`, 2 words, SHA-256 `5f2e52332dbead77b816cc59cd64826d645aa11c31489ab990ff4e32918937eb`. |

The source runtime’s File Provider condition was not propagated. The candidate did not use it: the build explicitly received `INTEGRA_WORD_ALIGNMENT_SITE_PACKAGES=/private/tmp/integra-word-alignment-runtime-issue-142/lib/python3.13/site-packages`, and candidate preflight returned its packaged copy.

## 5. Candidate build and identity

| Field | Value |
| --- | --- |
| Repository branch | `codex/issue-142-word-alignment-runtime-recovery` |
| Source HEAD before this report | `df784b0d49409b69624e0be169c3604e1d78f36b` |
| SeminarText input | `970bde598ddd649599295139986933e0e06cb9c0`; CLI SHA-256 `f7f411bf106341ae970bc40d759e1e3c964273b977bdb12d0f1840e629def13a` |
| VideoText input | clean detached `2e098d1705b6815628bee1e023f4742718eabf02` |
| BookText input | `46396649214275eb18054b670a842bace02d02e1` |
| Candidate | `/private/tmp/integra-candidate-issue-142/Integra.app` |
| Build duration | 77.15 s |
| Candidate content | 33,269 files, 2.2 GiB; no symlink was reported by bundle checks |
| Bundle SHA-256 | `8728ad7ebd0785d9d5b2c52d2c771b99c7d242c998d076852c55068211fcc556` (component smoke digest) |

The build was invoked with all component/runtime source paths explicitly set. The existing installed/current Integra app was not read, replaced or deployed.

## 6. Candidate-level validation

| Check | Status | Evidence |
| --- | --- | --- |
| Clean isolated build | PASS | Completed to fresh `/private/tmp/integra-candidate-issue-142/Integra.app`; no Word Alignment copy stall. |
| Native self-test | PASS | `INTEGRA_MACOS_SELF_TEST: PASS`. |
| Bundled SeminarText preflight | PASS | Bundled origin, commit `970bde...`, CLI hash `f7f411...` asserted. |
| Bundled Word Alignment isolation/preflight | PASS | Candidate-only packages/model asserted; actual alignment import and worker smoke PASS. |
| VideoText component smoke | PASS | Real bundled media clip/speed/burn/audio-analysis synthetic smoke. |
| SeminarText component smoke | PASS | Bundled machine-Evidence generation from synthetic transcript/timeline; no ASR or semantic acceptance claimed. |
| BookText component smoke | PASS | Real local OCR on synthetic 3-page PDF, selected pages 1 and 3; report SHA-256 `191de94f75e666257394587550db83e946f5798bfcdf32b08493bc5fbb1e5ecb`. |
| Publication dry runs | PASS | Obsidian and OneDrive bridge previews made no writes/external actions. |
| Agent validator | PASS | 6 permanent / 4 on-demand roles; 10 covered responsibilities. |
| Governance validator | PASS | Current accepted-contract validation. |
| Focused non-GUI regressions | PASS | 78 tests PASS, 27 skipped: Word Timeline, SeminarText runtime/ASR, application runtime, ASR reuse, shutdown, BookText selection, VideoText runtime/media. |
| GUI E2E | NOT_RUN | #138 constraint retained: existing `scripts/test_macos_app.sh` opens Finder/visible native app. Owner must execute it manually against this exact candidate. |

BookText’s successful real OCR still records its intentional local Surya executable/model prerequisite. It is not represented as a bundled Surya runtime. That pre-existing contract is explicit in the resulting artifact and is a remaining owner-environment prerequisite, not an accidental Word Alignment fallback.

## 7. Remaining risks

1. The reconstructed runtime is a disposable, exact-version candidate input. A durable/repeatable runtime-generation policy and package hash lock are separate packaging work, not silently introduced here.
2. CPython itself and BookText’s Surya/toolchain remain documented local prerequisites; the candidate validates their resolved paths but does not claim to bundle them.
3. Translation model availability and semantic/performance behavior, Topic quality, failure recovery (#137), partial-result UX and other #139 items remain outside this issue.
4. GUI E2E and all user acceptance remain pending. `TESTED` is not `USER_ACCEPTED`.

## 8. Owner acceptance checklist

Use exactly this candidate while it remains available:

`/private/tmp/integra-candidate-issue-142/Integra.app`

1. Record candidate path and bundle SHA-256 `8728ad7ebd0785d9d5b2c52d2c771b99c7d242c998d076852c55068211fcc556` in the acceptance record.
2. Launch that path manually; do not substitute the installed/current Integra app.
3. Verify source-first source selection, capability availability reasons, resolved plan and concrete result navigation.
4. On authorized non-private media, validate transcript/SRT/Word Timeline/Topics, including factual ASR quality-gate/retry visibility if triggered.
5. Validate a bounded translation, BookText OCR page selection/output, cancellation/retry, error/partial-result behavior and result locations.
6. Treat unavailable external requirements as factual preflight states, never as success. Record artifacts, logs and PASS/FAIL/BLOCKED per scenario.
7. Only the owner may subsequently decide `USER_ACCEPTED`; this issue does not grant that status.

## 9. Final status

`READY_FOR_OWNER_ACCEPTANCE`

The #140 Word Alignment copy blocker is removed for this exact isolated technical candidate. No deployment, merge, pin change, model change, semantic change or product repair was made.
