# Integra YouTube Playlist Pipeline v1

Status: `R8A_ACCEPTED`

## Outcome

R8A defines an offline-safe pipeline boundary for metadata snapshots already
obtained by a separately authorized official YouTube adapter. This reference
implementation performs no network access, account connection, download, or
publication. It deterministically discovers a collection, selects a subset,
estimates storage, processes one item at a time, checkpoints progress, resumes
without reprocessing verified completions, and compares a later snapshot.

## Identity and provenance

Collection and video source IDs derive only from provider-native IDs and their
immutable identity revisions. Playlist position, title, filesystem path and
display order are not identity inputs, while the snapshot preserves exact
title and order metadata. Each completed record binds the exact playlist
snapshot, original position, video source ID, confined artifact path,
independently measured byte count and content hash, and derived artifact ID. If
a remote item later disappears, verified local evidence is retained rather
than rewritten or invalidated.

## Execution and recovery

The plan declares `collection_kind=PLAYLIST`, `sequential=true` and
`max_parallel_items=1`, matching Operations v1 resource policy. Storage is an
explicit sum of source, extracted audio, cache, intermediate media, final
output and safety margin. A checkpoint hash covers completed and inaccessible
items plus every execution-relevant plan/snapshot field. The controller calls
the supplied checkpoint writer after every handled item, before
starting the next item. Resume revalidates both checkpoint identity and local
artifact bytes before skipping a completion; a complete checkpoint is an
idempotent no-op.

The snapshot, plan, checkpoint and refresh diff are explicit v1 JSON contracts.
Code validation additionally enforces invariants JSON Schema cannot express,
including stable IDs, contiguous positions, exact storage sums and provenance
bindings.

Unavailable items are recorded with exact snapshot provenance and do not
prevent later selected items from progressing. Refresh reports added, removed,
reordered, newly inaccessible and restored IDs independently. It never treats
remote absence as authority to delete a local artifact. Each refresh record is
recomputed from and hash-bound to both exact snapshots; retained records are
accepted only after their confined local bytes are reverified.

## Boundary

`integra_core/playlist.py` consumes sanitized metadata fixtures. Live playlist
discovery/download still requires an official adapter, capability preflight,
credentials where applicable, an Operations Job, ResourceReservation, Project
Lease for mutations, and the later Projects & Sources integration stage. R8A
does not access private playlists, credentials, source repositories, Dataset,
Gold, semantic authority, or external publication.
The integration owner must connect the callback to the Operations durable job
store; the reference module does not silently choose a project location.
