# WP3 — Primary Journey Stabilization Evidence

Status: `READY_FOR_SINGLE_OWNER_ACCEPTANCE` — repair cycle 1 Owner Entry Gate is green; not `USER_ACCEPTED`.

This report is evidence for Issue #156 on `codex/stabilization-mcwma` / PR #154. The
prior rejected product/evidence HEAD was `59c14d0759790eb4c1f53fc0a4e1098dc1597a01`;
repair cycle 1 is bounded to deterministic Word Timeline ffmpeg resolution. No
component-pin, model, ASR, Topics, secondary-capability, merge, deploy, or owner
retest action was performed. Secondary capabilities remain frozen.

## Owner Acceptance Failure — exact run and root-cause diagnosis

The single authorized owner acceptance attempt was rejected before repair. No owner
retest has been requested or performed; the rejected candidate remains historical
pre-repair evidence.

### Exact failed owner run

| Field | Evidence |
|---|---|
| Project | `urn:integra:project:e39e4c96-dc28-4bb5-91f9-c6f8a16a01fc` |
| Run | `urn:integra:run:e6462138-47c2-485a-9461-1a31f3a68bd5` |
| Job | `urn:integra:job:c236a2c1-936e-40bf-85c4-d0c4ac94a3dd` |
| Created / started / failed | `2026-09-21T19:36:46Z` / `19:36:47Z` / `19:37:26Z` |
| Stage / progress | `word_timeline` / `85` |
| GUI result | `Processing` → `Ошибка`; `completed_sources=0` |
| User-visible error | `Word Timeline worker did not produce a validated output` |
| Source SHA-256 | `9faa1c03460aad1e8867593d28db1f140d0c839879a569ac362cb6a5eaf6ce6c` |
| Candidate ID / bundle digest | `candidate-v1-a9c599ce6e958da69f3207a14871a8d8af31d24a296b11e71e9fa4269e5b1dab` / `991ee9d6f64df1c97ce74c62552b2fe8aa4eb84c2b10953066e16edb329545e9` |
| Failed-run JSON | `/Users/yurielokhin/Library/Application Support/Integra/projects/e39e4c96-dc28-4bb5-91f9-c6f8a16a01fc/runs/e6462138-47c2-485a-9461-1a31f3a68bd5.json` |
| Failed-run JSON SHA-256 | `f852cef104641ce5221a7825034718a094857843c00926704b735d71bc745489` |
| Candidate-bound diagnostic | `/Users/yurielokhin/Library/Application Support/Integra/projects/e39e4c96-dc28-4bb5-91f9-c6f8a16a01fc/artifacts/c236a2c1-936e-40bf-85c4-d0c4ac94a3dd/word_timeline.worker-evidence.json` |
| Diagnostic SHA-256 | `08509ee4f4a4bef34c39d4a723d5e52a8b1d7525f0f42fe779a6778c89f7a748` |

The diagnostic is bound to the exact rejected candidate and records the same
Word Python, model revision/weights, worker path, and owner-derived input hashes:

- audio/WAV: `acf25b9ac68a11dc3f0fd193ec67283843e856a4a190a8e4cb2f35fcfa3df67c`;
- SRT: `af17d83246dedc55dbef5aa0ff2059461dd263415dac1ce32e7d993c007c3492`;
- model revision: `2329100508896c6d9b157019803ab5601e6f3406`;
- model SHA-256: `d1cdb1a7921de7d363f967a9b0101a713602e109dba62b6f3f9ae2e0b2df0c1c`.

The decisive stderr is:

```text
File ".../whisperx/audio.py", line 61, in load_audio
  out = subprocess.run(cmd, capture_output=True, check=True).stdout
FileNotFoundError: [Errno 2] No such file or directory: 'ffmpeg'
```

Exit status was `1`; no Word Timeline output was produced and the validator
correctly returned `worker_nonzero_exit_or_missing_output`.

### Comparison of owner GUI, WP3 E2E, and controlled probe

| Path | Inputs/candidate | Launch environment | Result | What it proves |
|---|---|---|---|---|
| Owner GUI primary journey | owner WAV/SRT hashes above; rejected final candidate | Finder/launchd-style minimal environment; inherited PATH has no Homebrew `ffmpeg` | FAIL at audio load | Real production failure is deterministic and downstream of ASR; transcript/SRT had already been produced |
| Deterministic packaged E2E | run `urn:integra:run:5205a5ab-32cc-4177-893d-112bc08fee31`; final candidate; evidence SHA `5028a393fa1304d4e076b711e276dc0c8c2b8f2686931a7a4023630a83ec0ec7` | Shell harness; Homebrew PATH available | PASS | Production bridge orchestration works when bare `ffmpeg` resolves |
| Realistic packaged E2E | run `urn:integra:run:72be84a5-51e0-48cb-8fb8-f10227f6cf4e`; final candidate; evidence SHA `10852dc07672120980c71d2f2df6a135bded33b04ad6ad202b37136230dfede7` | Shell harness; Homebrew PATH available | PASS | Natural-Russian path does not exercise Finder PATH semantics |
| Owner-derived direct Word Timeline regression | owner WAV/SRT hashes above; evidence SHA `29bf456dae04e231a00c30288d02b02c5682f4fc85b944b6a60232da05e2e2cd` | Shell harness; Homebrew PATH available | PASS | Same content/candidate passes only under the non-GUI environment |
| Controlled failure/recovery probe | same packaged candidate; test-only fake alignment worker | Shell harness; fake worker masks WhisperX/ffmpeg | PASS recovery | State/retry semantics only; not an ffmpeg integration test |

The deterministic and realistic evidence therefore did not contradict the owner
failure: both were run with a materially different PATH. In addition,
`tests/native_workflow_probe.py` inherits the invoking shell environment, while
the test-only retry probe replaces the real alignment worker. Candidate evidence
sanitization intentionally omits the full PATH and therefore did not expose the
condition that decided the outcome. This is the false-positive Owner Entry Gate:
the gate treated shell-launched PASS evidence as GUI-equivalent although the
production GUI launch contract was not exercised.

### Root-cause classification

**Product failure (confirmed):** `macos/IntegraApp.swift` and
`macos/Resources/bridge.py` preserve the caller's environment; the Word Timeline
runtime preflight validates Python/site-packages/model but neither resolves nor
validates `ffmpeg`. `word_timeline_runtime.generate_word_timeline()` launches the
candidate worker without a deterministic ffmpeg binding, and WhisperX invokes the
bare command `ffmpeg`. Finder/launchd therefore fails before alignment whenever
Homebrew's directory is absent from PATH. The owner traceback, exact candidate,
and identical owner WAV/SRT hashes establish this as a deterministic launch-path
failure, not an intermittent model/content failure.

**Owner Entry Gate false positive (confirmed):** automated “GUI-equivalent” E2E
and the direct owner-derived regression were shell-launched with Homebrew PATH;
the recovery probe used a fake worker; and sanitized evidence omitted PATH. The
three checks could therefore all PASS while the actual Finder-launched primary
journey failed on the same candidate and content.

### Bounded repair and regression specification (no implementation in this step)

1. Add the smallest candidate-bound production repair: resolve the existing
   pinned ffmpeg identity (or an explicit candidate-bound runtime path), pass a
   deterministic executable/path to the Word Timeline worker, and fail closed in
   preflight when it is unavailable. Do not change model/component pins or ASR
   semantics.
2. Add a packaged/native regression that launches the real WhisperX worker under
   a Finder-like minimal PATH using the owner-derived WAV/SRT hashes; it must
   reproduce the current `FileNotFoundError` before repair and PASS after repair
   on the same candidate contract.
3. Record safe observability for resolved ffmpeg path and identity (path plus
   SHA-256, not credentials or an unbounded raw PATH) in Candidate-bound
   diagnostics. Run deterministic, realistic, and owner-derived checks through
   the same minimal-environment contract; keep the controlled retry probe as a
   state/recovery test only.
4. After an authorized repair, build a new candidate and rerun all mandatory WP3
   gates. Do not request owner retest until that evidence is green.

This diagnosis is complete with sufficient evidence. The candidate remains
owner-rejected; no code change, rebuild, owner retest, merge, or deploy is
authorized by this step.

## Repair cycle 1 — corrected Candidate and Owner Entry Gate

The pre-repair failure-class evidence was preserved before the bounded repair in
`docs/evidence/WP3_FFMPEG_PRE_REPAIR_REGRESSION.json`. It uses the exact rejected
Candidate, real WhisperX worker, owner-derived input hashes, Finder-like
`PATH=/usr/bin:/bin:/usr/sbin:/sbin`, exit status `1`, and the real
`FileNotFoundError: ... 'ffmpeg'` traceback. No fake worker was used for that
regression.

### Bounded product/evidence change

`integra_core/word_timeline_runtime.py` now resolves ffmpeg in this order:

1. explicit `INTEGRA_FFMPEG`;
2. fixed standard macOS locations (`ffmpeg-full` Homebrew prefix, Homebrew and
   `/usr/local`, then system locations);
3. no inherited PATH lookup.

Preflight verifies executable availability and `--version`, and records path,
version, SHA-256, resolution source, and bounded PATH classification. The real
worker receives a bounded PATH containing the resolved executable's parent plus
system directories. Candidate manifest execution identity binds the same
ffmpeg path/version/SHA. If resolution fails, Word Timeline fails closed before
worker execution. ASR, Word Alignment model, component pins, Topics, and output
semantics are unchanged.

### Final repair Candidate

| Identity | Value |
|---|---|
| Candidate path | `/private/tmp/integra-wp3-repair1-finalbuild.j9dBzZ/Integra.app` |
| Candidate ID | `candidate-v1-c5851d168b116fed83109014519ebc01c0291e23705ac9d2ec0a4e5df2471960` |
| Bundle SHA-256 tree digest | `90c6c816c7f4ec82b8a3393c46a5a96239ce7cbc16ba50a83677d78a0cdea8cb` |
| Candidate source HEAD | `da51a1c528a3b720a7ba97adcc4c1f26085f8232` |
| SeminarText commit / CLI SHA-256 | `970bde598ddd649599295139986933e0e06cb9c0` / `f7f411bf106341ae970bc40d759e1e3c964273b977bdb12d0f1840e629def13a` |
| Word Alignment model revision / weights | `2329100508896c6d9b157019803ab5601e6f3406` / `d1cdb1a7921de7d363f967a9b0101a713602e109dba62b6f3f9ae2e0b2df0c1c` |
| Resolved ffmpeg | `/opt/homebrew/Cellar/ffmpeg-full/9.0.1/bin/ffmpeg` |
| ffmpeg version / SHA-256 | `ffmpeg version 9.0.1` / `58b8f5171449c6d3174173d84409a35682b1ab157e2e24b4023a8d8b329d7e3d` |
| Resolution source | `standard:/opt/homebrew/opt/ffmpeg-full/bin`; `uses_inherited_path=false` |

### Corrected mandatory gates — all bound to the final Candidate

| Gate | Evidence | Result |
|---|---|---|
| Fresh isolated build, manifest validation, native self-test | Candidate above; `INTEGRA_MACOS_SELF_TEST: PASS` | PASS |
| Deterministic Russian full packaged bridge journey, minimal PATH | run `urn:integra:run:9302ceaa-7c75-4527-b9f1-fbb1b7191aee`; Word Timeline evidence SHA `8ba6246b653273525ebf71496aa6561abdb629154747261f709a6d1a0a2822c1`; Topics and navigation (2 segments) persisted | PASS |
| Realistic natural-Russian full packaged bridge journey, minimal PATH | run `urn:integra:run:4b0754c0-0a7d-47ea-8043-5efcfabf1237`; Word Timeline evidence SHA `69eccc1843ce3820f0388f81d69d2cfed0e76f37723aad99ee2fabac16a1cb65`; Topics and navigation (12 segments) persisted | PASS |
| Owner-derived real WhisperX regression, minimal PATH | owner WAV `acf25b…`, SRT `af17d8…`; evidence SHA `c736c315fe3e46ff563e0f79f872d36911b944072ee92ccb3d31d76b21c36c50`; 174 words | PASS |
| Controlled failure → subsequent successful run without restart | failed run `urn:integra:run:f6814a1d-e860-4a44-bf7b-a779939fad5e`, exit 23; subsequent run `urn:integra:run:d215d69d-533a-49e0-a9a0-11863c32d1c1`; retry evidence SHA `27fd22f3b334b8fa8d3f6b7055b5e5ab7b4796a0e580c7897edaae981d2ca915` | PASS |
| Focused resolver/runtime tests | `7 passed` (`tests/test_word_timeline_runtime.py`, `tests/test_candidate_identity.py`) | PASS |
| Targeted ASR/project-transcribe/integration tests | `30 passed, 26 skipped` | PASS |
| SeminarText ASR quality-gate contract | pinned checkout `tests/test_asr_quality_gate.py`: `7 passed` | PASS |
| Governance validator and shell/diff checks | `INTEGRA_GOVERNANCE_VALIDATION: PASS`; `bash -n`; `git diff --check` | PASS |
| GitHub Quality Gate | run `35655422848`, job `106517637471`, PASS on product/evidence HEAD `754cb885dece72d8f4d284939138a5095178b8c9` | PASS |

The final Candidate was built from clean product/evidence source HEAD
`da51a1c528a3b720a7ba97adcc4c1f26085f8232`; the later `754cb88…` commit only
binds the portable CI ffmpeg test fixture and does not alter the Candidate bundle.
The previous shell-only false-positive condition is explicitly absent from every
corrected Word Timeline evidence record: `uses_inherited_path=false`, with the
same resolved ffmpeg SHA-256. The old Candidate's PASS evidence is not reused.

The complete local suite ran `567 passed, 73 skipped, 2 failed` (118 subtests).
The two failures are unrelated worktree packaging failures: both scripts tried
to use the absent local `.runtime-components/seminartext-pinned` checkout before
any GUI action (`scripts/test_macos_app.sh` and `scripts/package_ready_app.sh`).
They do not affect the isolated Candidate gates above and were not repaired.

The numbered sections below preserve the prior WP3 pre-repair evidence for
lineage. Where they mention Candidate `candidate-v1-a9c599…` or the former
Owner Entry Gate, those values are historical and are superseded by the repair
cycle 1 section above.

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

The previous technical handoff used exactly one candidate:

`/private/tmp/integra-wp3-cleanbuild.91e4OE/Integra.app`

That candidate is now owner-rejected after the exact failed run recorded above.
This report does not authorize another owner attempt or claim user acceptance.
