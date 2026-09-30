# Issue #205 — independent final retention decision review

## Verdict

**PASS for presenting the bounded historical decision package to its separate Product Owner gate. No blocking discrepancy found in the reviewed package.** This is evidence review, not deletion authority, product acceptance, promotion authority, or approval to merge PR #206. No application, archive, CURRENT, policy, or GitHub record was changed by this review.

The reviewed JSON remains `dry_run=true`, `not_executable_authorization=true`, and `SAFE_TO_FREE_NOW=0`. Automatic historical adoption/deletion remains fail closed. The absent complete approved active-pin registry is not represented as an approved empty registry. An exact owner decision must attest the reconstructed legacy ownership, finite paths and protected survivor crosswalk; it cannot implicitly retire unrelated obligations.

## Bound sources

| Source | SHA-256 |
| --- | --- |
| `docs/ISSUE_205_FINAL_RETENTION_DECISION_PACKAGE.md` | `ea9cacb39d4f5011a24601af0c3376414ea6655abd4e53868fe4872a6128b68f` |
| `docs/evidence/ISSUE_205_FINAL_KEEP_DELETE_UNKNOWN_20260930.json` — raw bytes | `f48a7b51349822bb6fbb8ae1196bedfad9f9cc357a5f11d0676e0e06a7f1c69f` |
| Same JSON — semantic decision digest | `fb25cea8c3fe7b1bc85a7226b298512bdf8b26481eb327c4b09a3b9351769cdf` |
| `scripts/build_macos_app.sh` | `b905ba56beed4a8f5fdea5819d05de1bd1498634d235c6e0cbc321063e48e6b8` |
| `scripts/test_macos_app.sh` | `bded70e8c256344412c1ae2818e1f8fd4a1d12fd4bbcaba219b5cd0a416c552c` |
| `scripts/build_macos_candidate.py` | `f6575535e529f220a2be354bb8d6b07300b559411da16fa704c76c765194b855` |
| `tests/test_native_test_admission.py` | `9d92b20d4e5f2e15aa1c1d6a6325f5f8eceb72dd6323649883253cb9132ca83a` |

Semantic digest reproduction: parse JSON, remove its top-level `decision_package_sha256`, serialize with Python `json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)`, encode UTF-8, then SHA-256. The explicit `ensure_ascii=False` is necessary to reproduce the declared digest. All eleven embedded input raw-file digests matched their saved source files. The embedded free-space investigation is an explicitly pruned supporting projection with a raw-listing location, rather than a byte-for-byte JSON projection of its source.

## Identity, scope and authority checks

- The 42 actual application objects reconcile to 7 KEEP, 30 proposed owner-gated DELETE and 5 UNKNOWN. The 30 deletion paths are unique, match exactly the JSON objects classified DELETE, end in `Integra.app`, and were not symlinks at inspection. None is a KEEP or UNKNOWN application path. Kept parent evidence/source containers may contain a proposed app deletion; the gate is app-only and never authorizes removing those parents.
- Selected survivors cover CURRENT, immediate accepted predecessor/rollback, confirmed historical recovery, retained pilot, and the three present pending proposal identities. Retiring old accepted or engineering predecessors is expressly proposed; it is not automatic inferred Product Owner acceptance or a new global pin decision.
- Index 0's stale `2b779…` references in frozen PR #204/#206 proposals are disclosed. Their source/proposal/evidence records remain; present pending copies remain KEEP. The dossier does not claim those stale proposals can promote against the newer CURRENT.
- PR #182/#183/#186 remain unresolved pending obligations. Their exact proposed Candidate identities are absent in the inventoried scope, contribute no invented bytes, and are not retired by this gate.
- Indices 36/37/38 have embedded successful full streaming verification. The dirty-source index 36 is not represented as clean source or promotable provenance. Matching application payloads do not collapse distinct manifests, Candidate IDs or source provenance.
- The two originals with 39 extra generated cache files are not called verified archives or eligible promotion inputs. Their recorded files and clean alternatives have explicit verification evidence. The inert cache archive/index and unchanged manifests preserve the incident record. Proposed retirement does not repair an immutable archive in place.
- The earlier Storage Management directory-open observation and later targeted inactive observation are both disclosed. Inactivity is time-bound evidence, requiring recheck before any separately authorized destructive transaction.

## Accounting reconciliation

All values below are bytes. They are attributed regular-file/inode allocation or logical-byte accounting, not measured APFS exclusive extents.

| Quantity | Independently reconciled value |
| --- | ---: |
| All proposed DELETE apps, logical | 66,056,344,473 |
| All proposed DELETE apps, allocated | 68,208,316,416 |
| Managed archive roots before | 75,299,602,432 |
| Managed archive DELETE subset | 59,113,291,776 |
| Managed archive roots projected after | 16,186,310,656 |
| Managed root residual metadata | 273,330,176 |
| UNKNOWN apps plus UNKNOWN residual containers/top files | 2,385,362,944 |
| Entire known scope, allocated | 87,173,058,560 |

| Managed root | Before | Projected after |
| --- | ---: | ---: |
| BuildArchive | 68,461,793,280 | 16,171,540,480 |
| RecoveryArchive | 2,282,217,472 | 7,380,992 |
| BuildArchiveRecovery | 2,282,323,968 | 7,380,992 |
| CandidateBuilds | 2,273,267,712 | 8,192 |

The full managed-copy count reconciles 33 → 7. The projected managed value includes retained metadata, not just seven app payloads. `PROTECTED_BYTES=15,964,635,136` includes selected package metadata; adding `RETAINED_METADATA_BYTES=221,675,520` gives 16,186,310,656. No metadata is charged twice. The scope also accounts for 34 tmp containers and 166 top-level files; their preserved residuals are not silently counted as reclaimed.

The stated APFS reclaim interval 0…68,208,316,416 is appropriately qualified. Shared extents and inode allocation do not establish physical reclaim. Projected free space is not a guarantee that the real reservation floor or archive caps will pass after execution. The free-space-drop investigation separates observed new swap allocation from its unexplained residual; it does not claim unproved process or snapshot causation.

## Code and tests

The native test entry point now goes through the same reserved owned workspace and supervised child path. Its output is a strict descendant of that workspace; the builder lease guard rejects the workspace root itself and existing durable applications. `PYTHONDONTWRITEBYTECODE=1` is propagated. Native mode does not publish an archive. No lifecycle bypass found in this incremental change.

Independently reran the four small native admission/cache regressions: **4 PASS**. Independently checked `git diff --check`: **PASS**. Inspected saved focused results: 24 retention + 16 governance + 28 archive + 15 lifecycle + 4 native admission = **87 PASS**. The saved full suite reports **883 run, 790 PASS, 92 skipped, 1 FAIL**. Its failure is the declared R12 builder implementation hash mismatch involving both `build_macos_app.sh` and `test_macos_app.sh`; the dossier does not label the suite green or rewrite historical declarations. No additional Candidate/native build or whole-payload hashing was performed by this reviewer.

## Remaining limits

Before any execution: an explicit scoped historical owner gate, a fresh canonical CURRENT/open-proposal and survivor verification, activity/path/inode rechecks, and a separately bounded deletion transaction remain required. Automatic legacy ownership and absent canonical pin enumeration remain unresolved. PR #206 is still unmerged; a fresh source-bound Candidate and resulting governance evidence remain blocked by the present reserve/cap conditions. Historical source/payload equality is not product acceptance. The three absent old pending Candidates remain UNKNOWN obligations.

This review evaluated the saved snapshots and bound proof logs; it did not independently repeat all application hashes or refresh live GitHub at the final report boundary. The exact reviewed digest therefore identifies a decision proposal, not a perpetual assertion about changing filesystem or remote state.

```text
PRODUCT_RULES_READ: YES
APPLICABLE_PRODUCT_RULES: PR-010, PR-011, PR-013
PRODUCT_RULE_CONFLICTS: NONE
```

PR-011's consolidated user-return notification belongs to the coordinating task; this independent role does not emit an additional completion sound.

## Supplement — exact cache recompilation

**PASS; verdict and decision scope unchanged.** Reviewed `docs/evidence/ISSUE_205_EXACT_PYC_RECOMPILATION_20260930.json`, raw SHA-256 `1c680aa3f4ea4e91999e2ed7aab9bf6351bb7dc50501c6f11585910d2f205b0e`. All 39 unique paths match the prior forensic source associations and original digests, and match the inert index and the SHA-256 of their preserved `.bin` zip entries. Every saved compilation has exit 0, original/compiled hash equality, byte-for-byte equality and unchanged source metadata. The included compiler-driver source hashes to its declared `fdf61f0edf745ea2fbd98b6a0955ca39dc69a18f85123a361d036447175a18e4`.

The driver uses `py_compile` with explicit external `cfile`, original source `dfile`, optimize 0 and TIMESTAMP invalidation; it checks recorded source hashes and inode/size/mtime/ctime around compilation. It neither imports the inspected source modules nor executes/unmarshals the original bytecode. The saved supervisor command uses a fresh owned 1 MiB reservation; removal is recorded and its named workspace was absent at review. This supports exact compiler-derived bytes. It does not identify the historical writer or restore the originals to VERIFIED archive status. This reviewer checked the evidence and preserved small inert bytes, without running recompilation or hashing application payloads again.

The decision JSON raw hash remains `f48a7b51349822bb6fbb8ae1196bedfad9f9cc357a5f11d0676e0e06a7f1c69f`; its semantic digest remains `fb25cea8c3fe7b1bc85a7226b298512bdf8b26481eb327c4b09a3b9351769cdf`. The final decision Markdown now hashes to `764d9c8c8e603ca60294ec41e636b76d095fa812d97a7d663dd7c1e303930b8f`, superseding only that Markdown hash in the original table. Classifications, accounting, source code and test claims are unchanged.

## Supplement — manifestless relation correction

**PASS; deletion eligibility and execution limits unchanged.** Compared the corrected decision JSON to its committed predecessor. After removing only the four relation fields (`current_relation`, `accepted_relation`, `rollback_relation`, `recovery_relation`) on object indices 33, 35, 39, 40 and 41, and the top-level semantic digest, the parsed JSONs are exactly equal. All five objects remain UNKNOWN and now explicitly carry `UNKNOWN_NO_MANIFEST_BOUND_IDENTITY` for each relation. No directory-name-based nonidentity or nonrole assertion is justified for these objects. The exact 30 deletion paths, 7 KEEP objects, all accounting values, source-code and test evidence remain unchanged. The Markdown diff changes only the semantic digest and adds the explicit manifestless-identity limitation.

The latest authoritative review bindings supersede the earlier decision-document bindings:

- Decision JSON raw SHA-256: `c35f1cebd42040c66bddd67d2808b1aeca827d419c227ef69e015535736eb26c`.
- Recomputed decision JSON semantic SHA-256: `1100c4367510e7f005e3dd3b802cf40232c2dfc6c0c750aaf58ba643743126b1`.
- Decision Markdown raw SHA-256: `9ca3f7710d0436d8667b3e1b732ba1ebcf8e5f5438b655b88978219084019799`.

This is a factual uncertainty correction, not an approval to delete UNKNOWN objects or an expansion of the historical gate.
