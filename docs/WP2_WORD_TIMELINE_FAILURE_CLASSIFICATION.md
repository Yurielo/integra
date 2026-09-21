# WP2 — Word Timeline Failure Classification

Issue: [#155](https://github.com/Yurielo/integra/issues/155)
Scope: P1 diagnostic/classification only

## WP1 prerequisite

The canonical branch was unchanged at the accepted WP1 starting point:

| Item | Evidence |
| --- | --- |
| Branch | `codex/stabilization-mcwma` |
| PR #154 HEAD | `0699bc9d69c0d63fd4439c8d1f15f5ba6472a622` |
| PR #154 state | Draft, open, based on `main` |
| GitHub Quality Gate | PASS, run `35534134507` |
| Component/pin changes in WP2 | None |

The Word Alignment package/model input was the exact WP1-governed immutable
package/model tree; the application bundle itself was rebuilt in a new isolated
directory and the old WP1 app was not used as a candidate or as evidence.

## Fresh WP2 candidate

The fresh isolated candidate was built with the governed build script and
validated before attempts:

| Field | Value |
| --- | --- |
| Candidate path | `/private/tmp/integra-wp2-candidate.2iibLk/Integra.app` |
| Candidate ID | `candidate-v1-1ab75c9a7d2a643333f5cad2478382d4da406de1e75aa4ef285510f814462862` |
| Manifest identity SHA-256 | `1ab75c9a7d2a643333f5cad2478382d4da406de1e75aa4ef285510f814462862` |
| Bundle digest | `991ee9d6f64df1c97ce74c62552b2fe8aa4eb84c2b10953066e16edb329545e9` |
| Source HEAD | `0699bc9d69c0d63fd4439c8d1f15f5ba6472a622` |
| SeminarText | commit `970bde598ddd649599295139986933e0e06cb9c0`, CLI SHA `f7f411bf106341ae970bc40d759e1e3c964273b977bdb12d0f1840e629def13a` |
| VideoText | commit `2e098d1705b6815628bee1e023f4742718eabf02` |
| BookText | commit `46396649214275eb18054b670a842bace02d02e1` |
| Word Alignment model | revision `2329100508896c6d9b157019803ab5601e6f3406`, weights SHA `d1cdb1a7921de7d363f967a9b0101a713602e109dba62b6f3f9ae2e0b2df0c1c` |
| Word Alignment Python | `/opt/homebrew/Cellar/python@3.13/3.13.15/Frameworks/Python.framework/Versions/3.13/bin/python3.13`, SHA `1988a0dd685f91bbaf20b5267046e13cb78859dbb3b5f030e89b448c1fbfe8d4` |
| GUI Python contract | `/usr/bin/python3`, Python 3.9.6, SHA `179301dcb41ea78accc3fa0048a7e6f6710d891945a751a34addd622020c1818` |
| Ollama | `/Applications/Ollama.app/Contents/Resources/ollama`, version `0.33.1`, SHA `bd835b935229256fc8c5fcd983bef69f5b6142d4fa4f5d8baa05e5e77fd13fbf` |

Candidate Manifest validation and the native headless self-test both passed:
`INTEGRA_MACOS_SELF_TEST: PASS`.

## Historical failure and unavailable evidence

The historical #148 owner run was:

`local video → ASR → Transcript/SRT → Word Timeline`

with the top-level error `Word Timeline worker did not produce a validated
output`. The owner-derived input pair is preserved locally in the existing
Integra project artifact (not copied to this repository):

| Artifact | Provenance / SHA-256 |
| --- | --- |
| `video1591534861.mp4` source content | source SHA `9faa1c03460aad1e8867593d28db1f140d0c839879a569ac362cb6a5eaf6ce6c` |
| WAV | `acf25b9ac68a11dc3f0fd193ec67283843e856a4a190a8e4cb2f35fcfa3df67c` |
| SRT | `af17d83246dedc55dbef5aa0ff2059461dd263415dac1ce32e7d993c007c3492` |
| Preserved run | project `6ae742f5-25e7-480a-9e5a-2d7ff2ec7789`, failed at `word_timeline` |

The original worker exit status, stdout, stderr and environment were not
persisted. They cannot be reconstructed retroactively. The historical
candidate also predated the Candidate Manifest observability contract.

## Observability preflight

Before counting attempts, the fresh candidate executed a controlled failing
worker fixture. It persisted:

- Candidate ID, manifest identity SHA and bundle digest;
- stage and run correlation (`word_timeline`, `wp2-observability-preflight`);
- the exact command and candidate runtime paths;
- sanitized environment, including Candidate ID/run/stage;
- Word Alignment Python/model/site-package identity;
- timeout (`1200` seconds), exit status (`17`) and explicit failure reason;
- bounded stdout/stderr tails (both exactly `16384` bytes in the stress fixture);
- input WAV/SRT SHA-256 values;
- intended output path and absent-output SHA;
- persisted candidate evidence artifact.

Evidence: `/private/tmp/integra-wp2-evidence-observability-3/fixture.timeline.worker-evidence.json`, bound to Candidate ID
`candidate-v1-1ab75c9a7d2a643333f5cad2478382d4da406de1e75aa4ef285510f814462862`.

Focused contract tests also passed: 5 tests covering Candidate Manifest binding,
bounded worker diagnostics, exact runtime identity and fail-closed worker
failure.

## Bounded attempts

All three owner-derived attempts used the exact fresh candidate Word Alignment
worker/model, Python 3.13 runtime, unchanged WAV/SRT bytes, separate output
directories, and candidate-bound evidence. No source-tree runtime fallback was
used.

| Attempt | Result | Exit | Words | Output SHA-256 | Evidence |
| --- | --- | ---: | ---: | --- | --- |
| owner-derived-1 | PASS | 0 | 174 | `fadfa03e5bc5926458c75613bf8cf4ab429d8d08c61eb6847a03445872f8b8b9` | `/private/tmp/integra-wp2-owner-attempt-1.wJK7lP/word_timeline.worker-evidence.json` |
| owner-derived-2 | PASS | 0 | 174 | `fadfa03e5bc5926458c75613bf8cf4ab429d8d08c61eb6847a03445872f8b8b9` | `/private/tmp/integra-wp2-owner-attempt-2.QGXsq6/word_timeline.worker-evidence.json` |
| owner-derived-3 | PASS | 0 | 174 | `fadfa03e5bc5926458c75613bf8cf4ab429d8d08c61eb6847a03445872f8b8b9` | `/private/tmp/integra-wp2-owner-attempt-3.7Yo546/word_timeline.worker-evidence.json` |

Each evidence record has the same Candidate ID, input hashes, model revision,
weights hash and Python 3.13 identity. Stdout was bounded at 100 bytes and
stderr was empty for all three passes.

## Realistic non-private scenario

One public, non-private 30-second two-speaker speech fixture was executed through
the production Word Timeline worker path:

- audio: `pyannote.audio` packaged sample `sample.wav`, 16 kHz mono, 30.0 s,
  SHA `c319b4abca767b124e41432d364fd7df006cb26bb79d09326c487d606a134e6e`;
- transcript: the package's published `sample.stm` converted to SRT,
  SHA `933ef3dc573d93b5768057d2f232f132b50d80f67bb494903ce618b08c8899a2`;
- evidence: `/private/tmp/integra-wp2-realistic.qp5F7V/word_timeline.worker-evidence.json`.

The scenario failed closed before alignment because the fixture transcript is
English and the pinned production Word Timeline worker explicitly requires a
Russian transcript:

`ValueError: word alignment currently requires a Russian transcript`

This is a deterministic input-contract guard, not the historical #148 failure:
the owner-derived Russian input passed all three attempts. The scenario was not
treated as evidence of a Word Alignment product defect and no repair was made.

## Environment equivalence

The candidate-bound GUI preflight was executed with `/usr/bin/python3` and
reported SeminarText commit `970bde598ddd649599295139986933e0e06cb9c0` from the
bundled personal runtime. The actual Word Timeline worker was launched only by
the exact Python 3.13 path recorded in the candidate manifest. This explicitly
guards against the historical Python 3.14-versus-`/usr/bin/python3` identity
ambiguity.

## Competing explanations

| Explanation | Evidence | Classification |
| --- | --- | --- |
| Historical input/runtime intermittently fails in Word Timeline | Same owner WAV/SRT, exact current model/runtime, three isolated attempts all exit 0 with identical 174-word output | Not reproduced |
| Missing/incorrect worker diagnostics caused the historical top-level error | Controlled failure now persists complete candidate-bound diagnostics; historical candidate lacked them | Observability gap confirmed historically; fixed by WP1 plumbing, not a product repair in WP2 |
| Wrong interpreter identity | Candidate manifest and every attempt bind the exact Python 3.13 worker; GUI contract separately records `/usr/bin/python3` | Excluded for current attempts |
| Non-Russian input | Public realistic fixture fails explicitly at the Russian-language guard | Separate input-contract behavior, not #148 |
| Model/package drift | Candidate manifest and all evidence bind model revision/weights and package tree | Excluded |

## Final classification

`HISTORICAL_NON_REPRODUCIBLE_WITH_INSUFFICIENT_ORIGINAL_DIAGNOSTICS`

The historical #148 failure is **not claimed fixed**. Its original root cause
remains unknown because the original worker diagnostics were not persisted. The
current instrumented candidate did not reproduce that failure in the complete
bounded protocol: observability preflight passed, all three owner-derived
attempts passed, and the one realistic non-private scenario exercised a distinct
explicit language guard. Further historical speculation is stopped unless new
evidence appears.

No WP3 repair specification is authorized by this classification. Any future
WP3 work must retain Candidate-bound observability and add the owner-derived
regression plus a realistic Russian speech/media gate; it must not infer a fix
from this classification.

## Resource and scope compliance

- Owner-derived attempts used: **3 / 3 maximum**.
- Realistic non-private scenarios used: **1 / 1 required**.
- Owner was not asked to test or provide new artifacts.
- No product repair, model/parameter/pin change, or validation weakening.
- No WP3, packaged MCWMA E2E, merge, deploy, or installation was performed.
- No private audio/video was added to Git.

WP2 stops here for owner review.
