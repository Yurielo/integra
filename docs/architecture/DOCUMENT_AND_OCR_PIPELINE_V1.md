# Integra Document and OCR Pipeline v1

Status: `R8B_ACCEPTED`

Issue: `#11`

## Boundary

R8B is a deterministic local extraction boundary for PDF, PPTX, DOCX, TXT,
Markdown, images, and scans. It does not contact cloud services, open private
projects, or grant an OCR engine semantic authority. Every record is bound to
the exact source SHA-256 and remains
`PROVISIONAL_MACHINE_EXTRACTION`.

The v1 reference implementation directly reads UTF-8 text, safe OOXML ZIP
parts, and unfiltered PDF text operators. Compressed or otherwise unsupported
PDF text encodings fail to an explicit OCR-required state; they are never
presented as successfully extracted native text.

## Locators and fidelity

- TXT and Markdown retain exact UTF-8 characters and character offsets.
- DOCX retains paragraph order and character offsets.
- PPTX retains slide order, notes where present, and slide-local character
  offsets.
- PDF retains page and character locators for supported native text.
- OCR output requires a normalized page/image region plus character offsets.
- Source, text block, embedded-media, and complete record hashes are verified.
- Stable source identity is byte-derived and excludes path and display name.

Image and scan sources are classified as `SCAN`. A PDF, presentation, or DOCX
with visual content and insufficient native text, or a PDF with unsupported
text encoding, is `IMAGE_HEAVY`. Both states require either an explicit OCR
result or the visible status `OCR_REQUIRED`. Native fragments may be retained
alongside OCR evidence, but visual content is never represented as ordinary
complete text.

## Embedded media

DOCX and PPTX media parts and supported PDF image streams receive independent
content hashes, source-revision-bound artifact IDs, part locators, and parent
locators. Materialization is allowed only into a new Integra-owned directory;
existing paths are not overwritten. Every ancestor is traversed by descriptor
with no-follow semantics, and each written file is reproduced from and verified
against the immutable source bytes.

## OCR adapter

The reference pipeline accepts a local OCR provider callback with exact source
hash, format, media type, page count, reason, and source bytes. Results must
contain a valid page/image index, normalized region, non-empty text, and numeric
confidence in `[0, 1]`, plus exact component implementation and model hashes.
All pages/images requiring OCR must be covered. Invalid, empty, partial,
out-of-range, or structurally unknown results fail closed.

No OCR executable, model, account, network endpoint, credential, or paid
service is selected by R8B. Projects & Sources v1 may later bind a supported
local implementation through the accepted worker/operations contracts without
changing this evidence format.

## Security and limits

- Source files are read with no-follow semantics and rechecked during reading.
- PNG structure, chunk checksums, dimensions and bounded decoded scanlines are
  validated before an image is accepted as a scan source.
- OOXML member names, duplicates, and expanded sizes are bounded; XML entities
  and doctypes are rejected.
- The dependency-free PDF reader intentionally supports only simple,
  unfiltered, non-nested literal-string text streams, including standard
  escapes. Nested literal strings, mixed tokens, or unsupported encodings route
  to OCR rather than drop content or guess.
- No source application, Dataset, Gold, account, or external system is accessed.
- Cross-source alignment remains R8C; project registration remains Projects &
  Sources v1.
