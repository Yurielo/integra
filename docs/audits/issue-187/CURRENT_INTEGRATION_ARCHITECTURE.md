# Current integration architecture — Issue #187 audit

**Audit basis:** Integra `7de26af33037fc3236c92938fe5bdaf62dc1e963`; active
Issue [#187](https://github.com/Yurielo/integra/issues/187); canonical
VideoText `1a2c1b7891c0e31c66c5ec6198f9ab579773c66b`; local SeminarText
`9ce002236a974c7766a43905b85127dda8143705`; BookText
`974cfbfc3e39afab9f0566d371e604d2571e2c9c`.  Source working-tree changes
were not used as evidence. VideoText's ordinary local directory was an empty
Git shell, so its read-only audit used a fresh clone of the canonical GitHub
repository.

## Evidence-based architecture, not the intended target

Integra is a local control plane: it owns source registration, project/run/job
records, artifact directories, status/recovery, native UI, result persistence,
cross-navigation and managed publication. It invokes pinned source capability
bytes through local files and subprocess workers; it does not use a network
service. This is implemented in `integra_core/application_runtime.py`,
`integra_core/user_media.py`, `integra_core/capabilities.py`, and the JSONL
contract in `state/worker_protocol_v1.json`.

The accepted architecture says this should be capability-specific rather than
a new monolith (`docs/architecture/INTEGRA_ARCHITECTURE.md`). The current native
Process route is nevertheless a hybrid, and differs from the earlier R5 target:

```text
local media / selected YouTube video
  -> Integra detect_source + build_plan + application_runtime
  -> Integra import_source + JobStore/run record
  -> asr_reuse.transcribe_or_reuse
  -> SeminarText CLI (chunking, VAD, Whisper decoding, loop-quality retry)
  -> Integra transcript.json / readable text / provenance
  -> Integra WhisperX worker -> word_timeline.json
  -> SeminarText Topic Engine -> topics.json (REVIEW_REQUIRED)
  -> Integra TranslateGemma -> translation.json + translation.txt
  -> optional VideoText worker -> burn subtitles / clip / speed / audio analysis
```

The exact active ASR call is `integra_core/user_media.py:run_job` through
`integra_core/asr_reuse.py` and `integra_core/seminartext_asr_runtime.py`.
The latter is an owned-process adapter, not an alternative ASR algorithm: it
verifies the pinned SeminarText checkout/bytes and invokes `seminartext
project-transcribe`. Its documented implementation description explicitly
keeps chunking, VAD, decoding retries and text cleaning in SeminarText.

## Stage-level ownership

| Stage | Actual runtime owner | Integra's role | Evidence |
| --- | --- | --- | --- |
| Source registration/import and ordered plan | Integra | owns IDs, hashes, copy-on-write inputs and jobs | `integra_core/capabilities.py`, `application_runtime.py` |
| Audio preparation and ASR | SeminarText | verifies pin, executes and retains result/provenance/reuse record | `seminartext_asr_runtime.py`, `asr_reuse.py` |
| Segmentation, VAD, repeated-text/loop safety, retry | SeminarText | surfaces a fail-closed quality result | `seminartext_asr_runtime.py` |
| SRT/TXT assembly and Process artifact persistence | Integra + SeminarText output | serializes Process output and preserves raw/clean/review paths | `user_media.py` |
| Word-level timing | Integra-owned WhisperX adapter | consumes exact SRT and emits a distinct timeline artifact | `word_timeline_runtime.py` |
| Topic drafts/timestamps | SeminarText Topic Engine | runs a detail adapter; retains `REVIEW_REQUIRED` | `seminartext_runtime.py`, `seminartext_topic_detail_adapter.py` |
| Topic/transcript Evidence and canonical-Knowledge review paths | SeminarText pinned review/evidence runtime | creates Integra-owned request/result envelopes | `seminartext_evidence_runtime.py`, `seminartext_topic_review_runtime.py` |
| Translation | Integra TranslateGemma | owns inference/provenance and readable TXT | `translategemma_runtime.py`, `topic_translation.py` |
| Clips, burned subtitles, speed, audio analysis | VideoText worker | owns lifecycle/provenance around a pinned VideoText worker | `videotext_media_runtime.py`, `media.py` |
| Documents/native extraction | Integra | owns safe native extraction and document artifact | `document_extract.py`, `application_runtime.py` |
| OCR when selected/required | BookText runtime | invokes a pinned CLI and records a normalized OCR manifest | `booktext_runtime.py`, `workers/booktext_ocr_worker.py` |

## What is actually integrated

1. **VideoText media functions are real runtime dependencies.** The package
   build compiles a worker from the pinned VideoText Swift sources
   (`scripts/build_videotext_worker.sh`). `videotext_media_runtime.py` invokes
   it for media operations and verifies the runtime manifest and result.
2. **SeminarText is a real runtime dependency for normal Process ASR, Topics,
   Evidence, word alignment support and reviewed Knowledge inputs.** The app
   package copies verified pinned SeminarText modules and its CLI
   (`scripts/build_macos_app.sh`).
3. **BookText OCR is integrated only at the bounded OCR-provider level.** The
   app bundles an exact BookText entrypoint and Vision helper, and the worker
   invokes BookText's raw OCR path. Its rich canonical document/review package
   is not imported as Knowledge.
4. **Worker boundaries exist, but are mixed in maturity.** `state/worker_protocol_v1.json`
   defines local JSONL for the R3 adapter boundary; native user-media execution
   currently also uses direct bounded Python adapters. The standalone
   `workers/videotext_transcript_worker.swift` is an existing proof worker, not
   the normal Process executor.

## Important negative findings

- The current normal Process route **does call SeminarText at execution time**.
  A claim of VideoText-only Process would be false today.
- VideoText has `SegmentedWhisperTranscriber`, `TranscriptionQualityService`,
  `LocalWhisperRetryService`, `SRTService`, and `HybridTopicAdapter` in source,
  but Integra's normal route does not invoke them for ASR or Topics.
- The current local source fixture used in some Owner/Test journeys cannot be
  treated as an ASR-quality finding. It is insufficient evidence to attribute
  repeated text to source media, fixture construction, ASR, transcript assembly,
  cleaning, or Knowledge processing. The existing #187 proof gate requires a
  separate fresh-run comparison on controlled media.
- BookText's standalone `docs/INTEGRA_OCR_ADAPTER_CONTRACT.md` remains
  `DRAFT`; it explicitly says compatibility is not a Knowledge import.

## Consequence for Issue #187

The evidence supports the documented result
`VIDEOTEXT_ONLY_PROCESS_NOT_YET_PROVEN`, not replacement or retirement of
SeminarText. The smallest coherent next proof is the already-defined #187
Stage-A fresh VideoText ASR route with exact output mapping and no SeminarText
process/module call, followed separately by topic compatibility and lifecycle
proof. No conclusion here changes K1/K2, CURRENT, or a source-product pin.
