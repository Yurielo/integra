# Integra Architecture and Authority Model v1

Status: `R0_ACCEPTED`

## 1. Logical architecture

Integra uses a local control-plane architecture rather than copying source
application internals into a new monolith.

```text
macOS UI
  ↓
Integra control plane ── Project Registry / Job Queue / Project Lease
  ├── SeminarText worker adapter ── evidence, timeline, topics, knowledge
  ├── VideoText worker adapter ──── media preparation and recipes
  ├── source adapters ───────────── local files, YouTube, documents, OCR
  ├── review service ────────────── exception packages and ReviewDecision
  └── Publishing Hub ────────────── files, Obsidian, OneDrive, social APIs
             ↓
      versioned artifact store, manifests, hashes, logs, and recovery points
```

The initial worker boundary is a controlled local process with structured
artifact exchange. A network service and a rewrite of SeminarText in Swift are
not prerequisites. Concrete UI framework, storage engine, and process transport
choices remain R3/R4 implementation decisions provided they satisfy the
versioned contracts and resource limits.

R3 fixes that boundary as the dependency-free local JSONL contract documented
in [`WORKER_PROTOCOL_V1.md`](WORKER_PROTOCOL_V1.md), with exact component,
artifact, compatibility, job, cancellation, retry, timeout, and resume rules.
R4 proves the boundary against both pinned components with read-only inputs and
separate hashed output, as recorded in `state/adapter_spike_v1.json`.

R5 fixes technical integration defaults per capability rather than choosing one
source application as a universal winner. VideoText is primary for media
preparation, ASR, translation, cache, and recovery; SeminarText is primary for
word alignment and Topics; review and quality validation are composed along the
accepted ownership boundary. The exact replay evidence, retained fallbacks, and
limitations are recorded in `state/capability_benchmark_v1.json`. These choices
do not claim semantic superiority and do not authorize semantic acceptance.

## 2. Authority model

### Factual state authority

Execution-time Git, GitHub, component, runtime, artifact, filesystem, and
official external-platform facts. Facts are reverified before use; historical
reports never override them.

### Authorization authority

The latest explicit Product Owner instruction applicable to the exact action.
Authorization is bounded by action, repository, data, external system, and
time/state preconditions. Silence and logical next steps are not authorization.

### Governance authority

Accepted files on Integra `main`, led by `docs/PRODUCT_DEFINITION.md`, this
architecture, `docs/INTEGRA_PLAN.md`, `DEVELOPMENT_WORKFLOW.md`, and
`state/integra_state_v1.json`. A feature branch proposes governance; it does not
become accepted truth before merge.

### Semantic authority

Machine output may propose and organize meaning. Authoritative semantic state
requires a supported explicit human ReviewDecision. Technical validation proves
structure and lineage, not semantic truth.

## 3. Ownership direction

| Entity | Authoritative owner | Integra behavior |
| --- | --- | --- |
| Integra project index and orchestration | Integra | write under Project Lease |
| Source identity and fingerprint | Contract-selected single owner | index/reference |
| Machine transcript artifact | Selected pinned ASR component | reference/version |
| Canonical Word Timeline | SeminarText | read/reference |
| Topic Draft | Selected Topic component | propose/reference |
| ReviewDecision | Governed review contract | apply deterministically |
| Canonical Evidence and Knowledge | SeminarText | read/reference |
| Media recipe and artifact | VideoText | read/reference |
| Publication package and status | Integra Publishing Hub | write/version |
| Managed Obsidian view | Integra exporter | controlled one-way write |
| OneDrive publication | Integra Publishing adapter | stage/verify/reference |

The accepted field-level matrix and stable ID namespaces are defined in
[`DATA_OWNERSHIP_AND_PROJECT_LEASE.md`](DATA_OWNERSHIP_AND_PROJECT_LEASE.md)
and `state/data_ownership_v1.json`. R3 messages must use those identities and
cannot introduce a competing authoritative writer.

## 4. Project Lease

Every mutable project operation carries project ID, mutable entity, writer
component, process instance, operation ID, acquisition time, expiry, heartbeat,
and relevant readers. Only one writer may own a mutable entity. Stale-lock
recovery verifies both process and artifact state and fails closed on doubt.
The accepted schema is `schemas/project_lease_v1.schema.json`; the reference
policy implementation uses per-entity file locks, atomic records, writer
identity, and monotonic lease generations.

## 5. Trust boundaries

- Source repositories and projects are external protected systems.
- Worker responses are validated against pinned contract and component identity.
- Artifact store writes use staging, checksums, atomic promotion, and recovery.
- OneDrive and Obsidian share no concurrent writer target.
- Social platforms are external irreversible-action boundaries using official
  APIs, protected credentials, preflight, idempotency, and explicit status.
- Logs redact credentials, cookies, personal data, and private content by
  default.

## 6. Dependency direction

The UI depends on Integra domain contracts. The control plane depends on
adapter interfaces, never on source-project internal paths. Adapters depend on
pinned source components and translate into versioned Integra artifacts.
Derived studios consume evidence references and cannot write canonical truth.

## 7. Failure behavior

Unknown contract versions, component drift, hash mismatch, lease conflict,
partial cloud sync, ambiguous publication status, missing provenance, or source
regression are visible failures. Integra does not silently retry irreversible
operations or report partial artifacts as complete.
