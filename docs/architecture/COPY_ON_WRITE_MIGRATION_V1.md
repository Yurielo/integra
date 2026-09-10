# Integra Read-only Import and Copy-on-write Migration v1

Status: `R7_ACCEPTED`

## 1. Outcome

R7 imports recognized SeminarText and VideoText schema v7 projects without
changing their directories, repositories, manifests, media, or application
state. Discovery is read-only, dry-run creates no target, execution creates a
new exclusively owned target, and validation completes before any activation.

The reference implementation is `integra_core/migration.py`. Its contract
artifacts are:

- `schemas/migration_discovery_v1.schema.json`;
- `schemas/migration_plan_v1.schema.json`;
- `schemas/migration_report_v1.schema.json`;
- `schemas/migration_rollback_v1.schema.json`.

## 2. Discovery and source authority

SeminarText is recognized by `seminar.yaml` and `sources.json` schema v1.
Every registered in-project source must resolve to a regular file below the
project root. VideoText is recognized by `Support files/manifest.json` schema
v7. A VideoText media locator outside the project is recorded as an external
reference by locator hash only and is not opened or copied by R7.

Discovery rejects symlinks, unsafe directory entries, unsupported schemas,
missing registered SeminarText sources, path traversal, duplicate native
source identities, and mutation between discovery and execution. The source
root is never used for leases, markers, history, caches, or temporary output.

The committed fixtures are sanitized structural representatives derived from
the pinned contracts at SeminarText commit
`a94936cd77cde13561c97c804ece1ac1134e01a6` and VideoText commit
`2e098d1705b6815628bee1e023f4742718eabf02`. No private project, governed
Dataset, Gold, credential, or real media is accessed.

## 3. Stable IDs and hashes

The source revision is a canonical hash of the multiset of file hashes and
sizes. It deliberately excludes absolute paths, display names, and file order.
Project and artifact IDs use the accepted UUIDv5 imported-ID policy. Therefore
an unchanged project produces the same IDs after moving or renaming its root.

The layout hash separately binds every relative path, size, and content hash.
It detects a layout change before execution without making the root path an ID
input. Every dry-run mapping binds source path, destination path, size, SHA-256,
and stable artifact ID.

## 4. Copy, validation, and activation

The target root is created with an exclusive operation; an existing target is
always `BLOCKED` with `TARGET_EXISTS_NO_OVERWRITE`. Files are opened without
following symlinks, copied into a new `source/` tree, flushed, and hashed.
Integra then writes its own project and migration manifests below `.integra/`.

Copy, rollback, and interrupted recovery each require their own exact active
Operations v1 Job, capability, host ResourceReservation, and Project Lease for
the same project, executing process identity, and source-layout precondition.
Capability preflight hashes the actual `migration_fixtures.py` worker module,
the actual `migration.py` implementation, and the resolved Python executable;
it also hashes an execution contract containing the exact argument vector used
to launch `python -m integra_core.migration_fixtures --migration-worker`.
Runtime version-probe arguments remain separately identified as probe evidence
and are not treated as execution arguments. The launch and execution contract
share one code constant, while the module entry point rejects every other
worker argument vector.
An explicit target-locator SHA-256 is checked against the plan and bound by the
Project Lease and capability preflight without making a filesystem path an ID
input. A dry-run plan by itself grants no write or deletion authority, and a
copy authorization cannot be reused for rollback or recovery.

Every action terminates its durable Operations Job. Success is recorded only
after the worker process is reaped, the reservation and Project Lease are
durably released, and a hashed action-receipt artifact passes Integrity;
worker or evidence failure terminates the Job as `FAILED` with hashed failure
evidence. A returned migration result can therefore never leave its Job in
`RUNNING`.

Successful output remains `READY_NOT_ACTIVATED`. R7 does not register it as an
active user project. Validation proves:

- the source snapshot is unchanged;
- every expected copied file exists with the exact size and hash;
- no unexpected target file exists;
- the stored project manifest and migration report match the dry-run plan;
- the original source authority remains `PINNED_ORIGIN_READ_ONLY`.

## 5. Rollback and interruption recovery

Rollback first repeats full validation, then removes only the exact expected
files and directories under the Integra-created target. Any missing,
unexpected, symlinked, or altered entry blocks deletion and preserves the
target for investigation. Source paths are never deletion candidates.

An interrupted target carries a plan-bound in-progress marker. Recovery may
remove it only when every present source or generated metadata file is exact,
every present directory belongs to the planned layout, and no unknown bytes
exist. Empty planned directories left between create/write steps are handled.
This gives deterministic recovery without using a recursive broad delete.

## 6. Compatibility and limitations

The source projects stay byte-identical, so their standalone applications keep
the same inputs they had before discovery. R7 validates recognized source
formats and performs all executable migration evidence on sanitized fixtures.
The pinned SeminarText project-add regression and the pinned VideoText
ProjectSchemaProbe (legacy open/migration through current schema v7) also pass
from temporary workspaces. R7 does not launch either GUI or open private user
projects.

R7 does not copy or resolve external VideoText media, activate migrated
projects, consolidate repositories, edit source-native manifests, migrate
OneDrive/Obsidian views, or perform semantic work. Those capabilities remain in
later accepted roadmap stages and retain their own authority gates.
