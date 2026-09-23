# Process v1 Topic Review: saved review reopen repair

Status: owner GUI evidence accepted for the bounded `Topic edit/confirm` Board
row. This evidence does not change CURRENT, Process scope, Knowledge/Evidence
semantics, or confer whole-Process `USER_ACCEPTED`.

## Real owner evidence and classified divergence

The Product Owner changed `Проверка распознавания речи` to `Тест
распознавания речи`, selected confirmation, and received `Проверенные темы
сохранены.`. The persisted reviewed contract contains the new title and the
persisted decision is `RENAME` under `PROCESS_HUMAN_TOPIC_REVIEW`.

On reopening, the old title appeared because the bridge's prepare path always
called `prepare_process_topic_review(... topics_path=outputs["topics"])`.
That raw machine artifact correctly still contains the old title, but it is no
longer the user-facing authority after a saved human review. The write did not
fail; the read path had no reviewed-result precedence.

Classification: `TOPIC_REVIEW_REOPEN_MATERIALIZATION_DEFECT`.

## Bounded repair

When all three persisted Process-review outputs are present, reopen now:

- resolves them through the existing persisted-project path guard;
- verifies the reviewed-contract, receipt, decisions, result hashes, source,
  package binding, and `PROCESS_HUMAN_TOPIC_REVIEW` authority; and
- materializes the reviewed contract as a read-only Process Topic Review.

It never silently falls back to machine Topics if the saved state is partial or
invalid. A newly unsaved review continues to use the existing pinned machine
preparation path. The Process dialog exposes the saved title, summary, time
span, and persisted action without manual reviewer-ID input or any Knowledge or
Evidence transition.

## Focused proof

- 15 direct Topic-review/Process-surface regressions pass, including the new
  bridge reopen regression: machine Topics remain `Первая`, while reopening
  after `RENAME` returns `PROCESS_TOPIC_REVIEWED` and `Переименована`.
- The persisted-runtime regression verifies the same precedence and proves a
  tampered reviewed contract fails closed instead of falling back to machine
  Topics.
- The wider causally related suite ran 35 tests; four pre-existing tests were
  skipped only because they require an unavailable external runtime. The 15
  mandatory reopen regressions were not skipped.
- The fresh Candidate passed native self-test and manifest validation. Its
  manifest is preserved in the linked evidence file and binds source
  `ba94b39ac75517f6f5fb485e5a0fb93927895e40`.

## Final Product Owner GUI evidence

On Candidate `candidate-v1-65bf72d1262146c9137aca433b51ae3974d98bc4c8ed37042db13b46e0318a1d`,
the Product Owner opened Process Topic Review, renamed `Проверка распознавания
речи` to `Тест распознавания речи`, selected confirmation, saved, closed, and
reopened the review. The app reported `Проверенные темы сохранены.` after save.
The reopen view reported `Сохранённые решения человека для этого источника.`,
displayed `Тест распознавания речи`, and showed `Переименовано`.

The exact persisted contract confirms the same title and the exact one-decision
pinned-contract action `RENAME`. This is truthful: a confirmation accompanied
by a title edit is represented as `RENAME`, not a fabricated second `ACCEPT`.
The hash-bound receipt has authority `PROCESS_HUMAN_TOPIC_REVIEW`, binds the
owner project/run/source/topic, preserves the original machine Topic as
provenance, and states `Process Topic review only; no Evidence acceptance or
Knowledge inclusion occurred.` Its `COMPLETE_BENCHMARK_SEGMENTS` mapping is
unchanged. The Board transition is only `Topic edit/confirm: IN_PROGRESS →
DONE`.
