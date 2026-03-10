"""Worker upkeep settlement for the legacy company economy."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.config import settings
from agentropolis.models import Company, Worker
from agentropolis.services.inventory_svc import remove_resource


async def _consume_company_resource(
    session: AsyncSession,
    *,
    company: Company,
    ticker: str,
    quantity: float,
) -> float:
    if quantity <= 0:
        return 0.0
    try:
        await remove_resource(
            session,
            company.id,
            ticker,
            quantity,
            region_id=company.region_id,
        )
        return float(quantity)
    except ValueError:
        return 0.0


def _next_satisfaction(
    *,
    current: float,
    supplied_rat: bool,
    supplied_dw: bool,
) -> float:
    if supplied_rat and supplied_dw:
        return min(100.0, current + settings.SATISFACTION_RECOVERY_RATE)

    penalties = 0
    if not supplied_rat:
        penalties += 1
    if not supplied_dw:
        penalties += 1
    return max(0.0, current - settings.SATISFACTION_DECAY_RATE * penalties)


async def tick_consumption(session: AsyncSession) -> dict:
    """Settle one worker upkeep cycle for all active companies."""
    result = await session.execute(
        select(Company, Worker)
        .join(Worker, Worker.company_id == Company.id)
        .where(Company.is_active.is_(True))
    )
    rows = result.all()

    total_rat = 0.0
    total_dw = 0.0
    workers_lost = 0
    satisfaction_map: dict[int, float] = {}

    for company, worker in rows:
        worker_count = int(worker.count or 0)
        required_rat = float(worker_count) * float(settings.WORKER_RAT_PER_TICK)
        required_dw = float(worker_count) * float(settings.WORKER_DW_PER_TICK)

        consumed_rat = await _consume_company_resource(
            session,
            company=company,
            ticker="RAT",
            quantity=required_rat,
        )
        consumed_dw = await _consume_company_resource(
            session,
            company=company,
            ticker="DW",
            quantity=required_dw,
        )

        total_rat += consumed_rat
        total_dw += consumed_dw

        worker.satisfaction = _next_satisfaction(
            current=float(worker.satisfaction or 0.0),
            supplied_rat=consumed_rat >= required_rat and required_rat > 0,
            supplied_dw=consumed_dw >= required_dw and required_dw > 0,
        )

        if float(worker.satisfaction) <= 0 and worker_count > 0:
            lost = max(1, int(round(worker_count * settings.WORKER_ATTRITION_RATE)))
            worker.count = max(0, worker_count - lost)
            workers_lost += lost

        satisfaction_map[company.id] = float(worker.satisfaction)

    await session.flush()
    return {
        "companies_processed": len(rows),
        "total_rat_consumed": total_rat,
        "total_dw_consumed": total_dw,
        "workers_lost": workers_lost,
        "satisfaction_map": satisfaction_map,
    }
