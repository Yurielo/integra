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
Must be stable/recoverable now: bounded workers, fail-closed identities and
persisted diagnostics; one controlled primary-journey failure is presented
truthfully; no partial or failed result is labelled successful; its diagnostic
and any valid preceding artifacts remain inspectable; then a subsequent new
primary run can start and complete without an unexplained app restart. This is
the minimum recovery sanity, not a promise to solve all #137 recovery UX.
Translation, OCR, YouTube, publishing, knowledge expansion and media variants
may be unavailable; they must not be on the critical path. Marketing, learning,
social, release/signing and source consolidation defer until MCWMA acceptance.

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

`P0 canonical stabilization baseline → P1 candidate manifest → P2 observable,
bounded #148 classification → P3 primary journey stabilization → P4 owner
acceptance` is the critical path. The canonical baseline is established before
any further diagnosis or repair; all Candidate IDs, diagnostics, regressions and
E2E evidence are produced on that single line. Freeze unrelated implementation
while any stage is red.

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
Before further product diagnosis/repair, establish one canonical stabilization
baseline from current `main`, using the matrix below. This strategy does not
create it or transfer code. The later implementation package will transfer only
the approved individual changes, never an entire PR by implication. Do not
rebase the long stack under live evidence. Merge criteria: reviewed stabilization
PR and complete Owner Entry Gate; then explicitly supersede/archive old drafts.

### Salvage Matrix

| Change | Source PR | Purpose | Owner-proven? | Technically-proven? | Currently required? | Decision | Reason |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Clean Word Alignment runtime | #143 | exact Python/WhisperX/model bundle | No | component/preflight only | Yes | NEEDS_MORE_EVIDENCE | #148 owner failure reached this runtime. |
| Ollama GUI resolution | #145 | resolve packaged GUI executable | Owner launch PASS | Yes, narrow | Yes | TRANSFER_EXACT | no contradictory evidence; still needs Candidate binding. |
| SeminarText active CLI SHA | #147 | align ASR expected hash with final pin | Owner capability PASS | Yes | Yes | TRANSFER_EXACT | exact stale-identity repair, independently byte-verifiable. |
| Word Timeline diagnostics | #149 | retain worker status/logs | No historic cause | focused unit only | Yes | REIMPLEMENT_CLEANLY | current form is incomplete for timeout/validator/job linkage. |
| Packaged primary E2E harness | #149 | bridge-path acceptance | No | invalid candidate/interpreter evidence | Yes | REIMPLEMENT_CLEANLY | retain intent; rebuild under canonical Candidate ID. |
| #138 governance/pin migration/docs | #141 stack | review-era reconciliation | No | mixed historical evidence | No for MCWMA | HISTORICAL_EVIDENCE_ONLY | not a primary-journey control. |
| unrelated workflow/governance changes | #141–#149 | accumulated stack work | No | varies | No | DROP | no transfer without package-level need/evidence. |

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
| P0 | canonical baseline | salvage + one line | matrix review | candidate manifest | none | backend, QA, CI/CD | ambiguous transfer |
| P1 | observable failure classification | diagnostics/interpreter/#148 | unit failure paths | bounded bridge attempts | none | backend, QA, CI/CD | missing original evidence classified |
| P2 | restored primary journey | evidenced fix or classification | regression | deterministic+realistic+recovery E2E | none | backend, QA, CI/CD | semantic/model change |
| P3 | MCWMA handoff | coherent utility | manifest check | all primary rows | one owner acceptance | QA, CI/CD | owner tech failure→P1 |
| P5 | secondary journey | one capability | capability check | per-journey E2E | milestone only | minimal triggered | P0–P4 red |

## 9. Immediate three packages

1. **WP1 — Canonical Stabilization Baseline + Salvage Matrix + Candidate
   Manifest.** Pure identity/control outcome: one authoritative Integra line
   and Candidate ID; no Word Timeline repair/debugging.
2. **WP2 — Observability + bounded #148 failure classification.** Small fixed
   protocol: three instrumented GUI-equivalent bridge attempts using saved
   owner-derived WAV/SRT only where authorized/available, plus one realistic
   non-private fixture; each records Candidate ID and diagnostics. A reproduced
   failure requires root cause and repair. Otherwise terminal classification is
   `HISTORICAL_NON_REPRODUCIBLE_WITH_INSUFFICIENT_ORIGINAL_DIAGNOSTICS`; retain
   observability/regression and stop historical speculation.
3. **WP3 — Primary Journey Stabilization.** On one Candidate ID run
   deterministic packaged E2E, realistic packaged E2E, applicable known-failure
   regression, and MCWMA controlled-failure/subsequent-run sanity. Owner
   handoff remains forbidden until all are green.

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
