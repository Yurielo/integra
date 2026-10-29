# Candidate retention and recovery

Issue: [#192](https://github.com/Yurielo/integra/issues/192).

## Active bounded policy, 2026-09-30

The Product Owner decision in Issue #205 adopts
[`BOUNDED_CANDIDATE_RETENTION.md`](BOUNDED_CANDIDATE_RETENTION.md): 8 full copies,
20 GiB attributed archive allocation, and 15 GiB free after reservations.
Actual application bytes remain mandatory for every protected class. Historical
acceptance alone no longer grants indefinite full-byte protection; explicitly
active governance/provenance obligations remain protected. The exact historical
migration requires a separate Human Gate. The historical recovery evidence
below remains unchanged.

The Product Owner's 2026-10-09 standing terminal-retirement decision is
implemented by Issue #228 and
[`CANDIDATE_LIFECYCLE_RETENTION_POLICY.md`](CANDIDATE_LIFECYCLE_RETENTION_POLICY.md).
It permits only fully proven owned terminal archives with no remaining canonical
obligation. It does not authorize legacy ownership adoption, pending-decision
withdrawal or retirement of the four explicit holds. The policy is execution
authority only after canonical delivery; Phase A never deletes real archives.

## Autonomous bounded rotation — Issue #281

### Owner amendment — Issue #306, 2026-10-29

The Product Owner's direct instruction supersedes the Issue #281
terminal-only selection rule **for capacity rotation**. The maximum remains
eight full managed copies. Before admission of a new archived Candidate at
eight copies, the existing manager retires exactly the oldest physical full
copy, then admits the new one. No routine Owner selection is required. The
currently installed application is outside the managed target roots and is
never a rotation target. The prior terminal-retirement rule remains historical
and continues to govern explicit terminal cleanup outside capacity rotation.

New publishers persist an actual UTC publication timestamp under the catalog
lock. For legacy copies without that timestamp, the approved fallback is the
APFS directory birthtime observed at rotation, with Candidate ID as a tie
breaker. The two pre-amendment publisher records have monotonic sequences
but no publication timestamps; their initial placement is recorded as an
observed-now cohort position, with sequence 2 before sequence 3. The manager
persists the complete eight-copy initial ordinal under the existing catalog
lock, binding each path, Candidate identity, UID, inode, birthtime and order
source. Later runs compare live copies against that record and reject changed
paths or birthtimes. The observed APFS values are never called historical
publisher timestamps. If any copy lacks an exact
identity or an available approved ordering value, rotation fails closed. No
source-commit time, filename, or mtime is substituted.

Issue #310 clarifies the pre-amendment sequence evidence when a completed
archive's current APFS device differs from its catalog record. The sequence
is a **currently recorded, unsigned catalog value**; matching `COMPLETE`,
inventory, Candidate identity, manifest and full application bytes ties the
current archive to that record's identity, but does not authenticate when the
sequence was originally assigned or prove physical continuity. The physical
placement still uses observed-now APFS birthtime. Such a row retains
`publisher_owned = false`; the manager records the device discrepancy and
the exact observed catalog record without rewriting its historical fields.
Only this receipt-matched, same-UID, same-inode, device-drift case may use the
recorded pre-amendment sequence. A mismatched receipt, inventory, identity,
inactive-writer check or full archive proof blocks rotation. If that exact
copy later becomes oldest, the capacity transaction may retire it under the
Owner's v2 physical-copy policy with a distinct conflicting-record receipt;
the terminal-retirement ownership gate remains unchanged.
An exact rebuilt publisher archive at a retired identity-bound path is a new
physical incarnation only after its original retirement receipt, new physical
identity, publisher ownership and full `COMPLETE` archive verification pass.
The original ordinal remains historical. New publication timestamps must
advance with publisher sequence; a backwards clock records a conflict and
blocks later rotation rather than reordering existing copies.

Before physical retirement the manager verifies the exact Candidate manifest,
full current application tree, package inventory, UID/device/inode, inactive
writer and canonical Owner policy. An unarchived legacy build receives a
distinct observed-now attestation with no invented `COMPLETE` or publisher
record. A completed but unregistered legacy archive keeps its original
`COMPLETE` and inventory bytes in the receipt; it is still not called a
publisher-owned archive. The existing durable cleanup journal preserves
the exact manifest bytes, inventory, non-application provenance file bytes
(including legacy `build.log`, with a bounded fail-closed capture),
lifecycle/Proposal references and a
physical-availability receipt outside the payload. Interrupted retirement
recovers under the shared lock. A completed receipt says
`RETIRED_NOT_AVAILABLE` and cannot be used as a restorable application.

Earlier active Proposal or accepted status is not silently rewritten by
rotation. A rotated Candidate cannot be accepted or promoted from missing
bytes. A rotated outgoing CURRENT archive likewise keeps promotion fail-closed
until an exact verified physical replacement is archived and rebound under the
separate promotion contract. Capacity rotation itself grants no acceptance,
promotion, installation, release or semantic authority. The direct Owner task
payload is bound by SHA-256
`b511eb039f306552b249c8c13ab421e95bfa6fa86fe0f55040e747d927711848`;
the APFS birthtime clarification was a subsequent direct Owner instruction.
Issue #306 records implementation work and is not represented as an
Owner-authored GitHub comment.

The paragraphs below record the superseded Issue #281 capacity rule for
historical traceability.

Issue #281 establishes the permanent archive-rotation rule. At the eight-copy
or 20 GiB limit, the system may retire **one** full copy only when every
existing terminal-retirement predicate already passes. Among those candidates,
it selects the oldest by the monotonic publisher publication sequence recorded
under the shared catalog lock. It never uses a filename, Candidate ID, source
commit date, or filesystem mtime as a proxy for archive age.

Publication persists a catalog high watermark together with its publisher
record. When opening an older catalog, the next publication also considers
the publisher sequences retained in physical-retirement receipts. Removing the
last live numbered archive therefore cannot reuse an earlier sequence.
An invalid persisted high watermark blocks publication; unnumbered legacy
archives retain their unproven ordering status.

Each rotation re-verifies the exact Candidate/bundle/manifest tuple, archive
integrity, inactive writer state, canonical protection snapshot and deletion
lease immediately before its durable single-package cleanup transaction. The
same lock serializes cleanup and new-publication admission; a racing publisher
cannot consume a slot before completed retirement is rechecked.

An archive without publisher ordering provenance, a historical/foreign archive,
or any archive with unresolved lifecycle/protection evidence remains retained.
When all eight copies are protected or unknown, the system deletes nothing and
does not create a ninth copy. It reports the concrete fail-closed capacity
limitation; a semantic lifecycle transition must be established elsewhere by
its own authority before a future rotation can occur. Product Owners are never
asked to assess or pick archive IDs.

## Exact 721d withdrawal and ownership recovery — Issue #293

The [recorded direct Product Owner instruction](https://github.com/Yurielo/integra/issues/293#issuecomment-6423470249)
approves only Candidate `721d5a…`, bundle `f7c053…`, manifest `241b9a…`.
The unchanged approved request is retained in
`docs/evidence/ISSUE_293_721D_OWNER_DECISION_REQUEST.txt`; its historical
"not yet received" heading describes the request before that later approval.
`state/history/candidate_721d_withdrawal_v1.json` records the exact
`WITHDRAWN_SUPERSEDED` disposition. This is no semantic acceptance or promotion.
The registry adds one exact withdrawal grant; all general holds remain intact.

After this procedure and its executable are merged unchanged on canonical main,
run `scripts/candidate_721d_ownership_recovery.py` with `--dry-run`, then
`--apply`, then `--reconcile-target`. The fixed authorization in
`state/candidate_721d_ownership_recovery_v1.json` binds the approved request,
owner comment, withdrawal history and original publisher attestation. The
recovery requires full archive verification, unchanged inode/UID, inactive
writer and the measured current volume. It changes only the target publisher
record's device from `16777233` to `16777232`, plus its dedicated transaction
journal. The current VolumeUUID does not establish historical volume
continuity: the original catalog did not record that UUID.

Immutable raw catalog backup and BEFORE/AFTER receipts remain under the shared
Retention directory, outside application payloads. Interrupted checkpoints are
revalidated and resumed; a conflicting binding or receipt fails closed. Target
reconciliation uses the existing canonical resolver, copies back only the
verified protection context and exact withdrawn record, and preserves every
other artifact record. It supplies no publication ordering provenance.

Only then may the existing `candidate_retention.cleanup_exact` executor receive
that exact full identity. It independently rechecks canonical authority,
protected survivors, ownership, bytes and activity before its durable retirement
transaction. The archived application stays intact during ownership recovery;
retirement's rename/journal safeguards apply before physical unlink. Metadata
backups and retirement receipts preserve provenance, not a restorable copy of
deleted application bytes. No ninth full copy, general adoption, CURRENT/K1/K2
change, installed-app change or model deletion is authorized by this procedure.

## Lifecycle

1. Build in a fresh, uniquely owned workspace. The low-level historical
   `build_macos_app.sh` deletes an existing `Integra.app` at its output path;
   never direct it at a retained archive or reuse a review Candidate path.
2. Verify the bundle and complete the relevant checks.
3. Create a completed archive using `scripts/candidate_archive.py`. Keep the
   archive outside temporary directories. The reference Mac uses
   `~/Library/Application Support/Integra/Build Archive`.
4. Verify the copied bytes against the expected Candidate, bundle and manifest
   digests. Archive creation copies rather than hard-links the source files.
   The completion record is published last. An incomplete or mismatched
   archive cannot qualify for promotion.
5. Retain the archive path and receipt with the Candidate evidence. Recheck
   the archive when preparing promotion. The promotion helper requires
   `--candidate-archive`, `--current-archive` for the outgoing baseline, and
   still requires explicit owner acceptance. Both archives are rehashed;
   output records cannot be written inside either archive.
6. Only after archival verification may the original, demonstrably owned
   transient workspace be considered for cleanup under its separate policy.

Archive identity includes both Candidate ID and bundle digest. Candidate ID
describes source and execution identity; it alone does not prove byte equality.
Existing archive destinations must be verified, never replaced or repaired
in place. A missing or damaged archive is an explicit recovery incident.

## Scope of protection

The archive records regular-file contents, sizes and permission modes. Its
verification is offline byte-integrity checking. Runtime executability on the
current host is a separate `candidate_manifest.py validate` and native-test
check, because external interpreters and tools can change independently.

Archive creation/verification is separate from the ownership catalog and
policy-controlled retention executor. Cleanup in #180/#181/#205 distinguishes
owned disposable builds from protected Candidate bytes. Filesystem UID, age,
a green test log and a copied manifest do not establish deletion ownership or
prove a protected Candidate has a verified retained survivor. Historical
unmarked objects require explicit ownership attestation at the migration gate.

This repair changes development tooling, not the packaged runtime, CURRENT,
source-product pins, semantic authority or installed application. It does not
implement general process cleanup or claim that #180/#181 are complete.

## Exact Excel #7 successor exception

The Product Owner's exact `d8bd… → 5f6384…` decision is implemented by
`scripts/successor_transaction.py` and the immutable
`state/history/excel7_successor_transaction_v1.json` event. Historical gaps
refer to the identities accepted in #214, independently of today's role.
Missing historical bytes remain non-restorable and rollback-ineligible.
The incoming archive is mandatory and reverified against its complete inventory.
No other missing outgoing archive becomes promotable under this event.

The governed merge holds the existing retention catalog lock through the last
archive recheck and canonical application. It coordinates managed retention;
external filesystem deletion is detected by later audit, not prevented.
Preparation consumes no authority. Only the exact successor tree on main
records consumption; a failed post-check cannot silently restore permission.

## Backup limitations

A local archive and Git bundle protect against transient-directory cleanup
and interruption. Copies on the same disk do not protect against disk loss.
A second independent backup should retain the archive and its receipts; no
cloud upload or external backup is claimed by local verification.

## Accepted Candidate recovery, 2026-09-26

Accepted Candidate `65bf72...` was previously built successfully; its original
temporary path later became unavailable. The precise removal mechanism is
unproven. The recorded build predates the interrupted session, and QA had
already reported the missing path before that session's usage-limit failure.

The retained pilot Candidate `2fe375...` supplied a verifiable byte superset.
Git comparison of packaged source paths showed exactly two added Python
modules. Before modifying any recovery copy, hashing the full pilot bundle
with those two paths excluded produced the recorded accepted bundle digest.

Recovery copied the verified pilot into a separate permanent directory,
removed those two files only from that recovery copy, and restored the exact
historical manifest after confirming the accepted bundle hash. The resulting
bundle and manifest both match the retained records:

- Bundle: `044594f1a632f1c140af28bb7de8e4acf782daca9863d84b9c5d77edb731fdf8`.
- Manifest: `c59d18552b8b860019852a420d4b7d6337e32408196df0615c8599179d44a2a5`.
- Accepted logical bytes: `2201478232`.
- Pilot logical bytes: `2201496430`.
- Pilot increase: `18198` bytes.

These size measurements include the embedded manifest and exclude Python
bytecode, consistently with the existing Candidate identity contract. They
are logical file bytes, not allocated filesystem space. No new compilation,
substitute baseline or owner acceptance was used. Python bytecode identity,
timestamps and extended attributes are not claimed by the historical digest.

Machine-readable evidence: `docs/evidence/CANDIDATE_65BF72_RECOVERY.json`.
The retained Git bundle contains complete source history through pilot evidence
commit `44a0563ed290516e89befb45cddeadfa2f1b76e0`.

Independent verification is recorded in
`docs/evidence/CANDIDATE_65BF72_RECOVERY_QA.json`: exact hashes before/after,
self-test, visible launch, close and the existing native workflow probe all
passed. The probe processed an isolated synthetic two-second video, producing
a speed-adjusted video and audio analysis; it did not run ASR or access user
projects. The QA record's `source_commit` identifies the validation checkout,
not the recovered application's historical build source.

Both completed permanent archives were freshly reverified with the final
tooling. Their receipts are `docs/evidence/CANDIDATE_65BF72_ARCHIVE.json` and
`docs/evidence/CANDIDATE_2FE375_ARCHIVE.json`. Each archive retains a separate
manifest, file/permission inventory and completion record. These receipts
report archival verification only; native QA is separately bound above.

## Repair validation

- Independent code review: 68 focused tests passed, zero skips. Review findings
  for case-insensitive filesystem aliases and promotion outputs inside an
  archive were fixed and rechecked. Archive verification rejects hard links,
  symlinks, special files, corruption, missing payloads and temporary roots.
- Local supported regression discovery: 735 tests, 655 passed, 80 skipped,
  zero failures or errors. The exact per-test results are retained in
  `docs/evidence/CANDIDATE_RETENTION_REGRESSION.txt`.
- Of those skips, 78 are existing environment-dependent checks. Two unchanged
  tests that perform full new application builds were explicitly deferred for
  this development-tooling repair: `test_reproducible_build_and_launch_probe`
  and `test_local_candidate_is_reproducible_signed_and_launchable`. They are
  not reported as passing or as a two-build reproducibility proof.
- Governance and agent-team validators pass with `CURRENT_VALID`.
- CURRENT SHA-256 remains
  `e7138dde52c4ad70fc73cb3f68af90b0775b05ced6426464f2238fc93d7e8db4`.
- Original build-script SHA-256 remains
  `f2c7577b3afcde75e00828e8a9d0303a9370eac517902d7c49a87cce65237623`.
- No packaged runtime, source-product pin, installed application, accepted
  baseline record or pilot source A/evidence B was modified.

The exact-size evidence blocker for #190 is resolved by this recovery. The
historical pilot report remains unchanged as the record of what was available
at the time. Its remaining proposal, governance and acceptance steps must be
evaluated separately; recovery alone does not make PR #191 ready to promote.
