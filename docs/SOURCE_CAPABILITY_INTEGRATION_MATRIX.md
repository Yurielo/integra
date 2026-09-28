# Source-product capability audit and Integra integration

Issue #129, exact Product Owner task of 2026-09-13. This inventory covers
user-facing operations, not every internal helper. Code and source tests were
inspected independently; source-test existence alone is not runtime proof.
All three GitHub main heads match the current Integra pins:

- SeminarText `a94936cd77cde13561c97c804ece1ac1134e01a6`
- VideoText `2e098d1705b6815628bee1e023f4742718eabf02`
- BookText `46396649214275eb18054b670a842bace02d02e1`

Source repositories remain read-only. Duplicate implementations are not imported
when an existing selected owner already serves the same requirement. Source
workflow/storage control is not substituted for Integra project/job ownership.

## SeminarText

Paths are relative to the pinned source unless prefixed `Integra:`.

| Capability / source implementation | Integra task and actual path | Remaining gap |
|---|---|---|
| ASR, VAD, 300-second chunks, retry, raw/clean/review TXT and SRT: `seminartext:process_record/run_whisper_piece` | Transcription → `seminartext_asr_runtime.transcribe` calls original CLI | Careful-mode option and optional pandoc DOCX not exposed |
| Zoom directory/ordered source queue: `seminartext:build_queue` | Multiple-source plans run sequentially in application services | Zoom-specific directory discovery absent |
| YouTube/project source ingestion: `project_add/project_transcribe/project_link_youtube` | Integra own YouTube and project adapters | Source-owned project storage deliberately not reused directly |
| Native PDF/PPTX content: `project_documents` | Integra document adapter/BookText | Equivalent coverage; no second extraction engine needed |
| Multi-source corpus: `project_corpus` | R8C alignment contracts only | No runtime corpus output; skip-missing legacy behavior needs completeness guard |
| Topics and granularity: `seminartext_topics.py:make_topics` and boundary/label functions | The R6 worker retains its historical low-detail path; the normal Process uses the bounded `integra_core/seminartext_topic_detail_adapter.py` for the same pinned functions | `low` / `auto` / `high` are the only source-supported detail parameters; the normal Process default is `auto`, requested/executed provenance is persisted, and this does not claim a general semantic hierarchy |
| EN→RU text/topic translation: `seminartext_translate.py` | VideoText selected owner for transcript translation | Topic translation absent |
| SRT/burn/cut: `subtitles_command/cut_command` | VideoText selected owner | Duplicate engine intentionally not added |
| Machine Evidence: `evidence_foundation.promote_transcript/align_project/evidence_check` | `create_machine_evidence` → bridge → explicit native continuation action | Full TXT verification is optional; machine assurance stays `machine_unverified` |
| Human transcript verification | `apply_human_transcript_review` → original component | Selective correction revisions not exposed |
| Word Timeline | Real WhisperX adapter supplies alignment to original Evidence canonicalizer | Not falsely described as source module running WhisperX itself |
| Topic review V1/V2: `human_review_workflow.prepare/apply/apply_v2` | Actual pinned review adapter and native ACCEPT/REJECT dialog | RENAME/SPLIT/MERGE/DEFER and boundary-resolution UI not exposed |
| Canonical Knowledge, provenance, managed vault: `project_knowledge_bridge.compile_documents/export_project` | Actual review/knowledge adapter for compatible V1; safe managed package exporter | V2 exact fragments remain reviewed fragments, not canonical knowledge |
| Concept/relations schemas, benchmark/Gold/research scripts | Governance and validation only | Not evidence of working auto-concept mining, Assistant, Learning or Marketing |

Source evidence includes `test_machine_transcript_evidence`,
`test_evidence_foundation_e2e`, `test_word_timeline_mvp`,
`test_human_review_workflow`, `test_human_review_contract_v2`,
`test_project_knowledge_bridge`. Integra machine Evidence tests execute the real
pinned component with synthetic inputs and verify downstream review preparation.
Applicable rules: PR-001–008, PR-010, PR-012–014; no rule changes or conflicts.

## VideoText

| Capability / production implementation | Integra runtime/UI path | Remaining gap |
|---|---|---|
| ASR/VAD/segmented retries: `WhisperCLITranscriber`, `SegmentedWhisperTranscriber` | SeminarText is the explicitly selected current ASR owner | No duplicate recognition pass |
| Language/quality/review: `LanguageDetectionService`, `TranscriptionQualityService`, `HumanReviewService` | Existing Integra quality/review composition | Source-specific review UI not imported |
| SRT parse/write/clip/speed: `SRTService` | Bundled subtitle adapter → ASR and translation | Original source retained |
| RU/EN translation: `TranslationAdapter` | Bundled worker → selected translation output | Requires local model; not automatic semantic acceptance |
| AI topic analysis/cache: `HybridTopicAdapter`, `OllamaTopicProvider` | SeminarText chosen topic owner | Do not silently change semantic engine |
| Exact video clipping: `FFmpegAdapter.cutAccurate` | Media-navigation clip button → bridge → versioned media adapter | Source function is video-only; legacy audio compatibility remains separate |
| Subtitle burn/style: `FFmpegAdapter.burnSubtitles` | Selected burn output → media adapter | Source service replaces duplicate Integra video-render command |
| Speed derivative: `FFmpegAdapter.adjustSpeed` | Source-first `Видео со скоростью 1,25×` → media adapter | Arbitrary speed UI and accompanying retimed SRT not yet exposed |
| Audio measurements: `AudioEnhancementAdapter.analyze` | Source-first analysis output → media adapter | Measurements are not a claim of dereverberation |
| Blur: `FFmpegAdapter.applyStaticBlur` | Recipe contract only | Native controls/runtime absent; actual range 1–30 differs from broad recipe |
| Watermark: `FFmpegAdapter.applyWatermark` | Recipe contract only | Native controls/runtime absent; actual limits narrower than recipe |
| Topic/quote clipping: `createTopicFragment/createQuoteFragment`, `QuoteRangeMatcher` | SRT-range clipping exists | Semantic selection UI not integrated |
| Filler candidates/muting: `FillerWordService`, `muteAudioIntervals` | Recipe only | Token alignment and explicit mute decisions not connected |
| Dereverb: `AudioEnhancementAdapter.enhance` | Integra loudness normalization is NOT this function | Requires source-specific audio-separator/models; not marked equivalent |
| Dubbing: `SpeechSynthesisAdapter.synthesize` | Recipe only | Voice/rubberband preflight, control and runtime adapter absent |
| QA, duration, stream validation | Real media worker invokes `strictValidationReport` | Results promoted only after validation |
| Store/history/recovery/cancellation | Integra retains own lifecycle and copy-on-write migration | Replacing storage with source app would violate ownership |

Source probes cover SRT, speed, fragments, blur, watermark, filler, audio,
speech synthesis, recovery and lifecycle. New Integra media tests execute the
compiled service on synthetic media; no model/network workload is needed.

## BookText

| Capability / production implementation | Integra runtime/UI path | Remaining gap |
|---|---|---|
| PDF/image OCR: `prepare_pages`, `recognize_pages_surya` | Actual BookText CLI through bundled worker | Local dependencies/models still required |
| Include/exclude pages: `parse_page_spec`, `choose_pages` | Native OCR page selection → plan-bound options → original CLI | Original page numbers preserved; selection applies to OCR, not original file deletion |
| TXT/MD/JSON/page artifacts | Existing explicit output actions | None for produced artifacts |
| Searchable PDF: `create_searchable_pdf` | Optional file exposed only if present | Text layer is OCRmyPDF/Tesseract, not Surya; optional failure not called success |
| Vision QA/review: `vision_qa_page` and Vision helper | Raw QA and review outputs | Interactive OCR correction not integrated |
| Geometry/words/paragraphs/tables/lists | Raw Vision output retained | Normalized contract still page-level; no fabricated word/region correspondence |
| DjVu: `render_djvu_page` | Not integrated | Input contract/locators require extension |
| Ordered multi-image book | Source multi-input CLI exists | Integra treats files as separate sources |
| Illustrations: `detect_visual_regions/mask_and_extract_visuals/describe_visual` | Worker deliberately uses raw OCR/no descriptions | Local model preflight and real visual smoke needed |
| Legacy Tesseract OCR | Source CLI supported | No selector; not claimed equivalent quality |
| Frequency-table reconstruction | Narrow tested prototype | Not a general production table extractor |
| Chapters/outline | No production implementation found | Remains `В разработке`; cannot import nonexistent function |
| Hybrid experimental scripts | Research only | Excluded from production capabilities |

BookText source suite: 4 frequency-table tests passed during audit; it is not
an OCR end-to-end suite. New integration tests distinguish contract fixtures
from real OCR. An available local model hash cannot attest a reused Surya
server's actual loaded model; this limitation is explicit in provenance and
unsupported model overrides fail closed.

## Delivery truth

This is a capability-by-capability backlog, not a claim that all source features
are integrated. New operations require focused tests, full suite, native build,
actual bundled smoke and independent review before promotion. Missing operations
stay unavailable; semantic decisions, private datasets, real external
publication and source-repository changes are not authorized by this audit.
