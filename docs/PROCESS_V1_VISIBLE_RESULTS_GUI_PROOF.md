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
| Review TXT | Candidate opening/provenance without source replacement | Candidate has the existing Review TXT control, but the isolated silence source did not produce a transcript to present for review. | Yes: correctness and usable review of a successful TXT are human-visible. | `AWAITING_OWNER_GUI_ACCEPTANCE` | none |
| Unified results screen | Packaged result view; unavailable outputs honestly labelled | Packaged UI showed the results/status surface and truthful failure state; existing output-row rendering is not treated as proof of a successful selected-result screen. | Yes | `AWAITING_OWNER_GUI_ACCEPTANCE` | none |
| Open result | Open actual produced Process artifacts from GUI | Existing normal GUI route labels transcript, SRT, review report and provenance actions; no successful non-private artifact was available for safe opening. | Yes | `AWAITING_OWNER_GUI_ACCEPTANCE` | none |
| Reopen after restart | Candidate close/relaunch/reopen proof with no hidden rerun | Current records are persisted, but safe isolated GUI proof requires a completed result. Normal shutdown against a default data root can also reconcile active owner work, so it was not used. | Yes | `AWAITING_OWNER_GUI_ACCEPTANCE` | none |
| Ordinary-file export | Selected ordinary Process files, not publication | Generated-output actions exist, but no completed isolated transcript/SRT was available. No source-level control is counted as user proof. | Yes | `AWAITING_OWNER_GUI_ACCEPTANCE` | none |
| GUI-only normal use | Complete selected scope through Finder-like GUI | Import, output choice, execution and visible terminal failure used normal packaged UI only. The completed-result/reopen portion requires the owner’s representative speech result. | Yes | `AWAITING_OWNER_GUI_ACCEPTANCE` | none |
| Real progress | Observable progress evidence | Candidate GUI visibly showed `Выполняется`, `0 из 1`, and current stage `Расшифровка` during a non-trivial run, followed by truthful `Ошибка`. | No | `DONE` | `IN_PROGRESS → DONE` |

There is no newly proven integration defect in the six human-bound rows. The
silent fixture is not representative speech and cannot establish a successful
ASR result; the generic adapter exit message is recorded as evidence, not
classified as a repair request in this verification-only package.

## OWNER_GUI_TEST

Use this exact Candidate once, with one non-private local audio/video containing
ordinary speech and with no unrelated processing active in the same app-data
root:

1. Launch Integra normally from Finder. Choose **Видео или аудио с Mac**, select
   the source, choose **Расшифровка** and **Субтитры (SRT)**, then press
   **Выполнить**. Observe a changing processing status/stage and terminal
   **Готово** without Terminal or Codex.
2. In **Готовые результаты**, verify the completed source and the ordinary TXT,
   SRT, cleaned-text/review-report actions. Open TXT and SRT using their normal
   GUI actions; verify each is the selected source’s artifact. Use the existing
   generated-output action to reveal/export the ordinary files—not publication.
3. Use **Проверить TXT и создать Evidence** only to inspect the Review TXT
   dialog and its explicit human-confirmation boundary; do not accept Evidence
   unless the full TXT is actually reviewed.
4. Close Integra normally only after no unrelated run is active. Relaunch it
   normally, choose **Проекты**, reopen this exact project/run, and confirm the
   same completed artifacts are still present without rerunning processing.

This is one compact human acceptance test, not Process v1 acceptance. Its
purpose is only the six rows above.

## Board and next action

Board changes only for Real progress: **21 DONE / 9 IN_PROGRESS / 17 NOT_DONE /
1 BLOCKED** → **22 DONE / 8 IN_PROGRESS / 17 NOT_DONE / 1 BLOCKED**.

Owner participation is now required for the six human-visible rows. The single
next Board-selected action after that evidence is **protective retry
VERIFY_EXISTING**, because it remains an `IN_PROGRESS` frozen MUST with an
existing production path and does not depend on a new integration package.
