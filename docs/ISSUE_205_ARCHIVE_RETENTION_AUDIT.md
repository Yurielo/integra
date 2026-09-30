# Issue #205 archive-retention audit

This audit is intentionally metadata-first. It reads the archived Candidate
manifest and `COMPLETE.json` receipt and does **not** rehash every multi-GiB
payload. A receipt records a previous archival byte-integrity verification; the
inventory command labels its own result `METADATA_ONLY_NO_PAYLOAD_REHASH`.

## Reference-Mac inventory — 2026-09-30

`scripts/candidate_archive.py inventory --archive-root ~/Library/Application\
 Support/Integra/Build\ Archive` found 22 completed Candidate archives, 14
declared bundle digests, and 17,612,428,378 logical bytes beyond one copy per
repeated digest. The repeated groups are evidence for a retention decision,
not permission to delete:

| Declared bundle digest | Completed Candidate identities | Extra logical bytes after one copy |
| --- | ---: | ---: |
| `448e5ee0…` | 4 | 6,604,507,554 |
| `dfa6b010…` | 4 | 6,604,620,454 |
| `d05c0863…` | 3 | 4,403,300,370 |

Each archive preserves its own Candidate identity, source commit, build
timestamp, manifest digest, bundle digest, receipt status and logical app
size. Different Candidate identities can have equal application bytes because
the identity also records source/execution inputs. The current retention
contract requires both identity and actual bytes for accepted or review-pending
Candidates, and archive creation intentionally copies rather than hard-links
files. Therefore the digest groups are `RETAINED_PENDING_POLICY`, not
`STALE-SAFE-TO-DELETE`.

## Full-size copy classes

| Class | Owner/creator | Current lifecycle | Audit classification |
| --- | --- | --- | --- |
| `Build Archive/candidate-v1-*` | `candidate_archive.py create`, requested by a Candidate/recovery workflow | Published with `COMPLETE.json`; no pruning command exists | `RETAINED_PENDING_POLICY` |
| `Build Archive/retained` | PR #193 historical accepted/current recovery | Explicit accepted and pilot baseline recovery evidence | `RETAINED-CANONICAL` |
| `Recovery Archive` and `Build Archive Recovery` | historical recovery workflows | Each duplicates a completed Candidate also present in Build Archive | `RETAINED_PENDING_POLICY` |
| `Candidate Builds/topic-translation-*` | historical candidate workflow | Full Candidate duplicate with matching archived Candidate | `RETAINED_PENDING_POLICY` |
| `AI/runtimes/integra/current-build` | older local runtime workflow | No embedded Candidate manifest; current product/runtime identity is not proven by this audit | `UNKNOWN_PROTECTED` |
| `/private/tmp/integra-excel*` | pre-#206 direct low-level build calls | Unmarked legacy workspaces; PR #206 rejects a new one before materialization | see Issue #205 exact-root classifications |

## Policy finding

`docs/CANDIDATE_RETENTION.md`, accepted by PR #193, makes archive bytes
mandatory for accepted and review-pending Candidates and deliberately provides
no deletion or pruning operation. It does not define a bounded population,
retention period, a class for duplicate-byte Candidates, or an authority that
may retire archived evidence. As a result, using `--archive-root` for every
review build grows the archive indefinitely even when the compiled bundle bytes
repeat.

The next Product Owner decision must define a retention class and bound for
non-canonical review history, including whether a Candidate identity with a
previously retained equal bundle digest may retain immutable metadata/evidence
plus a reference to that byte-verified archive instead of another full bundle.
Until then, the lifecycle manager may clean only its own disposable workspace;
it must not prune or hard-link retained archives.

## New read-only inventory command

`scripts/candidate_archive.py inventory --archive-root PATH` emits the
manifest/receipt inventory above. It reports duplicates and preserves every
archive. It is suitable for a future policy-controlled retention executor to
consume after the Product Owner defines bounded classes and deletion authority.
