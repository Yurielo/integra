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
- [Acceptance criteria](docs/ACCEPTANCE_CRITERIA.md)
- [Risk register](docs/RISK_REGISTER.md)
- [Machine-readable state](state/integra_state_v1.json)

Validate the governance baseline with:

```bash
python3 scripts/validate_governance.py
python3 -m unittest discover -s tests -v
```
