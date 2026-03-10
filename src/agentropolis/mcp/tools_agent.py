"""Agent-centric MCP tools for lifecycle and public profile reads."""

from __future__ import annotations

from sqlalchemy import select

from agentropolis.mcp._shared import (
    agent_tool_context,
    handle_tool_error,
    parity_http_error,
    public_tool_context,
)
from agentropolis.mcp.server import mcp
from agentropolis.models import Agent
from agentropolis.services.agent_svc import (
    drink as drink_agent,
    eat as eat_agent,
    get_agent_status as get_agent_status_svc,
    register_agent as register_agent_svc,
    rest as rest_agent,
)
from agentropolis.services.strategy_svc import get_public_profile
from agentropolis.services.trait_svc import get_agent_traits


@mcp.tool()
async def register_agent(name: str, home_region_id: int | None = None) -> dict:
    try:
        async with public_tool_context() as session:
            payload = await register_agent_svc(session, name, home_region_id)
            await session.commit()
            return {"ok": True, "agent": payload}
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def get_agent_status(agent_api_key: str) -> dict:
    try:
        async with agent_tool_context(agent_api_key, family="agent_self") as (session, agent):
            return {"ok": True, "agent": await get_agent_status_svc(session, agent.id)}
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def eat(agent_api_key: str, amount: int = 1) -> dict:
    try:
        async with agent_tool_context(
            agent_api_key,
            family="agent_self",
            mutate=True,
            allow_in_degraded_mode=True,
            operation="vitals_mutations",
        ) as (session, agent):
            payload = await eat_agent(session, agent.id, amount=amount)
            await session.commit()
            return {
                "ok": True,
                "message": f"Ate {payload['consumed']} RAT. Hunger is now {payload['status']['hunger']:.1f}.",
                "result": payload,
            }
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def drink(agent_api_key: str, amount: int = 1) -> dict:
    try:
        async with agent_tool_context(
            agent_api_key,
            family="agent_self",
            mutate=True,
            allow_in_degraded_mode=True,
            operation="vitals_mutations",
        ) as (session, agent):
            payload = await drink_agent(session, agent.id, amount=amount)
            await session.commit()
            return {
                "ok": True,
                "message": f"Drank {payload['consumed']} DW. Thirst is now {payload['status']['thirst']:.1f}.",
                "result": payload,
            }
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def rest(agent_api_key: str) -> dict:
    try:
        async with agent_tool_context(
            agent_api_key,
            family="agent_self",
            mutate=True,
            allow_in_degraded_mode=True,
            operation="vitals_mutations",
        ) as (session, agent):
            payload = await rest_agent(session, agent.id)
            await session.commit()
            return {
                "ok": True,
                "message": f"Rested. Energy is now {payload['energy']:.1f}.",
                "status": payload,
            }
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def get_agent_profile(agent_api_key: str, agent_id: int) -> dict:
    try:
        async with agent_tool_context(agent_api_key, family="agent_self") as (session, _agent):
            result = await session.execute(select(Agent).where(Agent.id == agent_id))
            target = result.scalar_one_or_none()
            if target is None:
                raise parity_http_error(404, "Agent not found")

            strategy = await get_public_profile(session, agent_id)
            traits = await get_agent_traits(session, agent_id)

            return {
                "ok": True,
                "profile": {
                    "agent_id": target.id,
                    "name": target.name,
                    "reputation": target.reputation,
                    "is_alive": target.is_alive,
                    "current_region_id": target.current_region_id,
                    "career_path": target.career_path,
                    "strategy": strategy,
                    "traits": traits,
                },
            }
    except Exception as exc:
        return handle_tool_error(exc)
