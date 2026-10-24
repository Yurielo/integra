# Issue #279: superseded unaccepted K2 submission

The Product Owner explicitly authorized superseding the prior unaccepted fixed
K2 submission, recording its lifecycle decision and proceeding through governed
rotation to the replacement archive/proposal handoff, with CURRENT unchanged.
The verbatim directive and exact outgoing identity are recorded in
[the owner authorization](https://github.com/Yurielo/integra/issues/279#issuecomment-6380155631).
The comment transparently identifies Codex as the recorder of the controlling
conversation; it is not a new semantic acceptance.

The outgoing Candidate is
`candidate-v1-19e3438fea443e1d917b6575131fd67b47b5f44f71202a6940f85adda12b3b56`,
bundle `1fe98fb2822b50077f78f22db960dc1f457f5b6374736a3dace704e99e8fe7e0`,
manifest `0704fd913f525d050cdf52f16eefae938cd6d2c9776c92abaf39881f7973efbb`.
The immutable history event changes its lifecycle from
`AWAITING_OWNER_ACCEPTANCE` to `WITHDRAWN_SUPERSEDED`. The registry binds the
event's exact bytes and grants withdrawal retirement for only that exact archive
path and identity. The authority-comment SHA-256 is
`163fecd905ba317dc675d8e49b56a5063adeb28ccf566a8b5316bd1e1847abc0`.

The tested replacement is Candidate
`candidate-v1-e8064cba8acad3282d86b9d7eea043f85c5eed54ac7db015ccdf089943dee943`,
source `6e6978a5f88930158058df8e90dbe4275f11c29a`. Its regression and bounded
native GUI evidence is in PR #280. This lifecycle delivery adds no application
code and makes no claim that the replacement is owner accepted.

Canonical merge records the authority; it does not itself delete any bytes.
The existing maintenance executor must independently recheck integrity, owned
publisher provenance, inactive writers, fresh canonical protections and oldest
eligible publication order. The 8-copy / 20-GiB limits and 15-GiB reserve remain
unchanged. The replacement must be freshly reproduced from the tested source,
retained as actual verified application bytes, and handed off with its exact
proposal. CURRENT promotion and semantic acceptance remain separate decisions.

## Verification

- Independent read-only review: approved, no findings; live comment, body hash,
  outgoing tuple/path, immutable event, exact registry grant and CURRENT verified.
- Focused lifecycle/protection/retention tests: 80 passed, zero failures/errors.
- Full supported suite: 1,180 tests in 404.651 seconds; 1,116 passed,
  64 skipped, zero failures/errors.
- Governance: `CURRENT_VALID`; `git diff --check`: passed.

Changed-file scope is this report,
`state/candidate_protection_registry_v1.json`, and
`state/history/knowledge_k2_candidate_19e343_withdrawal_v1.json`.
No source-product repositories, pins, installed app, original projects or
CURRENT records change. CURRENT hashes remain:

- `state/current_product_baseline_v2.json`:
  `bdd2ea30b3102c59cd8e47bc56a0d53c6b57d3bfb0347e667663b1be951e52e2`.
- `state/current_canonical_baseline_v1.json`:
  `0493fbad50f1a5518b01be90e3ffb0cd10d3d8b7a97ae12918fc4595c4438840`.
