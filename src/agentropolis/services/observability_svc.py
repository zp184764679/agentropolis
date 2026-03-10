"""Local-preview observability snapshot helpers."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.middleware.metrics import get_request_metrics_snapshot
from agentropolis.models import Agent, Company, GameState, HousekeepingLog
from agentropolis.services.concurrency import get_concurrency_snapshot
from agentropolis.services.economy_governance import build_economy_health_thresholds


async def build_observability_snapshot(session: AsyncSession) -> dict:
    thresholds = build_economy_health_thresholds()
    state = await session.get(GameState, 1)
    latest_housekeeping = (
        await session.execute(
            select(HousekeepingLog).order_by(HousekeepingLog.sweep_count.desc()).limit(1)
        )
    ).scalar_one_or_none()

    active_agents = int(
        (
            await session.execute(
                select(func.count(Agent.id)).where(Agent.is_active.is_(True))
            )
        ).scalar_one()
        or 0
    )
    active_companies = int(
        (
            await session.execute(
                select(func.count(Company.id)).where(Company.is_active.is_(True))
            )
        ).scalar_one()
        or 0
    )

    inflation_index = float(state.inflation_index) if state is not None else 1.0
    worker_warning = thresholds["worker_satisfaction"]["warning_below"]
    return {
        "requests": get_request_metrics_snapshot(),
        "concurrency": get_concurrency_snapshot(),
        "economy": {
            "active_agents": active_agents,
            "active_companies": active_companies,
            "total_currency_supply": int(state.total_currency_supply) if state is not None else 0,
            "inflation_index": inflation_index,
            "thresholds": thresholds,
            "health_flags": {
                "inflation_warning": inflation_index >= thresholds["inflation_index"]["warning_above"],
                "inflation_critical": inflation_index >= thresholds["inflation_index"]["critical_above"],
                "worker_satisfaction_warning_below": worker_warning,
            },
        },
        "housekeeping": {
            "latest_sweep": (
                {
                    "sweep_count": latest_housekeeping.sweep_count,
                    "completed_at": (
                        latest_housekeeping.completed_at.isoformat()
                        if latest_housekeeping.completed_at
                        else None
                    ),
                    "duration_seconds": latest_housekeeping.duration_seconds,
                    "error_count": latest_housekeeping.error_count,
                }
                if latest_housekeeping is not None
                else None
            ),
            "runtime_tick": int(state.current_tick) if state is not None else 0,
            "tick_interval_seconds": int(state.tick_interval_seconds) if state is not None else 0,
            "is_running": bool(state.is_running) if state is not None else False,
        },
    }
