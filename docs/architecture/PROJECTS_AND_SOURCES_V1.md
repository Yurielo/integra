# Integra Projects & Sources v1

Status: `ACCEPTED`

Issue: `#47`

## Contract

Integra maintains one deterministic control-plane registry for seminar,
course, series and event projects. Project identity is derived from an
immutable caller-owned key and project kind; names, paths and ordering never
participate in identity. Explicit rename and lifecycle transitions are retained
as ordered immutable history events.

Sources have stable identity, current lifecycle and an ordered revision ledger.
Each revision binds its observation time, source hash or remote metadata hash,
availability, exact provenance hash and the preceding revision in an ordered
hash chain. Relationships between projects and
sources are reciprocal and validated. Reopening a serialized registry or
refreshing an unchanged source cannot duplicate either identity.

The module emits and validates canonical registry bytes but does not introduce
a second mutable store. A control-plane caller persists those bytes through the
accepted Project Lease and atomic artifact mechanisms from R2/R6.
The accepted registry artifact hash is the external precondition that prevents
a complete history rewrite; the internal revision chain detects truncation,
insertion and reordering before that accepted head.

Supported source families are local video/audio, individual YouTube videos,
YouTube playlists, PDF, PPTX, DOCX, TXT, Markdown, images and scans. The
registry consumes accepted R8A playlist discovery and R8B document extraction;
it does not download remote media, re-extract documents or perform OCR. A
standalone YouTube video uses exactly the same stable per-video source ID as the
same video inside a playlist and remains independently attachable/resumable.
Playlist membership is a separate immutable relationship record binding the
R8A collection and snapshot IDs, snapshot hash, item position, title,
availability, duration and storage estimate. One video can therefore belong to
multiple playlists without changing its identity or losing membership evidence.

## Failure and authority

Unavailable remote content remains a visible `UNAVAILABLE` source revision;
unsupported or missing local input raises a visible error. Identity, hash,
lineage, reciprocal-reference and record-seal mismatches fail closed. No
provenance is inferred when evidence is absent.

Local audio/video classification requires both a supported extension and its
container signature (ISO BMFF, Matroska, RIFF/WAVE, MP3, FLAC or AAC). This is
an indexing preflight, not a claim that every codec stream has been decoded;
R6 remains the governed media-processing proof.

This module reads local source bytes only to fingerprint explicitly supplied
audio/video. It never changes source files, source projects or source
repositories. Live network access, credentials, private sources, destructive
migration and semantic acceptance are outside v1. Registry metadata is
technical control-plane state with no semantic authority.
