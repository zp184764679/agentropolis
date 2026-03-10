"""Strategy, autonomy, digest, and briefing MCP tools."""

from __future__ import annotations

from sqlalchemy import select

from agentropolis.mcp._shared import (
    agent_tool_context,
    handle_tool_error,
    parity_http_error,
)
from agentropolis.mcp.server import mcp
from agentropolis.models.agent import Agent as AgentModel
from agentropolis.models.strategy_profile import StrategyProfile
from agentropolis.services.autopilot import (
    get_autonomy_config,
    get_standing_orders,
    update_autonomy_config,
    update_standing_orders,
)
from agentropolis.services.decision_log_svc import get_decision_analysis, get_recent_decisions
from agentropolis.services.digest_svc import acknowledge_digest_for_agent, build_dashboard, build_digest
from agentropolis.services.goal_svc import create_goal, list_goals, update_goal
from agentropolis.services.strategy_svc import create_or_update_profile, get_profile, get_public_profile


async def _list_public_standing_orders(session, region_id: int | None = None) -> dict:
    query = (
        select(StrategyProfile, AgentModel.name, AgentModel.current_region_id)
        .join(AgentModel, StrategyProfile.agent_id == AgentModel.id)
        .where(
            StrategyProfile.standing_orders.is_not(None),
            AgentModel.is_active.is_(True),
        )
    )
    if region_id is not None:
        query = query.where(AgentModel.current_region_id == region_id)
    result = await session.execute(query)
    rows = result.all()
    return {
        "standing_orders": [
            {
                "agent_id": profile.agent_id,
                "agent_name": name,
                "current_region_id": current_region,
                "combat_doctrine": profile.combat_doctrine.value,
                "standing_orders": profile.standing_orders,
            }
            for profile, name, current_region in rows
        ]
    }


@mcp.tool()
async def strategy_profile_tool(
    agent_api_key: str,
    action: str = "get",
    target_agent_id: int | None = None,
    combat_doctrine: str | None = None,
    risk_tolerance: float | None = None,
    primary_focus: str | None = None,
    secondary_focus: str | None = None,
    default_stance: str | None = None,
) -> dict:
    mutate = action == "update"
    try:
        async with agent_tool_context(
            agent_api_key,
            family="strategy",
            mutate=mutate,
            operation="strategy_profile_update" if mutate else None,
        ) as (session, agent):
            if action == "get":
                profile = await get_profile(session, agent.id)
                if profile is None:
                    payload = await create_or_update_profile(session, agent.id)
                    await session.commit()
                    return {"ok": True, "profile": payload}
                return {
                    "ok": True,
                    "profile": {
                        "agent_id": profile.agent_id,
                        "combat_doctrine": profile.combat_doctrine.value,
                        "risk_tolerance": profile.risk_tolerance,
                        "primary_focus": profile.primary_focus.value,
                        "secondary_focus": profile.secondary_focus.value if profile.secondary_focus else None,
                        "default_stance": profile.default_stance.value,
                        "standing_orders": profile.standing_orders,
                        "version": profile.version,
                    },
                }
            if action == "update":
                payload = await create_or_update_profile(
                    session,
                    agent.id,
                    combat_doctrine=combat_doctrine,
                    risk_tolerance=risk_tolerance,
                    primary_focus=primary_focus,
                    secondary_focus=secondary_focus,
                    default_stance=default_stance,
                )
                await session.commit()
                return {"ok": True, "profile": payload}
            if action == "scout":
                if target_agent_id is None:
                    raise ValueError("target_agent_id is required for scout")
                payload = await get_public_profile(session, target_agent_id)
                if payload is None:
                    raise parity_http_error(404, "Agent has no strategy profile")
                return {"ok": True, "profile": payload}
            raise ValueError("Unsupported action for strategy_profile_tool")
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def autonomy_tool(
    agent_api_key: str,
    action: str = "get_config",
    goal_id: int | None = None,
    goal_type: str | None = None,
    target: dict | None = None,
    priority: int | None = None,
    notes: str | None = None,
    status: str | None = None,
    progress: dict | None = None,
    standing_orders: dict | None = None,
    autopilot_enabled: bool | None = None,
    mode: str | None = None,
    spending_limit_per_hour: int | None = None,
) -> dict:
    mutate = action in {"update_config", "update_standing_orders", "create_goal", "update_goal"}
    try:
        operation = None
        if action == "update_config":
            operation = "autonomy_config_update"
        elif action == "update_standing_orders":
            operation = "standing_order_replace"
        elif action in {"create_goal", "update_goal"}:
            operation = "goal_create_update"
        async with agent_tool_context(
            agent_api_key,
            family="strategy",
            mutate=mutate,
            operation=operation,
        ) as (session, agent):
            if action == "get_config":
                return {"ok": True, "config": await get_autonomy_config(session, agent.id)}
            if action == "update_config":
                payload = await update_autonomy_config(
                    session,
                    agent.id,
                    autopilot_enabled=autopilot_enabled,
                    mode=mode,
                    spending_limit_per_hour=spending_limit_per_hour,
                )
                await session.commit()
                return {"ok": True, "config": payload}
            if action == "get_standing_orders":
                return {"ok": True, "standing_orders": await get_standing_orders(session, agent.id)}
            if action == "update_standing_orders":
                payload = await update_standing_orders(session, agent.id, standing_orders)
                await session.commit()
                return {"ok": True, "standing_orders": payload}
            if action == "list_goals":
                return {"ok": True, "goals": await list_goals(session, agent.id)}
            if action == "create_goal":
                if goal_type is None:
                    raise ValueError("goal_type is required for create_goal")
                payload = await create_goal(
                    session,
                    agent.id,
                    goal_type=goal_type,
                    target=target,
                    priority=priority or 100,
                    notes=notes,
                )
                await session.commit()
                return {"ok": True, "goal": payload}
            if action == "update_goal":
                if goal_id is None:
                    raise ValueError("goal_id is required for update_goal")
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
            raise ValueError("Unsupported action for autonomy_tool")
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def digest_tool(agent_api_key: str, action: str = "get") -> dict:
    mutate = action == "ack"
    try:
        async with agent_tool_context(
            agent_api_key,
            family="strategy",
            mutate=mutate,
            operation="digest_acknowledge" if mutate else None,
        ) as (session, agent):
            if action == "get":
                return {"ok": True, "digest": await build_digest(session, agent.id)}
            if action == "ack":
                payload = await acknowledge_digest_for_agent(session, agent.id)
                await session.commit()
                return {"ok": True, "digest": payload}
            raise ValueError("Unsupported action for digest_tool")
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def briefing_tool(
    agent_api_key: str,
    section: str = "dashboard",
    limit: int = 50,
    decision_type: str | None = None,
    region_id: int | None = None,
) -> dict:
    try:
        async with agent_tool_context(agent_api_key, family="strategy") as (session, agent):
            if section == "dashboard":
                return {"ok": True, "briefing": await build_dashboard(session, agent.id)}
            if section == "decisions":
                return {
                    "ok": True,
                    "briefing": {
                        "entries": await get_recent_decisions(
                            session,
                            agent.id,
                            limit=limit,
                            decision_type=decision_type,
                        )
                    },
                }
            if section == "analysis":
                return {"ok": True, "briefing": await get_decision_analysis(session, agent.id)}
            if section == "public_standing_orders":
                return {"ok": True, "briefing": await _list_public_standing_orders(session, region_id=region_id)}
            raise ValueError("Unsupported section for briefing_tool")
    except Exception as exc:
        return handle_tool_error(exc)
