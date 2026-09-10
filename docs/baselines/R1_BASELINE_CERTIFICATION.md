# R1 Pinned Component Baseline Certification

Status: `ACCEPTED`

Verified: 2026-09-10

This report certifies exactly what Integra can depend on from the accepted
`main` branches of SeminarText and VideoText. It does not promote either source
application, alter a source repository, or convert documentation claims into
test evidence.

The machine-readable authority is
[`state/component_baselines_v1.json`](../../state/component_baselines_v1.json).

## Pinned identities

| Component | Repository | Commit | Version/schema | Clean checkout |
| --- | --- | --- | --- | --- |
| SeminarText | `Yurielo/seminartext` | `a94936cd77cde13561c97c804ece1ac1134e01a6` | 4.0.0; state schema 3 | yes |
| VideoText | `Yurielo/videotext` | `2e098d1705b6815628bee1e023f4742718eabf02` | 0.6.4 build 2026.09.09.1; project schema 7 | yes |

Only these merged commits and the hashed contracts in the manifest are valid
R1 dependencies. Local working branches, untracked files, unmerged Issues, and
installed application bundles are not dependency inputs.

## SeminarText evidence

- GitHub `main` Quality Gate: PASS for the pinned commit, run
  [33909188798](https://github.com/Yurielo/seminartext/actions/runs/33909188798).
- Fresh Python 3.14.6 `dev_test` profile: PASS.
- Product Rules validation and `seminartext-dev check`: PASS.
- Full suite from a clean temporary checkout: 285 passed, 0 skipped.
- Integrity: G1-G5, G7, and G8 PASS; G6 `NOT_IMPLEMENTED`; overall PARTIAL for
  that single declared reason.
- Installed governed runtime was byte-identical to the pinned repository and
  functional smoke checks passed.

This baseline is suitable for contract discovery and adapter work. It is not a
claim that the broader SeminarText product-integration program or Issue #68 is
complete.

## VideoText evidence

- Fresh clean checkout build: PASS; the temporary `.app` passed plist,
  ad-hoc signing, and signature verification.
- Twenty-eight input-independent deterministic standalone probes: PASS.
- Long-topic probe: PASS on 3131 cues; 42 topics passed strict validation.
- Current release gate: PASS for the pinned commit and unchanged release-input
  hash; two consecutive real-video E2E runs, candidate signing, smoke, and
  post-smoke signature verification passed.
- GitHub CI: not configured; GitHub reports no check runs for the pinned commit.
- The repository states that the last full local deterministic cycle passed,
  but also states that deterministic probes do not replace real-media,
  listening, or release E2E evidence.

The release test used the same previously established read-only VideoText QA
fixture and Whisper model. The evidence binds the hashes of the source commit,
release inputs, video, model, and candidate; it does not make path names or
media content an Integra dependency. The candidate was not promoted to the
stable application path. The benchmark files named in VideoText documentation
remain uncommitted and were not found at their documented adjacent `work`
locations, so their narrative claims are limitations rather than R1 evidence.

## R1 disposition

- Reproducible compatibility manifest: PASS.
- Unmerged work excluded as a dependency: PASS.
- Clean deterministic source gates: PASS for both components.
- Supported standalone gates: PASS for both pinned components.
- VideoText current real-media release gate: PASS without promotion.
- SeminarText G6 remains explicitly `NOT_IMPLEMENTED`; R1 does not reinterpret
  an unavailable gate as a failure of its supported standalone suite.

R1 is `ACCEPTED`. Integra may use these exact pins for contract and adapter
work. This acceptance does not release either source product, authorize an
installed-app replacement, or waive later Integra combined real-media gates.

No Dataset, Gold, source-project data, source repository, installed stable app,
credential, or external account was changed or accessed.
