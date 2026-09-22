# Integra: staged Process → Knowledge → Studio

Дата: 2026-09-22. Design-only review с участием Astra.
Рекомендация: **VIABLE_WITH_BOUNDED_CHANGES**, условная до проверки изоляции.
Статус: для Product Owner review; не новая planning/governance authority.

## 1. Основание и предел вывода

Проверенный current `main`: `2af7de54964d267ff47267f9e43bb9c0b41973ac`
(совпадает с live `origin/main` на момент проверки).
Authoritative inventory: [SOURCE_PRODUCT_INTEGRA_PARITY_CURRENT.md](SOURCE_PRODUCT_INTEGRA_PARITY_CURRENT.md),
его #129/#131 evidence и точные границы modern acceptance #156.
Новый source capability audit не проводился. Прочитаны current repository truths
по AGENTS.md; дополнительно проверены только integration/build/test/state seams.

Вывод: runtime уже выполняет Process без запуска Canonical Knowledge или
Studio. Главные связи, мешающие независимому завершению, — packaging,
общий worker, изменяемый каталог результатов и широкий acceptance harness.
Нет установленной необходимости переписывать ASR/OCR/Topics, заменять project
storage или создавать отдельные приложения. Достаточность bounded изменений
пока является архитектурным выводом по коду, а не результатом нового pilot.

Гипотеза владельца сохраняется:

`PROCESS USER_ACCEPTED → PROCESS + KNOWLEDGE USER_ACCEPTED → PROCESS + KNOWLEDGE + STUDIO USER_ACCEPTED`

Переход к `PRODUCT DONE` допустим лишь если владелец сопоставил фазам весь
обязательный product scope, включая shared lifecycle, cross-navigation,
publication и local macOS usability. Три названия фаз сами по себе не доказывают
полноту [Product Definition](PRODUCT_DEFINITION.md). Его requirements и deferrals
не изменяются этим документом. В частности, принятый primary #156 не равен
приёмке всего Process; historical «accepted core» не повышает parity-статусы.

Не запускались builds/tests/Candidates, GUI, processing или Recovery continuation.
Не изменялись code, Recovery, pins, CURRENT, Product Definition, roadmap либо
historical evidence. Pilot ниже только предложен; feature WPs не создаются.

## 2. Распределение всего source inventory

Единица счёта — исходная строка с ID, не независимый user journey. Каждая из
58 строк имеет ровно один primary domain. Исходные classifications неизменны.
Сокращения scope: `CLEAR` = `CLEAR_PROCESS_V1`; `OWNER` =
`OWNER_DECISION_REQUIRED` для включения полной строки в Process v1; `—` =
не входит в предлагаемый Process inventory. Domain `OWNER_DECISION_REQUIRED`
означает, что даже цель всей сгруппированной строки пока нельзя однозначно
назначить одному домену.

`CLEAR` — технически ясный кандидат из уже подключённых путей, **не решение
владельца об обязательных форматах и не USER_ACCEPTED**. OCR/document rows
применимы, если эти inputs входят в owner-approved Process. Сам факт наличия
пути не отменяет существующие product deferrals.

| ID | SOURCE CAPABILITY (кратко; полная область в parity sheet) | PRIMARY DOMAIN | PROCESS SCOPE | EXISTING CLASSIFICATION |
| --- | --- | --- | --- | --- |
| S01 | Local ASR → TXT/SRT, bounded Russian video | PROCESS | CLEAR | PARITY_PROVEN |
| S02 | Contextual-loop gate → protective retry | PROCESS | CLEAR | VERIFY_EXISTING |
| S03 | Clean/review derivative TXT | PROCESS | CLEAR | VERIFY_EXISTING |
| S04 | Careful ASR mode | PROCESS | OWNER | INTEGRATE_EXISTING |
| S05 | Optional pandoc DOCX | STUDIO | — | DEFERRED_BY_OWNER |
| S06 | Ordered multiple local inputs | PROCESS | CLEAR | VERIFY_EXISTING |
| S07 | Zoom directory discovery | PROCESS | OWNER | INTEGRATE_EXISTING |
| S08 | Single YouTube input | PROCESS | OWNER | VERIFY_EXISTING |
| S09 | Native PDF/PPTX text | PROCESS | CLEAR | VERIFY_EXISTING |
| S10 | Multi-source corpus assembly | PROCESS | OWNER | INTEGRATE_EXISTING |
| S11 | Chronological combined-clear + provenance | PROCESS | OWNER | INTEGRATE_EXISTING |
| S12 | Basic Topics/timestamps | PROCESS | CLEAR | PARITY_PROVEN |
| S13 | Topic detail selector | PROCESS | OWNER | INTEGRATE_EXISTING |
| S14 | EN→RU transcript translation | PROCESS | OWNER | INTEGRATE_EXISTING |
| S15 | Topic translation | PROCESS | OWNER | INTEGRATE_EXISTING |
| S16 | Subtitle burn/cut via selected VideoText | STUDIO | — | VERIFY_EXISTING |
| S17 | Machine Canonical Evidence | KNOWLEDGE | — | VERIFY_EXISTING |
| S18 | Human whole-transcript verification → Evidence | KNOWLEDGE | — | VERIFY_EXISTING |
| S19 | Canonical Word Timeline + Evidence linkage | PROCESS | OWNER | VERIFY_EXISTING |
| S20 | Topic ACCEPT/REJECT, exact fragments | KNOWLEDGE | — | VERIFY_EXISTING |
| S21 | Extended Topic/boundary review | KNOWLEDGE | — | INTEGRATE_EXISTING |
| S22 | V1 Canonical Knowledge + managed vault | KNOWLEDGE | — | VERIFY_EXISTING |
| S23 | Production three-level hierarchy | PROCESS | OWNER | UNKNOWN |
| S24 | Concepts/relations, Assistant/Learning/Marketing research | OWNER_DECISION_REQUIRED | — | UNKNOWN |
| V01 | Source-specific ASR/VAD/retries correspondence | PROCESS | OWNER | VERIFY_EXISTING |
| V02 | Source language/quality/review diagnostics | PROCESS | OWNER | INTEGRATE_EXISTING |
| V03 | SRT parse/normalize/write | PROCESS | CLEAR | PARITY_PROVEN |
| V04 | Clip/retime SRT | STUDIO | — | INTEGRATE_EXISTING |
| V05 | Current EN-target transcript translation JSON | PROCESS | OWNER | VERIFY_EXISTING |
| V06 | Language choice + translated TXT/SRT | PROCESS | OWNER | INTEGRATE_EXISTING |
| V07 | Source-specific Topics/cache correspondence | PROCESS | OWNER | VERIFY_EXISTING |
| V08 | Exact video clip by SRT bounds | STUDIO | — | VERIFY_EXISTING |
| V09 | Subtitle burn, current defaults | STUDIO | — | VERIFY_EXISTING |
| V10 | Subtitle style controls | STUDIO | — | INTEGRATE_EXISTING |
| V11 | 1.25× video | STUDIO | — | VERIFY_EXISTING |
| V12 | Arbitrary speed + paired retimed SRT | STUDIO | — | INTEGRATE_EXISTING |
| V13 | Loudness/noise/pause measurements | PROCESS | OWNER | VERIFY_EXISTING |
| V14 | Static blur | STUDIO | — | INTEGRATE_EXISTING |
| V15 | Watermark | STUDIO | — | INTEGRATE_EXISTING |
| V16 | Topic/quote-driven clipping | STUDIO | — | INTEGRATE_EXISTING |
| V17 | Filler candidates + explicit muting | STUDIO | — | INTEGRATE_EXISTING |
| V18 | Dereverb/audio enhancement | STUDIO | — | INTEGRATE_EXISTING |
| V19 | Speech synthesis/dubbing | STUDIO | — | INTEGRATE_EXISTING |
| V20 | Derived-media duration/stream QA | STUDIO | — | VERIFY_EXISTING |
| V21 | Store/history/reuse/cancel correspondence | SHARED_PLATFORM | CLEAR | VERIFY_EXISTING |
| B01 | PDF/image Surya OCR | PROCESS | CLEAR | VERIFY_EXISTING |
| B02 | Include/exclude original pages | PROCESS | CLEAR | VERIFY_EXISTING |
| B03 | TXT/MD/JSON/page artifacts | PROCESS | CLEAR | VERIFY_EXISTING |
| B04 | Optional searchable PDF | PROCESS | OWNER | VERIFY_EXISTING |
| B05 | Vision QA / review outputs | PROCESS | CLEAR | VERIFY_EXISTING |
| B06 | Retained raw geometry/words/tables/lists | PROCESS | CLEAR | VERIFY_EXISTING |
| B07 | DjVu | PROCESS | OWNER | INTEGRATE_EXISTING |
| B08 | Ordered multi-image book | PROCESS | OWNER | INTEGRATE_EXISTING |
| B09 | Illustrations extraction/descriptions | PROCESS | OWNER | INTEGRATE_EXISTING |
| B10 | Legacy Tesseract selection | PROCESS | OWNER | INTEGRATE_EXISTING |
| B11 | General frequency-table reconstruction | PROCESS | OWNER | UNKNOWN |
| B12 | Semantic chapters/outline | PROCESS | OWNER | IMPLEMENT_MISSING |
| B13 | Hybrid experimental scripts | OWNER_DECISION_REQUIRED | — | UNKNOWN |

| PRIMARY DOMAIN | SeminarText | VideoText | BookText | Total |
| --- | ---: | ---: | ---: | ---: |
| PROCESS | 16 | 7 | 12 | 35 |
| KNOWLEDGE | 5 | 0 | 0 | 5 |
| STUDIO | 2 | 13 | 0 | 15 |
| SHARED_PLATFORM | 0 | 1 | 0 | 1 |
| OWNER_DECISION_REQUIRED | 1 | 0 | 1 | 2 |
| Total | 24 | 21 | 13 | 58 |

### Границы, предотвращающие двойной счёт

- S10/S11 — сборка/нормализация source content, не cross-source semantic merging.
  S06 queue не заменяет их или единую книгу B08.
- S12/S13/S15/S23/B12 — source-scoped provisional Topics/structure. Принятая
  семантика, Concept identity и Canonical Knowledge принадлежат Knowledge.
  Назначение domain не делает UNKNOWN hierarchy обязательной реализацией.
- S17/S18 — canonicalization/semantic review на входе Knowledge, не требование
  запускать Evidence engine ради raw provenance Process.
- S19 намеренно не разделена и не повышена до proven: принят aligned Word
  Timeline #156, но не вся Canonical Evidence linkage. Word/time provenance
  нужна Process; существующий P156 alignment asset используется отдельно, не
  создавая 59-ю source-inventory строку и не принимая всю S19.
- V01/V07 не требуют второго ASR/Topics engine: общий результат обеспечивают
  выбранные S01/S12. Их source-specific correspondence — отдельное решение.
- S16 и V08/V09 описывают разные source inventory, но используют один selected
  production path; числа не являются суммой уникальных реализаций.
- V13 измеряет исходник; V18 создаёт изменённую производную. Если владелец
  потребует enhancement как preprocessing, это явное расширение Process closure,
  а не основание незаметно втянуть весь Studio. V20 проверяет media derivatives,
  а не заменяет shared integrity.
- B06 означает raw inspection, не готовую точную region navigation. B09
  descriptions остаются provisional. B04 — searchable rendition исходника,
  не общий publishing/export product.
- S05 остаётся deferred. S24 содержит разнородные research направления; B13
  не имеет определённого production outcome. Им нельзя назначить финальную фазу
  либо обязательность на основании одного старого названия.

## 3. Candidate Process v1 и объём reuse

Предлагаемая граница: **поддержанный input → выбранная обработка → structured,
provenance-preserving result → сохранение/повторное открытие → управляемые
failure/retry/recovery**. Завершение не зависит от создания принятого Knowledge,
творческого media derivative или внешней publication.

| PARITY CLASSIFICATION | CLEAR_PROCESS_V1 | Additional OWNER-decision Process | Maximum mapped Process + shared |
| --- | ---: | ---: | ---: |
| PARITY_PROVEN | 3 | 0 | 3 |
| VERIFY_EXISTING | 10 | 7 | 17 |
| INTEGRATE_EXISTING | 0 | 13 | 13 |
| REPAIR_INTEGRATION | 0 | 0 | 0 |
| IMPLEMENT_MISSING | 0 | 1 | 1 |
| UNKNOWN | 0 | 2 | 2 |
| DEFERRED_BY_OWNER | 0 | 0 | 0 |
| Total inventory positions | 13 | 23 | 36 |

CLEAR: SeminarText 6 (2 proven + 4 verify), VideoText 2 (1 proven + 1 verify,
включая shared V21), BookText 5 (5 verify). Optional: SeminarText 10,
VideoText 6, BookText 7. S24/B13 не включены даже в maximum Process envelope:
их domain ещё не определён. Это не проценты готовности и не трудозатраты.

Для 13-row candidate не установлен отсутствующий source algorithm.
Десять позиций требуют прежде всего современной проверки существующего пути,
а не переписывания. В optional envelope 13 расширений используют уже существующие
source implementations; единственная установленная missing implementation —
B12. B11/S23 UNKNOWN нельзя бюджетировать как простое подключение готового кода.
Ноль REPAIR_INTEGRATION в inventory не доказывает отсутствие будущих дефектов
и не закрывает отдельный Recovery #161/#162.

**Это не «ноль нового кода».** Integra ещё нужна небольшая projection/validation
граница ProcessedSource, bounded build/test isolation и завершённый required
lifecycle proof. Эти работы не являются новыми source capabilities и не
подменяют source count. Нет оснований строить новый engine или generic plugin
framework там, где хватит проверки пути/добавления параметра/выдачи результата.

Дополнительные обязательные свойства сквозного Process (не новые inventory rows):
real aligned Word Timeline для соответствующей media области; сохранение source
identity/revision и статуса machine output; truthful COMPLETED; reopen без
повторного ASR/OCR; navigation с реально доступной точностью; отсутствие смешивания
partial/accepted результатов; restart/recovery и безопасное reuse. Primary #156
доказывает лишь свою bounded область, не весь этот набор по всем input types.

## 4. Current-main isolation audit

Ниже static evidence, не новые execution PASS. `MUST_DECOUPLE_BEFORE_PROCESS`
означает обязательное устранение зависимости **вне выбранного Process scope**,
не разрешение удалить сегодняшние required gates. Если владелец включает OCR
или translation, соответствующий runtime становится законным Process dependency.

| Current path / exact coupling | Classification | Bounded action / граница |
| --- | --- | --- |
| [user_media.py](../integra_core/user_media.py), `run_job`, lines 239–351: ASR→SRT→optional translation/alignment/Topics; burn только при выборе. Lines 346–349 явно не создают Knowledge/package. [application_runtime.py](../integra_core/application_runtime.py) выполняет source plans и сохраняет результаты. | ALREADY_ISOLATED | Сохранить dispatch/production orchestration. Не переписывать pipeline только потому, что разные операции в одном файле. |
| [capabilities.py](../integra_core/capabilities.py), registry lines 83–117: для media опрашивает media worker, ASR, ffmpeg, Topics, alignment, translation независимо от выбранных outputs. Большинство ошибок переводится в availability flags. | MUST_DECOUPLE_BEFORE_PROCESS | Requested dependency closure определяет blocking preflight; остальных — информационная availability. Не утверждается, что всякий нынешний missing runtime уже блокирует ASR: flags частично независимы. Доказывать отсутствие вызова/блокировки, а не только import absence. |
| [build_videotext_worker.sh](../scripts/build_videotext_worker.sh), lines 10–12: один `translation-worker` компилирует все Swift Sources/videotext кроме App/UI плюс translation и media workers. [videotext_subtitles.py](../integra_core/videotext_subtitles.py) использует его для SRT. | MUST_DECOUPLE_BEFORE_PROCESS | Выделить минимальную compile closure pinned SRT service или воспроизводимо переиспользовать её exact governed build artifact. Не исключать VideoText целиком и не писать новый SRT engine. Возможность отдельной closure ещё предстоит доказать pilot. |
| [build_macos_app.sh](../scripts/build_macos_app.sh), lines 32–91: все prechecks; VideoText compile; BookText Vision compile; SeminarText Evidence/review; alignment; full manifest без выбора Process profile. | MUST_DECOUPLE_BEFORE_PROCESS | Explicit capability build closure либо hash-verified immutable reuse frozen components, сохраняя полный current bundle contract. Нельзя считать compiler interruption дефектом source algorithm. Не копировать неизвестный stale binary. |
| [package_review_runtime.py](../scripts/package_review_runtime.py): Python 3.14, governed review-wheel cache, offline hash-locked install/jsonschema проверяются безусловно при любой build. | MUST_DECOUPLE_BEFORE_PROCESS | Review-only packaging не должно быть execution prerequisite Process. При сохранении full bundle допустим проверенный frozen artifact; при profile нужна явная новая declared contract граница, не пропуск hash checks. |
| [candidate_manifest.py](../scripts/candidate_manifest.py), `generate`, и [candidate_identity.py](../integra_core/candidate_identity.py), `validate_bundle`: требуются все 3 component runtimes и alignment; whole-bundle digest. | MUST_DECOUPLE_BEFORE_PROCESS | Если вводится optional profile — строго объявить included/excluded capability closure и проверять каждый included byte; default full profile неизменен. Иначе сохранить все required artifacts byte-bound и изолировать их повторную сборку. Нельзя просто удалить runtime и ослабить validator. |
| [test_macos_app.sh](../scripts/test_macos_app.sh): full build, Finder/launch probes, self-test, ST/Word/Book preflight, Obsidian/OneDrive previews, native media/lifecycle probes. | MUST_DECOUPLE_BEFORE_PROCESS | Разделить gate ownership: shared shell + selected Process + frozen-domain integrity; functional Knowledge/Studio proof только в соответствующей фазе. GUI checks не приравнивать headless PASS. Existing обязательные checks сохраняются до отдельного authorized remapping. |
| [.github/workflows/quality-gate.yml](../.github/workflows/quality-gate.yml): Ubuntu governance + Python unittest discovery; macOS-only cases условны. | MUST_DECOUPLE_BEFORE_PROCESS | Явный Process gate ledger с платформой, Candidate, required/passed/skipped. Обязательный packaged Finder-like путь не выводится из Linux green или skipped macOS tests. Не обязательно отдельный CI engine. |
| [bridge.py](../macos/Resources/bridge.py), `_record_review_outputs`, lines 257–277: Knowledge/review добавляет ссылки в тот же source `outputs`; есть lock, compare-and-swap, protection dependent Evidence. | MUST_DECOUPLE_BEFORE_PROCESS | Не использовать изменяемый result dictionary как canonical Process boundary: запечатать immutable projection; Knowledge extension владеет отдельным revision/reference record. Существующие CAS/locks сохранить. Замена project DB не нужна. |
| [documents.py](../integra_core/documents.py), [artifact_reference_v1](../schemas/artifact_reference_v1.schema.json), [document_extraction_v1](../schemas/document_extraction_v1.schema.json): identity/hash/revision, locators, authority, original artifacts уже представлены. | ALREADY_ISOLATED | Переиспользовать vocabulary/validation через adapter; не выдавать source-level schema за уже поставленный unified ProcessedSource. |
| [application_runtime.py](../integra_core/application_runtime.py), lines 132–153: OCR blocks получают full-page rectangle. Local MEDIA path отдельно проверяет равенство imported и planner source ID перед созданием job. | MUST_DECOUPLE_BEFORE_PROCESS | В boundary точно выразить locator precision и происхождение identity, сохранив существующую equality guard. Здесь не установлен identity mismatch defect. Fine region navigation можно отложить, fabricated precision — нельзя. |
| [transcript_topic_studio.py](../integra_core/transcript_topic_studio.py), lines 40–56: legacy owner ASR=VideoText, SeminarText old pin в historical domain model. | CAN_DEFER | Не подключать этот model unchanged как current producer authority. Reuse artifact concepts, но current projection связывать с actual runtime. Historical declarations не переписывать ради этого design. |
| [bridge.py](../macos/Resources/bridge.py) отдельные review/Evidence/publishing handlers; [knowledge.py](../integra_core/knowledge.py) hash-bound projection; [media.py](../integra_core/media.py) derivative validation/no Knowledge mutation. | ALREADY_ISOLATED | Сохранить downstream consumer направление. Static import pure definitions сам по себе не доказывает runtime dependency или необходимость refactor. |
| Native shell, project/run history, leases, atomic persistence, shutdown/reuse shared с downstream. | CAN_DEFER | Не делить storage/app на три. Изолировать ownership новых outputs; shared mutations тестировать по impact. Отдельные процессы/БД не нужны без доказанного blocking defect. |

**Точный bounded change set до независимого Process completion:** (1) один
immutable ProcessedSource projection/validator/reader; (2) capability-scoped
preflight и output ownership; (3) deterministic SRT build dependency closure
и frozen-runtime reuse или additive build profile с fail-closed manifest;
(4) explicit Process acceptance ledger поверх существующих probes, с честным
Candidate/environment accounting. Для выбранного scope ещё требуется проверка
существующих путей и Recovery, но не новый architecture rewrite. При full-bundle
варианте profile-specific manifest change не требуется; это альтернативы,
а не два обязательных параллельных проекта.

## 5. ProcessedSource v1: минимальная граница, не новый продукт

Это **предлагаемый**, ещё не реализованный immutable envelope над существующими
артефактами. Он не заменяет source formats, project storage или Canonical Evidence.
Нельзя прямо использовать legacy current-owner/pin constants как его authority.

| Field group | Contract rule |
| --- | --- |
| Version/identity | Schema major/minor, ProcessedSource ID/revision, predecessor; Integra canonical source ID и явные planner/import/source mappings. Никакого равенства ID только по совпавшему имени поля. |
| Source | Тип, original revision/byte hash, immutable original artifact reference; credential-free locator. Owned copy и external read-only origin различаются. |
| Text | Original/normalized text artifact + hash, encoding; cleaned derivative отдельно с parent link. Не заменять исходные формулировки текстом review/translation. |
| Segments | Stable IDs, text spans, original source locators; declared timing/offset units и validation bounds. |
| Words/time | Optional aligned word IDs, intervals, parent segments, aligner/model/config/output hashes и status. Отсутствующие timestamps не синтезируются. |
| Documents | Original page/slide numbering, selected-page coverage, blocks; locator precision PAGE/SLIDE/REGION/WORD только фактически доказанная. Для нынешнего normalized OCR — page precision; raw geometry сохраняется отдельной ссылкой. |
| Translations/Topics | Optional derivative references, language, source-span links, producer configuration. Machine semantics PROVISIONAL/REVIEW_REQUIRED; Topics не становятся accepted Knowledge. |
| Producer/evidence | Component pin/implementation/config/model identities насколько они реально подтверждены, Candidate/run binding и quality report refs. Unattested model identity честно отмечается, не достраивается фиктивным hash. |
| Completeness | По requested output: produced / not applicable / not requested / unavailable / failed. Whole input vs selected pages/intervals различаются; общий COMPLETED только по обязательному requested closure. |
| Artifact seal | Artifact IDs, byte hashes/sizes, parent lineage, revision and manifest hash; relocatable owned-store references, safe resolver. Absolute paths сегодняшних outputs не являются portable contract. |

Producer после проверки required stages атомарно публикует seal. Partial run
может сохранять diagnostics, но не masquerade как completed ProcessedSource.
Reopen читает и валидирует sealed version, а не незаметно перезапускает ASR/OCR.
Изменение исходника/настроек создаёт новую revision; старый результат остаётся
воспроизводимо адресуемым. Run index может добавлять ссылки, но не менять bytes
принятой Process revision. Никакой destructive migration старых проектов.

Knowledge получает envelope + artifacts через read adapter, при необходимости
создаёт source-compatible Canonical Evidence и review records. Оно не импортирует
ASR/OCR orchestration и не вызывает ffmpeg, чтобы «достроить» потерянный input.
Недостающий field означает явное requirement/version decision, не hidden rerun.
Принятие семантики остаётся explicit human ReviewDecision.

Минимальный будущий Knowledge→Studio contract: immutable selection/brief,
knowledge revision/hash, Evidence/source refs, точные locators, semantic/review
status и разрешённый derivative operation. Studio создаёт новый derivative + QA,
не меняя Process/Evidence/Knowledge. Здесь не проектируются редактор, renderer,
publishing subsystem или Studio schema целиком.

## 6. Защита уже принятых фаз

После `PROCESS USER_ACCEPTED` фиксируются owner-approved capability/input limits,
ProcessedSource version, exact runtime/dependency closure, representative fixtures
и accepted Candidate evidence. Это не навечное освобождение от regression.

| Subsequent change | Required Process regression scope |
| --- | --- |
| Только Knowledge consumer/UI, Process runtime/closure unchanged | Producer/consumer v1 conformance, old fixture reader compatibility, один representative accepted Process journey с save/reopen/navigation, плюс changed Knowledge tests. Не автоматически весь ASR/OCR matrix. |
| Process producer, locator/identity/authority semantics, pin/model/config changed | Affected Process scenarios и contract tests; owner acceptance только изменившегося user scope. Нельзя наследовать прежний PASS новых bytes. |
| Shared persistence/lease/recovery, environment resolution, package closure или launcher changed | Finder-like packaged primary + affected Recovery и input/runtime gates; downstream compatibility по dependency impact. |
| Documentation-only | Documentation integrity; никакого нового product PASS или пересборки без реального trigger. |

Whole-app Candidate hash и semantic acceptance — разные вещи. Новый app binary
требует truthful new Candidate/integrity evidence; это не отменяет неизменную
scope-bound human acceptance каждой старой функции. Reuse evidence разрешён лишь
с доказанно неизменным dependency closure. Technical green не означает
USER_ACCEPTED/merge authority. CURRENT/PROPOSED rules продолжают действовать.

Additive optional fields с неизменным смыслом — compatible minor evolution;
изменение identity/locator/authority/completeness semantics — major v2, отдельный
adapter или parallel producer. Сохранить v1 artifacts/readers. Не мигрировать
destructively и не заставлять Knowledge удобством своей схемы переоткрывать Process.
Эта будущая regression policy требует owner-approved gate mapping: документ сам
не отменяет существующие mandatory suites.

## 7. Recovery #161/#162: необходимая функция, не новый roadmap

Recovery — SHARED_PLATFORM, но его Process область необходима для заявленной
цепочки failure/retry/recovery: failure, timeout, cancel, stale RUNNING, orphan
cleanup, governed reuse/invalidation, subsequent success и persistence/restart
не заменяются одним happy-path COMPLETED. Не обязательно иметь весь lifecycle
будущего Studio, чтобы принять Process; точный scope определяет владелец.

На snapshot [PR #162](https://github.com/Yurielo/integra/pull/162) draft/open,
head `b630ae384f09122c07648094594d68bdd0e2605c`, base main после #166.
[Owner direction](https://github.com/Yurielo/integra/issues/161#issuecomment-5772574080)
сохраняет 12/12 non-skipped ASR reuse/invalidation как source-test evidence,
но требует fresh Candidate и обязательные Candidate gates. Это не full Recovery
USER_ACCEPTED и не доказательство его готовности внутри нового package.

VideoText нужен accepted Process path причинно: SRT normalization использует
его worker. В нынешней сборке общий worker причинно требует большой Swift compile;
поэтому его interruption блокирует fresh Candidate. Но media/translation closure
**не является логической необходимостью Recovery semantics**. Reported build
environment interruption не доказывает ошибку Recovery или compiler/source
defect. Нельзя исключить весь VideoText, подменить worker или зачесть skip.

Bounded build isolation/reproducible artifact reuse могло бы устранить лишнюю
связь без repair cycle Recovery, но это отдельное разрешение/implementation,
не действие этого review. #161/#162, его branch, ledger и build не менялись.

## 8. Reuse и sunk cost

| Category | Existing work | Как использовать / что не сохранять по инерции |
| --- | --- | --- |
| DIRECT_PROCESS_ASSET | Pinned SeminarText ASR/retry, VideoText SRT, real WhisperX, basic Topics, native extraction, BookText worker/raw outputs, source-first UI, P156 fixtures | Проверять/оборачивать existing paths. Не создавать второй ASR/OCR engine. |
| FUTURE_KNOWLEDGE_ASSET | Evidence canonicalizer, review adapters, Knowledge projection, provenance/navigation contracts, managed Knowledge export | Сохранить и заморозить feature expansion до Knowledge; не требовать semantic promotion для Process completion. |
| FUTURE_STUDIO_ASSET | VideoText clip/burn/speed/QA, media recipes, derivative navigation, remaining source implementations | Сохранить код и historic evidence; не требовать нового Studio acceptance для чистого Process изменения. |
| SHARED_PLATFORM_ASSET | Native app shell, projects/history, identities/revisions, leases, atomic writes, diagnostics, recovery/reuse, Candidate manifest, integrity | Один общий владелец состояния и exact evidence. Пользоваться существующим, не строить вторую инфраструктуру. |
| PROCESS_BLOCKING_COMPLEXITY | Unconditional unrelated compile/preflight/review packaging; monolithic acceptance requirements; legacy identity assumptions при ошибочном применении к current producer | Устранить конкретную coupling seam, не переписать все содержащие её модули. |
| NON_BINDING_HISTORICAL_OVERHEAD | Broad прошлые «accepted» labels вне доказанного scope; duplicate narrative ledgers, abandoned research как якобы обязательный путь | Историю не удалять/переписывать; не делать sunk effort обязательством для Process. Действующие governance contracts сюда автоматически не относятся. |

До Knowledge/Studio замораживаются новые semantic review extensions, hierarchy/
concepts, creative media controls, synthesis/dubbing и expansion publication
journeys. Freeze означает no expansion, а не удаление работающих действий или
ложное объявление их отсутствующими. Existing callable paths остаются честно
обозначены; в additive Process profile недоступные capabilities должны быть
явно unavailable, не «успешными» заглушками. Product Definition не урезается.

## 9. Adversarial self-review

| Concrete failure mode | Guardrail / evidence that detects it |
| --- | --- |
| «Весь parity» затаскивает dubbing, blur и semantic chapters в Process | Explicit owner inclusion list; inventory allocation не scope approval; optional rows не блокируют approved Process. |
| Полная S19 заставляет выполнять Canonical Evidence/review для word timestamps | Separate aligned Process artifact и downstream canonical adapter; full S19 остаётся owner decision. |
| Изменение Studio Swift type/review wheel ломает каждую Process build | Declared compile/runtime closure; pinned frozen artifact reuse либо fail-closed profile; negative absent-downstream dependency check. |
| Knowledge добавляет поле в общий run JSON и меняет accepted Process bytes | Immutable sealed revision + owned extension record; mutation/compare-and-swap tests и hash evidence. |
| Knowledge тайно перезапускает ASR ради удобного текста/Topics | Read-only consumer adapter; any reprocessing explicit new Process revision/request. |
| Каждый Candidate hash превращается в повторную приёмку всего приложения | Разделять integrity, changed closure и accepted user scope; impact-linked regression ledger. Не наследовать PASS изменённых runtime. |
| Current profile тихо удаляет required runtime или исключает неудобный hash | Included/excluded closure декларируется и валидируется; default contract unchanged; no skip-as-PASS. |
| Surya raw geometry/page rectangle объявляется word/region navigation | Typed locator precision; requested fine-grained navigation fail-closed при отсутствии данных. |
| Успешная queue выдаётся за complete corpus/book | Selected-source/page coverage и separate assembly manifest; S06 не доказательство S10/S11/B08. |
| Provisional Topics выдаются за принятые semantic facts | Explicit authority status; Knowledge ReviewDecision, human-only USER_ACCEPTED. |
| Interrupted/changed source переиспользует старый transcript | Hash/config identity + governed invalidation; partial output не получает final seal. |
| Upstream «latest» меняет все фазы одновременно | Fixed source pins, per-capability dependency mapping; pin change только explicit bounded authority. |
| Governance/agent bookkeeping становится новым циклом вместо результата | Existing minimal contracts; новый governance механизм только для конкретной authority gap; no role/roadmap expansion здесь. |
| Pilot на одном Russian video объявляется приёмкой OCR/YouTube/всех языков | Pilot proves isolation only; owner-defined supported-input matrix остаётся отдельной acceptance границей. |
| Заморозка скрывает существующую функцию либо publication выпадает из PRODUCT DONE | Preserve current behavior; explicit whole-product-to-domain correspondence и owner decision по незакреплённым obligations. |

## 10. Один минимальный обратимый pilot — только дизайн

**Один вертикальный slice:** существующий local Russian video → ASR → SRT →
real alignment → basic Topics → sealed ProcessedSource → reopen. Та же Integra.app,
тот же source-first/bridge/orchestration path, те же pins, а не новая demo CLI.

Предлагается additive isolated Process build/acceptance profile в отдельной
экспериментальной ветке/output directory, на fixture/copied project. Default
build, existing app, CURRENT, проекты и source repositories не изменяются.
Не переносить туда OCR, translation, Knowledge UI или новые Recovery semantics.

Узкая поверхность изменений — selection boundary, нужная SRT compile closure,
честный manifest/profile declaration, тонкий ProcessedSource projection.
Сначала проверить, достаточно ли reproducible exact frozen-runtime reuse с
нынешним full manifest; тогда отдельный manifest profile вообще не вводить.
Если такая reuse не устраняет dependency, профиль обязан явно описывать absence
optional runtimes и unavailable actions, не ослабляя integrity. Это два варианта
одного эксперимента, не разрешение строить две архитектуры.

План наблюдений (сейчас ничего не выполняется):

1. Зафиксировать control source/runtime hashes и production entrypoint.
2. Повторно использовать pinned SRT service, не весь media feature pipeline;
   доказать compile/runtime closure. В full-bundle варианте frozen artifacts
   должны иметь воспроизводимый provenance/hash contract, не случайный cache.
3. Установить fail-on-call наблюдение на Knowledge/Studio producers и их
   optional preflight. В profile варианте недоступные downstream runtimes не
   должны препятствовать выбранному Process; required missing SRT обязан fail.
4. Через packaged Finder-like path получить настоящий результат, проверить
   byte hashes/locators, закрыть/reopen copied project без повторного processing.
5. Один controlled interruption→retry на том же fixture подтверждает safe
   reuse/новую revision; это не полный Recovery acceptance и не разрешение repair.
6. Подтвердить неизменность original inputs, default profile и frozen code;
   в runtime/ledger не должно быть test doubles вместо ASR/aligner.

**PASS:** slice реально завершается и открывается из stored immutable boundary;
Knowledge/Studio producers не вызывались; unrelated runtime/build dependency
устранена доказанным closure/reuse; required integrity и truthful failure
сохранились. Все identity/evidence относятся к exact experimental Candidate.
**FAIL/INCONCLUSIVE:** хоть один критерий не доказан, integration требует hidden
downstream execution, либо build environment не позволила получить evidence.
Environment interruption — INCONCLUSIVE/BLOCKED, не structural failure.

Pilot не даёт PROCESS USER_ACCEPTED, не принимает все source types, не создаёт
новый roadmap и не выдаёт intermediate Candidate владельцу как ready product.
Rollback — отказаться от additive ветки/profile, не мигрируя пользовательские
данные и не заменяя текущую установленную app. Pilot здесь не реализован.

## 11. Owner decisions и условия пересмотра

Необходимые owner decisions до scope/acceptance implementation:

1. Какие inputs/languages и quality limits обязательны для Process v1: только
   accepted local media или также native documents/OCR; какие из 23 OWNER rows
   включены? `CLEAR` не отменяет Product Definition deferrals.
2. Требуется ли whole S19 Canonical Evidence continuation уже в Process, либо
   достаточно aligned provenance до Knowledge? Требуется ли source-specific
   V01/V07 equivalence сверх принятой selected-engine композиции?
3. Какая точная Process save/reopen/restart/recovery и provenance-navigation
   область обязательна, включая precision для документов и selected-page scope?
4. Как обязательные whole-product publication/cross-navigation/local macOS
   usability obligations распределяются между фазами/shared acceptance, и как
   explicit deferral S05, unresolved research/domain disposition S24/B13 и
   optional inputs соотносятся с этой моделью?
5. Разрешён ли описанный обратимый isolation pilot и последующее explicit gate
   remapping, не меняющее meaning of CURRENT/USER_ACCEPTED?

Отказаться от **bounded** рекомендации либо пересмотреть её после доказательства,
что (a) SRT closure нельзя отделить/воспроизводимо переиспользовать без крупного
fork source internals; (b) provenance требует destructive storage/identity
replacement; (c) required Process неизбежно исполняет semantic Knowledge/Studio;
(d) честная Candidate validation optional domains невозможна без bypass;
(e) выбранные owner inputs/recovery требуют принципиально более широкого redesign;
либо владелец требует иной coupled all-domain acceptance boundary.

Такие доказательства сейчас отсутствуют. Compiler interruption или неизвестная
стоимость optional функции не являются доказательством нужды в трёх приложениях.
При выявлении structural condition остановить pilot, показать конкретный graph/
contract conflict и заново оценить architecture — не продолжать под ярлыком
«bounded». До этого оптимальное направление — reuse, verification и четыре
узких seam changes из §4, а не новый engine/framework.

## 12. Review outcome

**VIABLE_WITH_BOUNDED_CHANGES**: одна Integra.app, независимая completion boundary
Process, потом Knowledge consumer, потом Studio derivatives. Текущая работа
сохраняет ценность, но historical effort не определяет обязательный scope.
Это design conclusion для владельца, не implementation authorization и не
PRODUCT DONE. Следующее действие в рамках этого задания — только owner review.
