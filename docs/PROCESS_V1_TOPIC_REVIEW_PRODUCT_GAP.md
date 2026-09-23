# Process v1: Topic edit/confirm product-gap evidence

Status: `TOPIC_REVIEW_PRODUCT_GAP`. This report records a bounded
`VERIFY_EXISTING` result for the frozen **Topic edit/confirm** Board row. It
does not change product code, `CURRENT`, component pins, Process scope, or any
Board state, and it does not contain a human review decision.

## Canonical state and reused Candidate

| Binding | Exact value |
| --- | --- |
| Canonical `main` after protective-retry evidence merge | `23b09210d4e6b5e0ff5948dee6e3fa3c421f0d01` |
| CURRENT baseline | `current-v2-f7f0fd92b37ce8e8b172a6cfedba5c2b98d968f201de0f10c9cff06c61673777` |
| Reused Candidate | `candidate-v1-f7f0fd92b37ce8e8b172a6cfedba5c2b98d968f201de0f10c9cff06c61673777` |
| Candidate app | `/private/tmp/integra-pr174-owner-final.vpWEu6/Integra.app` |
| Candidate source / tree | `2eade0c58d5e162bdbb36442c6874a6c21b03967` / `b112309d14fb65de1a6eece0a34c79b0b658b9e6` |
| Candidate manifest SHA-256 | `55c96ecde3e8f53bfb648a81dc0ef12abb586b35dbd3037b5c15530508e251d0` |

The difference from Candidate source to canonical main contains no
`macos/` or `integra_core/` path. The Candidate was not rebuilt.

## Real packaged preparation — no human decision applied

The exact bundled app was run once through its packaged production bridge with
an isolated app-data root and a pre-existing deterministic Russian-video
fixture. The selected real outputs were `transcript`, `word_timeline`, and
`topics`; no mock worker, edited result JSON, or fabricated review decision was
used.

| Item | Exact value |
| --- | --- |
| Source SHA-256 | `db0cbfd61a3861442114d27633d0b8115af792f6532674298886d86fd57cf3e4` |
| Project / run / source | `urn:integra:project:94a049d1-58e1-4684-98f0-fd2f8e3d8542` / `urn:integra:run:e20354fd-dbdc-46bf-8fd7-9dc199ea0961` / `urn:integra:source:f8f2239a-599c-5f4a-98de-ae7f60436efa` |
| Persisted run SHA-256 | `1e142b52577df968b76a5e0439db596a3bbda693151753a392fcc004e1da4d42` |
| Topics SHA-256 | `81aa628a738240bc3d7c51b84c8b8cae0859d9aaf9466fef3c7218d4f0ee7953` |
| Canonical Evidence SHA-256 | `ad74a5012374ea35e06cf71e7773e142b360deed8d6834ad64db0c472edd15e6` |
| Machine-Evidence result SHA-256 | `c05f1f6b5dcebb61e9c462449d5ea9ad404efa1f31f592f33e2fbe0c64071adb` |
| Prepared review package SHA-256 | `89d1b037758cd8e71d12f64c619dee79edf023cb05c10ec2a43be12d7505db5e` |

The run completed. `create-machine-evidence` truthfully returned
`EVIDENCE_CREATED`, `MACHINE_EVIDENCE_UNVERIFIED`, `machine_unverified`, and
`reviewer_id: null`. It created no human review or accepted Knowledge.

`prepare-knowledge-review` then returned a real package with
`status: REVIEW_REQUIRED`, `automatic_acceptance: false`, and
`review_mode: EXACT_FRAGMENTS_V2`. It contains one generated Topic, including
its displayed title, summary, quote, and `0.080–5.728 s` source interval. No
call to `apply-knowledge-review` was made.

Thus the persisted pre-review authority is correctly pending/unreviewed. The
required human action is technically representable by the bridge and dialog
code, but it is not reachable through normal Process UI.

## Exact GUI reachability failure

`macos/IntegraApp.swift` has the implementation methods:

- `createMachineEvidence` at lines 1037–1048;
- `prepareTopicReview` at lines 1069–1093, which calls
  `prepare-knowledge-review` and then `presentTopicReview`;
- `presentTopicReview` at lines 1094–1160, containing real
  accept/reject controls, reviewer identification, exact-boundary
  acknowledgement, and `apply-knowledge-review` persistence.

But no normal Process result control reaches either preparation method:

1. `renderResultRows` (lines 919–936) renders primary cards, source navigation,
   and technical data only.
2. `renderPrimaryProcessResults` (lines 938–979) deliberately treats `topics`
   JSON as technical data unless a `topics_txt` or `topics_markdown` artifact
   exists.
3. `renderTechnicalData` (lines 1006–1022) creates only
   `Открыть технические данные: …` controls. It never creates a machine-evidence
   or topic-review action.
4. A source-wide selector search found zero call sites for
   `#selector(prepareTopicReview`, `#selector(createMachineEvidence`, and
   `#selector(buildReviewedPackage`); each name appears only as its dormant
   method declaration.

The compiled Candidate binary retains the bridge operation strings, so this is
not an absent runtime. It is a missing user-visible wiring from the normal
Process result surface to the existing preparation/review controls.

## Disposition

The Product Owner cannot perform the required normal-GUI edit/confirm action
for the real prepared package without a Terminal/bridge/developer path. Asking
the owner to call bridge operations or supplying a synthetic `ACCEPT` would
violate the frozen human-authority rule. Therefore no owner test is requested
and **Topic edit/confirm remains `IN_PROGRESS`**.

Current Board remains exactly: **27 DONE / 1 IN_PROGRESS / 16 NOT_DONE / 1
BLOCKED**. No `PROCESS V1 USER_ACCEPTED` claim is made.

Any future repair must be separately authorized and bounded to exposing the
existing truthful preparation/review/persistence path; this report neither
implements nor approves that repair.
