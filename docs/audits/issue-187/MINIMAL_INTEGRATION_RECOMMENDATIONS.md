# Minimal integration recommendations

These are recommendations, not implementation authorization. They preserve the
accepted source-product boundaries and do not propose a new framework.

| Priority | Recommendation | Benefit | Required bounded change / dependency | Risk and acceptance criterion | Existing issue |
| --- | --- | --- | --- | --- | --- |
| P0 | Execute #187 Stage-A VideoText ASR feasibility proof against the frozen three Russian controls | Answers whether source reuse can replace the active ASR executor | One adapter/result mapping using existing `SegmentedWhisperTranscriber`/quality services; exact selected worker closure | Must prove fresh and warm paths, valid SRT/TXT/provenance and no SeminarText call; otherwise retain SeminarText | #187 |
| P0 | Define one owner for fuzzy-loop retry and limits before implementation | Prevents nested retries, lost speech and false claims of recovery | Contract only; reuse existing detector first | Distinguish trigger, false-positive, safe-failure and actual recovery | #187 |
| P0 | Add VideoText-topic-to-Process mapping only after ASR proof | Reuses existing topic capability without changing semantic authority | Bounded adapter over cue IDs/times and `REVIEW_REQUIRED` output | Review/save/reopen keeps original machine provenance; no K1/K2 change | #187 |
| P1 | Re-run executor-sensitive lifecycle cases after the swap | Preserves Process reliability while avoiding duplicate lifecycle code | Existing Integra JobStore/reuse/cancel/timeout tests | No orphan, stale-running, retry or partial-failure regression | #161, #187 |
| P1 | Stabilize BookText artifact adapter v1 | Lets Integra reuse BookText fidelity instead of recreating OCR/review features | Versioned output carrying block IDs, regions, assurance/review state, assets and revision hashes | Validate complete coverage, idempotent import/reopen and exact source navigation; no Knowledge acceptance | BookText BT-02/BT-07; Integra #113 follow-on |
| P2 | Update the architecture/ownership matrix after factual proof | Prevents plans from being mistaken for active runtime | Documentation only, after exact evidence | Clearly separates current and target paths | #187 |

## Explicit non-recommendations

- Do not remove, unpin or retire SeminarText before `VIDEOTEXT_ONLY_PROCESS_PROVEN`
  plus a separate Product Owner decision.
- Do not rewrite VideoText or SeminarText in Integra languages.
- Do not make VideoText the owner of Concepts, Relations, Canonical Evidence,
  Canonical Knowledge, human semantic authority or publication.
- Do not implement BookText Knowledge import, Stage 2 knowledge, or a new
  integration framework under #187.
- Do not use a fixture-only repeated transcript as a defect verdict.
