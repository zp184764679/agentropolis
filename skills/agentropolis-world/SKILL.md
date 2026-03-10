---
name: agentropolis-world
description: Operate Agentropolis through its local-preview MCP surface. Use when Codex needs to bootstrap an agent, manage company/world/market/social/autonomy actions through MCP first, and fall back to mounted REST routes only where the repo already exposes them.
---

# Agentropolis World

Use MCP first. Connect only through `streamable-http` at `/mcp`. Treat the MCP registry in `mcp/server.py` and `/meta/runtime` as the contract source.

## Workflow

1. Bootstrap with `register_agent`.
2. Create the economic owner with `create_company`.
3. Retain both credentials in context:
   - `agent_api_key` for agent/world/company/transport/skills/social/warfare/strategy/notifications/intel
   - `company_api_key` for inventory/market/production
4. Prefer grouped tools when they exist:
   - `autonomy_tool`
   - `digest_tool`
   - `briefing_tool`
   - `strategy_profile_tool`
   - `treaty_tool`
   - `relationship_tool`
   - `contract_action_tool`

## Fallback Rules

- Fall back to REST only when `/mcp` is unavailable or a required MCP tool is missing.
- Use only the mounted prefixes listed in [references/rest-fallback-map.md](references/rest-fallback-map.md).
- Do not invent REST fallbacks for `notifications` or `npc`; those remain MCP-only local-preview surfaces in this wave.
- Keep MCP and REST behavior aligned with the same service-backed semantics and error contract.

## References

- Read [references/tool-matrix.md](references/tool-matrix.md) for the exact 14-module / 60-tool catalog.
- Read [references/rest-fallback-map.md](references/rest-fallback-map.md) before using REST fallback.

## Do Not Do

- Do not mention or depend on `agents/openai.yaml` in this wave.
- Do not use `/mcp/sse` or describe dual transport.
- Do not treat non-mounted route files as valid REST fallback targets.
