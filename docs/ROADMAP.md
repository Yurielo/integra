# Integra Executable Roadmap

Source plan: `docs/INTEGRA_PLAN.md`

Program Epic: [GitHub Issue #1](https://github.com/Yurielo/integra/issues/1)

Delivery is coordinated by the governed nine-role agent team defined in
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
| R6 Core Alpha | #8 | M1 | R5 | PLANNED |
| R7 Copy-on-write migration | #9 | M1 | R6 | PLANNED |
| R8A YouTube playlists | #10 | M2 | R6, R3 | PLANNED |
| R8B Documents and OCR | #11 | M2 | R6, R3 | PLANNED |
| R8C Multi-source alignment | #12 | M2 | R8A, R8B | PLANNED |
| R9A Knowledge integration | #13 | M3 | R6, relevant R8 | PLANNED |
| R9B Media integration | #14 | M3 | R6, R5 | PLANNED |
| R9C Cross-navigation | #15 | M3 | R8C, R9A, R9B | PLANNED |
| R10 Publishing, Obsidian, OneDrive | #16 | M4 | R9C | PLANNED |
| R11 Marketing Studio v1 | #17 | M4 | R0, R9A, R10 | PLANNED |
| Learning Studio v1 | #18 | M4 | R0, R9A | PLANNED |
| Knowledge Assistant v1 | #19 | M4 | R0, R9A, R9C | PLANNED |
| Social adapter foundation | #20 | M5 | R10 | DEFERRED_UNTIL_DEPENDENCY |
| Seven platform adapters | #21–#27 | M5 | #20, R10 | DEFERRED_UNTIL_DEPENDENCY |
| R12 Combined Beta | #28 | M6 | all required 1.0 capabilities | PLANNED |
| R13 Security and release E2E | #29 | M7 | R12 | PLANNED |
| R14 Product Owner acceptance | #30 | M7 | R13 | HUMAN_GATE |
| R15 Repository consolidation | #31 | M8 | accepted 1.0 | POST_1_0_DEFERRED |

## Advancement rule

A stage may start only when its dependencies are accepted and its exact scope
is authorized by current policy or Product Owner instruction. Technical work
continues autonomously inside that scope. Protected data, live accounts,
external publication, semantics, destructive migration, merge, release, and
source-product retirement retain their explicit gates.

R1 pins clean merged source commits and their supported contracts. SeminarText
passed its complete supported suite and Integrity baseline. VideoText passed a
clean build, all input-independent probes, the long-topic probe, and two
sequential real-video E2E runs through its release gate. The candidate was not
promoted and R1 does not authorize source-product release.
