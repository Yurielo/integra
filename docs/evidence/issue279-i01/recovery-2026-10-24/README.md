# I01 K2 recovery, archive and proposal evidence — 24 October 2026

Issue #279 / PR #280. This evidence overlay freezes actual recovery, rotation,
fresh application and regression receipts before the proposal-only declaration.
Final declaration validation and full CI are recorded separately at the exact
PR head; this overlay itself does not grant semantic acceptance or promotion.

## Exact Candidate

- Source A: `6e6978a5f88930158058df8e90dbe4275f11c29a`, tree `d6a4ba71a2939e62bf7d765270b148ea67034dae`.
- Candidate: `candidate-v1-e8064cba8acad3282d86b9d7eea043f85c5eed54ac7db015ccdf089943dee943`.
- Bundle: `1fe98fb2822b50077f78f22db960dc1f457f5b6374736a3dace704e99e8fe7e0`.
- Manifest: `25255077dfd65185268ba152c50a1a5ba66d1a425ff9bcab342263f6fbb2c58e`.
- Permanent archive: `/Users/yurielokhin/Library/Application Support/Integra/Build Archive/candidate-v1-e8064cba8acad3282d86b9d7eea043f85c5eed54ac7db015ccdf089943dee943/1fe98fb2822b50077f78f22db960dc1f457f5b6374736a3dace704e99e8fe7e0`.

The fresh build reproduces the exact Candidate/bundle/manifest used for the
previous native GUI proof. Fresh bundle validation, the actual packaged schema
round trip, native self-test and isolated packaged K2 bridge probe passed again.
Actual application bytes were copied into the durable archive and independently
rehashed. Independent QA (`independent-incoming-archive-review.json`) also
verified all 29,626 files, the exact GUI tuple, publisher ownership, sequence 2
and high watermark 2 following retired sequence 1, eight full copies, allocation
and free-space limits, and unchanged CURRENT. A manifest alone is not being offered as retention evidence. The owned
execution workspace was cleaned only after archival verification.

## Authorized recovery and governed rotation

The prior unaccepted fixed K2 submission was explicitly superseded through owner
comment #6380155631 and canonical PR #289, merge a3fb04e. Its exact lifecycle event
and grant remain unchanged. The first governed build attempt exposed extra cache
entries; the earlier failure and recovery plan remain in `../handoff-2026-10-24/`.

The owner authorized the exact recovery exception in
https://github.com/Yurielo/integra/issues/279#issuecomment-6380883524, plan SHA-256
`d89bed43693b767fc510076ff9a8330a9222c63af960173241137d134fa89b50`.
The reviewed helper passed 18 isolated preservation/failure/rejection tests.
Under the common catalog lock and fresh canonical checks, it preserved the three
exact cache trees, all 45 files / 1,568,777 bytes, in
`/Users/yurielokhin/Library/Application Support/Integra/Integrity Quarantine/issue279-625264b464534f998a25427504d010b2`. Independent QA rehashed every quarantined file.
The quarantine, inventory and durable recovery journal remain retained; their
deletion is not authorized.

Strict verification of the original archive then passed all 29,626 recorded
files / 2,202,189,271 bytes. Original inventory, COMPLETE and manifest records
were not rewritten. Ordinary maintenance still retained it at an activity/unknown
classification; that failed attempt and the differing inactive-probe samples are
preserved here. The accepted canonical exact-withdrawal executor subsequently
rechecked the exact owner grant, integrity, ownership and inactivity under the
shared catalog lock. It retired only `candidate-v1-19e3438fea443e1d917b6575131fd67b47b5f44f71202a6940f85adda12b3b56` and recorded a durable
`RETIRED_NOT_AVAILABLE` receipt. The old application is physically unavailable;
its exact lifecycle, source, manifest, ownership and verification evidence remain.
This is separate from the retained cache quarantine. This was an exact
owner-authorized withdrawal retirement, not an oldest-first selection claim.
The outgoing publisher sequence was 1. Before replacement publication, the
canonical control-tool repair in [PR #290](https://github.com/Yurielo/integra/pull/290), recorded in `publication-sequence-repair.json`
preserved monotonic ordering through retirement receipts and a durable high
watermark; independent tests reproduce and prevent sequence reuse. Normal maintenance and capacity admission
then ran again for the fresh replacement build.

Capacity moved from eight full copies to seven, then back to eight after the new
publication. Final attributed allocation is 18292744192 bytes. Limits remain
8 copies, 20 GiB allocation and a 15-GiB free reserve. No cap, publisher ordering,
ownership or integrity rule was relaxed. APFS exclusive physical reclaim is not
claimed by attributed allocation or the observed free-space change.

## Regression evidence and declaration boundary

The full supported unit suite ran 1218 tests in 1049.352 seconds:
1154 passed, 64 skipped, zero failures/errors. It used the exact
temporary accounting fixture retained here, SHA-256
`166de248a59bcd6a4fe2974ebdfea5e67dd2f8d91d917d18bdb86f1491d7d079`. The four checkout-accounting
checks received the exact 11-file before/after delta as unit-test input.
Strict governance explicitly rejected that fixture as not a Proposal. It had no
PASS gates, acceptance, status or declaration claim, and was removed before this
evidence commit. Product bytes remain identical to frozen A. The evidence checkout also contains
the canonical publication-sequence repair and its independent regression tests;
the full suite was rerun after those control-tool changes.

The earlier source-A full log with four missing-proposal failures remains
unchanged. Those failures are not relabelled as passing. The actual strict
source A -> evidence B -> proposal-only C declaration must validate separately,
and full CI must run using the real declaration. The proposal will bind all 11
governed paths, no historical test successors, this exact manifest/archive and
candidate evidence, with `owner_acceptance: null`. A later registry-only canonical
binding protects the unchanged Proposal by its ID, file hash and exact tuple.

## Native GUI scope and retained boundaries

The unchanged binary's actual native GUI proof is in `../gui-2026-10-24/`: explicit
ACCEPT/EDIT/REJECT/DEFER, unchecked initial selectors/confirmation, two Concepts,
one Relation, no admitted rejected/deferred Topics, exact edited-label/revision
persistence through quit/relaunch/reopen, and generated-demo player navigation
with matching quote/hash at 0.080–5.728 seconds. Audible playback was not assessed.
These fixture choices are QA evidence, not Product Owner semantic acceptance.

CURRENT remains the accepted K1 baseline and both record hashes remain exact:

- `current_product_baseline_v2.json`:
  `bdd2ea30b3102c59cd8e47bc56a0d53c6b57d3bfb0347e667663b1be951e52e2`.
- `current_canonical_baseline_v1.json`:
  `0493fbad50f1a5518b01be90e3ffb0cd10d3d8b7a97ae12918fc4595c4438840`.

No source-product repository/pin, installed application or original project is
changed. No upstream Process/model rerun, live publication, signing/notarization,
release, semantic owner acceptance or CURRENT promotion is performed. New scope
is this receipt/evidence directory and dated pointers in the three earlier
reports; the one-off recovery helper is evidence, not packaged product code.
The next genuine gate is Product Owner review of the exact K2 Candidate.
