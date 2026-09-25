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
| Fuzzy/contextual loop quality gate and protective retry | SeminarText CLI | VideoText or an explicit Integra quality layer | No proven equivalent. This is a required implementation/proof boundary. |
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

## Phase 1 conclusion

The VideoText-only direction is technically plausible, but it is **not yet
proven**. The smallest first technical proof is a VideoText-native ASR shadow
route that emits the current Integra transcript/SRT provenance contract and is
run against the three already-compared real Russian videos plus the known
fuzzy-loop regression. It must not replace the existing Process path or remove
SeminarText. The result decides whether the next bounded change is an adapter,
a quality/retry implementation, or a stop due to missing equivalence.
