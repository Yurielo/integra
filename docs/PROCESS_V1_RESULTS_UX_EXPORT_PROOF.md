# Process v1: bounded Results UX and ordinary-file export

Status: technical proposal evidence only. This document does not change
`CURRENT`, the Completion Board, or claim `PROCESS V1 USER_ACCEPTED`.

## Bound source and Candidate

| Binding | Exact value |
| --- | --- |
| CURRENT base | `a718efc6b58745524f86f53b2d020e760fb7e15a` |
| Product source A | `2eade0c58d5e162bdbb36442c6874a6c21b03967` |
| Product source tree | `b112309d14fb65de1a6eece0a34c79b0b658b9e6` |
| Candidate ID | `candidate-v1-f7f0fd92b37ce8e8b172a6cfedba5c2b98d968f201de0f10c9cff06c61673777` |
| Candidate bundle digest | `2ae73aa6e301c503d4ed6881c0b499d0b11b23c5d091cbf77d60225114409b30` |
| Candidate manifest SHA-256 | `55c96ecde3e8f53bfb648a81dc0ef12abb586b35dbd3037b5c15530508e251d0` |

The Candidate was built once in a fresh isolated path from source A. Its
manifest validation and native `--self-test` both passed. It retains the
governed SeminarText pin `970bde598ddd649599295139986933e0e06cb9c0` and CLI
SHA-256 `f7f411bf106341ae970bc40d759e1e3c964273b977bdb12d0f1840e629def13a`.

## Bounded correction

The owner confirmed that the earlier export-mapping concern was a test-path
error: the native Save dialog on the Transcript card proposes `transcript`, and
the Cleaned Text card maps to its own artifact. Export behavior and filenames
were intentionally not changed.

Only two Process-surface changes are included in source A:

- publication controls are no longer rendered by `renderOutputs()`; their
  underlying publication methods and data remain intact outside the Process
  results surface;
- the source navigation label is `Открыть источник с расшифровкой`; its action
  remains unchanged.

## Evidence

| Gate | Result | Evidence |
| --- | --- | --- |
| Results surface regression suite | PASS | `tests/test_process_results_surface.py`, plus `tests/test_transcript_output.py`, `tests/test_operations_ui.py`, and `tests/test_seminartext_asr_runtime.py`: 29 pass; six environment skips; no Results UX assertion is counted through a skip. |
| Swift typecheck | PASS | `xcrun swiftc -parse-as-library -typecheck macos/IntegraApp.swift -framework AppKit -framework AVFoundation -framework AVKit`. |
| Candidate manifest and native self-test | PASS | `docs/evidence/PROCESS_V1_RESULTS_UX_CANDIDATE_MANIFEST.json`; `INTEGRA_MACOS_SELF_TEST: PASS`. |
| Packaged Finder-like result surface | PASS | `docs/evidence/PROCESS_V1_RESULTS_UX_NATIVE_RUN.json` and `docs/evidence/PROCESS_V1_RESULTS_UX_RESULTS.png`. The bundled app completed a real protective-ASR-retry/reuse run and presents Transcript and Cleaned Text as the wide two-column primary cards, each with Open and Export; source navigation uses the new label; `Технические данные` is collapsed; no publication block or publication action is present. |

The native evidence uses a non-private synthetic audio fixture. It confirms the
implemented visual surface and packaged runtime binding; it does not replace
the separate final minimal Product Owner visual check.

## Proposal boundary

The only governed product/runtime path changed from CURRENT base to source A is
`macos/IntegraApp.swift`:

| Path | CURRENT SHA-256 | Source A SHA-256 |
| --- | --- | --- |
| `macos/IntegraApp.swift` | `5803c63f59261ad18ed9a3a88b22e0675a8a1337f5d4db9db5546ea5d708a86e` | `995fa3946f43fba215d6fec90985e5fce1c49350c3b4eedb145ddcdc508b6507` |

The evidence overlay contains only this report and candidate-bound evidence;
it contains no product/runtime byte. The Completion Board remains unchanged
pending final owner visual acceptance.
