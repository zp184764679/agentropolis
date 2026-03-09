"""Decision Log service - record, resolve, and analyze agent decisions.

Every significant action (trade, combat, production, travel) is logged with
context at decision time. A background resolve step fills in the outcome
so players can review what worked and what didn't.
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.models.decision_log import AgentDecisionLog, DecisionType
from agentropolis.models.trade import Trade

logger = logging.getLogger(__name__)

# How long to wait before resolving a decision outcome
RESOLVE_DELAY_SECONDS = 600  # 10 minutes


# ─── Record ────────────────────────────────────────────────────────────────


async def record_decision(
    session: AsyncSession,
    agent_id: int,
    decision_type: DecisionType,
    summary: str,
    *,
    context_snapshot: dict | None = None,
    reference_type: str | None = None,
    reference_id: int | None = None,
    region_id: int | None = None,
    amount_copper: int = 0,
) -> AgentDecisionLog:
    """Record a new decision log entry. Called from service hooks."""
    entry = AgentDecisionLog(
        agent_id=agent_id,
        decision_type=decision_type,
        summary=summary,
        context_snapshot=context_snapshot,
        reference_type=reference_type,
        reference_id=reference_id,
        region_id=region_id,
        amount_copper=amount_copper,
    )
    session.add(entry)
    await session.flush()
    return entry


# ─── Resolve Outcomes ──────────────────────────────────────────────────────


async def resolve_pending_decisions(
    session: AsyncSession,
    now: datetime | None = None,
) -> int:
    """Resolve unresolved decisions whose resolve window has passed.

    For TRADE decisions: check if the price moved favorably.
    For COMBAT decisions: mark based on contract result.
    For others: mark as neutral.

    Returns count of resolved decisions.
    """
    if now is None:
        now = datetime.now(UTC)

    cutoff = now - timedelta(seconds=RESOLVE_DELAY_SECONDS)

    result = await session.execute(
        select(AgentDecisionLog).where(
            AgentDecisionLog.resolved_at.is_(None),
            AgentDecisionLog.created_at <= cutoff,
        ).limit(200)  # batch limit
    )
    pending = list(result.scalars().all())

    resolved_count = 0
    for entry in pending:
        resolved = await _resolve_one(session, entry, now)
        if resolved:
            resolved_count += 1

    return resolved_count


async def _resolve_one(
    session: AsyncSession,
    entry: AgentDecisionLog,
    now: datetime,
) -> bool:
    """Resolve a single decision entry based on its type."""
    if entry.decision_type == DecisionType.TRADE:
        return await _resolve_trade(session, entry, now)
    elif entry.decision_type == DecisionType.COMBAT:
        return _resolve_combat(entry, now)
    else:
        # For non-trade, non-combat: mark as resolved with neutral outcome
        entry.resolved_at = now
        entry.outcome_summary = "Completed"
        entry.is_profitable = None
        entry.profit_copper = 0
        return True


async def _resolve_trade(
    session: AsyncSession,
    entry: AgentDecisionLog,
    now: datetime,
) -> bool:
    """Resolve a trade decision by comparing current market price to trade price."""
    ctx = entry.context_snapshot or {}
    trade_price = ctx.get("price")
    resource_id = ctx.get("resource_id")
    region_id = entry.region_id
    order_type = ctx.get("order_type", "BUY")

    if trade_price is None or resource_id is None:
        entry.resolved_at = now
        entry.outcome_summary = "Insufficient context data"
        entry.is_profitable = None
        return True

    # Get most recent trade price for this resource in this region
    recent = await session.execute(
        select(Trade.price)
        .where(
            Trade.resource_id == resource_id,
            Trade.region_id == region_id,
        )
        .order_by(Trade.created_at.desc())
        .limit(1)
    )
    current_price = recent.scalar_one_or_none()

    if current_price is None:
        entry.resolved_at = now
        entry.outcome_summary = "No recent trades for comparison"
        entry.is_profitable = None
        return True

    quantity = ctx.get("quantity", 1)

    if order_type == "BUY":
        # Bought at trade_price, now worth current_price
        profit = (current_price - trade_price) * quantity
        entry.outcome_summary = f"Bought at {trade_price}, now {current_price} ({'+' if profit >= 0 else ''}{profit} copper)"
    else:
        # Sold at trade_price, now worth current_price
        profit = (trade_price - current_price) * quantity
        entry.outcome_summary = f"Sold at {trade_price}, now {current_price} ({'+' if profit >= 0 else ''}{profit} copper)"

    entry.resolved_at = now
    entry.profit_copper = profit
    entry.is_profitable = profit > 0
    entry.quality_score = min(100.0, max(0.0, 50.0 + profit / max(entry.amount_copper, 1) * 50))
    return True


def _resolve_combat(entry: AgentDecisionLog, now: datetime) -> bool:
    """Resolve a combat decision from context snapshot."""
    ctx = entry.context_snapshot or {}
    result = ctx.get("result")

    entry.resolved_at = now
    if result == "victory":
        entry.outcome_summary = "Victory"
        entry.is_profitable = True
        entry.profit_copper = ctx.get("reward", 0)
    elif result == "defeat":
        entry.outcome_summary = "Defeat"
        entry.is_profitable = False
        entry.profit_copper = -ctx.get("loss", 0)
    else:
        entry.outcome_summary = "Combat resolved"
        entry.is_profitable = None
    return True


# ─── Query ─────────────────────────────────────────────────────────────────


async def get_recent_decisions(
    session: AsyncSession,
    agent_id: int,
    limit: int = 50,
    decision_type: str | None = None,
) -> list[dict]:
    """Get an agent's recent decisions."""
    query = (
        select(AgentDecisionLog)
        .where(AgentDecisionLog.agent_id == agent_id)
        .order_by(AgentDecisionLog.created_at.desc())
        .limit(limit)
    )
    if decision_type:
        query = query.where(AgentDecisionLog.decision_type == DecisionType(decision_type))

    result = await session.execute(query)
    entries = result.scalars().all()

    return [_entry_to_dict(e) for e in entries]


async def get_decision_analysis(
    session: AsyncSession,
    agent_id: int,
) -> dict:
    """Analyze an agent's decision history.

    Returns per-type stats: count, win rate, avg profit, best/worst decision.
    """
    result = await session.execute(
        select(
            AgentDecisionLog.decision_type,
            func.count().label("total"),
            func.count(case((AgentDecisionLog.is_profitable == True, 1))).label("wins"),  # noqa: E712
            func.count(case((AgentDecisionLog.is_profitable == False, 1))).label("losses"),  # noqa: E712
            func.avg(AgentDecisionLog.profit_copper).label("avg_profit"),
            func.sum(AgentDecisionLog.profit_copper).label("total_profit"),
            func.max(AgentDecisionLog.profit_copper).label("best_profit"),
            func.min(AgentDecisionLog.profit_copper).label("worst_profit"),
            func.avg(AgentDecisionLog.quality_score).label("avg_quality"),
        )
        .where(
            AgentDecisionLog.agent_id == agent_id,
            AgentDecisionLog.resolved_at.is_not(None),
        )
        .group_by(AgentDecisionLog.decision_type)
    )
    rows = result.all()

    analysis = {}
    for row in rows:
        dt = row.decision_type.value if hasattr(row.decision_type, 'value') else row.decision_type
        total = row.total or 0
        wins = row.wins or 0
        analysis[dt] = {
            "total_decisions": total,
            "wins": wins,
            "losses": row.losses or 0,
            "win_rate": round(wins / total, 3) if total > 0 else 0.0,
            "avg_profit_copper": int(row.avg_profit) if row.avg_profit else 0,
            "total_profit_copper": int(row.total_profit) if row.total_profit else 0,
            "best_profit_copper": int(row.best_profit) if row.best_profit else 0,
            "worst_profit_copper": int(row.worst_profit) if row.worst_profit else 0,
            "avg_quality_score": round(float(row.avg_quality), 1) if row.avg_quality else None,
        }

    # Overall stats
    total_decisions = sum(a["total_decisions"] for a in analysis.values())
    total_wins = sum(a["wins"] for a in analysis.values())
    total_profit = sum(a["total_profit_copper"] for a in analysis.values())

    return {
        "agent_id": agent_id,
        "overall": {
            "total_decisions": total_decisions,
            "total_wins": total_wins,
            "overall_win_rate": round(total_wins / total_decisions, 3) if total_decisions > 0 else 0.0,
            "total_profit_copper": total_profit,
        },
        "by_type": analysis,
    }


# ─── Helpers ───────────────────────────────────────────────────────────────


def _entry_to_dict(entry: AgentDecisionLog) -> dict:
    return {
        "id": entry.id,
        "decision_type": entry.decision_type.value,
        "summary": entry.summary,
        "context_snapshot": entry.context_snapshot,
        "reference_type": entry.reference_type,
        "reference_id": entry.reference_id,
        "region_id": entry.region_id,
        "amount_copper": entry.amount_copper,
        "created_at": entry.created_at.isoformat(),
        "resolved_at": entry.resolved_at.isoformat() if entry.resolved_at else None,
        "outcome_summary": entry.outcome_summary,
        "profit_copper": entry.profit_copper,
        "is_profitable": entry.is_profitable,
        "quality_score": entry.quality_score,
    }
