# Seminar Library read-only preview v1

Status: bounded Product Owner authorization, Issue #302. The catalog is an
Integra-owned, rebuildable **projection**, not a second canonical store.
SeminarText owns Canonical Evidence and Knowledge; VideoText owns media and
subtitles; BookText owns document extraction and OCR. Native manifests and
review decisions remain authoritative. The Four Products Architecture release
registry is not an input or output of this feature.

Run `python3 -m integra_core.seminar_library --seminartext PROJECT/sources.json
--videotext 'PROJECT/Support files/manifest.json' --booktext PACKAGE/manifest.json
--integra REGISTRY.json`. Every argument is explicit. `--exclude MANIFEST` marks
the corresponding project `EXCLUDED_BY_USER` in this preview only.
`--exclude-project OWNER:NATIVE_ID` selects one project in a multi-project
Integra registry. Excluded projects retain a status row but their sources and
artifacts are absent from the library view. The default
is `INCLUDED`. `--classify-seminar MANIFEST` explicitly classifies a VideoText or
BookText project; otherwise its classification is `REVIEW_REQUIRED`. SeminarText
`seminar.yaml` and Integra project kind `SEMINAR` supply native classification.
There is no history scan, setting write, catalog file or user-facing settings UI.

The v1 output follows `schemas/seminar_library_preview_v1.schema.json` and is
printed as sorted canonical JSON. Each input carries its SHA-256. A re-read
fails if input bytes changed during generation. The catalog hash seals all
normalized records and diagnostics. Record keys distinguish preview records;
they are never cross-product semantic or content identity. Native IDs and
revisions are preserved separately. Unknown values are `null`; absent hashes
are never inferred from filenames, paths, sizes or timestamps. An explicit
duplicate-content candidate diagnostic never merges or deletes records.
`location_identity_sha256` binds the locator string only; `content_sha256`
comes from a producer record when present. `semantic_identity` is always null:
this preview cannot assert semantic equivalence.
Rebuild bytes are identical when manifest bytes **and observed locator
availability** are unchanged. Reconnecting a drive changes an availability
observation and therefore correctly changes the preview seal.

Supported versions: SeminarText `sources.json` v1 with `seminar.yaml` metadata
and optional project Evidence manifest v2;
VideoText project manifest v8; BookText portable package manifest and document
v0.1 with exact package/document hash binding; Integra Projects & Sources
registry v1.0. Unsupported versions yield a diagnostic and no partial records.
Malformed JSON fails visibly. Local locator checks use `lstat` on every path
component, reporting missing, symlink and unsafe traversal without opening
media or following links. YouTube entries retain URL and video ID; remote
availability is unverified, and no download or local media is required.
BookText's portable source filename is retained only as provenance; its source
locator and availability remain unknown because that package does not bind a
source path.

The first stage changes no product source, installed app, user manifest,
Canonical Knowledge, semantic decision or storage policy. It does not perform
migration, managed copies, automatic deduplication or reuse. Future persistence,
project settings, broader classification or storage retention require a
separate bounded scope and applicable lifecycle gates.

Source and artifact records expose their native revision IDs when known, with
the recorded revision list for Integra sources and VideoText transcript
artifacts. Absence of a native revision is an empty list, not an invented ID.
