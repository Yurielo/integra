# Issue #138 isolated candidate recovery — Issue #140 evidence

Date: 2026-09-20
Issue: [#140](https://github.com/Yurielo/integra/issues/140)
Final gate status: `BLOCKED`

## 1. Candidate identity

| Field | Value |
| --- | --- |
| Repository | `/Users/yurielokhin/Documents/Codex/2026-09-19/seminartext-production-asr-quality-gate-protective/work/integra-issue-138` |
| Base / current lineage HEAD before this report | `8fce7a625cac3d57f0d197e2ea610241821452f5` |
| Branch | `codex/issue-140-isolated-candidate-recovery` |
| #138 review state | 30 uncommitted files, 230 insertions / 106 deletions; diff content SHA-256 `9aa0888e7fbc3d7b036d61877cd9364b48b8ac3fe85c4a0f7c0968b5ed1a5f26` before this report |
| Intended SeminarText | commit `970bde598ddd649599295139986933e0e06cb9c0`; CLI SHA-256 `f7f411bf106341ae970bc40d759e1e3c964273b977bdb12d0f1840e629def13a` |
| VideoText | clean detached checkout `2e098d1705b6815628bee1e023f4742718eabf02` |
| BookText | pinned checkout `46396649214275eb18054b670a842bace02d02e1` |
| Word Alignment source | `/Users/yurielokhin/Documents/integra/.runtime-word-alignment/lib/python3.13/site-packages` |
| Word Alignment model | HF snapshot `2329100508896c6d9b157019803ab5601e6f3406`; `pytorch_model.bin` SHA-256 `d1cdb1a7921de7d363f967a9b0101a713602e109dba62b6f3f9ae2e0b2df0c1c` |
| Expected bundle destination | `Integra.app/Contents/Resources/runtime/word-alignment/site-packages` |
| Reproduction output | `/Users/yurielokhin/Documents/Codex/2026-09-19/seminartext-production-asr-quality-gate-protective/work/integra-candidate-issue-140-baseline/Integra.app` |

This is the exact #138/#139 review lineage. No current installed build, standalone component or component pin was changed.

## 2. Reproduction result

The baseline isolated build was invoked without increasing any timeout:

```bash
env \
  INTEGRA_SEMINARTEXT_BUILD_CHECKOUT=.../work/seminartext-final-970bde \
  INTEGRA_VIDEOTEXT_BUILD_CHECKOUT=.../work/videotext-final-2e098d \
  INTEGRA_BOOKTEXT_BUILD_CHECKOUT=/Users/yurielokhin/Documents/integra/.runtime-components/booktext-pinned \
  INTEGRA_WORD_ALIGNMENT_SITE_PACKAGES=/Users/yurielokhin/Documents/integra/.runtime-word-alignment/lib/python3.13/site-packages \
  INTEGRA_REVIEW_WHEELS=.../work/integra-review-wheels-issue-138 \
  bash scripts/build_macos_app.sh \
  .../work/integra-candidate-issue-140-baseline
```

The normal native and VideoText compilation stages completed. The build then stopped making progress at:

```bash
rsync -aL --exclude '__pycache__' --exclude '*.pyc' \
  /Users/yurielokhin/Documents/integra/.runtime-word-alignment/lib/python3.13/site-packages/ \
  .../Integra.app/Contents/Resources/runtime/word-alignment/site-packages/
```

After the Word Alignment stage began, the partial output remained at **1,355 files / 91 MiB**. It did not advance during the observed interval; the disposable build process was terminated. The build script itself provides no `rsync` timeout, so the timeout is not a repository timeout-policy setting that could be safely enlarged. It is a stalled I/O operation.

The source runtime contains **45,670 regular files**, 3 symlinks and approximately **1.0 GiB**. Source and output are different APFS mount points. The partial artifact is not a candidate and must not be used for validation.

## 3. Root cause

Classification: **abnormal/corrupted runtime source** and **packaging/build-design exposure**; not an ASR, alignment-model, pin or feature defect.

The stalled source tree carries File Provider / quarantine / provenance metadata, including `com.apple.fileprovider.dir#N` on directories and many `com.apple.provenance` / `com.apple.quarantine` attributes. The previously identified blocker path is:

```text
.../site-packages/fontTools/misc/filesystem/_errors.py
```

That small file is `hidden` and carries `com.apple.provenance`; direct content operations on the affected runtime were observed to block. `rsync -aL` traverses and copies the entire developer Python environment, including packages not proven by the production worker’s import closure. Excluding `__pycache__` and `.pyc` does not exclude this condition.

`import whisperx` alone succeeds from the source runtime, but importing the actual alignment module (`from whisperx.alignment import load_align_model`) did not finish during the diagnostic window. Therefore it would be unsafe to delete/exclude `fontTools` or other packages merely to make the bundle copy finish: that would change the effective runtime closure without proving the worker still works.

## 4. Changes made

No source-code, dependency, model, runtime-pin, ASR or Word Alignment semantic change was made.

The only repository addition is this focused evidence report. A safe repair would require a complete, readable, reproducible Word Alignment runtime input (or a separately approved locked runtime-closure packaging design). Neither can be fabricated from the current File Provider-affected source tree.

## 5. Build evidence

| Check | Result | Evidence |
| --- | --- | --- |
| Candidate lineage identity | PASS | Exact #138 review worktree, pinned clean SemText/VideoText inputs and script constants recorded above. |
| Baseline isolated build reproduced | PASS | Build reaches `rsync` Word Alignment site-packages stage. |
| Clean isolated build | FAIL | `rsync` I/O stalls; partial 1,355-file/91-MiB app only. |
| Produced candidate identity | NOT_AVAILABLE | Partial app is explicitly invalid and was not used. |

## 6. Runtime preflight evidence

| Runtime check | Result | Evidence |
| --- | --- | --- |
| SeminarText source identity | PASS (input) | Script validates `970bde...` and CLI `f7f411...`; prior #138 partial-bundle evidence confirmed it. |
| VideoText source identity | PASS (input) | Clean detached `2e098...` checkout used. |
| BookText source identity | PASS (input) | Build constants and hash checks remained unchanged. |
| Word Alignment package source usable as an imported root module | PASS, limited | `PYTHONPATH=<source> python3.13 -c 'import whisperx'` returned `READY`. |
| Word Alignment actual alignment import | FAIL / blocked | `from whisperx.alignment import load_align_model` did not complete in the diagnostic window. |
| Bundled runtime isolation / false-positive external-resource check | NOT_RUN | No valid bundle exists. It must be run against a rebuilt exact candidate only. |

## 7. Automated test evidence

No candidate-level test was run against the invalid partial bundle.

The prior #138 evidence remains: focused tests 199 PASS; selected headless suite 624 PASS / 73 skipped; governance and agent validators PASS. That evidence does not establish a valid #140 candidate. GUI-producing `scripts/test_macos_app.sh` was not run automatically.

## 8. GUI E2E evidence

`NOT_RUN`. A packaged-candidate GUI E2E would be invalid without a complete candidate. No Finder, Preview, media player or Integra GUI was opened by this work package.

## 9. Remaining risks

1. The build input currently depends on a developer runtime whose file availability is not stable or fully readable.
2. The production alignment import has not completed from that source tree; a superficial root-package preflight is insufficient evidence for actual alignment.
3. The build cannot distinguish a full declared runtime closure from a partial environment copied from a workstation.
4. Issue #137 interruption recovery and #139 semantic/UX gaps remain outside this issue and were not changed.

## 10. Owner acceptance checklist (prepared, not executed)

This checklist becomes actionable only after a new clean isolated candidate is built:

1. Record repository commit, branch, clean working-tree state, build command, output path and SHA-256 manifest of the bundle.
2. Verify bundled (not external) SeminarText `970bde...` / `f7f411...`, VideoText, BookText, Word Alignment model and actual `whisperx.alignment` import.
3. Run native `--self-test`, headless bundle smoke and each component smoke against that exact app.
4. Launch exactly that `.app` manually and record the launch path/candidate identity.
5. Run owner scenarios: local media transcription/SRT/Word Timeline/Topics, visible quality-gate/retry behavior where triggered, translation, BookText OCR, result/error/partial-output location and cancellation/retry.
6. Record PASS/FAIL/BLOCKED with artifact paths and screenshots/logs; only the owner can mark a later candidate `USER_ACCEPTED`.

## 11. Final gate status

| Gate | Status | Evidence |
|---|---|---|
| Candidate identity | PASS | #138/#139 review lineage and build inputs recorded. |
| Clean isolated build | FAIL | Word Alignment site-packages `rsync` stalls. |
| Word Alignment runtime | FAIL | File Provider-affected source blocks copy and actual alignment-module import did not complete. |
| Runtime preflights | FAIL | No complete isolated bundle; input-only checks are insufficient. |
| Bundle smoke | NOT_RUN | No valid candidate. |
| Native self-test | NOT_RUN | No valid candidate. |
| GUI E2E | NOT_RUN | Correctly deferred; no candidate. |
| Owner acceptance | PENDING | owner only; prerequisite candidate is absent. |

**Final status: `BLOCKED`.**
