# План доведения Integra до реальных интеграций

Статус: `REBASELINED after PR #104; package and Word Timeline gaps remain`.

Этот план не меняет текущую правду приложения: пока у функции нет
упакованного runtime, callable пути из macOS и smoke-проверки, в UI она
остаётся disabled с подписью «В разработке».

## Уже работает

- локальные видео и аудио: TXT, SRT, улучшенный M4A, встроенные субтитры,
  клипы по SRT-диапазону;
- документы: нативный текст, структура, извлечение встроенных изображений;
- проекты, история, переход от SRT к медиа;
- выбор проверенного package, Obsidian и файловая публикация OneDrive с
  preview-before-write.
- условные SeminarText drafts тем: для Integra-owned SRT вызывается
  закреплённый read-only Topic Engine; результат всегда `REVIEW_REQUIRED`.
  Функция становится доступна только когда внешний закреплённый runtime и
  локальная модель прошли preflight.

## Этап 0 — общая основа runtime

**Результат:** каждый компонент запускается из bundle без абсолютных путей к
рабочим копиям и без обращения к source-репозиторию во время работы.

1. Зафиксировать commit, лицензию, бинарники/модели и SHA-256 каждого runtime.
2. Добавить versioned Integra contracts: вход, выход, отмена, ошибки,
   provenance и совместимость версий.
3. Добавить dependency preflight в Diagnostics: что найдено, чего не хватает,
   без показа секретов.
4. Добавить reproducible bundle/smoke для чистого `.app`.

**Критерий UI:** кнопка становится доступной только после успешного preflight.

## Этап 1 — SeminarText: Word Timeline и Topics

**Цель:** для уже полученного SRT строить Word Timeline и drafts тем через
read-only закреплённый SeminarText runtime.

1. Упаковать точный SeminarText topic runtime и локальную модель; не менять
   репозиторий SeminarText.
2. Adapter принимает только Integra-owned TXT/SRT и создаёт versioned output
   с source/revision/word/time locators.
3. Добавить planner dependencies: `transcript → word_timeline → topics`.
4. Показать темы как `REVIEW_REQUIRED`, а не как принятые знания.
5. Добавить cancellation/retry, synthetic end-to-end smoke и macOS UI smoke.

**Текущая граница:** PR #104 реализовал callable Topics path, а PR #108
пакует точный модуль Topic Engine в personal-use `.app` после проверки commit
и SHA-256. PR #109 добавляет самостоятельный Word Timeline runtime: WhisperX
3.8.6 запускается только для forced alignment уже созданного SRT, а точная
русская модель закреплена revision и SHA-256. Он не требует source checkout во
время запуска и никогда не подменяет отсутствующее выравнивание выдуманными
таймкодами.

**После выполнения:** включить «Темы и таймкоды»; Review/Evidence/Knowledge
остаются отдельным этапом до реального authoring/review пути.

## Этап 2 — SeminarText: Review, Evidence и Knowledge

**Цель:** сделать настоящий controlled workflow, не имитацию знаний.

1. Преобразовать topic drafts в versioned review input.
2. Добавить явные действия пользователя для принятия/отклонения; никакого
   автоматического semantic acceptance.
3. Только после ReviewDecision создавать Evidence и Knowledge с полным
   provenance.
4. Экспортировать в Obsidian/OneDrive только проверенные пакеты.

## Этап 3 — VideoText runtime

**Цель:** реальные перевод, тематические клипы и media-processing из Integra.

1. Закрепить совместимый VideoText runtime, модели и лицензионную поставку.
2. Реализовать adapter для Integra-owned media и контракты output/provenance.
3. Сначала включить перевод; затем тематические клипы, использующие
   SeminarText topics; затем остальные media-output возможности.
4. Каждый output проходит real-media smoke на чистом bundle.

## Этап 4 — BookText OCR

**Цель:** локальный OCR для PDF/сканов/изображений.

1. Закрепить BookText version, OCR engine и модели с hash/preflight.
2. Adapter возвращает текст, confidence и page/region locators.
3. Показать OCR как машинский результат с маршрутом к странице/региону.
4. Затем включить document outline и связанные document workflows.

## Этап 5 — YouTube и последующие студии

После R14 в Integra подключён отдельный local runtime для выбранного
пользователем одиночного YouTube-видео: `yt-dlp` сохраняет медиа в проекте, а
затем оно проходит тот же source-first media pipeline. Это не даёт права
использовать аккаунт, публиковать что-либо или обрабатывать плейлисты.

Отдельными решениями остаются:

- live playlist discovery/download реализованы отдельным local runtime: он
  получает фактический inventory через `yt-dlp`, сохраняет provenance,
  нормализует его в принятый offline-контракт и скачивает элементы строго
  последовательно с checkpoint после каждого обработанного элемента.
  источников;
- Marketing, Learning, Assistant и social требуют отдельных production
  adapters и не могут быть открыты общей заглушкой.

## Обязательная проверка каждого этапа

1. Пинning и SHA-256 runtime/моделей.
2. Unit + bridge end-to-end + cancellation/retry tests.
3. `python3 scripts/validate_governance.py`, полный suite, `git diff --check`.
4. Чистая macOS build и smoke реального callable пути.
5. UI Implementation Matrix: источник, capability, компонент, runtime путь,
   доказательство, финальное UI-состояние.
