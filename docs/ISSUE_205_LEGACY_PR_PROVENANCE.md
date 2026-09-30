# Issue #205 — legacy PR Candidate provenance

Scope: read-only reconstruction for Issue #205 / PR #206. No historical bytes,
CURRENT, policy, promotion or GitHub state changed. This report supplements the
historical Human Gate and grants no deletion authority.

## Result

All three exact Candidate obligations remain **UNKNOWN / preserve**. None is
accepted in the 18-record canonical history. All three PRs and source Issues
remain open; proposals retain null owner acceptance and the old `65bf72…`
CURRENT base. No reviewed comment, review, timeline or canonical record
explicitly rejects, abandons or retires any exact Candidate. Consequently:

`HUMAN_GATE_DELETE_PATHS = NONE` for this subtask.

The frozen proposals are historical declarations against a superseded base;
they are not currently promotable against `d8bd6…`. PR #182 additionally has
an exact-head failed governance check. PR #183/#186 have successful historical
checks, which do not establish current-base validity or owner acceptance.
PR #186 expressly awaits proposal-specific owner authorization. Open proposals
must stay conservatively unresolved until their exact disposition is recorded;
this report does not convert an old pending obligation into terminal status.

| PR / source Issue | Exact captured HEAD | Candidate | Recorded check | Retention status |
| --- | --- | --- | --- | --- |
| #182 / #180 | `b672417b76a0d2bb094d09dd8492b8e488d5a818` | `candidate-v1-7a254e707443a278606ffa956cc76e8374f5c20115077351e093230547f8bd62` | FAILURE (historical exact head) | UNKNOWN |
| #183 / #181 | `19242b5e778bba3564a554c67f2f8c686856d1db` | `candidate-v1-f4673faeb53b6d4ca3b71dda9cb383a175cb01c24519f907ec2e9d2cbea5eafc` | SUCCESS (historical exact head) | UNKNOWN |
| #186 / #185 | `1a1daf73aabca19a8112fb8f0710a60eab6ee3c8` | `candidate-v1-9c969dab6d8aab30458bd202dd792d709e1faea8db207306e3ccb46c886c1e98` | SUCCESS (historical exact head) | UNKNOWN |

Capture: canonical main `4161ec1dd5eeef9f4cfc6b8df02e6af577d9ec87`; all three exact PR heads and main were
reread unchanged at the end. Full source responses, proposal bytes, digest
checks, comments/reviews/timelines and findings are preserved in
`docs/evidence/ISSUE_205_LEGACY_PR_PROVENANCE.json`.

## PR #182 / Issue #180

[PR #182](https://github.com/Yurielo/integra/pull/182) says:

> The 2.1 GiB owned root was removed after each full run.

The [exact-head lifecycle report](https://github.com/Yurielo/integra/blob/b672417b76a0d2bb094d09dd8492b8e488d5a818/docs/ISSUE_180_TEMP_ARTIFACT_LIFECYCLE_REPORT.md)
records three controlled builds and zero owned roots after each wrapper exit.
That is evidence that these measured disposable test copies were intentionally
cleaned, not evidence that the open proposal was rejected. The proposal's
Candidate/source/manifest remains distinct from accepted `65bf72…` even though
both declare bundle digest `044594f1…`.

[Issue #180 comment](https://github.com/Yurielo/integra/issues/180#issuecomment-5816936673)
reports the failed R12/CURRENT shell-harness provenance chain. It does not
contain owner Candidate acceptance or terminal disposition.

## PR #183 / Issue #181

The [exact-head report](https://github.com/Yurielo/integra/blob/19242b5e778bba3564a554c67f2f8c686856d1db/docs/ISSUE_181_TEMP_LIFECYCLE_REPORT.md)
records two sequential exact-source builds with no remaining owned Candidate
scratch root. Again, disposal of controlled scratch is distinct from retiring
the historical proposal.

[Issue #181 comment](https://github.com/Yurielo/integra/issues/181#issuecomment-5849336105)
subsequently establishes:

> A copied manifest/log alone is insufficient.

It requires verified permanent bytes for accepted/review-pending Candidates and
explicitly does not complete broader lifecycle work. Merged
[PR #193](https://github.com/Yurielo/integra/pull/193) says:

> their broader cleanup scope remains open.

PR #206 is a later lifecycle implementation covering this broader concern,
but remains open. Overlapping or stronger implementation does not itself
supersede #183's exact Candidate or disposition.

## PR #186 / Issue #185

The [exact-head proof](https://github.com/Yurielo/integra/blob/1a1daf73aabca19a8112fb8f0710a60eab6ee3c8/docs/PROCESS_V1_TRANSLATION_INTEGRATION_PROOF.md)
records the original path:

`/private/tmp/integra-185-translation-final-candidate.M1Bjos/Integra.app`

That exact path is absent at this capture. No matching Candidate ID or declared
bundle `e6ab2fd5…` exists in the saved bounded app inventory. This establishes
scoped absence; it neither proves global loss nor permits dropping retention.
The proof states:

> does not contain any owner decision.

[PR #186](https://github.com/Yurielo/integra/pull/186) describes a technically
valid proposal awaiting proposal-specific promotion authorization. No issue or
PR comment/review supplies that authorization or a terminal rejection.

Later merged, owner-accepted canonical implementations address its named
outcomes in their own bounded scopes:

| Outcome | Later accepted PR | Accepted Candidate | Exact replacement? |
| --- | --- | --- | --- |
| Transcript translation | [#198](https://github.com/Yurielo/integra/pull/198) | `de25ee…` | No: different Candidate/bundle |
| Translation-language choice | [#199](https://github.com/Yurielo/integra/pull/199) | `654599…` | No: different Candidate/bundle |
| Translated TXT | [#200](https://github.com/Yurielo/integra/pull/200) | `a6d470…` | No: different Candidate/bundle |
| Topic translation (excluded by #186) | [#207](https://github.com/Yurielo/integra/pull/207) | `8be1ad…` | Separate outcome |

These Candidates are present in accepted main history with exact Product Owner
promotion references. Later feature delivery supplies canonical outcome
successors, not identical historical bytes or retirement authority. Full
behavioral equivalence is not asserted: #199, for example, explicitly limits
the visible target to English for Russian source speech. PR #207
explicitly does not automatically supersede an existing PR.

## Active references and identity distinctions

The [canonical completion plan](https://github.com/Yurielo/integra/blob/4161ec1dd5eeef9f4cfc6b8df02e6af577d9ec87/docs/INTEGRA_COMPLETION_PLAN_2026-09-13.md)
treats #183/#186 as existing lifecycle/translation drafts to verify, not already
accepted functionality. The [canonical proof gate](https://github.com/Yurielo/integra/blob/4161ec1dd5eeef9f4cfc6b8df02e6af577d9ec87/docs/PROCESS_V1_VIDEOTEXT_ONLY_PROOF_GATE.md)
requires review/reuse of relevant source implementation. These are active
**source references**. A requirement to retain their exact full application
bytes is not expressly established by those statements. No complete approved
byte-pin registry is asserted here, so pin absence is not declared resolved.

Merged [PR #188](https://github.com/Yurielo/integra/pull/188) explicitly says:

> this PR does not merge, accept or deliver them.

Its [post-merge comment](https://github.com/Yurielo/integra/pull/188#issuecomment-5838857784)
confirms #183/#186 were left untouched. [Issue #187 clarification](https://github.com/Yurielo/integra/issues/187#issuecomment-5838807552)
requires their work to be reviewed and proved, not treated as delivered.
PR #189 updates sequencing only. PR #191/#193 preserve the separate accepted
`65bf72…` recovery and `2fe375…` pilot; neither retires these three Candidates.

Official GitHub source-to-main comparisons report **diverged** for all three
source commits. Their source commits were not integrated by ancestor merge.
Source reuse, feature equivalence, bundle-payload equality and exact Candidate
identity must therefore remain separate claims.

## Known bytes and accounting

The saved bounded inventory contains no exact `7a254e…`, `f4673f…` or `9c969d…`
Candidate. Their unknown missing-byte obligations contribute no invented size
or reclaim to the current archive totals.

For #182/#183, the accepted `65bf72…` payload's recorded bundle digest equals
their declared bundle digest. Two known copies are:

- `/Users/yurielokhin/Library/Application Support/Integra/Build Archive/recovered-current-65bf72/Integra.app`
- `/Users/yurielokhin/Library/Application Support/Integra/Build Archive/retained/candidate-v1-65bf72d1262146c9137aca433b51ae3974d98bc4c8ed37042db13b46e0318a1d/044594f1a632f1c140af28bb7de8e4acf782daca9863d84b9c5d77edb731fdf8/Integra.app`

Each recorded logical app size is 2,201,478,232 bytes. Their manifest digest
`c59d1855…` differs from both old proposals. These are payload-equivalence
candidates and accepted historical recovery bytes; they are not full-app exact
duplicates of either legacy proposal Candidate. No replacement manifest or
new acceptance was fabricated, and no payload hash was repeated in this task.

## Method and limits

Official `gh api` reads collected exact PR metadata, every issue comment,
review, inline review comment and timeline, with bounded exhaustive pagination.
All PR bodies were scanned for direct source-issue/PR references. Related
#187/#188/#189/#191/#192/#193/#198/#199/#200/#205/#206/#207 evidence was reviewed.
Immutable source files and exact canonical main history were read separately.
All nine small proposal evidence files match their declared SHA-256 digests.

No home-wide search, full payload hash, application execution, deletion,
promotion, policy edit or GitHub publication occurred. The earlier inventory
is a scoped snapshot, not proof of global absence. A local canonical-main Git
object was unavailable; canonical reads used GitHub at the exact main SHA.

The historical Human Gate may explicitly resolve these precise frozen
proposals/Candidate obligations. Until then they remain UNKNOWN. This report
proposes no deletion path and no change to the accepted 8 / 20 GiB / 15 GiB
policy.
