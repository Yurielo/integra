# Integra Codex operating instructions

Before changing or evaluating Integra product behavior, architecture,
governance, lifecycle, migration, publishing, or source-application
integration, read these current repository truths:

1. `docs/PRODUCT_DEFINITION.md`
2. `docs/architecture/INTEGRA_ARCHITECTURE.md`
3. `state/integra_state_v1.json`
4. `DEVELOPMENT_WORKFLOW.md`
5. `docs/AUTONOMOUS_EXECUTION_POLICY.md`
6. `docs/architecture/AGENT_TEAM_OPERATING_MODEL.md`

Work only from the accepted roadmap, an explicitly authorized GitHub Issue, or
an exact Product Owner instruction. The accepted roadmap plus satisfied
dependencies provides standing authority for safe technical delivery under
`docs/AUTONOMOUS_EXECUTION_POLICY.md`. Open Issues, prior reports, and silence
are not authority for protected data, semantic acceptance, live external
publication, destructive migration, source-repository changes, release, or
credential access.

Within bounded authorized work, complete all safe deterministic technical
substeps without routine human dispatch. Do not ask before the next
dependency-ready Issue, verified PR merge, post-merge verification, or eligible
governed local runtime reconciliation. Stop only at a genuine decision or
authorization boundary defined in `DEVELOPMENT_WORKFLOW.md` and the autonomous
execution policy.

SeminarText and VideoText are protected source products. Unless the exact task
explicitly authorizes a source-repository change, treat them as read-only,
pinned external components. Never overwrite source projects during migration.

Before a PR, run the governance validator, relevant focused tests, the full
supported suite, and `git diff --check`. Report the exact changed-file scope at
a genuine gate or final completion; routine reports must not pause execution.

## Governed agent team

The canonical team contract is
`docs/architecture/AGENT_TEAM_OPERATING_MODEL.md`, with machine-readable truth
in `state/agent_team_v1.json` and registrations in `.codex/agents/`.

`product-owner` is the lead coordinating agent. For material multi-module or
product-facing work it establishes the bounded outcome and activates the
smallest useful specialist set. It does not replace the human Product Owner or
create routine approval stops. Narrow tasks with complete Issue scope may go
directly to their implementation owner.

QA and PR review are independent evidence roles. Agent handoffs must preserve
authority, scope, write ownership, acceptance criteria, actual verification,
and the next technical owner or genuine gate. Jira and Confluence names are
compatibility role IDs only; GitHub and repository documentation are the
defaults unless an exact instruction authorizes another external system.
