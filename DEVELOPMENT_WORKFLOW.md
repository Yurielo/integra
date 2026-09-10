# Integra Development Workflow

## 1. Authority order

When sources disagree, use this order and fail closed rather than blending
conflicting claims:

1. **Factual state:** repository, GitHub, component, runtime, artifact, and
   external-platform facts verified at execution time.
2. **Authorization:** the latest explicit Product Owner instruction applicable
   to the exact action.
3. **Governance:** accepted files on Integra `main`, especially the product
   definition, architecture, autonomous execution policy, and machine-readable
   state.
4. **Evidence only:** Issues, PR discussions, historical reports, plans, and
   conversations that are not themselves current authorization.

Silence, roadmap proximity, an open Issue, or a technically obvious next step
does not authorize protected data access, semantic acceptance, external
publication, destructive migration, source-repository changes, merge, release,
or credentials.

## 2. Issue-first delivery

1. Verify current `main`, the target Issue, dependencies, and repository state.
2. Work on `codex/issue-<number>-<slug>` unless the Issue specifies otherwise.
3. Keep the change bounded to one Issue and preserve unrelated user work.
4. Record contracts and migration behavior before implementation that depends
   on them.
5. Run focused tests, the full supported suite, governance validation, and
   `git diff --check`.
6. Open a PR with acceptance evidence and explicit source-product impact.
7. Merge and eligible governed local runtime reconciliation proceed
   automatically when every fail-closed condition in
   `docs/AUTONOMOUS_EXECUTION_POLICY.md` is proven. Release and protected or
   external actions retain their explicit gates.

## 3. Autonomous technical work

After a bounded task is authorized, Codex continues through safe deterministic
substeps: inspection, implementation, tests, documentation, local fixtures,
scope checks, commit, push, PR preparation, safe merge, post-merge verification,
and transition to the next dependency-ready roadmap Issue. Routine stage
completion is not a human gate.

### 3.1 Agent routing

The governed team is defined in
`docs/architecture/AGENT_TEAM_OPERATING_MODEL.md`. `product-owner` is the lead
coordinator for material or multi-role work; a fully specified narrow task may
be routed directly to its specialist. The coordinator chooses a risk-based
minimal set, assigns one owner per shared write scope, and consolidates
evidence. It must not make all roles a serial checklist or ask the human Product
Owner to relay deterministic handoffs.

Role authority is:

- **AUTO:** bounded planning, implementation, tests, repository documentation,
  read-only review, CI repair, verified merge, Issue lifecycle, and eligible
  governed local reconciliation under accepted policy;
- **ADVISORY:** specialist recommendations that would change product,
  architecture, lifecycle, semantics, release, or protected boundaries;
- **RESERVED_HUMAN:** the genuine gates listed below.

## 4. Genuine human gates

Stop only when the next action requires at least one of:

- a new or changed product, architecture, lifecycle, or authority decision;
- authoritative semantic authoring or acceptance;
- access to private data, governed datasets, Gold, credentials, or accounts;
- a real external publication, deletion, message, or account mutation not
  already covered by an accepted standing policy;
- destructive or irreversible migration;
- source-repository modification outside the exact authorized scope;
- release, live deployment/publication, or retirement authority not already
  granted;
- resolution of an unexplained conflict, drift, data loss, or ambiguity.

Human review is exception-only. Repeated exceptions should be clustered into a
single evidence package and one explicit bulk decision whenever authority and
the review contract permit it.

Verified in-scope PR merge, explained governed local runtime reconciliation,
Issue closure, CI handling, and roadmap advancement are explicitly not human
gates. Their exact fail-closed conditions are defined in
`docs/AUTONOMOUS_EXECUTION_POLICY.md`.

## 5. Protected source applications

- SeminarText and VideoText remain independently runnable until a separate
  post-acceptance retirement decision.
- Integra consumes pinned components through versioned contracts.
- Discovery is read-only; migration is dry-run first and copy-on-write.
- One writer may own a mutable entity at a time under the Project Lease.
- Project Lease operations follow `schemas/project_lease_v1.schema.json` and
  `docs/architecture/DATA_OWNERSHIP_AND_PROJECT_LEASE.md`; expiry alone never
  authorizes recovery.
- A standalone regression blocks promotion of Integra.

## 6. External systems

Adapters use official supported APIs only. Implementation authority does not
grant live account access. Tokens belong in the macOS protected credential
store and must never enter the repository or logs. Ambiguous publication
results are not retried automatically.

## 7. Completion evidence

Every completed Issue records branch and commit identities, changed files,
tests, compatibility impact, data/account access, migrations, external actions,
known limitations, participating agent roles and their evidence, and the next
genuine authorization boundary.
