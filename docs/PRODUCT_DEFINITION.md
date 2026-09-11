# Integra Product Definition v1

Status: `READY_APP_V1_REBASELINED`

Authority: Product Owner authorization in GitHub Issue #62

Baseline date: 2026-09-11

## 1. Product outcome

Integra is a separate native macOS product that provides one governed workflow
from heterogeneous source material to traceable knowledge, media, and safe
local publication outputs. It integrates accepted, pinned SeminarText and
VideoText capabilities without requiring either source application to stop
working.

The `READY_APP_V1` outcome is:

`source -> transcript/document evidence -> Topics -> exception-only review -> canonical knowledge/media -> cross-navigation -> Obsidian export -> OneDrive publication -> usable macOS application`

Every substantive result retains an exact route back to its source interval,
word, page, slide, region, or artifact revision.

## 2. Required READY_APP_V1 scope

The active delivery chain is `R9C -> R10 -> ONEDRIVE_PUBLICATION_V1 -> R12 ->
R13 -> USER_MEDIA_WORKFLOW_V1 -> R14`. R9C and its prerequisites are accepted. The remaining stages must
deliver all of the following:

1. **Accepted core:** Projects & Sources, Transcript & Topic Studio, Knowledge
   Studio, Media Studio, cross-navigation, Operations & Diagnostics, and
   compatibility/copy-on-write migration remain required and regression-safe.
2. **Obsidian export (R10):** deterministic one-way export of managed
   Markdown/JSON metadata with preview, staging, manifest, hashes, export lock,
   collision protection, exact source links, atomic promotion, and rebuild.
3. **OneDrive publication (#63):** filesystem-backed staged publication with
   immutable versions, manifests, checksums, `COMPLETE.json` written last,
   offline queueing, Files On-Demand checks, conflict detection, mutual
   exclusion, and verified recovery.
4. **Native macOS application (R12):** a buildable, launchable, usable native
   application exposing the accepted core, Obsidian export, OneDrive
   publication, Operations & Diagnostics, and a read-only Deferred Features
   registry. Unavailable features cannot present runnable or successful
   placeholder actions.
5. **Hardening and local package (R13):** minimum macOS and bundle identity,
   entitlements boundary, privacy/redaction, dependency and licensing review,
   reproducible local `.app` package, backup, crash recovery, update readiness,
   and rollback evidence.
6. **Product Owner acceptance (R14):** explicit acceptance of the exact
   `READY_APP_V1` candidate, included capability list, deferred registry, known
   limitations, compatibility, migration, and release boundary.

## 3. Deferred to later work

The following capabilities are deliberately visible in the ready application
but are not required for `READY_APP_V1` and cannot block R12-R14:

- Publishing Hub formats beyond the managed Obsidian Markdown/JSON metadata
  and OneDrive package contracts, including general standalone DOCX, PDF, SRT,
  audio, and video export;
- Marketing Studio v1 and its project playbooks;
- Learning Studio v1;
- Knowledge Assistant v1;
- Social Adapter Foundation and adapters for Facebook Pages, Instagram,
  Threads, YouTube, Telegram, WhatsApp Business, and TikTok;
- live YouTube API/media download, a bound local OCR engine, automatic
  multi-source matching, and representative full Media Studio execution;
- bidirectional Obsidian synchronization and Microsoft Graph OneDrive;
- unattended or live external publication;
- public distribution, signing, notarization, and update publication;
- source-repository consolidation or source-application retirement;
- mobile, web, Windows, multi-user server, personalized adaptive learning,
  unrestricted RAG, and full autonomous semantic authoring.

Issue #64 owns the durable `DEFERRED_TO_LATER_WORK` registry. Deferred work may
be planned only after R14 unless the Product Owner explicitly rebaselines the
roadmap again. Deferral is not implementation, acceptance, or authorization.

## 4. Product invariants and retained gates

- Machine semantic output remains `PROVISIONAL` or `REVIEW_REQUIRED` until an
  explicit authorized ReviewDecision.
- Original source wording and provenance are preserved through normalization.
- Derived media, export, and future marketing/learning views cannot silently
  alter Canonical Evidence or Canonical Knowledge.
- One bulk decision may cover an explicitly enumerated validated package.
- Source applications and projects remain independently usable through R14.
- External publication is a separate, auditable operation from generation.
- Protected or private data, credentials/accounts, live external writes,
  authoritative semantic acceptance, Concept-identity merging, destructive
  migration, signing identity, and release authority remain explicitly gated.
  Neither R14 acceptance nor deferred status grants those authorities.

## 5. Success measures

- The accepted core and its exact provenance continue to pass their governed
  evidence and regression checks.
- Obsidian export and filesystem-backed OneDrive publication survive
  interruption, preserve user-owned content, and detect conflict.
- A reproducible native macOS application builds, launches, and supports the
  complete `READY_APP_V1` user journey on the reference Mac.
- Deferred capabilities are visible as later/unavailable and cannot be mistaken
  for implemented behavior.
- SeminarText and VideoText standalone compatibility remains intact.
- The Product Owner explicitly accepts the exact candidate at R14. Signing,
  notarization, public distribution, live external actions, and source-product
  retirement remain separate authorization boundaries.
