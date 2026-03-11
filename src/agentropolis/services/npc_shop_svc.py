"""NPC shop service - NPC vendor buy/sell with dynamic pricing.

Dynamic pricing: effective_price = base_price * (1 + elasticity * (1 - stock / max_stock))
Low stock -> higher prices. High stock -> lower prices.
Reputation modifier stacks on top.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.config import settings
from agentropolis.models import Agent, Inventory, Resource
from agentropolis.models.npc_shop import NpcShop


def calculate_dynamic_price(
    base_price: int,
    current_stock: int,
    max_stock: int,
    elasticity: float,
) -> int:
    """Calculate dynamic price based on stock level.

    effective_price = base_price * (1 + elasticity * (1 - stock / max_stock))
    """
    if max_stock <= 0:
        return base_price

    stock_ratio = current_stock / max_stock
    multiplier = 1.0 + elasticity * (1.0 - stock_ratio)

    # Clamp multiplier
    multiplier = max(
        settings.NPC_SHOP_MIN_PRICE_MULTIPLIER,
        min(settings.NPC_SHOP_MAX_PRICE_MULTIPLIER, multiplier),
    )

    return max(1, int(base_price * multiplier))


async def get_effective_prices(
    session: AsyncSession,
    shop_id: int,
    reputation: float = 0.0,
    agent_id: int | None = None,
) -> dict:
    """Get effective buy/sell prices for a shop considering stock, reputation, and strategy.

    When agent_id is provided, applies strategy profile and trait modifiers:
    - Low risk tolerance → NPC discount
    - ISOLATIONIST stance → NPC discount
    - MERCHANT_PRINCE trait → NPC discount
    - IRON_TRADER trait → trade tax reduction

    Returns: {"buy_prices": {ticker: price}, "sell_prices": {ticker: price}}
    """
    from agentropolis.services.reputation_svc import check_shop_access, get_reputation_modifier

    result = await session.execute(
        select(NpcShop).where(NpcShop.id == shop_id)
    )
    shop = result.scalar_one_or_none()
    if shop is None:
        raise ValueError(f"Shop {shop_id} not found")
    if not check_shop_access(reputation):
        raise ValueError("Agent reputation too low for NPC shop access")

    rep_modifier = get_reputation_modifier(reputation)

    # Strategy + trait modifier (discount for buy prices)
    strategy_modifier = 1.0
    guild_discount = 0.0
    if agent_id is not None:
        try:
            from agentropolis.services.training_hooks import get_npc_price_modifier
            strategy_modifier = await get_npc_price_modifier(session, agent_id)
        except Exception:
            strategy_modifier = 1.0
        try:
            from agentropolis.services.guild_svc import get_agent_guild_effects

            guild_effects = await get_agent_guild_effects(session, agent_id)
            guild_discount = float(guild_effects["npc_discount"])
        except Exception:
            guild_discount = 0.0

    max_stock = shop.max_stock or {}
    current_stock = shop.stock or {}
    elasticity = shop.elasticity if shop.elasticity is not None else settings.NPC_SHOP_DEFAULT_ELASTICITY

    effective_buy: dict[str, int] = {}
    for ticker, base_price in (shop.buy_prices or {}).items():
        ms = max_stock.get(ticker, 100)
        cs = current_stock.get(ticker, 0)
        dynamic = calculate_dynamic_price(base_price, cs, ms, elasticity)
        # Buy from shop: lower price = better for agent
        effective_buy[ticker] = max(
            1,
            int(dynamic * rep_modifier * strategy_modifier * (1.0 - guild_discount)),
        )

    effective_sell: dict[str, int] = {}
    for ticker, base_price in (shop.sell_prices or {}).items():
        ms = max_stock.get(ticker, 100)
        cs = current_stock.get(ticker, 0)
        dynamic = calculate_dynamic_price(base_price, cs, ms, elasticity)
        effective_sell[ticker] = max(1, int(dynamic * rep_modifier))

    return {"buy_prices": effective_buy, "sell_prices": effective_sell}


def _coerce_now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(UTC)
    if now.tzinfo is None:
        return now.replace(tzinfo=UTC)
    return now


async def _get_shop_for_update(session: AsyncSession, shop_id: int) -> NpcShop:
    shop = (
        await session.execute(
            select(NpcShop).where(NpcShop.id == shop_id).with_for_update()
        )
    ).scalar_one_or_none()
    if shop is None:
        raise ValueError(f"Shop {shop_id} not found")
    return shop


async def _get_agent_for_update(session: AsyncSession, agent_id: int) -> Agent:
    agent = (
        await session.execute(
            select(Agent).where(Agent.id == agent_id).with_for_update()
        )
    ).scalar_one_or_none()
    if agent is None:
        raise ValueError(f"Agent {agent_id} not found")
    return agent


async def _get_resource(session: AsyncSession, resource_ticker: str) -> Resource:
    resource = (
        await session.execute(select(Resource).where(Resource.ticker == resource_ticker))
    ).scalar_one_or_none()
    if resource is None:
        raise ValueError(f"Unknown resource ticker: {resource_ticker}")
    return resource


async def _get_or_create_agent_inventory_row(
    session: AsyncSession,
    *,
    agent_id: int,
    region_id: int,
    resource_id: int,
) -> Inventory:
    inventory = (
        await session.execute(
            select(Inventory)
            .where(
                Inventory.agent_id == agent_id,
                Inventory.company_id.is_(None),
                Inventory.region_id == region_id,
                Inventory.resource_id == resource_id,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if inventory is None:
        inventory = Inventory(
            agent_id=agent_id,
            company_id=None,
            region_id=region_id,
            resource_id=resource_id,
            quantity=0,
            reserved=0,
        )
        session.add(inventory)
        await session.flush()
    return inventory


async def buy_from_shop(
    session: AsyncSession,
    agent_id: int,
    shop_id: int,
    resource_ticker: str,
    quantity: int,
) -> dict:
    """Buy resources from an NPC shop.

    Returns: {"cost", "quantity", "new_balance"}
    """
    if quantity <= 0:
        raise ValueError("quantity must be greater than 0")

    from agentropolis.services.storage_svc import check_storage_available

    shop = await _get_shop_for_update(session, shop_id)
    agent = await _get_agent_for_update(session, agent_id)
    if int(agent.current_region_id) != int(shop.region_id):
        raise ValueError("Agent must be in the same region as the shop")

    prices = await get_effective_prices(
        session,
        shop_id,
        reputation=float(agent.reputation),
        agent_id=agent.id,
    )
    unit_price = prices["sell_prices"].get(resource_ticker)
    if unit_price is None:
        raise ValueError(f"Shop {shop_id} does not sell {resource_ticker}")

    stock = dict(shop.stock or {})
    available_stock = int(stock.get(resource_ticker, 0))
    if available_stock < quantity:
        raise ValueError(
            f"Insufficient stock for {resource_ticker}: need {quantity}, available {available_stock}"
        )

    has_storage = await check_storage_available(
        session,
        quantity,
        shop.region_id,
        agent_id=agent.id,
    )
    if not has_storage:
        raise ValueError(
            f"Storage capacity exceeded in region {shop.region_id}: need {quantity} additional units"
        )

    total_cost = int(unit_price) * int(quantity)
    if int(agent.personal_balance) < total_cost:
        raise ValueError(
            f"Insufficient balance: need {total_cost}, have {int(agent.personal_balance)}"
        )

    resource = await _get_resource(session, resource_ticker)
    inventory = await _get_or_create_agent_inventory_row(
        session,
        agent_id=agent.id,
        region_id=shop.region_id,
        resource_id=resource.id,
    )
    inventory.quantity = float(inventory.quantity) + float(quantity)
    stock[resource_ticker] = available_stock - quantity
    shop.stock = stock
    agent.personal_balance = int(agent.personal_balance) - total_cost
    await session.flush()

    return {
        "agent_id": agent.id,
        "shop_id": shop.id,
        "resource_ticker": resource_ticker,
        "quantity": int(quantity),
        "unit_price": int(unit_price),
        "total_cost": int(total_cost),
        "remaining_stock": int(stock[resource_ticker]),
        "new_balance": int(agent.personal_balance),
    }


async def sell_to_shop(
    session: AsyncSession,
    agent_id: int,
    shop_id: int,
    resource_ticker: str,
    quantity: int,
) -> dict:
    """Sell resources to an NPC shop.

    Returns: {"revenue", "quantity", "new_balance"}
    """
    if quantity <= 0:
        raise ValueError("quantity must be greater than 0")

    shop = await _get_shop_for_update(session, shop_id)
    agent = await _get_agent_for_update(session, agent_id)
    if int(agent.current_region_id) != int(shop.region_id):
        raise ValueError("Agent must be in the same region as the shop")

    prices = await get_effective_prices(
        session,
        shop_id,
        reputation=float(agent.reputation),
        agent_id=agent.id,
    )
    unit_price = prices["buy_prices"].get(resource_ticker)
    if unit_price is None:
        raise ValueError(f"Shop {shop_id} does not buy {resource_ticker}")

    resource = await _get_resource(session, resource_ticker)
    inventory = await _get_or_create_agent_inventory_row(
        session,
        agent_id=agent.id,
        region_id=shop.region_id,
        resource_id=resource.id,
    )
    available = float(inventory.quantity) - float(inventory.reserved)
    if available < quantity:
        raise ValueError(
            f"Insufficient {resource_ticker}: need {quantity}, available {available:.0f}"
        )

    total_earned = int(unit_price) * int(quantity)
    inventory.quantity = float(inventory.quantity) - float(quantity)

    stock = dict(shop.stock or {})
    stock[resource_ticker] = int(stock.get(resource_ticker, 0)) + int(quantity)
    shop.stock = stock
    agent.personal_balance = int(agent.personal_balance) + total_earned
    await session.flush()

    return {
        "agent_id": agent.id,
        "shop_id": shop.id,
        "resource_ticker": resource_ticker,
        "quantity": int(quantity),
        "unit_price": int(unit_price),
        "total_earned": int(total_earned),
        "remaining_stock": int(stock[resource_ticker]),
        "new_balance": int(agent.personal_balance),
    }


async def get_shops_in_region(session: AsyncSession, region_id: int) -> list[dict]:
    """Get all NPC shops in a region with effective prices."""
    result = await session.execute(
        select(NpcShop).where(NpcShop.region_id == region_id)
    )
    shops = result.scalars().all()

    return [
        {
            "shop_id": s.id,
            "region_id": s.region_id,
            "shop_type": s.shop_type,
            "buy_prices": s.buy_prices or {},
            "sell_prices": s.sell_prices or {},
            "stock": s.stock or {},
            "max_stock": s.max_stock or {},
            "elasticity": s.elasticity,
        }
        for s in shops
    ]


async def restock_shops(
    session: AsyncSession,
    now: datetime | None = None,
) -> int:
    """Restock all NPC shops based on elapsed time. Returns count restocked."""
    effective_now = _coerce_now(now)
    shops = (
        await session.execute(select(NpcShop).with_for_update())
    ).scalars().all()

    shops_restocked = 0
    for shop in shops:
        last_restock_at = _coerce_now(shop.last_restock_at or effective_now)
        elapsed_hours = max(
            0.0,
            (effective_now - last_restock_at).total_seconds() / 3600.0,
        )
        if elapsed_hours <= 0:
            continue

        stock = dict(shop.stock or {})
        max_stock = dict(shop.max_stock or {})
        changed = False
        for ticker, per_hour in (shop.restock_rate or {}).items():
            rate = float(per_hour or 0)
            if rate <= 0:
                continue
            replenish = int(rate * elapsed_hours)
            if replenish <= 0:
                continue
            current = int(stock.get(ticker, 0))
            cap = int(max_stock.get(ticker, current + replenish))
            updated = min(cap, current + replenish)
            if updated != current:
                stock[ticker] = updated
                changed = True

        if changed:
            shop.stock = stock
            shop.last_restock_at = effective_now
            shops_restocked += 1

    await session.flush()
    return shops_restocked
