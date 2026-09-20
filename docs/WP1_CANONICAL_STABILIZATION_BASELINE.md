# WP1 — Canonical Stabilization Baseline

Issue: [#153](https://github.com/Yurielo/integra/issues/153)  
Scope: P0 / identity and control only

## Starting evidence

`main` began at `8fce7a625cac3d57f0d197e2ea610241821452f5`, clean. The
canonical branch is `codex/stabilization-mcwma`, created directly from that
commit (not from a stacked draft). Historical heads are provenance only:

| Historical PR | Head | WP1 disposition |
| --- | --- | --- |
| #141 | `df784b0d49409b69624e0be169c3604e1d78f36b` | historical evidence only |
| #143 | `f46bb382cdc6f52eace25f185d7278d547b838b0` | Word Alignment runtime identity only |
| #145 | `0de3d4d188fd217dbc8ee65cd300d78732767d6d` | narrow Ollama resolver only |
| #147 | `e05aab3959d5a171d64b212ec49553f687e3ac3b` | active SeminarText CLI hash only |
| #149 | `a6c6276621f9a930e8c783515aa6eca519114a66` | observability reimplemented; E2E harness not transferred |

The required consumed component inputs are: SeminarText
`970bde598ddd649599295139986933e0e06cb9c0`, CLI SHA-256
`f7f411bf106341ae970bc40d759e1e3c964273b977bdb12d0f1840e629def13a`;
VideoText `2e098d1705b6815628bee1e023f4742718eabf02`; and BookText
`46396649214275eb18054b670a842bace02d02e1`.

## Applied Salvage Matrix

| Item | Source / exact provenance | Applied WP1 change | Explicit non-transfer |
| --- | --- | --- | --- |
| Word Alignment | #143, `f46bb38`; clean CPython 3.13 / WhisperX 3.8.6 / exact-version package construction and Russian model revision `232910…f3406`, weights `d1cdb1…df0c1c` | Candidate records bundled package-tree digest, model bytes and external Python identity; isolated candidate reruns preflight only | no inherited candidate PASS, no Timeline debugging, no product E2E |
| Ollama | #145, `0de3d4d` | deterministic configured/PATH/Homebrew/official-app resolver plus focused tests | no install, model selection, or pin change |
| SeminarText ASR | #147, `e05aab3` | active CLI expected hash and build runtime manifest use the final accepted CLI bytes | historical `a94936…` vendor/evidence remains untouched; no ASR semantic change |
| Word diagnostics | #149, `ead6f69` provenance only | generic candidate-bound worker evidence: correlation, command, sanitized environment, timeout, exit, bounded logs, I/O hashes and validator reason | old diagnostic patch and all primary E2E claims/harness |
| Packaged E2E | #149, `5f75d21` / `a6c6276` | Candidate identity interface only | no packaged product E2E in WP1 |
| #138 governance/pin migration and unrelated stack files | #141–#149 | none | historical evidence only / dropped |

## Candidate Manifest and evidence contract

`schemas/candidate_manifest_v1.schema.json` defines the embedded
`Integra.app/Contents/Resources/candidate-manifest.json`. Its identity-bearing
fields are `identity.source` (commit/tree/dirty diff digest), the build-script
identity, consumed component runtime identities, GUI and Word Alignment Python
identities, bundled Word Alignment package/model identities, and the Ollama
resolution contract. Canonical JSON (sorted keys, compact UTF-8) of that object
is SHA-256 hashed as `candidate-v1-<sha256>`.

`build.timestamp` and `build.build_id` are informational only: they do not
change the Candidate ID, so byte-identical identity inputs remain comparable.
The bundle digest is a deterministic SHA-256 tree digest excluding the manifest
itself, avoiding a self-referential hash. The build embeds this digest, then
`scripts/candidate_manifest.py validate <Integra.app>` validates the manifest,
bundle, component runtime manifests, Word packages/model, and the external GUI
and Word Python identities without opening the GUI.

`schemas/candidate_evidence_v1.schema.json` defines future gate evidence. Each
record binds Candidate ID, manifest identity digest, bundle digest, gate name,
timestamp, PASS/FAIL/BLOCKED result, artifact locations and bounded details.
Word Timeline external-worker evidence uses this contract. It is observability,
not an acceptance decision.

## WP1 validation record

Completed cheapest-first checks:

| Check | Result |
| --- | --- |
| Python syntax for changed modules and candidate tool | PASS |
| `bash -n scripts/build_macos_app.sh` / `git diff --check` | PASS |
| focused Candidate Manifest, Ollama, Word Timeline, VideoText and SeminarText runtime tests | PASS: 26 run, 6 environment skips |
| agent validator | PASS |
| governance validator | NOT RECERTIFIED: its immutable R12 implementation hashes intentionally describe historical accepted bytes and detect this WP1 bridge/build change |
| review-wheel contract and two fresh-cache restorations | PASS: five exact wheels, identical filename/hash inventory |
| clean isolated candidate build | PASS |
| embedded Candidate Manifest and bundle digest validation | PASS |
| native self-test | PASS (`INTEGRA_MACOS_SELF_TEST: PASS`) |
| bundled SeminarText identity/preflight | PASS: commit `970bde…cb9c0`, CLI `f7f411…ef13a` |
| Candidate-bound Word Alignment identity/preflight | PASS: CPython 3.13, model revision `232910…f3406`, weights `d1cdb1…df0c1c` |

The isolated build used clean detached source checkouts: SeminarText final pin,
VideoText final pin and BookText final pin. It correctly rejected the original
local VideoText checkout because its `TranslationAdapter.swift` bytes differed
from the pinned hash; that checkout was not changed. With the clean checkouts,
the build reached `scripts/package_review_runtime.py` and initially stopped
fail-closed because the new worktree had no governed wheel cache. That blocker
was resolved only by the contract-first procedure above; the clean retry used
the validated fresh cache through `INTEGRA_REVIEW_WHEELS`. No old candidate
runtime or wheel file was copied.

The authoritative final candidate produced the following immutable evidence:

| Field | Value |
| --- | --- |
| Candidate path | `/private/tmp/integra-wp1-candidate-authoritative.FINhlx/Integra.app` |
| Candidate ID | `candidate-v1-59cbbfbea96fc6340fdf169739418cddca4ba51cf090e8b000d87ecdc068424a` |
| Bundle digest | `1bef491399fe36189260e1c7dee2d06b2d926616d2959007662aba830ba39764` |
| Build source commit | `57f784594d5f5783bd1ccec17bb3e0827a1648fc` |

The manifest reports `dirty=false` and tree `8f1c00f1b2e7902c1a91451cd200bf74794c3e9a`.
The subsequent report-only commit does not alter the candidate or its bundle;
the manifest remains bound to the clean implementation commit shown above.

This is not a Word Timeline diagnosis, product repair, runtime-pin change, or
permission to reuse an old candidate PASS.

The governed review-wheel closure is explicit in
`state/review_runtime_cache_v1.json`: requirements-file digest, PyPI
simple-index provenance, CPython 3.14/macOS arm64 wheel contract, all five
filenames and hashes, and the offline install command. Two independently
restored fresh caches were produced with hash-locked `pip download`; both
passed the validator and produced identical filename/hash inventories. No
wheel was installed or copied from an old candidate. Packaging now invokes the
validator before its existing offline install and receives the validated cache
through `INTEGRA_REVIEW_WHEELS`.

This issue claims neither primary product E2E, MCWMA readiness, nor owner
acceptance. WP2 is the first permitted #148 classification work; WP3 owns
repair and E2E.

**WP1 status: `WP1_PASS`.** The canonical stabilization branch, itemized
salvage, immutable Candidate Manifest/ID, candidate-bound evidence contract,
fresh-cache provenance closure, isolated build, native self-test, final
SeminarText identity and Word Alignment preflight all pass. No product E2E,
WP2/WP3 work, or owner acceptance is claimed.
