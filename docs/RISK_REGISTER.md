# Integra Risk Register v1

| ID | Risk | Severity | Prevention / detection | Stop condition |
| --- | --- | --- | --- | --- |
| IR-001 | Standalone SeminarText or VideoText regression | Critical | Pinned SHAs and cross-repository standalone CI | Any unexplained regression |
| IR-002 | Destructive source-project migration | Critical | Read-only discovery, dry run, copy-on-write, rollback | Any source mutation outside authorization |
| IR-003 | Competing writers corrupt shared state | Critical | Field ownership and Project Lease | Ambiguous owner or lease conflict |
| IR-004 | Provenance or stable-ID loss | Critical | Hashes, immutable references, round-trip tests | Missing or changed lineage |
| IR-005 | Automatic semantic promotion | High | Provisional lifecycle and explicit ReviewDecision | Machine content becomes authoritative |
| IR-006 | Credential or private-content leakage | Critical | Keychain, redaction, least privilege, secret scanning | Secret in file, log, fixture, or commit |
| IR-007 | Ambiguous or duplicated external publication | High | Preview, idempotency, status audit, no blind retry | Unknown publication result |
| IR-008 | Social API/policy drift | High | Runtime capability discovery and official-doc recheck | Unsupported scope or changed policy |
| IR-009 | OneDrive partial sync reported complete | High | Staging, hashes, physical-size check, COMPLETE last | Any incomplete or conflicting publication |
| IR-010 | Obsidian overwrites user notes | Critical | Managed subtree, ownership boundary, collision report | User-owned collision |
| IR-011 | Resource exhaustion on 16 GB Mac | High | Resource Scheduler, sequential heavy work, disk estimate | Unsafe memory, swap, disk, or process state |
| IR-012 | Dependency/model/component drift | High | Pinned identities and compatibility matrix | Unverified identity change |
| IR-013 | OCR or alignment presented as exact evidence | High | Assurance state and locator validation | Unsupported source-fidelity claim |
| IR-014 | Human-review burden grows linearly | Medium | Exception clustering, bulk decisions, reusable playbooks | Routine item-by-item gate reappears |
| IR-015 | Release cannot be restored | Critical | Versioned backup, migration report, update rollback | Failed recovery rehearsal |
| IR-016 | Licensing or notarization blocks distribution | High | R13 inventory and local-package evidence; signing/notarization remain separately gated | Unresolved license or signing requirement |
| IR-017 | Deferred feature appears implemented or blocks the ready app | High | Machine-readable deferred registry, unavailable UI state, active-chain dependency validation | Placeholder runs, claims success, or becomes an R12-R14 dependency |
| IR-018 | Governance and GitHub roadmap diverge after rebaseline | High | Stable Issue mapping, schema/validator checks, post-merge GitHub reconciliation | Mismatched ID, status, dependency, or milestone |

Risks are reviewed at the start and completion of each roadmap stage. A stage
may add evidence or mitigation, but changing accepted risk ownership or
severity requires explicit review.
