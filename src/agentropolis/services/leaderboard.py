"""Leaderboard service - ranking and market analysis.

Provides:
- Company rankings by various metrics (net_worth, balance, workers, buildings)
- Market analysis per resource (supply/demand ratio, trend, averages)
- Trade history queries
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from agentropolis.models import (
    Building,
    Company,
    Order,
    OrderStatus,
    OrderType,
    PriceHistory,
    Resource,
    Trade,
)


async def get_leaderboard(
    session: AsyncSession,
    metric: str = "net_worth",
    limit: int | None = 20,
) -> list[dict]:
    """Get ranked leaderboard.

    Metrics: "net_worth", "balance", "workers", "buildings"
    Returns: [{"rank", "company_name", "net_worth", "balance", "worker_count", "building_count"}]
    """
    building_counts = (
        select(Building.company_id, func.count(Building.id).label("building_count"))
        .group_by(Building.company_id)
        .subquery()
    )

    metric_columns = {
        "net_worth": Company.net_worth,
        "balance": Company.balance,
        "workers": func.coalesce(Company.npc_worker_count, 0),
        "buildings": func.coalesce(building_counts.c.building_count, 0),
    }
    normalized_metric = metric.lower()
    if normalized_metric not in metric_columns:
        raise ValueError(f"Unsupported leaderboard metric: {metric}")

    stmt = (
        select(
            Company.id,
            Company.name,
            Company.net_worth,
            Company.balance,
            func.coalesce(Company.npc_worker_count, 0).label("worker_count"),
            func.coalesce(building_counts.c.building_count, 0).label("building_count"),
        )
        .outerjoin(building_counts, building_counts.c.company_id == Company.id)
        .where(Company.is_active.is_(True))
        .order_by(metric_columns[normalized_metric].desc(), Company.name.asc())
    )
    if limit is not None:
        stmt = stmt.limit(limit)

    result = await session.execute(stmt)
    return [
        {
            "company_id": company_id,
            "rank": index,
            "company_name": company_name,
            "net_worth": int(net_worth or 0),
            "balance": int(balance or 0),
            "worker_count": int(worker_count or 0),
            "building_count": int(building_count or 0),
        }
        for index, (company_id, company_name, net_worth, balance, worker_count, building_count) in enumerate(
            result.all(),
            start=1,
        )
    ]


async def get_market_analysis(session: AsyncSession, resource_ticker: str) -> dict:
    """Analyze market conditions for a resource.

    Returns: {
        "ticker", "avg_price_10t", "price_trend" (rising/falling/stable),
        "supply_demand_ratio", "total_buy_volume", "total_sell_volume", "trade_count_10t"
    }
    """
    resource = (
        await session.execute(select(Resource).where(Resource.ticker == resource_ticker))
    ).scalar_one_or_none()
    if resource is None:
        raise ValueError(f"Unknown resource ticker: {resource_ticker}")

    history_rows = (
        await session.execute(
            select(PriceHistory)
            .where(PriceHistory.resource_id == resource.id)
            .order_by(PriceHistory.tick.desc())
            .limit(10)
        )
    ).scalars().all()
    history = list(reversed(history_rows))

    avg_price = None
    trend = "stable"
    if history:
        closes = [int(row.close) for row in history]
        avg_price = round(sum(closes) / len(closes))
        if len(closes) >= 2:
            delta = closes[-1] - closes[0]
            if delta > 0:
                trend = "rising"
            elif delta < 0:
                trend = "falling"

    open_order_statuses = (OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED)
    buy_volume = int(
        (
            await session.execute(
                select(func.coalesce(func.sum(Order.remaining), 0))
                .where(
                    Order.resource_id == resource.id,
                    Order.order_type == OrderType.BUY,
                    Order.status.in_(open_order_statuses),
                )
            )
        ).scalar_one()
        or 0
    )
    sell_volume = int(
        (
            await session.execute(
                select(func.coalesce(func.sum(Order.remaining), 0))
                .where(
                    Order.resource_id == resource.id,
                    Order.order_type == OrderType.SELL,
                    Order.status.in_(open_order_statuses),
                )
            )
        ).scalar_one()
        or 0
    )

    latest_trade_tick = (
        await session.execute(
            select(func.max(Trade.tick_executed)).where(Trade.resource_id == resource.id)
        )
    ).scalar_one()
    trade_count = 0
    if latest_trade_tick is not None:
        trade_count = int(
            (
                await session.execute(
                    select(func.count(Trade.id)).where(
                        Trade.resource_id == resource.id,
                        Trade.tick_executed >= max(int(latest_trade_tick) - 9, 0),
                    )
                )
            ).scalar_one()
            or 0
        )

    return {
        "ticker": resource.ticker,
        "avg_price_10t": avg_price,
        "price_trend": trend,
        "supply_demand_ratio": (buy_volume / sell_volume) if sell_volume > 0 else None,
        "total_buy_volume": buy_volume,
        "total_sell_volume": sell_volume,
        "trade_count_10t": trade_count,
    }


async def get_trade_history(
    session: AsyncSession,
    resource_ticker: str | None = None,
    ticks: int = 10,
) -> list[dict]:
    """Get recent trade history, optionally filtered by resource.

    Returns: [{"trade_id", "buyer", "seller", "resource", "price", "quantity", "tick"}]
    """
    buyer = aliased(Company)
    seller = aliased(Company)

    resource_id: int | None = None
    if resource_ticker is not None:
        resource = (
            await session.execute(select(Resource).where(Resource.ticker == resource_ticker))
        ).scalar_one_or_none()
        if resource is None:
            raise ValueError(f"Unknown resource ticker: {resource_ticker}")
        resource_id = resource.id

    latest_tick_stmt = select(func.max(Trade.tick_executed))
    if resource_id is not None:
        latest_tick_stmt = latest_tick_stmt.where(Trade.resource_id == resource_id)
    latest_tick = (await session.execute(latest_tick_stmt)).scalar_one()
    if latest_tick is None:
        return []

    stmt = (
        select(
            Trade.id,
            buyer.name,
            seller.name,
            Resource.ticker,
            Trade.price,
            Trade.quantity,
            Trade.tick_executed,
        )
        .join(buyer, buyer.id == Trade.buyer_id)
        .join(seller, seller.id == Trade.seller_id)
        .join(Resource, Resource.id == Trade.resource_id)
        .where(Trade.tick_executed >= max(int(latest_tick) - max(ticks, 1) + 1, 0))
        .order_by(Trade.tick_executed.desc(), Trade.id.desc())
    )
    if resource_id is not None:
        stmt = stmt.where(Trade.resource_id == resource_id)

    result = await session.execute(stmt)
    return [
        {
            "trade_id": trade_id,
            "buyer": buyer_name,
            "seller": seller_name,
            "resource": ticker,
            "price": int(price or 0),
            "quantity": int(quantity or 0),
            "tick": int(tick_executed),
        }
        for trade_id, buyer_name, seller_name, ticker, price, quantity, tick_executed in result.all()
    ]


async def get_price_history(
    session: AsyncSession, resource_ticker: str, ticks: int = 50
) -> list[dict]:
    """Get OHLCV price history for a resource.

    Returns: [{"tick", "open", "high", "low", "close", "volume"}]
    """
    resource = (
        await session.execute(select(Resource).where(Resource.ticker == resource_ticker))
    ).scalar_one_or_none()
    if resource is None:
        raise ValueError(f"Unknown resource ticker: {resource_ticker}")

    result = await session.execute(
        select(PriceHistory)
        .where(PriceHistory.resource_id == resource.id)
        .order_by(PriceHistory.tick.desc())
        .limit(max(ticks, 1))
    )
    history_rows = list(reversed(result.scalars().all()))
    return [
        {
            "tick": int(row.tick),
            "open": int(row.open),
            "high": int(row.high),
            "low": int(row.low),
            "close": int(row.close),
            "volume": int(row.volume),
        }
        for row in history_rows
    ]
