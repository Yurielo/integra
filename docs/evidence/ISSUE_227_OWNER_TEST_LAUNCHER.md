# Issue #227 — Owner Test launcher repair

## Exact failure and cause

The failed launch command ran `temp_workspace_lifecycle.py run`, which starts a
supervised child without allocating a TTY. The child invoked `/bin/bash -lc`;
its standard input was already EOF (`stdin=DEVNULL` in the reproducible
non-interactive execution). `/usr/bin/open` dispatches an app to LaunchServices
and returns unless asked to wait (`open -W`). The following `read -r` therefore
returned immediately with EOF. The shell exited, the lifecycle supervisor
observed its child exit, and it removed the owned workspace while the
LaunchServices app could still be running outside that supervised process.

Reproduction is committed in
`tests/test_issue227_owner_test_launcher.py::test_old_bash_lc_read_failure_reproduces_eof_then_cleanup`:
the lifecycle child reaches the launch stub, prints `OPEN_REACHED`, immediately
prints `READ_RETURNED` with no keyboard input, and lifecycle events show cleanup
of that same workspace. This establishes stdin EOF plus detached launch as the
cause; it is not a K2 product/semantic failure.

## Bounded repair

`scripts/launch_k2_owner_test.py` provides one command for the exact retained
Candidate. It re-verifies the Candidate archive, makes a separate owned
execution copy, prepares and checks the synthetic Issue #236 K2 fixture, then
starts the copied app's native GUI executable in the lifecycle-supervised
process group. It does not use a shell prompt, TTY, `read`, or LaunchServices
detachment. `--wait-for-child-exit` disables wall-clock expiration only for
this interactive session; parent cancellation still terminates and waits for
the supervised process group before cleanup. Normal cleanup occurs after the
GUI process exits.

The optional `--verify-launch` validation mode uses the app's existing
launch-observation probe, which exits after its visible-window marker is
written. It is not the Owner Test command and does not make semantic choices.

## Verification

- Candidate ID: `candidate-v1-0f69e617c0841f27afe2238a28d6c25ae5a80ce0fedf01cf0c114638de575032`
- Bundle: `3d4d33a983455572157b06460c3faaef5afd0b977a0e3d2717101588a25718e5`
- Manifest: `3aed49cda900a6af0d0e8abcae4f3db114d988ad9bf16c62c53ba6671d06cbfe`
- Archive verification before and after launch probe: `COMPLETE`; inventory SHA-256 remains
  `d07e2a9692c85ef28d92d4ba97b4a0be0bf4d9d33d0365b0110689245963b25f`.
- Packaged native GUI probe: `PASS`, observed
  `LAUNCHED visible=true workflow=source-first title=Integra — Новая обработка`.
- Synthetic fixture setup: `2 reviewed units → 2 Concepts → 1 Relation`; QA-only,
  no K2 apply, no semantic product acceptance.
- Session regression: workspace and fixture remained present while the fake
  GUI process was live; it was cleaned after the process exited; an immutable
  Candidate sentinel stayed byte-identical.
- Focused launcher/lifecycle tests:
  `python3 -B -m unittest tests.test_issue227_owner_test_launcher tests.test_temp_workspace_lifecycle -v` — 19 passed.
- Full supported suite, using a lifecycle-owned execution copy of the exact
  Candidate's review runtime (never importing from the retained archive):
  `./scripts/run_review_tests.sh` — 1,232 passed, 130 skipped, 480.789 seconds.
  The 130 skips are the suite's declared unavailable pinned-source/media or
  explicit-reference conditions; the suite finished `OK`.
- `python3 -B scripts/validate_governance.py`: PASS;
  `python3 -B scripts/check_agents.py`: PASS;
  `git diff --check`: PASS.
- Post-suite archive reverification: `COMPLETE`, 29,626 files,
  app size 2,202,205,078 bytes, retained size 2,202,212,083 bytes, with the
  same inventory SHA-256 above.
- The first full-suite attempt without the required review-runtime path failed
  during test import (`ModuleNotFoundError: jsonschema`). A second attempt
  initially inherited the temporary workspace marker and one retention test
  correctly retained its lease until workspace cleanup. The final supported
  run supplied the exact Candidate review runtime from an owned execution copy
  and removed only the transient workspace environment from the test process;
  all 1,232 tests then passed. No code or Candidate bytes were changed to
  address either environment setup issue.
- Product code, Candidate archive, CURRENT, Process Board, and accepted
  semantic artifacts were not changed.
