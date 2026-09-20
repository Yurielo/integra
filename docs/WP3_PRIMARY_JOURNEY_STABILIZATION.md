# WP3 — Primary Journey Stabilization Evidence

Status: `READY_FOR_SINGLE_OWNER_ACCEPTANCE` (technical handoff only; not `USER_ACCEPTED`).

This report is evidence for Issue #156 on `codex/stabilization-mcwma` / PR #154. Final
evidence/report HEAD: `59c14d0759790eb4c1f53fc0a4e1098dc1597a01`. No
product repair, component-pin change, semantic change, merge, deploy, or owner
request was made. Secondary capabilities remained frozen.

## 1. Prerequisites

| Check | Result |
|---|---|
| Accepted entering baseline HEAD | `b1f2621cdf5b9fa6982d9625b5e23eb811d994a2` (historical WP3 entry baseline) |
| PR #154 head before WP3 | exact accepted HEAD |
| Prior GitHub Quality Gate | run `35535680951`, PASS |
| WP2 report | present; classification `HISTORICAL_NON_REPRODUCIBLE_WITH_INSUFFICIENT_ORIGINAL_DIAGNOSTICS` |
| Product changes entering WP3 | none; WP2 added documentation only |
| Evidence-backed repair cycles | 0 (no mandatory-gate defect reproduced) |

## 2. Final isolated Candidate

The governed build was run into a new isolated output directory using the existing
`scripts/build_macos_app.sh` inputs and exact WP1 component/runtime pins. The final
bundle is not installed and does not replace `current-build`.

| Identity | Value |
|---|---|
| Candidate path | `/private/tmp/integra-wp3-cleanbuild.91e4OE/Integra.app` |
| Candidate ID | `candidate-v1-a9c599ce6e958da69f3207a14871a8d8af31d24a296b11e71e9fa4269e5b1dab` |
| Bundle SHA-256 tree digest | `991ee9d6f64df1c97ce74c62552b2fe8aa4eb84c2b10953066e16edb329545e9` |
| Build source snapshot | `b1f2621cdf5b9fa6982d9625b5e23eb811d994a2` (clean; product source unchanged by evidence-only commits) |
| SeminarText commit | `970bde598ddd649599295139986933e0e06cb9c0` |
| SeminarText CLI SHA-256 | `f7f411bf106341ae970bc40d759e1e3c964273b977bdb12d0f1840e629def13a` |
| VideoText commit | `2e098d1705b6815628bee1e023f4742718eabf02` |
| BookText commit | `46396649214275eb18054b670a842bace02d02e1` |
| Word Alignment revision / weights | `2329100508896c6d9b157019803ab5601e6f3406` / `d1cdb1a7921de7d363f967a9b0101a713602e109dba62b6f3f9ae2e0b2df0c1c` |
| GUI Python | `/usr/bin/python3`, Python 3.9.6 |
| Word Timeline Python | `/opt/homebrew/opt/python@3.13/bin/python3.13`, Python 3.13.15 |
| Ollama | 0.33.1, exact packaged model `gemma3:4b` available |

The candidate manifest was generated and validated before the gates. The product
tree between the accepted build input and the final build is byte-identical; the
new candidate is nevertheless isolated and has its own manifest/evidence closure.

## 3. Production-path equivalence

Both successful journeys entered the packaged `Contents/Resources/bridge.py` and
used the same production sequence:

`detect-sources → capability-registry → build-plan → execute-plan → spawned
process-plan/execute_run → bundled SeminarText ASR → bundled Word Timeline worker →
bundled SeminarText Topics worker/Ollama → persisted run/artifacts → run-status /
media-navigation`.

No mock worker, alternate test orchestration, source-tree runtime, or fake Ollama
response was used for either primary journey. Headless automation replaced only
GUI presentation/clicking.

## 4. Fixture A — deterministic Russian gate

| Field | Evidence |
|---|---|
| Fixture | `/private/tmp/integra-issue-148-phase1-probe/generated-russian-speech.mp4` |
| Provenance | Existing deterministic Russian speech fixture from the Issue #148 probe; synthetic bounded fixture only (not realistic evidence) |
| Duration / SHA-256 | 7.464989 s / `db0cbfd61a3861442114d27633d0b8115af792f6532674298886d86fd57cf3e4` |
| Candidate-bound run | `urn:integra:run:5205a5ab-32cc-4177-893d-112bc08fee31` |
| Run terminal state | `COMPLETED` |
| Source state | `COMPLETED`; source id `urn:integra:source:f8f2239a-599c-5f4a-98de-ae7f60436efa` |
| TXT SHA-256 | `2293db7c751eaf796116e44c584f9c1fc4000afdc8ab4149d9cf8f6cff6f8fd7` |
| SRT SHA-256 | `92a597c6ae39f4dce3e0990c25cfeb89286a1f22f6caf6a25a6c14354ed1aa3e` |
| Word Timeline SHA-256 | `616e2bd2778b9a98a80a06998369b8027c1ab09db83a072bb1a30c95bf3d19ec`; 18 words |
| Topics SHA-256 | `81aa628a738240bc3d7c51b84c8b8cae0859d9aaf9466fef3c7218d4f0ee7953` |
| Navigation evidence | `media-navigation` result SHA `4768a3a39bf3e21c7f333e1984dec06a1c1fdf3190474a5ce943ee3e1219718a`; 2 timed segments |

All 15 mandatory stage/result checks passed: ingestion, preflight/registry, plan,
real ASR, TXT, SRT, real Word Timeline, validation, Topics execution/validation,
persistence, navigation, terminal state, bounded diagnostics, and no normal-status
raw exception.

## 5. Fixture B — realistic public natural Russian

| Field | Evidence |
|---|---|
| Fixture | Wikimedia Commons `File:Lenin - About Natural Tax.ogg` |
| Source URL | https://commons.wikimedia.org/wiki/File:Lenin_-_About_Natural_Tax.ogg |
| Direct media URL | https://upload.wikimedia.org/wikipedia/commons/e/eb/Lenin_-_About_Natural_Tax.ogg |
| Provenance/licence | 1921 Russian gramophone speech; Wikimedia Commons marks the work public domain (Public Domain Mark 1.0). No private owner media. |
| Local fixture | `/private/tmp/integra-wp3-realistic-lenin/fixture.ogg` |
| Duration / bytes | 130.861769 s / 1,164,240 bytes |
| SHA-256 | `00270ff4b993a1bdc77304256f7fb6b32fa54afc73c59388561d123830d79c98` |
| Candidate-bound run | `urn:integra:run:72be84a5-51e0-48cb-8fb8-f10227f6cf4e` |
| Run terminal state | `COMPLETED` |
| Source state | `COMPLETED`; source id `urn:integra:source:8f62a21e-04e2-5316-824a-3f314d1671de` |
| TXT SHA-256 | `8dc5bac1d6184f7b725fa19524dfab4d4ce4f700e6d7bff033d438acc7fe2305` |
| SRT SHA-256 | `2ca65c80d93ee4a6438b2d31c87081465a274b70e17b5ed40f4cf4e7cc7084b0` |
| Word Timeline SHA-256 | `16911a37af50a6fa31049fa2e46d8bac20fb9af3b46f66f1b5a671e414093b65`; 111 words |
| Topics SHA-256 | `aac6a7f13e8397308fa2f5da81543382836f2d6efd8269f1bc7a00d547a40863` |
| Topics runtime | bundled SeminarText commit `970bde…`, production model `gemma3:4b`; two topics, `qa_status: ok` |
| Navigation evidence | `media-navigation` result SHA `0b8e938ca0e179c4c2d4aeeb1c7bb8246e9ce5a4f69c200264dda51e615558af`; 12 timed segments |

The actual speech reached ASR, SRT, Word Timeline (not the English-language guard),
and Topics. All mandatory primary-journey checks passed.

## 6. Historical owner-derived Word Timeline regression

The authorized local regression uses the already-preserved owner-derived WAV/SRT
only; neither input is copied into Git.

| Field | Evidence |
|---|---|
| Audio SHA-256 | `acf25b9ac68a11dc3f0fd193ec67283843e856a4a190a8e4cb2f35fcfa3df67c` |
| SRT SHA-256 | `af17d83246dedc55dbef5aa0ff2059461dd263415dac1ce32e7d993c007c3492` |
| Output SHA-256 | `fadfa03e5bc5926458c75613bf8cf4ab429d8d08c61eb6847a03445872f8b8b9` |
| Word count | 174 |
| Evidence | `/private/tmp/integra-wp3-final-owner-regression-1789938047/word_timeline.worker-evidence.json` |
| Result | `PASS`, candidate ID exact final candidate |

## 7. Controlled failure and subsequent run without restart

The existing native retry probe supplied a bounded, non-destructive test-only
alignment failure. It used the packaged app and one native process; the failure was
not a product repair or a primary success-path substitute.

| Check | Evidence |
|---|---|
| Failure run | `urn:integra:run:cfa12c84-464f-4cb7-8cfb-f1fdc653e12b`, terminal `FAILED` |
| Failure stage/reason | `word_timeline`; `Word Timeline worker did not produce a validated output` |
| Candidate-bound failed evidence | `word_timeline.worker-evidence.json`: candidate exact final ID, result `FAIL`, exit `23`, reason `worker_nonzero_exit_or_missing_output` |
| Preceding artifacts | ASR artifacts persisted and remain inspectable; failed run was not reported successful |
| Subsequent run | `urn:integra:run:226c657c-819f-4bd4-b8d2-13af8c992702`, terminal `COMPLETED` |
| Reuse safety | ASR recognizer count `1`; alignment attempts `2`; second run reports ASR reuse `REUSED`; distinct run IDs |
| Restart | none; same native app process/runtime state |

The recovery gate is therefore PASS without touching failed-run recovery product
semantics.

## 8. Repairs, candidate transitions, and resource budget

No mandatory gate exposed a reproducible product defect. Consequently:

- speculative repairs: 0;
- evidence-backed repair cycles: 0/2 allowed;
- candidate transitions: none; all mandatory PASS evidence is bound to
  `candidate-v1-a9c599…`;
- no Word Alignment, ASR, Topics, pin, or model changes;
- no secondary capability work;
- no owner contact or private-media request.

## 9. Owner Entry Gate

| Gate | Result |
|---|---|
| Clean governed build | PASS |
| Candidate manifest generation/validation | PASS |
| Native self-test | PASS (`INTEGRA_MACOS_SELF_TEST: PASS`) |
| GitHub Quality Gate | PASS, final run `35537652581` / job `106149447789` on final HEAD `59c14d0759790eb4c1f53fc0a4e1098dc1597a01` |
| Runtime/component identity | PASS |
| Deterministic Russian packaged E2E | PASS |
| Realistic Russian packaged E2E | PASS |
| Historical owner-derived Word Timeline regression | PASS |
| Topics production execution/validation | PASS |
| Persistence/navigation | PASS |
| Controlled failure diagnostics | PASS |
| Subsequent run without restart | PASS |

## 10. Frozen/deferred scope

Translation, BookText/OCR, YouTube/playlist, publication/cloud targets, clips,
Marketing/Learning/Assistant/social, signing/notarization/distribution, and broad
roadmap/governance cleanup were not exercised or repaired. They remain outside WP3
and must not be inferred as accepted from this report.

## 11. Handoff

Technical handoff may use exactly one candidate:

`/private/tmp/integra-wp3-cleanbuild.91e4OE/Integra.app`

Open the packaged app through the owner's normal acceptance workflow and test only
the primary journey described in Issue #156. This report authorizes a single owner
acceptance attempt; it does not claim user acceptance.
