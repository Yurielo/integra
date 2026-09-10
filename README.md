# Integra

Integra is a separate macOS application that unifies accepted SeminarText and
VideoText capabilities for knowledge, media, learning, marketing, and
publishing workflows.

Implementation follows the governed, issue-first roadmap. SeminarText and
VideoText remain independently usable products throughout integration; Integra
does not destructively migrate their projects or silently take ownership of
their authoritative artifacts.

## Repository truth

- [Integration plan](docs/INTEGRA_PLAN.md)
- [Product definition and 1.0 scope](docs/PRODUCT_DEFINITION.md)
- [Architecture and authority model](docs/architecture/INTEGRA_ARCHITECTURE.md)
- [Executable roadmap](docs/ROADMAP.md)
- [Development workflow](DEVELOPMENT_WORKFLOW.md)
- [Continuous autonomous execution policy](docs/AUTONOMOUS_EXECUTION_POLICY.md)
- [Agent team operating model](docs/architecture/AGENT_TEAM_OPERATING_MODEL.md)
- [Machine-readable agent registry](state/agent_team_v1.json)
- [Acceptance criteria](docs/ACCEPTANCE_CRITERIA.md)
- [Risk register](docs/RISK_REGISTER.md)
- [Machine-readable state](state/integra_state_v1.json)
- [Pinned component baselines](state/component_baselines_v1.json)
- [R1 baseline certification](docs/baselines/R1_BASELINE_CERTIFICATION.md)
- [Data ownership and Project Lease](docs/architecture/DATA_OWNERSHIP_AND_PROJECT_LEASE.md)
- [Machine-readable ownership matrix](state/data_ownership_v1.json)
- [Local worker and artifact contract](docs/architecture/WORKER_PROTOCOL_V1.md)
- [Machine-readable worker protocol](state/worker_protocol_v1.json)
- [R4 adapter spike certification](docs/baselines/R4_ADAPTER_SPIKE_CERTIFICATION.md)
- [Machine-readable R4 evidence](state/adapter_spike_v1.json)
- [R6 Core Alpha certification](docs/baselines/R6_CORE_ALPHA_CERTIFICATION.md)
- [Machine-readable R6 evidence](state/core_alpha_v1.json)

Validate the governance baseline with:

```bash
python3 scripts/validate_governance.py
python3 scripts/check_agents.py
python3 -m unittest discover -s tests -v
```

The accepted R5 capability selection and its raw two-run replay evidence are
stored in `state/capability_benchmark_v1.json` and
`state/capability_benchmark_raw_v1.json`. Reproduce it only with clean temporary
checkouts of the pinned source commits using `scripts/run_capability_benchmark.py`.
