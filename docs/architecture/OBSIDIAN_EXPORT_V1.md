# Managed Obsidian Export v1

Status: `R10_IMPLEMENTED`

Issue #16 implements the bounded `READY_APP_V1` one-way Obsidian export. It
does not implement bidirectional synchronization, OneDrive publication, live
external writes, or the deferred general export formats.

## Inputs and authority

The exporter consumes the exact managed Markdown output already produced by
the pinned SeminarText `project-obsidian-export` capability and validated at
the accepted R6 worker boundary. It revalidates the closed source manifest,
file inventory and every file hash. The output package is additionally bound
to the exact R9A Knowledge view and R9C cross-navigation record. Canonical
Evidence and Canonical Knowledge remain read-only source truth; exported notes
are `MANAGED_GENERATED` derived views.

`build_obsidian_package` is pure and deterministic. Its caller-supplied UTC
creation instant is part of the immutable identity, so the same complete input
produces the same version. `_meta/integra_navigation.json` retains each exact R9C target ID,
locator, action and explicit unavailable state without guessing a local path.

## Managed filesystem boundary

The only writable Vault area is:

```text
<vault>/Integra/<project-slug>/
  versions/<version-sha256>/
    <managed notes and metadata>
    publish_manifest.json
    checksums.sha256
    COMPLETE.json
  CURRENT.json
```

The caller selects an existing non-symlink Vault. Every relative output is
validated against absolute paths, traversal and symlinks. Unknown entries in
the project-managed root, an unknown current pointer, an altered immutable
version, or any source-manifest mismatch is a visible collision. No such
collision is overwritten or deleted. Files elsewhere in the Vault are never
enumerated as managed and remain user-owned.

Preview performs all deterministic package and collision checks without
writing. Every mutating publication or recovery requires the exact active,
unexpired durable Project Lease for the package and its content precondition.
Publication additionally uses one nonblocking `fcntl` target lock under
`.integra-locks`; the filesystem-backed OneDrive publisher must derive the same
lock name whenever both operations resolve to the same target.

## Atomic publication and recovery

Files are written into a version-specific `.partial` directory with exclusive
temporary files, file and directory `fsync`, exact size/hash verification, and
atomic replacement. The manifest and checksum list are verified before
`COMPLETE.json` is written last. Only then is the staging directory atomically
renamed to its immutable version and `CURRENT.json` atomically updated.

An exact existing complete version is an idempotent `UNCHANGED` replay.
Interrupted staging is never current. Recovery accepts only expected files
whose existing bytes equal the requested package; unknown, changed, or symlink
content fails closed. A verified partial tree is discarded and rebuilt under
the same lock. Receipts always state `cloud_verified: false`; local Obsidian
export can never claim OneDrive completion.

## Limits

- The current adapter input is the already validated SeminarText managed-view
  byte set; a native UI and general project-to-worker orchestration belong to
  R12.
- OneDrive publication, offline queues and Files On-Demand detection belong to
  Issue #63.
- No real user Vault, private project, credential, account, semantic decision,
  or external publication was used for R10 evidence.
