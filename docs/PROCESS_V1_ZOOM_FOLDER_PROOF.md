# Zoom Folder Evidence

Candidate `candidate-v1-d8bd6fc2649e061d50bfabae37c636d8caeb764965c941cf4fef88ae5fe301a8`
implements **Zoom folder — Excel #5 / S07**. It adds the explicit user action
`Папка Zoom`, while reusing the canonical folder picker, preview/confirmation,
and ordered multi-source ingestion introduced by Excel #4. It adds no second
picker or parallel ingestion architecture.

The S07 discovery contract is recursive and recognizes recording directories,
not arbitrary filenames. For every eligible recording directory it selects the
largest `audio_only.m4a`, otherwise the largest supported audio, otherwise the
largest supported video. Recording directories are ordered by case-folded path.
Alternative audio/video representations in one directory are excluded; distinct
recording directories are retained even if their contents happen to be equal.
Config, chat, transcript, participant-audio, and metadata paths do not enter
the Process source set. An empty or invalid Zoom folder fails before ingestion.

The exact user-visible preview is the exact ordered set handed to the existing
multi-source plan after explicit confirmation. Per-source identity and the
Zoom recognition/order provenance are retained. Generic nonrecursive folder
discovery and single-file import are unchanged.

A read-only probe of the real existing Zoom folder
`/Users/yurielokhin/Documents/Zoom/2026-08-21 13.36.10 Zoom Meeting Yuri Elokhin`
selected only `audio1922670491.m4a`; it excluded `recording.conf` and the
secondary `video1922670491.mp4`. The folder was not changed and processing was
never started. The packaged app opened the native chooser titled
`Выберите папку с записью Zoom`; no source confirmation was performed.

Focused regressions pass `57` tests with `6` declared environment skips. The
packaged macOS suite passes its self-test, bundled-component preflights, real
VideoText workflow, active-run close/quit, stale-run reconciliation, protected
ASR retry, cancellation, and native launch checks. The Candidate manifest and
durable archive are independently validated. The full supported suite passes
`833` tests with `92` declared skips after the Proposal declaration; governance
reports `CURRENT_VALID` and
`PROPOSED_BASELINE_VALID / AWAITING_OWNER_ACCEPTANCE`.

This is a proposed baseline only. It does not begin Zoom playlist, combined
transcript/provenance/corpus, runtime closure, or any work associated with
PR #206.
