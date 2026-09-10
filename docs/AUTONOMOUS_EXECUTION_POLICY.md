# Integra Continuous Autonomous Execution Policy

Status: `PRODUCT_OWNER_AUTHORIZED`

Authority: Product Owner directive of 2026-09-10 to continue approved Integra
roadmap work without routine dispatch or approval stops.

## 1. Operating rule

Codex executes the singular dependency-ready item in the accepted roadmap and
continues through every safe deterministic delivery step. Routine completion is
not a human gate and the Product Owner must not be used as a command courier.

Standing authority covers:

- starting the next dependency-ready roadmap Issue;
- inspection, design within accepted contracts, implementation, local fixtures,
  tests, documentation, commits, pushes, and PR creation;
- correcting in-scope implementation, test, review, and CI failures;
- merging an in-scope PR when all fail-closed merge conditions below pass;
- synchronizing `main`, post-merge verification, Issue closure verification,
  and deterministic governance/state reconciliation;
- one governed local runtime reconciliation when it is the only explained
  post-merge drift, the target is exact, the operation is reversible, and no
  protected data, credential, account, or external publication is involved;
- advancing immediately to the next singular dependency-ready roadmap item.

## 2. Fail-closed automatic merge

A PR may be merged automatically only when all of the following are true:

1. it implements one authorized roadmap Issue or an exact Product Owner task;
2. its head and base are verified and its diff contains no unexplained scope;
3. required focused tests, full tests, governance validation, and diff checks
   pass;
4. GitHub reports the PR mergeable and every required check successful;
5. no unresolved material review, conflict, source-product regression, data
   mutation, credential access, external action, or semantic promotion exists;
6. the merge method is the repository's established non-destructive method.

After merge, Codex verifies GitHub truth, fast-forward synchronizes local
`main`, runs proportionate post-merge checks, and continues. A failed condition
causes investigation and an in-scope repair when possible, not a routine
Product Owner dispatch.

## 3. Genuine human gates

Codex stops only when continuing requires at least one of:

- a product, architecture, lifecycle, authority, or prioritization decision
  with multiple materially different valid outcomes not resolved by accepted
  repository truth;
- authoritative semantic authoring, semantic acceptance, Concept identity, or
  domain review;
- protected/private data, Gold, credentials, accounts, signing identity, paid
  service, or permission that has not already been supplied for the exact use;
- live external publication, messaging, account mutation, payment, or another
  irreversible external action not covered by an accepted standing policy;
- destructive or irreversible migration, deletion, source-project mutation,
  source-product retirement, or user-owned file overwrite;
- security, privacy, legal, release, or final Product Owner acceptance;
- an unexplained conflict, provenance loss, runtime target ambiguity, unsafe
  resource state, or failure whose repair would expand scope or change policy.

At a genuine gate Codex presents one consolidated decision package with the
minimum choices needed. A sound is emitted only then, on an unrecoverable hard
stop, or on final release completion.

## 4. Events that are not human gates

The following never justify a routine stop when their fail-closed conditions
are satisfied:

- finishing an implementation or test phase;
- creating or updating a branch, commit, Issue, or PR;
- waiting for, inspecting, or repairing CI;
- merging a verified in-scope PR;
- running post-merge verification;
- reconciling explained local runtime drift through the governed mechanism;
- closing the completed Issue and updating roadmap state;
- starting the next dependency-ready technical Issue;
- reporting progress, token use, test counts, or a known non-blocking warning.

## 5. Safety boundary

Autonomy never converts unknown facts into permission and never broadens an
Issue. SeminarText and VideoText remain read-only pinned source products unless
an exact task says otherwise. Protected datasets, Gold, semantic authority,
credentials, live publication, destructive migration, release, and retirement
remain gated as defined above.
