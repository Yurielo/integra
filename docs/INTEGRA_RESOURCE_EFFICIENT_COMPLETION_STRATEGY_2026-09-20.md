# Resource-efficient completion strategy

Issue #151 proposal. Planning only. It preserves #150's binding controls and
does not alter product code, pins, deployment, or historical state.

## 1. Executive strategy and MCWMA

The shortest reliable path is one vertical **Minimum Correctly Working macOS
App** journey:

`Finder launch → local Russian video → ASR → TXT/SRT → Word Timeline → Topics
→ persisted/navigable results → owner acceptance`.

Maturity is strictly `PLANNED → IMPLEMENTED → INTEGRATED →
PACKAGED_E2E_PROVEN → USER_ACCEPTED`. Only the human Product Owner assigns the
last state. Historical Issue closure, roadmap `ACCEPTED`, source tests and
component smoke prove none of the higher states.

Must work now: source selection, truthful capability plan, bundled production
execution, results/navigation, error/progress and Candidate ID diagnostics.
Must be stable now: bounded workers, fail-closed identities, persisted
diagnostics, retry/cancel truthfulness. Translation, OCR, YouTube, publishing,
knowledge expansion and media variants may be unavailable; they must not be on
the critical path. Marketing, learning, social, release/signing and source
consolidation defer until MCWMA acceptance.

## 2. Diagnosis

| Waste | Evidence | Process control |
| --- | --- | --- |
| Component PASS became product claim | #142/#144/#146 passed before next owner failure | only journey gate opens owner handoff |
| Easy fixture overstated confidence | #149 7-second TTS did not reproduce #148 | deterministic + realistic + failure-class fixture |
| Candidate/interpreter drift | #149 used #146e and Python 3.14; GUI uses `/usr/bin/python3` | immutable Candidate ID and GUI-equivalence assertion |
| Diagnostics lost | old Word worker/bridge discarded status and logs | persisted common process diagnostic before another speculative repair |
| Long stack evidence drift | #141→#149 | one clean stabilization baseline after controls |
| Owner used as integration tester | #144/#146/#148 | hard Owner Entry Gate |
| Historical roadmap inflated reality | main says R14 ACCEPTED despite owner failures | dashboard reports maturity/evidence, not issue state |

## 3. Critical path and lifecycle

`P0 truthful baseline → P1 candidate/observability controls → P2 classify #148
failure → P3 root-cause repair/regression → P4 two-fixture packaged E2E → P5
owner acceptance` is the critical path. Freeze unrelated implementation while
any stage is red.

Evidence ladder: UNIT, COMPONENT, INTEGRATION, PACKAGED_E2E_DETERMINISTIC,
PACKAGED_E2E_REALISTIC, KNOWN_FAILURE_REGRESSION, USER_ACCEPTANCE. Each proves
only its named layer. A failed owner milestone returns to P2; the owner does not
test intermediate repairs.

## 4. Candidate, observability and Owner Entry Gate

Build emits an immutable manifest and Candidate ID binding Integra commit/tree,
clean state, build command, bundle digest, components/hashes, actual GUI
interpreter/architecture, Word runtime/model, Ollama contract and timestamp.
Every result names that ID; rebuild means new ID.

Before a second external-worker attempt, retain Candidate/run/stage IDs, exact
command and relevant sanitized environment, timeout, exit status, bounded
stdout/stderr, input/output hashes and validator reason. No release-blocking
`DEVNULL` without an equivalent retained record.

Owner receives a candidate only when the same ID has build/self-test, runtime
identity, deterministic E2E, realistic E2E, known-failure regression and
recovery sanity green. Owner evaluates utility/UX/quality, not runtime setup.

## 5. Codex, agents and packages

One session owns one dominant uncertainty. Checkpoint/commit after
classification, repair and gate; report exact command, Candidate ID, inputs,
result and next cheap action. Use backend + QA + CI/CD for primary journey;
activate frontend only for proven GUI divergence, database for persisted-schema
behavior, architect for a material contract/NFR decision, reviewer only at a
material-diff boundary. Do not activate agents ceremonially.

One package has one outcome, one uncertainty, non-goals, cheapest test,
automated exit criterion and persisted handoff. Two speculative repairs maximum
before observability/root-cause escalation; one owner retest per milestone;
full suite only after focused gates are green and before merge.

## 6. Branch/PR reset

#141/#143/#145/#147/#149 are historical draft evidence, not a merge queue.
After P1–P4 pass, create one clean stabilization branch from current `main` and
cherry-pick only verified repairs/controls. Do not rebase the long stack under
live evidence. Merge criteria: reviewed stabilization PR and complete Owner
Entry Gate. Then explicitly supersede/archive old drafts.

## 7. Cost versus information

| Gate | Cost | Catches | Does not prove | Blocks |
| --- | --- | --- | --- | --- |
| syntax/identity | VERY_LOW | stale hash/syntax | runtime | all |
| focused unit | LOW | validator branches | process | integration |
| preflight | LOW | missing runtime | orchestration | build |
| production integration | MEDIUM | persistence/handoff | package | E2E |
| packaged deterministic | HIGH | candidate happy path | realistic class | realistic |
| packaged realistic + regression | HIGH | media/failure class | UX | owner |
| owner acceptance | HIGHEST | usefulness/UX | future features | acceptance |

## 8. Completion plan

| Order | Outcome | Uncertainty | First test | Packaged gate | Owner gate | Agents | Stop |
| --- | --- | --- | --- | --- | --- | --- |
| P0 | truth baseline | identity/maturity | manifest schema | manifest embedded | none | backend, QA, CI/CD | contradiction |
| P1 | observable primary path | diagnostics/interpreter | unit failure paths | candidate diagnostic | none | backend, QA, CI/CD | unavailable identity |
| P2 | classify #148 | realistic fixture/root cause | fixture provenance | bridge repetition | decision only if private-only | backend, QA, CI/CD | missing evidence |
| P3 | restored journey | evidenced fix | root-cause regression | two-fixture E2E | none | backend, QA, CI/CD | semantic/model change |
| P4 | MCWMA handoff | coherent utility | manifest check | all primary rows | one owner acceptance | QA, CI/CD | owner tech failure→P2 |
| P5 | secondary journey | one capability | capability check | per-journey E2E | milestone only | minimal triggered | P0–P4 red |

## 9. Immediate three packages

1. P0/P1 Candidate Manifest plus complete worker diagnostic contract.
2. P2 #148 realistic, non-private failure-class classification; no owner test.
3. P3 only after P2: minimal repair, original-class regression and
deterministic+realistic E2E on one Candidate ID.

## 10. Dashboard, no-work list and preconditions

Add only `state/journey_status_v1.json` and a human
`docs/CURRENT_STABILIZATION_DASHBOARD.md`: journey, maturity, blocker, Candidate
ID, evidence, cheapest next action, owner, forbidden work and next owner gate.

Do not now work on Translation, BookText, YouTube, publishing, broad cleanup,
roadmap-state rewrites, governance refactor, stack merge, deploy or signing.

The app is correctly working only when one immutable Candidate ID has
GUI-equivalent interpreter/runtime, deterministic and realistic primary E2E,
known-failure regression, bounded observable failure/recovery, truthful
disabled secondary capabilities, and explicit human `USER_ACCEPTED`. #150 is
not complete; its final audit is a dependency for formal state/governance
migration, not a reason to weaken these controls.
