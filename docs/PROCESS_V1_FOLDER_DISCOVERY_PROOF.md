# Folder Discovery/Confirmation Evidence

Candidate `candidate-v1-e5de327bd01cd38dd6f737ad03ff10dcf5e313e6f4aaaa07788cd0261f394779`
implements Excel #4 / S06 as a native Process selection flow. It adds only
folder discovery and explicit confirmation before the existing multi-source
plan; it does not add recursive collection, Zoom discovery, playlist, corpus,
or another executor.

The native UI presents `Папка с Mac`, opens the system folder chooser, then
shows `Подтвердите источники`. Confirmation is required before sources become
available for result selection and existing plan execution. The displayed order
is the case-folded filename order passed unchanged into the plan.

Focused deterministic coverage is `54 run / 6 declared environment skips /
0 failures`, including bridge discovery, preview-to-plan equality, duplicate,
hidden, unsupported, and symlink cases. Existing application runtime tests
retain source ordering, later-source continuation, failure isolation,
persistence, single-source import, ASR, translation and Topic paths.

The full supported suite ran `830` tests with `92` declared skips. Its three
failures are the expected pre-Proposal CURRENT byte-drift checks for the three
changed governed files; no product test failed. The proposed-baseline overlay
below is the mechanism that closes that intentional governance gap.

The packaged macOS self-test passed with the exact pinned SeminarText,
VideoText, BookText, review-runtime and word-alignment inputs. The Candidate
manifest validates and the durable archive has independently verified byte
integrity. Native interaction is mechanically established by the compiled
AppKit controls and bridge contract; final owner acceptance remains the single
required subjective confirmation of the visible folder chooser/preview.
