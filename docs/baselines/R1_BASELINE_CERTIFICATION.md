# R1 Pinned Component Baseline Certification

Status: `IMPLEMENTED_PENDING_REVIEW_WITH_EVIDENCE_GAP`

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
- GitHub CI: not configured; GitHub reports no check runs for the pinned commit.
- The repository states that the last full local deterministic cycle passed,
  but also states that deterministic probes do not replace real-media,
  listening, or release E2E evidence.

VideoText therefore has a usable pinned engineering baseline, but not a
release-certified baseline. The required two consecutive real-video E2E runs
after the last production change were not run in R1 because no authorized
private media/model input or existing complete evidence package was available.
The benchmark files named in VideoText documentation are not committed and
were not found at their documented adjacent `work` locations.
The long-topic probe also requires an external long SRT and was not counted as
passed without that input.

## R1 disposition

- Reproducible compatibility manifest: PASS.
- Unmerged work excluded as a dependency: PASS.
- Clean deterministic source gates: PASS for both components.
- Complete source-application release/real-media certification: INCOMPLETE for
  VideoText and G6 not implemented for SeminarText.

R1 is therefore `PARTIAL`, not accepted. Integra may use these pins for
read-only contract work, but promotion past any roadmap stage that requires
real-media or release certification remains fail-closed until the missing
evidence is supplied under an exact authorization.

No Dataset, Gold, source-project data, source repository, installed stable app,
credential, or external account was changed or accessed.
