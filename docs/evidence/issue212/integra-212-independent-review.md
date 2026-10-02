# Issue #212 independent implementation review

## Verdict and scope

**PASS for lifecycle implementation source A `74785b5f34cb12e1cd557b34731bffbe191cbe15`.** No unresolved blocking code finding in the reviewed scope. This is independent code/fixture QA, not a claim that native Candidate evidence, the final proposal, full-suite governance or PR quality gates have already passed. The completed native evidence is independently checked in the final supplement below; final declaration/full-suite/CI quality gates remain pending.

The change is development tooling and policy enforcement: 20 source/doc/test files, no PR #206 forensic records, proposal overlays, CURRENT updates, protected archive edits or source-product edits. Review made no changes to code/tests or real archives. Only this independent report was added. The reused controls remain 8 full copies, 20 GiB attributed archive allocation and 15 GiB free after reservations; policy authority and historical migration gates are preserved.

## Findings resolved

1. Cleanup now uses `_finish_container` on normal completion and on recovery after the final payload unlink. It attempts only an exact empty Candidate parent under registered roots. Nonempty/foreign content is preserved; no recursive parent removal is introduced. The crash-boundary regression passes.
2. Pre-build/pre-copy maintenance mechanically refreshes an existing confirmed protection context from exact canonical CURRENT and every open PR, retains exact immediate rollback, confirmed recovery and governance pins, then fully verifies selected survivors through `sync_protection`. Ambiguous/missing survivors, drift or unavailable authority block cleanup. The local CURRENT must already equal canonical main; this tool does not update repository truth or create product acceptance.
3. Tests and native packaging enter the same reservation/supervisor. `--package-tests` invokes `package_ready_app.sh` as an admitted child using a fresh strict descendant of its owned workspace. It explicitly reports `candidate_identity_claimed=false`: post-signing bytes are disposable package validation, not a retained Candidate identity. Raw low-level builder output cannot overwrite an existing app or archive.
4. Fixture isolation is explicit: catalog, root set and reservation files are test-local. Stale-workspace startup reclamation is restricted to its exact base; archive-stage recovery uses journaled paths. Test fixtures do not reinterpret old unmarked directories as owned disposable work.

## Concurrency and destructive boundaries

The catalog lock serializes lease reservation, ownership publication, role reconciliation and deletion. Maintenance releases its initial snapshot lock before invoking the executor; the executor rechecks the exact plan and authority under the lock. Atomic admission rechecks current copy/byte charges and live reservations, so a previously observed free slot cannot authorize a racing build. Publication closes writer exclusion only after verified immutable COMPLETE publication and recorded ownership. Protection, path/inode/UID, exact payload, journal metadata and activity checks remain required for deletion; publisher completion does not waive them.

Cleanup withdraws one verified package into no-replace journaled trash, then deletes bounded recorded entries through directory descriptors. An interrupted transaction is reauthorized with fresh protection and full remaining-byte checks. Unknown entries, replacements, changed bytes, active handles, incomplete ownership or foreign collision fail closed. This does not establish immunity to arbitrary same-user concurrent filesystem tampering; the control is fail-closed lifecycle management with the recorded checks, not an OS security sandbox.

Production canonical governance pins are still unresolved (`explicit_governance_pins=null`). Incomplete canonical pin enumeration or missing protected survivors therefore prevents automatic cleanup. Legacy receipts/UID alone do not grant catalog ownership. Legacy objects remain charged against caps and preserved; rejection can be the safe outcome. The isolated fixture's complete simulated authority is not evidence that the real canonical registry is complete.

## Independent verification and limits

- Independently ran `test_issue212_lifecycle.py`: **7 PASS** in 3.525 seconds, including actual macOS `lsof` open-file exclusion, interruption after final unlink, nonempty parent preservation and twelve filesystem publication/fixture-promotion cycles.
- Independently ran `test_native_test_admission.py` before the portable fixture-only correction: **5 PASS** in 0.112 seconds, including the new packaging child regression.
- Inspected saved focused results: 3 disk admission, 28 archive, 24 retention, 16 governance, 15 TMP lifecycle, 7 Issue #212 and the then-current 4 native admission tests all PASS. The independent five-test rerun covers the additional packaging test.
- The first full suite is explicitly **904 run, 3 failures, 92 skipped**; it is not green. The coordinator must bind the new actual native manifest/evidence to source A and verify the resulting proposal/governance overlays and final supported suite before reporting final quality gates as PASS.

The twelve-cycle test exercises real copy/publication/inventory/capture/verification/reconciliation/executor code with synthetic app bytes, test-local canonical/activity adapters and a **simulated 64 GiB free-space probe**. It shows at most six copies during a cycle, five exact protected survivors afterwards and zero owned TMP workspaces between cycles. It proves bounded mechanics under the explicit fixture assumptions, not native build/signing, real free-space availability, product acceptance or an authorized change to real CURRENT. Separate native runtime/package runs remain separate evidence.

The ongoing native driver was inspected: fresh unique TMP base, owned input clone pinned to the exact source revision, one new Validation archive, then disposable native and packaging runs. It does not direct output at an existing protected archive. The driver/evidence results are not counted here until completion; no native result was inferred from launch or partial logs.

Heavy runtime deduplication remains deliberately conservative: exact package reuse exists, no hard links or external compulsory model store are introduced. APFS cloning is discussed as an investigation; attributed `st_blocks` and observed free-space changes do not prove exclusive APFS reclaim.

## Source bindings

| File | SHA-256 |
| --- | --- |
| `scripts/candidate_retention.py` | `cf98d0d6b1935d0b80e940905271954bb4882fdaed3b2121395eaec8d214568d` |
| `scripts/retention_cleanup.py` | `e58de82359669f689d8a8e959df166917fabd011f0d14ddaf4b0a1de61732225` |
| `scripts/retention_governance.py` | `8d5d2e22787c2a7ef88e359f344fefbbf116726185ce782330d572da89adbe39` |
| `scripts/build_macos_candidate.py` | `ba3664f579e166e4e291ac95988f168ee82afd3834ff88551e379b4b53104c24` |
| `scripts/build_disk_admission.py` | `643370a3ea7727d41fe1141ef4afdcf9605c993f489e22255ffb61a461fa65e3` |
| `scripts/temp_workspace_lifecycle.py` | `00ff4a35e92ef8d35f5bf1b1b0b4579f08c18442406f5afdc0f48401b402b71d` |
| `tests/test_issue212_lifecycle.py` | `dd344bd4939b830f2b873002f5bc869192bdabfd8ce108e6329b1978a724d250` |
| `tests/test_native_test_admission.py` | `7bd40d9fdbf9dcd8d81511d9311e230b069581f71f59c25d93cd351c80cd7e6d` |

## Source A portable fixture correction and interrupted native evidence

Latest source A is `74785b5f34cb12e1cd557b34731bffbe191cbe15`. Compared it to `9ef8d33`: the sole change replaces a hardcoded `/private/tmp` packaging test workspace with a resolved `TemporaryDirectory`; no product code, lifecycle guard, manifest generation, signing or policy changed. The checkout was clean at review. Focused coverage totals **98 tests**: 3 disk admission + 28 archive + 24 retention + 16 governance + 15 TMP + 7 Issue #212 + 5 native admission. Saved per-file logs originally contain four native admission tests; the independent five-test rerun and coordinator's updated result cover the new packaging test.

Inspected `integra-212-native-sigterm-cleanup.json`: the interrupted archived-native attempt exited 128 after 526.49 seconds and reports zero remaining owned roots, temporary inputs removed. This is failure/cancellation cleanup evidence, not a completed Candidate/build PASS. The still-named native evidence file contained this prior failed attempt at inspection; its existence alone is not evidence that the newer driver finished.

Inspected read-only runtime-input verification: expected and actual site-packages tree digest both `66d2ad50eac6194b8808b0316d37bdb64d69d27560847a671cc0f593119ac0c7`, bound to retained65's recorded manifest. The new driver uses own pinned SeminarText/VideoText Git fetches and hash-required wheels, with retained runtime bytes as read-only source. This verifier did not repeat that large runtime hash. Actual new native results remain pending and must bind this source A before being counted.

## Completed native and real-cap evidence supplement

**PASS for the completed source-A native lifecycle evidence.** Read the final native evidence files and corresponding logs. Four actual runs exit 0: archived native (151.42 s), disposable native (104.86 s), disposable signed package (110.25 s), and full native test probes (143.56 s). Each records zero residual owned workspaces; both driver summaries record input removal and no remaining owned roots. Inspected those disposable paths were absent, and the one new Validation archive exists. All fourteen recorded native PASS markers occur in the actual native test log. Package validation continues to make no post-signing Candidate identity claim.

The two actual unsigned build manifests are exactly equal as JSON, including clean source A `74785b5f34cb12e1cd557b34731bffbe191cbe15`, Candidate `candidate-v1-82ba92224a7dcdc0f1738155ba2e3f73dbdfc529ce2a8ffc461be73fa1351f29`, bundle `fedc5481c20a8829f92fd6f6579e53197b1495bd960c238efe9fdd14c2cb5582`, and manifest digest `667539142be8f7909dc56acb60be1e1fa30c05c6cec44ab931f32fcc8dd36c39`. The permanent receipt reports COMPLETE archival integrity of 29,607 files and 2,201,629,355 app bytes. Archive byte verification and native runtime validation are separate evidence; the receipt itself correctly reports runtime validation NOT_PERFORMED. This reviewer compared recorded manifests/logs and did not rehash that full application.

Real cap evidence reports **8 charged full copies, 18,278,240,256 attributed bytes**. Attempting a ninth full copy is rejected before a new workspace materializes. Its catalog has one newly owned Validation archive, no historical adoptions, unchanged empty deletion journals and no canonical protection context. The actual plan confirms `DELETABLE_BYTES=0`, `protection_context_valid=false`, 2,280,722,432 bytes protected as awaiting acceptance and 15,997,517,824 bytes UNKNOWN. This proves actual cap rejection without interpreting missing pin authority as deletion permission. It does not prove that real historical archive cleanup is enabled.

Protected preservation evidence reports **162,377 unchanged metadata entries**, identical before/after identity digests, and empty changed/missing/added lists over retained/recovery/Candidate Builds roots. Checked fields are device, inode, size, mode, mtime and ctime; the evidence explicitly does not claim a second complete payload hash. Runtime subset verification is separate. The final post-all-probe preservation rerun, final A→B→declaration binding, supported-suite and CI/governance results remain the coordinator's pending gates and must not be inferred from these native PASS results.

| Evidence at review | Raw SHA-256 |
| --- | --- |
| `integra-212-native-evidence.json` | `443f86f70d2d4c0f781ff59fdddc7afe6f17d4d14767a6fe3a73844f6618594b` |
| `integra-212-native-tests-evidence.json` | `95930e9ad86ccca7e7be24c5036cfdb5e4fd22b3ec4959411c411934852c6f8f` |
| `integra-212-real-cap-validation.json` | `5909c17bdd20afbe19a4e92954d2a51d8b00fd4c78c1af81049ac0ba8eb3c2d3` |
| `integra-212-real-archive-plan.json` | `da48cc3675d76da1759f437cea5ab77576962605166101aa4524faf07572aba9` |
| `integra-212-protected-preservation.json` — prior final rerun | `f40d1ab5dc27f3318606c7f6f3671832cb23b577fcd09eb3a12c6fa358183443` |

Earlier failed native attempts remain failure/cancellation evidence. Their successful owned-root cleanup is retained; later success does not convert their exits into PASS. No protected bytes, CURRENT or installed runtime were modified by this reviewer.
