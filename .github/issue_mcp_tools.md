## Overview

Rewrite the local-preview MCP surface to match repo truth:

- `streamable-http` is the only supported transport
- MCP registration stays static in `src/agentropolis/mcp/server.py`
- the Wave 1 preview surface exposes **14 tool modules / 60 tools**
- MCP tools call the same services as REST routes; do not add MCP-only business logic

This issue is a **local-preview integration slice**, not a public OpenClaw rollout.

## Files

- **Modify**: `src/agentropolis/mcp/server.py`
- **Modify**: `src/agentropolis/runtime_meta.py`
- **Create/Modify**: `src/agentropolis/mcp/tools_agent.py`
- **Create/Modify**: `src/agentropolis/mcp/tools_world.py`
- **Create/Modify**: `src/agentropolis/mcp/tools_inventory.py`
- **Create/Modify**: `src/agentropolis/mcp/tools_market.py`
- **Create/Modify**: `src/agentropolis/mcp/tools_npc.py`
- **Create/Modify**: `src/agentropolis/mcp/tools_production.py`
- **Create/Modify**: `src/agentropolis/mcp/tools_company.py`
- **Create/Modify**: `src/agentropolis/mcp/tools_transport.py`
- **Create/Modify**: `src/agentropolis/mcp/tools_skills.py`
- **Create/Modify**: `src/agentropolis/mcp/tools_social.py`
- **Create/Modify**: `src/agentropolis/mcp/tools_warfare.py`
- **Create/Modify**: `src/agentropolis/mcp/tools_strategy.py`
- **Create/Modify**: `src/agentropolis/mcp/tools_notifications.py`
- **Create/Modify**: `src/agentropolis/mcp/tools_intel.py`
- **Modify**: `src/agentropolis/main.py` (conditional mount only)
- **Modify**: `tests/test_mcp_core.py`

## Repo-Truth Surface

### Module Catalog

- `tools_agent.py` — 6 tools
- `tools_world.py` — 5 tools
- `tools_inventory.py` — 3 tools
- `tools_market.py` — 8 tools
- `tools_npc.py` — 2 tools
- `tools_production.py` — 5 tools
- `tools_company.py` — 4 tools
- `tools_transport.py` — 3 tools
- `tools_skills.py` — 2 tools
- `tools_social.py` — 7 tools
- `tools_warfare.py` — 4 tools
- `tools_strategy.py` — 4 grouped tools
- `tools_notifications.py` — 2 tools
- `tools_intel.py` — 5 tools

Total: **60 tools**

### Grouped Tools

- `treaty_tool(action=propose|accept|list)`
- `relationship_tool(action=list|set)`
- `contract_action_tool(action=get|enlist|activate|cancel|execute)`
- `strategy_profile_tool(action=get|update|scout)`
- `autonomy_tool(action=get_config|update_config|get_standing_orders|update_standing_orders|list_goals|create_goal|update_goal)`
- `digest_tool(action=get|ack)`
- `briefing_tool(section=dashboard|decisions|analysis|public_standing_orders)`

## Auth Split

- `agent_api_key` for `agent/world/company/transport/skills/social/warfare/strategy/notifications/intel`
- `company_api_key` for `inventory/market/production`
- `register_agent`, `get_game_status`, `get_leaderboard`, and public resource/profile reads may remain public where the backing service already allows it

## Runtime Rules

- Mount MCP only at `/mcp`
- Use `mcp.streamable_http_app()`
- Do not keep `/mcp/sse` examples or dual-transport docs
- Keep static registration in `mcp/server.py` so runtime metadata and tests can count the exact surface
- Report repo truth through `/meta/runtime`:
  - `transport=streamable-http`
  - `tool_count=60`
  - real 14-module group map
  - `local_preview_only=true`
  - `public_rollout_ready=false`
- `npc` and `notifications` are allowed to remain MCP-only local-preview groups in this wave

## Acceptance Criteria

- [ ] Exactly 14 tool modules are registered in `mcp/server.py`
- [ ] Exactly 60 tools are exposed
- [ ] `main.py` mounts `/mcp` with `streamable_http_app()` only when `MCP_SURFACE_ENABLED=true`
- [ ] `runtime_meta.py` reports the same 14-module / 60-tool surface as the real registry
- [ ] At least one MCP/REST parity path passes using the same backing services
- [ ] `npc` and `notifications` are documented as MCP-only local-preview groups
- [ ] No MCP tool duplicates business logic that already exists in services or mounted REST routes

## Dependencies

- **Depends on**: mounted preview REST/API families plus the current service layer
- **Blocks**: MCP-first skill/docs sync and later OpenClaw rollout work
