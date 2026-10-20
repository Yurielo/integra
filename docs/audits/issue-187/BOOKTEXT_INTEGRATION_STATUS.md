# BookText integration status

## Implemented bounded integration

Integra has a real local OCR path, not only a planning document:

- `scripts/build_macos_app.sh` verifies the exact BookText commit
  `46396649214275eb18054b670a842bace02d02e1`, copies `booktext.py`, builds
  the Vision helper and records a packaged runtime manifest.
- `integra_core/booktext_runtime.py` verifies the packaged bytes, local Surya
  model/tools and invokes `workers/booktext_ocr_worker.py`.
- `application_runtime.execute_run` invokes that adapter for selected/required
  OCR and records outputs beside the Integra document artifact.
- The adapter verifies source SHA-256, selected pages/exclusions and a
  non-empty BookText manifest before exposing results.

This qualifies as **bounded OCR reuse**, and not as whole-BookText integration.

## What BookText can provide independently

The audited BookText source implements OCR for PDF/DjVu/images, native text
extraction, Surya and independent Apple Vision QA, page/block/table/figure
provenance, review queues and reversible decisions, Canonical Document Model
(CDM), publication exports, a source-anchored translation layer, and a local
JSONL machine protocol. These contracts are described in its `README.md`,
`docs/architecture/CANONICAL_DOCUMENT_MODEL.md` and
`docs/architecture/MACHINE_PROTOCOL.md`.

## Exact integration gap

`docs/INTEGRA_OCR_ADAPTER_CONTRACT.md` in BookText is explicitly **DRAFT** and
states that it is not a Knowledge import. The Integra worker currently reduces
BookText output to page-level `unit_index`, text and aggregate confidence. It
does not carry BookText's normalized block region, block-level reading order,
review-decision layer, CDM, table/figure asset links, translation revision
lineage or full output manifest into an accepted Integra import contract.

Consequently the following statements would be inaccurate today:

- that Integra receives exact BookText page-and-region coordinates for all OCR
  blocks;
- that BookText review states are represented in Integra Knowledge;
- that illustrations/tables/CDM or BookText translations are imported;
- that a document can travel BookText -> Integra -> Knowledge with proven
  duplicate/revision behavior; or
- that DjVu is supported through the current Integra document contract.

## Readiness table

| Interface | Status | Evidence / remaining condition |
| --- | --- | --- |
| Pinned local BookText OCR invocation | Implemented | `booktext_runtime.py`, packaged build, Issue #113 history |
| Integra document source hash and pages selection | Implemented | `application_runtime.py`, `capabilities.py` |
| Provider/model provenance | Partial | runtime manifest and output hashes exist; adapter candidate mapping remains draft |
| Page/region/block fidelity | Partial | Integra accepts normalized regions in principle; worker does not export them per block |
| OCR assurance/review state | Partial | BookText has it; current Integra output exposes only bounded QA status |
| Document structure, tables, illustrations | Not integrated | BookText CDM/exports are standalone |
| Document translation | Not integrated | BookText derivative translation remains standalone |
| Knowledge import/reopen/idempotency | Not proven | BT-07 in BookText development plan; out of #187 implementation scope |

## Minimal future boundary

Do not copy BookText's OCR/review/CDM logic into Integra. Stabilize one
versioned machine/artifact adapter that carries source revision, page/block
IDs, normalized regions, raw machine text, provider/model hashes, assurance
and review state. Then prove validation, idempotent import, revision history,
exact page/region navigation and no semantic promotion. This is a separate
Document/Knowledge task, not a change authorized by Issue #187.
