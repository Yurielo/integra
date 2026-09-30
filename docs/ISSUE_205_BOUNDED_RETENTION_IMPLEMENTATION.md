# Issue #205 — adopted bounded retention implementation and migration dry-run

Authority: [Product Owner retention decision](https://github.com/Yurielo/integra/issues/205#issuecomment-5917563905).
Scope: existing PR #206 only. Historical bulk deletion, CURRENT promotion,
archive repair, source-product modification and Quality Gate bypass were not
performed. Prior cleanup of only `integra-excel07-final-current` is already
recorded in Issue #205; this stage removed no historical Candidate or runtime.

## Implementation

- Adopted both limits: 8 full copies and 20 GiB attributed allocation;
  15 GiB must remain after planned and live reservations. Unknown legacy
  bytes count toward caps. Shared user catalog prevents root/volume quota
  splitting; existing volume admission remains shared and atomic.
- All native build entry points require a live reservation and a fresh output
  below the validated owned workspace. Output cannot overwrite retained apps.
- New publications bind ownership to prepublication run/stage inode, exact
  Candidate/bundle/manifest and COMPLETE/inventory. Publication crash recovery
  cannot adopt a foreign no-replace collision. Exact full-package reuse spans
  registered roots; differing Candidate metadata or retained evidence is not
  silently collapsed.
- Protection refresh reads exact canonical main and exhaustively enumerates
  every open PR/head/proposal. Required identity tuples and verified selected
  survivors bind protection. Missing approved pin enumeration or selectors
  blocks deletion. Arbitrary local authority strings cannot confirm recovery.
- Owned terminal cleanup uses a durable, bounded package transaction with
  no-replace withdrawal, exact inventory hashes and fd-relative filesystem
  checks. A crash in either PREPARED or DELETING is resumable only after a
  new fresh authority/integrity check; foreign/replaced/active bytes remain.
- Existing PR #206 common supervision handles normal completion, failure,
  SIGINT/SIGTERM, abandoned callers and stale workspaces. It was extended
  with admission/ownership journaling rather than duplicated.
- Historical ownership is not automatically imported. `post-promotion` is
  a reconciliation/cleanup entry point for **actual authorized promotion**;
  the existing helper that only prepares promotion outputs is not treated
  as promotion. No promotion was invoked.

Contract: `docs/BOUNDED_CANDIDATE_RETENTION.md` and
`state/candidate_retention_policy_v1.json`.
Independent implementation review: `docs/ISSUE_205_RETENTION_IMPLEMENTATION_REVIEW.md`.

## Forensic prerequisites

Both original a6d470 and 8be1ad inventory mismatches are explained as additions-
only drift: 38 CPython3.14 caches/six directories and one CPython3.13 cache/one
 directory. All recorded files freshly matched hashes, modes, sizes and types.
Cache headers/source associations match; the writer remains unproven.
Existing Recovery Archive a6d470 and Build Archive Recovery 8be1ad independently
passed full archive verification. Originals remain QUARANTINED_RETAIN and
cannot be used for promotion. No in-place immutable archive repair occurred.
Details: `docs/ISSUE_205_RETENTION_FORENSICS.md` and its JSON evidence.

Legacy tmp/release/source/worktree and manifestless runtime objects are
classified; none has a confirmed publisher/run ownership marker. Their
provenance does not confer deletion authority. Source-worktree and partial
build preservation remains required. Minecraft and other user data are outside
this task and were not modified.

## Strict initial historical migration dry-run

Allocation below uses st_blocks/device/inode attribution, not logical payload
size. It charges each observed inode once. APFS exclusive/shared extents and
actual reclaim are not proven. Root/container overhead remains UNKNOWN.
All four archive roots are disjoint; retained is a subset of Build Archive.

| Metric | Bytes |
| --- | ---: |
| BEFORE_BYTES | 75,299,602,432 |
| PROTECTED_BYTES | 22,785,179,648 |
| DELETABLE_BYTES | 0 |
| UNKNOWN_BYTES | 52,514,422,784 |
| EXPECTED_AFTER_BYTES | 75,299,602,432 |
| EXPECTED_FREE_SPACE | 16,097,386,496 |

33 full copies exceed 8; 70.13 GiB exceeds 20 GiB. This conservative plan
protects ten present copies / seven identities including unresolved retained
provenance and duplicate survivors. Three additional open-PR Candidate
identities (#182, #183, #186) are absent in scope. Across confirmed/provisional
CURRENT, rollback, recovery and all pending proposals there are nine distinct
roles/identities before an additional legacy pilot provenance pin; protected
roles cannot be evicted automatically to satisfy a cap.

DELETABLE_BYTES is **zero**. Of the UNKNOWN total, 47,898,103,808 bytes belong
to 21 metadata-clean but publisher-unconfirmed legacy packages; 4,616,318,976
bytes are quarantined/uncategorized packages and archive overhead. The former
is conditional review/adoption volume, not permission or guaranteed savings.
The protected total includes conservative duplicate copies; selected survivor
reconciliation must precede removing extra protected copies.

The exact annotated inventory/report is
`docs/evidence/ISSUE_205_BOUNDED_RETENTION_DRY_RUN_20260930.json`.
This is evidence, **not an executable authorized historical deletion plan**.
No production ownership catalog was initialized by this migration inspection.

### Inventory

| PATH | SIZE (allocated bytes) | IDENTITY | ROLE | STATUS | SAFE_TO_DELETE |
| --- | ---: | --- | --- | --- | --- |
| `Build Archive/candidate-v1-136e1a5b80644c20a4e7f9ecf66741ab069f88d66418123e6e85b409bfc714b8/d05c0863dcb4a205a3c0fd4e4787e8b15f70a17058335f09f46236bda64ca4ba` | 2,280,742,912 | `136e1a5b8064` | AWAITING_OWNER_ACCEPTANCE | PROTECTED / OWNERSHIP_UNCONFIRMED | NO |
| `Build Archive/candidate-v1-14b3c10e4d779ff8b5a520bf15e2b7087673aec2cd0abd25aac4e1d0ded77892/ab53369d4d46fc8a4dece0b8e0f777f5017731b2256ff34ecb27738a849d8c94` | 2,280,628,224 | `14b3c10e4d77` | AWAITING_OWNER_ACCEPTANCE | PROTECTED / OWNERSHIP_UNCONFIRMED | NO |
| `Build Archive/candidate-v1-26b131104a0ccbcb75d61325412339b1d1bc264fdbf40bea1c9b6845c5d1de34/dfa6b0102940534f2e06284a3768245d7476052bbe9f3e82713e1679b05a0204` | 2,280,611,840 | `26b131104a0c` | REVIEW_HISTORY_RETIREMENT_UNAUTHORIZED | UNKNOWN / OWNERSHIP_UNCONFIRMED | NO |
| `Build Archive/candidate-v1-2b779255c5b57a7b6602f153ea13c497bf738a18a84412773f8b6ed5261fbfcc/dfa6b0102940534f2e06284a3768245d7476052bbe9f3e82713e1679b05a0204` | 2,280,611,840 | `2b779255c5b5` | ACCEPTED_HISTORY | UNKNOWN / OWNERSHIP_UNCONFIRMED | NO |
| `Build Archive/candidate-v1-316393126468279aed6c5b645f29365067a6016cf5e06893775810d8a8d50ef8/d05c0863dcb4a205a3c0fd4e4787e8b15f70a17058335f09f46236bda64ca4ba` | 2,280,738,816 | `316393126468` | REVIEW_HISTORY_RETIREMENT_UNAUTHORIZED | UNKNOWN / OWNERSHIP_UNCONFIRMED | NO |
| `Build Archive/candidate-v1-3348b6fc8ed525632d7d0abed1337f2e37b66404f0d6f4488cb3c012c3afca83/448e5ee02ed22c2c77837b25934278750ea9a4a08a9d7f02e70c372886a83d7a` | 2,282,147,840 | `3348b6fc8ed5` | REVIEW_HISTORY_RETIREMENT_UNAUTHORIZED | UNKNOWN / OWNERSHIP_UNCONFIRMED | NO |
| `Build Archive/candidate-v1-43bdfe7b93052a3f2f9b5b6b089179580ef5387ebe82d0e96ef69e612257b0cd/306e3301484b24f1933c3b3ef51583ab4c786263b4ac3ecea241060177aa5eb1` | 2,280,595,456 | `43bdfe7b9305` | ACCEPTED_HISTORY | UNKNOWN / OWNERSHIP_UNCONFIRMED | NO |
| `Build Archive/candidate-v1-6545998b95e0f2d84abc7cd82baaea79bf8aa3c80cdd6d76840f47e87a42f996/a344385ab7ab27812752c92530bb682313018b420363f9f3c91ae48500003faf` | 2,280,652,800 | `6545998b95e0` | ACCEPTED_HISTORY | UNKNOWN / OWNERSHIP_UNCONFIRMED | NO |
| `Build Archive/candidate-v1-726f3a48f66879bce611096db2ffe934727d1ef0372d8a5487db5a7ad69685a5/448e5ee02ed22c2c77837b25934278750ea9a4a08a9d7f02e70c372886a83d7a` | 2,280,591,360 | `726f3a48f668` | REVIEW_HISTORY_RETIREMENT_UNAUTHORIZED | UNKNOWN / OWNERSHIP_UNCONFIRMED | NO |
| `Build Archive/candidate-v1-83a2fe1744d4ba79e2a0cb9321ee15a860a56216dc028d15bc4a0a724d731877/dfa6b0102940534f2e06284a3768245d7476052bbe9f3e82713e1679b05a0204` | 2,280,611,840 | `83a2fe1744d4` | REVIEW_HISTORY_RETIREMENT_UNAUTHORIZED | UNKNOWN / OWNERSHIP_UNCONFIRMED | NO |
| `Build Archive/candidate-v1-8be1ad5ca090afd08b869761046e6f4c56727e11dbf6ae968f6ad6f227d2b173/c4dc155349dc73f2177fa8e8ee29709cc494662a999c2c4a6800e2b992c3907b` | 2,282,328,064 | `8be1ad5ca090` | QUARANTINED_RETAIN_ADDITIONS_ONLY_ORIGINAL | QUARANTINED_RETAIN | NO |
| `Build Archive/candidate-v1-91d028895714a30e4693b5268be1ca078daad385c2ac4364cbb4644a8839c0a0/dfa6b0102940534f2e06284a3768245d7476052bbe9f3e82713e1679b05a0204` | 2,280,611,840 | `91d028895714` | REVIEW_HISTORY_RETIREMENT_UNAUTHORIZED | UNKNOWN / OWNERSHIP_UNCONFIRMED | NO |
| `Build Archive/candidate-v1-95d3284963a5c51105a5a37a215c1398e95ca203e0b167a33c4d1c8fef5da844/d05c0863dcb4a205a3c0fd4e4787e8b15f70a17058335f09f46236bda64ca4ba` | 2,280,738,816 | `95d3284963a5` | REVIEW_HISTORY_RETIREMENT_UNAUTHORIZED | UNKNOWN / OWNERSHIP_UNCONFIRMED | NO |
| `Build Archive/candidate-v1-986ea18cde8d8a78332f5e2b1fc3005b9119cf551dcfb7de339f039d01b656de/dfa6b0102940534f2e06284a3768245d7476052bbe9f3e82713e1679b05a0204` | 2,280,611,840 | `986ea18cde8d` | REVIEW_HISTORY_RETIREMENT_UNAUTHORIZED | UNKNOWN / OWNERSHIP_UNCONFIRMED | NO |
| `Build Archive/candidate-v1-9fa80fda7d7711776415927d1c71d41d0d70e5b1212ccc02a8c4d9b7056660ed/448e5ee02ed22c2c77837b25934278750ea9a4a08a9d7f02e70c372886a83d7a` | 2,280,595,456 | `9fa80fda7d77` | REVIEW_HISTORY_RETIREMENT_UNAUTHORIZED | UNKNOWN / OWNERSHIP_UNCONFIRMED | NO |
| `Build Archive/candidate-v1-a52cd2b257c55f0c50251ec21c253a3370de9d72f16148459650243c5fb3b669/afc07aee895fe1e4cefd882eafae1956ce44a5bf6f62d38fe676f5d84928c925` | 2,280,665,088 | `a52cd2b257c5` | ACCEPTED_HISTORY | UNKNOWN / OWNERSHIP_UNCONFIRMED | NO |
| `Build Archive/candidate-v1-a6d470e1e68163ed119bda229acffb2754b404f2d64310a93cc5dbbab19e5583/2efeff23bab95ec8c54decd11916aae171e0cf5042a14b27ff43dea3304210a8` | 2,282,770,432 | `a6d470e1e681` | QUARANTINED_RETAIN_ADDITIONS_ONLY_ORIGINAL | QUARANTINED_RETAIN | NO |
| `Build Archive/candidate-v1-af81b2867f893e8e529a2d4f64d6c1370dd1249b46eb999d427fb408229680fa/4032ad5334a42a9bbce6384b85b35857557afc2241d2c4d85c9e45379eca620c` | 2,280,718,336 | `af81b2867f89` | ROLLBACK_SELECTOR_RECOMMENDED_RETAIN | PROTECTED / OWNERSHIP_UNCONFIRMED | NO |
| `Build Archive/candidate-v1-c5f5b6ea7e8495c967c0b999dd24bdf7a3162c1fb34035cb0dcedbd5fe323cd2/dfa6b0102940534f2e06284a3768245d7476052bbe9f3e82713e1679b05a0204` | 2,280,611,840 | `c5f5b6ea7e84` | AWAITING_OWNER_ACCEPTANCE | PROTECTED / OWNERSHIP_UNCONFIRMED | NO |
| `Build Archive/candidate-v1-ce1b1abbb4a9a6bb9350d38a24a948a8313077b7c663ea7e3ec8da5d7c5cf807/dfa6b0102940534f2e06284a3768245d7476052bbe9f3e82713e1679b05a0204` | 2,280,611,840 | `ce1b1abbb4a9` | REVIEW_HISTORY_RETIREMENT_UNAUTHORIZED | UNKNOWN / OWNERSHIP_UNCONFIRMED | NO |
| `Build Archive/candidate-v1-d8bd6fc2649e061d50bfabae37c636d8caeb764965c941cf4fef88ae5fe301a8/fedc5481c20a8829f92fd6f6579e53197b1495bd960c238efe9fdd14c2cb5582` | 2,280,722,432 | `d8bd6fc2649e` | CURRENT, LATEST_ACCEPTED_BASELINE | PROTECTED / OWNERSHIP_UNCONFIRMED | NO |
| `Build Archive/candidate-v1-de25ee770d537b88eafd805249769e50694f7f5b56daab2f0771ec2c7706fd3d/3506954cab9fc7a4bd92f681e638fad2974042981f47af24bb2433cbf2cc215a` | 2,280,628,224 | `de25ee770d53` | ACCEPTED_HISTORY | UNKNOWN / OWNERSHIP_UNCONFIRMED | NO |
| `Build Archive/candidate-v1-e13b57a839bb722fb10cb7d46295ae58e77f4641bfacc1226147eedc28df4277/dfa6b0102940534f2e06284a3768245d7476052bbe9f3e82713e1679b05a0204` | 2,280,611,840 | `e13b57a839bb` | REVIEW_HISTORY_RETIREMENT_UNAUTHORIZED | UNKNOWN / OWNERSHIP_UNCONFIRMED | NO |
| `Build Archive/candidate-v1-e5de327bd01cd38dd6f737ad03ff10dcf5e313e6f4aaaa07788cd0261f394779/25522c028bc6f6bd720e1178a2abf8ce86c5d28b279a67aeb61b0588466cbd74` | 2,280,718,336 | `e5de327bd01c` | REVIEW_HISTORY_RETIREMENT_UNAUTHORIZED | UNKNOWN / OWNERSHIP_UNCONFIRMED | NO |
| `Build Archive/candidate-v1-ec1ae4eaccc5a2af225490135dc6385920c5f26ee0433059311be9074f6a2e57/4794bca8031cf6ff0d6a8c019e5492646604ba9e66b3e591167c0c9e63929ffd` | 2,280,615,936 | `ec1ae4eaccc5` | ACCEPTED_HISTORY | UNKNOWN / OWNERSHIP_UNCONFIRMED | NO |
| `Build Archive/candidate-v1-f9ef07f48ff155645239f9c72b454732f53fecabdbf9379ad4d25b1a5acbdc9a/448e5ee02ed22c2c77837b25934278750ea9a4a08a9d7f02e70c372886a83d7a` | 2,280,591,360 | `f9ef07f48ff1` | ACCEPTED_HISTORY | UNKNOWN / OWNERSHIP_UNCONFIRMED | NO |
| `Build Archive/pilot-2fe375-original` | 2,274,074,624 | `2fe375cc31b3` | LEGACY_RETAINED_PROVENANCE_UNRESOLVED | PROTECTED / OWNERSHIP_UNCONFIRMED | NO |
| `Build Archive/recovered-current-65bf72` | 2,273,202,176 | `65bf72d12621` | ACCEPTED_HISTORICAL_RECOVERY_RETAIN | PROTECTED / OWNERSHIP_UNCONFIRMED | NO |
| `Build Archive/retained/candidate-v1-2fe375cc31b3a57d74ad0f994894bd610442deae3adfff033cdc5f3cf400fcd3/47befb29a6c221db7cb79262fc949f29248095e31dceba7fc4d46e78ab06c39e` | 2,280,636,416 | `2fe375cc31b3` | LEGACY_RETAINED_PROVENANCE_UNRESOLVED | PROTECTED / OWNERSHIP_UNCONFIRMED | NO |
| `Build Archive/retained/candidate-v1-65bf72d1262146c9137aca433b51ae3974d98bc4c8ed37042db13b46e0318a1d/044594f1a632f1c140af28bb7de8e4acf782daca9863d84b9c5d77edb731fdf8` | 2,280,574,976 | `65bf72d12621` | ACCEPTED_HISTORICAL_RECOVERY_RETAIN | PROTECTED / OWNERSHIP_UNCONFIRMED | NO |
| `Build Archive Recovery/candidate-v1-8be1ad5ca090afd08b869761046e6f4c56727e11dbf6ae968f6ad6f227d2b173/c4dc155349dc73f2177fa8e8ee29709cc494662a999c2c4a6800e2b992c3907b` | 2,282,323,968 | `8be1ad5ca090` | SECOND_ROLLBACK_BASELINE | UNKNOWN / OWNERSHIP_UNCONFIRMED | NO |
| `Candidate Builds/topic-translation-47be46d` | 2,273,267,712 | `14b3c10e4d77` | AWAITING_OWNER_ACCEPTANCE | PROTECTED / OWNERSHIP_UNCONFIRMED | NO |
| `Recovery Archive/candidate-v1-a6d470e1e68163ed119bda229acffb2754b404f2d64310a93cc5dbbab19e5583/2efeff23bab95ec8c54decd11916aae171e0cf5042a14b27ff43dea3304210a8` | 2,282,217,472 | `a6d470e1e681` | ACCEPTED_HISTORY | UNKNOWN / OWNERSHIP_UNCONFIRMED | NO |

## Verification and delivery boundary

- 40 focused retention/governance tests PASS (24 + 16), 28 archive tests PASS.
- Full supported suite: **879 run / 786 passed / 92 skipped / one failed**.
  The failing governance regression rejects an unexplained new builder hash.
- `scripts/check_agents.py` and `git diff --check`: PASS.
- Independent bounded implementation review: PASS, exact source SHA-256 table.
- `scripts/validate_governance.py`: **FAIL_CLOSED**, R12 builder hash differs.
  The existing proposal describes the previous exact source/Candidate and a
  stale CURRENT. It is not evidence for the new source. No historical record
  was rewritten to suppress this failure.
- A fresh native Candidate/source→evidence→declaration chain is required.
  It cannot be built under the adopted archive caps and disk reserve in this
  existing state. No full native build was started; PR remains unmerged.

Policy adoption is complete; implementation is published for review, not
released. Root cause is established (unowned legacy temporary builds plus
unbounded permanent publication); recurrence prevention is not yet deployed.
Current unrelated free-space fluctuation is not attributed to these read-only
archive observations, and the cache writer is not identified.

## Consolidated next authorization boundary

The already accepted 8/20/15 policy does not need reapproval. Historical bulk
migration remains the owner's explicitly separate Human Gate. Its review must
resolve exact rollback/recovery survivor paths (recommended accepted af81b286
and canonical historical recovery65bf72), enumerate active provenance pins
(including retained pilot2fe375), resolve the three missing old open-PR
Candidates, and attest exact legacy ownership/terminal disposition. Only then
can a separately generated exact deletion-plan digest be considered. The
current strict deletion plan is empty; no implicit mass deletion is authorized.
Protected roles, active worktrees, quarantined originals and unknown runtime
copies remain preserved. Fresh source Candidate and Quality Gate must follow
before merge/promotion. No new TTL, relaxed cap or acceptance inference was
invented to avoid this boundary.

PRODUCT_RULES_READ: YES
APPLICABLE_PRODUCT_RULES: PR-010, PR-011, PR-013
PRODUCT_RULE_CONFLICTS: NONE
