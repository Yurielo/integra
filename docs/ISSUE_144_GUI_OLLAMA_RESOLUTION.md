# Issue #144 — packaged GUI Ollama resolution

Date: 2026-09-20
Issue: [#144](https://github.com/Yurielo/integra/issues/144)
Final technical status: `READY_FOR_OWNER_RETEST`

## Owner failure evidence

The owner launched the exact #142 candidate:

`/private/tmp/integra-candidate-issue-142/Integra.app`

The native GUI opened, but New Processing immediately reported:

```text
[Errno 2] No such file or directory: 'ollama'
```

That is real owner-acceptance evidence. It supersedes prior automated assumptions that an interactive Terminal PATH was representative of a macOS GUI launch.

## Root cause

There were two independent bare-name paths:

| Runtime | Previous resolution | GUI consequence |
| --- | --- | --- |
| `seminartext_runtime.preflight()` | `shutil.which("ollama")` only | Minimal Finder/AppKit PATH did not include Homebrew. |
| `videotext_runtime.preflight()` | `subprocess.run(["ollama", "list"])` | A missing shell PATH produced raw `FileNotFoundError`, escaping the capability preflight boundary. |

The owner’s Ollama executable existed at standard macOS locations, including `/opt/homebrew/bin/ollama` and the official application resource path. The defect was Integra executable discovery, not a missing installation, model or component pin.

## Executable-resolution contract

`integra_core.ollama_runtime` is now the shared resolver for the two production preflights. It resolves in deterministic order:

1. Explicit `INTEGRA_OLLAMA` override, when supplied;
2. `ollama` found on inherited PATH;
3. `/opt/homebrew/bin/ollama`;
4. `/usr/local/bin/ollama`;
5. `/Applications/Ollama.app/Contents/Resources/ollama`.

Each candidate is strictly resolved and must be a regular executable. The resolver never invokes a login shell or changes user PATH/Ollama configuration. A missing or unlaunchable executable becomes a factual `ValueError` beginning `Ollama is unavailable: ...`; it no longer becomes raw `[Errno 2]` on New Processing. Capability registry callers can therefore expose an unavailable reason rather than crash unrelated workflows.

## Code changes

| File | Change |
| --- | --- |
| `integra_core/ollama_runtime.py` | New shared deterministic macOS executable resolver and model-list preflight. |
| `integra_core/seminartext_runtime.py` | Uses shared model-list preflight; no bare PATH-only `shutil.which`. |
| `integra_core/videotext_runtime.py` | Uses shared model-list preflight; no bare executable subprocess. |
| `tests/test_ollama_runtime.py` | Regression for GUI-minimal PATH and factual missing-runtime error. |
| `tests/test_videotext_runtime.py` | Regression that missing Ollama cannot raise raw OS error. |

No Ollama installation, configuration, model choice, model/component pin, ASR/Word Alignment behavior, standalone product, or unrelated feature was changed.

## Regression evidence

| Check | Result |
| --- | --- |
| Resolver test with `PATH=/usr/bin:/bin` and a standard-location mock executable | PASS |
| Missing executable returns `ValueError("Ollama is unavailable...")` | PASS |
| VideoText preflight does not leak raw `FileNotFoundError` | PASS |
| Focused resolver/SeminarText/VideoText/capability tests | 20 PASS |
| Non-GUI syntax/diff checks | PASS |

## Fresh isolated candidate

| Field | Value |
| --- | --- |
| Source branch | `codex/issue-144-gui-ollama-resolution` |
| Source parent | `f46bb382cdc6f52eace25f185d7278d547b838b0` (#143 lineage) |
| Candidate | `/private/tmp/integra-candidate-issue-144/Integra.app` |
| Build inputs | Clean #142 Word Alignment runtime at `/private/tmp/integra-word-alignment-runtime-issue-142`; exact existing SeminarText, VideoText and BookText pins |
| Build duration | 60.74 s |
| Bundle | 29,684 files, 2.1 GiB |
| SeminarText CLI SHA-256 | `f7f411bf106341ae970bc40d759e1e3c964273b977bdb12d0f1840e629def13a` |
| Word Alignment model SHA-256 | `d1cdb1a7921de7d363f967a9b0101a713602e109dba62b6f3f9ae2e0b2df0c1c` |

The candidate was built to a new isolated location. The installed/current Integra app was not replaced or deployed.

## Candidate-level validation

| Check | Result | Evidence |
| --- | --- | --- |
| Native self-test | PASS | `INTEGRA_MACOS_SELF_TEST: PASS` |
| Simulated GUI PATH resolver | PASS | `PATH=/usr/bin:/bin` resolved `/Applications/Ollama.app/Contents/Resources/ollama` from the candidate process. |
| Simulated GUI SeminarText preflight | PASS | Bundled personal runtime, `gemma3:4b`, no raw exception. |
| Simulated GUI VideoText preflight | PASS | Supported installed translation model discovered without inherited Terminal PATH. |
| Bundled Word Alignment preflight/import | PASS | Packaged path asserted; actual `whisperx.alignment` import succeeds. |
| Bundled BookText preflight | PASS | Existing declared local Surya/toolchain contract remains explicit. |
| Bundle component smoke | PASS / limited | VideoText media and SeminarText Evidence PASS; BookText not requested in this repeated synthetic smoke because it already passed the real #142 OCR smoke. |
| GUI E2E | NOT_RUN | Owner-only re-test; this automated work did not launch Finder or visible Integra UI. |

## Exact owner re-test

1. Launch exactly `/private/tmp/integra-candidate-issue-144/Integra.app`, not the installed/current Integra app.
2. Open **Новая обработка** with normal GUI launch, not a Terminal-launched process.
3. Confirm the screen does **not** show `[Errno 2] No such file or directory: 'ollama'`.
4. Confirm Topic and Translation capability availability is either ready with the installed models or displayed as a clear factual unavailable reason beginning with the affected capability/Ollama state.
5. Continue only the previously planned bounded owner scenarios; record candidate path, observed preflight state and PASS/FAIL/BLOCKED evidence.
6. Do not mark `USER_ACCEPTED` from this re-test alone. Report any new finding for separately scoped work.

## Final status

`READY_FOR_OWNER_RETEST`

The known owner-facing GUI Ollama resolution failure is fixed and technically verified on a fresh isolated candidate. Owner GUI re-test remains the next gate.
