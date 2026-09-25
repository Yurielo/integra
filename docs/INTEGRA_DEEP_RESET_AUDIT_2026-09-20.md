# Integra deep reset audit: product reality and completion control

Issue: #150. Audit date: 2026-09-25. Status: `OWNER_REVIEW_REQUIRED`.

This is a read-only audit of the canonical repository state and recorded
evidence. It changes no product behavior, pins, roadmap state, Candidate or
owner-acceptance record.

## 1. Executive diagnosis

Integra has not been slow because it needs to recreate the algorithms of
SeminarText, VideoText and BookText. The source-capability inventory shows that
many required algorithms already exist. The cost has come from turning those
algorithms into one ordinary macOS workflow: source selection, runtime
availability, process ownership, saved results, recovery, a usable result
surface, and truthful proof that the packaged GUI takes the same path.

That work is real, but the project has made it costlier than necessary. Product
scope, domain boundaries, Candidate identity and technical readiness have often
been established in different artifacts at different times. This allowed a
local technical PASS to look more complete than the user-visible journey it
actually proved. Owner reports in #144, #146 and #148 then exposed GUI/runtime
problems that the preceding gates did not cover.

The immediate product truth is narrower than `READY_APP_V1`: the Process v1
Board records a substantial proven local-media slice, but Process v1 is not
accepted and the full Product Definition still includes Knowledge, publication
and other later outcomes. No document supports calling Integra a fully working
macOS application today.

## 2. Exact baselines and identity boundaries

| Surface | Identity | Meaning |
| --- | --- | --- |
| Canonical repository main | `745a95d01c59d1b1b66c52c7a764f8ef3760620c` | Current repository baseline audited here. |
| Active CURRENT v2 record | `current-v2-65bf72d1262146c9137aca433b51ae3974d98bc4c8ed37042db13b46e0318a1d` | Governed promotion register; its scope is not whole-product acceptance. |
| Latest scoped Topic-review Candidate | `candidate-v1-65bf72d1262146c9137aca433b51ae3974d98bc4c8ed37042db13b46e0318a1d` | Owner accepted only the Topic Review save/reopen outcome. |
| Historical MCWMA Candidate | `candidate-v1-c5851d168b116fed83109014519ebc01c0291e23705ac9d2ec0a4e5df2471960` | Owner-accepted local Russian-video journey in #156; not evidence for every current-main capability. |
| Pending lifecycle PR | #183, draft | Separate technical proposal; it is not in `main` and cannot improve the audited main product state until reviewed and merged. |

Evidence must never cross these boundaries merely because a Candidate has a
similar bundle digest or because a historical report was accepted for a narrower
scope.

## 3. Product goal and minimum working-app contract

The higher authority, `PRODUCT_DEFINITION.md`, defines `READY_APP_V1` as a
source-to-traceable-knowledge/media/publication macOS application. The staged
architecture defines a deliberate sequence: `PROCESS → KNOWLEDGE → STUDIO`.
The frozen Process v1 DoD is the authority for its first phase only.

The minimum correctly working Process application is therefore:

`Finder launch → select supported local media → select available outputs → execute pinned ASR path → readable transcript/clean text/selected outputs → saved truthful result → close/reopen → controlled failure/cancel/timeout/retry without corruption.`

This is a meaningful product milestone, but it is not `READY_APP_V1` and it is
not a substitute for the later Knowledge and Studio domains.

## 4. Plan-versus-reality matrix

| Capability area | Main implementation | Packaged proof | Owner acceptance | Current status | Action |
| --- | --- | --- | --- | --- | --- |
| Native shell, local media, transcript/SRT | Present | Bounded primary and Process evidence | Bounded local-video acceptance | `WORKING_NOT_USER_ACCEPTED` for whole Process | Keep; use as the canonical regression journey. |
| Word Timeline and basic Topics/timestamps | Present | P156 / Process evidence | P156 bounded scope | `WORKING_NOT_USER_ACCEPTED` beyond accepted journey | Keep; do not equate with Knowledge acceptance. |
| Process Topic Review save/reopen | Present | Candidate-bound proof | Explicit scoped owner evidence | `WORKING_ACCEPTED` for this row | Keep isolated from Knowledge/Evidence. |
| Recovery lifecycle | Present | Candidate-bound controlled evidence | No whole-Process acceptance | `WORKING_NOT_USER_ACCEPTED` | Retain regression ledger; prove again only when relevant bytes change. |
| Several local inputs and one YouTube video | Present | Candidate-bound Process proof | No complete Process acceptance | `WORKING_NOT_USER_ACCEPTED` | Keep existing paths; do not reimplement. |
| Folder, Zoom and playlist discovery | Partial/source capability exists | No current packaged proof | None | `NOT_IMPLEMENTED` as Process UI outcomes | Integrate only after selecting a coherent discovery journey. |
| Translation, language/settings/diagnostics, Topic summary/detail | Source implementations or partial workers exist | No frozen Process packaged proof | None | `IMPLEMENTED_NOT_PROVEN` or `PARTIAL` | Treat as integration work, not source-algorithm work. |
| Combined transcript/provenance/corpus | SeminarText capability exists | No Integra path | None | `NOT_IMPLEMENTED` | Integrate as one multi-source result journey. |
| Selected-Capability Runtime Closure | Broad availability/build closure exists | No selected-output closure proof | None | `BLOCKED` | Bounded architecture repair; it is a prerequisite only where it blocks selected Process outputs. |
| BookText / Process Documents | Pinned source capability exists | Historical/component evidence only | No Process owner selection | `DEFERRED` | Keep out of Process v1 pending a separate owner decision. |
| Knowledge, Evidence, publication and Studio | Historical implementations and contracts exist | Mixed historical/technical evidence | No current whole-domain acceptance | `PARTIAL` | Preserve; do not call them completed or pull them into Process. |

The Process Board contains 45 rows for 47 MUST requirements because
Selected-Capability Runtime Closure aggregates three owner requirements. Its
recorded state is `28 DONE / 0 IN_PROGRESS / 16 NOT_DONE / 1 BLOCKED`. These
are Process-row states, not a percentage of full Integra completion.

## 5. Why prior technical readiness was unsatisfactory

| Owner failure | Earlier claim | What owner evidence disproved | Root cause | Preventive control |
| --- | --- | --- | --- | --- |
| #140 / #142 | Candidate packaging was ready to assess | Word Alignment source could not be copied/imported reliably | Runtime input and packaging evidence were incomplete | Candidate must bind the exact runtime actually packaged; production import is a required packaged gate. |
| #144 | Candidate GUI was ready | Finder-launched GUI could not resolve `ollama` | Shell PATH differed from GUI environment | Packaged executable resolution must be asserted from the GUI-equivalent launch contract. |
| #146 | ASR was available after Ollama repair | GUI disabled transcript/SRT because pinned bytes differed | Packaged runtime identity differed from governed expectation | Candidate manifest and preflight must compare the actual bundled bytes before handoff. |
| #148/#149 | Initial primary E2E phase passed | Owner found Word Timeline failure in real flow | Synthetic/short fixture and incomplete observability did not exercise failure class | Realistic packaged fixture and known-failure regression are required before owner handoff. |
| Topic Review reopen | Save was reported successful | Reopen showed machine Topic instead of reviewed title | Save and read/materialization paths were tested separately | Test `save → close → reopen` as one Process journey with persisted receipt. |
| #181 | Candidate verification completed | Development runs retained multi-GiB temp bundles and orphan processes | No single lifecycle owner for disposable build roots | Marker-owned root, process group, timeout, cleanup and conservative stale reaper; PR #183 supplies this pending-main work. |

The systemic error was treating a lower evidence level as evidence of a higher
one. A unit test proves a rule; component smoke proves a boundary; a packaged
run proves a specific Candidate; owner acceptance proves usability of that
Candidate and scope. None proves the next level automatically.

## 6. Architecture and runtime findings

1. **The source products are assets, not drop-in macOS subsystems.** They own
   ASR, media and OCR behavior. Integra must own selection, process lifecycle,
   project persistence and user-visible result semantics. Reimplementing source
   algorithms in Integra would be waste; thin, pinned adapters are appropriate.

2. **The broad runtime closure is a real cost center.** Static architecture
   evidence records that the current build/preflight packages and probes
   SeminarText, VideoText, BookText, Word Alignment and review dependencies as
   a broad bundle. This makes a small UI or Process change pay for unrelated
   runtimes. It does not justify weakening byte validation. A future bounded
   change must either prove a selected capability closure or prove safe reuse of
   immutable, hash-verified build inputs.

3. **The result boundary is still too mutable.** The DoD identifies
   ProcessedSource v1 as a needed immutable projection over existing artifacts.
   It should be a thin seal/reader over current storage, not a new database or
   a rewrite of SeminarText, VideoText or BookText.

4. **Historical governance is being asked to carry current product truth.**
   Historical R12/R13 and source evidence must remain immutable. Current product
   claims require an exact current Candidate, a stated scope and a separate
   owner decision. Proposal Lite addresses that distinction, but its use must
   not become a reason to rebuild a Candidate for documentation-only evidence.

## 7. Required evidence ladder

| Level | Proves | Does not prove |
| --- | --- | --- |
| UNIT | Local rule | Integration or packaging |
| COMPONENT | One adapter/runtime contract | GUI selection or user journey |
| INTEGRATION | Production orchestration path | Packaged execution identity |
| PACKAGED_E2E_DETERMINISTIC | Exact Candidate on controlled fixture | Natural-media robustness or usability |
| PACKAGED_E2E_REALISTIC | Exact Candidate on representative permitted media | Human usefulness or UX judgement |
| KNOWN_FAILURE_REGRESSION | A reported failure class remains fixed | Other failure classes |
| USER_ACCEPTANCE | The owner accepts the stated scope/Candidate | Any broader scope or later Candidate |

Every result above component level must name Candidate ID, source commit/tree,
component/runtime identity and fixture class. A skipped test is not a PASS.

## 8. Product-state control and accountability

Each user-visible capability needs a record with these states:

`PLANNED → IMPLEMENTED → INTEGRATED → PACKAGED_E2E_PROVEN → USER_ACCEPTED`.

The Process Board can remain its phase-specific outcome view, but it must link
each `DONE` row to one maturity record and exact evidence. Issue closure and
roadmap `ACCEPTED` must remain planning/governance states; neither may raise a
capability's maturity. Candidate manifests supply build identity. Only the
Product Owner writes `USER_ACCEPTED`.

| Gate | Implement | Verify technical evidence | Authorize handoff | Declare user acceptance |
| --- | --- | --- | --- | --- |
| Unit/component/integration | Assigned developer | QA/CI | Technical lead | Never automated |
| Packaged E2E | Assigned developer | QA on exact Candidate | Product owner or delegated release authority | Product Owner only |
| Scope usability | — | Evidence is supplied to owner | Product owner schedules handoff | Product Owner only |

## 9. Completion control and immediate sequence

The project should use one canonical journey at a time. A repair must name the
journey gate it restores. A non-essential feature cannot begin while that
journey is red. Candidate handoff occurs only after the required evidence
ladder is green for the same bytes.

The recommended sequence is:

1. **Merge-safe lifecycle hygiene (#181).** Finish review of PR #183, then
   merge only after normal repository authority. It removes a development-cost
   leak; it does not advance Product Board rows.
2. **Select one Process integration journey from the 16 NOT_DONE rows.** Use
   the Board's existing dependency rules. Do not batch folder, playlist,
   translation, Topics and corpus into one tranche. The first selected journey
   must declare its selected runtime closure and exact acceptance evidence.
3. **Prove the journey on one Candidate before owner handoff.** Run deterministic
   and realistic packaged E2E plus affected recovery checks, then offer one
   coherent owner test. Update the Board only from that evidence.

No work should begin yet on BookText/Process Documents, Knowledge, Studio,
publication, broad architecture rewrites, source-product replacement or public
distribution.

## 10. Capability, Issue and roadmap reconciliation

| Area | Reality on audited main | Classification |
| --- | --- | --- |
| SeminarText local ASR / clean text / SRT | Pinned production route is connected; bounded Process evidence exists | `KEEP_NOW` |
| Word Timeline / basic Topics | Bounded accepted journey exists; not full Knowledge semantics | `KEEP_NOW` |
| VideoText translation and media derivatives | Source capability/worker paths exist, but the frozen Process controls and outputs are not all connected | `PROVE_NOW` / `IMPLEMENT_NOW` only when selected by Board |
| BookText OCR and documents | Source and historical integration evidence exist; owner left Process Documents scope unselected | `DEFER` |
| Knowledge / Evidence / publication | Historical contracts and code exist; full current user journey is not proven | `DEFER` from Process; retain as later product work |
| Native lifecycle and recovery | Strong bounded proof exists; it remains a shared regression requirement | `KEEP_NOW` |
| Runtime closure | Broad package/probe behavior conflicts with selected-output Process goal | `REPAIR_NOW` only when it blocks the selected next journey |

| GitHub item | Truthful classification |
| --- | --- |
| #129 source-capability audit | `OPEN_HISTORICAL`: its inventory remains useful, but it does not prove current packaged parity. |
| #138–#149 | `OPEN_HISTORICAL`: they document runtime/owner-gate failures and their bounded fixes; their branches must not be treated as current product truth. |
| #156 | `TRUE_COMPLETE` for the stated local Russian-video MCWMA acceptance only. |
| #165 | `TRUE_COMPLETE` for Proposed Baseline Lite, not a product feature. |
| #169 | `TRUE_COMPLETE` for proof-first Process/recovery closure; it does not accept full Process. |
| #170–#179 merged Process work | `TRUE_COMPLETE` only at their named Board/evidence scope. |
| #181 / PR #183 | `OPEN_ACTIVE`: lifecycle hygiene is technically proposed and must be reviewed/merged before it becomes main behavior. |
| Older open draft PRs #141/#143/#145/#149/#152/#162/#178 | `OPEN_HISTORICAL` or `SUPERSEDED` candidates for explicit owner triage; no one is a current delivery line merely by remaining open. |

`state/integra_state_v1.json` still presents a delivery target whose chain uses
historical `ACCEPTED` terms. Those terms are not equivalent to capability
`USER_ACCEPTED`. The state should not be rewritten in this audit. A later
governed migration should add capability maturity links rather than changing
historical rows retroactively.

## 11. Preventive-control table

| Failure mode | Root cause | Preventive control | Automated enforcement | Evidence | Rollout |
| --- | --- | --- | --- | --- | --- |
| Technical PASS presented as readiness | Evidence level was unstated | Capability maturity record | Validator rejects missing level/identity | Candidate-bound gate ledger | Before next owner handoff |
| Component smoke used as E2E | Fixtures did not traverse GUI-equivalent path | Mandatory packaged deterministic + realistic gates | Gate ledger requires both | Exact Candidate IDs and fixture references | Next selected Process journey |
| Shell/GUI divergence | PATH/interpreter resolution was implicit | Packaged runtime-resolution contract | Native preflight verifies the packaged executable | GUI-equivalent preflight result | Shared runtime-closure work |
| Runtime/pin drift | Build input and bundled bytes were not compared early enough | Immutable Candidate Manifest | Build and preflight validate actual bundle bytes | Manifest/bundle hashes | Existing contract; keep strict |
| Owner discovers integration failures | Handoff happened after a partial gate | Owner Entry Gate | Handoff blocked until evidence ladder is complete | One scoped Candidate dossier | Next owner milestone |
| Stacked evidence drift | Candidate, source and proposal had separate moving heads | A→B→C proposal discipline and short product branches | Proposal material validation | Source/tree, overlay and declaration IDs | Existing Proposal Lite; simplify use |
| Hanging external processes | No single lifecycle owner | Marker-owned scratch root and process group | Lifecycle tests plus timeout proof | Root marker/cleanup receipt | #181 after merge |

## 12. Branch and Candidate strategy

Use a short branch for one coherent journey. Keep source A immutable once its
Candidate is built. Evidence overlay B may contain only reports/manifests; the
proposal declaration C may contain only the proposal. A documentation correction
must not cause a Candidate rebuild if it changes no product/runtime byte. Before
any owner handoff, publish exactly one local app path and Candidate ID. When a
journey is accepted and promoted, merge it before selecting the next journey.

This is a simplification of the current practice, not a new governance system.
It uses Proposal Lite's existing distinction between CURRENT and PROPOSED and
removes the need to infer readiness from stacked branch names.

## 13. Runtime, package and UX limits

The repository records a 16-GB reference-machine resource model and broad
runtime packaging, but this audit has no current exact-bundle composition,
idle-memory or processing-memory measurement. The observed approximately
2.2-GiB Candidate footprint must be measured on one exact Candidate before
changing copy/cache mechanics. Until then, lifecycle cleanup is the justified
control; a runtime-cache redesign is only a hypothesis.

The visible Process UX has scoped owner evidence for result cards, ordinary-file
export, source navigation and Topic Review. It does not prove the remaining
translation, discovery, playlist, corpus or selected-runtime-closure UX.

## 14. Unknowns and limits

This audit did not launch GUI/Finder, rebuild a Candidate, modify state, or
re-run source-product workloads. It does not claim that a historical Candidate
is currently runnable. It does not measure the current bundle's 2.2-GiB
composition, idle memory or processing memory; those require a separately
defined exact Candidate and controlled measurement plan. The observed
temporary-build footprint is addressed by #181 but remains pending merge.

The Product Owner must resolve one planning ambiguity before a whole-product
completion claim is possible: whether `READY_APP_V1` remains the Product
Definition's full Knowledge/Publication chain, or whether it will be explicitly
rebaselined to staged Process acceptance first. The existing staged architecture
allows Process as Phase 1, but it does not silently replace the higher-level
definition.
