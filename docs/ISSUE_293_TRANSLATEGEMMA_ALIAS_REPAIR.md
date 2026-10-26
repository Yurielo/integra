# Installed TranslateGemma compatibility repair — Issue #293

Date: 2026-10-26 (Europe/Istanbul).

Terminal state: **OWNER_ACTION_REQUIRED**. `READY_FOR_OWNER_TEST: NO`.
This is an implementation and evidence package in [draft PR #294](https://github.com/Yurielo/integra/pull/294),
not an accepted baseline, retained Candidate, installation or completed migration
of the installed application. Tracking: [Issue #293](https://github.com/Yurielo/integra/issues/293).
Exact machine-readable results: [evidence](evidence/ISSUE_293_TRANSLATEGEMMA_ALIAS.json).

## Verified problem and architecture review

The requested dependency audit was read first:
`/Users/yurielokhin/AI/research/qwen3-8b-dependency-audit-2026-10-26/REPORT.md`.
Its installed-app finding is reproducible: the READY_APP bridge still selects
`qwen3:8b`. Its bridge SHA-256 is
`2d2708bcc3052d1a1f088db2e77cd5d6c6885376917242fc2de33616db60b844`.
That application has no embedded Candidate manifest; its exact Integra build
commit cannot be established. Its bundled bridge and worker source differ from
current canonical source. It was not generated from the current source tree.

The audit's source inspection used an old dirty checkout. Canonical `main`
`2522960f486213a4e1d89ee4735c0a9c56167f93` already contains the completed
TranslateGemma migration (#218) and subsequent accepted baseline. The active
Integra inference adapter is `integra_core/translategemma_runtime.py`;
VideoText remains the pinned owner of subtitle/media operations.

Independent architecture review confirmed that importing a second inference
implementation from newer standalone VideoText would duplicate the accepted
adapter. The accepted four-product planning direction preserves the existing
product-specific adapters and distinct translation profiles. This task does
not implement a shared translation service or adopt further roadmap proposals.

The remaining source defect was reproduced: canonical preflight rejected the
installed `translategemma:4b` because it required the absent registration
`translategemma:4b-it-q4_K_M`. The installed alias has the exact governed full
manifest digest `c49d986b0764f5881c476eb21435bb62b7abc62347aab3d4a6071e811be510a1`
and weights `bdbf939b402e2f88fbe3e918beb777813009335756b4c17be7fe008dfe4815d4`.

## Bounded implementation

The existing adapter now resolves only that installed alias when the canonical
tag is absent. A present wrong or duplicate canonical registration fails closed;
it cannot be hidden by a valid alias. Daemon identity, the selected tag's actual
local manifest and all layers retain full hash validation. The actual request
tag is checked before and after each response and the returned model must match.

Artifacts retain the canonical model identity. Alias execution additionally
records `request_model` and hashes it into the runtime identity, separating reuse
and provenance from canonical-tag execution. The canonical-only preflight shape,
prompt, languages, request options, cue IDs/timing and review-required semantic
status remain unchanged. There is no Qwen fallback or model registration change.

Two implementation hash entries are updated in the proposed branch; CURRENT,
acceptance statuses and authority are unchanged. Runtime-enabled tests exposed
two pre-existing fixture defects: Process still asserted a historical VideoText
commit field, and the mixed-media callbacks omitted current diagnostic/detail
arguments and detail provenance. Only those test expectations/stubs were repaired.
Independent review confirmed the assertions remain meaningful.

## Verification and limits

- Independent QA/review: 106 tests PASS, zero failures, errors or skips, using
  exact pinned SeminarText and the unchanged VideoText worker. This includes
  Process, Topic/TXT, legacy Qwen artifact compatibility, Media/Studio contracts
  and actual VideoText subtitle/media operations.
- Standalone VideoText translation adapter probe and retired-model guard: PASS;
  its source working tree and installed binary hashes remain unchanged.
- Real synthetic RU→EN and EN→RU translation: PASS, both from source and from
  the built application's bundled adapter. Nonconsecutive cue IDs, exact clocks
  and source bytes were preserved. This is technical evidence, not semantic
  acceptance or a general translation-quality benchmark.
- One disposable native build from clean `f1d7499dbbcb07fba1272d9737fb4ecc9ae7e328`:
  native self-test and two manifest validations PASS. Its bundle digest remained
  `0147f1a0ff7d740fd4f66847da906f6dd821833e5f1419b18e63d2bd07f74edc` before/after
  checks. Later commits change only tests/evidence, with identical production,
  build and schema inputs. The standard supervisor disposed the app and released
  its leases. No full application bytes are retained for owner review.
- The supported full suite and governance/CI gates are **not PASS**. Completed
  counts and exact failing checks are retained in the JSON evidence and logs.
  CURRENT drift cannot be suppressed or self-accepted to make them green.

## Exact lifecycle boundary

Authority: [Candidate retention](CANDIDATE_RETENTION.md),
[bounded retention](BOUNDED_CANDIDATE_RETENTION.md), and
[Proposal Lite](PROPOSED_BASELINE_LITE_IMPLEMENTATION.md). These accepted rules
require retained application bytes and explicit scoped owner acceptance; a
disposable proof or technical green result cannot replace either requirement.

The supported retained-build preflight refreshed and verified canonical
protection, retained every package, and rejected admission: **8 full copies**,
**18,292,744,192 allocated bytes**, zero eligible terminal copies,
`BUILD_HEADROOM_REJECTED / 8_COPY_OR_20_GIB_CAP`. No archive was deleted or
modified. The eight-copy limit independently blocks another retained Candidate.
The separate supported `archive_copy=False` admission allowed the disposable
test build; it does not supply a retained Candidate or Proposal Lite.

CURRENT/K1 remains `candidate-v1-675acf457d65e7633481bcea700036b7e9ef6298e0c6d6eb097e513d3bff249f`.
The canonical protection registry, K2 proposal, source products, installed
applications and all model registrations are preserved. The installed Integra
still requires Qwen; its replacement has not been proven or performed.

Continuation requires an independently authorized lifecycle resolution that
restores normal retained-Candidate admission. Then build/archive the exact
Candidate, prepare Proposal Lite, pass full governance/CI, obtain the applicable
owner acceptance and complete any separately authorized promotion/installation.
No owner is asked to pick archive IDs, no ninth archive is created, and no
existing pending proposal is silently withdrawn. Qwen removal additionally
requires all active dependencies and installed-build replacement to be proven
and separately authorized; this task grants no removal authority.

Repository governance and source-integration Product Rules were read. No rule
or architectural ownership change is adopted by this proposal. Participating
evidence roles: coordination, backend implementation, independent architecture,
independent QA/PR review, and CI/CD native verification.
