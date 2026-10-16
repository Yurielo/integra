# CURRENT → PROPOSED → PROMOTED governance design

Design-only review for [Issue #163](https://github.com/Yurielo/integra/issues/163),
2026-09-22. Architectural and adversarial reasoning: Astra. Reference main:
`4f20ed5ad76af164a5561e33510b7d36b903eee8`. No product implementation,
governance migration, build, product test, owner retest, merge, or deployment is
part of this review. The mechanism below is a proposed implementation, not a
claim that the repository already enforces it.

## 1. Problem statement

Recovery changes the startup/run-lifecycle behavior of the packaged bridge.
That is a legitimate proposed product change, but neither its author nor a
green test can accept its user-visible behavior on the owner's behalf.
Comparing every feature branch only with accepted CURRENT hashes confuses two
questions: whether the branch is an explained, technically proved proposal,
and whether it is authorized to replace CURRENT.

The smallest useful change is an immutable proposal plus two independent
decisions: authenticated technical attestation, then human acceptance and an
exact promotion transaction. CURRENT is an append-only chain of accepted
records with one active reference; PROPOSED is a candidate for the next record;
PROMOTED describes a completed transition, not a third mutable copy of all
the same hashes. Feature authors may describe intended changes but cannot
provide the authority that makes their own description sufficient.

This preserves [#150](https://github.com/Yurielo/integra/issues/150) and
[#151](https://github.com/Yurielo/integra/issues/151): technical maturity and
human product acceptance remain separate; realistic packaged evidence and
the owner-entry gate are required; only the human Product Owner assigns
`USER_ACCEPTED`. The review is bounded to the sources named in #163. The broad
historical reading list in AGENTS.md is not an instruction to expand this
explicitly narrower issue.

## 2. Existing governance behavior

The checked-in `state/current_canonical_baseline_v1.json` is an older
stabilization supersession record, not a complete representation of the final
owner acceptance. It binds source `573c27b5c32646e83250e8c93b204867f4fee3e4`,
Candidate `candidate-v1-12b31da7ff02f9ad329c6d6a535d8ced3525ef52a727e3ab648c10acc3d94c03`,
and exactly five files: bridge, build script, app-test script, governance
validator, and current-baseline schema. The human's later
[#156 acceptance](https://github.com/Yurielo/integra/issues/156#issuecomment-5768296395)
is specifically for the primary journey on
`candidate-v1-c5851d168b116fed83109014519ebc01c0291e23705ac9d2ec0a4e5df2471960`,
bundle `90c6c816c7f4ec82b8a3393c46a5a96239ce7cbc16ba50a83677d78a0cdea8cb`.
[#159](https://github.com/Yurielo/integra/issues/159) and
[#160](https://github.com/Yurielo/integra/pull/160) promoted the accepted
lineage to reference main. These identities must remain distinct in migration;
the older baseline file must not be relabeled as the #156 accepted Candidate.

`scripts/validate_governance.py` hard-codes the baseline source, parent,
Candidate tuple and four expected current hashes. Its record also hashes the
validator itself. `_historical_hash_is_superseded` permits an exact
path/current-hash/old-hash supersession for R12/R13. Whole validation checks the
baseline as well as the historical records; the supersession helper alone is
not an authorization boundary. This catches isolated byte drift, but does
not supply independent authority against an author changing validator,
records, workflow and tests together. Self-hashing is not a trust root.

Existing governance tests cover byte mutation, missing/corrupt baseline,
Candidate ID substitution and exact historical supersession. The historical
test establishes that running the validator does not rewrite the two state
files; it does not authenticate their contents against an external immutable
snapshot. Candidate tests cover deterministic identity, ID mismatch, evidence
fields and the exclusion of Python caches. They do not establish who may
declare PASS or product acceptance.

The exact [#162 failed run](https://github.com/Yurielo/integra/actions/runs/35667745204)
ran on head `a1f28058822aabe7caebaacd6021b4ce7900ecd3` and stopped at:

```text
current canonical baseline hash differs: macos/Resources/bridge.py
R12 implementation hash differs: macos/Resources/bridge.py
R13 implementation hash differs: macos/Resources/bridge.py
```

The Linux test step follows validation and did not run after this failure;
no earlier whole-suite green can be inherited by this head. The failed run is
not proof of a completed GitHub test suite. `.github/workflows/quality-gate.yml` checks out
the PR content and executes its validator/tests on Ubuntu. It has read-only
repository contents permission, but PR-controlled validation logic is still
not an independent trust root. It does not attest the local macOS bundle.

Candidate v1 hashes `identity` to obtain the Candidate ID; the bundle digest
and build timestamp are outside that identity hash. `validate_manifest`
proves self-consistency; it does not prove clean source provenance. Generation
records dirty status but does not reject it, and its Git diff hash omits
untracked file content. Bundle hashing excludes every `*.pyc`/`__pycache__`
entry and omits file modes. Candidate evidence permits `SOURCE_UNBOUND`, null
identity fields and unauthenticated PASS claims. These are useful diagnostic
formats, not sufficient promotion credentials.

Read-only repository administration checks returned HTTP 403 for both main
protection and rulesets, with the response that the private repository needs
an upgrade or public visibility for that feature. The active GitHub identity
has admin/maintain/push permission. This review therefore cannot claim that
required checks, protected environments, or separate human credentials are
currently enforced. A comment from login `Yurielo` cannot distinguish the
human from an agent using that account's token.

## 3. Threat model

Treat feature source, tests, workflow files, proposed hashes, local reports,
PR text, tag names and submitted acceptance fields as untrusted input. The
feature author may make arbitrary coordinated changes to them. A compromised
candidate process has the same relevant threat as malicious feature code.
The owner and independently administered verifier are the explicit trust
roots; compromise of their isolated keys or administrator is outside the
guarantee and requires key revocation/rebootstrap. Merely assigning another
agent a QA role in the same account does not establish that isolation.

| Threat/error | Blocking invariant |
|---|---|
| Code and matching proposed hashes change together | Hash consistency only creates a submission. Independent attestation must bind the exact submission and bytes; promotion also needs owner authority. |
| Proposal generated from arbitrary dirty bytes | Only a trusted clean checkout/build or verified equivalent source mapping is admissible. Dirty, untracked, ignored build inputs and unresolved source mapping fail. |
| Candidate ID and proposed files disagree | Verify source commit/tree against Git objects, full manifest digest, actual bundle inventory and source-to-package mapping; require exact proposal equality. |
| Candidate never passed a required gate | Authenticated gate inventory is selected by trusted policy; missing, skipped mandatory, failed, stale or unbound gates fail. |
| Old evidence reused after a change | Attestation binds proposal digest, product closure, Candidate tuple, gate-plan digest and immutable evidence digests. No implicit transfer. |
| Proposal asserts `USER_ACCEPTED` | Proposal schema has no acceptance authority field; only a verified human-signed decision can yield that state for its exact journey. |
| Branch renamed to resemble a release/accepted branch | No branch-name rule changes admission or trust. Repository identity, immutable OIDs, policy and signatures decide. |
| Forged/missing acceptance, including an owner-account bot comment | Separate owner key, absent from developer hosts and execution workers, signs exact decision content. GitHub author labels and copied signatures over different data fail. |
| Product/runtime changes after owner acceptance | Acceptance names the immutable proposal/product closure/Candidate tuple; all later non-allowlisted changes invalidate it. |
| Merge resolves conflicts to different content | Compare the complete prepared merge tree with accepted head plus the exact promotion overlay; any unexplained entry, mode, deletion or addition fails. |
| R12/R13, prior CURRENT or rejected evidence rewritten | Compare immutable records with anchored content digests; history is append-only, not simply whatever the PR calls history. |
| Green CI proves only attacker-controlled consistency | Authoritative check runs a pinned trusted validator outside feature execution, with independently authenticated evidence and an external authority anchor. |
| Tags, evidence URLs or artifacts replaced | Names/URLs are locators only; resolve content-addressed bytes and authenticate producer, digest and subject. Missing immutable bytes fail closed. |
| Concurrent promotion, stale base, replay or rollback | Expected-base compare-and-swap, monotonic signed CURRENT sequence and consumed transaction ID; no silent rebase or stale authorization reuse. |
| Feature changes validator, gate policy or allowlist | Apply the already trusted policy. A policy change is an explicitly owner-authorized transition; the new policy cannot authorize itself. |

## 4. Authority model

Use one small owner-controlled verifier/promotion command with an append-only
receipt store outside the developer workspace. This is not a new release
platform. The owner root key and promotion credential must be unavailable to
ordinary agents and candidate execution processes. The verifier's attestation
key is separate from the owner's acceptance key.

| Assertion/action | Authorized producer and limits |
|---|---|
| Candidate identity | Builder calculates the manifest; independent macOS verifier authenticates correspondence to clean source and the actual app. Identity alone conveys no acceptance. |
| `PACKAGED_E2E_PROVEN` | Independent verifier supervisor after its required packaged gate plan passes on that tuple. It signs the result outside the untrusted worker. |
| `PROPOSED_BASELINE_VALID` | Trusted base-policy validator after all structural, delta, identity, evidence and authority-chain checks. This says technically admissible, awaiting the separate acceptance decision. |
| Owner acceptance / `USER_ACCEPTED` | Human Product Owner alone, using the isolated owner key and an explicit decision naming journey/scope and exact proposal/Candidate tuple. An automated signer must not infer this decision from tests. |
| Promotion to CURRENT | Owner-controlled command, executing a human-authorized transaction after fresh independent verification. Its restricted write credential cannot invent acceptance. |
| Policy/bootstrap/key changes | Human owner, using the established external root, exact policy digest, key IDs and scope. Feature credentials cannot rotate roots or broaden exemptions. |

All product/runtime changes initially require explicit owner acceptance before
promotion. To avoid owner retesting for pure bookkeeping, define one narrow
acceptance class: `NON_PRODUCT_METADATA_AUTHORIZED`. It applies only when the
trusted validator proves equality of the complete product closure and every
difference is an allowed, schema-validated metadata change. The owner may
authorize such a transaction without running the app again. This class never
creates or extends `USER_ACCEPTED`. Test, build, validator, schema, execution
config and dependency changes do not qualify merely because their author
calls them internal. Recovery requires `OWNER_PRODUCT_ACCEPTED`.

Concrete credential plan for this private repository: ordinary development
agents retain local write access but have only read-only GitHub credentials;
the owner-controlled command performs reviewed branch publication and main
promotion using its separate credential. This adds publication friction but
does not depend on unavailable branch protection or a hypothetical fork.
It can be an owner-invoked local command; no always-on broker is required.
Keeping today's shared admin token while claiming exclusive main promotion
is incompatible with the design. Revocation/removal and separation are
activation prerequisites, not actions authorized by this document.

## 5. Recommended state model

Use one immutable transition payload per WP attempt, plus external
attestations and a current pointer. Avoid a second mutable "proposed current"
file. Define these exact subjects:

* `B`: expected current main OID, paired with the externally anchored current
  record digest/sequence and trusted policy digest.
* `S`: clean source commit and Git tree used to build the Candidate.
* `H`: exact feature head being proposed, including final report/test bytes.
* `K`: Candidate ID, identity SHA-256, exact embedded manifest-file SHA-256,
  existing bundle digest, and a supplemental strict bundle inventory digest.
* `P`: canonical proposal digest binding repository, issue/PR, `B`, `S`, `H`,
  `K`, intended journey/scope, full source/product inventory, exact governed
  before/after deltas, gate-plan digest and immutable evidence index.

The proposal is a detached immutable object so `P` may name `H` without
requiring a commit to contain its own hash. Store submitted objects as CI
artifacts with content hashes or in the controller's content-addressed store;
archive accepted objects into the next promotion commit. Mutable upload
locations confer no authority. An amended proposal gets a new digest.

Define the **product closure conservatively**: every tracked path, content,
mode and object type, excluding only an exact list of data-only metadata
paths owned by the trusted policy. This includes all `integra_core` files,
native sources/resources, workers, pins, build/package scripts, test/harness
code, schemas and governance/CI policy code. It deliberately exceeds the
old five-file baseline. Build-input inventories additionally cover external
runtime/model/tool bytes and build environment inputs. Unknown/untracked
inputs fail instead of disappearing from the closure.

Allowed metadata consists of the machine record/current-pointer paths and
immutable content-addressed records under a tightly schema-validated
governance-record directory. No `docs/**`, `state/**`, `tests/**` or filename
suffix exemption. For the existing Recovery source/report split, the owner
bootstrap policy may explicitly admit
`docs/RECOVERY_WP_CURRENT_MAIN.md` as non-executable report content after
confirming it is not a package/build/runtime input. Its exact bytes remain
bound by `H` and the final merge tree. A new exemption requires owner-approved
policy, not a feature-generated allowlist. Metadata parsers use strict keys,
unique normalized relative paths, bounded sizes and no symlink/path escape;
these records cannot load code or change gate policy.

The supplemental bundle inventory closes Candidate v1's specific omissions:
all executable content, paths, file types, executable modes, and symlink
policy are authenticated. Verification starts with no preexisting bytecode
caches, disables bytecode writes for proof execution, and rejects injected
`*.pyc`/`__pycache__` as acceptance inputs. Hashing executable source while
executing an excluded cache is not equivalent. Any permitted transient
runtime files live outside the immutable app. Do not change Candidate v1 or
relabel old manifests merely to add this outer verification envelope.

Derived states are:

```text
CURRENT(n) --submission--> PROPOSED(P, unverified)
           --independent technical proof--> PROPOSED_BASELINE_VALID(P)
           --human decision--> ACCEPTED_PROMOTABLE(P)
           --exact authorized CAS promotion--> CURRENT(n+1)
```

CURRENT(n) remains authoritative throughout. Rejection, withdrawn evidence,
or a superseded proposal never becomes CURRENT; retain its record. A missing
gate may be reported as pending while work continues, but cannot obtain
`PROPOSED_BASELINE_VALID`. Active CURRENT is a view of the accepted chain,
not a developer-editable assertion trusted in isolation.

## 6. CI semantics

Split the technical verdict from the promotion verdict. This removes the
circular requirement to promote before owner handoff, while keeping the
authorization barrier visible.

| Condition | Trusted Quality Gate / artifact | Promotion gate |
|---|---|---|
| Exact CURRENT, allowed ordinary metadata only | PASS, `CURRENT_VALID` after applicable checks | Separate authorization still required for writes |
| Unexplained governed/product drift | FAIL, paths and expected/actual hashes | BLOCKED |
| Missing/invalid proposal or evidence | FAIL or explicit incomplete/pending while running; never technical green | BLOCKED |
| Fully proved proposal, no owner decision | PASS, `PROPOSED_BASELINE_VALID — NOT CURRENT; AWAITING OWNER ACCEPTANCE` | Pending/blocked |
| Accepted proposal, fresh checks satisfied | PASS, `ACCEPTED_PROMOTABLE` | Eligible for the exact transaction only |
| Invalid signature, stale ref/policy, unauthorized main write | FAIL, precise authority/ref error | BLOCKED |

Choose technical green plus the separate promotion gate. Leaving every valid
proposal red obscures actionable defects and recreates the owner-entry
deadlock. Technical green authorizes neither merge nor `USER_ACCEPTED`.
The owner-entry decision additionally verifies the WP's complete technical
gate inventory; a schema/governance-only green is insufficient.

The authoritative validator must execute from the policy revision named in
the last authenticated CURRENT/owner policy receipt. Fetch that exact commit
and pinned dependencies into a separate trusted directory; read `H`/merge
objects as data. Never import modules, run shell hooks or load schemas from
the PR as authority. The current validator imports repository modules, so
copying just that script from base while importing PR modules is unsafe.
Use a small isolated transition checker (standard-library parsing/hashing
plus a pinned signature verifier), or the complete pinned trusted dependency
closure. PR tests run separately without authority keys or promotion tokens.

The owner-controlled command publishes the authoritative check/artifact for
the exact repo/OID/policy/producer; a check with the same display name from a
feature workflow is not accepted. Read ordinary GitHub run IDs as evidence
only when trusted expected workflow bytes and subject are verified. No
privileged `pull_request_target` job may execute untrusted PR code with
secrets. The command independently repeats authorization verification before
writing main; it does not trust GitHub's overall green icon. With effective
credential separation this is enforceable even without required-check UI.

For the local macOS Candidate, a second agent checking locally authored JSON
is not independent verification. The verifier supervisor controls a separate
account/worker sandbox and trusted harness; the product process has no
access to its signing key, controller receipt store or GitHub write token.
The signer is not an API that signs developer-uploaded PASS JSON. Its
supervisor creates the envelope from its own observed trusted-harness run
and provenance checks; only that supervisor can request a technical
signature. Independent exhaustive review may establish a retained build's
provenance, but submitted reports cannot replace independently verified gate
execution. The technical key cannot sign owner acceptance or promotion.
It resolves the clean source, captures build provenance (or exhaustively
verifies a retained build's mapping), executes the mandatory Finder-like
packaged plan and produces immutable logs/result digests. New WP regression
tests may be submitted by the developer, but the independently approved gate
plan and mandatory gate inventory cannot be reduced by the submission.

## 7. Promotion transaction

After explicit human acceptance, the owner-controlled command performs one
bounded transaction. The owner decision signs repository, issue/PR, `P`,
`K`, product closure, acceptance scope/class, expected `B`, policy digest,
technical-attestation digest and a unique transaction ID. It records what
was accepted, not merely "looks good" or a mutable tag name.

1. Read the external current receipt and fetch immutable Git objects. Verify
   main equals `B`, feature head equals accepted `H`, policy and key versions
   are current, proposal/evidence hashes and signatures are valid, every
   required gate passed, and acceptance is not revoked/consumed. Recheck
   retained bundle/runtime identities; missing artifacts block.
2. Prepare a merge commit with parent `B` (and `H` if using a merge commit),
   preserving the accepted feature tree except for the strictly enumerated
   promotion metadata overlay. Do not ask GitHub to compute unspecified
   future merge content. A conflict or an advanced base stops the attempt.
3. The overlay appends the exact proposal, technical attestation and owner
   decision; appends a new immutable current record linking its predecessor;
   updates the current index to that record. Preserve v1 legacy baseline,
   R12/R13, previous current records and rejected evidence byte-for-byte.
   Include exact old/new governed hashes and the accepted subject. No product
   or policy bytes change in a promotion-only overlay.
4. Independently verify the **entire resulting tree**, including additions,
   removals, modes, executable/symlink entries and metadata file contents.
   Require product closure equality with the accepted proposal and exact
   equality to `H` outside the enumerated overlay. Run metadata/schema,
   chain and trusted governance checks on this prepared commit. No broad
   category such as "docs-only" is an acceptable merge-tree exception.
5. The owner-controlled authorization envelope, kept outside the prepared
   commit, binds its final full tree/OID, exact parent `B`, proposal,
   acceptance and overlay digests. This avoids a self-referential commit
   hash. Persist a durable PREPARED receipt before updating the ref.
6. Update `refs/heads/main` from exactly `B` to exactly the prepared commit
   through an expected-old-OID Git ref transaction. A Git push with an
   explicit expected-old lease is suitable only after the controller also
   proves `B` is the parent/ancestor and disallows history rewrites. A
   normal merge endpoint's expected feature HEAD alone does not protect
   against base movement. Never retry against a newly observed base without
   fresh validation and authorization.
7. Read back the remote OID and full tree, then append the externally signed
   PROMOTED receipt and advance its monotonic sequence. If publication fails,
   leave CURRENT unchanged. If the process crashes after ref update, resume
   only the same PREPARED transaction: exact expected remote OID permits
   completion; any other value freezes promotion for investigation. No
   second transaction starts while one is unresolved.

Main is new CURRENT only when its bytes and signed promotion chain agree.
Unauthorized raw main writes are explicit drift, never automatic acceptance.
Under today's shared admin credential such writes cannot be prevented by a
JSON schema; that is why removal of that credential is a rollout gate.
Retain the external latest receipt to detect rollback/replay of an otherwise
valid old signed chain.

The promotion commit does not require rebuilding/retesting the app when the
already tested app is retained unchanged and the exact product closure,
source mapping, external runtime contract and bundle inventory still match.
Run promotion checks, not another expensive product journey or owner retest.
The app truthfully retains its original source commit and Candidate tuple;
the promotion record explains its correspondence to main. Do not edit the
embedded manifest to pretend the app came from the promotion commit.

A different Git commit SHA with identical complete tree does not alter
product bytes, but still needs a fresh exact-ref authorization envelope; it
is not the already authorized transaction. A merge commit with the expected
metadata overlay similarly has a new full tree but identical product closure.
If anyone actually rebuilds, v1 may or may not generate a different ID because
its ID excludes the bundle/build fields. Always treat the new manifest and
bundle tuple as a separate verification subject; do not inherit PASS by ID
alone. An explicit byte-identical/equivalent rule may avoid another human
scenario only when independent technical verification proves its conditions.

## 8. Candidate/evidence separation

| Artifact | Single authoritative responsibility |
|---|---|
| Existing Candidate Manifest | Actual built source, components, runtime/model/tool identities and bundle identity; no user acceptance or permission to promote. Preserve v1 bytes. |
| Proposed-baseline record | Intended delta from authenticated CURRENT, exact `S`/`H`/product closure/`K`, gate plan, evidence index and scope. Developer may submit it; submission is not authority. |
| Technical attestation | Independent producer, trusted harness/policy, provenance/source-to-bundle mapping, strict supplemental inventory, exact evidence digests and complete gate outcomes. |
| Acceptance record | Human decision, scope/class, proposal and technical subject, constraints and expected base. Signed by the owner; no test process can generate it. |
| Current record/index | Accepted transition and predecessor reference; current values are derived from the accepted proposal, not separately editable competing hashes. |
| External transaction receipt | Root/key/policy identity, monotonically advancing accepted chain and exact prepared/published main commit. Detects forged workflow results and rollback. |

Evidence URLs and `/private/tmp` paths are discovery aids. Before admission,
retain digest-addressed artifact bytes and authenticate their producer and
subject. A correct Candidate ID pasted into a PASS report proves nothing
about execution. Reject `SOURCE_UNBOUND`, missing/null manifest/bundle fields,
duplicate or unknown gate names, missing required tests and skipped required
gates. A skip is permissible only where the trusted plan explicitly makes
that check non-mandatory and records why; it cannot satisfy a required gate.
All gate outcomes include actual exit/result, test count/skip accounting,
fixture/input identity, run/stage, relevant environment/runtime identities,
and log/artifact digests. Reports summarize these records; they cannot
override them.

## 9. Recovery #162 worked example

The bounded [#161](https://github.com/Yurielo/integra/issues/161) lifecycle is:

| Step | Concrete Recovery subject and decision |
|---|---|
| Accepted starting product | main `4f20ed5ad76af164a5561e33510b7d36b903eee8`; #156 primary-journey acceptance, with the #159/#160 promotion correspondence preserved. |
| Recovery source | `242e70517bb345e74b84086994639a919daa511a`, tree `7c65fd09d22a90637d9e3f40f6b2d362c74f3f16`. |
| Submitted feature head | `a1f28058822aabe7caebaacd6021b4ce7900ecd3`, tree `39121bc5aa41063d39ff10b21f2dcaf91a3beaa9`. |
| Candidate | `candidate-v1-ae870cf0394a50f620f564af0812b20ec0ae610bf0a6503d76ef2233ba165c8c`; bundle `de6c6186918ba084fd74d5146313e9d235e0f7801cdff27f664495bba00a50d1`. Whole manifest and supplemental inventory digests must be independently captured; they are not inferred here. |
| Technical proof | Authenticated complete #161 Recovery and primary-journey gate inventory under Finder-like conditions, on the exact tuple. Current report is submitted evidence, not yet this attestation. |
| Proposed validation | With trusted mechanism installed and the prerequisites met: `PROPOSED_BASELINE_VALID`, CURRENT unchanged, owner acceptance pending. |
| Owner acceptance | Future explicit human acceptance of Recovery failure/cancel/interruption/retry semantics on that exact proposed Candidate. #156 does not grant it. |
| Promotion | Owner-authorized exact metadata overlay and compare-and-swap transaction; new main CURRENT links back to prior CURRENT and retains #156 scope/history. |

Git comparison shows that the source-to-feature-head difference is the added
`docs/RECOVERY_WP_CURRENT_MAIN.md` only. Relative to starting main, the
feature changes `integra_core/shutdown_runtime.py`, `macos/Resources/bridge.py`,
adds `tests/test_recovery_contract.py`, and adds that report. This is useful
correspondence evidence, not proof that every packaged byte came from source.
The independent verifier still checks the full closure and actual package.

Today #162 stays `BLOCKED` and its existing failure remains honestly red.
Do not rename the current failed run green. After implementation and verified
bootstrap, a new trusted run can replace the inappropriate CURRENT-only
interpretation with the proposed-state verdict. The three historical/current
drift diagnostics become an explained proposed delta only after all proposal
checks pass; arbitrary drift remains an error.

Do not claim owner-entry readiness solely from #162's report. Its full-suite
line reports 646 run, 641 pass, 73 skipped, two errors and three failures,
which cannot be a consistent count if skips are part of tests run. Some
reported reuse/invalidation tests were skipped in the recorded execution.
The next technical step is to reconcile actual results against the mandatory
gate inventory and independently verify the necessary evidence, not to ask
the owner to discover whether required technical cases passed. This is an
evidence-admission issue, not authorization for a new product audit or repair
in #163.

Existing Recovery Candidate bytes need not be rebuilt just because
promotion metadata changes. Retain them if the verifier
can establish trustworthy clean provenance, complete source-to-package
correspondence, cache/mode integrity and all required technical gates on that
exact app. Current developer-authored reports alone cannot do this. If the
app/artifacts are unavailable, provenance cannot be established, or required
gates remain unproved, a fresh independent build/revalidation is necessary
and a new tuple/proposal is required before owner entry. This is a real
possible cost, not an unconditional promise to reuse the old Candidate.

Bootstrap advances main beyond `4f20...`; before resuming #162, compute its
exact merge with that new base. Because this design conservatively includes
governance code in the product closure, an in-repository checker/policy-code
bootstrap normally changes that closure and requires a fresh Candidate and
independent technical revalidation for the resulting Recovery head. Do not
claim byte equivalence merely because that policy code is not packaged.
Retaining the existing Candidate is conditional on the exact closure rule
actually holding; no undocumented policy-code exemption is implied. A mere
clean textual rebase is insufficient. The owner decision
names the new expected base and final proposed head. Once that decision has
been obtained, a verified promotion-only metadata commit requires neither a
new Recovery owner retest nor repetition of #156 primary acceptance. Any
later runtime or visible semantic change returns to the proposal/technical
gate process and gets the appropriate new acceptance.

## 10. Alternatives and resource tradeoffs

| Dimension | A: feature directly updates CURRENT | B: manual promotion Issue after each WP | C: explicit proposed state and exact promotion |
|---|---|---|---|
| Safety | Unsafe with ordinary developer authority; coordinated hash/validator edits self-certify. Adding real separate authority effectively becomes C. | Can be safe when independent review/authority are real; an extra Issue alone supplies neither. | Defined independent attestation and human authority; safe only after trust separation is activated. |
| Context/token cost | Low apparent cost, repeated drift diagnosis and hidden acceptance ambiguity. | Repeated discovery, diff classification and handoffs per WP. | One bootstrap/design cost, thereafter one generated delta and compact evidence/decision record per attempt. |
| CI complexity | Small initially; recurring hard-coded exceptions. | Existing checks plus manual reconciliation; operator-specific consistency risk. | Small separate trusted transition checker and explicit technical/promotion verdicts; keys/receipts are additional operations. |
| Owner burden | Hidden acceptance or accidental delegation. | Often both governance repair review and coherent product acceptance. | One coherent product decision plus exact promotion authorization; metadata-only proof avoids app retest. Credential-safe branch publication adds real friction without branch restrictions. |
| Rebuild cost | Temptation to reuse stale evidence. | Frequently rebuilt to rediscover correspondence. | Retained identical app avoids promotion rebuild; independent macOS provenance/gates may initially require reruns or a fresh build for #162. |
| Identity drift | High: mutable current hashes and reports. | Reduced by careful manual full-tree audit, but easy to omit a late delta. | Full proposal/manifest/bundle/closure binding and ref CAS; explicit failure on stale base or changed bytes. |
| Implementation cost | Lowest only if self-certification is tolerated. | Low automation cost, recurring labor. | Moderate bounded bootstrap: schemas, isolated checker, signed evidence/decisions, owner command and adversarial tests. No release/distribution framework. |

Choose C. Independent macOS execution and owner-key isolation are material
costs, not free consequences of a JSON schema. They address the original
false-positive/self-certification problem. B remains the conservative
operational fallback until C is installed, with no claim that another Issue
number itself fixes authority. C cannot honestly promise no owner involvement
in every product change; it removes repeated governance rediscovery and
promotion-only product retests.

## 11. Minimal implementation plan

One bounded governance implementation WP can deliver the following; none is
implemented by this design document.

1. Add strict proposal/technical-attestation/acceptance/current-transition
   schemas, a policy record with exact metadata paths and required gate IDs,
   and a content-addressed `state/governance_records/` archive. Keep the v1
   baseline and historical schemas/records intact. Introduce a small current
   index for the accepted record; do not use feature edits of the old file
   as promotion. Store signed payloads with explicit domain/version/repo and
   verify exact canonical bytes using a pinned standard signature tool.
2. Add an isolated `scripts/validate_baseline_transition.py` and owner-invoked
   `scripts/promote_baseline.py`, loaded from the authenticated policy
   revision. The former reads trees as data, verifies exact inventories,
   signatures/evidence and current/proposed context. The latter prepares the
   bounded overlay, validates whole-tree equality and performs durable
   receipt/ref transaction handling. Keys and promotion credentials live
   outside repo/developer execution; paths/names here are proposed files.
3. Adapt the current/historical portion of `scripts/validate_governance.py`
   to consume a verified transition context. Preserve legacy/R12/R13 schema
   and content checks. Explain superseded file hashes using the validated
   accepted/proposed chain; do not pass an arbitrary developer JSON object
   directly to a drift-suppression helper. Feature-local validation remains
   diagnostic; the trusted command repeats authorization checks independently.
4. Add a small outer technical envelope around Candidate v1/evidence v1.
   Require full manifest digest, strict bundle inventory and verified source
   mapping without modifying the app just to carry acceptance data. Define
   the independent macOS supervisor/harness recipe and protected signing
   boundary, complete gate inventory, cache rules and retained artifact store.
5. Update CI integration to show the two verdicts and exact subject/policy.
   Keep untrusted product tests isolated from keys. Trusted checker tests must
   execute the pinned policy, even when the feature changes those tests.
   Resolve the existing positive baseline tests so proposed context is
   explicit, while preserving drift/missing-record negative cases.
6. Add focused adversarial tests from section 12. Test source/proposal/policy
   manipulation, mandatory skips, forged attestations, full merge content,
   signatures/key purpose, history tamper and concurrency/recovery. These
   test the trust boundary, not just matching hashes generated by one helper.
7. Bootstrap under section 13, demonstrate effective credential separation,
   then resume #162 with a final exact merge proposal and independent
   technical evidence. No separate governance-repair Issue is needed after
   each future normal product WP; it uses this existing mechanism.

No package signing, notarization, distribution service, roadmap rewrite,
general release train or changes to Recovery implementation are required by
this implementation plan. If the bounded trust prerequisites cannot be met,
do not partially deploy a green-proposal exception.

## 12. Adversarial self-review

These are required implementation acceptance cases, not tests claimed to
have run in this design-only issue.

| Concrete attempted defeat | Expected result and reason |
|---|---|
| Change bridge, proposal hash, baseline JSON, validator and test expectations together; make the PR workflow print PASS. | FAIL. External checker runs previous authorized policy; old CURRENT cannot be edited; no independent attestation or owner signature exists for the new subject. |
| Submit original Candidate ID with a modified bundle and recompute its v1 bundle digest. | FAIL. Whole manifest digest and strict bundle inventory differ from the independently signed `K`, although v1 Candidate ID may be unchanged. |
| Supply clean-looking manifest but copy an untracked shutdown module or an injected `.pyc` into the app. | FAIL. Trusted source mapping, clean input inventory and no-cache verification reject it. A supplied dirty=false field is not trusted provenance. |
| Flip executable mode, replace a file with a symlink, or introduce a new worker not in the five baseline paths. | FAIL. Whole product tree and supplemental bundle inventory cover modes/types/new paths; symlink escape is rejected. |
| Copy yesterday's PASS JSON, set its Candidate ID to Recovery, omit the skipped reuse test and sign it with a developer key. | FAIL. Required inventory, immutable log digests, independent producer key purpose and complete `P`/`K` bindings fail. |
| Agent posts "USER_ACCEPTED" through the owner's GitHub admin token, or puts that field in a proposal. | FAIL. No human-key signature over the exact acceptance subject. Today's admin token can still write raw main until revoked, so activation must remain blocked while it is available. |
| Move a `recovery-approved` tag or replace an uploaded evidence object after acceptance. | FAIL on digest/OID mismatch; names are never authority. If the exact old object remains retrievable and authenticated, only that old object is used. |
| Sneak a source change into `state/` or `.github/`, calling it metadata, or broaden the allowlist in the feature. | FAIL. Exact trusted metadata paths/schema apply; policy/test/build changes remain in product closure and cannot self-authorize. |
| Accept H, then push H2 with a new bridge, or resolve a merge conflict into different shutdown code. | FAIL before promotion. Expected H and complete merge tree mismatch; even unrelated late changes need a newly bound exact proposal/authorization. |
| Two authorized transactions read the same B and both try to promote. | Only one expected-old-OID ref update succeeds. Other transaction cannot reuse acceptance against the advanced base. Durable transaction IDs prevent replay. |
| Controller crashes after Git update but before receipt finalization. | No automatic next promotion. Resume only its stored PREPARED transaction and exact published OID; otherwise fail closed for reconciliation. |
| Restore old signed CURRENT files and old main to make a rollback appear valid. | FAIL against external latest sequence/receipt. Valid old signatures are historical, not authorization to roll back. |
| Modify R12/R13 and their new references together, or erase a rejected Candidate. | FAIL against anchored historical digests and append-only archive, even if current in-tree JSON is internally consistent. |
| Malicious candidate writes fabricated successful logs and steals signer credentials. | Worker lacks key/store/token access; supervisor observes process results and validates outputs against its trusted gate plan before signing. A key placed in that worker violates activation requirements and must fail the isolation test. |

The design addresses these attempts with explicit enforceable boundaries.
It does not claim tests prove arbitrary code benign; code review and the
defined evidence ladder still determine technical sufficiency. It also does
not claim cryptography can distinguish the owner from an agent that has the
owner's private key. Such shared access is forbidden, measurable in rollout,
and an activation blocker. There is no remaining material bypass *within the
stated separated trust model*; the current repository has not established
that model.

## 13. Migration/rollout

Bootstrap is an explicit owner policy decision, never a feature PR silently
updating its own expected hashes. Freeze the reference main OID, capture its
entire tree and the exact legacy baseline, R12/R13 and retained rejected
records. Preserve those bytes as historical authority. Record the distinct
#156 accepted Candidate/journey and #159/#160 correspondence, including
which historical technical claims are grandfathered rather than newly
attested. Do not manufacture independent signatures for past test execution.

The human owner creates an external genesis receipt binding reference main,
the reviewed bootstrap policy/checker digests, owner/verifier key identities,
legacy record digests and accepted journey scope. Public keys in a PR are
not sufficient: the owner-installed external root authenticates them. A
later key/policy rotation requires the old trusted owner root and an explicit
new policy digest/epoch; an unavailable old root requires an explicit owner
rebootstrap with recorded discontinuity, not silent fallback to repo keys.

Install the owner command and independent verifier under accounts unavailable
to developer/candidate execution. Remove the broad developer GitHub token
and establish the read-only/publisher separation from section 4. Verify an
ordinary development session cannot access owner/verifier keys, invoke an
unrestricted signer, update main, rotate policy or mint authoritative checks.
No existing GitHub branch rule is assumed to supply this boundary. Where
such isolation cannot be established, rollout stops; retaining the current
red gate is safer than shipping an untrusted proposal exception.

Run the isolated adversarial fixtures for the new checker and promotion
transaction in a controlled non-production test repository/store. Verify
both valid-proposal/no-acceptance blocking and exactly authorized promotion,
including concurrent updates and crash recovery. Review the bootstrap diff
under the external owner root because the new checker cannot validate its
own introduction as the original authority. Only then publish/activate the
new policy and index in one owner-authorized bootstrap transaction. An
unconfigured/missing root always means FAIL, never legacy permissive mode.

The active record must reconcile both the original accepted product and any
new governance-policy bytes; do not claim those policy bytes were tested in
the historical app. Keep policy authority and historical app acceptance
separate, with explicit closure correspondence. After bootstrap, recompute
#162's proposed merge and technical evidence requirements against the new
base. Missing durable Recovery evidence or mandatory skipped checks remain
technical blockers; they cannot be grandfathered into a new Recovery PASS.

This review verified repository code/schema/test behavior and the failed
GitHub log by inspection. It did not activate keys, change permissions,
verify an isolated runner, authenticate the retained local package, execute
new tests, or perform migration. Those are explicit implementation/rollout
prerequisites, not hidden claims of present readiness.

## 14. Final recommendation

`GOVERNANCE_DESIGN_READY`

Approve the design for a bounded implementation and owner-reviewed bootstrap.
Use technically green, explicitly non-current proposals; require independent
macOS technical attestation, human-only product acceptance and an exact
owner-authorized promotion transaction. Preserve legacy baseline and
R12/R13/rejected records. Do not rewrite historical hashes to make Recovery
pass, and do not mistake technical green for permission to merge.

This is design readiness only. Activation and #162 owner entry remain blocked
until credential/key isolation, trusted policy execution, durable evidence,
complete mandatory gates and migration correspondence are demonstrated. If
the owner chooses to retain shared administrator/signing authority with the
developer, this mechanism cannot be honestly activated as fail-closed.
Stop here for owner review; no owner retest is requested by #163.
