# Integra Executable Roadmap

Source plan: `docs/INTEGRA_PLAN.md`

Program Epic: [GitHub Issue #1](https://github.com/Yurielo/integra/issues/1)

Rebaseline authority: [GitHub Issue #62](https://github.com/Yurielo/integra/issues/62)

The active target is `READY_APP_V1`. Delivery is coordinated by the governed
ten-role agent team defined in
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
| R9B Media integration | #14 | M3 | R5, R6, OPERATIONS_AND_DIAGNOSTICS_V1 | ACCEPTED |
| R9C Cross-navigation | #15 | M3 | R8C, R9A, R9B | ACCEPTED |
| R10 deterministic one-way Obsidian export | #16 | M4 | R9C | ACCEPTED |
| ONEDRIVE_PUBLICATION_V1 | #63 | M4 | R10 | ACCEPTED |
| R12 usable native macOS application | #28 | M6 | ONEDRIVE_PUBLICATION_V1 | ACCEPTED |
| R13 hardening and reproducible local `.app` package | #29 | M7 | R12 | ACCEPTED |
| USER_MEDIA_WORKFLOW_V1 | #72 | M7 | R13 | ACCEPTED |
| SOURCE_FIRST_UI_V1 | #76 | M7 | USER_MEDIA_WORKFLOW_V1 | ACCEPTED |
| R14 Product Owner READY_APP_V1 acceptance | #30 | M7 | SOURCE_FIRST_UI_V1 | ACCEPTED (2026-09-13) |
| DEFERRED_CAPABILITIES_V1 registry | #64 | Later | R14 | DEFERRED_TO_LATER_WORK |
| R11 Marketing Studio v1 | #17 | Later | R9A, R10, R14 | DEFERRED_TO_LATER_WORK |
| LEARNING_V1 | #18 | Later | R9A, R14 | DEFERRED_TO_LATER_WORK |
| ASSISTANT_V1 | #19 | Later | R9A, R9C, R14 | DEFERRED_TO_LATER_WORK |
| SOCIAL_FOUNDATION | #20 | Later | R10, R14 | DEFERRED_TO_LATER_WORK |
| SOCIAL_FACEBOOK | #21 | Later | SOCIAL_FOUNDATION | DEFERRED_TO_LATER_WORK |
| SOCIAL_INSTAGRAM | #22 | Later | SOCIAL_FOUNDATION | DEFERRED_TO_LATER_WORK |
| SOCIAL_THREADS | #23 | Later | SOCIAL_FOUNDATION | DEFERRED_TO_LATER_WORK |
| SOCIAL_YOUTUBE | #24 | Later | SOCIAL_FOUNDATION | DEFERRED_TO_LATER_WORK |
| SOCIAL_TELEGRAM | #25 | Later | SOCIAL_FOUNDATION | DEFERRED_TO_LATER_WORK |
| SOCIAL_WHATSAPP | #26 | Later | SOCIAL_FOUNDATION | DEFERRED_TO_LATER_WORK |
| SOCIAL_TIKTOK | #27 | Later | SOCIAL_FOUNDATION | DEFERRED_TO_LATER_WORK |
| R15 optional repository consolidation | #31 | Later | R14 | DEFERRED_TO_LATER_WORK |

## READY_APP_V1 sequence

R10 owns only deterministic one-way Obsidian export. Issue #63 then owns the
filesystem-backed OneDrive publication contract. R12 must build and test a
usable native macOS application over the accepted core plus both publication
paths. R13 hardens that application and produces a reproducible local `.app`
package. Corrective Issue #72 adds the missing raw audio/video-to-publication
journey. Issue #76 replaces the module-first shell with the source-first
Capability Registry and planner UI. R14 was explicitly accepted by the Product
Owner on 2026-09-13; post-R14 work still requires its own bounded scope and
retains every non-product gate.

Signing identity, notarization, public distribution, live external writes,
credentials, protected data, authoritative semantics, destructive migration,
and source-product retirement are not authorized by this roadmap or by R14.

## Deferred registry

Issue #64 records all unavailable later-work capabilities in machine-readable
and user-visible form. Marketing, Learning, Assistant, additional Publishing
Hub formats, the social foundation and all seven social adapters follow R14 and
cannot block the active chain. Their current Issue numbers remain stable;
deferral is not completion or standing authority to implement them. R15 uses
the same `DEFERRED_TO_LATER_WORK` status and also remains blocked by R14 and its
separate source-repository authorization boundary.

## Advancement rule

A stage may start only when its dependencies are accepted and its exact scope
is authorized by current policy or Product Owner instruction. Technical work
continues autonomously inside that scope. Protected data, live accounts,
external publication, semantics, destructive migration, signing, release, and
source-product retirement retain their explicit gates. Verified in-scope merge
is automatic only under the fail-closed execution policy.
