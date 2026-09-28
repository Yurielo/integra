# Process v1 Folder Discovery and Confirmation

## Scope

Excel #4 / S06 adds a bounded source-selection step before the existing local
multi-source Process plan. It does not create a second ingestion executor,
recursive collection import, Zoom-folder flow, playlist flow, corpus, or
combined transcript.

## Discovery contract

- The user selects one accessible local folder in the native Process UI.
- Integra considers only direct children. Discovery is non-recursive.
- Candidates are regular, readable, non-symlink files accepted by the existing
  `detect_source` contract: supported local audio/video and supported document
  inputs.
- Candidates are ordered by case-folded file name, then original file name.
  The displayed order is the confirmed and executed order.
- Hidden entries, non-regular entries, unreadable files, unsupported files, and
  repeated content identities are excluded. They never enter the Process plan.
- Equal content identities retain the first item in the deterministic order and
  record later items as `DUPLICATE_CONTENT`.
- An empty eligible set is an honest error. Folder selection alone never starts
  a project, run, or processing worker.

## Confirmation and provenance

Integra shows the discovered supported set and a single explicit confirmation
action before the existing capability selection and plan execution. The frozen
S06 requirement has no per-item removal or reorder control, so the confirmation
is of the complete displayed deterministic set.

Each confirmed source retains its existing source ID and includes the selected
folder, non-recursive method, ordering rule, and ordinal in the persisted plan.
The existing run plan, source plans, copy-on-write import, source hash checks,
ordered execution, per-source failure isolation, and reopen behavior remain the
only execution path. A source that disappears or changes after confirmation is
handled by that existing path without silently widening or changing the set.
