# Filesystem-backed OneDrive Publication v1

Status: `ACCEPTED`

Issue: `#63`; dependency: accepted R10.

## Boundary

This adapter consumes a fully validated immutable R10 Obsidian package and
publishes a derived managed package through a local filesystem directory chosen
as a OneDrive sync root. It does not use Microsoft Graph, credentials, a live
account, protected data, or cloud status APIs. A successful local operation is
`LOCALLY_PUBLISHED`, never verified cloud publication.

Package construction and durable staging occur under an explicitly supplied
workspace outside the synchronized directory. The adapter rejects a workspace
that is the sync root, inside it, or its ancestor. Reproducible caches and
temporary render products are not accepted as inputs; only the exact R10
managed file inventory is packaged.

## Layout and ownership

```text
<workspace>/
  onedrive-staging/<project-slug>/<version>.stage/
  onedrive-queue/<version>.json

<sync-root>/Integra/<project-slug>/
  .export.lock
  CURRENT.json
  versions/<version>/
    <managed payload>
    publish_manifest.json
    checksums.sha256
    COMPLETE.json
```

The destination version is immutable. Unknown, changed, linked, placeholder,
or conflict-copy content fails closed and is not erased or overwritten. The
same `<sync-root>/Integra/<project-slug>/.export.lock` used by R10 is acquired
with non-blocking `fcntl` locking whenever an Obsidian Vault and OneDrive target
resolve to the same managed identity. Every mutation also requires the exact
active Project Lease owned by `integra.onedrive_publisher`; expiry is checked
against the current UTC clock.

## Publication and recovery

The outside-sync stage is fully hashed and completed first. The publisher then
creates the destination version, copies only absent expected files, validates
physical regular-file size and SHA-256, and detects Files On-Demand placeholders.
It writes and verifies `publish_manifest.json` and `checksums.sha256` before
writing `COMPLETE.json` last. `CURRENT.json` is created or switched only after
the requested immutable version passes complete verification.

If the sync root is absent or reports a filesystem placeholder, the exact
package remains staged outside it and an idempotent queue record is written.
No synchronized path is created. A later authorized retry publishes from the
verified stage and removes only the exact matching queue record.

Recovery accepts only an incomplete destination whose present bytes exactly
match the verified outside-sync stage. Unknown paths, conflict-copy names,
symlinks, FIFOs or other special filesystem nodes, placeholders, changed bytes, invalid current pointers, hash/size
mismatch, or an ambiguous completion marker are preserved and reported as
failures. A complete version missing `CURRENT.json` is verified before the
pointer is repaired.

## Files On-Demand and conflict truth

The default filesystem probe explicitly treats macOS `stat.SF_DATALESS` and,
where available, portable `stat.UF_OFFLINE` flags as non-materialized. It uses
the platform's non-following extended-attribute API when available and otherwise
checks only an already proven non-symlink path. Tests cover the native macOS flag
and inject a deterministic probe against temporary local files. Conflict filenames containing
`conflicted copy`, `conflict copy`, `conflicted version`, or `conflict version`
are rejected anywhere in the managed subtree.

## Limits

- Local file presence cannot prove upload, remote durability, remote identity,
  or cloud convergence; every receipt and completion record has
  `cloud_verified: false`.
- Microsoft Graph, credentials, private OneDrive content, real synchronized
  directories, unattended external publication, and blind retry of ambiguous
  external outcomes remain outside this contract.
- The R12 native application owns user interaction and orchestration over this
  accepted service.
