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

## Candidate retention

Follow `docs/CANDIDATE_RETENTION.md` before building, promoting or cleaning up
Candidates. Build only into a fresh owned output directory: the low-level
historical builder overwrites an existing application. Never use an archive
as a build output. Accepted and review-pending Candidates require a completed,
verified permanent archive of the actual application bytes. A manifest or Git
commit alone is not a backup. Temporary cleanup must preserve these Candidates
until that archive is verified. The promotion helper requires exact archives
of both the proposed and outgoing CURRENT applications in addition to the
existing owner-acceptance and proposal checks.

The later Product Owner capacity-rotation amendment is recorded in
`state/candidate_archive_rotation_policy_v2.json` and `docs/CANDIDATE_RETENTION.md`.
Once that policy is canonical on main, the existing manager may retire the
oldest full managed copy at the eight-copy limit after exact verification and
durable unavailable-byte evidence, even if its historical lifecycle decision
remains pending or accepted. The incoming Owner-test Candidate still needs its
own completed verified archive. A rotated older Candidate is not restorable or
promotable from metadata alone. An absent outgoing CURRENT archive remains a
promotion gate until a verified physical replacement exists. Never describe a
legacy observed-now attestation as an original publisher receipt.

## Unified four-product rules

Before drafting or executing work in this repository, explicitly resolve and read the complete canonical rules document:
`Yurielo/integra` `main:docs/governance/UNIFIED_CODEX_RULES.md`.

A URL or filename is not automatic instruction loading. Resolve `main` to a full Git commit using GitHub or Git, then read that exact blob and record the commit and SHA-256 in material task evidence. If GitHub is unavailable, use only a local Integra checkout whose commit identity has already been verified; otherwise fail closed on the missing source access.

This directive adds no runtime dependency. Repository-specific instructions, Product Rules, governance, lifecycle, and terminal-state requirements remain applicable and take precedence as required by unified rule 0.
