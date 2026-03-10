"""Legacy scaffold market-engine stub.

This module still describes batch matching keyed to game ticks and company-owned
orders. The target plan moves toward regional, agent-aware market interactions
with a contract surface shared across REST and MCP.

Use these stubs as migration placeholders, not as the final market semantics.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.models import Order, OrderStatus, OrderType, PriceHistory, Resource, Trade


async def match_all_resources(session: AsyncSession, current_tick: int) -> dict:
    """Legacy scaffold batch-match stub. Returns trade summary.

    Args:
        session: DB session (caller manages transaction)
        current_tick: Current game tick number

    Returns:
        {"total_trades": int, "total_volume": float, "by_resource": {ticker: {trades, volume}}}
    """
    raise NotImplementedError("Issue #1: Implement market matching engine")


async def place_buy_order(
    session: AsyncSession,
    company_id: int,
    resource_ticker: str,
    quantity: float,
    price: float,
    current_tick: int,
) -> int:
    """Legacy scaffold buy-order stub. Reserves balance (price * quantity).

    Returns: order_id
    Raises: ValueError if insufficient balance or invalid resource
    """
    raise NotImplementedError("Issue #1: Implement market matching engine")


async def place_sell_order(
    session: AsyncSession,
    company_id: int,
    resource_ticker: str,
    quantity: float,
    price: float,
    current_tick: int,
) -> int:
    """Legacy scaffold sell-order stub. Reserves inventory quantity.

    Returns: order_id
    Raises: ValueError if insufficient inventory or invalid resource
    """
    raise NotImplementedError("Issue #1: Implement market matching engine")


async def cancel_order(session: AsyncSession, company_id: int, order_id: int) -> bool:
    """Legacy scaffold order-cancel stub. Unreserves balance or inventory.

    Returns: True if cancelled, False if order not found or not owned
    """
    raise NotImplementedError("Issue #1: Implement market matching engine")


async def get_market_prices(session: AsyncSession) -> list[dict]:
    """Return legacy scaffold market overview rows for all resources."""
    resources = (
        await session.execute(select(Resource).order_by(Resource.ticker.asc()))
    ).scalars().all()

    latest_trade_tick = (await session.execute(select(func.max(Trade.tick_executed)))).scalar_one()
    trade_cutoff = max(int(latest_trade_tick) - 23, 0) if latest_trade_tick is not None else None
    open_order_statuses = (OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED)

    prices: list[dict] = []
    for resource in resources:
        latest_price = (
            await session.execute(
                select(PriceHistory.close)
                .where(PriceHistory.resource_id == resource.id)
                .order_by(PriceHistory.tick.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        best_bid = (
            await session.execute(
                select(func.max(Order.price)).where(
                    Order.resource_id == resource.id,
                    Order.order_type == OrderType.BUY,
                    Order.status.in_(open_order_statuses),
                )
            )
        ).scalar_one()
        best_ask = (
            await session.execute(
                select(func.min(Order.price)).where(
                    Order.resource_id == resource.id,
                    Order.order_type == OrderType.SELL,
                    Order.status.in_(open_order_statuses),
                )
            )
        ).scalar_one()

        volume_stmt = select(func.coalesce(func.sum(Trade.quantity), 0)).where(
            Trade.resource_id == resource.id
        )
        if trade_cutoff is not None:
            volume_stmt = volume_stmt.where(Trade.tick_executed >= trade_cutoff)
        volume = (await session.execute(volume_stmt)).scalar_one()

        best_bid_value = float(best_bid) if best_bid is not None else None
        best_ask_value = float(best_ask) if best_ask is not None else None
        prices.append(
            {
                "ticker": resource.ticker,
                "name": resource.name,
                "last_price": float(latest_price) if latest_price is not None else None,
                "best_bid": best_bid_value,
                "best_ask": best_ask_value,
                "spread": (
                    best_ask_value - best_bid_value
                    if best_bid_value is not None and best_ask_value is not None
                    else None
                ),
                "volume_24h": float(volume or 0),
            }
        )
    return prices


async def get_order_book(session: AsyncSession, resource_ticker: str) -> dict:
    """Legacy scaffold order-book read implementation."""
    resource = (
        await session.execute(select(Resource).where(Resource.ticker == resource_ticker))
    ).scalar_one_or_none()
    if resource is None:
        raise ValueError(f"Unknown resource ticker: {resource_ticker}")

    result = await session.execute(
        select(
            Order.order_type,
            Order.price,
            func.coalesce(func.sum(Order.remaining), 0).label("quantity"),
            func.count(Order.id).label("order_count"),
        )
        .where(
            Order.resource_id == resource.id,
            Order.status.in_((OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED)),
        )
        .group_by(Order.order_type, Order.price)
    )

    bids: list[dict] = []
    asks: list[dict] = []
    for order_type, price, quantity, order_count in result.all():
        entry = {
            "price": float(price),
            "quantity": float(quantity or 0),
            "order_count": int(order_count or 0),
        }
        if order_type == OrderType.BUY:
            bids.append(entry)
        else:
            asks.append(entry)

    bids.sort(key=lambda item: item["price"], reverse=True)
    asks.sort(key=lambda item: item["price"])
    return {"ticker": resource.ticker, "bids": bids, "asks": asks}


async def get_my_orders(
    session: AsyncSession, company_id: int, status: str | None = "OPEN"
) -> list[dict]:
    """Legacy scaffold company-order query read implementation."""
    stmt = (
        select(
            Order.id,
            Order.order_type,
            Resource.ticker,
            Order.price,
            Order.quantity,
            Order.remaining,
            Order.status,
            Order.created_at_tick,
        )
        .join(Resource, Resource.id == Order.resource_id)
        .where(Order.company_id == company_id)
        .order_by(Order.created_at.desc(), Order.id.desc())
    )

    if status and status.upper() != "ALL":
        try:
            normalized_status = OrderStatus[status.upper()]
        except KeyError as exc:
            raise ValueError(f"Unsupported order status: {status}") from exc
        stmt = stmt.where(Order.status == normalized_status)

    result = await session.execute(stmt)
    return [
        {
            "order_id": order_id,
            "order_type": order_type.value,
            "resource": ticker,
            "price": float(price),
            "quantity": float(quantity),
            "remaining": float(remaining),
            "status": status_value.value,
            "created_at_tick": int(created_at_tick),
        }
        for order_id, order_type, ticker, price, quantity, remaining, status_value, created_at_tick in result.all()
    ]
