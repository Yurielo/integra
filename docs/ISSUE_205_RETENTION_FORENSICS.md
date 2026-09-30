# Issue #205 — independent retention forensics, 2026-09-30

Authority: the Product Owner's bounded retention implementation under Issue
#205 / PR #206. This evidence role wrote only this report and
`docs/evidence/ISSUE_205_RETENTION_FORENSICS_20260930.json`. It did not execute
archived bytecode, launch applications, build Candidates, delete or repair
archives, change CURRENT, restore a runtime, or select a new canonical archive.

## Two retained archive integrity incidents

| Original archive | Detected additions | Fresh recorded-file comparison | Disposition |
| --- | --- | --- | --- |
| Build Archive / `a6d470…` / `2efeff23…` | 38 `.cpython-314.pyc` files, 471,558 logical bytes; six new `__pycache__` directories | All 29,646 recorded files and 32,497 recorded entries match recorded checksums, sizes, modes and types; regular files have one link | `QUARANTINED_RETAIN` |
| Build Archive / `8be1ad…` / `c4dc1553…` | One `.cpython-313.pyc`, 2,564 logical bytes; one new `__pycache__` directory | All 29,649 recorded files and 32,500 recorded entries match recorded checksums, sizes, modes and types; regular files have one link | `QUARANTINED_RETAIN` |

The two original comparisons hashed 4,406,198,631 bytes in total, with one
600-second process limit per archive. They took 4.664 and 5.131 seconds. This
establishes additions-only drift relative to the recorded regular-file and
directory inventory at the time of comparison. No recorded-file mutation was
detected. It does not identify the writer.

All 39 extra files were read as bytes. Their 16-byte headers are timestamp-based
(`flags=0`); all header source timestamps and sizes match the associated `.py`
files. The 39 source SHA-256 values also match the original recorded inventory.
Magic `2b0e0d0a` matches the installed CPython 3.14.6 interpreter, and
`f30d0d0a` matches CPython 3.13.15. All extra files' observed birth times follow
the original COMPLETE publication. The JSON retains each SHA-256, header,
source association, birth time and modification time.

This is consistent with Python import-cache generation after archival
completion. Cache headers and timestamps do not establish the writer process,
the initiating user action, or bytecode semantics. No bytecode was unmarshalled
or executed. The writer remains `UNPROVEN`.

## Existing alternates are freshly verified

| Existing location | Candidate | Bundle | Manifest | Result |
| --- | --- | --- | --- | --- |
| Recovery Archive | `a6d470…` | `2efeff23…` | `4c9027d2…` | Full `verify_archive` PASS, 9.178 seconds |
| Build Archive Recovery | `8be1ad…` | `c4dc1553…` | `4e54fcce…` | Full `verify_archive` PASS, 9.036 seconds |

Each bounded verification checked the exact expected Candidate, bundle and
manifest, the complete byte/permission inventory, directory key, separate
manifest, COMPLETE receipt, and absence of hard-linked retained files. The
fresh receipts and complete command arguments are in the JSON. This proves
archival byte integrity; application execution was not tested.

The originals remain unchanged. Their extra file and directory sets necessarily
differ from their recorded inventories. `candidate_archive.py` rejects that
difference; `promote_proposed_baseline_lite.py` invokes archive verification for
both proposed and outgoing CURRENT before writing outputs. Source hashes and
guard locations are recorded in the JSON. No real promotion was invoked, and
the originals were not rehashed a second time merely to repeat the established
inventory failure. Existing alternates are available for an explicitly governed
recovery decision; their successful verification does not switch a canonical
reference or CURRENT.

## Five prior unknown objects

| Object | Additional evidence | Classification and remaining boundary |
| --- | --- | --- |
| `integra-excel07-release` | Manifest Candidate `0020e329…`, dirty source `4161ec1…`, historical build-script hash `ad81f7…`; source commit associated with merged PR #209 | Manifest-bound legacy Integra build; distinct Candidate is not accepted merely because its source appears in a merged PR; no lifecycle/publisher attestation |
| `integra-excel07-source-current` | Manifest Candidate `e594978…`, clean declared source `2cc003f…`, historical build-script hash `ad81f7…`; GitHub source lookup returned HTTP 422 | Manifest-bound legacy Integra build; declared bundle equal to other Candidates does not establish whole-copy or disposal identity |
| `integra-excel05-zoom-candidate-b53d3d2` | Manifest Candidate `132cff…`, clean declared source `b53d3d2…`, historical build-script hash `ad81f7…`; GitHub source lookup returned HTTP 422 | Manifest-bound legacy Integra build; no exact completed Candidate archive found in the prior scoped inventory |
| Partial `integra-excel22-topic-translation/build/excel-22/Integra.app` | 7,586,596 logical bytes; no Candidate manifest; enclosing clean tracked worktree on `codex/excel-22-topic-translation`, HEAD `f958b361…`; PR #204 remains open | Build inside an active source-worktree context; preserve the worktree and partial output pending explicit lifecycle/ownership resolution |
| `AI/runtimes/integra/current-build/Integra.app` | Integra bundle identifier, version 1.0.0/build 100; no Candidate manifest or ownership marker; `application_runtime.py` SHA matches one governed file of historical accepted Candidate `c5851d…` | Legacy Integra application with incomplete identity; single-file association does not establish the complete Candidate, runtime consumers, or deletion ownership |

All five lack a lifecycle marker at the inspected scope and app parent. UID 501,
an Integra name, a build manifest, and source provenance do not supply a new
publisher/run attestation or deletion authority. No selected native executable
or bridge file was open in the normal-user `lsof` snapshot; no matching scope
appeared in the process-command snapshot. These are limited snapshots, not proof
that every consumer is absent. Full payload verification was not expanded to
these five objects. All remain retained; automatic deletion is prohibited.

Fresh PR #204 head `93a080dcc9d1cd6509b56905b99e1593004df8b1` still names pending
Candidate `14b3c10…` with no owner acceptance and the stale `2b779…` base. Head
maintenance did not create a replacement Candidate. The active worktree's
local branch and HEAD are distinct facts, not proof that every output belongs
to the pending Candidate.

## Selector recommendations and authority

Fresh main CURRENT is `d8bd6fc…`. The immediately preceding accepted record is
`af81b286…`, bundle `4032ad53…`, manifest `c0f016e1…`: it is the evidence-based
recommendation for an outgoing accepted baseline / rollback selector.

Retained historical recovery Candidate `65bf72…`, bundle `044594f1…`, manifest
`c59d1855…`, is the evidence-based recovery-selector recommendation. Its
historical recovery and independent QA are documented in the accepted retention
contract. Neither recommended selector was freshly fully verified in this
stage. Exact IDs and archive paths are retained in the JSON.

Existing Candidate acceptance and historical recovery evidence do not by
themselves confirm a new named retention-policy slot. Product Owner selector
confirmation remains distinct from this recommendation. This role performed no
selection, promotion, restore, copy, or canonical-reference change.

## Retention implementation advice

The authorized 8-copy / 20-GiB cap and 15-GiB free reserve must count observed
managed legacy archive occupancy even when automatic deletion ownership remains
unconfirmed. Otherwise legacy bytes would disappear from quota accounting.

A verified COMPLETE receipt plus a bound Git receipt/path plus UID provides
strong historical artifact provenance. It does not fabricate the new catalog's
publisher/run ownership attestation. Keep those facts separate: managed legacy
archive, ownership unconfirmed, conditional lifecycle eligibility, and
automatic deletion prohibited. Historical mass deletion remains a separate
HumanGate with enumerated paths, exact identities, fresh verification,
filesystem device/inode, ownership attestations and retirement authority.

Physical APFS extent sharing and exact reclaim remain unmeasured. No archive,
runtime, user data, or transient application was removed by this investigation.

PRODUCT_RULES_READ: YES
APPLICABLE_PRODUCT_RULES: PR-013
PRODUCT_RULE_CONFLICTS: NONE
