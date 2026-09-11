# Integra Integration Plan

Version: 1.0 (consolidates audited planning revision v5)
Status: APPROVED BASELINE — SAFE ROADMAP IMPLEMENTATION AUTHORIZED
Product name: Integra
Recorded: 2026-09-09
Implementation authorization recorded: 2026-09-10

## 1. Purpose

Integra is a planned native macOS application that unifies the existing
SeminarText knowledge/evidence workflows and VideoText media-production
workflows while preserving both source applications as independently working
products until Integra has passed final acceptance.

The complete product direction includes:

- project and source management;
- local video and audio processing;
- individual YouTube videos and YouTube playlists;
- PDF, PPTX, DOCX, TXT, Markdown, images, scans, and supporting materials;
- transcription, translation, Word Timeline, Topics, and Human Review;
- Canonical Evidence and Canonical Knowledge;
- Media Studio;
- Marketing Studio;
- Learning Studio;
- Obsidian and OneDrive integration;
- search and knowledge-assistant capabilities;
- governed publishing, diagnostics, recovery, and quality control.

The accepted Projects & Sources v1 foundation now provides the unified project
registry and stable source/revision lineage for every source family above. It
reuses the accepted playlist and document contracts and preserves original
files and applications as read-only source systems.

The Product Owner has authorized safe roadmap implementation after the GitHub
Issues and milestones were created. A stage may proceed when its dependencies
and factual preconditions are verified. This standing implementation authority
authorizes verified in-scope merge under the fail-closed autonomous execution
policy. It does not authorize release, live external actions, credentials,
private or governed data, semantic acceptance, destructive migration,
source-product retirement, or source-repository changes. Those boundaries
remain explicit and must be reverified at execution time.

## 2. Non-negotiable invariants

### 2.0 Governed delivery team

Integra is developed by a risk-routed Codex agent team. `product-owner` is the
lead coordinating agent: it maintains scope and acceptance criteria, selects
only relevant specialists, assigns non-overlapping ownership, and consolidates
evidence. The human Product Owner remains the authority at genuine gates.

The team includes system architecture, backend, frontend, data-contract, QA, CI/CD, independent PR
review, delivery planning, and repository-documentation roles. These roles do
not form a mandatory serial pipeline; a narrow change may use one implementer
plus proportionate verification. Technical handoffs, safe repairs, CI, verified
merge, and progression along the accepted roadmap do not require user dispatch.
The governed contract is
`docs/architecture/AGENT_TEAM_OPERATING_MODEL.md`.

### 2.1 Parallel operation guarantee

Until final Integra acceptance:

- SeminarText MUST continue to run independently;
- VideoText MUST continue to run independently;
- an Integra build MUST remain a third, separately testable product;
- existing projects MUST remain openable by their original application;
- integration work MUST NOT destructively migrate or overwrite existing projects;
- a regression in either standalone application blocks promotion of Integra;
- retirement of either source application requires a separate Product Owner
  decision after Integra acceptance.

### 2.2 No Big Bang migration

Integration proceeds through versioned contracts, adapters, read-only discovery,
copy-on-write migration, feature flags, compatibility testing, and rollback.
Physical consolidation of Git repositories is optional and is never a
precondition for one unified application.

### 2.3 Evidence and semantic authority

- Machine output may proceed automatically as `PROVISIONAL`.
- Machine-generated semantic content MUST NOT become authoritative without an
  explicit human ReviewDecision.
- One explicit bulk ReviewDecision may cover a validated package of many items.
- Original source material, terminology, revision lineage, and provenance MUST
  remain traceable.
- Marketing, learning, media, and Obsidian outputs are derived views and MUST NOT
  silently modify Canonical Evidence or Canonical Knowledge.

### 2.4 Exception-only human interaction

Technical work is autonomous by default. Human interaction is reserved for:

- an actual product, architecture, or authority decision;
- authoritative semantic acceptance;
- genuinely ambiguous semantic evidence;
- privacy or publication approval;
- destructive or irreversible migration;
- unresolved conflicts or unsafe external actions.

Routine builds, tests, provisional generation, manifests, safe recovery,
read-only discovery, dry runs, and deterministic exports are not human gates.

### 2.5 Protected data and source systems

Integration work does not infer permission to access governed datasets, Gold,
private media, external accounts, credentials, or real project data. Each task
must carry explicit scope and permissions. Historical instructions and open
Issues are context, not authorization.

## 3. Product boundaries

### 3.1 Core Merge

Core Merge establishes one working Integra shell over accepted, pinned versions
of SeminarText and VideoText with:

- projects and source references;
- local video/audio ingestion;
- transcript and Topic workflows;
- versioned Human Review integration;
- Canonical Evidence/Knowledge access;
- media output;
- provenance, diagnostics, cancellation, and recovery;
- preservation of both standalone applications.

### 3.2 Mandatory Integration Extensions

The complete integration release must additionally support:

- individual YouTube videos and YouTube playlists;
- document and presentation processing;
- multi-source alignment;
- safe one-way Obsidian export;
- safe filesystem-backed OneDrive publication and recovery;
- migration of existing SeminarText and VideoText projects without data loss.

### 3.3 Product modules

R0 fixed the following modules as required Integra 1.0 scope:

- Marketing Studio with initial project playbooks for “Лунные практики” and
  “Человек. Инструкция по применению”;
- Learning Studio;
- Knowledge Assistant;
- the Publishing Hub and seven social-adapter implementations defined in the
  Product Definition.

They remain outside the bounded Core Merge but are mandatory before Combined
Beta and Integra 1.0 acceptance. Full RAG, automatic external social
publishing, Microsoft Graph, bidirectional Obsidian sync, and personalized
learning remain outside Core Merge unless separately adopted.

## 4. Target user-facing modules

### 4.1 Projects & Sources

- seminar, course, series, and event projects;
- local video and audio;
- YouTube video and playlist sources;
- PDF, PPTX, DOCX, TXT, Markdown, images, scans, and supporting material;
- Source Registry, project history, lifecycle, and provenance.

### 4.2 Transcript & Topic Studio

- media preparation and ASR;
- machine and reviewed TranscriptRevision;
- translation;
- Word Timeline;
- transcript-quality findings;
- detailed, normal, and coarse Topic sets;
- hierarchy and source alignment;
- exception-only review queues and bulk ReviewDecision packages.

### 4.3 Knowledge Studio

- Canonical Evidence;
- Concepts, Practices, Terms, and Relations;
- Canonical Knowledge and Knowledge Graph views;
- methodology development and cross-seminar traceability;
- Knowledge Diff and safe Obsidian export.

### 4.4 Media Studio

- clip extraction by interval, Topic, or quote;
- subtitles, translation, and TTS;
- speed adjustment, blur, watermark, audio enhancement, and filler-word mute;
- deterministic media recipes, rendering, QA, and provenance.

### 4.5 Marketing Studio

- evidence-backed meaning foundation and Marketing Passport;
- WhatsApp, Telegram, Instagram, Stories, Threads, and YouTube packages;
- image prompts and visual packages;
- factual, privacy, format, visual, and publication quality gates;
- versioned Project Playbooks rather than executable monolithic prompts.

### 4.6 Learning Studio

- summaries, course notes, methodological material, FAQ, exercises, tests,
  prerequisites, difficulty levels, and learning routes;
- every substantive output remains linked to exact evidence.

### 4.7 Knowledge Assistant

- evidence-cited search and answers across projects, sources, Topics,
  knowledge entities, media artifacts, and clips;
- exact source, evidence, and media navigation with visible uncertainty and
  provisional/accepted state.

### 4.8 Publishing Hub

- Obsidian, OneDrive, Markdown, JSON, DOCX, PDF, SRT, audio, and video outputs;
- versions, manifests, checksums, publication queues, recovery, and collision
  handling.

### 4.9 Operations & Diagnostics

- job queue, progress, ETA, capability checks, logs, cache, cancellation,
  process shutdown, model lifecycle, Integrity, and recovery.

## 5. Sources of truth and data ownership

Before code integration, R2 must produce a field-level ownership matrix. The
initial direction is:

| Entity | Intended owner | Other components |
| --- | --- | --- |
| Integra project orchestration/index | Integra | read/reference |
| Source identity and fingerprint | contract-defined single owner | read/reference |
| Machine transcript artifact | selected ASR component | read |
| Canonical Word Timeline | SeminarText | read |
| Topic Draft | selected Topic component | propose/read |
| ReviewDecision | governed Human Review contract | read |
| Canonical Evidence/Knowledge | SeminarText | read |
| Media recipe and media artifact | VideoText | read/reference |
| Publication package/status | Integra Publishing | read/reference |
| Obsidian managed view | Integra exporter with user-owned boundary | controlled write |
| OneDrive publication | Integra Publishing adapter | verify/reference |

Integra orchestration MUST index component-owned artifacts rather than duplicate
and independently mutate their authoritative fields.

### 5.1 Project lease

Parallel applications require an inter-process Project Lease containing at
least:

- project ID;
- writer component and process instance;
- operation ID;
- acquisition and expiry timestamps;
- heartbeat;
- reader information where relevant.

Only one writer may own a mutable entity at a time. Stale-lock recovery must be
fail-closed and must verify process and artifact state before releasing a lease.

## 6. Versioned integration protocol

The SeminarText worker and VideoText adapters must expose a local, structured,
versioned protocol supporting:

- protocol handshake and capability discovery;
- pinned component and model identities;
- job ID and idempotency key;
- structured requests, progress events, and results;
- cancellation acknowledgement;
- retry classification and structured errors;
- input and output hashes;
- timeouts and resume tokens;
- backward-compatibility declaration;
- worker and runtime identity.

The first implementation should prefer a controlled local process and artifact
exchange over a network service. Rewriting SeminarText in Swift is not required
for integration.

## 7. Selection of overlapping implementations

The application is not selected as one winner. Each overlapping capability is
evaluated separately:

- media preparation;
- ASR;
- word/cue alignment;
- translation;
- Topic generation and hierarchy;
- Human Review mechanics;
- cache, recovery, and quality validation.

The comparison order is:

`contracts -> minimal adapters -> normalized replay fixtures -> benchmark -> selection`

Every comparison records:

- exact input and source lifecycle;
- component, model, configuration, and code hashes;
- hard correctness and provenance gates;
- quality metrics appropriate to the capability;
- human correction burden where semantic quality is involved;
- resource use and runtime;
- recovery and reproducibility results;
- selected implementation, fallback, and decision authority.

No benchmark may silently use a prohibited dataset or change an accepted model,
Gold, semantic decision, or lifecycle role. A losing implementation remains a
challenger or fallback until replacement is proven and accepted.

## 8. Source pipelines

### 8.1 YouTube playlists

A playlist is a collection, not one media file. Integra must:

- inspect playlist metadata before downloading media;
- preserve playlist ID, video ID, order, title, availability, and snapshot time;
- allow all-item or subset selection;
- process one heavy item at a time with checkpoints;
- avoid redownloading completed video IDs;
- retain local evidence when a remote item becomes private, unavailable, or
  deleted;
- report additions, removals, and reorderings on refresh;
- estimate storage requirements before execution;
- preserve per-video provenance while composing course/seminar results.

### 8.2 Documents and presentations

The document pipeline must cover:

- PPTX slide text, structure, images, and notes where available;
- PDF pages, text, and image-heavy/OCR fallback;
- DOCX structure and media;
- TXT and Markdown;
- images and scans without falsely presenting visual content as ordinary text;
- page, slide, region, and character locators;
- video-to-slide, Topic-to-page/slide, and Evidence-to-document alignment.

YouTube collection, document extraction, and multi-source alignment are separate
milestones so that one incomplete source class does not obscure another.

## 9. Obsidian and OneDrive

### 9.1 Obsidian

The first complete integration requires deterministic one-way export:

- Canonical Knowledge remains authoritative;
- generated files live in a managed subtree;
- user-owned notes are protected;
- staging, manifest, hashes, export lock, collision report, and rebuild checks
  are mandatory;
- exact video, page, slide, and evidence links are retained.

Bidirectional sync requires a separate conflict and authority contract and is
not part of Core Merge.

### 9.2 OneDrive

Heavy processing must occur outside the synchronized OneDrive directory. A
filesystem-backed adapter must provide:

- staging and atomic publication of completed artifacts;
- immutable versions, `publish_manifest.json`, `checksums.sha256`, and
  `COMPLETE.json` written last;
- queueing while OneDrive is unavailable;
- Files On-Demand placeholder detection;
- physical-size and hash verification;
- conflict-copy detection;
- verified recovery;
- exclusion of reproducible heavy cache and temporary render files by default.

A successful local write must not be represented as a verified cloud
publication without the required verification. Microsoft Graph is optional and
requires separate scope.

An Obsidian Vault stored in OneDrive must additionally use a managed subtree,
export lock, staging, and conflict detection. Obsidian export and OneDrive
recovery must not write the same target concurrently.

## 10. Marketing Project Playbooks

The existing master prompts for “Лунные практики” and “Человек. Инструкция по
применению” are reference/governance source documents, not executable runtime
instructions. Import follows:

`source prompt -> requirement extraction -> evidence matrix -> common rules -> project-specific rules -> conflict review -> playbook draft -> Product Owner review -> versioned profile`

The source prompts remain immutable and traceable. Initial playbooks may cover:

- project structure and terminology;
- event/practice or meeting lifecycle;
- manifests, registers, versions, and statuses;
- approved channel formats;
- methodology, privacy, factual, visual, and publication gates;
- OneDrive and Obsidian mappings.

Marketing outputs are `DERIVED_MARKETING_CONTENT`. They may not become evidence
or silently update Canonical Knowledge. External publication remains a bounded
explicit action.

## 11. Human-gate model

The desired processing loop is:

`automatic processing -> deterministic QA -> provisional output -> exception clustering -> consolidated review package -> explicit bulk decision when authority is required -> automatic derived outputs -> one publication gate`

Human interaction is minimized through:

- selective transcript/audio verification;
- confidence and risk classification;
- clustering repeated exceptions;
- exact evidence and neighbouring context;
- bulk decisions with explicit item membership;
- project playbooks and previously accepted terminology;
- no intermediate technical report when safe autonomous work can continue.

Prior decisions improve proposals and reduce repeated questions, but do not
automatically accept new semantic meaning.

## 12. Resource model

The reference development and acceptance machine is currently:

- MacBook Air 13-inch;
- Apple M5, 10 CPU cores, 8 GPU cores;
- 16 GB unified memory;
- 512 GB internal SSD.

This is a reference profile, not a permanent minimum system requirement. The
first release must use capability detection and a Resource Scheduler.

### 12.1 Resource Scheduler

Jobs are classified as lightweight, heavy-model, or heavy-media. On a 16 GB
system:

- no more than one heavy-model operation runs at once;
- no more than one heavy-media operation runs at once;
- Whisper and Ollama do not run concurrently by default;
- heavy FFmpeg rendering does not run concurrently with Whisper by default;
- playlist items are processed sequentially;
- memory pressure, swap, loaded models, free disk, child processes, and target
  availability are checked before heavy work.

Integra must support model unloading, checkpoints, pause/resume, cancellation,
bounded retries, safe child-process termination, and graceful degradation.

### 12.2 Storage and external SSD

Required temporary space is calculated per operation from source size, extracted
audio, cache, intermediate media, final output, and a safety margin. Fixed disk
thresholds are warnings only; the calculated requirement is authoritative.

Users must be able to choose internal or external APFS-compatible workspaces and
separate cache/render/result locations. Device removal must fail safely and
permit verified resume after reconnection.

## 13. Migration and compatibility

Migration supports existing SeminarText projects, VideoText schema v7 projects,
OneDrive structures, Obsidian notes, and approved project manifests/registers
when in scope.

Mandatory properties:

- read-only discovery;
- dry run;
- copy-on-write output;
- stable-ID mapping;
- source and artifact hashes;
- migration report;
- validation before activation;
- no deletion or rewriting of the source project;
- rollback and continued use of the original application.

Combined Beta must test SeminarText standalone, VideoText standalone, and
Integra together. Any regression in a source product blocks promotion.

## 14. Test and release architecture

One giant E2E is not sufficient. Required layers are:

1. unit tests;
2. schema validation;
3. contract tests;
4. component tests;
5. deterministic replay;
6. integration tests with pinned component SHAs;
7. real-media tests;
8. migration and recovery tests;
9. release E2E.

Cross-repository CI records:

- Integra SHA;
- SeminarText SHA;
- VideoText SHA;
- contract versions;
- supported project schemas;
- supported macOS version;
- dependency/model identities where relevant;
- complete test result.

Integra dependencies must be pinned. A new source-project commit must not change
an Integra build until the compatibility matrix is updated and passes.

Before a public 1.0 release, the plan must define and verify:

- minimum supported macOS version;
- bundle identifier;
- signing, Hardened Runtime, and notarization;
- credential/cookie storage and log redaction;
- dependency, model, codec, and distribution licensing;
- application update and rollback strategy;
- backup and recovery of user projects.

## 15. Roadmap

### R0 — Product Definition and Governance

Persist the bounded product definition, 1.0 scope, out-of-scope list, authority
model, data-ownership model, human-gate contract, Roadmap, machine-readable
State, risk register, acceptance criteria, and governed delivery-agent model.
R0 contains no product-code integration.

### R1 — Baseline Certification

- Pin accepted SeminarText `main`; an unmerged Issue/PR is not a dependency.
- Pin a clean VideoText commit and complete its required focused, real-media,
  candidate, and release evidence.
- Record standalone compatibility and known limitations.

### R2 — Data Ownership, ID Namespace, and Project Lease

Finalize field-level ownership, stable ID namespaces, simultaneous-access rules,
writer leases, collision policy, and recovery semantics.

### R3 — Versioned Contracts

Define artifact references, worker protocol, schema evolution, capability
handshake, error model, idempotency, progress, cancellation, resume, and
compatibility rules.

### R4 — Minimal Adapter Spike

Prove that an isolated Integra shell can invoke pinned SeminarText and VideoText
capabilities through the versioned protocol without mutating source projects.

### R5 — Normalized Capability Benchmark

Use authorized normalized fixtures to compare overlapping implementations and
record component-level selection or retained challenger status.

### R6 — Integra Core Alpha

Implement one bounded local-video path:

`source -> transcript -> Topics -> review -> knowledge artifact -> media clip`

Both source applications remain independently usable.

R6 uses two complementary evidence layers. The dependency-free
`CONTRACT_REPLAY` proves pinned routing, content-addressed lineage, Project
Lease enforcement, cancellation, deterministic checkpoints and fail-closed
resume. The `PINNED_REAL_MEDIA` run invokes accepted VideoText and SeminarText
revisions on a generated non-private local video, then promotes their results
through the same Core Alpha pipeline and validated R3 envelopes. It proves
transcript, Topic, review-package, provisional-knowledge and media-clip output
with source-grounded hashes, exact intervals and parent lineage. Machine
semantic output remains `REVIEW_REQUIRED` or `PROVISIONAL`; technical R6
acceptance is not a human semantic decision.

Every real stage starts from the Core Alpha stage loop under the Project Lease,
performs an ordered R3 stdio JSONL handshake and job in a separate adapter
process, validates an existing staged result, and promotes those exact bytes.
Source internals execute only from clean archived copies of the pinned Git
trees; the standalone checkouts remain read-only.

### Operations & Diagnostics v1

Implement the horizontal control-plane services required by subsequent stages:
versioned jobs, progress and honest ETA, capability checks, Resource Scheduler,
structured redacted logs, Integrity, cancellation, resume, recovery, model
lifecycle, and child-process cleanup. This stage follows R6 and is a dependency
of migration and source-expansion work.

The accepted v1 implementation uses one atomic versioned JobStore, exact
capability preflight, a distinct atomic host ResourceReservation store, an
explicit calculated-disk record, recursively redacted/allowlisted logs,
product-neutral artifact Integrity, verified process-group shutdown and
job-owned model unloading. Unknown operational truth blocks unsafe work;
technical success is persisted only after Integrity and cleanup.

### R7 — Read-only Import and Copy-on-write Migration

Open representative existing SeminarText and VideoText projects, produce a
migration plan and copy, validate it, and prove rollback without altering the
original.

The accepted v1 implementation uses sanitized representatives of SeminarText
project schema v1 and VideoText project schema v7. It binds path-independent
stable IDs, a separate layout hash, exact file mappings and a no-overwrite
target. The imported copy remains `READY_NOT_ACTIVATED`; rollback deletes only
an exact verified Integra-owned target. External VideoText media is classified
by a hashed locator and not accessed by R7.

### R8A — YouTube Playlist Pipeline

Implement collection discovery, selection, sequential processing, refresh,
resume, provenance, and storage estimation.

The accepted v1 boundary consumes an already-fetched official-adapter metadata
snapshot without network access. It provides stable collection/video identity,
exact title/order metadata, subset plans, explicit disk estimates, durable
per-item sequential checkpoint/resume that skips only byte-verified
completions, inaccessible-item evidence, refresh diffs and retained per-video
provenance when remote membership changes.

### R8B — Document and OCR Pipeline

Implement and validate supported document types, structure, locators, OCR
fallback, and source fidelity.

The accepted v1 boundary directly preserves UTF-8 TXT/Markdown, DOCX paragraph
structure and media, PPTX slides/notes/media, and supported PDF page text and
image streams. Every result is source-hash bound with page, slide, region or
character locators. Images, scans, image-heavy PDFs and unsupported PDF text
encodings remain explicitly OCR-required unless a validated local OCR adapter
supplies region evidence; they are never reported as ordinary complete text.

### Projects & Sources v1

Complete the Project Registry, project history and lifecycle, local audio,
individual YouTube video handling, and stable source identity and provenance
across all supported source types. This stage composes R7, R8A, and R8B rather
than duplicating their pipelines.

### Transcript & Topic Studio v1

Complete media preparation, ASR, translation, Canonical Word Timeline access,
transcript-quality findings, Topic levels and hierarchy, exception packages,
and deterministic bulk ReviewDecision application. Machine semantic output
remains `PROVISIONAL` or `REVIEW_REQUIRED` until an authorized human decision.
This stage owns per-source Topic-to-locator binding; cross-source alignment
remains owned by R8C.

The accepted v1 studio binds every operation to the current Project/Source
revision and exact R5 component, model, contract and configuration identities.
It preserves time, word, page, slide, region, character and artifact-revision
locators, separates original wording from translation, clusters explicit
exceptions with neighboring evidence, and records lease-bound human decisions
without rewriting component-owned artifacts.

### R8C — Multi-source Alignment

Link video, transcript, slides, pages, supporting documents, Topics, and Evidence
without erasing per-source provenance.

The accepted v1 graph is bound to the exact current Projects & Sources registry
and current source revisions. Each node preserves a source-native locator plus
an artifact-revision locator; each typed link is content-bound to its endpoint
and evidence hashes. Forward and reverse navigation deterministically covers
video-to-transcript/slide, Topic-to-page/slide and Evidence-to-document routes.
Machine matches remain `PROVISIONAL` or `REVIEW_REQUIRED`, source artifacts are
never rewritten, and UI cross-navigation remains owned by R9C.

### R9A — Knowledge Integration

Expose Canonical Evidence/Knowledge, Concepts, Relations, review state, and
traceable navigation in Integra.

The accepted v1 read projection binds exact SeminarText component and artifact
hashes, requires every substantive Topic/Concept/Relation claim to resolve to
Canonical Evidence, preserves preferred labels and source aliases as Terms,
and exposes deterministic graph and Knowledge Diff views without semantic
promotion. Practice knowledge remains represented by its source Concept records;
Integra does not invent a separate identity or classification.

### R9B — Media Integration

Expose VideoText media recipes and verified derivative outputs without changing
knowledge truth.

### R9C — Cross-navigation

Prove bidirectional UI navigation between knowledge entities, exact source
locators, Topic ranges, and media clips.

### R10 — Obsidian and OneDrive Publishing

Implement versioned package preview; deterministic Markdown, JSON, DOCX, PDF,
SRT, audio, and video export; the bounded one-way Obsidian export;
filesystem-backed OneDrive publication; collision safety; queueing; integrity
verification; and recovery.

### R11 — Marketing Studio v1

As fixed by R0, implement the shared Marketing Engine and the two initial
versioned Project Playbooks with evidence-backed draft generation, QA, bulk
review, and a single publication-package gate.

### Learning Studio v1

Implement evidence-linked notes, summaries, methodology, FAQ, exercises,
tests, prerequisites, difficulty levels, and learning routes.

### Knowledge Assistant v1

Implement evidence-cited search and answers across projects, sources, Topics,
knowledge entities, media artifacts, and clips with exact round-trip navigation.

### Social Adapter Foundation and Seven Platform Adapters

After R10, implement the shared official-API contract and deterministic dry-run
evidence, then the Facebook Pages, Instagram, Threads, YouTube, Telegram,
WhatsApp Business, and TikTok adapters. Credentials, live account connection,
and external publication remain separately authorized human gates.

### R12 — Combined Beta on the Reference Mac

Run standalone and combined test matrices on the M5/16 GB reference machine,
including resource scheduling, playlist resume, document processing, migration,
Obsidian, OneDrive, every required studio, Knowledge Assistant, social-adapter
dry runs, recovery, and absence of leaked child processes.

### R13 — Security, Packaging, and Release E2E

Complete security/privacy checks, signing, notarization, dependency/license
review, immutable candidate creation, real-media E2E, rollback, and release
evidence.

### R14 — Integra 1.0 Acceptance

Accept only the R0-defined 1.0 scope after all required functional, compatibility,
resource, migration, publishing, and release gates pass. The original
applications remain available until a separate retirement decision.

### R15 — Optional Repository Consolidation

After 1.0, evaluate federated repositories, packages, subtree history import, or
a monorepo. Consolidation must have a demonstrated maintenance benefit and must
not break standalone products or history.

## 16. Completion definitions

### Core Merge complete

- Integra runs as a separate macOS application;
- accepted pinned SeminarText and VideoText components are integrated;
- local video traverses transcript, Topic, review, knowledge, and media paths;
- provenance and component identity are preserved;
- existing projects and standalone applications remain usable;
- contract, integration, migration, recovery, and real-media tests pass.

### Complete Integration Release

In addition to Core Merge:

- YouTube playlists work with resume and source provenance;
- supported documents and multi-source alignment work;
- Projects & Sources and Transcript & Topic Studio meet their complete 1.0
  contracts;
- one-way Obsidian export is deterministic and safe;
- OneDrive publication and recovery are verified;
- every required functional module and social-adapter contract is complete;
- Operations & Diagnostics meets its job, resource, Integrity, recovery, and
  process-cleanup contract;
- the reference-Mac beta and release gates pass.

### Integra 1.0 complete

The Product Owner has accepted the exact R0-defined scope, release candidate,
known limitations, migration behavior, and continued standalone-product policy.

## 17. Stop conditions

Stop and request the appropriate authority when there is:

- a Product Rule or authority conflict;
- an ambiguous source of truth or concurrent writer;
- unexplained data loss, ID drift, or provenance loss;
- an unapproved semantic promotion;
- an unapproved dataset, Gold, private-media, or credential access;
- destructive migration or user-owned file collision;
- unexpected source-project regression;
- unclear external publication consequences;
- an unpinned or changed dependency/runtime;
- a material architecture choice not already accepted.

## 18. Current implementation boundary

The current implementation stage is
[Issue #8](https://github.com/Yurielo/integra/issues/8),
`INTEGRA-R6 — Implement Core Alpha vertical slice`, with status `ACCEPTED`
after repeatable real local-video execution through the governed control plane.

The Product Owner instruction of 2026-09-10 authorizes safe implementation
along this roadmap after dependency checks. It does not bypass the protected
authorization boundaries listed in the Purpose, Development Workflow, or
machine-readable state.
