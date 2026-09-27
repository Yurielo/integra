# Process V1 Topic Summary Proof

Scope: Excel #24 / S12 partial + S13 only. This delivery exposes the existing
real Topic summary in the normal Process result. It does not add a Topic
engine, Topic-detail selection, Topic translation, Knowledge, Evidence,
provider selection, a Process routing switch, Stage B, installation, or
deployment.

## User-visible result

The normal Process `Темы и таймкоды` card now has `Открыть темы` alongside the
existing `Проверить темы` action. The read-only view presents each persisted
Topic as three distinct fields: `Время`, `Тема`, and `Краткое содержание`.
The latter is the Topic Engine's actual summary; raw JSON remains secondary.

`Проверить темы` remains the sole human Process review path. When a review has
already been saved, the ordinary view reopens the reviewed title and summary
through the existing receipt, decision and contract verification rather than
returning to the machine draft.

## Contract and failure boundary

The selected SeminarText Topic Engine creates a title and one neutral summary
for each labelled range, then retains the original start/end times and segment
IDs. The Integra reader verifies the persisted component identity,
`REVIEW_REQUIRED` authority, title, non-empty source summary and valid time
range before it exposes a Topic. It returns a content digest and source span
for each displayed item.

An empty or malformed source summary is not replaced with a title, quotation
or placeholder: opening summaries fails closed while the stored Topic artifact
and any transcript remain unchanged. Existing valid topic outputs are read
without rerunning the Topic Engine.

## Candidate evidence

Candidate `candidate-v1-a52cd2b257c55f0c50251ec21c253a3370de9d72f16148459650243c5fb3b669`
was built from source `5301527da6d447e474ec0df9ed657b836ef7d1a1` and archived
at `~/Library/Application Support/Integra/Build Archive/candidate-v1-a52cd2b257c55f0c50251ec21c253a3370de9d72f16148459650243c5fb3b669/afc07aee895fe1e4cefd882eafae1956ce44a5bf6f62d38fe676f5d84928c925`.

Its packaged bridge read a real generated Topic for a 16-second Russian test
recording. The returned summary was `В этом сегменте рассматриваются ключевые
этапы создания эффективного плана для групповой работы.` and remained distinct
from the title `Составление плана занятия`; it retained time `0.000–16.000 s`
and source segment range `1–4`. The bridge produced no review decision and no
provider execution.

Focused tests cover the ordinary bridge, source/span binding, absent-summary
failure, normal UI wording, Process-only review, reviewed-state reopen,
translation preservation and application lifecycle. The complete suite is
re-run after the governed Proposal Lite is recorded.
