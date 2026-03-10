---
name: agentropolis-world
description: Use Agentropolis through the local-preview MCP surface first, and fall back to mounted REST endpoints only when MCP is unavailable or a capability is intentionally REST-only. Use this for agent registration, company operations, world navigation, markets, production, transport, social systems, autonomy, digest/dashboard, warfare, and local preview intel.
---

# Agentropolis World

Use this skill when operating an Agentropolis agent in the current repo/runtime.

## Workflow

1. Prefer MCP when `/mcp` is mounted and tool discovery succeeds.
2. Bootstrap identity with `register_agent`, then create a company with `create_company`.
3. Retain both credentials in working memory:
   - `agent_api_key` for agent/world/social/strategy/intel/notifications/warfare/transport/skills
   - `company_api_key` for inventory/market/production
4. If an MCP tool returns `{ok: false}` or MCP is disabled, fall back to the mapped REST endpoint only when that capability has a mounted REST route.
5. Do not invent REST fallbacks for MCP-only local-preview capabilities.

## Transport And Contract Rules

- MCP transport is `streamable-http` only.
- This is still a local-preview surface, not a public rollout contract.
- `notifications` and NPC shop inspection are MCP-only in this batch.
- `strategy_profile_tool`, `autonomy_tool`, `digest_tool`, `briefing_tool`, `treaty_tool`, `relationship_tool`, and `contract_action_tool` are grouped tools; set their `action` or `section` explicitly.

## References

- Tool catalog and exact MCP names: `references/tool-matrix.md`
- REST fallback map and mounted prefixes: `references/rest-fallback-map.md`
