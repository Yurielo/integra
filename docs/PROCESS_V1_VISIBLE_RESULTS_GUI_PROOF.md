# Process v1: visible results, persistence and GUI proof

Date: 2026-09-22. This is a proof-first, documentation-only verification of
the frozen Process v1 Board. It starts at canonical `main`
`230845ce9847806c584bc33402467a9b19787ec9`, CURRENT
`current-v2-6dd918b453e051e38422e81e05141ce0fcae02a6e2ce1c5b0f8df3ec551de611`.
No product/runtime byte changed and no Candidate was rebuilt.

## Applicable evidence inventory

The exact current Candidate is
`candidate-v1-6dd918b453e051e38422e81e05141ce0fcae02a6e2ce1c5b0f8df3ec551de611`,
bound to source `10dcb5573728073ef42eea37783c67e0da838d02`. Its timeout/recovery
evidence is retained but not rerun: it does not prove visible result actions.
Prior current-main evidence establishes persisted project/run/output records,
but does not substitute for current packaged GUI proof of result viewing,
opening, export and reopen.

An objective normal-GUI check was performed with that Candidate and a newly
generated non-private, three-second WAV fixture (SHA-256
`dda88a05be436880eaa8817ab39ab2d903744e42323c092c7e0ee95402ed8072`). The
user interaction itself was GUI-only: choose **Видео или аудио с Mac**, select
the file in the native picker, choose **Расшифровка**, and press **Выполнить**.
The visible app state truthfully changed to **Выполняется**, `0 из 1`, stage
**Расшифровка**, then to **Ошибка** with a retry control. The silence fixture
returned `SeminarText transcription failed (exit 1); see owned adapter.log`.
It therefore proves visible progress and truthful failure presentation, not a
successful transcript result. No owner project or private source was opened:
the Projects view revealed existing owner projects, so verification stopped
before inspecting or reusing them.

## Frozen Board outcomes

| Board item | Frozen acceptance gate | Machine evidence | Human evidence required? | Result | Board transition |
| --- | --- | --- | --- | --- | --- |
| Unified results screen | Packaged result view; unavailable outputs honestly labelled | The Product Owner confirmed that the results screen aggregates outputs, but it presents implementation/component artifacts (for example `… SeminarText (JSON)`, `… VideoText (JSON)`, and Word Timeline JSON) as normal result actions. The owner did not accept that as a finished Process results experience. | No further verification can make the present UX satisfy this gate. | `OPEN_PRODUCT_GAP` | none |
| Open result | Open actual produced Process artifacts from GUI | Product Owner clicked **Открыть расшифровку (TXT)** from the Process results screen. It opened the correct persisted `transcript.txt` for the processed source. | No | `DONE` | `IN_PROGRESS → DONE` |
| Reopen after restart | Candidate close/relaunch/reopen proof with no hidden rerun | Product Owner completely exited Integra, relaunched the same `.app`, opened **Обработанные материалы**, and saw `video1591534861.mp4` as `COMPLETED` with persisted result actions. | No | `DONE` | `IN_PROGRESS → DONE` |
| Ordinary-file export | Selected ordinary Process files, not publication | Current Process result controls are **Открыть …** actions. The only explicit export/publication controls are **Экспортировать в Obsidian** and **Опубликовать в папку OneDrive**, which operate on reviewed packages and are not a normal-user export/save action for selected Process files. | No: a distinct user-facing path is absent. | `OPEN_PRODUCT_GAP` | none |
| GUI-only normal use | Complete selected scope through Finder-like GUI | Product Owner completed the representative normal GUI journey and reopened the persisted result without Terminal/Codex. | No | `DONE` | `IN_PROGRESS → DONE` |
| Real progress | Observable progress evidence | Candidate GUI visibly showed `Выполняется`, `0 из 1`, and current stage `Расшифровка` during a non-trivial run, followed by truthful `Ошибка`. | No | `DONE` | `IN_PROGRESS → DONE` |

The silent fixture is not representative speech and cannot establish a
successful ASR result; its generic adapter exit message remains recorded as
machine evidence, not a repair request. The Product Owner's separate successful
GUI observations are the basis for the three Board transitions and the two
results-surface product-gap classifications below.

## Product Owner GUI evidence

The Product Owner supplied the following real normal-GUI observations for the
exact owner-test Candidate named above. Screenshot evidence remains in the
controlling conversation; this report records the resulting product evidence
without copying private screenshots into the repository.

1. **Open result — PASS.** `Открыть расшифровку (TXT)` opened the correct
   `transcript.txt` for the processed source.
2. **Reopen after restart — PASS.** After a complete app exit and ordinary
   relaunch, `video1591534861.mp4` remained `COMPLETED` in
   `Обработанные материалы`, with its result actions available.
3. **GUI-only normal use — PASS for the representative journey.** The owner
   completed the journey and its reopen without Terminal/Codex.

These observations do not claim whole-Process acceptance or convert a
developer-oriented result list into a finished user result experience. The
separate Evidence/Canonical Evidence interaction is frozen for Knowledge, not
counted as a Process result gate.

## Remaining open UX rows

| Board item | Current state | Frozen acceptance gate | Owner observation | Current product path | Classification | Minimum required change |
| --- | --- | --- | --- | --- | --- | --- |
| Unified results screen | `IN_PROGRESS` | A packaged result view presents selected ordinary Process results cohesively; unavailable outputs are honest and internal component/provenance artifacts are not the normal-user result experience. | The visible screen exposes internal output/component artifacts such as SeminarText JSON, VideoText JSON and Word Timeline JSON. The owner did not accept this as a finished results experience. | `Обработанные материалы` → `ГОТОВЫЕ РЕЗУЛЬТАТЫ` → `renderResultRows`; it renders every stored output key as an **Открыть …** action. | `OPEN_PRODUCT_GAP` | Create a curated user-facing Process results presentation, while retaining provenance/internal artifacts outside the primary normal-user result set. |
| Ordinary-file export | `IN_PROGRESS` | Available readable transcript, cleaned-text and translation results can be exported/saved through a normal user action; this is distinct from publication. | No `Экспортировать`, `Сохранить как…`, or equivalent ordinary-file action was visible. | Ordinary artifacts have **Открыть …** actions. `Экспортировать в Obsidian` / `Опубликовать в папку OneDrive` are reviewed-package publication paths, not ordinary-file export. | `OPEN_PRODUCT_GAP` | Add an explicit user-facing export/save action for available readable Process artifacts, distinct from opening and publication. |

The smallest coherent future UX repair package indicated by this evidence is
**user-facing Process results and ordinary-file export**. Its frozen design is:

| Left | Right |
| --- | --- |
| Расшифровка — Открыть / Экспортировать | Очищенный текст — Открыть / Экспортировать |
| Перевод — Открыть / Экспортировать | Темы и таймкоды — Открыть |

Only cards for outputs that actually exist are shown. The normal desktop layout
has two columns; a narrow window collapses to one column without horizontal
scrolling. A separate normal Process action is **Открыть исходное видео/аудио с
расшифровкой**. SRT, Word Timeline, raw transcript/translation JSON, Topics
JSON, ASR diagnostics, model/runtime metadata and provenance are preserved in a
collapsed **Технические данные** area. Component names do not define the primary
result taxonomy. Evidence/Canonical Evidence actions are frozen for Knowledge;
Studio owns user-facing subtitle/translated-subtitle creation/export.

This is a classification and frozen design only, not a repair WP or authorization
to implement. No additional Product Owner action is required before that bounded
repair.

## Process-scope owner GUI protocol

Use this exact Candidate once, with one non-private local audio/video containing
ordinary speech and with no unrelated processing active in the same app-data
root:

1. Launch Integra normally from Finder. Choose **Видео или аудио с Mac**, select
   the source, choose **Расшифровка**, then press **Выполнить**. Observe a
   changing processing status/stage and terminal **Готово** without Terminal or
   Codex.
2. In **Готовые результаты**, verify the completed source and the ordinary TXT,
   cleaned-text, translation and Topics/timestamps cards that actually exist.
   Open the TXT and use the separate source-navigation action. User-facing SRT
   and Evidence/Canonical Evidence are outside this Process-scope protocol.
3. Close Integra normally only after no unrelated run is active. Relaunch it
   normally, choose **Проекты**, reopen this exact project/run, and confirm the
   same completed artifacts are still present without rerunning processing.

This is one compact human acceptance test, not Process v1 acceptance. Its
purpose is limited to the scoped Process results/persistence evidence above.

## Board and next action

Machine proof moved Real progress: **21 DONE / 9 IN_PROGRESS / 17 NOT_DONE / 1
BLOCKED** → **22 DONE / 8 IN_PROGRESS / 17 NOT_DONE / 1 BLOCKED**. Product
Owner evidence then moved Open result, Reopen after restart and GUI-only normal
use: **22 DONE / 8 IN_PROGRESS / 17 NOT_DONE / 1 BLOCKED** → **25 DONE / 5
IN_PROGRESS / 17 NOT_DONE / 1 BLOCKED**. The subsequent owner scope correction
reclassified user-facing SRT and translated SRT to Studio, and Review TXT/
Evidence interaction to Knowledge: **24 DONE / 4 IN_PROGRESS / 16 NOT_DONE / 1
BLOCKED** across the 45 active Process Board entries.

The remaining classifications above are evidence reconciliation only. They do
not create a repair WP, alter frozen Process scope, claim `PROCESS V1
USER_ACCEPTED`, or select a next implementation action.
