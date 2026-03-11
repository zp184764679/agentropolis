"""Migration-phase market engine with legacy company-auth compatibility."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from agentropolis.models import Company, GameState, Order, OrderStatus, OrderType, PriceHistory, Resource, Trade
from agentropolis.services.company_svc import credit_balance, debit_balance
from agentropolis.services.inventory_svc import (
    add_resource,
    consume_reserved_resource,
    reserve_resource,
    unreserve_resource,
)
from agentropolis.services.tax_svc import collect_tax
from agentropolis.services.treaty_effects_svc import get_trade_tax_modifier, get_treaty_between


def _coerce_now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(UTC)
    if now.tzinfo is None:
        return now.replace(tzinfo=UTC)
    return now


async def _get_company_for_update(session: AsyncSession, company_id: int) -> Company:
    company = (
        await session.execute(
            select(Company).where(Company.id == company_id).with_for_update()
        )
    ).scalar_one_or_none()
    if company is None:
        raise ValueError(f"Company {company_id} not found")
    if not company.is_active:
        raise ValueError(f"Company {company_id} is inactive")
    if company.region_id is None:
        raise ValueError(f"Company {company_id} does not have an operating region")
    return company


async def _get_resource(session: AsyncSession, resource_ticker: str) -> Resource:
    resource = (
        await session.execute(select(Resource).where(Resource.ticker == resource_ticker))
    ).scalar_one_or_none()
    if resource is None:
        raise ValueError(f"Unknown resource ticker: {resource_ticker}")
    return resource


async def _current_tick(session: AsyncSession) -> int:
    state = await session.get(GameState, 1)
    if state is None:
        return 0
    return int(state.current_tick)


async def _record_price_point(
    session: AsyncSession,
    *,
    resource_id: int,
    tick: int,
    price: float,
    quantity: float,
) -> None:
    candle = (
        await session.execute(
            select(PriceHistory)
            .where(PriceHistory.resource_id == resource_id, PriceHistory.tick == tick)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if candle is None:
        candle = PriceHistory(
            resource_id=resource_id,
            tick=tick,
            open=price,
            high=price,
            low=price,
            close=price,
            volume=quantity,
        )
        session.add(candle)
    else:
        candle.high = max(float(candle.high), price)
        candle.low = min(float(candle.low), price)
        candle.close = price
        candle.volume = float(candle.volume) + quantity
    await session.flush()


def _serialize_order(order: Order, resource_ticker: str) -> dict:
    return {
        "order_id": order.id,
        "order_type": order.order_type.value,
        "resource": resource_ticker,
        "price": float(order.price),
        "quantity": float(order.quantity),
        "remaining": float(order.remaining),
        "status": order.status.value,
        "created_at_tick": int(order.created_at_tick),
    }


async def _lock_open_orders(
    session: AsyncSession,
    *,
    region_id: int,
    resource_id: int,
    order_type: OrderType,
) -> list[Order]:
    ordering = [Order.price.desc()] if order_type == OrderType.BUY else [Order.price.asc()]
    ordering.append(Order.id.asc())
    result = await session.execute(
        select(Order)
        .where(
            Order.region_id == region_id,
            Order.resource_id == resource_id,
            Order.order_type == order_type,
            Order.status.in_((OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED)),
            Order.remaining > 0,
        )
        .order_by(*ordering)
        .with_for_update()
    )
    return list(result.scalars().all())


async def _settle_match(
    session: AsyncSession,
    *,
    buy_order: Order,
    sell_order: Order,
    tick_number: int,
) -> float:
    trade_quantity = min(float(buy_order.remaining), float(sell_order.remaining))
    maker_is_buy = buy_order.id < sell_order.id
    execution_price = float(buy_order.price if maker_is_buy else sell_order.price)
    gross_value = execution_price * trade_quantity
    resource_ticker = (
        await session.execute(select(Resource.ticker).where(Resource.id == buy_order.resource_id))
    ).scalar_one()

    buyer = await _get_company_for_update(session, buy_order.company_id)
    seller = await _get_company_for_update(session, sell_order.company_id)
    treaty_tax_modifier = 1.0
    if buyer.founder_agent_id is not None and seller.founder_agent_id is not None:
        treaties = await get_treaty_between(session, buyer.founder_agent_id, seller.founder_agent_id)
        treaty_tax_modifier = get_trade_tax_modifier(treaties)

    await consume_reserved_resource(
        session,
        seller.id,
        resource_ticker,
        trade_quantity,
        region_id=sell_order.region_id,
    )
    await add_resource(
        session,
        buyer.id,
        resource_ticker,
        trade_quantity,
        region_id=buy_order.region_id,
    )

    if float(buy_order.price) > execution_price:
        refund = (float(buy_order.price) - execution_price) * trade_quantity
        if refund > 0:
            await credit_balance(session, buyer.id, refund)

    tax_summary = await collect_tax(
        session,
        sell_order.region_id or seller.region_id,
        gross_value * treaty_tax_modifier,
        "market_trade",
        payer_company_id=seller.id,
    )
    seller_credit = gross_value - float(tax_summary["amount"])
    if seller_credit > 0:
        await credit_balance(session, seller.id, seller_credit)

    buy_order.remaining = float(buy_order.remaining) - trade_quantity
    sell_order.remaining = float(sell_order.remaining) - trade_quantity
    buy_order.status = (
        OrderStatus.FILLED if float(buy_order.remaining) <= 0 else OrderStatus.PARTIALLY_FILLED
    )
    sell_order.status = (
        OrderStatus.FILLED if float(sell_order.remaining) <= 0 else OrderStatus.PARTIALLY_FILLED
    )

    trade = Trade(
        buy_order_id=buy_order.id,
        sell_order_id=sell_order.id,
        buyer_id=buyer.id,
        seller_id=seller.id,
        resource_id=buy_order.resource_id,
        region_id=buy_order.region_id,
        price=execution_price,
        quantity=trade_quantity,
        tick_executed=tick_number,
    )
    session.add(trade)
    await session.flush()
    await _record_price_point(
        session,
        resource_id=buy_order.resource_id,
        tick=tick_number,
        price=execution_price,
        quantity=trade_quantity,
    )
    return trade_quantity


async def _match_region_resource(
    session: AsyncSession,
    *,
    region_id: int,
    resource_id: int,
    tick_number: int,
) -> dict:
    bids = await _lock_open_orders(
        session,
        region_id=region_id,
        resource_id=resource_id,
        order_type=OrderType.BUY,
    )
    asks = await _lock_open_orders(
        session,
        region_id=region_id,
        resource_id=resource_id,
        order_type=OrderType.SELL,
    )

    trades = 0
    volume = 0.0
    bid_index = 0
    ask_index = 0
    while bid_index < len(bids) and ask_index < len(asks):
        bid = bids[bid_index]
        ask = asks[ask_index]
        if float(bid.remaining) <= 0:
            bid_index += 1
            continue
        if float(ask.remaining) <= 0:
            ask_index += 1
            continue
        if float(bid.price) < float(ask.price):
            break

        settled_quantity = await _settle_match(
            session,
            buy_order=bid,
            sell_order=ask,
            tick_number=tick_number,
        )
        # Recompute actual remaining after settlement for index movement.
        trades += 1
        volume += float(settled_quantity)
        if float(bid.remaining) <= 0:
            bid_index += 1
        if float(ask.remaining) <= 0:
            ask_index += 1

    return {"trades": trades, "volume": volume}


async def match_all_resources(session: AsyncSession, current_tick: int) -> dict:
    """Match all open orders that cross for the current compatibility tick."""
    result = await session.execute(
        select(Order.region_id, Order.resource_id)
        .where(
            Order.status.in_((OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED)),
            Order.remaining > 0,
        )
        .distinct()
    )
    pairs = result.all()
    summary: dict[str, dict[str, float | int]] = {}
    total_trades = 0
    total_volume = 0.0
    for region_id, resource_id in pairs:
        if region_id is None:
            continue
        match_summary = await _match_region_resource(
            session,
            region_id=region_id,
            resource_id=resource_id,
            tick_number=current_tick,
        )
        if match_summary["trades"] <= 0:
            continue
        ticker = (
            await session.execute(select(Resource.ticker).where(Resource.id == resource_id))
        ).scalar_one()
        summary[ticker] = match_summary
        total_trades += int(match_summary["trades"])
        total_volume += float(match_summary["volume"])
    return {"total_trades": total_trades, "total_volume": total_volume, "by_resource": summary}


async def place_buy_order(
    session: AsyncSession,
    company_id: int,
    resource_ticker: str,
    quantity: float,
    price: float,
    current_tick: int | None = None,
) -> int:
    """Place a company buy order and attempt immediate matching."""
    if quantity <= 0 or price <= 0:
        raise ValueError("quantity and price must be greater than 0")

    company = await _get_company_for_update(session, company_id)
    resource = await _get_resource(session, resource_ticker)
    tick_number = int(current_tick if current_tick is not None else await _current_tick(session))
    escrow = float(quantity) * float(price)
    await debit_balance(session, company.id, escrow)

    order = Order(
        company_id=company.id,
        region_id=company.region_id,
        resource_id=resource.id,
        order_type=OrderType.BUY,
        price=price,
        quantity=quantity,
        remaining=quantity,
        status=OrderStatus.OPEN,
        created_at_tick=tick_number,
    )
    session.add(order)
    await session.flush()
    await _match_region_resource(
        session,
        region_id=company.region_id,
        resource_id=resource.id,
        tick_number=tick_number,
    )
    return order.id


async def place_sell_order(
    session: AsyncSession,
    company_id: int,
    resource_ticker: str,
    quantity: float,
    price: float,
    current_tick: int | None = None,
) -> int:
    """Place a company sell order and attempt immediate matching."""
    if quantity <= 0 or price <= 0:
        raise ValueError("quantity and price must be greater than 0")

    company = await _get_company_for_update(session, company_id)
    resource = await _get_resource(session, resource_ticker)
    tick_number = int(current_tick if current_tick is not None else await _current_tick(session))
    await reserve_resource(
        session,
        company.id,
        resource.ticker,
        quantity,
        region_id=company.region_id,
    )

    order = Order(
        company_id=company.id,
        region_id=company.region_id,
        resource_id=resource.id,
        order_type=OrderType.SELL,
        price=price,
        quantity=quantity,
        remaining=quantity,
        status=OrderStatus.OPEN,
        created_at_tick=tick_number,
    )
    session.add(order)
    await session.flush()
    await _match_region_resource(
        session,
        region_id=company.region_id,
        resource_id=resource.id,
        tick_number=tick_number,
    )
    return order.id


async def cancel_order(session: AsyncSession, company_id: int, order_id: int) -> bool:
    """Cancel an open or partially-filled order."""
    order = (
        await session.execute(
            select(Order)
            .where(Order.id == order_id, Order.company_id == company_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if order is None:
        return False
    if order.status not in (OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED):
        return False

    remaining = float(order.remaining)
    if order.order_type == OrderType.BUY and remaining > 0:
        await credit_balance(session, company_id, remaining * float(order.price))
    elif order.order_type == OrderType.SELL and remaining > 0:
        resource_ticker = (
            await session.execute(select(Resource.ticker).where(Resource.id == order.resource_id))
        ).scalar_one()
        await unreserve_resource(
            session,
            company_id,
            resource_ticker,
            remaining,
            region_id=order.region_id,
        )

    order.status = OrderStatus.CANCELLED
    order.remaining = 0
    await session.flush()
    return True


async def get_market_prices(session: AsyncSession) -> list[dict]:
    """Return market overview rows for all seeded resources."""
    resources = (
        await session.execute(select(Resource).order_by(Resource.ticker.asc()))
    ).scalars().all()
    latest_trade_tick = (await session.execute(select(func.max(Trade.tick_executed)))).scalar_one()
    trade_cutoff = max(int(latest_trade_tick) - 23, 0) if latest_trade_tick is not None else None
    open_statuses = (OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED)
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
                    Order.status.in_(open_statuses),
                )
            )
        ).scalar_one()
        best_ask = (
            await session.execute(
                select(func.min(Order.price)).where(
                    Order.resource_id == resource.id,
                    Order.order_type == OrderType.SELL,
                    Order.status.in_(open_statuses),
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
    """Return grouped bid/ask depth for one resource."""
    resource = await _get_resource(session, resource_ticker)
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
            Order.remaining > 0,
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
    """List orders for one company."""
    stmt = (
        select(Order, Resource.ticker)
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
        _serialize_order(order, ticker)
        for order, ticker in result.all()
    ]


async def get_recent_trades(
    session: AsyncSession,
    *,
    resource_ticker: str | None = None,
    ticks: int = 10,
) -> list[dict]:
    """Read recent trades for one resource or the whole market."""
    buyer = aliased(Company)
    seller = aliased(Company)
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
        .order_by(Trade.tick_executed.desc(), Trade.id.desc())
    )
    if resource_ticker is not None:
        resource = await _get_resource(session, resource_ticker)
        stmt = stmt.where(Trade.resource_id == resource.id)

    latest_tick = (
        await session.execute(select(func.max(Trade.tick_executed)))
    ).scalar_one()
    if latest_tick is not None:
        stmt = stmt.where(Trade.tick_executed >= max(int(latest_tick) - max(ticks, 1) + 1, 0))

    result = await session.execute(stmt)
    return [
        {
            "trade_id": trade_id,
            "buyer": buyer_name,
            "seller": seller_name,
            "resource": ticker,
            "price": float(price),
            "quantity": float(quantity),
            "tick": int(tick_executed),
        }
        for trade_id, buyer_name, seller_name, ticker, price, quantity, tick_executed in result.all()
    ]
