"""Local-preview observability snapshot helpers."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.middleware.metrics import get_request_metrics_snapshot
from agentropolis.mcp.metrics import get_mcp_metrics_snapshot
from agentropolis.models import (
    Agent,
    Company,
    GameState,
    HousekeepingLog,
    Notification,
    Order,
    OrderStatus,
    PreviewAgentPolicy,
    TaxRecord,
    TransportOrder,
    TransportStatus,
    Worker,
)
from agentropolis.services.concurrency import get_concurrency_snapshot
from agentropolis.services.economy_governance import build_economy_health_thresholds
from agentropolis.services.execution_svc import build_execution_snapshot


def _utc_now() -> datetime:
    return datetime.now(UTC)


async def _count_agents_below(session: AsyncSession, field_name: str, threshold: float) -> int:
    field = getattr(Agent, field_name)
    return int(
        (
            await session.execute(
                select(func.count(Agent.id)).where(
                    Agent.is_active.is_(True),
                    Agent.is_alive.is_(True),
                    field < threshold,
                )
            )
        ).scalar_one()
        or 0
    )


def _isoformat(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()


async def _build_agent_behavior_snapshot(
    session: AsyncSession,
    *,
    limit: int,
) -> tuple[list[HousekeepingLog], dict]:
    result = await session.execute(
        select(HousekeepingLog).order_by(HousekeepingLog.sweep_count.desc()).limit(limit)
    )
    logs = list(result.scalars().all())

    reflex_actions = 0
    reflex_failures = 0
    reflex_notifications = 0
    standing_order_buys = 0
    standing_order_sells = 0
    standing_order_skipped_no_company = 0
    standing_order_skipped_budget = 0
    standing_order_failures = 0
    goals_processed = 0
    goals_completed = 0

    for log in logs:
        autonomy = dict(log.autonomy_summary or {})
        reflex = dict(autonomy.get("reflex") or {})
        standing = dict(autonomy.get("standing_orders") or {})
        goals = dict(autonomy.get("goals") or {})

        reflex_actions += int(reflex.get("actions") or 0)
        reflex_failures += int(reflex.get("failures") or 0)
        reflex_notifications += int(reflex.get("notifications") or 0)
        standing_order_buys += int(standing.get("buy_orders_created") or 0)
        standing_order_sells += int(standing.get("sell_orders_created") or 0)
        standing_order_skipped_no_company += int(standing.get("skipped_no_company") or 0)
        standing_order_skipped_budget += int(standing.get("skipped_budget") or 0)
        standing_order_failures += int(standing.get("failures") or 0)
        goals_processed += int(goals.get("goals_processed") or 0)
        goals_completed += int(goals.get("completed_now") or 0)

    recent_sweeps = [
        {
            "sweep_count": log.sweep_count,
            "trigger_kind": log.trigger_kind,
            "duration_seconds": log.duration_seconds,
            "error_count": log.error_count,
            "completed_at": _isoformat(log.completed_at),
        }
        for log in logs
    ]

    return logs, {
        "window_sweeps": len(logs),
        "reflex_actions": reflex_actions,
        "reflex_failures": reflex_failures,
        "reflex_notifications": reflex_notifications,
        "standing_order_buy_orders": standing_order_buys,
        "standing_order_sell_orders": standing_order_sells,
        "standing_order_skipped_no_company": standing_order_skipped_no_company,
        "standing_order_skipped_budget": standing_order_skipped_budget,
        "standing_order_failures": standing_order_failures,
        "goals_processed": goals_processed,
        "goals_completed": goals_completed,
        "recent_sweeps": recent_sweeps,
        "average_sweep_duration_seconds": round(
            sum(float(log.duration_seconds or 0.0) for log in logs) / len(logs),
            6,
        )
        if logs
        else 0.0,
    }


async def build_observability_snapshot(session: AsyncSession) -> dict:
    thresholds = build_economy_health_thresholds()
    now = _utc_now()
    state = await session.get(GameState, 1)

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
    open_orders = int(
        (
            await session.execute(
                select(func.count(Order.id)).where(
                    Order.status.in_(
                        (
                            OrderStatus.OPEN.value,
                            OrderStatus.PARTIALLY_FILLED.value,
                        )
                    )
                )
            )
        ).scalar_one()
        or 0
    )
    transports_in_flight = int(
        (
            await session.execute(
                select(func.count(TransportOrder.id)).where(
                    TransportOrder.status.in_(
                        (
                            TransportStatus.PENDING.value,
                            TransportStatus.IN_TRANSIT.value,
                        )
                    )
                )
            )
        ).scalar_one()
        or 0
    )
    overdue_transports = int(
        (
            await session.execute(
                select(func.count(TransportOrder.id)).where(
                    TransportOrder.status.in_(
                        (
                            TransportStatus.PENDING.value,
                            TransportStatus.IN_TRANSIT.value,
                        )
                    ),
                    TransportOrder.arrives_at.is_not(None),
                    TransportOrder.arrives_at < now,
                )
            )
        ).scalar_one()
        or 0
    )
    unread_notifications = int(
        (
            await session.execute(
                select(func.count(Notification.id)).where(Notification.is_read.is_(False))
            )
        ).scalar_one()
        or 0
    )
    low_hunger_agents = await _count_agents_below(
        session,
        "hunger",
        float(thresholds["agent_vitals"]["warning_below"]),
    )
    low_thirst_agents = await _count_agents_below(
        session,
        "thirst",
        float(thresholds["agent_vitals"]["warning_below"]),
    )
    low_energy_agents = await _count_agents_below(
        session,
        "energy",
        float(thresholds["agent_vitals"]["warning_below"]),
    )
    critical_hunger_agents = await _count_agents_below(
        session,
        "hunger",
        float(thresholds["agent_vitals"]["critical_below"]),
    )
    critical_thirst_agents = await _count_agents_below(
        session,
        "thirst",
        float(thresholds["agent_vitals"]["critical_below"]),
    )
    critical_energy_agents = await _count_agents_below(
        session,
        "energy",
        float(thresholds["agent_vitals"]["critical_below"]),
    )
    low_worker_satisfaction_companies = int(
        (
            await session.execute(
                select(func.count(Worker.company_id)).where(
                    Worker.satisfaction < float(thresholds["worker_satisfaction"]["warning_below"])
                )
            )
        ).scalar_one()
        or 0
    )
    critical_worker_satisfaction_companies = int(
        (
            await session.execute(
                select(func.count(Worker.company_id)).where(
                    Worker.satisfaction < float(thresholds["worker_satisfaction"]["critical_below"])
                )
            )
        ).scalar_one()
        or 0
    )
    tax_collected_total = int(
        (
            await session.execute(select(func.coalesce(func.sum(TaxRecord.amount), 0)))
        ).scalar_one()
        or 0
    )

    inflation_index = float(state.inflation_index) if state is not None else 1.0
    execution_snapshot = await build_execution_snapshot(session, recent_limit=10)
    latest_housekeeping = execution_snapshot["housekeeping_phase_contract"]["latest_sweep"]
    recent_logs, agent_behavior = await _build_agent_behavior_snapshot(session, limit=10)
    mcp_metrics = get_mcp_metrics_snapshot()

    preview_budget_thresholds = thresholds["preview_budget"]
    policy_result = await session.execute(select(PreviewAgentPolicy))
    policies = list(policy_result.scalars().all())
    exhausted_family_budget_policies = 0
    exhausted_operation_budget_policies = 0
    low_spend_budget_policies = 0
    critical_spend_budget_policies = 0
    for policy in policies:
        family_budgets = {
            key: int(value)
            for key, value in (policy.family_budgets or {}).items()
        }
        operation_budgets = {
            key: int(value)
            for key, value in (policy.operation_budgets or {}).items()
        }
        if any(value <= 0 for value in family_budgets.values()):
            exhausted_family_budget_policies += 1
        if any(value <= 0 for value in operation_budgets.values()):
            exhausted_operation_budget_policies += 1
        if policy.remaining_spend_budget is not None:
            remaining = int(policy.remaining_spend_budget)
            if remaining <= preview_budget_thresholds["warning_remaining_below"]:
                low_spend_budget_policies += 1
            if remaining <= preview_budget_thresholds["critical_remaining_below"]:
                critical_spend_budget_policies += 1

    return {
        "requests": get_request_metrics_snapshot(),
        "mcp": mcp_metrics,
        "concurrency": get_concurrency_snapshot(),
        "preview_policy": {
            "policies_total": len(policies),
            "policies_with_operation_budgets": sum(
                1 for policy in policies if bool(policy.operation_budgets)
            ),
            "policies_with_denied_operations": sum(
                1 for policy in policies if bool(policy.denied_operations)
            ),
            "policies_with_spending_caps": sum(
                1
                for policy in policies
                if policy.max_spend_per_operation is not None
                or policy.remaining_spend_budget is not None
            ),
            "exhausted_family_budget_policies": exhausted_family_budget_policies,
            "exhausted_operation_budget_policies": exhausted_operation_budget_policies,
            "low_spend_budget_policies": low_spend_budget_policies,
            "critical_spend_budget_policies": critical_spend_budget_policies,
            "thresholds": preview_budget_thresholds,
        },
        "economy": {
            "active_agents": active_agents,
            "active_companies": active_companies,
            "total_currency_supply": int(state.total_currency_supply) if state is not None else 0,
            "inflation_index": inflation_index,
            "open_orders": open_orders,
            "transports_in_flight": transports_in_flight,
            "overdue_transports": overdue_transports,
            "unread_notifications": unread_notifications,
            "low_hunger_agents": low_hunger_agents,
            "low_thirst_agents": low_thirst_agents,
            "low_energy_agents": low_energy_agents,
            "critical_hunger_agents": critical_hunger_agents,
            "critical_thirst_agents": critical_thirst_agents,
            "critical_energy_agents": critical_energy_agents,
            "low_worker_satisfaction_companies": low_worker_satisfaction_companies,
            "critical_worker_satisfaction_companies": critical_worker_satisfaction_companies,
            "source_sink_proxy": {
                "tax_collected_total": tax_collected_total,
            },
            "stuck_work_signals": {
                "open_orders": open_orders,
                "overdue_transports": overdue_transports,
                "pending_execution_jobs": int(execution_snapshot["counts"]["pending_or_accepted"]),
                "retryable_jobs": int(execution_snapshot["lag"]["retryable_jobs"]),
            },
            "thresholds": thresholds,
            "health_flags": {
                "inflation_warning": inflation_index >= thresholds["inflation_index"]["warning_above"],
                "inflation_critical": inflation_index >= thresholds["inflation_index"]["critical_above"],
                "starvation_warning": any(
                    value > 0
                    for value in (
                        low_hunger_agents,
                        low_thirst_agents,
                        low_energy_agents,
                    )
                ),
                "starvation_critical": any(
                    value > 0
                    for value in (
                        critical_hunger_agents,
                        critical_thirst_agents,
                        critical_energy_agents,
                    )
                ),
                "worker_satisfaction_warning": low_worker_satisfaction_companies > 0,
                "worker_satisfaction_critical": critical_worker_satisfaction_companies > 0,
                "stuck_work_present": any(
                    value > 0
                    for value in (
                        overdue_transports,
                        execution_snapshot["counts"]["pending_or_accepted"],
                        execution_snapshot["lag"]["retryable_jobs"],
                    )
                ),
            },
        },
        "agent_behavior": agent_behavior,
        "housekeeping": {
            "latest_sweep": latest_housekeeping,
            "recent_sweeps": agent_behavior["recent_sweeps"],
            "average_duration_seconds_recent": agent_behavior["average_sweep_duration_seconds"],
            "runtime_tick": int(state.current_tick) if state is not None else 0,
            "tick_interval_seconds": int(state.tick_interval_seconds) if state is not None else 0,
            "is_running": bool(state.is_running) if state is not None else False,
            "recent_sweep_count": len(recent_logs),
        },
        "execution": execution_snapshot,
    }
