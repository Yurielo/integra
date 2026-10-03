# Process v1 — Excel to current DoD scope reconciliation

Date: 2026-09-23. Status: traceability only. This document reconciles the completed Product Owner workbook with the canonical Process v1 DoD and current Completion Board. It is not a planning authority, scope decision, Board update, implementation authorization, or product evidence.

## Authorities and count arithmetic

Workbook authority: /Users/yurielokhin/Documents/integra/Integra_Process_v1_scope_selection.xlsx, SHA-256 22ddb5c5c46c850a2c5923607bab0b3ad5faef3de5ef20019255ba70c5718137. The Process v1 sheet has 68 selected rows. The BookText — отдельно sheet has 17 rows and every selection cell is blank.

Current scope authority: PROCESS_V1_DEFINITION_OF_DONE.md §§B–C, read with the canonical Process / Knowledge / Studio boundary document. This traceability document does not itself authorize a capability audit, build, Candidate, or Board-state change; the states below reflect separately recorded canonical evidence. N/A in CURRENT BOARD STATE means that the selection is not an active Process MUST Board row; it was not lost.

| Workbook selection read from file | Count |
| --- | ---: |
| MUST | 51 |
| OPTIONAL | 5 |
| LATER | 12 |
| Process-sheet total | 68 |
| Blank BookText rows | 17 |

The authoritative count is 51 MUST, not the earlier conversational recount of 52. Four approved scope corrections account for the present frozen scope:

| Excel row | Original | Current domain / priority | Effect |
| ---: | --- | --- | --- |
| 9 SRT-субтитры | MUST | STUDIO / LATER | −1 Process MUST |
| 14 Review TXT | MUST | KNOWLEDGE / LATER | −1 Process MUST |
| 21 Переведённый SRT | MUST | STUDIO / LATER | −1 Process MUST |
| 27 Иерархия тем | MUST | KNOWLEDGE / LATER | −1 Process MUST |

Therefore: 51 original MUST − 4 approved transfers = 47 current Process MUST. The original 12 LATER + 4 transfers = 16 LATER/out-of-phase. All five OPTIONAL rows are unchanged. The 17 blank BookText rows are PROCESS_DOCUMENTS / NOT_APPLICABLE, not LATER.

## Every Process-sheet row

| EXCEL ROW NUMBER | OWNER ITEM | ORIGINAL OWNER SELECTION | CURRENT DOMAIN | CURRENT PRIORITY | CURRENT BOARD ROW | CURRENT BOARD STATE | SCOPE-CHANGE AUTHORITY / REASON |
| ---: | --- | --- | --- | --- | --- | --- | --- |
| 1 | Локальное видео | MUST | PROCESS | MUST | Local video | DONE | Retained in DoD inputs. |
| 2 | Локальное аудио | MUST | PROCESS | MUST | Local audio | DONE | Retained in DoD inputs. |
| 3 | Несколько видео/аудио за один запуск | MUST | PROCESS | MUST | Several local files | DONE | Retained; distinct from ordered processing. |
| 4 | Папка с материалами | MUST | PROCESS | MUST | Folder discovery/confirmation | DONE | Candidate `candidate-v1-af81b2867f893e8e529a2d4f64d6c1370dd1249b46eb999d427fb408229680fa` proves native folder selection, deterministic supported-source preview, explicit confirmation, and reuse of canonical multi-source ingestion. |
| 5 | Папка Zoom | MUST | PROCESS | MUST | Zoom folder | DONE | Candidate `candidate-v1-d8bd6fc2649e061d50bfabae37c636d8caeb764965c941cf4fef88ae5fe301a8` proves real Zoom-folder S07 discovery, exact preview/confirmation and canonical multi-source ingestion; Product Owner GUI acceptance and CURRENT promotion recorded. |
| 6 | YouTube — одно видео | MUST | PROCESS | MUST | One YouTube video | DONE | Retained. |
| 7 | YouTube playlist | MUST | PROCESS | MUST | YouTube playlist | DONE | Accepted Candidate `candidate-v1-5f6384c8d68c96cc84432e3c72039ef1cdb0642f6399c6d5df60387774a7ed1e`; native real-playlist A/C selection, explicit confirmation, ordered sources and exact provenance. |
| 8 | Автоматическая расшифровка → TXT | MUST | PROCESS | MUST | Automatic TXT transcript | DONE | Retained. |
| 9 | SRT-субтитры | MUST | STUDIO | LATER | — | N/A | Owner correction: user-facing SRT is Studio; internal timing/SRT remains Process dependency. |
| 10 | Word Timeline | MUST | PROCESS | MUST | Word Timeline | DONE | Retained; timing/provenance is Process. |
| 11 | Careful / повышенный режим ASR | MUST | PROCESS | MUST | Careful ASR mode | DONE | Candidate `candidate-v1-f9ef07f48ff155645239f9c72b454732f53fecabdbf9379ad4d25b1a5acbdc9a`: neutral selector, persisted requested/executed mode and provenance; evidence is pending only the explicit baseline-acceptance gate. |
| 12 | Protective retry | MUST | PROCESS | MUST | Protective retry | DONE | Retained; distinct from user retry; controlled packaged proof is recorded in `PROCESS_V1_PROTECTIVE_RETRY_PROOF.md`. |
| 13 | Clean TXT | MUST | PROCESS | MUST | Clean TXT | DONE | Retained. |
| 14 | Review TXT | MUST | KNOWLEDGE | LATER | — | N/A | Owner correction: Review TXT / Evidence interaction is Knowledge; Clean TXT remains Process. |
| 15 | Выбор языка исходной речи | MUST | PROCESS | MUST | Source-speech language | DONE | Candidate `candidate-v1-43bdfe7b93052a3f2f9b5b6b089179580ef5387ebe82d0e96ef69e612257b0cd` proves the supported Russian-only V02 GUI selection and `ru → ru` provenance; no detection or additional languages are claimed. |
| 16 | Настройки качества распознавания | MUST | PROCESS | MUST | ASR quality settings | DONE | The single normal/careful selector already is the bounded quality setting; requested/executed provenance and default are proven in `PROCESS_V1_ASR_QUALITY_SETTINGS_PROOF.md`. |
| 17 | Диагностика качества распознавания | MUST | PROCESS | MUST | ASR diagnostics | DONE | Candidate `candidate-v1-ec1ae4eaccc5a2af225490135dc6385920c5f26ee0433059311be9074f6a2e57` proves readable persisted diagnostics for recovered and failed protective retry, with actual mode/language and no silent fallback. |
| 18 | Перевод расшифровки | MUST | PROCESS | MUST | Transcript translation | DONE | Candidate `candidate-v1-de25ee770d537b88eafd805249769e50694f7f5b56daab2f0771ec2c7706fd3d` proves fixed `ru` to `en` translation from a reusable completed transcript with persisted review-required provenance and readable cue result. |
| 19 | Выбор языка перевода | MUST | PROCESS | MUST | Translation-language choice | DONE | Candidate `candidate-v1-6545998b95e0f2d84abc7cd82baaea79bf8aa3c80cdd6d76840f47e87a42f996` proves the supported Russian-source to English-target control and truthful requested/executed target-language provenance; no broader multilingual capability is claimed. |
| 20 | Переведённый TXT | MUST | PROCESS | MUST | Translated TXT | DONE | Candidate `candidate-v1-a6d470e1e68163ed119bda229acffb2754b404f2d64310a93cc5dbbab19e5583` proves managed UTF-8 TXT, evidence-bound legacy recovery without provider re-execution, and ordinary Results Open/Export. |
| 21 | Переведённый SRT | MUST | STUDIO | LATER | — | N/A | Owner correction: user-facing translated SRT is Studio. |
| 22 | Перевод Topics | MUST | PROCESS | MUST | Topic translation | DONE | Candidate `candidate-v1-8be1ad5ca090afd08b869761046e6f4c56727e11dbf6ae968f6ad6f227d2b173` proves real `ru` to `en` Topic translation with additive persisted text, preserved Topic identity/order/spans/detail provenance, truthful reopen without retranslation, and Process-only review authority. |
| 23 | Topics + timestamps | MUST | PROCESS | MUST | Topics/timestamps | DONE | Retained. |
| 24 | Summary каждой темы | MUST | PROCESS | MUST | Topic summary | DONE | Candidate-bound normal Process result; title, summary and timing remain source-bound and review stays separate. |
| 25 | Выбор детализации Topics | MUST | PROCESS | MUST | Topic detail choice | DONE | Candidate `candidate-v1-2b779255c5b57a7b6602f153ea13c497bf738a18a84412773f8b6ed5261fbfcc` proves the bounded `Крупно`/`Обычно`/`Подробно` choice, persisted requested/executed provenance, reopen and fail-closed mismatch handling. |
| 26 | Редактирование/подтверждение Topics | MUST | PROCESS | MUST | Topic edit/confirm | DONE | Retained as Topic review, not Evidence review; owner accepted rename/save/reopen on the bound Candidate. |
| 27 | Иерархия тем | MUST | KNOWLEDGE | LATER | — | N/A | Owner correction: mandatory hierarchy deferred to later/Knowledge. |
| 28 | Ordered processing | MUST | PROCESS | MUST | Ordered processing | DONE | Retained; distinct from several local files. |
| 29 | Объединённая расшифровка | MUST | PROCESS | MUST | Combined transcript | NOT_DONE | Retained; playlist does not imply it. |
| 30 | Provenance при объединении | MUST | PROCESS | MUST | Combined provenance | NOT_DONE | Retained. |
| 31 | Corpus из нескольких материалов | MUST | PROCESS | MUST | Multi-source corpus | NOT_DONE | Retained as separate selected output. |
| 32 | Громкость | OPTIONAL | PROCESS | OPTIONAL | — | N/A | Retained OPTIONAL; not a MUST Board row. |
| 33 | Шум | OPTIONAL | PROCESS | OPTIONAL | — | N/A | Retained OPTIONAL; not a MUST Board row. |
| 34 | Паузы | OPTIONAL | PROCESS | OPTIONAL | — | N/A | Retained OPTIONAL; not a MUST Board row. |
| 35 | Диагностика качества аудио | OPTIONAL | PROCESS | OPTIONAL | — | N/A | Retained OPTIONAL; not a MUST Board row. |
| 36 | Единый экран результатов | MUST | PROCESS | MUST | Unified results screen | DONE | Retained; scoped owner acceptance is recorded in current evidence. |
| 37 | Открытие результата из Integra | MUST | PROCESS | MUST | Open result | DONE | Retained. |
| 38 | История обработок | OPTIONAL | PROCESS | OPTIONAL | — | N/A | Retained OPTIONAL; not a MUST Board row. |
| 39 | Reopen после перезапуска | MUST | PROCESS | MUST | Reopen after restart | DONE | Retained. |
| 40 | Reuse промежуточных результатов | MUST | PROCESS | MUST | Reuse intermediates | DONE | Retained. |
| 41 | Invalidation при изменениях | MUST | PROCESS | MUST | Invalidation | DONE | Retained. |
| 42 | Экспорт результатов | MUST | PROCESS | MUST | Ordinary-file export | DONE | Retained as ordinary-file export, not Studio subtitles or managed publication. |
| 43 | Отмена обработки | MUST | PROCESS | MUST | Cancel | DONE | Retained. |
| 44 | Retry после ошибки | MUST | PROCESS | MUST | Retry after failure | DONE | Retained; distinct from row 12 protective retry. |
| 45 | Работа после ошибки без restart | MUST | PROCESS | MUST | Subsequent run without restart | DONE | Retained. |
| 46 | Timeout зависшего процесса | MUST | PROCESS | MUST | Timeout | DONE | Retained. |
| 47 | Очистка фоновых процессов | MUST | PROCESS | MUST | No orphan workers | DONE | Retained. |
| 48 | Reconcile stale RUNNING | MUST | PROCESS | MUST | Reconcile stale RUNNING | DONE | Retained. |
| 49 | Сохранение успешных upstream результатов | MUST | PROCESS | MUST | Preserve upstream result | DONE | Retained. |
| 50 | Обычная работа только через GUI | MUST | PROCESS | MUST | GUI-only normal use | DONE | Retained. |
| 51 | Preflight runtimes/models | MUST | PROCESS | MUST | Selected-Capability Runtime Closure | BLOCKED | DoD aggregation with rows 52 and 56. |
| 52 | Понятная ошибка отсутствующей зависимости | MUST | PROCESS | MUST | Selected-Capability Runtime Closure | BLOCKED | DoD aggregation with rows 51 and 56. |
| 53 | Реальный progress | MUST | PROCESS | MUST | Real progress | DONE | Retained. |
| 54 | Понятные статусы | MUST | PROCESS | MUST | Clear statuses | DONE | Retained. |
| 55 | Выбор нужных outputs | MUST | PROCESS | MUST | Select outputs before run | DONE | Retained. |
| 56 | Недоступные функции показаны заранее | MUST | PROCESS | MUST | Selected-Capability Runtime Closure | BLOCKED | DoD aggregation with rows 51 and 52. |
| 57 | Тематические видеоклипы | LATER | STUDIO | LATER | — | N/A | Workbook LATER retained; creative media derivative is Studio. |
| 58 | Blur | LATER | STUDIO | LATER | — | N/A | Workbook LATER retained; creative media derivative is Studio. |
| 59 | Watermark | LATER | STUDIO | LATER | — | N/A | Workbook LATER retained; creative media derivative is Studio. |
| 60 | Изменение скорости видео | LATER | STUDIO | LATER | — | N/A | Workbook LATER retained; creative media derivative is Studio. |
| 61 | Filler mute | LATER | STUDIO | LATER | — | N/A | Workbook LATER retained; media derivative is Studio. |
| 62 | Dereverb | LATER | STUDIO | LATER | — | N/A | Workbook LATER retained; outside frozen Process v1. |
| 63 | Dubbing / TTS | LATER | STUDIO | LATER | — | N/A | Workbook LATER retained; new media is Studio. |
| 64 | Маркетинговые материалы | LATER | STUDIO | LATER | — | N/A | Workbook LATER retained; downstream content creation is Studio. |
| 65 | Knowledge / Evidence / relations | LATER | KNOWLEDGE | LATER | — | N/A | Workbook LATER retained; reviewed/canonical knowledge is Knowledge. |
| 66 | Obsidian / OneDrive publication | LATER | KNOWLEDGE | LATER | — | N/A | Workbook LATER retained; managed publication is downstream of reviewed Knowledge, not Process. |
| 67 | Social | LATER | STUDIO | LATER | — | N/A | Workbook LATER retained; downstream distribution is Studio. |
| 68 | Learning / Assistant | LATER | KNOWLEDGE | LATER | — | N/A | Workbook LATER retained; knowledge/assistant behavior is outside Process. |

## Board reconciliation

The active Board has 45 rows. Its states sum exactly: 41 DONE + 0 IN_PROGRESS + 3 NOT_DONE + 1 BLOCKED = 45.

One explicit DoD aggregation explains the distinct denominators:

| Aggregated Board row | Owner requirements represented | Reason |
| --- | --- | --- |
| Selected-Capability Runtime Closure | #51 Preflight runtimes/models; #52 clear missing-dependency error; #56 unavailable functions shown before run | One bounded requirement tests selected real dependencies while retaining pins and integrity. |

Every other PROCESS/MUST workbook row maps one-to-one to an active Board row.

    Current Process MUST requirements = 47
      = 44 one-to-one Board mappings + 3 requirements in Runtime Closure

    Active Completion Board rows = 45
      = 44 one-to-one rows + 1 Runtime Closure aggregate row

The five OPTIONAL and 16 LATER/out-of-phase selections are intentionally not active Process MUST Board rows.

## BookText worksheet reconciliation

Every BookText selection is blank. All 17 rows map to PROCESS_DOCUMENTS, priority NOT_APPLICABLE, with no Process Board row or state. This is the owner-approved separate Process Documents destination, not LATER.

| EXCEL ROW NUMBER | OWNER ITEM | ORIGINAL OWNER SELECTION | CURRENT DOMAIN | CURRENT PRIORITY | CURRENT BOARD ROW | CURRENT BOARD STATE | SCOPE-CHANGE AUTHORITY / REASON |
| --- | --- | --- | --- | --- | --- | --- | --- |
| B1 | PDF text extraction | blank | PROCESS_DOCUMENTS | NOT_APPLICABLE | — | N/A | Blank BookText selection; separate Process Documents decision. |
| B2 | OCR PDF | blank | PROCESS_DOCUMENTS | NOT_APPLICABLE | — | N/A | Same. |
| B3 | OCR изображений / сканов | blank | PROCESS_DOCUMENTS | NOT_APPLICABLE | — | N/A | Same. |
| B4 | PPTX text extraction | blank | PROCESS_DOCUMENTS | NOT_APPLICABLE | — | N/A | Same. |
| B5 | DOCX extraction | blank | PROCESS_DOCUMENTS | NOT_APPLICABLE | — | N/A | Same. |
| B6 | TXT / Markdown | blank | PROCESS_DOCUMENTS | NOT_APPLICABLE | — | N/A | Same. |
| B7 | Выбор страниц для OCR | blank | PROCESS_DOCUMENTS | NOT_APPLICABLE | — | N/A | Same. |
| B8 | Исключение страниц | blank | PROCESS_DOCUMENTS | NOT_APPLICABLE | — | N/A | Same. |
| B9 | Page / region provenance | blank | PROCESS_DOCUMENTS | NOT_APPLICABLE | — | N/A | Same; future ProcessedSource must permit page/region provenance. |
| B10 | Raw geometry / words / tables / lists | blank | PROCESS_DOCUMENTS | NOT_APPLICABLE | — | N/A | Same. |
| B11 | Searchable PDF | blank | PROCESS_DOCUMENTS | NOT_APPLICABLE | — | N/A | Same. |
| B12 | DjVu | blank | PROCESS_DOCUMENTS | NOT_APPLICABLE | — | N/A | Same. |
| B13 | Несколько изображений → одна книга | blank | PROCESS_DOCUMENTS | NOT_APPLICABLE | — | N/A | Same. |
| B14 | Иллюстрации: extraction / descriptions | blank | PROCESS_DOCUMENTS | NOT_APPLICABLE | — | N/A | Same. |
| B15 | Выбор OCR engine / legacy Tesseract | blank | PROCESS_DOCUMENTS | NOT_APPLICABLE | — | N/A | Same. |
| B16 | Reconstruction сложных таблиц | blank | PROCESS_DOCUMENTS | NOT_APPLICABLE | — | N/A | Same. |
| B17 | Semantic chapters / outline | blank | PROCESS_DOCUMENTS | NOT_APPLICABLE | — | N/A | Same. |

## Result

- Process-sheet rows represented: 68 / 68.
- BookText rows represented: 17 / 17.
- Lost workbook rows: 0.
- Duplicated owner requirements: 0. Rows 51, 52, and 56 share one Board row but remain separately enumerated owner requirements.
- Current frozen scope confirmed: 47 MUST, 5 OPTIONAL, 16 LATER/out-of-phase, and 17 PROCESS_DOCUMENTS rows.
