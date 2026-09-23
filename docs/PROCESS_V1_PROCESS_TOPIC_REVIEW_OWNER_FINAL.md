# Process Topic Review: reviewer identity UX correction

Candidate `candidate-v1-d3fc1248e3c1485a4949d1412d1ff7844af5a4342aee4b365fce631082a4a7e7` is bound to clean source `6457911c967cc1b520ba96839bb3daaa9b8fa6cd` and `/private/tmp/integra-process-topic-review-owner-final/Integra.app`.

The normal Process dialog no longer displays or requires **Идентификатор проверяющего**. The bridge records the deterministic internal actor `integra-process-local-human` with pinned-contract `actor_type: product_owner`; Process authority remains `PROCESS_HUMAN_TOPIC_REVIEW`.

Focused regressions passed: field absence, save with no manual reviewer ID, provenance persistence, `RENAME`, `ACCEPT`, reopen/idempotence, no Knowledge/Evidence run outputs, Results surface, and persisted path containment. Candidate manifest validation and native self-test passed. The Completion Board remains `27 DONE / 1 IN_PROGRESS / 16 NOT_DONE / 1 BLOCKED` pending owner evidence.
