"""State snapshot, replay, and derived-state repair helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.config import settings
from agentropolis.models import (
    Agent,
    Company,
    ContractStatus,
    ExecutionJob,
    ExecutionJobStatus,
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


def _utc_now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(UTC)
    if now.tzinfo is None:
        return now.replace(tzinfo=UTC)
    return now


def build_recovery_plan() -> dict:
    return {
        "strategy": "snapshot_replay_repair",
        "local_preview_only": True,
        "backup_restore_paths": [
            {
                "path_id": "postgres_logical_dump",
                "backup": "pg_dump --format=custom --file backup.dump $DATABASE_URL",
                "restore": "pg_restore --clean --if-exists --dbname $DATABASE_URL backup.dump",
                "when_to_use": "before destructive migrations or manual repair on a PostgreSQL runtime",
            },
            {
                "path_id": "sqlite_file_copy_preview",
                "backup": "copy the preview SQLite file before local repair/replay work",
                "restore": "replace the working SQLite file with the captured copy",
                "when_to_use": "closed-environment smoke tests and local rehearsal runs",
            },
        ],
        "replay_paths": [
            {
                "path_id": "housekeeping_replay",
                "script": "scripts/replay_housekeeping.py",
                "cli": "agentropolis replay-housekeeping",
                "mode": "direct_manual_replay",
            },
            {
                "path_id": "execution_backfill_enqueue",
                "route": "/meta/execution/jobs/housekeeping-backfill",
                "mode": "accepted_async_backfill_job",
            },
        ],
        "repair_paths": [
            {
                "repair_class": "derived_state",
                "script": "scripts/repair_derived_state.py",
                "cli": "agentropolis repair-derived-state",
                "covers": ["net_worth", "currency_supply", "inflation_index"],
            },
            {
                "repair_class": "snapshot_compare",
                "script": "scripts/export_world_snapshot.py",
                "cli": "agentropolis world-snapshot",
                "covers": ["world_state_verification", "before_after_diff"],
            },
        ],
        "migration_safety_boundaries": [
            "Always capture a world snapshot before destructive repair or replay work.",
            "For destructive schema/data changes, prefer restore-from-backup over down-migrations after live data mutation.",
            "Do not patch balances, inventories, or order state with ad hoc SQL unless a before/after snapshot pair is captured.",
            "Use housekeeping replay only in a controlled maintenance window and compare post-replay snapshots before widening exposure.",
        ],
        "irreversible_change_policy": [
            "Dropping tables/columns or rewriting historical economic events requires a logical backup first.",
            "Bulk deletes and historical event rewrites are restore-only operations, not hotfix-by-SQL operations.",
            "Any direct database repair must be documented with reason, operator, and before/after artifacts.",
        ],
        "incident_flow": [
            "Capture contract, observability, governance, and world snapshots.",
            "Choose between replay, derived-state repair, or restore based on drift class.",
            "Apply repair/replay on a protected runtime or maintenance window.",
            "Capture after-state artifacts and compare against the before snapshot.",
            "Only reopen preview traffic after rollout-readiness and alerts return to expected levels.",
        ],
    }


async def build_world_snapshot(
    session: AsyncSession,
    *,
    housekeeping_limit: int = 5,
) -> dict:
    captured_at = _utc_now().isoformat()
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
        "pending_execution_jobs": int(
            (
                await session.execute(
                    select(func.count(ExecutionJob.id)).where(
                        ExecutionJob.status.in_(
                            (
                                ExecutionJobStatus.ACCEPTED.value,
                                ExecutionJobStatus.PENDING.value,
                                ExecutionJobStatus.FAILED.value,
                            )
                        )
                    )
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
    latest_housekeeping = housekeeping_rows[0] if housekeeping_rows else None

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
                "trigger_kind": row.trigger_kind,
                "execution_job_id": row.execution_job_id,
                "completed_at": row.completed_at.isoformat() if row.completed_at else None,
                "duration_seconds": row.duration_seconds,
                "error_count": row.error_count,
            }
            for row in housekeeping_rows
        ],
        "recovery_markers": {
            "latest_housekeeping_trigger": latest_housekeeping.trigger_kind if latest_housekeeping else None,
            "latest_housekeeping_tick": latest_housekeeping.sweep_count if latest_housekeeping else None,
            "recommended_repair_flows": [
                "scripts/repair_derived_state.py",
                "scripts/replay_housekeeping.py",
            ],
        },
    }


async def replay_housekeeping_range(
    session: AsyncSession,
    *,
    start_tick: int,
    sweeps: int,
    now: datetime | None = None,
) -> dict:
    if start_tick <= 0:
        raise ValueError("start_tick must be > 0")
    if sweeps <= 0:
        raise ValueError("sweeps must be > 0")

    from agentropolis.services.game_engine import run_housekeeping_sweep

    effective_now = _utc_now(now)
    state = await session.get(GameState, 1)
    interval_seconds = max(int((state.tick_interval_seconds if state else None) or settings.TICK_INTERVAL_SECONDS), 1)
    summaries: list[dict] = []

    for offset in range(sweeps):
        tick_number = start_tick + offset
        replay_now = effective_now + timedelta(seconds=interval_seconds * offset)
        summary = await run_housekeeping_sweep(
            session,
            now=replay_now,
            tick_number=tick_number,
            trigger_kind="manual_replay",
        )
        summaries.append(
            {
                "tick": summary["current_tick"],
                "period_end": summary["period_end"],
                "error_count": summary["error_count"],
                "trigger_kind": summary["trigger_kind"],
            }
        )

    return {
        "trigger_kind": "manual_replay",
        "requested_start_tick": start_tick,
        "requested_sweeps": sweeps,
        "applied_sweeps": len(summaries),
        "interval_seconds": interval_seconds,
        "final_tick": summaries[-1]["tick"] if summaries else None,
        "summaries": summaries,
    }


async def repair_derived_state(session: AsyncSession) -> dict:
    companies_revalued = await recalculate_all_net_worths(session)
    economy = await update_game_state_economics(session)
    return {
        "companies_revalued": companies_revalued,
        "economy": economy,
    }
