# Issue #130 — verified native shutdown

Bounded P1 delivery in `INTEGRA_COMPLETION_PLAN_2026-09-13.md`; this is not
completion of all reliability work or the full application.

## Architecture and behavior

- Native window close and Quit request application-service shutdown. The main
  window remains owned and visible until the result is known. `terminateLater`
  receives its reply in AppKit modal run-loop modes, not only the main dispatch
  queue. This fixes a reproduced use-after-close crash and a reproduced hang.
- Native service calls are serialized; new execute/retry actions are gated
  during termination. The backend lifecycle lock excludes concurrent starts
  from the active-run scan.
- Source-first workers register nonce-bound ownership before input is sent.
  Cancellation is separate from progress JSON, so progress cannot erase it.
- Cancellation freezes the verified process tree before terminating it, using
  kernel birth identity (Darwin libproc; Linux /proc) rather than PID alone.
  Captured children remain identifiable across exec/session changes. Stopped
  descendants are killed without executing fork-capable SIGTERM handlers;
  failed attempts resume only processes stopped by this operation. This favors
  bounded verified termination over arbitrary graceful callbacks. Completed
  files remain; interrupted staging may require later cleanup/recovery.
- The application exits only after `SHUTDOWN_READY`. An unidentified legacy
  active PID is not signalled or falsely marked cancelled; failure leaves the
  app open and visible. Unrelated processes and source files are preserved.

## Evidence levels

- Unit/service regression: ownership, stale PID, cancellation, lifecycle locks,
  state preservation and process-tree boundary cases.
- Native acceptance: actual compiled application, close and Quit with an active
  harmless test recognizer and its SIGTERM-ignoring child; unrelated process
  survives, run becomes CANCELLED, input bytes unchanged.
- Native failure acceptance: unowned legacy PID remains alive and RUNNING;
  application refuses to exit and emits its displayed failure for verification.
- Fixtures are lifecycle tests, **not** ASR quality evidence. All native probes
  use isolated app-data roots; no user runs or private materials are touched.

## Remaining limitations

- Long direct bridge operations already queued (for example clip creation or
  Evidence preparation) drain before shutdown begins. They are not yet covered
  by prompt active-run cancellation. Separate bounded work is needed for fully
  cancellable direct operations.
- Unidentified legacy runs fail closed instead of guessing process ownership.
- Force quit/OS crash is not graceful application shutdown. General restart,
  offline recovery and progress-quality work remain in P1.
- No source-product edits, private transcription, semantic acceptance, cloud
  publication or public release is part of this change.

## Verification record

- Full supported local suite: **606 tests PASS, zero skips, 449.080 seconds**.
- Clean retained macOS build: PASS; native active close, active Quit, ambiguous
  ownership refusal, and actual VideoText media workflow: PASS.
- Full suite also passed clean native build/launch/icon tests and byte-identical
  independently packaged local applications with ad-hoc signature verification.
- Independent review: both reproduced process races repaired; 16 focused
  runtime/UI tests PASS. No remaining blocker for the bounded source-first scope.
- Governance validation and `git diff --check`: PASS.
- Installed old application backed up and inventory/hash equality verified
  before promotion. Installation itself is a separate post-merge step, not
  asserted by these pre-merge results.

Reproduce with a new isolated output directory:

```bash
python3 -m unittest tests.test_shutdown_runtime tests.test_shutdown_ui -v
python3 tests/native_shutdown_probe.py /path/to/Integra.app /new/temporary/output
python3 tests/native_workflow_probe.py /path/to/Integra.app /another/new/output
python3 -m unittest discover -s tests -v
python3 scripts/validate_governance.py
git diff --check
```

The full suite calls `scripts/test_macos_app.sh` (clean native build, icon,
launch, active shutdown and real media workflow) and reproducible packaged-app
tests. Build dependencies use the same supported alignment override documented
in #129; no runtime dependency on that absolute build-machine path is added.
