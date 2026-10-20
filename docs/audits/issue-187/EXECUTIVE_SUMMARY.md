# Итог аудита интеграции Integra

## Короткий вывод

Integra уже является интеграционным приложением, но текущая обработка видео
ещё использует гибридный маршрут. Это не «четвёртая самостоятельная программа
для распознавания»: Integra хранит проекты, задания, версии, происхождение,
интерфейс и результаты, а вычислительные возможности берёт из source products.

### Что уже интегрировано

- **SeminarText:** реальная расшифровка в обычном Process-пути, контроль
  качества, Topics, word timeline/Evidence/Knowledge-контракты и review
  механика.
- **VideoText:** реальные операции с медиа — субтитры, клипы, скорость,
  аудиоанализ и SRT-сервис; в исходниках также есть сильный ASR и topic stack.
- **BookText:** локальный OCR запускается из Integra через проверенный pinned
  runtime; результат привязан к исходному файлу и выбору страниц.
- **Integra:** владеет проектами, источниками, jobs/recovery, provenance,
  persistence, source-first UI, cross-navigation и экспортом в Obsidian.

### Что пока дублируется или пересекается

Есть два ASR и два topic stack: активный SeminarText и потенциальный VideoText.
Это исторически объяснимый переходный слой, но его нельзя считать завершённой
интеграцией. Есть также два translation implementation, однако активный
production runtime уже принадлежит Integra (TranslateGemma), а не VideoText.

Повторяющийся synthetic transcript не доказывает дефект ASR: по имеющимся
данным невозможно честно сказать, породил ли повтор source media, fixture,
ASR, сборка текста или последующий слой.

### Может ли VideoText заменить SeminarText для Process?

**Потенциально — да, но сегодня это не доказано.** VideoText уже содержит
подходящие функции ASR, VAD, сегментации, проверки повторов, SRT и topics.
Однако Integra пока не использует их в обычном Process-маршруте. Не доказаны
совместимость артефактов, безопасная retry/recovery семантика, topics/review,
multi-source и точный Candidate без вызова SeminarText.

Поэтому правильный текущий статус: **VideoText-only Process ещё не доказан**.
SeminarText нельзя удалять или отключать.

### Что уникально остаётся у SeminarText

Canonical Evidence/Knowledge, Concepts/Relations, проверяемая семантическая
review authority, word/evidence contracts и текущий production путь Topics.
VideoText не имеет доказанного функционального эквивалента этим слоям.

### Что не хватает BookText

BookText OCR уже вызывается, но его полный пакет ещё не передаётся в Integra:
координаты каждого блока, review statuses, таблицы, иллюстрации, CDM,
переводы и надёжный import/reopen в Knowledge. Контракт адаптера пока DRAFT.

### Что Integra должна оставлять у себя

Интеграцию и управление: проекты, источники, ревизии, jobs, отмену/recovery,
provenance, UI, Process result contract, cross-source navigation, persistence,
Obsidian/OneDrive. Она не должна заново писать ASR/OCR/topic engines.

## Практический следующий шаг

Не строить новую архитектуру. Выполнить ограниченный proof #187: подключить
существующий VideoText ASR через адаптер, прогнать три зафиксированных русских
контрольных видео и доказать: exact artifacts, warm reuse, quality/retry,
отсутствие SeminarText в выбранном Process route и сохранение всех
Process-гарантий. Только затем принимать решение о дальнейшей миграции.
