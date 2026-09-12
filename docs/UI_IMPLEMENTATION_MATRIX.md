# UI Implementation Matrix — Issue #76

Verified against Integra `main` at `9db46df0ab162f892092745dafda4c0530853549`,
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
| Local video/audio | Word Timeline | SeminarText | contract and source implementation exist | no production user-app dispatch path | SeminarText tests and Integra contract tests only | В разработке |
| Local video/audio | Topics and timecodes | SeminarText | pinned Topic worker exists; current user runtime instead uses non-authoritative deterministic grouping | no SeminarText user-app dispatch path | R6 certification worker evidence only | В разработке |
| Local video/audio | Review / Evidence / Canonical Knowledge | SeminarText | versioned contracts and validators exist | no end-to-end user-app authoring/review dispatch | contract tests; no user runtime smoke | В разработке |
| Local video/audio | Translation | VideoText / SeminarText fallback | VideoText production adapter exists in pinned source | no packaged Integra runtime path | component benchmark/probes only | В разработке |
| Local video | Burn subtitles, clips, social variants | VideoText | several component implementations exist; only subtitle burning has an Integra runtime | source-first `burn_subtitles` → owned local ffmpeg adapter | application-runtime and macOS smoke tests for subtitle burning; component probes for remaining VideoText features | Clips and social variants — В разработке |
| TXT / Markdown / DOCX / PPTX / text PDF | Detect format, native text extraction, page/slide locators | Integra document adapter | `integra_core.documents.extract_document` | Python API only; bridge path added by #76 | `test_documents.py` | Работает |
| PDF / image / scan | Detect that OCR is required | Integra document adapter | `extract_document` returns exact `content_mode` and OCR requirement | Python API only; bridge path added by #76 | `test_documents.py` | Работает |
| PDF / image / scan | Perform OCR | BookText | real BookText CLI exists remotely; Surya/Vision tools exist on reference Mac | no pinned BookText identity, versioned Integra contract, adapter, or bridge path | BookText has one narrow table-reconstruction unit suite; no Integra smoke | В разработке |
| DOCX / PPTX / PDF | Discover embedded media | Integra document adapter | extraction record contains hashed embedded-media metadata | Python API only; bridge path added by #76 | `test_documents.py` | Работает |
| DOCX / PPTX / PDF | Materialize extracted images | Integra document adapter | source-hash-verified `materialize_embedded_media` | source-first `execute-plan` → `application_runtime.execute_run` → `materialize_embedded_media`; app opens the new Integra-owned output directory and manifest | runtime, bridge and macOS build/smoke tests | Работает |
| Documents | Structure, chapters, TOC, topics, summary, terms, concepts, practices, Evidence, Knowledge, FAQ, tests | BookText / SeminarText / future Integra services | no complete production path in Integra | none | none end-to-end | В разработке |
| YouTube URL(s) / playlist | URL classification | Integra | deterministic URL shape classification added by #76 | capability service | planner tests | Работает (classification only) |
| YouTube URL(s) / playlist | Remote discovery/download/ingest | future YouTube adapter | offline playlist contracts exist; live API/download explicitly deferred | none | offline contract tests only | В разработке |
| Multiple local files | Detection, per-source capability and plan | Integra application service | centralized registry/planner added by #76 | capability/plan bridge | application-service tests | Работает |
| Collection | Cross-source alignment/common knowledge/summary/glossary | Integra + SeminarText | accepted contracts exist but no production authoring path from arbitrary user sources | none | contract tests only | В разработке |
| Completed validated package | Obsidian managed export | Integra | `publishing.preview_obsidian_export` / `publish_obsidian_export` | `package-preview` / `package-publish` | publication integration tests | Работает |
| Completed validated package | Filesystem-backed OneDrive publication | Integra | `onedrive.preview_onedrive_publication` / `publish_onedrive_package` | `package-preview` / `package-publish` | OneDrive integration tests | Работает; never claims cloud verification |
| Any | Learning, Marketing, social publishing | future services | not implemented | none | none | В разработке |

## Repository-truth conflicts retained

1. Issue #76 describes Integra as integrating BookText, but accepted Integra
   component state currently pins only SeminarText and VideoText. BookText is
   therefore not executable from production UI in this Issue.
2. The current user media path does not call the accepted VideoText component;
   it calls a real local ffmpeg/Whisper adapter. The UI identifies the real
   runtime and leaves VideoText-only outputs disabled.
3. The existing user-media topic grouping is not equivalent to the pinned
   SeminarText Topic Engine. The new source-first UI does not expose it as a
   completed Topics or Knowledge capability.
4. Live YouTube discovery/download and playlist ingest are explicitly deferred
   in accepted product truth. The UI represents the entry point but cannot
   execute it and labels it `В разработке`.
