"""Migration-phase housekeeping orchestrator."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import logging
from time import monotonic

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.config import settings
from agentropolis.database import async_session
from agentropolis.models import Agent, Company, GameState, HousekeepingLog
from agentropolis.services.company_svc import check_bankruptcies, recalculate_all_net_worths
from agentropolis.services.consumption import tick_consumption
from agentropolis.services.currency_svc import update_game_state_economics
from agentropolis.services.employment_svc import settle_all_wages
from agentropolis.services.event_svc import expire_events
from agentropolis.services.market_engine import match_all_resources
from agentropolis.services.nxc_mining_svc import adjust_difficulty, check_halving, update_active_refineries
from agentropolis.services.production import settle_all_buildings
from agentropolis.services.tax_svc import get_region_tax_history
from agentropolis.services.transport_svc import settle_transport_arrivals
from agentropolis.services.trait_svc import evaluate_agent_traits
from agentropolis.services.world_svc import settle_travel_arrivals
from agentropolis.services.agent_vitals import settle_all_agent_vitals

logger = logging.getLogger(__name__)


def _coerce_now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(UTC)
    if now.tzinfo is None:
        return now.replace(tzinfo=UTC)
    return now


def _normalize_timestamp(value: datetime | None, fallback: datetime) -> datetime:
    if value is None:
        return fallback
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


async def _get_or_create_game_state(session: AsyncSession) -> GameState:
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
    return state


async def _evaluate_traits(session: AsyncSession, now: datetime) -> dict:
    agent_ids = (
        await session.execute(select(Agent.id).where(Agent.is_active.is_(True)))
    ).scalars().all()
    awarded = 0
    upgraded = 0
    decayed = 0
    failures = 0
    for agent_id in agent_ids:
        try:
            summary = await evaluate_agent_traits(session, agent_id, now=now)
            awarded += len(summary["awarded"])
            upgraded += len(summary["upgraded"])
            decayed += len(summary["decayed"])
        except Exception:
            failures += 1
            logger.exception("Failed to evaluate traits for agent %s", agent_id)
    return {
        "agents_evaluated": len(agent_ids),
        "awarded": awarded,
        "upgraded": upgraded,
        "decayed": decayed,
        "failures": failures,
    }


async def _active_company_count(session: AsyncSession) -> int:
    return int(
        (
            await session.execute(
                select(func.count(Company.id)).where(Company.is_active.is_(True))
            )
        ).scalar_one()
        or 0
    )


async def _mark_runtime_running(session: AsyncSession, *, now: datetime) -> None:
    state = await _get_or_create_game_state(session)
    state.tick_interval_seconds = settings.TICK_INTERVAL_SECONDS
    state.is_running = True
    if state.started_at is None:
        state.started_at = now
    if state.last_tick_at is None:
        state.last_tick_at = now
    await session.flush()


async def _mark_runtime_stopped(session: AsyncSession) -> None:
    state = await _get_or_create_game_state(session)
    state.is_running = False
    await session.flush()


async def _run_phase(name: str, fn) -> tuple[dict, float, dict | None]:
    started = monotonic()
    try:
        result = await fn()
        return result, monotonic() - started, None
    except Exception as exc:
        logger.exception("Housekeeping phase %s failed", name)
        return {}, monotonic() - started, {"phase": name, "detail": str(exc)}


async def _execute_housekeeping_sweep(
    session: AsyncSession,
    *,
    now: datetime,
    requested_tick: int | None = None,
) -> dict:
    state = await _get_or_create_game_state(session)
    previous_tick = int(state.current_tick or 0)
    current_tick = int(requested_tick if requested_tick is not None else previous_tick + 1)
    period_start = _normalize_timestamp(state.last_tick_at, now)

    phase_timings: dict[str, float] = {}
    errors: list[dict] = []

    consumption_summary, timing, error = await _run_phase(
        "consumption",
        lambda: tick_consumption(session),
    )
    phase_timings["consumption"] = round(timing, 6)
    if error:
        errors.append(error)

    production_summary, timing, error = await _run_phase(
        "production",
        lambda: settle_all_buildings(session, now=now),
    )
    phase_timings["production"] = round(timing, 6)
    if error:
        errors.append(error)

    trade_summary, timing, error = await _run_phase(
        "market_matching",
        lambda: match_all_resources(session, current_tick=current_tick),
    )
    phase_timings["market_matching"] = round(timing, 6)
    if error:
        errors.append(error)

    wages_summary, timing, error = await _run_phase(
        "wages",
        lambda: settle_all_wages(session, now=now),
    )
    phase_timings["wages"] = round(timing, 6)
    if error:
        errors.append(error)

    vitals_summary, timing, error = await _run_phase(
        "agent_vitals",
        lambda: settle_all_agent_vitals(session, now=now),
    )
    phase_timings["agent_vitals"] = round(timing, 6)
    if error:
        errors.append(error)

    logistics_summary, timing, error = await _run_phase(
        "logistics",
        _logistics_phase(session, now),
    )
    phase_timings["logistics"] = round(timing, 6)
    if error:
        errors.append(error)

    analytics_summary, timing, error = await _run_phase(
        "analytics",
        _analytics_phase(session, now),
    )
    phase_timings["analytics"] = round(timing, 6)
    if error:
        errors.append(error)

    admin_summary, timing, error = await _run_phase(
        "admin",
        _admin_phase(session),
    )
    phase_timings["admin"] = round(timing, 6)
    if error:
        errors.append(error)

    nxc_summary, timing, error = await _run_phase(
        "nxc",
        _nxc_phase(session, now),
    )
    phase_timings["nxc"] = round(timing, 6)
    if error:
        errors.append(error)

    state.current_tick = current_tick
    state.tick_interval_seconds = settings.TICK_INTERVAL_SECONDS
    state.is_running = True
    if state.started_at is None:
        state.started_at = now
    state.last_tick_at = now

    sweep_duration = sum(phase_timings.values())
    log = HousekeepingLog(
        period_start=period_start,
        period_end=now,
        completed_at=now,
        sweep_count=current_tick,
        duration_seconds=sweep_duration,
        consumption_summary=consumption_summary,
        production_summary=production_summary,
        trade_summary=trade_summary,
        vitals_summary=vitals_summary,
        logistics_summary=logistics_summary,
        analytics_summary=analytics_summary,
        admin_summary=admin_summary,
        nxc_summary=nxc_summary,
        phase_timings=phase_timings,
        active_companies=await _active_company_count(session),
        error_count=len(errors),
        errors=errors or None,
    )
    session.add(log)
    await session.flush()

    return {
        "current_tick": current_tick,
        "period_start": period_start.isoformat(),
        "period_end": now.isoformat(),
        "consumption": consumption_summary,
        "production": production_summary,
        "trade": trade_summary,
        "vitals": vitals_summary,
        "logistics": logistics_summary,
        "analytics": analytics_summary,
        "admin": admin_summary,
        "nxc": nxc_summary,
        "error_count": len(errors),
    }


def _logistics_phase(session: AsyncSession, now: datetime):
    async def runner() -> dict:
        transport_arrivals = await settle_transport_arrivals(session, now=now)
        travel_arrivals = await settle_travel_arrivals(session, now=now)
        return {
            "transport_arrivals": transport_arrivals,
            "travel_arrivals": travel_arrivals,
        }

    return runner


def _analytics_phase(session: AsyncSession, now: datetime):
    async def runner() -> dict:
        traits = await _evaluate_traits(session, now)
        events_expired = await expire_events(session)
        economics = await update_game_state_economics(session)
        return {
            "traits": traits,
            "events_expired": events_expired,
            "economics": economics,
        }

    return runner


def _admin_phase(session: AsyncSession):
    async def runner() -> dict:
        bankruptcies = await check_bankruptcies(session)
        companies_revalued = await recalculate_all_net_worths(session)
        return {
            "bankruptcies": bankruptcies,
            "companies_revalued": companies_revalued,
        }

    return runner


def _nxc_phase(session: AsyncSession, now: datetime):
    async def runner() -> dict:
        active_refineries = await update_active_refineries(session)
        difficulty = await adjust_difficulty(session, now=now)
        halving = await check_halving(session, now=now)
        return {
            "active_refineries": active_refineries,
            "difficulty": difficulty,
            "halving": halving,
        }

    return runner


async def execute_tick(tick_number: int | None = None) -> dict:
    """Run one housekeeping sweep and commit it."""
    now = _coerce_now()
    async with async_session() as session:
        summary = await run_housekeeping_sweep(
            session,
            now=now,
            tick_number=tick_number,
        )
        await session.commit()
        return summary


async def run_housekeeping_sweep(
    session: AsyncSession,
    *,
    now: datetime | None = None,
    tick_number: int | None = None,
) -> dict:
    """Run one housekeeping sweep against a provided session."""
    return await _execute_housekeeping_sweep(
        session,
        now=_coerce_now(now),
        requested_tick=tick_number,
    )


async def run_tick_loop(stop_event: asyncio.Event | None = None) -> None:
    """Compatibility loop entrypoint backed by housekeeping sweeps."""
    if stop_event is None:
        stop_event = asyncio.Event()

    async with async_session() as session:
        await _mark_runtime_running(session, now=_coerce_now())
        await session.commit()

    try:
        while not stop_event.is_set():
            try:
                await asyncio.wait_for(
                    stop_event.wait(),
                    timeout=float(settings.TICK_INTERVAL_SECONDS),
                )
            except asyncio.TimeoutError:
                await execute_tick()
    finally:
        async with async_session() as session:
            await _mark_runtime_stopped(session)
            await session.commit()


async def record_price_history(current_tick: int) -> dict:
    """Compatibility helper for the old tick engine API."""
    async with async_session() as session:
        summary = await match_all_resources(session, current_tick=current_tick)
        await session.commit()
        return {
            "current_tick": current_tick,
            "market_matching": summary,
            "mode": "inline_trade_candles",
        }
