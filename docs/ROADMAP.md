# Integra Executable Roadmap

Source plan: `docs/INTEGRA_PLAN.md`

Program Epic: [GitHub Issue #1](https://github.com/Yurielo/integra/issues/1)

Delivery is coordinated by the governed ten-role agent team defined in
[`AGENT_TEAM_OPERATING_MODEL.md`](architecture/AGENT_TEAM_OPERATING_MODEL.md).
`product-owner` is the lead agent; specialist activation is risk-based and does
not add routine human gates or change stage dependencies.

| Stage | Issue | Milestone | Depends on | Current state |
| --- | ---: | --- | --- | --- |
| R0 Product definition and governance | #2 | M0 | — | ACCEPTED |
| R1 Baseline certification | #3 | M0 | R0 | ACCEPTED |
| R2 Ownership, IDs, lease | #4 | M0 | R0, R1 | ACCEPTED |
| R3 Versioned contracts | #5 | M0 | R1, R2 | ACCEPTED |
| R4 Adapter spike | #6 | M0 | R1–R3 | ACCEPTED |
| R5 Capability benchmark | #7 | M1 | R4 | ACCEPTED |
| R6 Core Alpha | #8 | M1 | R5 | ACCEPTED |
| OPERATIONS_AND_DIAGNOSTICS_V1 | #46 | M1 | R6 | ACCEPTED |
| R7 Copy-on-write migration | #9 | M1 | R6, OPERATIONS_AND_DIAGNOSTICS_V1 | ACCEPTED |
| R8A YouTube playlists | #10 | M2 | R3, R6, OPERATIONS_AND_DIAGNOSTICS_V1 | ACCEPTED |
| R8B Documents and OCR | #11 | M2 | R3, R6, OPERATIONS_AND_DIAGNOSTICS_V1 | ACCEPTED |
| PROJECTS_AND_SOURCES_V1 | #47 | M2 | R6, R7, R8A, R8B | ACCEPTED |
| TRANSCRIPT_AND_TOPIC_STUDIO_V1 | #48 | M2 | R6, PROJECTS_AND_SOURCES_V1 | ACCEPTED |
| R8C Multi-source alignment | #12 | M2 | R8A, R8B, PROJECTS_AND_SOURCES_V1, TRANSCRIPT_AND_TOPIC_STUDIO_V1 | ACCEPTED |
| R9A Knowledge integration | #13 | M3 | R6, R8C, TRANSCRIPT_AND_TOPIC_STUDIO_V1 | ACCEPTED |
| R9B Media integration | #14 | M3 | R5, R6, OPERATIONS_AND_DIAGNOSTICS_V1 | PLANNED |
| R9C Cross-navigation | #15 | M3 | R8C, R9A, R9B | PLANNED |
| R10 Publishing, Obsidian, OneDrive | #16 | M4 | R9C | PLANNED |
| R11 Marketing Studio v1 | #17 | M4 | R9A, R10 | PLANNED |
| LEARNING_V1 | #18 | M4 | R9A | PLANNED |
| ASSISTANT_V1 | #19 | M4 | R9A, R9C | PLANNED |
| SOCIAL_FOUNDATION | #20 | M5 | R10 | DEFERRED_UNTIL_DEPENDENCY |
| SOCIAL_FACEBOOK | #21 | M5 | SOCIAL_FOUNDATION | DEFERRED_UNTIL_DEPENDENCY |
| SOCIAL_INSTAGRAM | #22 | M5 | SOCIAL_FOUNDATION | DEFERRED_UNTIL_DEPENDENCY |
| SOCIAL_THREADS | #23 | M5 | SOCIAL_FOUNDATION | DEFERRED_UNTIL_DEPENDENCY |
| SOCIAL_YOUTUBE | #24 | M5 | SOCIAL_FOUNDATION | DEFERRED_UNTIL_DEPENDENCY |
| SOCIAL_TELEGRAM | #25 | M5 | SOCIAL_FOUNDATION | DEFERRED_UNTIL_DEPENDENCY |
| SOCIAL_WHATSAPP | #26 | M5 | SOCIAL_FOUNDATION | DEFERRED_UNTIL_DEPENDENCY |
| SOCIAL_TIKTOK | #27 | M5 | SOCIAL_FOUNDATION | DEFERRED_UNTIL_DEPENDENCY |
| R12 Combined Beta | #28 | M6 | OPERATIONS_AND_DIAGNOSTICS_V1, R7, PROJECTS_AND_SOURCES_V1, TRANSCRIPT_AND_TOPIC_STUDIO_V1, R8C, R9C, R10, R11, LEARNING_V1, ASSISTANT_V1, SOCIAL_FACEBOOK–SOCIAL_TIKTOK | PLANNED |
| R13 Security and release E2E | #29 | M7 | R12 | PLANNED |
| R14 Product Owner acceptance | #30 | M7 | R13 | HUMAN_GATE |
| R15 Repository consolidation | #31 | M8 | accepted 1.0 | POST_1_0_DEFERRED |

## Advancement rule

A stage may start only when its dependencies are accepted and its exact scope
is authorized by current policy or Product Owner instruction. Technical work
continues autonomously inside that scope. Protected data, live accounts,
external publication, semantics, destructive migration, release, and
source-product retirement retain their explicit gates. Verified in-scope merge
is automatic only under the fail-closed execution policy.

R1 pins clean merged source commits and their supported contracts. SeminarText
passed its complete supported suite and Integrity baseline. VideoText passed a
clean build, all input-independent probes, the long-topic probe, and two
sequential real-video E2E runs through its release gate. The candidate was not
promoted and R1 does not authorize source-product release.

R6 combines the dependency-free contract-replay checkpoint in
`state/core_alpha_v1.json` with pinned real-media evidence in
`state/core_alpha_real_v1.json`. Replay proves content-addressed lineage,
Project Lease, cancellation, deterministic checkpoints and fail-closed resume.
The actual run passes pinned VideoText and SeminarText results through the same
control plane and validated R3 envelopes, binding exact source/model hashes,
word/topic/clip intervals and parent lineage. It yields an unresolved review
package, provisional knowledge and a rendered media clip. R6 technical
acceptance does not promote machine semantics.
