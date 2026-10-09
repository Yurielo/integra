# Isolated K2 Relation fixture — Issue #236

`scripts/k2_qa_fixture.py` supplies deterministic, synthetic QA execution input
with two different reviewed semantic units: solar-panel conversion and battery
storage. It never reads or alters the canonical generated-demo project.

This is a development-only fixture, not a change to K1 or K2 implementation,
Candidate bytes, semantic authority, CURRENT or the Process Board. Synthetic
reviewer choices apply only to the disposable fixture. They do not constitute
Product Owner acceptance or evidence about real seminar content.

## Execution contract

1. Revalidate retention/protection and the exact immutable Candidate archive
   with the supported archive verifier. Never execute/import retained bytes.
2. Use `temp_workspace_lifecycle.py run` with purpose `issue236-k2-fixture` and
   an admitted full-copy reservation. Copy the verified application into that
   workspace's `execution/Integra.app`. Do not build, sign or repackage it.
3. Validate the execution copy with `candidate_manifest.py validate`, including
   the expected Candidate, bundle and manifest digests.
4. In the supervised child run:

   ```sh
   python3 -B scripts/k2_qa_fixture.py --app "$INTEGRA_OWNED_WORKSPACE/execution/Integra.app"
   ```

5. Revalidate the execution-copy bundle and original archive afterward. A
   matching manifest alone is not proof of bundle integrity. Retain the stdout
   JSON receipt outside the disposable workspace; the supervisor removes its
   owned execution copy and fixture on completion/failure.

The script rejects foreign roots, wrong-purpose/dead-owner markers, writable
workspace modes, symlinks and existing output. All generated inputs live in the
fresh purpose-bound project; UUID5 identities, text and relative layout are
fixed. Absolute source locators necessarily bind the particular disposable
workspace. Repeating preparation against the same reviewed fixture must yield
an identical provisional Relation package.

The packaged bridge performs real K1 review-contract serialization, observes
at least two distinct reviewed units and Concept identities, and prepares a
Relation with exact endpoints and selected fragments. No K2 apply, acceptance,
export or publication occurs. Every proposal must remain `REVIEW_REQUIRED`
and no canonical Knowledge revision may exist. Too few units/Concepts, wrong
Relation endpoints or nondeterministic preparation fail closed.

## Verification boundary

Focused regressions cover deterministic input, actual pinned K1 serialization,
isolation, no overwrite, symlink/ownership rejection and the two-unit guard.
The local packaged proof additionally verifies real Concept → Relation
preparation using the existing immutable K2 Candidate. Neither fixture tests
nor this preparation-only proof claim completion of Issue #227, full native
K2 QA, Owner Test, Owner acceptance or delivery. Resuming #227 requires the
Product Owner's separate decision.
