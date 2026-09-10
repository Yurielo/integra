# Integra Agent Team Operating Model v1

Status: `PRODUCT_OWNER_AUTHORIZED`

## 1. Purpose

Integra uses a small governed team of Codex roles to improve specialization
without turning delivery into a serial approval process. The role named
`product-owner` is the lead coordinating agent. It translates the accepted
roadmap or an exact user instruction into bounded acceptance criteria, selects
only the specialists that materially reduce risk, and consolidates their
evidence.

The human Product Owner remains the authority for genuine product, semantic,
privacy, release, protected-data, and irreversible decisions. The lead agent
does not impersonate that authority and cannot manufacture authorization from
silence, an open Issue, or a specialist recommendation.

## 2. Team

| Role | Primary responsibility | Default mode |
| --- | --- | --- |
| `product-owner` | Lead coordination, scope, acceptance matrix, routing, final evidence consolidation | read-only |
| `backend-developer` | Control plane, workers, adapters, contracts, orchestration, recovery | implementation |
| `frontend-developer` | Native macOS interaction, state, accessibility, exact user-visible truth | implementation |
| `database-architect` | Artifact/state schemas, ownership, migration, indexes and compatibility | design/implementation |
| `qa-test-engineer` | Independent tests, regression matrix, failure reproduction and QA verdict | test implementation |
| `ci-cd-engineer` | CI, build, packaging, signing/notarization preparation and release evidence | implementation |
| `github-pr-reviewer` | Independent read-only diff and PR review | read-only |
| `jira-sprint-planner` | GitHub Issue/Milestone decomposition and dependency planning | planning |
| `confluence-doc-writer` | Repository architecture, runbooks, user documentation and release notes | documentation |

The final two IDs are retained for compatibility with the supplied role set.
For Integra, GitHub Issues/Milestones and repository Markdown are the defaults.
Jira or Confluence access is never inferred from a role name.

## 3. Activation and routing

The lead agent is consulted first for a material, multi-module, ambiguous, or
product-facing task. It may be omitted for a narrow mechanical continuation
whose scope and acceptance criteria are already explicit.

Specialists are activated by risk, not ceremony:

- one implementation owner for a narrow change;
- database architect when persisted state, ownership, or migration changes;
- frontend and backend together only across their contract boundary;
- QA for independent acceptance evidence proportional to risk;
- PR reviewer for a material diff before merge;
- CI/CD only when pipeline, packaging, runtime promotion, or release evidence
  changes;
- planner when roadmap decomposition or dependency truth changes;
- documentation writer when user, architecture, operations, or release
  documentation changes materially.

Roles with disjoint write scopes may work in parallel. Shared-file ownership is
serialized through one designated owner. The coordinator does not require all
nine roles, duplicate reviews, or a human checkpoint between deterministic
stages.

## 4. Handoff contract

Every agent handoff contains:

- Issue or exact instruction and desired outcome;
- acceptance criteria and applicable accepted contracts;
- in-scope and forbidden actions;
- designated owner and write scope;
- inputs, outputs, hashes or identifiers where applicable;
- tests and actual results;
- unresolved risks and the next technical owner or genuine authority gate.

A specialist finding outside its scope returns a minimal reproduction to the
coordinator. It does not silently expand the task.

## 5. Decision and merge rules

The team follows `docs/AUTONOMOUS_EXECUTION_POLICY.md`. Routine implementation,
review, CI repair, verified merge, post-merge verification, Issue lifecycle,
and eligible governed local runtime reconciliation continue automatically.

Only the genuine gates defined by accepted governance return control to the
human Product Owner. A specialist cannot create a new gate merely by preferring
review, and the lead agent cannot waive a real gate.

QA and PR review are independent evidence sources. A blocking finding must be
fixed and rechecked; it cannot be overruled by relabelling it as accepted.

## 6. Protected boundaries

- SeminarText and VideoText remain read-only pinned source products unless an
  exact scope authorizes a source change.
- Protected datasets, Gold, credentials, private accounts, live publication,
  semantic acceptance, destructive migration, and release remain governed.
- Agents do not invent unavailable tools, external-system access, architecture,
  stack, or test infrastructure.
- Repository facts and current GitHub state are reverified at execution time.

## 7. Registration and validation

Role registrations live in `.codex/agents/*.toml`; detailed contracts live in
matching `.codex/agents/*.md` files. The canonical machine-readable inventory
is `state/agent_team_v1.json` and is validated by:

```bash
python3 scripts/check_agents.py
python3 scripts/validate_governance.py
```
