# Source-product → Integra parity: current correspondence

Дата: 2026-09-22. Статус: `SOURCE_PARITY_RECONCILED`.

Проверенный `Yurielo/integra main`: `2af7de54964d267ff47267f9e43bb9c0b41973ac`.
Это documentation-only reconciliation инвентаря #129 с текущим main. Документ не
назначает roadmap, implementation, приоритеты или новую authority. Source
repositories, pins, CURRENT, Recovery #161/#162 и исторические отчёты не изменены.
Новых product tests, builds, Candidates, GUI-запусков или source processing нет.

## 1. Восстановленный результат #129

Сначала изучены существующие deliverables; новый широкий аудит не проводился.

| Источник #129 | Что установлено и как используется здесь |
| --- | --- |
| [Issue #129][i129] | OPEN. Поручение: сопоставить работающие source functions, actual runtime и UI; частичная доставка не закрывает всю интеграцию. Комментариев нет. |
| [SOURCE_CAPABILITY_INTEGRATION_MATRIX.md](SOURCE_CAPABILITY_INTEGRATION_MATRIX.md) | Основной инвентарь: 14 строк SeminarText, 17 VideoText, 13 BookText, включая research/non-production позиции. Повторное обследование source-продуктов заменено проверкой pins и изменений с этой точки. |
| [INTEGRA_PROJECT_AUDIT_2026-09-13.md](INTEGRA_PROJECT_AUDIT_2026-09-13.md) | Исторический pre-delivery snapshot. Его «в процессе» не переносится на main после доставки. |
| [INTEGRA_AUDIT_REVIEW_2026-09-13.md](INTEGRA_AUDIT_REVIEW_2026-09-13.md) | Поправки: component/unit evidence не равно GUI; Topics low не доказывает hierarchy; loudnorm не равно dereverb; filesystem OneDrive не равно cloud confirmation. |
| [INTEGRA_COMPLETION_PLAN_2026-09-13.md](INTEGRA_COMPLETION_PLAN_2026-09-13.md) | Сохраняет остаток работ и ссылки на доставку #131/#132/#134/#136. Использован как historical correspondence, не как новая очередь реализации. |
| [PR #131][p131] | MERGED; merge `a903b7976b194a7e430bd70bcc2c7e1699d13f5d` — ancestor current main. Первая bounded delivery #129, не complete parity. В PR нет review/comment evidence сверх описания и repository deliverables. |
| [ISSUE_129_DELIVERY_EVIDENCE.md](ISSUE_129_DELIVERY_EVIDENCE.md) — **H129** | Исторические 590 tests, 0 skips; build; real bundled machine Evidence, clip/burn/speed/audio analysis, OCR страниц 1 и 3. Bundle digest `c6223561393974ca695b2b6c7bd18cacfb9bc127d8c2521bf3ddad08697b7529`. Здесь не повторялись. |
| [native-plan.png](evidence/issue129/native-plan.png), [native-results.png](evidence/issue129/native-results.png) | Сохранённые screenshots просмотрены. Native results показывают COMPLETED, speed/audio-analysis outputs и unavailable последующие действия. Это не evidence каждого диалога/функции. |
| [smoke_source_components_bundle.py](../scripts/smoke_source_components_bundle.py), [native_workflow_probe.py](../tests/native_workflow_probe.py) | Изучены границы исторического proof: component script использует synthetic transcript/timeline, а native probe — injected selection и настоящий Execute/backend для speed/audio analysis. Scripts не запускались. |
| [Installed verification после #132][installed] — **H132** | Историческая установленная сборка main `6831887c8067df41ca8b624d1e00430d12879d7d`, bundle `81d5652a24ed31e3e061de2bcee658c0e143efe22dd7667c9106580d832c853a`: повторные component/native smokes. Это technical verification, не explicit human acceptance всех capabilities. |

Timeline #129 ссылается на #130, #131, #150, #157; PR search по #129 находит #131.
H132 включён потому, что на него прямо ссылается completion plan #129. Наличие
исходных `/tmp` logs старого smoke здесь не переаттестовано: доказательствами
служат сохранённый delivery report, screenshots, probe scope и GitHub record.

## 2. Pins и изменения после #129

| Source product | Pin в #129 | Current consumed pin | Correspondence |
| --- | --- | --- | --- |
| SeminarText | `a94936cd77cde13561c97c804ece1ac1134e01a6` | `13644d262776aacdf36221b9a9fc7ebd0a7c0737` | CLI изменён; Topic/Evidence/review/knowledge modules и schemas remain outside the Careful-ASR repair boundary. |
| VideoText | `2e098d1705b6815628bee1e023f4742718eabf02` | `2e098d1705b6815628bee1e023f4742718eabf02` | Source inventory #129 остаётся применимым к тому же pin. |
| BookText | `46396649214275eb18054b670a842bace02d02e1` | `46396649214275eb18054b670a842bace02d02e1` | Source inventory #129 остаётся применимым к тому же pin. |

Current identities проверены в [build script](../scripts/build_macos_app.sh) и
runtime modules. Сравнение **git objects** старого/нового SeminarText выявило
ровно пять изменённых файлов: CLI `seminartext`, README и три test files.
CLI SHA-256 вычислен из pinned Git object и совпадает с current build/runtime contract:
`30d8c1bd6f5ca717391b168cba71228a030009feaec4eb443bb1e76dab230a6c`.
Область — pinned versions, не произвольные последние upstream branches.

Новые source возможности относительно #129:

- SeminarText PR #123: contextual/fuzzy-loop quality gate с ordinal progression
  exemption вызывает существующий protective retry. Он входит в CLI, вызываемый
  Integra; отдельный packaged proof срабатывания именно fuzzy-trigger в этой
  reconciliation не установлен.
- SeminarText PR #124: `project-transcribe --combined-clear`, chronological
  ordering, optional with-sources и manifest, fail-closed incomplete inputs.
  В Integra нет вызывающего пути/выхода для combined-clear: её ASR adapter
  создаёт single-source project и вызывает `--only video_001`.
- SeminarText PR #125: headless execution controls. Это execution property,
  не дополнительный пользовательский output; в capability counts не добавлен.
- SeminarText PR #126: минимально разрешает `project-transcribe --careful`,
  сохраняя существующие careful-настройки и protective retry. В Integra это
  используется только за нейтральным выбором `Тщательный`; точное Candidate
  evidence записано в `PROCESS_V1_CAREFUL_ASR_MODE_PROOF.md`.

На стороне Integra diff от merge #131 до current main сохраняет byte-identical
`capabilities.py`, BookText runtime/worker, VideoText media/subtitle workers,
SeminarText Evidence/review adapters, #129 matrix/delivery report/screenshots
и оба #129 smoke/probe scripts. Изменения затрагивают orchestration/reuse/shutdown,
native operations UI, active SeminarText CLI identity, Ollama/ffmpeg resolution,
Word Alignment diagnostics, packaging и Candidate/governance contracts.
Поэтому историческая работающая интеграция не объявлена отсутствующей;
исторический bundle PASS также не переносится автоматически на новую сборку.

Современное product evidence — **P156**: [финальные исправленные gates #156](WP3_PRIMARY_JOURNEY_STABILIZATION.md#corrected-mandatory-gates--all-bound-to-the-final-candidate),
[explicit owner acceptance][owner156] и [CURRENT v2](../state/current_product_baseline_v2.json).
Candidate `candidate-v1-c5851d168b116fed83109014519ebc01c0291e23705ac9d2ec0a4e5df2471960`,
bundle `90c6c816c7f4ec82b8a3393c46a5a96239ce7cbc16ba50a83677d78a0cdea8cb`:
local Russian video → transcript/SRT → aligned Word Timeline → Topics/timestamps
→ persisted accessible results → COMPLETED. Это ограниченная приёмка; она
не принимает secondary capabilities, Canonical Knowledge или все media/language cases.
Старый owner-rejected Candidate из того же report не используется как PASS.

## 3. Правила чтения матрицы

- `PARITY_PROVEN`: в явно ограниченном пользовательском результате есть production
  path, современный packaged proof и соответствующая owner acceptance. Это не
  побайтовая/семантическая эквивалентность двух разных ASR/Topic engines.
- `VERIFY_EXISTING`: нужный production path уже существует. Требуется проверка
  его указанной области на актуальном package и/или owner acceptance. Статус не
  обещает, что проверка пройдёт без дефектов, и не означает новую реализацию.
- `INTEGRATE_EXISTING`: source implementation существует, но соответствующий
  вызов/параметры/GUI/output не подключены в Integra. Adapter или recipe сами
  по себе не меняют этот статус.
- `REPAIR_INTEGRATION`: доказан дефект уже соединённого пути. В этой ограниченной
  сверке новых таких выводов нет; Recovery не переаудирован.
- `IMPLEMENT_MISSING`: нужной production-функции нет и в проверенном source
  inventory; это не потерянная интеграция существующей функции.
- `DEFERRED_BY_OWNER`: есть конкретная source capability и явная действующая
  граница deferral. Это не диагноз implementation. Недоступная кнопка сама по
  себе не доказывает owner deferral.
- `UNKNOWN`: source production capability или её достаточное evidence не
  установлены. Наличие prototype/schema/test не повышает статус.

**GUI:** «Да, static» — прослежен actual handler → bridge → production call;
это не новый GUI run. **Packaged:** H129/H132 — только явно названная historical
граница; P156 — только accepted primary scope. **Owner:** «нет записи» означает
отсутствие конкретной acceptance в использованном evidence, не owner rejection.
Частичные функции разбиты на отдельные строки, чтобы существующий путь не
скрывался за недостающим расширением. ID нужны только для correspondence/counts.

Все source entrypoints ниже взяты из #129, кроме явно отмеченного CLI delta.
Source paths относятся к pins §2. Integra paths — к snapshot main; сокращения:
`app` = `integra_core/application_runtime.py`, `media` = `integra_core/user_media.py`,
`GUI` = `macos/IntegraApp.swift`, `bridge` = `macos/Resources/bridge.py`.
Точки проверки correspondence: [app](../integra_core/application_runtime.py),
[media](../integra_core/user_media.py), [GUI](../macos/IntegraApp.swift),
[bridge](../macos/Resources/bridge.py), [media worker](../workers/videotext_media_worker.swift),
[translation/subtitle worker](../workers/videotext_translation_worker.swift),
[BookText worker](../workers/booktext_ocr_worker.py),
[Topic worker](../workers/seminartext_topics_worker.py),
[review adapter](../integra_core/seminartext_topic_review_runtime.py).

### SeminarText

| SOURCE PRODUCT | SOURCE CAPABILITY | SOURCE EVIDENCE | INTEGRA IMPLEMENTATION | GUI REACHABLE | PACKAGED E2E | OWNER ACCEPTED | CLASSIFICATION | GAP |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SeminarText | S01 — Normal local ASR → TXT/SRT, bounded Russian-video result | #129: CLI `process_record/run_whisper_piece`; current CLI pin | `app.execute_run → media.run_job → asr_reuse → seminartext_asr_runtime.transcribe → original CLI` | Да; native source/output/Execute | P156 | Да, P156 only | PARITY_PROVEN | Не обобщать на все языки, записи и отсутствие любых ASR ошибок. |
| SeminarText | S02 — Contextual-loop detection → protective retry | CLI delta #123: `quality_check`, `fuzzy_contextual_repetition`, ordinal exemption; source `test_asr_quality_gate.py` | Current CLI вызывается без переписывания detector/ASR policy | Автоматически внутри ASR | P156 выполняет CLI; trigger-specific packaged evidence не установлено | Приёмка primary не является отдельной приёмкой всех trigger cases | VERIFY_EXISTING | Source tests/исправление не заменяют evidence срабатывания retry в packaged path. |
| SeminarText | S03 — Clean/review derivative TXT | #129: CLI `clean_text/process_record` | `media.run_job` сохраняет `transcript_cleaned`, `transcript_quality_report`, ASR record; GUI output actions | Да, static | Нет отдельного current proof этих derivatives | Нет записи для всей этой области | VERIFY_EXISTING | Читаемость/полезность производных файлов отдельно от accepted raw transcript. |
| SeminarText | S04 — Careful ASR mode | #129; CLI `--careful/run_whisper_piece` | ASR adapter выбирает штатный project-transcribe path; careful selector отсутствует | Нет | Нет | Нет записи | INTEGRATE_EXISTING | Подключение параметра/пользовательского выбора, не новый ASR engine. |
| SeminarText | S05 — Optional pandoc DOCX | #129; CLI optional pandoc output | Не выдаётся как Integra result; ограниченный ASR environment не предоставляет pandoc | Нет | Нет | Нет записи | DEFERRED_BY_OWNER | General DOCX export явно deferred в [Product Definition §3](PRODUCT_DEFINITION.md#3-deferred-to-later-work); не считать существующим GUI export. |
| SeminarText | S06 — Ordered multiple local inputs | #129: `build_queue`, project source ordering | `app.execute_run` последовательно обходит source plans | Да, static: «Несколько файлов» | Нет current multi-source packaged proof | P156 только 1 source | VERIFY_EXISTING | Последовательная очередь есть; это не merged corpus/semantic alignment. |
| SeminarText | S07 — Zoom directory discovery | #129: `build_queue` | Нет Zoom-specific directory discovery в source detection/planner | Нет | Нет | Нет записи | INTEGRATE_EXISTING | Пользователь сейчас выбирает файлы; source discovery не подключён. |
| SeminarText | S08 — Single YouTube source → processing | #129: `project_add/project_transcribe/project_link_youtube` | Выбран Integra `youtube_runtime.download_video → app → media.run_job` | Да, static | Нет current proof; external availability не проверялась | Нет записи | VERIFY_EXISTING | Путь существует; источник/сеть/yt-dlp и actual output нуждаются в проверке. Source-owned project storage не переносится поверх Integra storage. |
| SeminarText | S09 — Native PDF/PPTX document text | #129: `project_documents` | Выбран `documents.extract_document → app`, OCR fallback отдельно B01 | Да, static | Нет современного отдельно bound proof | Нет записи | VERIFY_EXISTING | Проверить поддержанные native extraction cases; engine replacement сам по себе не gap. |
| SeminarText | S10 — Multi-source corpus | #129: `project_corpus` | Только alignment/domain contracts; нет runtime corpus output | Нет | Нет | Нет записи | INTEGRATE_EXISTING | Нужна связь с existing source corpus и completeness boundary; последовательная очередь её не заменяет. |
| SeminarText | S11 — Combined-clear chronological transcript + provenance | Current source CLI delta #124; `project_transcribe`, `tests/test_project_combined_clear.py` | ASR вызывает single-source `--only video_001`; combined flags/result/manifest в GUI path отсутствуют | Нет | Нет | Нет записи | INTEGRATE_EXISTING | Source capability появилась после #129; bundled CLI presence не означает, что функция доступна пользователю Integra. |
| SeminarText | S12 — Basic Topics/timestamps, low detail | #129: Topic Engine boundary/label functions | `media → seminartext_runtime.generate_topics → seminartext_topics_worker.run_topics(detail="low")` | Да | P156 | Да, drafts остаются REVIEW_REQUIRED | PARITY_PROVEN | Не Canonical Knowledge и не complete hierarchy. |
| SeminarText | S13 — Topic detail selection | #129: source granularity parameter | Worker фиксирует `low`; selector не передаётся | Нет для выбора detail | Нет | Нет записи | INTEGRATE_EXISTING | Подключить существующий параметр; evidence трёхуровневой hierarchy отдельно S23. |
| SeminarText | S14 — EN→RU transcript text translation | #129: `seminartext_translate.py` | Выбран VideoText worker, который поддерживает target; GUI call использует default `en` | Нет выбора RU target | Нет для EN→RU GUI journey | Нет записи | INTEGRATE_EXISTING | Backend translation существует, но требуемое направление не соединено с GUI. Реальный текущий translation path отдельно V05. |
| SeminarText | S15 — Topic translation | #129: `seminartext_translate.py` | Нет Topic translation call в `media`/bridge | Нет | Нет | Нет записи | INTEGRATE_EXISTING | Не подменять переводом transcript. |
| SeminarText | S16 — Subtitle burn/cut | #129: `subtitles_command/cut_command` | Выбран VideoText: V08/V09, `create-media-clip` и burn output | Да, static | H129 component; current whole path не доказан | Нет записи | VERIFY_EXISTING | Дублировать source engine не требуется; остаётся проверка уже соединённых путей. |
| SeminarText | S17 — Machine Evidence | #129: `evidence_foundation.promote_transcript/align_project/evidence_check` | Result action → `create-machine-evidence → seminartext_evidence_runtime.create_machine_evidence` | Да, static; общий registry Evidence disabled не отменяет result action | H129/H132 component с supplied synthetic transcript/timeline; не GUI E2E | Нет записи | VERIFY_EXISTING | Пройти actual result continuation; machine_unverified не становится принятой семантикой. |
| SeminarText | S18 — Human verification of full transcript → Evidence | #129: human transcript verification; Evidence Foundation | `showTranscriptReview → apply-transcript-review → apply_human_transcript_review` | Да, static | Нет современного whole-path proof | Нет записи | VERIFY_EXISTING | Whole-TXT acknowledgement существует; selective correction editor не доказан этой строкой. |
| SeminarText | S19 — Canonical Word Timeline from supplied alignment, Evidence linkage | #129: Evidence canonicalizer; Word Timeline source tests | Integra real WhisperX создаёт aligned JSON; `seminartext_evidence_runtime` отдельно передаёт alignment original canonicalizer | Да, static: Word output и Evidence continuation | P156 для aligned output; H129/H132 для canonicalizer с synthetic alignment | Только aligned output P156, не Canonical Evidence linkage | VERIFY_EXISTING | Не смешивать два evidence levels. Source Evidence module сам не запускает WhisperX; end-to-end canonical continuation ещё не owner-proven. |
| SeminarText | S20 — Topic ACCEPT/REJECT and exact-fragment inclusion/exclusion | #129: `human_review_workflow.prepare/apply/apply_v2` | `prepare/apply-knowledge-review → seminartext_topic_review_runtime`; actual GUI dialog | Да, static | Нет современного whole-path proof | Нет записи | VERIFY_EXISTING | V1 compatible boundaries → Knowledge; V2 → reviewed fragments. Общий review menu disabled не означает отсутствие result dialog. |
| SeminarText | S21 — Extended Topic review/boundary operations | #129: RENAME/SPLIT/MERGE/DEFER и boundary tools | Integra decision validator разрешает только ACCEPT/REJECT; расширенные handlers/UI отсутствуют | Нет | Нет | Нет записи | INTEGRATE_EXISTING | Подключение supported source contracts, не создание новой semantic authority. |
| SeminarText | S22 — Compatible V1 Canonical Knowledge and managed vault output | #129: `project_knowledge_bridge.compile_documents/export_project` | Review adapter вызывает original bridge; reviewed package → managed publisher | Да, static, после совместимого review | Нет современного полного review→knowledge→export proof | Нет записи | VERIFY_EXISTING | Не весь Knowledge Studio; V2 fragments не компилируются автоматически в Canonical Knowledge. |
| SeminarText | S23 — Production three-level semantic hierarchy | #129/re-audit: production hierarchy не доказана | Domain hierarchy contracts; actual worker low only | Нет complete hierarchy | Нет | Нет записи | UNKNOWN | Нельзя выводить working source capability из параметра detail или schemas. |
| SeminarText | S24 — Automatic concepts/relations / Assistant / Learning / Marketing from research schemas | #129: schemas, benchmark/Gold/research scripts; не production engine | Domain/governance material и unavailable entries | Нет | Нет | Нет записи | UNKNOWN | Не считать source-function, которую можно просто подключить. Это сгруппированная non-production позиция старого инвентаря. |

### VideoText

| SOURCE PRODUCT | SOURCE CAPABILITY | SOURCE EVIDENCE | INTEGRA IMPLEMENTATION | GUI REACHABLE | PACKAGED E2E | OWNER ACCEPTED | CLASSIFICATION | GAP |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| VideoText | V01 — ASR/VAD/segmented retries | #129: `WhisperCLITranscriber`, `SegmentedWhisperTranscriber` | Current selected ASR owner — SeminarText, S01/S02; VideoText recognizer не запускается вторым проходом | Да, через выбранный owner | P156 для common Russian-video result, не VideoText algorithm parity | Только common primary result | VERIFY_EXISTING | Specific VideoText retry/quality behavior не аттестовано как эквивалентное. Это выбранная композиция, не доказанная потеря всего ASR. |
| VideoText | V02 — Source language/quality/review diagnostics | #129: `LanguageDetectionService`, `TranscriptionQualityService`, `HumanReviewService` | Integra имеет собственную quality/review composition; все source-specific reports/controls не вызваны | Частично: общие ASR/review действия | Нет source-specific whole-path proof | Нет записи | INTEGRATE_EXISTING | Не объявлять source diagnostics перенесёнными только из-за другого quality gate. |
| VideoText | V03 — SRT parse/normalize/write in primary path | #129: `SRTService` | `videotext_subtitles → bundled --subtitle-request → original service`, ASR emits persisted SRT | Да, primary output | P156 | Да, SRT в P156 | PARITY_PROVEN | Только primary SRT scope; clip/speed operations отдельно V04. |
| VideoText | V04 — Clip/retime SRT | #129: `SRTService`; bundled worker operations `clip/speed` | Transport/worker operations есть; пользовательский связанный SRT output не подключён | Нет отдельного output | Нет современного GUI proof | Нет записи | INTEGRATE_EXISTING | Executable worker entrypoint не равен native user journey. |
| VideoText | V05 — Actual transcript translation, current EN-target JSON output | #129: `TranslationAdapter` | `media.run_job → videotext_runtime.translate(target="en") → bundled worker → TranslationAdapter` | Да, static: selected Translation → open JSON | Нет современного secondary packaged proof | Нет записи | VERIFY_EXISTING | Existing callable path; local model, корректный исходный язык/непустой перевод и качество требуют проверки. |
| VideoText | V06 — User language choice and readable translated TXT/SRT | #129/audit: RU/EN translation and SRT facilities | Worker target parameter есть; GUI не передаёт выбор и сохраняет только translation JSON | Нет для полной области | Нет | Нет записи | INTEGRATE_EXISTING | Не объявлять отсутствующим весь перевод из-за недостающей выдачи/controls. |
| VideoText | V07 — AI Topics/cache, selected-engine correspondence | #129: `HybridTopicAdapter`, `OllamaTopicProvider` | Выбран SeminarText Topic Engine, S12; source-specific cache не доказан | Да для basic topics | P156 только selected SeminarText path | Да только basic result, не VideoText engine/cache | VERIFY_EXISTING | Engine/cache equivalence не доказана; отсутствие второго engine не требует автоматического дублирования. |
| VideoText | V08 — Exact video clip by SRT bounds | #129: `FFmpegAdapter.cutAccurate` | GUI `createSRTClip → create-media-clip → local_audio_clip → videotext_media_runtime.cut` | Да, static | H129/H132 real bundled clip; не current native-dialog E2E | Нет записи | VERIFY_EXISTING | Audio-only clip остаётся отдельным legacy compatibility path; thematic selection отдельно V16. |
| VideoText | V09 — Subtitle burn with current defaults | #129: `FFmpegAdapter.burnSubtitles` | Selected burn → `media → videotext_media_runtime → compiled original adapter` | Да, static | H129/H132 real component; current mixed-output journey не доказан | Нет записи | VERIFY_EXISTING | Исторический topics+burn defect исправлен #131; текущая ветка выполняет обе операции. Новый defect не установлен. |
| VideoText | V10 — Source subtitle style controls | #129: burn/style capability | Worker request не принимает style; используются source defaults | Нет выбора style | Нет | Нет записи | INTEGRATE_EXISTING | Расширение уже подключённого burn, не новый renderer. |
| VideoText | V11 — 1.25× video | #129: `FFmpegAdapter.adjustSpeed` | Selected `speed_video → media.run_job → media worker(speed_factor=1.25)` | Да, static; historical real Execute probe | H129/H132 native probe, injected selection; не current Candidate | Нет записи | VERIFY_EXISTING | Реальное производство файла уже было доказано исторически; modern Candidate/owner proof отсутствует. |
| VideoText | V12 — Arbitrary speed + corresponding retimed SRT | #129: `adjustSpeed`, `SRTService` | Worker допускает 0.5–2; application фиксирует 1.25; paired SRT output отсутствует | Нет полной области | Нет | Нет записи | INTEGRATE_EXISTING | Параметры и output composition, не отсутствующий source algorithm. |
| VideoText | V13 — Loudness/noise/pause measurements | #129: `AudioEnhancementAdapter.analyze` | Selected `audio_analysis → media worker → original analyze` | Да, static; historical Execute probe | H129/H132 native/component evidence | Нет записи | VERIFY_EXISTING | Измерения не доказывают dereverb. |
| VideoText | V14 — Static blur | #129: `FFmpegAdapter.applyStaticBlur` | Recipe contract only; media worker dispatch не содержит blur | Нет | Нет | Нет записи | INTEGRATE_EXISTING | Source implementation есть; контролы/runtime отсутствуют; source range 1–30. |
| VideoText | V15 — Watermark | #129: `FFmpegAdapter.applyWatermark` | Recipe only; нет worker operation | Нет | Нет | Нет записи | INTEGRATE_EXISTING | Нужны supported source limits, input and user controls. |
| VideoText | V16 — Topic/quote-driven clipping | #129: `createTopicFragment/createQuoteFragment`, `QuoteRangeMatcher` | Есть только SRT-range action; thematic clips entry unavailable | Нет semantic selection journey | Нет | Нет записи | INTEGRATE_EXISTING | Не путать existing interval cut и связку «тема/цитата → clip». |
| VideoText | V17 — Filler candidates and explicit muting | #129: `FillerWordService`, `muteAudioIntervals` | Recipe only | Нет | Нет | Нет записи | INTEGRATE_EXISTING | Token alignment, review/mute decisions и runtime не соединены. |
| VideoText | V18 — Dereverb/audio enhancement | #129: `AudioEnhancementAdapter.enhance` | Integra `enhance_audio` вызывает собственный FFmpeg loudnorm, не source enhance | Нет source dereverb | Нет | Нет записи | INTEGRATE_EXISTING | Source-specific separator/models, runtime/control; loudnorm не является parity. |
| VideoText | V19 — Speech synthesis/dubbing | #129: `SpeechSynthesisAdapter.synthesize` | Recipe only; нет production worker dispatch | Нет | Нет | Нет записи | INTEGRATE_EXISTING | Voice/rubberband dependencies и actual user path не подключены. |
| VideoText | V20 — Output duration/stream QA | #129: `strictValidationReport` | Media worker вызывает original validation перед promotion output | Автоматически внутри V08/V09/V11 | H129/H132 component outputs; не current secondary E2E | Нет записи | VERIFY_EXISTING | Уже реальная проверка производимых файлов, не только schema/test. |
| VideoText | V21 — Store/history/reuse/cancel lifecycle correspondence | #129: source Store/history/recovery/cancellation | Integra сохраняет own projects/runs; `asr_reuse`, `shutdown_runtime`; original store не подменяет владельца данных | Да, static: history/retry/cancel | Исторические #132/#134; P156 только bounded recovery sanity | Только primary #156; полного Recovery acceptance нет | VERIFY_EXISTING | Full source lifecycle parity не доказана. #161/#162 остаются отдельной незавершённой работой; их changes здесь не включены. |

### BookText

| SOURCE PRODUCT | SOURCE CAPABILITY | SOURCE EVIDENCE | INTEGRA IMPLEMENTATION | GUI REACHABLE | PACKAGED E2E | OWNER ACCEPTED | CLASSIFICATION | GAP |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BookText | B01 — PDF/image Surya OCR | #129: `prepare_pages/recognize_pages_surya` | `app → booktext_runtime.run_ocr → bundled worker → original booktext.main` | Да, static | H129/H132 real PDF OCR, не current GUI E2E/все images | Нет записи | VERIFY_EXISTING | External models/tools, OCR quality и actual GUI journey требуют проверки; функция не отсутствует. |
| BookText | B02 — Include/exclude original pages | #129: `parse_page_spec/choose_pages` | Native OCR-page dialog → plan-bound options → actual CLI | Да, static | H129/H132 pages 1,3 excluding 2; dialog interaction не автоматизирована | Нет записи | VERIFY_EXISTING | Original numbering сохранена; selection не удаляет страницы исходника. |
| BookText | B03 — TXT/MD/JSON/page artifacts | #129: original output files | `_booktext_outputs → GUI` открывает реальные произведённые файлы | Да, static | H129/H132 OCR outputs; нет current whole-path proof | Нет записи | VERIFY_EXISTING | Отдельная приёмка читаемости/полноты; доступный файл не равен качественному OCR. |
| BookText | B04 — Optional searchable PDF | #129: `create_searchable_pdf` | Worker объявляет файл только при наличии; GUI output action | Да, если файл произведён | H129 report: PDF generated; не современный proof | Нет записи | VERIFY_EXISTING | Text layer OCRmyPDF/Tesseract, не Surya; optional failure не success. |
| BookText | B05 — Vision QA / review outputs | #129: `vision_qa_page`, Vision helper | Worker QA status + raw/review files; GUI open actions | Да для inspection | H129 report: QA completed; не quality certification | Нет записи | VERIFY_EXISTING | Interactive OCR correction editor не доказан; loaded reused Surya model не аттестуется только hash локального файла. |
| BookText | B06 — Raw geometry/words/paragraphs/tables/lists | #129: Vision output | Raw output retained/openable; normalized Integra blocks page-level | Да для raw inspection | Только historical raw output scope, не region navigation | Нет записи | VERIFY_EXISTING | Word/region navigation не построена; сырые координаты не объявлены нормализованными ссылками. |
| BookText | B07 — DjVu | #129: `render_djvu_page` | Нет source type/locator/GUI execution path | Нет | Нет | Нет записи | INTEGRATE_EXISTING | Source function есть; требуется её интеграция. |
| BookText | B08 — Ordered multi-image book | #129: multi-input CLI | Integra создаёт separate sources вместо одной упорядоченной книги | Нет для book composition | Нет | Нет записи | INTEGRATE_EXISTING | Не считать multiple-file queue эквивалентом единого book. |
| BookText | B09 — Illustrations extraction/descriptions | #129: `detect_visual_regions/mask_and_extract_visuals/describe_visual` | Worker задаёт `--raw-ocr --no-descriptions`; это не тот же путь, что native embedded-image extraction | Нет полной source capability | Нет | Нет записи | INTEGRATE_EXISTING | Existing source logic не соединена; local model preflight/visual proof отсутствуют. |
| BookText | B10 — Legacy Tesseract OCR selection | #129: source CLI alternative OCR | Worker фиксирует `--ocr surya`; selector отсутствует | Нет | Нет | Нет записи | INTEGRATE_EXISTING | Не заявляется равенство качества двух движков. |
| BookText | B11 — General frequency-table reconstruction | #129: четыре tests узкого prototype, не production table extractor | Нет general production path | Нет | Нет | Нет записи | UNKNOWN | Узкий prototype нельзя считать готовым общим source capability. |
| BookText | B12 — Semantic chapters/outline | #129: production algorithm не найден при source audit | Registry `document_outline` unavailable; извлечённая структура страниц — другая функция | Нет | Нет | Нет записи | IMPLEMENT_MISSING | Нет готовой функции для переноса; реализация отсутствует в source inventory, не потеря интеграции. Это не разрешение начать её разработку. |
| BookText | B13 — Hybrid experimental scripts | #129: research only | Production path не доказан | Нет | Нет | Нет записи | UNKNOWN | Не включать research в перечень доказанно работающих функций. |

## 4. Количество позиций по classification

Единица подсчёта — одна строка матрицы с ID. Исходные 44 строки #129 разделены
там, где смешивали working path и missing extension; добавлен current CLI delta.
Повторяющиеся outcomes разных source-products остаются в каждом соответствующем
product inventory; сумма не является количеством независимых user journeys.
S23/S24/B11/B12/B13 — пять явно non-production/unproven позиций старого инвентаря,
а не пять доказанно работающих source functions.

| CLASSIFICATION | SeminarText | VideoText | BookText |
| --- | ---: | ---: | ---: |
| PARITY_PROVEN | 2 | 1 | 0 |
| VERIFY_EXISTING | 11 | 9 | 6 |
| INTEGRATE_EXISTING | 8 | 11 | 4 |
| REPAIR_INTEGRATION | 0 | 0 | 0 |
| IMPLEMENT_MISSING | 0 | 0 | 1 |
| DEFERRED_BY_OWNER | 1 | 0 | 0 |
| UNKNOWN | 2 | 0 | 2 |
| Всего inventory positions | 24 | 21 | 13 |
| Из них source production capability / выбранный equivalent outcome по #129 и CLI delta | 22 | 21 | 10 |

Нули `REPAIR_INTEGRATION` означают отсутствие нового доказанного defect verdict
в этой сверке, не доказательство безошибочности. `VERIFY_EXISTING` не означает
полную функциональную parity за пределами scope строки. Deferral не выводился
из greyed-out controls; blanket deferral OCR/media из старого Product Definition
не использован для сокрытия последующей реальной доставки #129.

## 5. Фактические ответы на четыре вопроса

**1. Какие работающие source возможности уже реально интегрированы?**

Современный accepted результат — normal local Russian ASR/transcript/SRT,
aligned Word Timeline и basic Topics/timestamps с сохранёнными результатами.
Выбранные владельцы: SeminarText CLI/Topics, VideoText SRTService, Integra
WhisperX orchestration. Это P156; Canonical Evidence linkage не входит в эту
приёмку. H129/H132 дополнительно доказывают историческое фактическое выполнение
machine Evidence из supplied transcript/timeline, VideoText clip/burn/1.25×/
audio measurements, BookText selected-page OCR и произведённых ancillary files.
Они существуют в current production path, но не получили перенос current
packaged/owner PASS автоматически.

**2. Какие уже написаны/подключены и требуют проверки?**

26 позиций `VERIFY_EXISTING`: включая translation EN-target JSON, ordered
multi-file processing, single YouTube, native document extraction, derivative
TXT, Evidence continuations, full-TXT review, bounded Topic review, compatible
V1 Knowledge/export, video clip/burn/speed/audio QA, BookText OCR/pages/outputs.
Сюда также отнесены source-specific equivalence questions выбранных ASR/Topics
owners и полный lifecycle. Их existing path не нужно заново писать по причине
отсутствия modern proof. Недостающие расширения выделены отдельно: например,
V05 требует проверки, V06 — подключения language/output controls.

**3. Какие source возможности ещё не интегрированы?**

23 позиции `INTEGRATE_EXISTING`: careful mode, Zoom discovery, source corpus и
новый combined-clear, Topic detail/translation/extended review; source-specific
VideoText diagnostics, SRT clip/retime user output, language/style/speed controls,
thematic/quote clipping, blur/watermark, filler mute, dereverb и dubbing;
BookText DjVu, ordered image book, illustrations/descriptions и alternate OCR.
DOCX export отдельно явно deferred (S05). General hierarchy, concepts/research
и table/hybrid prototypes не объявлены готовыми source functions; semantic
chapters не найдены в source production inventory и не могут быть получены
простым «переносом».

**4. Что существенного Integra добавила сверх отдельных source-продуктов?**

| Добавление Integra | Actual implementation и граница proof |
| --- | --- |
| Единый native source-first workflow между компонентами | `GUI → bridge → capabilities.build_plan → app.execute_run`; собственные project/run/result records. P156 доказывает одну полную композицию, H129 — native media subset. Не каждый пункт меню является работающей студией. |
| Реальный WhisperX alignment перед downstream Evidence | `word_timeline_runtime` и packaged alignment worker связывают ASR/SRT с word timestamps. Source Evidence canonicalizer сам WhisperX не выполняет. Aligned output принят P156; дальнейшее canonical linkage требует отдельного proof. |
| Общие source IDs, provenance, ownership и copy-on-write migration | `projects_sources.py`, `project_lease.py`, `migration.py`; native results сохраняют source/run binding. Полный import wizard и все lifecycle cases не доказаны. |
| Объединение document extraction/BookText и native file results | `documents.py`, `app._materialize_embedded_images`, OCR fallback и page-bound result pointers. Это orchestration/native extraction, не BookText illustration description. |
| Единый reviewed package и безопасная публикация | `reviewed_result_package.py`, `publishing.py`, `onedrive.py`, actual `build-reviewed-package/package-preview/package-publish` GUI handlers. Добавлены collision protection/version/lease boundaries между source outputs; текущая whole-path owner acceptance отсутствует. OneDrive только filesystem-backed. |
| Межпродуктовые alignment/knowledge/media navigation contracts | `multi_source_alignment.py`, `knowledge.py`, `media.py`, `cross_navigation.py`: domain/index layer существует. Полный user-facing multi-source Knowledge Studio не доказан; это architectural addition, не готовый продуктовый результат. |
| Общий lifecycle, diagnostics и binding сборки к evidence | Integra-owned jobs/reuse/shutdown, `candidate_identity.py`, manifest и Word-worker diagnostics. Candidate binding — infrastructure, не самостоятельный user outcome и не proof полного Recovery. #161/#162 не изменялись. |

«Добавила» здесь означает фактическую интеграционную/архитектурную функцию;
каждая строка отдельно ограничивает пользовательский proof. Упомянутые
capabilities/контракты не превращаются в новые обязательства или roadmap.

## 6. Evidence limits и scope результата

#129 достаточен как исходный capability inventory: его deliverables найдены,
delivery status восстановлен, pins и current paths сопоставлены. Поэтому
результат `SOURCE_PARITY_RECONCILED`, хотя большинство secondary outcomes
ещё не имеют современного owner proof. Неизвестное отмечено в строках; ни один
adapter, registry flag, unit test или closed Issue не использован как замена
GUI/packaged/owner acceptance. Исторический общий R14 не распределён по строкам
нового runtime без соответствующего evidence.

Read-only checks: GitHub issue/timeline/PR records; current main; ancestry;
targeted diffs и pinned source Git objects; static GUI→bridge→worker tracing;
сохранённые reports/probes/screenshots. Ни product execution, ни перепроверка
source quality/экспериментальных algorithms не проводились. Изменение этой
задачи — только данный новый документ. Implementation и новые Issues не начаты.

[i129]: https://github.com/Yurielo/integra/issues/129
[p131]: https://github.com/Yurielo/integra/pull/131
[installed]: https://github.com/Yurielo/integra/pull/132#issuecomment-5655958350
[owner156]: https://github.com/Yurielo/integra/issues/156#issuecomment-5768296395
