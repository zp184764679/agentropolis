"""Core MCP tools for world and travel surfaces."""

from __future__ import annotations

from agentropolis.mcp._shared import agent_tool_context, handle_tool_error
from agentropolis.mcp.server import mcp
from agentropolis.services.world_svc import (
    find_path,
    get_all_regions,
    get_travel_status,
    start_travel,
)


@mcp.tool()
async def get_world_map_tool(agent_api_key: str) -> dict:
    try:
        async with agent_tool_context(agent_api_key, family="world") as (session, _agent):
            return {"ok": True, "regions": await get_all_regions(session)}
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def get_route_tool(agent_api_key: str, to_region_id: int) -> dict:
    try:
        async with agent_tool_context(agent_api_key, family="world") as (session, agent):
            route = await find_path(session, agent.current_region_id, to_region_id)
            return {
                "ok": True,
                "route": {
                    "agent_id": agent.id,
                    "from_region_id": agent.current_region_id,
                    "to_region_id": to_region_id,
                    **route,
                },
            }
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def get_travel_status_tool(agent_api_key: str) -> dict:
    try:
        async with agent_tool_context(agent_api_key, family="world") as (session, agent):
            return {"ok": True, "travel": await get_travel_status(session, agent.id)}
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def start_travel_tool(agent_api_key: str, to_region_id: int) -> dict:
    try:
        async with agent_tool_context(agent_api_key, family="world", mutate=True) as (session, agent):
            payload = await start_travel(session, agent.id, to_region_id)
            await session.commit()
            return {"ok": True, "travel": payload}
    except Exception as exc:
        return handle_tool_error(exc)
