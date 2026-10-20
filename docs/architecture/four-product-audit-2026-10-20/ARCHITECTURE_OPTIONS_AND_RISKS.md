# Architecture options and risks

Status: **adapter-first direction accepted for planning; implementation remains a PROPOSAL / advisory comparison**. FACT basis: [four-product audit](FOUR_PRODUCT_ARCHITECTURE_AUDIT.md). Costs below are relative engineering estimates, not delivery commitments or measured financial forecasts.

The accepted planning boundary is versioned sidecar manifests with explicit read-only handoff/import. Any discovery index is opt-in and rebuildable metadata, not physical storage or an automatic cross-project discovery/copy/reuse/retention mechanism. The acceptance does not authorize M1–M7 execution, a shared core, migration, release or semantic promotion.

## FACT — constraints shaping the choice

There are functioning standalone products, materially different native data models, accepted timing and semantic contracts, Python/Bash/Swift boundaries, existing local worker protocols and an Integra control plane. VideoText already reuses a SeminarText ASR snapshot; BookText, VideoText and Integra already use the same installed TranslateGemma digest through different adapters. Cross-product caches and resource leases are not uniformly shared. Current application pins lag canonical source mains. Rebuilding accepted functionality or automatically upgrading all pins would introduce risk without proving user benefit.

## INFERENCE — strategy comparison

| Criterion | A. Independent execution paths + interoperability adapters | B. Shared transcription/translation libraries | C. Integra orchestration + standalone product adapters |
| --- | --- | --- | --- |
| Initial implementation cost | Lowest: envelope/mapping and conformance work | Highest: untangle packaging, language/runtime, profiles, release coupling | Moderate: reuse existing control plane, complete adapters and discovery |
| Maintenance | Duplicate request/cache policy can persist | Lowest only after stable shared contracts; central changes affect all consumers | Shared job/resource/artifact policy; native engine maintenance remains |
| Correctness | Strong isolation; mapping can lose meaning unless strictly validated | Consistent shared primitive; one defect can affect every product | Explicit capabilities/provenance; orchestration cannot repair invalid native artifacts |
| Regression risk | Lowest immediate risk, bounded adapters | Highest during extraction and model/profile unification | Moderate, controlled by exact pins and standalone regression gates |
| Migration complexity | Sidecars/copy-on-write, little native churn | Dependency/API/data migrations across Python/Swift/shell | Additive imports/handoffs; avoid mandatory project migration |
| Runtime resources | No savings unless reuse/admission is added | Shared library does not by itself share model residency or inference | Existing scheduler can coordinate participating jobs; standalone participation still needs a common lease |
| Standalone independence | Strong | Strong only if no central service/runtime is mandatory | Strong only if orchestration is optional and contracts are usable independently |
| Extensibility | New adapter per capability/profile | Good for stable common primitives, poor for forced universal text model | Good for new consumers and workflows, with governance overhead |
| Governance impact | Low; native owners retained | Material shared component owner/release authority needed | Aligned with accepted Integra direction, but source ownership must remain explicit |
| Main failure mode | Permanent divergence and duplicate inference despite common model | Premature abstraction, forced migrations, coupled release failures | Integra becomes mandatory platform or a second canonical truth store |

## PROPOSAL — staged A + constrained C, selective B only after proof

Choose **artifact interoperability through existing adapters first**, with **optional Integra orchestration using its existing contracts**. Preserve SeminarText ASR reuse already present in VideoText. Keep accepted TranslateGemma adapters during the transition. Add reliable source/artifact identity, review-scope exchange and cooperative resource admission. This produces observable savings without an engine rewrite.

Evaluate a small shared provider/checkpoint library only after equivalent profiles have two verified consumers. Do not extract BookText CDM as a universal text model, select VideoText-only ASR merely to satisfy a product label, or create another translation daemon. #187 remains a proof/owner boundary: a VideoText wrapper that invokes SeminarText cannot prove “no SeminarText dependency.”

This recommendation has a reversible sequence: versioned sidecar export → explicit read-only import → future scope-approved compatible reuse → optional orchestration → measured extraction. A step is successful only when invocation counts, handoff fidelity, review preservation and user outcomes improve. An index may assist an opted-in route but cannot replace physical native ownership or make the preceding actions automatic. Elegance alone is not a gate.

## FACT / INFERENCE — resource implications on the 16 GB target

The user specifies MacBook Air M5 / 16 GB; this audit read `hw.memsize=17179869184`. CPU/model SKU was not independently benchmarked. The Ollama inventory reports TranslateGemma ~3.30 GB stored bytes and Gemma3:4b ~3.34 GB; these are **not peak RAM estimates**. Whisper, KV/context state, OCR page images, FFmpeg buffers, apps and macOS add memory. No quantitative safe concurrency ceiling can be inferred from weights alone.

| Workload | Observed implementation | Planning implication |
| --- | --- | --- |
| Whisper + VAD | Existing large-v3/Silero paths, chunking, bounded local threads | Reuse one result; serialize heavy recognition and avoid duplicate model processes |
| TranslateGemma / Gemma / Ollama | Shared daemon, independent adapters and residency policies | A common model file is not common job ownership; serialize heavy requests and preserve another app's session |
| BookText OCR / vision | Surya CLI/llama-server, Apple Vision QA, optional Gemma vision | Bound pages and contexts; OCR and visual-model admission must join the same resource contract |
| FFmpeg | Preparation, renders, mixing and conversion | Distinguish lightweight probing from heavy transforms; disk needs include intermediates and outputs |
| TTS | Future multilingual production not verified | Introduce as heavy-model until measured; segment/checkpoint before full-video rendering |
| Several apps open | UI may be idle while workers/models remain resident | Inventory processes/residency and durable reservations; open windows alone do not imply capacity |

Integra's existing `ResourceScheduler`/`ResourceReservationStore` already enforce one heavy-model and one heavy-media slot, deny Whisper/Ollama overlap and heavy FFmpeg/Whisper overlap, serialize playlist items, and require known resource/process/disk/lease truth. Its JobStore and Project Lease are different mechanisms. Do not introduce a new orchestration framework.

## PROPOSAL — minimal shared resource coordination

Adapt that existing file-lock/reservation design into a small opt-in versioned per-user host protocol usable while Integra is closed, without the Integra UI, a daemon or a server. Admission includes job/capability/model class, estimated memory/disk, exact PID/start token, operation, lease generation and cancellation owner. Atomic reservation precedes model load. Unknown pressure or an unresolved owner blocks a new heavy job; light UI/metadata work remains available. Ownership-based residency release replaces family-name unloading; a model name alone never permits another application's Ollama residency to be unloaded. Expiry alone is never proof of dead ownership.

Start conservatively with serialized heavy phases; allow more overlap only after bounded measurements on the actual Mac. Record cold/warm latency, peak process-tree RSS, system pressure/swap, temp disk, model/request counts and cancellation recovery. Keep per-product retry/process/temp cleanup and accepted archive retention. No cache-cleanup rule may delete retained candidates or user sources. Cross-app protocol participation is new work, not a claim about current enforcement. OCR/TTS workload identities need an explicitly versioned scheduler extension where the current closed enums do not support them; alternate names must not bypass existing exclusions.

## FACT / INFERENCE / PROPOSAL — risk register

| Risk | Evidence / consequence | Mitigation and milestone |
| --- | --- | --- |
| False source reuse | SeminarText path marker; VideoText size/mtime; BookText unordered collection hash | Content/ordered-member identity and negative tests before shared reuse, M1/M2 |
| Cross-app model eviction | VideoText unloads matching model families globally | Cooperative ownership lease, preserve foreign jobs; M1/M2 |
| Loss of raw timing | Directed tokens and padded selected ranges differ from playable intervals | Preserve #129/#131/#132/#133 and later #138 clarification; typed timing mapping, M1 |
| False semantic acceptance | Technical QA/source enum/release acceptance mistaken for per-artifact human decision | Scope-bound attributable receipts, PR-001/002/012; M2/M4/M6 |
| Document policy noncompliance | BookText handwriting exclusion has bypass/fallback paths | Repair/verify accepted policy, not relax it; M1 |
| Provenance reduction | Integra BookText bridge reduces rich block/review/CDM output | Lossless adapter and exact page/region references; M2/M6 |
| Hidden executor dependency | VideoText ASR wrapper and lagging Integra pins | Record full dependency closure; #187 cannot claim independence; M0/M1 |
| Stale governance/acceptance | Older R14 labels, newer CURRENT and withdrawn K2 candidate | Exact-scope baseline table; preserve historical states; M0/M1 |
| Common core regression | Premature extraction removes profile-specific behavior | Extraction only after conformance/real parity and reversible adapters; M4/M7 |
| Resource exhaustion / disk growth | Multiple model stacks and retained app copies | Existing admission/retention policy, measured bounds, no extra daemon; M1/M7 |
| Unbounded retries | Provider retry × quality retry × orchestrator retry | One declared budget owner and finite stage limits; M4 |
| Overstated multilingual readiness | EN↔RU evidence does not prove all languages or dubbing | Per-profile/language/voice acceptance, M4/M5 |
| Duplicate roadmap/semantic stores | #257 and four source plans diverge | Preserve #257 and CURRENT/K1/K2 gates; one non-blocking coordination proposal and source-native authority; M0/M6 |
| Privacy/consent/external publication | Source content, model prompts, cloned voices or destination actions | Local data by default, explicit consent/scope and separate publication receipts; M5/M6 |

## UNVERIFIED and decision boundary

No benchmark in this audit proves a numeric performance gain, memory budget or total implementation duration. Savings are expected from avoided work and must be measured through call-count and resource evidence. The owner has accepted the adapter-first planning direction and its clarification boundaries; actual shared-storage participation, automatic reuse, implementation prioritization, releases and semantic decisions retain their applicable future gates. See [decisions](PRODUCT_OWNER_DECISIONS.md) and [roadmap](INTEGRATED_DEVELOPMENT_ROADMAP.md).
