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
| CURRENT recovery | MISSING_WITH_AVAILABLE_EVIDENCE |
| Immediate rollback recovery | MISSING_WITH_AVAILABLE_EVIDENCE |
| Canonical protection authority | PRODUCT_OWNER_ACCEPTED_PENDING_INTEGRATION |
| PR #213 promotion integration | MISSING; separate governed verification required |
| Promotion readiness | BLOCKED |
| PROTECTED / UNKNOWN / ELIGIBLE copies | 2 / 6 / 0 |

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

The exact Product Owner decision is preserved in Issue #214 comment
`5951189263` and bound by token SHA-256
`c0fbc7699ae3caa6ea56a59987410977515881043f2ce2fd9b4f39382cc132f8`.
It authorizes empty additional governance pins and deletion grants, and leaves
all UNKNOWN artifacts fail-closed. The full-byte source preflight compares a prospective source app against the
historical inventory digest, including files omitted by the bundle tree digest.
No source on this Mac has met that preflight. No recovery package was created.
The bootstrap plan explicitly records both accepted historical gaps. The
current promotion helper still requires the exact outgoing archive, and the
PR #213 lifecycle/deletion executor does not consume this registry; neither
promotional nor deletion authority is inferred from the gap decision.
Historical receipts and CURRENT were not changed.
