# Integra Data Ownership, Stable IDs, and Project Lease v1

Status: `R2_ACCEPTED`

## Ownership rule

Every authoritative field has exactly one writer selected either statically or
from an immutable pinned origin record. Integra indexes component-owned data;
it does not acquire write authority by copying it. The machine-readable matrix
is [`state/data_ownership_v1.json`](../../state/data_ownership_v1.json).

New Integra ReviewDecisions are owned by the review service. Imported decisions
remain immutable records owned by their origin contract; the Integra record
links to them instead of rewriting them. Obsidian and OneDrive outputs are
derived managed views, never canonical knowledge writers.

## Stable identifiers

Integra IDs use `urn:integra:<namespace>:<uuid>`. Imported IDs are UUIDv5 values
derived from four immutable inputs: namespace, source component, native ID, and
source-revision SHA-256. Display names, paths, and ordering are forbidden ID
inputs. An imported record therefore keeps the same ID after a move or rename.

Collision handling is fail-closed:

- same ID and same identity hash: the same identity;
- different IDs and the same identity hash: record an explicit alias;
- same ID with different hashes, or different IDs with different hashes where
  identity was expected: hard conflict requiring investigation.

## Project Lease

The schema is [`schemas/project_lease_v1.schema.json`](../../schemas/project_lease_v1.schema.json).
A lease binds one project and mutable entity to one writer process instance and
operation. It includes acquisition, heartbeat, expiry, artifact precondition,
readers, and a monotonic generation.

Lease records live only under an explicitly configured Integra-owned lease
directory. Per-entity guard files and atomic replacement serialize updates.
The source-project directory is never a lease store and is never modified by
lease acquisition.

An expired timestamp alone never releases a lease. Recovery is permitted only
when the original process is proven not running and the artifact revision/hash
is proven unchanged. `UNKNOWN`, a live process, or changed artifact denies
recovery. The recovery action records `VERIFIED_STALE_RECOVERY`; records are
retained rather than silently deleted.

Heartbeat and release require exact lease ID, writer identity, and generation.
This prevents an old process from releasing or extending a newer lease.

## Simultaneous access

- Multiple readers may be recorded while one writer owns the mutable entity.
- A second writer always fails with a visible conflict.
- Different mutable entities within one project may hold independent leases.
- Source applications remain authoritative for their owned fields and remain
  independently runnable.
- R3 protocol messages must carry the stable entity ID, operation ID, component
  identity, lease ID/generation where writing, and artifact precondition hash.
