# Process v1 — VideoText-only execution inventory

**Issue:** #187  
**Status:** Phase 1 factual inventory. No product/runtime byte is changed by
this document. It is evidence for the proof gate, not implementation approval.

## Method

This inventory traces the selected normal local media route in canonical main
from capability selection through persistence. It uses source paths and the
frozen Process v1 Definition of Done; it does not infer product integration
from a registry entry or a component unit test.

## Current selected local media route

```text
Process UI / bridge
  → application_runtime.execute_run
    → user_media.run_job
      → asr_reuse.transcribe_or_reuse
        → seminartext_asr_runtime.transcribe
          → bundled SeminarText project-transcribe
            → raw TXT / clean TXT / review TXT / source SRT
          → VideoText SRT normalization
      → Integra transcript persistence
      ├─ Word Timeline: Integra WhisperX adapter
      ├─ Topics: bundled SeminarText topic worker
      ├─ Translation: bundled VideoText translation worker
      └─ Burn / speed / audio analysis: bundled VideoText media worker
```

The normal transcript path is therefore **not VideoText-only today**.  It has
three material SeminarText dependencies:

1. `asr_reuse.py` imports `seminartext_asr_runtime`.
2. `seminartext_asr_runtime.transcribe` launches bundled `project-transcribe`
   and reads its quality, clean/review and provenance artifacts.
3. `user_media.run_job` calls the bundled SeminarText topic worker, while the
   accepted Process Topic Review route consumes its draft contract.

There is a fourth boundary defect, not a fourth dependency: the source SRT
from SeminarText is sent to the VideoText normalizer. The comparison run showed
that source SRT has no ordinal cue lines while VideoText requires its stricter
form. This is the direct class of the current ordinary-media failure; it must
not be carried into a VideoText-native route.

## Ownership table

| Process responsibility | Current execution owner | VideoText-only target owner | Current dependency verdict |
| --- | --- | --- | --- |
| Source import, hashes, plan, run/job records | Integra | Integra | Reuse unchanged. |
| Transcript reuse/invalidation identity and lifecycle | Integra `asr_reuse`, with SeminarText executor identity | Integra, with a VideoText executor identity | Keep cache/lifecycle semantics; replace only executor-specific identity and artifacts. |
| ASR, VAD, segmentation, raw TXT, timed SRT | SeminarText CLI | VideoText `SegmentedWhisperTranscriber` and `SRTService` | VideoText source capability exists; native Process path absent. |
| Fuzzy/contextual loop quality gate and protective retry | SeminarText CLI | VideoText or an explicit Integra quality layer | VideoText has a different local retry for low-confidence and implausible-text-rate review tasks. It does not detect the known fuzzy/contextual loop class, so there is no proven equivalent. This is a required implementation/proof boundary. |
| Clean and review text derivatives | SeminarText CLI | VideoText output plus minimal Integra derivative adapter if needed | No proven VideoText-equivalent current Process artifact. |
| SRT serialization | SeminarText output then VideoText normalization | VideoText only | Native VideoText SRT removes the failing cross-component handoff. |
| Word Timeline | Integra WhisperX adapter | Integra WhisperX adapter | Reuse unchanged once given VideoText SRT. |
| Topic drafts and timecodes | SeminarText topic worker | VideoText hybrid topics | Source capability exists; draft shape and Process semantics need an adapter/proof. |
| Human Process Topic Review persistence | SeminarText-backed receipt and reviewed-state contract | Integra-owned receipt/precedence contract | The human decision semantics must be preserved, not discarded or promoted to Knowledge. |
| Translation | VideoText worker | VideoText worker | Reuse; its input will be VideoText-native SRT. |
| Burn subtitles, speed, audio analysis | VideoText media worker | VideoText media worker | Already VideoText-owned where selected. |
| Progress, cancellation, timeout, orphan cleanup, stale recovery | Integra | Integra | Reuse with targeted reruns after executor swap. |
| Results UI, open/export, persistence/reopen | Integra | Integra | Reuse unchanged. |

## Non-negotiable proof requirements before migration

1. **No hidden SeminarText invocation.** Candidate-bound process/provenance
   evidence must show a normal selected Process journey invokes no SeminarText
   executable or module.
2. **Quality is not word count.** VideoText-native ASR must reproduce the
   known fuzzy-loop failure class or establish an evidence-backed equivalent
   detection/retry. A missing block of speech may never be “fixed” by deduping
   repeated text.
3. **Existing Process guarantees survive.** Reuse/invalidation and controlled
   failure → subsequent success must be repeated after an ASR executor change;
   historical SeminarText-backed PASS cannot be inherited.
4. **Topics remain Process review, not Knowledge.** A reviewed title must save,
   close, reopen and retain machine-topic provenance without creating
   Evidence/Knowledge acceptance.
5. **SRT is a formal boundary.** VideoText-native numbered SRT is the only SRT
   consumed by translation, Word Timeline, burn and media operations. The raw
   ASR artifact and any compatibility form must remain hash-linked.

## Existing but non-production VideoText transcript worker

`workers/videotext_transcript_worker.swift` was introduced by the historical
Core Alpha real-stage certification (commit `05e7760822c91f8aad99d5d8d627f7ebcbb9b04b`).
It compiles pinned VideoText sources and can emit a machine-unverified source
transcript checkpoint with native numbered SRT, TXT and Whisper JSON. This is
useful evidence that the pinned source component can produce the primary ASR
artifacts, but it is **not** the current Process runtime:

- it is invoked only by the historical Core Alpha harness;
- it is not packaged by `scripts/build_macos_app.sh` and is not selected by
  `user_media.run_job`;
- its contract stops at `SOURCE_TRANSCRIPT` and has no Integra reuse,
  Process-result persistence or current Candidate provenance integration;
- VideoText's `LocalWhisperRetryService` only retries tasks marked
  `low-confidence` or `implausible-text-rate`; it is not a fuzzy-loop detector.

It must therefore be treated as a source-level implementation asset, not as
proof of current user integration and not as a component to enable wholesale.

## Initial source-component run on the prior fuzzy-loop media

An exploratory, isolated source-component run used the pinned VideoText commit
`2e098d1705b6815628bee1e023f4742718eabf02` and the historical media identity
`9faa1c03460aad1e8867593d28db1f140d0c839879a569ac362cb6a5eaf6ce6c`
(`140.885333` seconds). The input was copied to a disposable private scratch
root; no owner source, current Candidate or Process record was altered.

The first completed VideoText project produced:

- 18 numbered SRT cues and a 184-word Russian TXT transcript;
- the formerly missing presentation/life-expectancy passage, including the
  approximately 71/76-year facts;
- no occurrence of the four-times-repeated SeminarText anchor phrase in the
  preserved failing transcript;
- a VideoText `transcription_quality.json` state of `ready` with zero review
  tasks.

This is positive evidence that VideoText's normal ASR can avoid the observed
failure on that media and that its native SRT boundary is usable. It is **not**
protective-retry equivalence: no loop occurred in this run, the quality report
did not reject it, and no retry ran. It is also not a packaged Candidate or an
Integra Process execution. The deterministic fuzzy-loop regression and the
three-video Candidate-bound shadow route remain mandatory.

## Phase 1 conclusion

The VideoText-only direction is technically plausible, but it is **not yet
proven**. The smallest first technical proof is a VideoText-native ASR shadow
route that may reuse the narrow artifact-production portion of the historical
worker, but emits the current Integra transcript/SRT provenance contract and is
run against the three already-compared real Russian videos plus the known
fuzzy-loop regression. It must not replace the existing Process path or remove
SeminarText. The result decides whether the next bounded change is an adapter,
a fuzzy-loop quality/retry implementation, or a stop due to missing
equivalence.
