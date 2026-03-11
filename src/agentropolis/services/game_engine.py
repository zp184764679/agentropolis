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
from agentropolis.services.concurrency import acquire_housekeeping_slot
from agentropolis.services.consumption import tick_consumption
from agentropolis.services.contract_svc import expire_contracts
from agentropolis.services.currency_svc import update_game_state_economics
from agentropolis.services.decay_svc import settle_all_perishable_decay
from agentropolis.services.digest_svc import build_digest_housekeeping_summary
from agentropolis.services.employment_svc import settle_all_wages
from agentropolis.services.execution_svc import (
    run_due_execution_jobs,
    schedule_missed_housekeeping_backfills,
)
from agentropolis.services.event_svc import apply_active_event_effects, expire_events
from agentropolis.services.goal_svc import compute_all_goal_progress
from agentropolis.services.market_engine import match_all_resources
from agentropolis.services.maintenance_svc import settle_all_building_decay
from agentropolis.services.nxc_mining_svc import adjust_difficulty, check_halving, update_active_refineries
from agentropolis.services.notification_svc import prune_old_notifications
from agentropolis.services.npc_shop_svc import restock_shops
from agentropolis.services.production import settle_all_buildings
from agentropolis.services.regional_project_svc import settle_project_completions
from agentropolis.services.structured_logging import emit_structured_log
from agentropolis.services.tax_svc import get_region_tax_history
from agentropolis.services.transport_svc import settle_transport_arrivals
from agentropolis.services.trait_svc import evaluate_agent_traits
from agentropolis.services.world_svc import settle_travel_arrivals
from agentropolis.services.agent_vitals import settle_all_agent_vitals
from agentropolis.services.autopilot import run_all_reflexes, run_all_standing_orders

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
    max_attempts = max(1, int(settings.EXECUTION_PHASE_MAX_ATTEMPTS))
    attempt_history: list[dict] = []
    for attempt in range(1, max_attempts + 1):
        try:
            result = await fn()
            attempt_history.append({"attempt": attempt, "status": "completed"})
            return (
                {
                    "status": "completed",
                    "attempts": attempt,
                    "max_attempts": max_attempts,
                    "retry_used": attempt > 1,
                    "attempt_history": attempt_history,
                    "result": result,
                    "last_error": None,
                },
                monotonic() - started,
                None,
            )
        except Exception as exc:
            logger.exception("Housekeeping phase %s failed on attempt %s", name, attempt)
            detail = str(exc)
            attempt_history.append(
                {
                    "attempt": attempt,
                    "status": "failed",
                    "detail": detail,
                    "retryable": attempt < max_attempts,
                }
            )
            if attempt >= max_attempts:
                return (
                    {
                        "status": "failed",
                        "attempts": attempt,
                        "max_attempts": max_attempts,
                        "retry_used": attempt > 1,
                        "attempt_history": attempt_history,
                        "result": {},
                        "last_error": {
                            "phase": name,
                            "detail": detail,
                            "attempt": attempt,
                        },
                        "manual_repair_path": [
                            "/meta/execution/jobs/housekeeping-backfill",
                            "/meta/execution/jobs/{job_id}/retry",
                            "agentropolis repair-derived-state",
                        ],
                    },
                    monotonic() - started,
                    {"phase": name, "detail": detail, "attempt": attempt},
                )
    return (
        {
            "status": "failed",
            "attempts": max_attempts,
            "max_attempts": max_attempts,
            "retry_used": False,
            "attempt_history": attempt_history,
            "result": {},
            "last_error": {"phase": name, "detail": "phase_failed"},
        },
        monotonic() - started,
        {"phase": name, "detail": "phase_failed"},
    )


async def _execute_housekeeping_sweep(
    session: AsyncSession,
    *,
    now: datetime,
    requested_tick: int | None = None,
    trigger_kind: str = "scheduled",
    execution_job_id: int | None = None,
) -> dict:
    state = await _get_or_create_game_state(session)
    previous_tick = int(state.current_tick or 0)
    current_tick = int(requested_tick if requested_tick is not None else previous_tick + 1)
    period_start = _normalize_timestamp(state.last_tick_at, now)

    phase_timings: dict[str, float] = {}
    phase_results: dict[str, dict] = {}
    errors: list[dict] = []

    consumption_phase, timing, error = await _run_phase(
        "consumption",
        lambda: tick_consumption(session),
    )
    consumption_summary = dict(consumption_phase["result"] or {})
    phase_timings["consumption"] = round(timing, 6)
    phase_results["consumption"] = consumption_phase
    if error:
        errors.append(error)

    production_phase, timing, error = await _run_phase(
        "production",
        lambda: settle_all_buildings(session, now=now),
    )
    production_summary = dict(production_phase["result"] or {})
    phase_timings["production"] = round(timing, 6)
    phase_results["production"] = production_phase
    if error:
        errors.append(error)

    trade_phase, timing, error = await _run_phase(
        "market_matching",
        lambda: match_all_resources(session, current_tick=current_tick),
    )
    trade_summary = dict(trade_phase["result"] or {})
    phase_timings["market_matching"] = round(timing, 6)
    phase_results["market_matching"] = trade_phase
    if error:
        errors.append(error)

    wages_phase, timing, error = await _run_phase(
        "wages",
        lambda: settle_all_wages(session, now=now),
    )
    wages_summary = dict(wages_phase["result"] or {})
    phase_timings["wages"] = round(timing, 6)
    phase_results["wages"] = wages_phase
    if error:
        errors.append(error)

    vitals_phase, timing, error = await _run_phase(
        "agent_vitals",
        lambda: settle_all_agent_vitals(session, now=now),
    )
    vitals_summary = dict(vitals_phase["result"] or {})
    phase_timings["agent_vitals"] = round(timing, 6)
    phase_results["agent_vitals"] = vitals_phase
    if error:
        errors.append(error)

    autonomy_phase, timing, error = await _run_phase(
        "autonomy",
        _autonomy_phase(session, now, current_tick),
    )
    autonomy_summary = dict(autonomy_phase["result"] or {})
    phase_timings["autonomy"] = round(timing, 6)
    phase_results["autonomy"] = autonomy_phase
    if error:
        errors.append(error)

    digest_phase, timing, error = await _run_phase(
        "digest",
        _digest_phase(session, now),
    )
    digest_summary = dict(digest_phase["result"] or {})
    phase_timings["digest"] = round(timing, 6)
    phase_results["digest"] = digest_phase
    if error:
        errors.append(error)

    logistics_phase, timing, error = await _run_phase(
        "logistics",
        _logistics_phase(session, now),
    )
    logistics_summary = dict(logistics_phase["result"] or {})
    phase_timings["logistics"] = round(timing, 6)
    phase_results["logistics"] = logistics_phase
    if error:
        errors.append(error)

    analytics_phase, timing, error = await _run_phase(
        "analytics",
        _analytics_phase(session, now),
    )
    analytics_summary = dict(analytics_phase["result"] or {})
    phase_timings["analytics"] = round(timing, 6)
    phase_results["analytics"] = analytics_phase
    if error:
        errors.append(error)

    admin_phase, timing, error = await _run_phase(
        "admin",
        _admin_phase(session, now),
    )
    admin_summary = dict(admin_phase["result"] or {})
    phase_timings["admin"] = round(timing, 6)
    phase_results["admin"] = admin_phase
    if error:
        errors.append(error)

    nxc_phase, timing, error = await _run_phase(
        "nxc",
        _nxc_phase(session, now),
    )
    nxc_summary = dict(nxc_phase["result"] or {})
    phase_timings["nxc"] = round(timing, 6)
    phase_results["nxc"] = nxc_phase
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
        trigger_kind=trigger_kind,
        execution_job_id=execution_job_id,
        consumption_summary=consumption_summary,
        production_summary=production_summary,
        trade_summary=trade_summary,
        vitals_summary=vitals_summary,
        logistics_summary=logistics_summary,
        autonomy_summary=autonomy_summary,
        digest_summary=digest_summary,
        analytics_summary=analytics_summary,
        admin_summary=admin_summary,
        nxc_summary=nxc_summary,
        phase_timings=phase_timings,
        phase_results=phase_results,
        active_companies=await _active_company_count(session),
        error_count=len(errors),
        errors=errors or None,
    )
    session.add(log)
    await session.flush()
    emit_structured_log(
        logger,
        "housekeeping_sweep_completed",
        sweep_count=current_tick,
        trigger_kind=trigger_kind,
        execution_job_id=execution_job_id,
        duration_seconds=round(sweep_duration, 6),
        error_count=len(errors),
        active_companies=log.active_companies,
        phase_timings=phase_timings,
        reflex_actions=int(
            ((autonomy_summary.get("reflex") or {}).get("actions") or 0)
        ),
        standing_orders_created=int(
            ((autonomy_summary.get("standing_orders") or {}).get("buy_orders_created") or 0)
        )
        + int(((autonomy_summary.get("standing_orders") or {}).get("sell_orders_created") or 0)),
        goals_completed=int(
            ((autonomy_summary.get("goals") or {}).get("completed_now") or 0)
        ),
    )

    return {
        "current_tick": current_tick,
        "period_start": period_start.isoformat(),
        "period_end": now.isoformat(),
        "trigger_kind": trigger_kind,
        "execution_job_id": execution_job_id,
        "consumption": consumption_summary,
        "production": production_summary,
        "trade": trade_summary,
        "vitals": vitals_summary,
        "autonomy": autonomy_summary,
        "digest": digest_summary,
        "logistics": logistics_summary,
        "analytics": analytics_summary,
        "admin": admin_summary,
        "nxc": nxc_summary,
        "phase_results": phase_results,
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


def _autonomy_phase(session: AsyncSession, now: datetime, current_tick: int):
    async def runner() -> dict:
        reflex = await run_all_reflexes(session, now=now)
        standing_orders: dict = {
            "skipped": True,
            "reason": "interval_not_reached",
        }
        goals: dict = {
            "skipped": True,
            "reason": "interval_not_reached",
        }

        if current_tick % settings.AUTOPILOT_STANDING_ORDER_SWEEP_INTERVAL == 0:
            standing_orders = await run_all_standing_orders(
                session,
                now=now,
                current_tick=current_tick,
            )

        if current_tick % settings.AUTOPILOT_GOAL_SWEEP_INTERVAL == 0:
            goals = await compute_all_goal_progress(session, now=now)

        return {
            "reflex": reflex,
            "standing_orders": standing_orders,
            "goals": goals,
        }

    return runner


def _digest_phase(session: AsyncSession, now: datetime):
    async def runner() -> dict:
        return await build_digest_housekeeping_summary(session, now=now)

    return runner


def _analytics_phase(session: AsyncSession, now: datetime):
    async def runner() -> dict:
        traits = await _evaluate_traits(session, now)
        events_expired = await expire_events(session)
        event_effects = await apply_active_event_effects(session, now=now)
        economics = await update_game_state_economics(session)
        return {
            "traits": traits,
            "events_expired": events_expired,
            "event_effects": event_effects,
            "economics": economics,
        }

    return runner


def _admin_phase(session: AsyncSession, now: datetime):
    async def runner() -> dict:
        bankruptcies = await check_bankruptcies(session)
        companies_revalued = await recalculate_all_net_worths(session)
        contracts_expired = await expire_contracts(session, now=now)
        notifications_pruned = await prune_old_notifications(session, now=now)
        perishable_decay = await settle_all_perishable_decay(session, now=now)
        building_decay = await settle_all_building_decay(session, now=now)
        shops_restocked = await restock_shops(session, now=now)
        projects_completed = await settle_project_completions(session, now=now)
        return {
            "bankruptcies": bankruptcies,
            "companies_revalued": companies_revalued,
            "contracts_expired": contracts_expired,
            "notifications_pruned": notifications_pruned,
            "perishable_decay": perishable_decay,
            "building_decay": building_decay,
            "shops_restocked": shops_restocked,
            "projects_completed": projects_completed,
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
    async with acquire_housekeeping_slot():
        async with async_session() as session:
            summary = await run_housekeeping_sweep(
                session,
                now=now,
                tick_number=tick_number,
                trigger_kind="scheduled",
            )
            await session.commit()
            return summary


async def run_housekeeping_sweep(
    session: AsyncSession,
    *,
    now: datetime | None = None,
    tick_number: int | None = None,
    trigger_kind: str = "scheduled",
    execution_job_id: int | None = None,
) -> dict:
    """Run one housekeeping sweep against a provided session."""
    return await _execute_housekeeping_sweep(
        session,
        now=_coerce_now(now),
        requested_tick=tick_number,
        trigger_kind=trigger_kind,
        execution_job_id=execution_job_id,
    )


async def _scheduled_sweep_due(session: AsyncSession, *, now: datetime) -> bool:
    state = await _get_or_create_game_state(session)
    interval_seconds = max(int(state.tick_interval_seconds or settings.TICK_INTERVAL_SECONDS), 1)
    if state.last_tick_at is None:
        return True
    last_tick_at = _normalize_timestamp(state.last_tick_at, now)
    return (now - last_tick_at).total_seconds() >= interval_seconds


async def run_housekeeping_iteration(*, now: datetime | None = None, session_factory=async_session) -> dict:
    effective_now = _coerce_now(now)
    async with acquire_housekeeping_slot():
        async with session_factory() as session:
            backfill_summary = await schedule_missed_housekeeping_backfills(session, now=effective_now)
            await session.commit()

        execution_jobs = await run_due_execution_jobs(
            now=effective_now,
            limit=int(settings.EXECUTION_JOB_DRAIN_LIMIT),
            session_factory=session_factory,
        )

        scheduled_sweep = None
        async with session_factory() as session:
            if await _scheduled_sweep_due(session, now=effective_now):
                scheduled_sweep = await run_housekeeping_sweep(
                    session,
                    now=effective_now,
                    trigger_kind="scheduled",
                )
                await session.commit()
            else:
                await session.rollback()

        return {
            "backfill": backfill_summary,
            "execution_jobs": execution_jobs,
            "scheduled_sweep": scheduled_sweep,
        }


async def run_tick_loop(stop_event: asyncio.Event | None = None) -> None:
    """Compatibility loop entrypoint backed by housekeeping sweeps."""
    if stop_event is None:
        stop_event = asyncio.Event()

    async with async_session() as session:
        await _mark_runtime_running(session, now=_coerce_now())
        await session.commit()

    try:
        while not stop_event.is_set():
            await run_housekeeping_iteration()
            try:
                await asyncio.wait_for(
                    stop_event.wait(),
                    timeout=float(settings.TICK_INTERVAL_SECONDS),
                )
            except asyncio.TimeoutError:
                continue
    finally:
        async with async_session() as session:
            await _mark_runtime_stopped(session)
            await session.commit()


async def record_price_history(current_tick: int) -> dict:
    """Compatibility helper for the old tick engine API."""
    async with acquire_housekeeping_slot():
        async with async_session() as session:
            summary = await match_all_resources(session, current_tick=current_tick)
            await session.commit()
            return {
                "current_tick": current_tick,
                "market_matching": summary,
                "mode": "inline_trade_candles",
            }
