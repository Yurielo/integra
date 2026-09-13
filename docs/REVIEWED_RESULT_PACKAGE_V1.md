# Reviewed-result export package v1

Runtime integration plan, Stage 2; implementation follow-up to issue #119.

The package is an Integra-owned projection of an already persisted human
review result. Building it does not accept topics, change source boundaries,
create Canonical Knowledge, or publish to an external destination.

## Contract

`integra.reviewed_result_package`, schema version `1.0`, is distinct from the
legacy `integra.obsidian_package`. It contains immutable file inventory hashes,
project/source identity, deterministic package/version identity, result kind,
and explicit result/provenance bindings. It does not impersonate an R9A
Knowledge view or require invented R9C media derivatives or a second source.

- `CANONICAL_KNOWLEDGE_V1` packages the real pinned compiler result and its
  verified derived-view inventory.
- `REVIEWED_FRAGMENTS_V2` packages the real exact-fragment review result and
  readable Markdown. This is not Canonical Knowledge.
- Evidence, review package, decisions, result receipt and relevant timelines
  remain byte-bound. Portable metadata does not expose local absolute paths.
- Source IDs and exact word/time locators remain unchanged. Export does not
  claim that the source media is available on another machine.

## Runtime path

macOS source results → **Подготовить проверенный пакет для Obsidian / OneDrive**
→ `build-reviewed-package` → reviewed-result builder/validator → immutable
Integra project package → persisted `package_dir`.

The existing publication chooser revalidates packages from completed runs.
It sends the selected `publication_target` explicitly: `obsidian` or
`onedrive`. Preview performs no publication. Only the subsequent user action
invokes publication.

The managed transport dispatches the new exact artifact type to its dedicated
validator. The legacy R10 package validator is unchanged. Staging, leases,
collision protection, immutable versions and completion markers are reused.
V1 derived notes are checked against the actual pinned SeminarText compiler
and renderer, including coverage and unavailable source-resolver states.
This verification requires the same preflighted Python/component runtime as
review; it must fail closed when that runtime is unavailable. It is not an
independent replacement compiler implemented in Integra. V2 fragment checks
do not require canonical compilation.
OneDrive wraps the reviewed package using its existing filesystem contract,
retains the complete reviewed manifest in `_meta/integra_reviewed_package.json`,
and revalidates its source bindings. Repeated preview/publication derives the
same immutable version from the source package timestamp.

OneDrive completion means local filesystem publication only, not successful
cloud synchronization. No live user Vault or OneDrive publication is part of
automated verification; tests use temporary synthetic destinations.
