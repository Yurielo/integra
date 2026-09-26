# Issue #181 temporary artifact lifecycle evidence

## Cause and bounded repair

Large historical `/private/tmp/integra*` directories came from disposable
Candidate/test callers that supplied an ad-hoc output path to the retained-app
builder. No single process owned the create/use/cleanup lifecycle. The repair
adds a marker-bound disposable-root owner: it records PID, process-start token,
run token, purpose and policy; starts one owned process group; handles normal
exit, failure, SIGINT, SIGTERM and a finite timeout; and deletes only that exact
marked `AUTO_CLEANUP` root. Crash recovery is conservative: the explicit-base
reaper removes only a marked root whose owner is no longer live.

The shell watchdog was corrected to a dedicated Python process. The former
subshell watchdog left a `sleep` descendant after normal completion, so a
wrapper could wait until its timeout despite a successful Candidate. The
replacement has no shell/sleep descendant and is explicitly stopped on normal
completion.

## Disk and retention policy

Candidate checks preflight 3 GiB expected output plus a 5 GiB reserve before
creating the root. Retained evidence Candidates use an explicit non-temporary
output and are rejected under `/tmp` or `/private/tmp`. The lifecycle never
removes current/canonical builds, production runtimes, user data, unmarked
paths, retained evidence, or a live owner root. It uses neither name-glob
cleanup, `pgrep -f` polling, nor a home-wide search.

One isolated bundle copy remains intentional: private pinned runtime/model
payloads are needed for reproducible Candidate hash closure. Hard links or
shared mutable runtimes would break isolation. The repair eliminates retained
copies, not Candidate isolation.

## Final source-bound evidence

Product source A is commit `0fa50284b1a7c1bb63c040972d14e3f885097aed`, tree
`7d3e96aa0beb06de1dad453f3bd6e4fb2872e4a6`. Two sequential isolated full
Candidate builds from this exact source produced
`candidate-v1-f4673faeb53b6d4ca3b71dda9cb383a175cb01c24519f907ec2e9d2cbea5eafc`.
Both passed native self-test and manifest validation, and each left no owned
Candidate scratch root. Focused lifecycle regressions passed 10/10, including
normal/failure, SIGINT/SIGTERM, timeout/process-group cleanup, concurrent-root
isolation, stale/live-owner protection, low-disk preflight and canonical-build
protection.

The source-A repeat on 2026-09-25 also found zero
`integra-scratch-macos-candidate-check-*` roots after completion. No
pre-existing `integra*` directory was touched. Therefore the residual temporary
space from the owned workflow is 0 large Candidate roots.
