# Capability ownership matrix — Issue #187 audit

Classifications use the five values required by Issue #187. **Runtime owner**
means the component actually called in Integra's current normal route, not a
component that merely has source code or a test.

| Capability | Existing implementation / evidence | Current runtime owner | Proposed runtime owner | Status and classification | Missing proof / gap |
| --- | --- | --- | --- | --- | --- |
| Source registration, hashes, ordered selection | Integra `capabilities.py`, `application_runtime.py` | Integra | Integra | Implemented; `INTEGRA_OWNED_REUSE` | Final exact-Candidate Process matrix only |
| Local media/audio ASR | SeminarText CLI adapter in `seminartext_asr_runtime.py` | SeminarText | VideoText `SegmentedWhisperTranscriber` | Active path is implemented; replacement is not; `REUSE_VIDEOTEXT` | Fresh Process execution on real controls, no SeminarText call, mapped artifacts |
| Audio extraction/segmentation/VAD | SeminarText current CLI; VideoText `WhisperCLITranscriber` / segmented transcriber | SeminarText | VideoText | VideoText source capability exists; `REUSE_VIDEOTEXT` | Packaged Integra adapter/preflight and selected-runtime proof |
| Loop/repeated-text detection and retry | SeminarText current quality record; VideoText `TranscriptionQualityService` and retry service | SeminarText | VideoText detector plus one bounded retry owner | Not equivalent yet; `IMPLEMENT_IN_VIDEOTEXT_OR_INTEGRA` | Detector false-positive, retry budget, safe-failure and successful-recovery proof |
| Clean/review text derivatives | SeminarText CLI artifacts; Integra persists paths | SeminarText + Integra | VideoText transcript plus small Integra projection | Not equivalent; `BOUNDED_ADAPTER` | Contract preserving raw, readable, review and provenance semantics |
| Timed numbered SRT | SeminarText ASR output; VideoText SRT worker used for selected normalization/media | SeminarText on normal ASR route | VideoText `SRTService` | Existing VideoText service; `REUSE_VIDEOTEXT` | VideoText-native ASR to Process SRT proof |
| Word-level timeline/source navigation | Integra `word_timeline_runtime.py`, bundled WhisperX | Integra | Integra | Implemented; `INTEGRA_OWNED_REUSE` | VideoText-SRT input and real alignment evidence |
| Topic drafts and timecodes | SeminarText Topic Engine; VideoText `HybridTopicAdapter` source | SeminarText | VideoText mapped through Integra | Source capability only; `REUSE_VIDEOTEXT` | Cue/time/output mapping, `REVIEW_REQUIRED`, normal-quality packaged proof |
| Topic review/save/reopen | SeminarText review runtime + Integra envelopes | SeminarText + Integra | Integra receipt/precedence over VideoText drafts | Existing semantics must be retained; `BOUNDED_ADAPTER` | Process-only review round trip; no Knowledge promotion |
| Transcript translation and readable TXT | Integra TranslateGemma (`user_media.py`) | Integra | Integra (current accepted runtime) | Implemented; `INTEGRA_OWNED_REUSE` | Final Process evidence; do not label active runtime VideoText |
| Topic translation | Integra `topic_translation.py`; separate selected output | Integra | Integra adapter | Partial journey; `BOUNDED_ADAPTER` | Candidate-bound selected-output/reopen proof |
| Burn subtitles, clip, speed, audio analysis | VideoText compiled worker via `videotext_media_runtime.py` | VideoText | VideoText | Implemented for supported selections; `REUSE_VIDEOTEXT` | Broader user-media Candidate matrix where applicable |
| Process jobs, cancellation, timeout, stale recovery, orphan cleanup | Integra `JobStore`, `user_media.py`, shutdown/operations code | Integra | Integra | Implemented control-plane responsibility; `INTEGRA_OWNED_REUSE` | Re-run only executor-sensitive cases after ASR swap |
| Multi-source ordering and partial failure | Integra sequential plan/run records | Integra | Integra | Ordering/failure base implemented; `INTEGRA_OWNED_REUSE` | Combined transcript/corpus with per-passage provenance: `BOUNDED_ADAPTER` |
| Selected-capability dependency closure | Integra capability registry/preflight | Integra | Integra | Incomplete; `IMPLEMENT_IN_VIDEOTEXT_OR_INTEGRA` | VideoText-only selection must not import/preflight SeminarText |
| Canonical Evidence, reviewed fragments, Concepts/Relations | SeminarText pinned contracts/runtimes | SeminarText + Integra presentation | SeminarText contract with Integra integration | Implemented K1/K2 scope; `BLOCKED_NO_EQUIVALENT` for VideoText replacement | VideoText has no evidenced canonical-evidence/knowledge equivalent |
| Document native text/page/slide extraction | Integra document pipeline | Integra | Integra | Implemented; `INTEGRA_OWNED_REUSE` | None for the bounded native formats |
| OCR selected pages | BookText worker/runtime (`booktext_runtime.py`) | BookText | BookText | Bounded OCR integrated; `BOUNDED_ADAPTER` | Retain per-block regions, review states and full BookText package, not only page text |
| BookText canonical document/review/exports | BookText CDM and review tools | BookText standalone | BookText artifact exchange into Integra | Available but not integrated; `BOUNDED_ADAPTER` | Accepted stable adapter, import/reopen/Knowledge tests |
| Cross-source knowledge integration/Obsidian export | Integra plus pinned SeminarText facts | Integra + SeminarText | Integra control plane | Implemented separately from #187; `INTEGRA_OWNED_REUSE` | Not in VideoText-only Process proof scope |

## Ownership rule

Reuse does not mean copying a source application's internals. The preferred
boundary is an exact pinned worker or a versioned artifact mapping; Integra
retains lifecycle, project records, provenance bindings, UI and publication.
This avoids making VideoText an owner of Knowledge or making SeminarText a
hidden owner of Process orchestration.
