# Issue #214 read-only protection audit

Source: `python3 -B scripts/candidate_protection_audit.py` on the Mac, using
exact GitHub `main` CURRENT bytes and all open PR proposal heads. This is a
snapshot; live disk and GitHub state must be recaptured before any action.

| Measure | Bytes / state |
| --- | ---: |
| Full managed copies | 8 |
| Physically attributed archive bytes | 18,227,019,776 |
| Candidate identity protected bytes | 4,553,990,144 |
| Byte-verified selected protected bytes | 2,280,722,432 |
| UNKNOWN historical bytes | 13,673,029,632 |
| ELIGIBLE bytes | 0 |
| CURRENT recovery | MISSING_HISTORICAL_RECOVERY_ARTIFACT |
| Immediate rollback recovery | MISSING_HISTORICAL_RECOVERY_ARTIFACT |
| Canonical protection authority | PROPOSED_INCOMPLETE_FAIL_CLOSED |
| Promotion readiness | BLOCKED |

The protected bytes include a Candidate matching an open proposal in PR #204
whose package is *not* a verified selected survivor. Only the PR #213 proposed
Candidate's selected package passed full archival byte verification. The six
other full-size packages remain UNKNOWN. This classification does not authorize
their deletion or turn an unverified package into an archive.

The historical CURRENT receipt names Candidate
`candidate-v1-d8bd6fc2649e061d50bfabae37c636d8caeb764965c941cf4fef88ae5fe301a8`,
bundle `fedc5481c20a8829f92fd6f6579e53197b1495bd960c238efe9fdd14c2cb5582`,
manifest `48cd6a5fb04677bc8b79d2a8e6212749c51bc931719fbb8923b1cdb8f7e71c56`,
and inventory `49194d2f7fe42c5a1d5feb5e7f8e14546b966fb1ce655256038ae85d2fd26e56`.
The named archive is absent. The immediate rollback receipt for `af81b286…`
also names an absent archive. Installed/runtime apps have no matching embedded
Candidate manifest and cannot establish either historical recovery artifact.

Open proposal discovery found PRs #182, #183, #186, #204, #206, #211, and
#213. Their exact observed heads and Candidate identities are enumerated in the
proposed registry; the resolver blocks if that set or any head changes.

The full-byte source preflight compares a prospective source app against the
historical inventory digest, including files omitted by the bundle tree digest.
No source on this Mac has met that preflight. No recovery package was created.
The bootstrap plan explicitly records both historical gaps and requires a
separate Product Owner recovery-gap decision. Historical receipts and CURRENT
were not changed.
