# Integra Development Workflow

## 1. Authority order

When sources disagree, use this order and fail closed rather than blending
conflicting claims:

1. **Factual state:** repository, GitHub, component, runtime, artifact, and
   external-platform facts verified at execution time.
2. **Authorization:** the latest explicit Product Owner instruction applicable
   to the exact action.
3. **Governance:** accepted files on Integra `main`, especially the product
   definition, architecture, and machine-readable state.
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
7. Merge or deploy only when current policy or an exact Product Owner
   authorization permits the action.

## 3. Autonomous technical work

After a bounded task is authorized, Codex continues through safe deterministic
substeps: inspection, implementation, tests, documentation, local fixtures,
scope checks, commit, push, and PR preparation. Routine stage completion is not
a human gate.

## 4. Genuine human gates

Stop only when the next action requires at least one of:

- a new or changed product, architecture, lifecycle, or authority decision;
- authoritative semantic authoring or acceptance;
- access to private data, governed datasets, Gold, credentials, or accounts;
- a real external publication, deletion, message, or account mutation not
  already covered by an accepted standing policy;
- destructive or irreversible migration;
- source-repository modification outside the exact authorized scope;
- merge, release, deployment, or retirement authority not already granted;
- resolution of an unexplained conflict, drift, data loss, or ambiguity.

Human review is exception-only. Repeated exceptions should be clustered into a
single evidence package and one explicit bulk decision whenever authority and
the review contract permit it.

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
known limitations, and the next genuine authorization boundary.
