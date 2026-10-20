# VideoText and SeminarText comparison — actual capability evidence

## Current conclusion

**VideoText cannot yet be declared the sole normal Integra Process runtime.**
It has credible source capabilities for a future replacement path, but the
complete #187 frozen Process proof matrix is not integrated or Candidate-bound.
The correct present outcome is `VIDEOTEXT_ONLY_PROCESS_NOT_YET_PROVEN`.

## Proven component strengths

| Area | VideoText evidence | SeminarText evidence | Current Integra use |
| --- | --- | --- | --- |
| ASR and audio preparation | `WhisperCLITranscriber`, `SegmentedWhisperTranscriber`; 5-minute segmentation, Russian long-form profile, VAD/no-VAD fallbacks | pinned `project-transcribe` through `seminartext_asr_runtime.py` | SeminarText |
| ASR quality/recovery | `TranscriptionQualityService` detects catastrophic, fuzzy-contextual and progressive repetition; segmented retry attempts | CLI quality record and protective retry; quality failure blocks downstream | SeminarText |
| SRT | `SRTService` parses, writes, validates timeline and preserves cue IDs | ASR emits source SRT | SeminarText output, VideoText normalization for selected media paths |
| Topics | `HybridTopicAdapter`, `OllamaTopicProvider`, topic files/review services | Topic Engine produces current Process draft shape and `REVIEW_REQUIRED` | SeminarText |
| Translation | Source `TranslationAdapter` exists | no active translation owner in normal route | Integra TranslateGemma, not either source product |
| Word alignment | no equivalent evidenced | Canonical evidence/word-timeline ecosystem; Integra packages WhisperX adapter | Integra WhisperX, aligned with SeminarText contracts |
| Canonical Evidence/Knowledge and semantic review | no equivalent evidenced | Evidence Foundation, review workflow, project knowledge bridge | SeminarText pinned runtime plus Integra K1/K2 presentation |
| Media transforms | clip/subtitle/speed/audio services | no equivalent claimed | VideoText worker |
| Project workflow/recovery | native Swift project/recovery services | governed transcript/evidence lifecycle | Integra owns orchestration; neither replaces it |

## Is VideoText-only Process feasible?

**Potentially, for the Process layer only, but not yet proven.** The existing
VideoText source covers the principal computational building blocks: real
Whisper execution, VAD-aware segmentation, quality detection, retry, SRT,
topics, translation, cancellation checks and project recovery. The #187
inventory and proof gate therefore correctly classify most replacement work as
reuse or a bounded adapter, not a rewrite.

It is not safe to infer equivalence from class/function names or component
tests. The current normal Process path has these unresolved boundaries:

1. a VideoText ASR worker must emit Integra's exact raw/clean/review/SRT/result
   contract with source/model/config provenance;
2. the fuzzy-loop detector needs a single bounded retry owner and proof that it
   neither silently loses speech nor treats genuine repetitions as errors;
3. VideoText topics must map to selected Process granularity and preserve cue
   IDs/times plus `REVIEW_REQUIRED` authority;
4. topic review, multi-source combined results and runtime dependency closure
   require explicit adapters or Integra-owned composition; and
5. the whole 47-MUST matrix must pass on one packaged Candidate with evidence
   that selected Process execution made no SeminarText process/module call.

## Unique SeminarText capability not covered by VideoText evidence

- Canonical Word Timeline/Evidence integration and assurance semantics;
- canonical Knowledge lifecycle, Concepts and Relations;
- governed human review and semantic authority contracts;
- exact source-oriented Evidence provenance schemas and validation;
- current Integra-compatible Topic draft/review binding; and
- the presently deployed Process ASR CLI/provenance contract.

This does **not** assert VideoText could never implement any of these. It says
functional equivalence is not evidenced in the audited source or #187 proof
matrix. VideoText-only Process must therefore not be generalized into
VideoText-only Knowledge, nor used to remove SeminarText.

## Recommended proof ordering, already aligned with #187

1. Freeze exact VideoText runner, controls, output mapping and retry budget.
2. Prove fresh ASR on the three established Russian controls with no cache or
   SeminarText call, then prove warm reuse.
3. Prove quality/recovery and genuine-repetition false-positive behavior.
4. Prove VideoText topic compatibility plus Process review/save/reopen.
5. Complete multi-source and selected-runtime closure, then execute the full
   exact-Candidate matrix and independent QA.
