# Process executor isolation pilot checkpoint

Date: 2026-09-26. Issue #190 / draft PR #191.

**Status: BLOCKED.** The bounded implementation and packaged proof passed;
the exact CURRENT package/size inventory is unavailable. The mandatory size
comparison cannot be certified. This is not an architecture falsification or
authorization to promote, merge, install, switch routing or start Stage B.

## Architecture and review

One capability: `process.timed_transcript.normalize.v1`. Integra owns the
request, strict timestamp validation, fixed executor dispatch, neutral result,
artifact provenance and atomic publication. The existing proven VideoText
normalizer is invoked only by the private adapter. The representative boundary
is an existing timed-transcript interoperability problem, not an ASR rewrite.

See `PROCESS_EXECUTOR_ISOLATION_PILOT.md` for the exact contract and limitations.
Astra reviewed the bounded design before product implementation: VALID with
constraints, reconciled before coding. Independent review found and verified
fixes for publication failures, malformed Candidate metadata, probe source
binding and exact baseline bundle-digest checking. Final review cleared one
build, not release. QA independently authored the contract/fault tests.
Final independent QA also confirmed manifest/evidence/artifact hash consistency,
unchanged CURRENT/routes, measured size and the reported pass/skip/fail counts.

Exact provider commit: `2e098d1705b6815628bee1e023f4742718eabf02`.
SRTService: `417017a6a3becc395e88e2554e8d7c2dca51b09de9743e8c5c0cf81ac9ba6205`.
Actual worker: `22ba7bbfd827a1f2937f3757070b74b2e5d4d1200ebea954c48c1eaac1162d28`.
Location: `Contents/Resources/runtime/videotext/translation-worker`.
The normal result contains neither provider names nor provider CLI vocabulary.
Internal evidence retains exact runtime, executor, adapter, request and output
identities. Success is MACHINE_UNVERIFIED, not semantic acceptance.

## Source A and one Candidate

- Source commit: `2e2403ac7ae41c2104371902b3c56a0319dfe4ff`.
- Source tree: `bd205716e186560b340c696a8855db3ce64dd15d`; clean at build/proof.
- Candidate: `candidate-v1-2fe375cc31b3a57d74ad0f994894bd610442deae3adfff033cdc5f3cf400fcd3`.
- Bundle digest: `47befb29a6c221db7cb79262fc949f29248095e31dceba7fc4d46e78ab06c39e`.
- Local package: `/private/tmp/integra-process-pilot-candidate.vr9Gq5/Integra.app`.
- Built once with unchanged `scripts/build_macos_app.sh`; not installed.
- Manifest validated before and after execution, and after native probes.

Source A -> one revised Candidate -> this evidence-only overlay B.
Declaration C is intentionally absent: all-PASS required evidence cannot be
declared truthfully. CURRENT and owner-acceptance rules are not bypassed.

## Actual validation

| Check | Result |
| --- | --- |
| Focused contract/provider/probe/Proposal Lite suite | 82 passed, no skips/errors/failures |
| Packaged isolated executor | Two real runs PASS; same request hash, distinct attempts, exact expected output |
| Existing adapter differential | PASS with the same actual pinned worker |
| Invalid duration | FAILED without artifacts, as required |
| Native self-test | PASS |
| Native launch and close probes | PASS, visible source-first window, clean last-window termination |
| Existing native media workflow | PASS on synthetic 2-second video: speed + audio analysis, no ASR |
| Candidate integrity after probes | PASS |
| Broad local regression at source A | 750 run: 670 passed, 78 skipped, 2 governance failures |
| Extra app-building tests | 2 explicitly deferred to honor the one-Candidate constraint |
| Local governance validator | FAIL: two new governed modules lack a completed Proposal Lite declaration |
| Exact CURRENT size delta | BLOCKED; no substitute baseline used |

The focused command was `python3 -m unittest tests.test_process_executor_pilot
tests.test_process_pilot_provider tests.test_process_pilot_probe
tests.test_process_pilot_reference tests.test_proposed_baseline_lite -q`, with
`PYTHONDONTWRITEBYTECODE=1` and `INTEGRA_PILOT_REFERENCE_APP` pointing at the
new Candidate. The real-provider test imports source executor code; the separate
packaged probe explicitly verifies import from the Candidate itself.

The broad run used standard unittest discovery and explicitly filtered only
`MacOSApplicationTests.test_reproducible_build_and_launch_probe` and
`ReadyAppTests.test_local_candidate_is_reproducible_signed_and_launchable`.
Those tests build additional bundles. They are NOT counted as passed. Native
checks on the already-built Candidate are narrower evidence, not a substitute
claim of the entire two-build reproducibility test passing. No second build or
byte-for-byte full-app reproducibility claim was made.

The two failing regression checks are
`GovernanceValidationTests.test_current_baseline_exact_contract_passes` and
`GovernanceValidationTests.test_historical_certification_records_are_not_rewritten`.
Both report undeclared new modules, not modified historical records. Full test
names, outcomes and traceback are retained in
`evidence/PROCESS_EXECUTOR_PILOT_REGRESSION.txt`. The suite is NOT green.

## Runtime restoration and size

Build restoration used exact ST/VT/BookText checkouts, the existing hash-verified
alignment model/packages and the five hash-locked Review wheels. No global
dependency upgrades, model inference or protected-source edits occurred.
Candidate component and execution identities match the retained CURRENT
manifest, including the alignment packages tree and model weights.

Logical bytes excluding bytecode, symlinks and filesystem allocation overhead:

| Item | Bytes |
| --- | ---: |
| Entire Candidate | 2,201,496,430 |
| Word alignment runtime | 2,190,889,170 |
| VideoText runtime | 4,156,890 |
| SeminarText runtime | 489,572 |
| Review Python runtime | 1,799,603 |
| BookText runtime | 266,841 |

426 regular `.so`/`.dylib` files and named provider executables were hashed:
no duplicate-byte groups found within that bounded inventory. This does not
prove absence of static linked overlap or all duplicated libraries. The pilot
adds zero worker binaries; the existing broadly compiled worker is reused.
It proves invocation isolation, not minimal linked dependency closure.

CURRENT: `current-v2-65bf72d1262146c9137aca433b51ae3974d98bc4c8ed37042db13b46e0318a1d`.
Expected CURRENT bundle digest:
`044594f1a632f1c140af28bb7de8e4acf782daca9863d84b9c5d77edb731fdf8`.
The retained manifest has no byte-size inventory. Bounded search of installed
apps, known temporary Candidates, historical locations, backups and Downloads
found no matching bundle. Other Candidates are not valid replacements.
`delta_vs_current_bytes` is null, not zero and not an estimate.

## Preservation and exact changed scope

The packaged proof compares 15 routing/GUI/build source blobs against CURRENT's
recorded source commit; every comparison passed. Entire `state/` is unchanged
from PR191's starting head `8c8f77fa4c0d1241f0d052317a3b8980560ce0f8`.
CURRENT file SHA-256 remains
`e7138dde52c4ad70fc73cb3f68af90b0775b05ced6426464f2238fc93d7e8db4`.
No normal routing, 28 DONE outcomes, pins, source products, user projects,
Knowledge/Studio or semantic acceptance was changed.

Net revised PR scope relative to main, before this evidence overlay:

- `integra_core/process_executor_pilot.py`
- `integra_core/_timed_transcript_provider.py`
- `scripts/probe_process_executor_pilot.py`
- `scripts/proposed_baseline_lite.py`
- `tests/test_process_executor_pilot.py`
- `tests/test_process_pilot_provider.py`
- `tests/test_process_pilot_reference.py`
- `tests/test_process_pilot_probe.py`
- `tests/test_proposed_baseline_lite.py`
- `docs/PROCESS_EXECUTOR_ISOLATION_PILOT.md`
- `docs/PROPOSED_BASELINE_LITE_IMPLEMENTATION.md`

Six superseded old Stage A files were removed from the PR, not from accepted
main. Their historical commits remain. Evidence B adds only this report,
Candidate manifest, packaged proof JSON and full regression log.

## Owner gate

Required next input is the exact CURRENT bundle (or an independently verifiable
size inventory bound to its bundle digest), or explicit revision of the size
comparison acceptance criterion. Recovering another package or rebuilding the
old source is not silently equivalent to recovering the accepted binary.

After resolving that gate: complete the size evidence, reconcile the remaining
reproducibility evidence under explicit build authority, prepare declaration C,
and rerun governance/full supported validation. None of this authorizes merge,
promotion, another capability, Stage B or SeminarText retirement automatically.
