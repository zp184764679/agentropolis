"""Core MCP tools for intelligence endpoints."""

from __future__ import annotations

from agentropolis.mcp._shared import agent_tool_context, handle_tool_error
from agentropolis.mcp.server import mcp
from agentropolis.services.market_analysis_svc import (
    get_market_intel,
    get_opportunities,
    get_route_intel,
)


@mcp.tool()
async def get_market_intel_tool(agent_api_key: str, resource: str) -> dict:
    try:
        async with agent_tool_context(agent_api_key, family="strategy") as (session, agent):
            return {"ok": True, "intel": await get_market_intel(session, agent.id, resource)}
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def get_route_intel_tool(agent_api_key: str, to_region_id: int) -> dict:
    try:
        async with agent_tool_context(agent_api_key, family="strategy") as (session, agent):
            return {"ok": True, "route": await get_route_intel(session, agent.id, to_region_id)}
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def get_opportunities_tool(agent_api_key: str) -> dict:
    try:
        async with agent_tool_context(agent_api_key, family="strategy") as (session, agent):
            return {"ok": True, "opportunities": await get_opportunities(session, agent.id)}
    except Exception as exc:
        return handle_tool_error(exc)
