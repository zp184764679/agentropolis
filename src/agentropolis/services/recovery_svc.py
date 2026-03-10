"""State snapshot and derived-state repair helpers."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.models import (
    Agent,
    Company,
    ContractStatus,
    GameState,
    HousekeepingLog,
    MercenaryContract,
    Notification,
    Order,
    OrderStatus,
    Region,
    TransportOrder,
    TransportStatus,
    Trade,
)
from agentropolis.services.company_svc import recalculate_all_net_worths
from agentropolis.services.currency_svc import update_game_state_economics
from agentropolis.services.leaderboard import get_leaderboard


async def build_world_snapshot(
    session: AsyncSession,
    *,
    housekeeping_limit: int = 5,
) -> dict:
    captured_at = datetime.now(UTC).isoformat()
    state = await session.get(GameState, 1)

    counts = {
        "agents": int((await session.execute(select(func.count(Agent.id)))).scalar_one() or 0),
        "active_agents": int(
            (
                await session.execute(
                    select(func.count(Agent.id)).where(Agent.is_active.is_(True))
                )
            ).scalar_one()
            or 0
        ),
        "companies": int((await session.execute(select(func.count(Company.id)))).scalar_one() or 0),
        "active_companies": int(
            (
                await session.execute(
                    select(func.count(Company.id)).where(Company.is_active.is_(True))
                )
            ).scalar_one()
            or 0
        ),
        "regions": int((await session.execute(select(func.count(Region.id)))).scalar_one() or 0),
        "open_orders": int(
            (
                await session.execute(
                    select(func.count(Order.id)).where(
                        Order.status.in_((OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED))
                    )
                )
            ).scalar_one()
            or 0
        ),
        "trades": int((await session.execute(select(func.count(Trade.id)))).scalar_one() or 0),
        "active_contracts": int(
            (
                await session.execute(
                    select(func.count(MercenaryContract.id)).where(
                        MercenaryContract.status.in_((ContractStatus.OPEN, ContractStatus.ACTIVE))
                    )
                )
            ).scalar_one()
            or 0
        ),
        "transports_in_flight": int(
            (
                await session.execute(
                    select(func.count(TransportOrder.id)).where(
                        TransportOrder.status == TransportStatus.IN_TRANSIT
                    )
                )
            ).scalar_one()
            or 0
        ),
        "unread_notifications": int(
            (
                await session.execute(
                    select(func.count(Notification.id)).where(Notification.is_read.is_(False))
                )
            ).scalar_one()
            or 0
        ),
    }

    housekeeping_rows = (
        await session.execute(
            select(HousekeepingLog)
            .order_by(HousekeepingLog.sweep_count.desc())
            .limit(housekeeping_limit)
        )
    ).scalars().all()

    return {
        "captured_at": captured_at,
        "game_state": (
            {
                "current_tick": state.current_tick,
                "tick_interval_seconds": state.tick_interval_seconds,
                "is_running": state.is_running,
                "last_tick_at": state.last_tick_at.isoformat() if state.last_tick_at else None,
                "total_currency_supply": state.total_currency_supply,
                "inflation_index": state.inflation_index,
            }
            if state is not None
            else None
        ),
        "counts": counts,
        "top_companies": await get_leaderboard(session, limit=5),
        "recent_housekeeping": [
            {
                "sweep_count": row.sweep_count,
                "completed_at": row.completed_at.isoformat() if row.completed_at else None,
                "duration_seconds": row.duration_seconds,
                "error_count": row.error_count,
            }
            for row in housekeeping_rows
        ],
    }


async def repair_derived_state(session: AsyncSession) -> dict:
    companies_revalued = await recalculate_all_net_worths(session)
    economy = await update_game_state_economics(session)
    return {
        "companies_revalued": companies_revalued,
        "economy": economy,
    }
