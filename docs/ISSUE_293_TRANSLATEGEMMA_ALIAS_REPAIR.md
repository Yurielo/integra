# Installed TranslateGemma compatibility repair — Issue #293

Evidence B snapshot: 2026-10-27 (Europe/Istanbul).

Status at this snapshot: **RETAINED_ENGINEERING_CANDIDATE_VERIFIED**.
`READY_FOR_OWNER_TEST: NO` at Evidence B: declaration C, canonical protection
registration, final full/governance/CI gates and the actual execution-copy handoff
are subsequent steps. Owner acceptance remains null. CURRENT and installed
Integra are preserved.

Implementation: [PR #294](https://github.com/Yurielo/integra/pull/294),
[Issue #293](https://github.com/Yurielo/integra/issues/293).
Exact [finalization result](evidence/issue293-owner-candidate/result.json),
[original manifest](evidence/issue293-owner-candidate/candidate-manifest.json),
[Candidate evidence](evidence/issue293-owner-candidate/candidate-evidence.json)
and [archive receipt](evidence/issue293-owner-candidate/candidate-archive-receipt.json)
are retained. [Earlier implementation evidence](evidence/ISSUE_293_TRANSLATEGEMMA_ALIAS.json)
remains historical.

## Verified problem and architecture review

The requested dependency audit was read first:
`/Users/yurielokhin/AI/research/qwen3-8b-dependency-audit-2026-10-26/REPORT.md`.
Its installed-app finding is reproducible: the READY_APP bridge still selects
`qwen3:8b`. Its bridge SHA-256 is
`2d2708bcc3052d1a1f088db2e77cd5d6c6885376917242fc2de33616db60b844`.
That application has no embedded Candidate manifest; its exact Integra build
commit cannot be established. Its bundled bridge and worker source differ from
current canonical source. It was not generated from the current source tree.

The audit's source inspection used an old dirty checkout. At initial inspection canonical `main`
`2522960f486213a4e1d89ee4735c0a9c56167f93` already contained the completed
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

## Retained Candidate and verified checks

- Clean Source A: `c89a10432733c4540504c469d483f3544f45d048`;
  tree `27b08b0fdd3ad2dac9389ae2b932e885159634e1`.
- Candidate: `candidate-v1-1b29ea21cb9dbab3c423b5770f6f2eb972bb6dcdfbbb694b7a19a0c9db9fc434`.
- Bundle: `0147f1a0ff7d740fd4f66847da906f6dd821833e5f1419b18e63d2bd07f74edc`.
- Original manifest SHA256:
  `708e8482fdf18f451cfefe242ea17e75c66f3b52792405c340568a35677a6753`.
- Native self-test, launch marker `visible=true` with full native title,
  close/termination, two manifest validations, synthetic media-only native
  workflow and bundled GUI-interpreter TranslateGemma preflight: PASS.
  The media workflow produced speed-video/audio-analysis outputs without ASR.
  Preserved screenshots/artifacts are hash-bound in Candidate evidence.
- Critical source/package equivalence and full bundle equality to the original
  valid translation build: PASS. Bundle bytes remained identical before/after
  checks; the validated runtime identity is identical.
- [Real RU→EN/EN→RU inference evidence is explicitly reused](evidence/issue293-owner-candidate/reused-inference-evidence.json)
  from source `f1d7499dbbcb07fba1272d9737fb4ecc9ae7e328`, Candidate
  `candidate-v1-aa93af7487c682f4ccbb55848ee6c48aaf1cc88fde9a724d4b8e3bb5cdd5176c`.
  No fresh inference or semantic acceptance is claimed. Nonconsecutive cue IDs,
  exact clocks and source bytes were preserved in the original real tests.
- Existing independent implementation QA:106/106 PASS, no skips, including
  actual pinned VideoText subtitle/media operations, Process, Topic/TXT,
  legacy Qwen artifacts and Media/Studio contracts. Completed translation tests
  were not unnecessarily repeated.
- First unpublished engineering attempt failed an external assertion expecting
  an incomplete native title. Its marker was not preserved and no visibility
  PASS is claimed for it. Its working app was disposed. The [reviewed repair](evidence/issue293-owner-candidate/native-marker-repair-review.json)
  only matches the unchanged complete native title and preserves markers before
  checking. One [explicit diagnosed retry](evidence/issue293-owner-candidate/native-marker-manual-retry-proof.json)
  passed; product source and all protection/admission guards were unchanged.
- Immutable archive verification/finalization:COMPLETE. Owned build/stage
  workspaces were cleaned. [Post-publication proof](evidence/issue293-owner-candidate/postpublication-preservation-proof.json)
  uses the supported inventory across all managed roots: physical8/8, only one
  new archive, all seven prior paths/identities/allocated bytes and publisher
  records unchanged, unchanged retirement history, no pending leases/deletions.
  Source/installed/model preservation snapshots match.

## Exact authorized lifecycle recovery

The original retained admission failed at8/8. A separate explicit Product Owner
instruction authorized only721d withdrawal, exact hold exception, supported
ownership repair and exact retirement. Persisted [authority](https://github.com/Yurielo/integra/issues/293#issuecomment-6423470249)
binds approved request SHA256
`0f2b9483cd791163b6d2ea97f2f23ec897baa30ee4cbf6e949a07c54b19920ff`.

Merged #297 (`334f3398e299887071dc1ce1ebfe6149bede03ed`) delivered the supported
transaction. Real ownership repair changed only target device16777233→16777232
and its dedicated journal, verifying inode45635682/UID501/full bytes/publisher
and current volume UUID; no historical volume continuity was invented.
Original BEFORE/AFTER receipt hashes remain
`98df8c60953294c7a5da6dcd9e21f676916cbac82e54a5481ecbff729c5a25a2` /
`7bedf61cb0f6875be19e32b1f6515b68eeeaa2902e66a1950b075e32488f4666`.

The first exact executor refused before deletion because the resolver omitted
WITHDRAWN_SUPERSEDED from terminal states. Merged #298
(`1872a57b9f9cce1f28d6519ef03637df24bad3b0`) repairs eligibility with exact
validated authority and full integrity required. Target-only main-observation
refresh requires unchanged authorization/registry/withdrawal bindings; original
ownership receipts remain immutable. Prerequisite PR and post-merge CI passed.
PR298 local full:1214 run,1155 PASS,59 declared skips,0 failures/errors;
Linux CI:1214 run,1095 PASS,119 declared skips,0 failures/errors.

Unchanged cleanup_exact completed transaction
`retirement-v1-0055fb6169914c8cbd85f50636d54de7` for only
`candidate-v1-721d5a88393dc361bb72d6ca1abab70d3fa2a6ba3e420737ca3b1bedc89136f5`,
bundle `f7c053a536e1c415adcc2e32b2f5a52248edfea17afaebc6cbca6c716d65cfa9`,
manifest `241b9ae31d16d28d3ba7d174f0776f31fb148bb4c52df2a6545c94e2c0130282`.
Its [receipt](evidence/issue293-owner-candidate/exact-721d-retirement-receipt.json)
is RETIRED_NOT_AVAILABLE, physical_available:false. Existing rename/journal
safeguards applied before unlink; metadata cannot restore deleted app bytes.
[Independent QA](evidence/issue293-owner-candidate/post-retirement-independent-qa.json)
proved physical7/8, complete authority/no blockers, seven unchanged audit rows,
CURRENT/K1/K2, installed critical files,11model registrations and original
ownership receipts preserved. Preexisting unverified legacy states were not
adopted or weakened. Only that freed slot was used for the new Candidate.

## Remaining pre-owner and human gates

The historical two CURRENT failures were release-governance failures: expected
unaccepted339→325 adapter byte drift lacked retained Candidate/Proposal binding.
They are not hidden by rewriting CURRENT. The correct next layer is strict
Proposal Lite declaration C, canonical protection registration preserving
K2/PR280, the permitted canonical registry sync, then final supported full,
governance and exact-head CI gates. No future gate is marked PASS here.

CURRENT/K1 remains675acf; its file SHA256 is
`bdd2ea30b3102c59cd8e47bc56a0d53c6b57d3bfb0347e667663b1be951e52e2`.
K2, other archives, independent source applications, installed Integra and all
models remain preserved. The installed app still requires Qwen. No model is
removed. After all pre-owner gates, genuine handoff uses a separate admitted
execution copy; the immutable archive itself must not be executed. Owner
acceptance and any post-owner promotion/installation remain separately gated.
