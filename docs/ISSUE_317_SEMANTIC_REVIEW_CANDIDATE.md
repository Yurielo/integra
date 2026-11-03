# Semantic Review Candidate — Issue #317

## Статус

`READY_FOR_OWNER_TEST`: Candidate подготовлен для ручной проверки владельцем
продукта. Это не является принятием продукта и не меняет `CURRENT`.

## Точная сборка

- Candidate: `candidate-v1-46bacd60f3f9320aafae735575e07c20666e7eaa8fdb7ed6a68223b5a558fd6f`
- Bundle digest: `1df9cfead00e90f37e4e824cc786d3227377b19b4b24765d4bdced0d312a6bc6`
- Manifest digest: `18000ea07734126cdbef5d472ba1ef87056a1f0bb01de737d099c399cd6fd11b`
- Product source: commit `5c6e31465572950dcb4a6ad630627d3b5c159d32`, tree `253487bba4d9edaae49951a100843590ac51302c`
- SeminarText semantic workflow: `ba4dc987b8fe48303ea4343a93e7b24c7eaf43ce`
- Semantic workflow file digest: `f4280f30a2290a11a95e496a69a24b62a67d44799bf960536fdfe48da56e12c4`

## Что проверять владельцу

1. Открыть архивный `Integra.app` именно из Candidate.
2. Выбрать подготовленный пакет Semantic Review и прочитать контекст,
   доказательство и локатор каждого предложения.
3. Проверить четыре понятных решения: принять, исправить формулировку,
   отклонить и отложить на следующий раунд.
4. Для исправления изменить только поля, обозначенные интерфейсом как
   редактируемые, затем явно подтвердить решение и убедиться, что запись
   появилась в истории решений.
5. Убедиться, что принятие не подменяет подтверждение: до явного подтверждения
   решение не фиксируется, после него история неизменяема.

## Автоматические доказательства

- `candidate_archive.py verify`: `PASS`, побайтная целостность архива.
- `candidate_protection_audit.py`: `authority_state=COMPLETE`, `blockers=[]`,
  восемь разрешённых архивных копий.
- Архивная ротация и безопасность удаления: 28 тестов, `PASS`.
- Нативный macOS UI/Runtime suite: `PASS`, включая Semantic Review и реальные
  проверки связанных компонентов.
- `READY_APP_PACKAGE_TEST_PASS`.

Подробные машиночитаемые результаты приведены в
`docs/evidence/issue317/automated-gates.json`. Все эти проверки являются
техническими; окончательная оценка понятности и полезности Semantic Review
остаётся за владельцем продукта.
