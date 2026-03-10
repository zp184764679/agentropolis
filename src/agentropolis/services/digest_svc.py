"""Digest and dashboard aggregation service."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.config import settings
from agentropolis.models import AgentDecisionLog, HousekeepingLog, Notification, PriceHistory, Resource
from agentropolis.services.agent_svc import get_agent_status
from agentropolis.services.autopilot import acknowledge_digest, ensure_autonomy_state, get_autonomy_config
from agentropolis.services.company_svc import get_agent_company
from agentropolis.services.decision_log_svc import get_decision_analysis
from agentropolis.services.goal_svc import list_goals
from agentropolis.services.world_svc import get_travel_status


def _coerce_now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(UTC)
    if now.tzinfo is None:
        return now.replace(tzinfo=UTC)
    return now


async def _market_movers(
    session: AsyncSession,
    *,
    limit: int,
) -> list[dict]:
    ticks = (
        await session.execute(
            select(PriceHistory.tick).distinct().order_by(PriceHistory.tick.desc()).limit(2)
        )
    ).scalars().all()
    if len(ticks) < 2:
        return []
    latest_tick, previous_tick = int(ticks[0]), int(ticks[1])
    result = await session.execute(
        select(
            PriceHistory.resource_id,
            func.max(case((PriceHistory.tick == previous_tick, PriceHistory.close))).label("previous_close"),
            func.max(case((PriceHistory.tick == latest_tick, PriceHistory.close))).label("current_close"),
        )
        .where(PriceHistory.tick.in_((previous_tick, latest_tick)))
        .group_by(PriceHistory.resource_id)
    )
    movers = []
    for resource_id, previous_close, current_close in result.all():
        if previous_close in (None, 0) or current_close is None:
            continue
        delta_pct = ((float(current_close) - float(previous_close)) / float(previous_close)) * 100.0
        ticker = (
            await session.execute(
                select(Resource.ticker).where(Resource.id == resource_id)
            )
        ).scalar_one_or_none()
        movers.append(
            {
                "ticker": ticker or str(resource_id),
                "previous_close": float(previous_close),
                "current_close": float(current_close),
                "delta_pct": round(delta_pct, 3),
            }
        )
    movers.sort(key=lambda item: abs(item["delta_pct"]), reverse=True)
    return movers[:limit]


async def build_digest(
    session: AsyncSession,
    agent_id: int,
    *,
    now: datetime | None = None,
) -> dict:
    timestamp = _coerce_now(now)
    state = await ensure_autonomy_state(session, agent_id)
    since = state.last_digest_at

    notification_stmt = (
        select(Notification)
        .where(Notification.agent_id == agent_id)
        .order_by(Notification.created_at.desc())
        .limit(settings.AUTOPILOT_DIGEST_MAX_ITEMS)
    )
    if since is not None:
        notification_stmt = notification_stmt.where(Notification.created_at > since)
    notifications = list((await session.execute(notification_stmt)).scalars().all())

    unread_count = int(
        (
            await session.execute(
                select(func.count(Notification.id)).where(
                    Notification.agent_id == agent_id,
                    Notification.is_read.is_(False),
                )
            )
        ).scalar_one()
        or 0
    )

    decision_stmt = (
        select(AgentDecisionLog)
        .where(AgentDecisionLog.agent_id == agent_id)
        .order_by(AgentDecisionLog.created_at.desc())
        .limit(settings.AUTOPILOT_DIGEST_MAX_ITEMS)
    )
    if since is not None:
        decision_stmt = decision_stmt.where(AgentDecisionLog.created_at > since)
    decisions = list((await session.execute(decision_stmt)).scalars().all())

    goals = await list_goals(session, agent_id)
    if since is not None:
        goals = [
            goal
            for goal in goals
            if goal["updated_at"] is not None and goal["updated_at"] > since.isoformat()
        ]

    return {
        "agent_id": agent_id,
        "generated_at": timestamp.isoformat(),
        "since": since.isoformat() if since is not None else None,
        "unread_count": unread_count,
        "notifications": [
            {
                "notification_id": notification.id,
                "event_type": notification.event_type,
                "title": notification.title,
                "body": notification.body,
                "is_read": bool(notification.is_read),
                "created_at": notification.created_at.isoformat(),
            }
            for notification in notifications
        ],
        "recent_decisions": [
            {
                "id": entry.id,
                "decision_type": entry.decision_type.value,
                "summary": entry.summary,
                "created_at": entry.created_at.isoformat(),
                "resolved_at": entry.resolved_at.isoformat() if entry.resolved_at else None,
                "outcome_summary": entry.outcome_summary,
            }
            for entry in decisions
        ],
        "goal_updates": [
            {
                "goal_id": goal["goal_id"],
                "goal_type": goal["goal_type"],
                "status": goal["status"],
                "progress": goal["progress"],
                "completed_at": goal["completed_at"],
            }
            for goal in goals[: settings.AUTOPILOT_DIGEST_MAX_ITEMS]
        ],
        "market_movers": await _market_movers(
            session,
            limit=settings.AUTOPILOT_DIGEST_MAX_ITEMS,
        ),
    }


async def acknowledge_digest_for_agent(
    session: AsyncSession,
    agent_id: int,
    *,
    now: datetime | None = None,
) -> dict:
    payload = await acknowledge_digest(session, agent_id, now=now)
    unread_count = int(
        (
            await session.execute(
                select(func.count(Notification.id)).where(
                    Notification.agent_id == agent_id,
                    Notification.is_read.is_(False),
                )
            )
        ).scalar_one()
        or 0
    )
    payload["unread_count"] = unread_count
    return payload


async def build_dashboard(
    session: AsyncSession,
    agent_id: int,
    *,
    now: datetime | None = None,
) -> dict:
    timestamp = _coerce_now(now)
    state = await ensure_autonomy_state(session, agent_id)
    agent = await get_agent_status(session, agent_id, now=timestamp)
    company = await get_agent_company(session, agent_id)
    travel = await get_travel_status(session, agent_id)
    goals = await list_goals(session, agent_id)
    decision_summary = await get_decision_analysis(session, agent_id)
    digest = await build_digest(session, agent_id, now=timestamp)
    autonomy = await get_autonomy_config(session, agent_id)

    return {
        "generated_at": timestamp.isoformat(),
        "agent": agent,
        "company": company,
        "travel": travel,
        "autonomy": autonomy,
        "goals": goals,
        "digest_unread_count": digest["unread_count"],
        "latest_digest_at": state.last_digest_at.isoformat() if state.last_digest_at else None,
        "decision_summary": decision_summary,
    }


async def build_digest_housekeeping_summary(
    session: AsyncSession,
    *,
    now: datetime | None = None,
) -> dict:
    timestamp = _coerce_now(now)
    latest_log = (
        await session.execute(
            select(HousekeepingLog).order_by(HousekeepingLog.id.desc()).limit(1)
        )
    ).scalar_one_or_none()
    return {
        "generated_at": timestamp.isoformat(),
        "last_sweep_id": latest_log.id if latest_log is not None else None,
        "last_sweep_tick": latest_log.sweep_count if latest_log is not None else None,
    }
