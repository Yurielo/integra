# Process V1 Topic Detail Choice Proof

Scope: Excel #25 / S13 only.  This delivery adds a bounded normal-Process
choice for the existing pinned SeminarText Topic Engine.  It does not add a
second Topic Engine, a second Topic representation, Topic translation,
Knowledge or Evidence routing, a Process routing switch, Stage B, installation
or deployment.

## Supported choice and default

The normal media Process screen shows one segmented control only after
`Темы и таймкоды` is selected:

| User label | Executed pinned parameter | Meaning in the pinned source |
| --- | --- | --- |
| `Крупно` | `low` | minimum topic duration 180 seconds; hard boundary gap 60 seconds |
| `Обычно` | `auto` | minimum topic duration 60 seconds; hard boundary gap 25 seconds |
| `Подробно` | `high` | minimum topic duration 45 seconds; hard boundary gap 15 seconds |

`Обычно` / `auto` is the default.  These are the complete exposed choices
because they are the exact accepted `DETAIL` values of the pinned source.  They
are not represented as a general semantic hierarchy or as arbitrary user
defined levels.

## Execution and provenance

The normal Process request carries `topic_detail`; `prepare_run` validates it
before a run record is created.  The requested value persists in the run record
and reaches the one source job.  `seminartext_runtime` invokes the internal
`seminartext_topic_detail_adapter`, which composes the same pinned SeminarText
functions as the existing Topic worker and forwards the selected value only to
`analyze_window_boundaries`.

The saved `topics.json` must return the same value as both `detail` and
`topic_detail.requested/executed`.  A mismatch, malformed value, or an
unsupported choice fails closed; no normal-detail substitution is made.  The
source result retains the executed record.  Reopening normal Topics and
Process Topic Review rereads that saved provenance.  Pre-S13 saved Topics are
readable as `UNAVAILABLE_LEGACY`, never retroactively labelled as `auto`.

The new adapter is an Integra-owned adapter boundary only.  The provider
identity, pinned commit, model and source-function composition remain in the
persisted Topic artifact/runtime provenance; the normal UI exposes only the
user meaning of the selected level.

## Real production evidence

With pinned SeminarText commit `13644d262776aacdf36221b9a9fc7ebd0a7c0737`
and local `gemma3:4b`, the same short real Russian SRT was processed
sequentially through the new adapter on 2026-09-28:

| Executed detail | Persisted detail | Generated topic count |
| --- | --- | ---: |
| `low` | `low` | 1 |
| `auto` | `auto` | 2 |
| `high` | `high` | 3 |

Thus the choice reaches real production boundary generation and changes the
saved Topics result; it is not a UI-only flag.  Machine Topics remain
`REVIEW_REQUIRED`.  The normal Topic summary remains the original persisted
source summary and is not generated or altered by this control.

## Failure and compatibility boundary

An unsupported detail is rejected before execution.  A source model response
that violates the existing title/summary contract still fails closed rather
than being repaired into an invented successful Topic.  Existing Process Topic
Review remains a source-hash-bound review of the same machine Topics artifact;
it neither re-executes the engine nor creates Knowledge/Evidence authority.
