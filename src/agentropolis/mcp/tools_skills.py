"""Skills MCP tools for the local preview surface."""

from __future__ import annotations

from agentropolis.mcp._shared import agent_tool_context, handle_tool_error
from agentropolis.mcp.server import mcp
from agentropolis.services.skill_svc import get_agent_skills, get_all_skill_definitions


@mcp.tool()
async def get_skill_definitions(agent_api_key: str) -> dict:
    try:
        async with agent_tool_context(agent_api_key, family="strategy") as (session, _agent):
            return {"ok": True, "skills": await get_all_skill_definitions(session)}
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def get_my_skills(agent_api_key: str) -> dict:
    try:
        async with agent_tool_context(agent_api_key, family="strategy") as (session, agent):
            return {"ok": True, "skills": await get_agent_skills(session, agent.id)}
    except Exception as exc:
        return handle_tool_error(exc)
