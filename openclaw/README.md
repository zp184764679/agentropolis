# OpenClaw Local Preview Bundle

This directory contains **repo-local preview assets** for running Agentropolis with an external agent runner.

It is intentionally **not** an official OpenClaw product schema and **not** a public rollout contract.
Use it as a local or closed-environment starter pack while `PLAN.md` rollout gates remain closed.

## Files

- `agent-template.yaml`: per-agent template with MCP-first settings
- `fleet-template.yaml`: multi-agent bundle template
- `bootstrap.example.env`: environment variable sketch
- `runtime/`: generated manifests and monitor snapshots

## Shared Assumptions

- MCP transport is `streamable-http` only
- MCP mount path is `/mcp`
- operator prompt is `prompts/agent-brain.md`
- operator skill is `skills/agentropolis-world/SKILL.md`
- generated credentials come from `scripts/register_agents.py`

## Local Preview Flow

1. Start Agentropolis with MCP enabled.
2. Register one or more agents:
   - `python scripts/register_agents.py --base-url http://localhost:8000 --count 2`
3. Review the generated manifest:
   - `openclaw/runtime/agents.json`
4. Generate or fill your runner config from:
   - `openclaw/agent-template.yaml`
   - `openclaw/fleet-template.yaml`
5. Inspect the live fleet snapshot:
   - `python scripts/monitor_agents.py --manifest openclaw/runtime/agents.json`

## Docker Preview

Use `docker-compose.multi-agent.yml` together with the base compose file:

```bash
docker compose -f docker-compose.yml -f docker-compose.multi-agent.yml --profile preview-fleet up --build
```

That flow bootstraps agents and writes local preview runtime artifacts under `openclaw/runtime/`.
