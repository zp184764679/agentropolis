"""Intel and public game-state MCP tools."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select

from agentropolis.api.auth import resolve_company_from_api_key
from agentropolis.mcp._shared import agent_tool_context, handle_tool_error, public_tool_context
from agentropolis.mcp.server import mcp
from agentropolis.models import Company, GameState
from agentropolis.services import leaderboard as leaderboard_svc
from agentropolis.services.market_analysis_svc import (
    get_market_intel as get_market_intel_svc,
    get_opportunities as get_opportunities_svc,
    get_route_intel as get_route_intel_svc,
)


@mcp.tool()
async def get_market_intel(agent_api_key: str, resource: str) -> dict:
    try:
        async with agent_tool_context(agent_api_key, family="strategy") as (session, agent):
            return {"ok": True, "intel": await get_market_intel_svc(session, agent.id, resource)}
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def get_route_intel(agent_api_key: str, to_region_id: int) -> dict:
    try:
        async with agent_tool_context(agent_api_key, family="strategy") as (session, agent):
            return {"ok": True, "intel": await get_route_intel_svc(session, agent.id, to_region_id)}
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def get_opportunities(agent_api_key: str) -> dict:
    try:
        async with agent_tool_context(agent_api_key, family="strategy") as (session, agent):
            return {"ok": True, "intel": await get_opportunities_svc(session, agent.id)}
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def get_game_status() -> dict:
    try:
        async with public_tool_context() as session:
            state = await session.get(GameState, 1)
            if state is None:
                raise ValueError("Game state has not been seeded yet.")

            total_companies = int(
                (await session.execute(select(func.count(Company.id)))).scalar_one() or 0
            )
            active_companies = int(
                (
                    await session.execute(
                        select(func.count(Company.id)).where(Company.is_active.is_(True))
                    )
                ).scalar_one()
                or 0
            )

            next_tick_in_seconds = None
            if state.is_running and state.last_tick_at is not None:
                last_tick_at = state.last_tick_at
                if last_tick_at.tzinfo is None:
                    last_tick_at = last_tick_at.replace(tzinfo=UTC)
                elapsed = (datetime.now(UTC) - last_tick_at).total_seconds()
                next_tick_in_seconds = max(float(state.tick_interval_seconds) - elapsed, 0.0)

            return {
                "ok": True,
                "status": {
                    "current_tick": state.current_tick,
                    "tick_interval_seconds": state.tick_interval_seconds,
                    "is_running": state.is_running,
                    "next_tick_in_seconds": next_tick_in_seconds,
                    "total_companies": total_companies,
                    "active_companies": active_companies,
                },
            }
    except Exception as exc:
        return handle_tool_error(exc)


@mcp.tool()
async def get_leaderboard(metric: str = "net_worth", company_api_key: str | None = None) -> dict:
    try:
        async with public_tool_context() as session:
            company = None
            if company_api_key:
                company = await resolve_company_from_api_key(session, company_api_key)

            ranked = await leaderboard_svc.get_leaderboard(session, metric=metric, limit=None)
            entries = [
                {
                    "rank": row["rank"],
                    "company_name": row["company_name"],
                    "net_worth": row["net_worth"],
                    "balance": row["balance"],
                    "worker_count": row["worker_count"],
                    "building_count": row["building_count"],
                }
                for row in ranked[:20]
            ]
            your_rank = None
            if company is not None:
                your_rank = next(
                    (row["rank"] for row in ranked if row["company_id"] == company.id),
                    None,
                )

            return {
                "ok": True,
                "leaderboard": {
                    "metric": metric.lower(),
                    "entries": entries,
                    "your_rank": your_rank,
                },
            }
    except Exception as exc:
        return handle_tool_error(exc)
