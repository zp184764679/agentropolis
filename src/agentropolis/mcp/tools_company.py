"""Agent-centric company MCP tools."""

from __future__ import annotations

from agentropolis.mcp._shared import agent_tool_context, handle_tool_error
from agentropolis.mcp.server import mcp
from agentropolis.services.company_svc import (
    get_agent_company,
    get_company_workers as get_company_workers_svc,
    register_company as register_company_svc,
)
from agentropolis.services.production import get_agent_company_buildings


@mcp.tool()
async def create_company(agent_api_key: str, company_name: str) -> dict:
    try:
        async with agent_tool_context(agent_api_key, family="agent_self", mutate=True) as (session, agent):
            payload = await register_company_svc(
                session,
                company_name,
                founder_agent_id=agent.id,
            )
            await session.commit()
            return {"ok": True, "company": payload}
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def get_company(agent_api_key: str) -> dict:
    try:
        async with agent_tool_context(agent_api_key, family="agent_self") as (session, agent):
            payload = await get_agent_company(session, agent.id)
            if payload is None:
                raise ValueError("Agent does not have an active company")
            return {"ok": True, "company": payload}
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def get_company_workers(agent_api_key: str) -> dict:
    try:
        async with agent_tool_context(agent_api_key, family="agent_self") as (session, agent):
            company = await get_agent_company(session, agent.id)
            if company is None:
                raise ValueError("Agent does not have an active company")
            return {"ok": True, "workers": await get_company_workers_svc(session, company["company_id"])}
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def get_company_buildings(agent_api_key: str) -> dict:
    try:
        async with agent_tool_context(agent_api_key, family="agent_self") as (session, agent):
            return {
                "ok": True,
                "buildings": await get_agent_company_buildings(session, agent.id),
            }
    except Exception as exc:
        return handle_tool_error(exc)
