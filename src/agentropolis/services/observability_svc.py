"""Local-preview observability snapshot helpers."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.middleware.metrics import get_request_metrics_snapshot
from agentropolis.models import Agent, Company, GameState, HousekeepingLog, PreviewAgentPolicy
from agentropolis.services.concurrency import get_concurrency_snapshot
from agentropolis.services.economy_governance import build_economy_health_thresholds
from agentropolis.services.execution_svc import build_execution_snapshot


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
    preview_budget_thresholds = thresholds["preview_budget"]
    execution_snapshot = await build_execution_snapshot(session, recent_limit=10)
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
                    "trigger_kind": latest_housekeeping.trigger_kind,
                    "execution_job_id": latest_housekeeping.execution_job_id,
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
        "execution": execution_snapshot,
    }
