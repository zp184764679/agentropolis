"""Core MCP tools for agent/autonomy surfaces."""

from __future__ import annotations

from agentropolis.mcp._shared import agent_tool_context, handle_tool_error
from agentropolis.mcp.server import mcp
from agentropolis.services.agent_svc import get_agent_status
from agentropolis.services.autopilot import (
    get_autonomy_config,
    get_standing_orders,
    update_autonomy_config,
    update_standing_orders,
)
from agentropolis.services.company_svc import get_agent_company, register_company
from agentropolis.services.digest_svc import (
    acknowledge_digest_for_agent,
    build_dashboard,
    build_digest,
)
from agentropolis.services.goal_svc import create_goal, list_goals, update_goal


@mcp.tool()
async def get_agent_status_tool(agent_api_key: str) -> dict:
    try:
        async with agent_tool_context(agent_api_key, family="agent_self") as (session, agent):
            return {"ok": True, "agent": await get_agent_status(session, agent.id)}
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def create_company_tool(agent_api_key: str, company_name: str) -> dict:
    try:
        async with agent_tool_context(agent_api_key, family="agent_self", mutate=True) as (session, agent):
            payload = await register_company(
                session,
                company_name,
                founder_agent_id=agent.id,
            )
            await session.commit()
            return {"ok": True, "company": payload}
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def get_company_tool(agent_api_key: str) -> dict:
    try:
        async with agent_tool_context(agent_api_key, family="agent_self") as (session, agent):
            return {"ok": True, "company": await get_agent_company(session, agent.id)}
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def get_autonomy_config_tool(agent_api_key: str) -> dict:
    try:
        async with agent_tool_context(agent_api_key, family="strategy") as (session, agent):
            return {"ok": True, "config": await get_autonomy_config(session, agent.id)}
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def update_autonomy_config_tool(
    agent_api_key: str,
    autopilot_enabled: bool | None = None,
    mode: str | None = None,
    spending_limit_per_hour: int | None = None,
) -> dict:
    try:
        async with agent_tool_context(agent_api_key, family="strategy", mutate=True) as (session, agent):
            payload = await update_autonomy_config(
                session,
                agent.id,
                autopilot_enabled=autopilot_enabled,
                mode=mode,
                spending_limit_per_hour=spending_limit_per_hour,
            )
            await session.commit()
            return {"ok": True, "config": payload}
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def get_standing_orders_tool(agent_api_key: str) -> dict:
    try:
        async with agent_tool_context(agent_api_key, family="strategy") as (session, agent):
            return {"ok": True, "standing_orders": await get_standing_orders(session, agent.id)}
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def update_standing_orders_tool(
    agent_api_key: str,
    standing_orders: dict | None = None,
) -> dict:
    try:
        async with agent_tool_context(agent_api_key, family="strategy", mutate=True) as (session, agent):
            payload = await update_standing_orders(session, agent.id, standing_orders)
            await session.commit()
            return {"ok": True, "standing_orders": payload}
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def get_digest_tool(agent_api_key: str) -> dict:
    try:
        async with agent_tool_context(agent_api_key, family="strategy") as (session, agent):
            return {"ok": True, "digest": await build_digest(session, agent.id)}
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def acknowledge_digest_tool(agent_api_key: str) -> dict:
    try:
        async with agent_tool_context(agent_api_key, family="strategy", mutate=True) as (session, agent):
            payload = await acknowledge_digest_for_agent(session, agent.id)
            await session.commit()
            return {"ok": True, "digest": payload}
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def get_dashboard_tool(agent_api_key: str) -> dict:
    try:
        async with agent_tool_context(agent_api_key, family="strategy") as (session, agent):
            return {"ok": True, "dashboard": await build_dashboard(session, agent.id)}
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def list_goals_tool(agent_api_key: str) -> dict:
    try:
        async with agent_tool_context(agent_api_key, family="strategy") as (session, agent):
            return {"ok": True, "goals": await list_goals(session, agent.id)}
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def create_goal_tool(
    agent_api_key: str,
    goal_type: str,
    target: dict | None = None,
    priority: int = 100,
    notes: str | None = None,
) -> dict:
    try:
        async with agent_tool_context(agent_api_key, family="strategy", mutate=True) as (session, agent):
            payload = await create_goal(
                session,
                agent.id,
                goal_type=goal_type,
                target=target,
                priority=priority,
                notes=notes,
            )
            await session.commit()
            return {"ok": True, "goal": payload}
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def update_goal_tool(
    agent_api_key: str,
    goal_id: int,
    status: str | None = None,
    priority: int | None = None,
    target: dict | None = None,
    progress: dict | None = None,
    notes: str | None = None,
) -> dict:
    try:
        async with agent_tool_context(agent_api_key, family="strategy", mutate=True) as (session, agent):
            payload = await update_goal(
                session,
                agent.id,
                goal_id,
                status=status,
                priority=priority,
                target=target,
                progress=progress,
                notes=notes,
            )
            await session.commit()
            return {"ok": True, "goal": payload}
    except Exception as exc:
        return handle_tool_error(exc)
