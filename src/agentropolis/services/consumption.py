"""NPC workforce upkeep settlement for the legacy company economy."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.config import settings
from agentropolis.models import AgentEmployment, Company
from agentropolis.services.inventory_svc import remove_resource

ROLE_CONSUMPTION_MULTIPLIER = {
    "worker": 1.00,
    "foreman": 1.20,
    "manager": 1.50,
    "director": 2.00,
    "ceo": 2.50,
}

ROLE_PRODUCTIVITY_BONUS = {
    "worker": 0.00,
    "foreman": 0.03,
    "manager": 0.08,
    "director": 0.15,
    "ceo": 0.25,
}

MAX_MANAGEMENT_BONUS = 0.75


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


def _base_worker_productivity_modifier(satisfaction: float) -> float:
    return 0.5 if satisfaction < settings.LOW_SATISFACTION_THRESHOLD else 1.0


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


def _empty_tier_counts() -> dict[str, int]:
    return {
        "npc_workers": 0,
        "worker": 0,
        "foreman": 0,
        "manager": 0,
        "director": 0,
        "ceo": 0,
    }


def _employment_tier_counts(employments: list[AgentEmployment]) -> dict[str, int]:
    counts = _empty_tier_counts()
    for employment in employments:
        counts[employment.role.value] = counts.get(employment.role.value, 0) + 1
    return counts


def _tier_consumption_load(employments: list[AgentEmployment]) -> float:
    return sum(
        ROLE_CONSUMPTION_MULTIPLIER.get(employment.role.value, 1.0)
        for employment in employments
    )


def _management_bonus(employments: list[AgentEmployment]) -> float:
    return min(
        MAX_MANAGEMENT_BONUS,
        sum(ROLE_PRODUCTIVITY_BONUS.get(employment.role.value, 0.0) for employment in employments),
    )


async def get_company_workforce_profile(
    session: AsyncSession,
    company_id: int,
) -> dict:
    company = (
        await session.execute(select(Company).where(Company.id == company_id))
    ).scalar_one_or_none()
    if company is None:
        raise ValueError(f"Company {company_id} not found")

    employments = list(
        (
            await session.execute(
                select(AgentEmployment).where(AgentEmployment.company_id == company_id)
            )
        ).scalars().all()
    )

    tier_counts = _employment_tier_counts(employments)
    npc_workers = int(company.npc_worker_count or 0)
    tier_counts["npc_workers"] = npc_workers
    satisfaction = float(company.npc_satisfaction or 0.0)
    employment_count = len(employments)
    management_bonus = _management_bonus(employments)
    equivalent_load = float(npc_workers) + _tier_consumption_load(employments)

    return {
        "company_id": company.id,
        "count": npc_workers,
        "satisfaction": satisfaction,
        "employment_count": employment_count,
        "total_headcount": npc_workers + employment_count,
        "tier_counts": tier_counts,
        "management_bonus": round(management_bonus, 3),
        "rat_consumption_per_tick": round(equivalent_load * settings.WORKER_RAT_PER_TICK, 3),
        "dw_consumption_per_tick": round(equivalent_load * settings.WORKER_DW_PER_TICK, 3),
        "productivity_modifier": round(
            _base_worker_productivity_modifier(satisfaction) * (1.0 + management_bonus),
            3,
        ),
    }


async def tick_consumption(session: AsyncSession) -> dict:
    """Settle one worker upkeep cycle for all active companies."""
    rows = (
        await session.execute(select(Company).where(Company.is_active.is_(True)))
    ).scalars().all()

    total_rat = 0.0
    total_dw = 0.0
    workers_lost = 0
    satisfaction_map: dict[int, float] = {}
    productivity_map: dict[int, float] = {}
    tier_counts_map: dict[int, dict[str, int]] = {}
    employment_count_map: dict[int, int] = {}

    employment_rows = (
        await session.execute(select(AgentEmployment).where(AgentEmployment.company_id.is_not(None)))
    ).scalars().all()
    employments_by_company: dict[int, list[AgentEmployment]] = {}
    for employment in employment_rows:
        employments_by_company.setdefault(employment.company_id, []).append(employment)

    now = datetime.now(UTC)

    for company in rows:
        worker_count = int(company.npc_worker_count or 0)
        employments = employments_by_company.get(company.id, [])
        tier_counts = _employment_tier_counts(employments)
        tier_counts["npc_workers"] = worker_count
        equivalent_load = float(worker_count) + _tier_consumption_load(employments)
        required_rat = equivalent_load * float(settings.WORKER_RAT_PER_TICK)
        required_dw = equivalent_load * float(settings.WORKER_DW_PER_TICK)

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

        company.npc_satisfaction = _next_satisfaction(
            current=float(company.npc_satisfaction or 0.0),
            supplied_rat=consumed_rat >= required_rat and required_rat > 0,
            supplied_dw=consumed_dw >= required_dw and required_dw > 0,
        )

        if float(company.npc_satisfaction) <= 0 and worker_count > 0:
            lost = max(1, int(round(worker_count * settings.WORKER_ATTRITION_RATE)))
            company.npc_worker_count = max(0, worker_count - lost)
            workers_lost += lost

        company.last_consumption_at = now
        satisfaction_map[company.id] = float(company.npc_satisfaction)
        productivity_map[company.id] = round(
            _base_worker_productivity_modifier(float(company.npc_satisfaction))
            * (1.0 + _management_bonus(employments)),
            3,
        )
        tier_counts_map[company.id] = tier_counts
        employment_count_map[company.id] = len(employments)

    await session.flush()
    return {
        "companies_processed": len(rows),
        "total_rat_consumed": total_rat,
        "total_dw_consumed": total_dw,
        "workers_lost": workers_lost,
        "satisfaction_map": satisfaction_map,
        "productivity_map": productivity_map,
        "tier_counts_map": tier_counts_map,
        "employment_count_map": employment_count_map,
    }
