"""Currency service - inflation monitoring and money supply tracking."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.config import settings
from agentropolis.models import Agent, Company, GameState


async def get_total_currency_supply(session: AsyncSession) -> int:
    """Calculate total copper in company and agent balances."""
    company_supply = int(
        (await session.execute(select(func.coalesce(func.sum(Company.balance), 0)))).scalar_one()
        or 0
    )
    agent_supply = int(
        (
            await session.execute(
                select(func.coalesce(func.sum(Agent.personal_balance), 0))
            )
        ).scalar_one()
        or 0
    )
    return company_supply + agent_supply


async def calculate_inflation_index(session: AsyncSession) -> float:
    """Calculate a simple inflation index based on active participants."""
    total_supply = await get_total_currency_supply(session)
    active_companies = int(
        (
            await session.execute(
                select(func.count(Company.id)).where(Company.is_active.is_(True))
            )
        ).scalar_one()
        or 0
    )
    active_agents = int(
        (
            await session.execute(
                select(func.count(Agent.id)).where(Agent.is_active.is_(True))
            )
        ).scalar_one()
        or 0
    )

    baseline = max(
        1,
        active_companies * int(settings.INITIAL_BALANCE)
        + active_agents * max(int(settings.INITIAL_BALANCE // 10), 1),
    )
    return round(max(0.1, float(total_supply) / float(baseline)), 4)


async def update_game_state_economics(session: AsyncSession) -> dict:
    """Update GameState with latest inflation_index and total_currency_supply."""
    state = await session.get(GameState, 1)
    if state is None:
        state = GameState(
            id=1,
            current_tick=0,
            tick_interval_seconds=settings.TICK_INTERVAL_SECONDS,
            is_running=False,
        )
        session.add(state)
        await session.flush()

    total_supply = await get_total_currency_supply(session)
    inflation_index = await calculate_inflation_index(session)
    state.total_currency_supply = total_supply
    state.inflation_index = inflation_index
    await session.flush()
    return {
        "total_currency_supply": total_supply,
        "inflation_index": inflation_index,
    }
