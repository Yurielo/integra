# Integra Product Definition v1

Status: `R0_ACCEPTED`

Authority: Product Owner authorization to implement the approved Integra plan

Baseline date: 2026-09-09

## 1. Product outcome

Integra is a separate native macOS product that provides one governed workflow
from heterogeneous source material to traceable knowledge, media, learning,
marketing, and publication outputs. It integrates accepted, pinned SeminarText
and VideoText capabilities without requiring either source application to stop
working.

The primary user outcome is:

`source → transcript/document evidence → Topics → exception-only review → canonical knowledge → derived media/learning/marketing output → governed publication`

Every substantive result retains an exact route back to its source interval,
word, page, slide, region, or artifact revision.

## 2. Required Integra 1.0 scope

Integra 1.0 requires all of the following product capabilities:

1. **Projects & Sources:** local media, individual YouTube videos, playlists,
   supported documents, presentations, images, scans, source identity, hashes,
   lifecycle, and provenance.
2. **Transcript & Topic Studio:** media preparation, ASR, translation, Word
   Timeline, Topic sets and hierarchy, quality findings, and exception-only
   review packages.
3. **Knowledge Studio:** Canonical Evidence, Concepts, Practices, Terms,
   Relations, Canonical Knowledge, graph views, Knowledge Diff, and exact
   source navigation.
4. **Media Studio:** clips, subtitles, translation, TTS, speed, blur,
   watermark, audio enhancement, filler-word mute, deterministic recipes, and
   media QA.
5. **Marketing Studio v1:** evidence-backed drafts, Marketing Passport,
   channel packages, shared rules, and versioned project playbooks for
   “Лунные практики” and “Человек. Инструкция по применению”.
6. **Learning Studio v1:** notes, summaries, methodology, FAQ, exercises,
   tests, prerequisites, difficulty, and evidence-linked learning routes.
7. **Knowledge Assistant v1:** search and evidence-cited answers across
   projects, sources, Topics, knowledge entities, and media.
8. **Publishing Hub:** versioned packages, preview, manifests, checksums,
   collision handling, recovery, Markdown/JSON/DOCX/PDF/SRT/media export,
   deterministic one-way Obsidian export, and filesystem-backed OneDrive
   publication.
9. **Social adapters:** official-API adapters for Facebook Pages, Instagram,
   Threads, YouTube, Telegram, WhatsApp Business, and TikTok after Publishing
   Hub is complete. Adapter code, capability checks, dry-run/contract evidence,
   and safe manual fallback are 1.0 scope. Live account connection, platform
   approval, or real publication requires separately applicable authorization.
10. **Operations & Diagnostics:** jobs, progress, cancellation, resume,
    resource scheduling, capability checks, structured logs, Integrity,
    recovery, component identities, and reference-Mac operation.
11. **Compatibility & Migration:** pinned source components, read-only
    discovery, copy-on-write migration, rollback, and combined regression
    testing while both standalone applications remain usable.

## 3. Explicitly outside Integra 1.0

- destructive or in-place conversion of source projects;
- retirement of SeminarText or VideoText;
- physical Git-repository consolidation;
- bidirectional Obsidian synchronization;
- Microsoft Graph OneDrive integration;
- unattended external publication without an accepted standing policy;
- automatic semantic acceptance or automatic Concept-identity merging;
- full autonomous semantic authoring;
- personalized adaptive learning and unrestricted RAG over unreviewed data;
- mobile, web, Windows, or multi-user server editions;
- access to private projects, governed datasets, Gold, accounts, or
  credentials without exact authorization.

## 4. Product invariants

- Machine semantic output remains `PROVISIONAL` or `REVIEW_REQUIRED` until an
  explicit authorized ReviewDecision.
- Original source wording and provenance are preserved through normalization.
- Derived marketing, learning, media, and Obsidian views cannot silently alter
  Canonical Evidence or Canonical Knowledge.
- One bulk decision may cover an explicitly enumerated validated package.
- Human review is reserved for genuine semantic, authority, privacy,
  publication, destructive, or unresolved ambiguity gates.
- Source applications and projects remain independently usable through 1.0.
- External publication is a separate, auditable operation from content
  generation.

## 5. Success measures

- One local video completes the Core Alpha path with exact provenance.
- Playlist, document, and multi-source pipelines resume safely and preserve
  source-specific locators.
- Knowledge, media, learning, and marketing outputs round-trip to evidence.
- Obsidian and OneDrive publishing survives interruption and detects conflict.
- Social adapters fail closed on capability, permission, or policy drift.
- The M5/16 GB reference Mac completes Combined Beta without uncontrolled
  resource contention or leaked child processes.
- SeminarText and VideoText standalone test matrices do not regress.
- The release candidate is signed, notarized, reproducible, recoverable, and
   explicitly accepted by the Product Owner.
