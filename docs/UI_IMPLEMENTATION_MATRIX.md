# UI Implementation Matrix — Issue #76

Verified against Integra through Issue #117,
SeminarText at pinned clean commit `a94936cd77cde13561c97c804ece1ac1134e01a6`,
VideoText at pinned commit `2e098d1705b6815628bee1e023f4742718eabf02`,
and BookText remote `main` at `46396649214275eb18054b670a842bace02d02e1`.

`Работает` means that Integra has a real production implementation, a callable
application runtime path, and test/smoke evidence. A component implementation
without an Integra runtime path is not called working.

| Source type | Capability | Responsible component | Real production implementation | Callable runtime path before #76 | Test/smoke evidence | Final UI state |
|---|---|---|---|---|---|---|
| Local video | Copy-on-write import and hash verification | Integra | `integra_core.user_media.import_source` | `bridge.py import-media` (currently starts ASR immediately) | `test_user_media.py`; real synthetic-media smoke | Работает |
| Local audio | Copy-on-write import and hash verification | Integra | `integra_core.user_media.import_source` | `bridge.py import-media` (currently starts ASR immediately) | `test_user_media.py`; real synthetic-media smoke | Работает |
| Local video/audio | Media preparation and transcription | Integra local media adapter; VideoText is accepted capability owner but is not the packaged runtime | real `ffmpeg` + `whisper-cli` subprocess pipeline in `run_job` | background `process-media-job` | real Whisper smoke; `test_user_media.py` | Работает when runtime preflight passes; otherwise disabled with reason |
| Local video/audio | SRT subtitles | Integra local media adapter | real Whisper SRT artifact is produced | background `process-media-job`; artifact was not exposed as a result before #76 | real Whisper smoke | Работает after #76 artifact exposure |
| Local video/audio | Navigate timed transcript to owned source media | Integra macOS UI + closed bridge | persisted source-first run resolves the owned source file and parses its generated SRT | `media-navigation` → AppKit/AVPlayer cue seek | bridge end-to-end test; macOS build/smoke | Работает |
| Local video/audio | Improve audio | Integra local media adapter | owned `ffmpeg` subprocess writes an AAC/M4A artifact with deterministic loudness-normalization parameters and an exact source-hash record | source-first `execute-plan` → `process-plan` → `application_runtime.execute_run` → `user_media.run_job` | capability and application-runtime tests; macOS build/smoke | Работает when ffmpeg preflight passes; otherwise disabled with reason |
| Local video/audio with generated SRT | Create a selected time-range clip | Integra local media adapter + closed macOS bridge | owned `ffmpeg` renders MP4 only from exact persisted SRT cue boundaries; source, subtitles, locator, and clip list are persisted | `media-navigation` → user chooses a displayed SRT range → `create-media-clip` | bridge end-to-end test; macOS build/smoke | Работает when ffmpeg preflight passes; thematic VideoText clips remain В разработке |
| Local Russian video/audio with generated SRT | Word Timeline | SeminarText / WhisperX alignment-only adapter | the existing SRT is passed to WhisperX 3.8.6; native word intervals and scores are retained, while unaligned words receive no invented interval | source-first `execute-plan` → `user_media.run_job` → `generate_word_timeline` → bundled Python 3.13 + WhisperX + pinned Russian model | real Russian synthetic-speech alignment smoke; bundled preflight; application-runtime dispatch test; macOS bundle smoke | Работает in the personal local build when the bundled Word Timeline runtime passes preflight; otherwise disabled with factual reason |
| Local video/audio with generated SRT | Topics and timecodes | SeminarText | pinned Topic Engine function composition is invoked by `integra_core.seminartext_runtime.generate_topics`; it accepts only `REVIEW_REQUIRED` drafts | source-first `execute-plan` → `application_runtime.execute_run` → `user_media.run_job` → `generate_topics` → packaged `seminartext_topics_worker.py` → exact personal-use Topic Engine module inside `Contents/Resources/runtime` | real local Russian-SRT/`gemma3:4b` smoke; bundled bridge end-to-end smoke; application-runtime dispatch test; runtime contract tests; macOS bundle preflight smoke | Работает in the personal local build when Ollama and the verified local model pass preflight; otherwise disabled with the factual missing-model reason |
| Local video/audio | Review / Evidence / Canonical Knowledge | SeminarText | versioned contracts and validators exist | no end-to-end user-app authoring/review dispatch | contract tests; no user runtime smoke | В разработке |
| Local video/audio | Translation | VideoText / SeminarText fallback | VideoText production adapter exists in pinned source | no packaged Integra runtime path | component benchmark/probes only | В разработке |
| Local video | Burn subtitles, clips, social variants | VideoText | several component implementations exist; only subtitle burning has an Integra runtime | source-first `burn_subtitles` → owned local ffmpeg adapter | application-runtime and macOS smoke tests for subtitle burning; component probes for remaining VideoText features | Clips and social variants — В разработке |
| TXT / Markdown / DOCX / PPTX / text PDF | Detect format, native text extraction, page/slide locators | Integra document adapter | `integra_core.documents.extract_document` | Python API only; bridge path added by #76 | `test_documents.py` | Работает |
| PDF / image / scan | Detect that OCR is required | Integra document adapter | `extract_document` returns exact `content_mode` and OCR requirement | Python API only; bridge path added by #76 | `test_documents.py` | Работает |
| PDF / image / scan | Perform OCR | BookText | pinned BookText `booktext.py` invokes Surya OCR; the Apple Vision QA executable is built from the exact pinned `VisionOCR.swift` source; Integra records actual page text/confidence and retains BookText TXT, Markdown, JSON, searchable PDF, raw Surya and review artifacts | source-first `execute-plan` → `application_runtime.execute_run` → `booktext_runtime.run_ocr` → bundled BookText worker → pinned `booktext.py` | BookText unit suite; bundled macOS runtime preflight; bundled real image OCR smoke with Surya + Apple Vision QA + TXT/PDF output | Работает when the personal local Surya runtime and required tools pass preflight; otherwise disabled with the factual reason |
| DOCX / PPTX / PDF | Discover embedded media | Integra document adapter | extraction record contains hashed embedded-media metadata | Python API only; bridge path added by #76 | `test_documents.py` | Работает |
| DOCX / PPTX / PDF | Materialize extracted images | Integra document adapter | source-hash-verified `materialize_embedded_media` | source-first `execute-plan` → `application_runtime.execute_run` → `materialize_embedded_media`; app opens the new Integra-owned output directory and manifest | runtime, bridge and macOS build/smoke tests | Работает |
| Documents | Structure, chapters, TOC, topics, summary, terms, concepts, practices, Evidence, Knowledge, FAQ, tests | BookText / SeminarText / future Integra services | no complete production path in Integra | none | none end-to-end | В разработке |
| YouTube URL(s) / playlist | URL classification | Integra | deterministic URL shape classification added by #76 | capability service | planner tests | Работает |
| Individual YouTube video | Remote download and handoff to selected media outputs | Integra local YouTube adapter | user-initiated local `yt-dlp` download into Integra-owned project storage; persisted URL, local runtime version and SHA-256 are then passed to the existing media runtime | source-first `execute-plan` → `application_runtime.execute_run` → `youtube_runtime.download_video` → `user_media.run_job` | adapter, planner, application-runtime and bridge end-to-end tests; real local `yt-dlp` public-video smoke | Работает when local `yt-dlp` and the selected downstream runtime pass preflight; otherwise disabled with reason |
| YouTube playlist | Remote discovery/download/ingest | future YouTube playlist adapter | offline playlist contracts exist; no live playlist runtime is connected | none | offline contract tests only | В разработке |
| Multiple local files | Detection, per-source capability and plan | Integra application service | centralized registry/planner added by #76 | capability/plan bridge | application-service tests | Работает |
| Collection | Cross-source alignment/common knowledge/summary/glossary | Integra + SeminarText | accepted contracts exist but no production authoring path from arbitrary user sources | none | contract tests only | В разработке |
| Completed validated package | Obsidian managed export | Integra | `publishing.preview_obsidian_export` / `publish_obsidian_export` | `package-preview` / `package-publish` | publication integration tests | Работает |
| Completed validated package | Filesystem-backed OneDrive publication | Integra | `onedrive.preview_onedrive_publication` / `publish_onedrive_package` | `package-preview` / `package-publish` | OneDrive integration tests | Работает; never claims cloud verification |
| Completed persisted run | Select package for publication | Integra macOS UI + closed bridge | bridge revalidates only persisted completed-run package outputs before the app presents a concrete project/source/package selector | `available-packages` → selected `package-preview` / `package-publish` | bridge end-to-end test; macOS build/smoke | Работает; no automatic “first result” selection |
| Any | Learning, Marketing, social publishing | future services | not implemented | none | none | В разработке |

## Repository-truth conflicts retained

1. BookText OCR is connected to the production UI only through the bundled
   local Surya/Apple Vision runtime. Higher-level BookText semantic workflows
   still have no Integra production authoring path.
2. The current user media path does not call the accepted VideoText component;
   it calls a real local ffmpeg/Whisper adapter. The UI identifies the real
   runtime and leaves VideoText-only outputs disabled.
3. The legacy user-media deterministic grouping is not equivalent to the
   pinned SeminarText Topic Engine and is not used for selected source-first
   Topics. The available integration persists only SeminarText-produced
   `REVIEW_REQUIRED` drafts; it does not create or accept Knowledge.
4. Live individual-video ingest is a local, user-initiated `yt-dlp` runtime;
   it does not discover or process playlists. Playlist ingest remains
   `В разработке`.
