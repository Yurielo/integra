# Integra Codex agent team

The governed inventory is `state/agent_team_v1.json`; the operating contract is
`docs/architecture/AGENT_TEAM_OPERATING_MODEL.md`.

`product-owner` is the lead coordinating agent. It activates the smallest
useful specialist set, preserves scope and acceptance criteria, and consolidates
evidence. The human Product Owner retains genuine product, semantic, protected
data, release, and irreversible decisions.

Each `.toml` registers a Codex role and points to a matching detailed `.md`
contract. Six roles are permanent operational owners; architecture, independent
review, planning, and documentation are retained as on-demand specialist
capabilities. Role activation does not create an approval gate. Jira and
Confluence in compatibility role IDs do not authorize those services; GitHub
Issues, Milestones, pull requests, and repository documentation are Integra
defaults.

Validate the complete set with:

```bash
python3 scripts/check_agents.py
```
