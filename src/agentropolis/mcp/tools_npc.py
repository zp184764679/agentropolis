"""NPC shop MCP tools for the local preview surface."""

from __future__ import annotations

from agentropolis.mcp._shared import agent_tool_context, handle_tool_error
from agentropolis.mcp.server import mcp
from agentropolis.services.npc_shop_svc import get_effective_prices, get_shops_in_region


@mcp.tool()
async def list_region_shops(agent_api_key: str, region_id: int | None = None) -> dict:
    try:
        async with agent_tool_context(agent_api_key, family="strategy") as (session, agent):
            target_region_id = region_id or agent.current_region_id
            return {
                "ok": True,
                "shops": await get_shops_in_region(session, target_region_id),
            }
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def get_shop_effective_prices(agent_api_key: str, shop_id: int) -> dict:
    try:
        async with agent_tool_context(agent_api_key, family="strategy") as (session, agent):
            payload = await get_effective_prices(
                session,
                shop_id,
                reputation=float(agent.reputation),
                agent_id=agent.id,
            )
            return {"ok": True, "prices": payload}
    except Exception as exc:
        return handle_tool_error(exc)
